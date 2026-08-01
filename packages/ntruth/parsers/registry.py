"""Assemblaggio del Document IR: dai file del progetto a sezioni, paragrafi e tabelle.

Il Document IR risultante e immutabile e conserva per ogni paragrafo gli offset
assoluti nel testo del file e per ogni cella le coordinate (PRD 11.3).
"""

from __future__ import annotations

from pathlib import Path

from ntruth import PARSER_VERSION
from ntruth.ingest.project import Project
from ntruth.ingest.safety import detect_injection
from ntruth.parsers.base import ParseFailure, Parser, RawBlock, RawDocument, RawTable
from ntruth.parsers.code import CodeParser
from ntruth.parsers.docx import DocxParser
from ntruth.parsers.jats import JatsParser
from ntruth.parsers.pdf import PdfParser
from ntruth.parsers.sections import classify_heading
from ntruth.parsers.tabular import CsvParser, XlsxParser
from ntruth.parsers.text import TextParser
from ntruth.schemas.core import stable_id
from ntruth.schemas.document import (
    DESIGN_RELEVANT_SECTIONS,
    DocumentIR,
    Paragraph,
    ParserStatus,
    Section,
    SectionRole,
    SourceFile,
    StatisticalCodeArtifact,
    StatisticalCodeCandidate,
    StatisticalCodeLanguage,
    Table,
    make_paragraph_id,
    make_section_id,
    make_table_id,
)
from ntruth.schemas.manifest import ProjectFile

PARSERS: tuple[Parser, ...] = (
    CodeParser(),
    TextParser(),
    DocxParser(),
    JatsParser(),
    PdfParser(),
    CsvParser(),
    XlsxParser(),
)


def parser_for(path: Path, media_type: str) -> Parser | None:
    return next((p for p in PARSERS if p.supports(path, media_type)), None)


def build_document_ir(project: Project) -> DocumentIR:
    """Costruisce il Document IR di tutto il progetto."""
    files: list[SourceFile] = []
    sections: list[Section] = []
    paragraphs: list[Paragraph] = []
    tables: list[Table] = []
    statistical_code: list[StatisticalCodeArtifact] = []
    texts: dict[str, str] = {}

    for project_file in project.manifest.files:
        path = project.path_of(project_file)
        source, file_sections, file_paragraphs, file_tables, file_code, text = _process_file(
            path, project_file
        )
        files.append(source)
        sections.extend(file_sections)
        paragraphs.extend(file_paragraphs)
        tables.extend(file_tables)
        statistical_code.extend(file_code)
        texts[source.id] = text

    document_id = stable_id("doc", project.manifest.project_id, *(f.sha256 for f in files))
    return DocumentIR(
        id=document_id,
        files=tuple(files),
        sections=tuple(sections),
        paragraphs=tuple(paragraphs),
        tables=tuple(tables),
        statistical_code=tuple(statistical_code),
        texts=texts,
        parser_version=PARSER_VERSION,
    )


def _process_file(
    path: Path, project_file: ProjectFile
) -> tuple[
    SourceFile,
    list[Section],
    list[Paragraph],
    list[Table],
    list[StatisticalCodeArtifact],
    str,
]:
    file_id = project_file.file_id
    parser = parser_for(path, project_file.media_type)
    warnings: list[str] = []

    if parser is None:
        source = SourceFile(
            id=file_id,
            filename=project_file.filename,
            relative_path=project_file.relative_path,
            media_type=project_file.media_type,
            size_bytes=project_file.size_bytes,
            sha256=project_file.sha256,
            parser="none",
            parser_version=PARSER_VERSION,
            status=ParserStatus.IGNORED,
            ignored_reason="nessun parser disponibile per questo tipo",
        )
        return source, [], [], [], [], ""

    try:
        raw = parser.parse(path)
    except ParseFailure as exc:
        source = SourceFile(
            id=file_id,
            filename=project_file.filename,
            relative_path=project_file.relative_path,
            media_type=project_file.media_type,
            size_bytes=project_file.size_bytes,
            sha256=project_file.sha256,
            parser=parser.name,
            parser_version=PARSER_VERSION,
            status=ParserStatus.FAILED,
            warnings=(exc.detail,),
        )
        return source, [], [], [], [], ""

    warnings.extend(raw.warnings)
    sections, paragraphs, text = _assemble_text(file_id, raw, warnings)
    tables = _assemble_tables(file_id, raw)
    code = _assemble_statistical_code(file_id, raw)
    if code and not text:
        # Il testo resta citabile nel Document IR, ma non diventa un paragrafo
        # Methods e quindi non alimenta gli estrattori deterministici esistenti.
        text = code[0].text

    warnings.extend(detect_injection(text))

    source = SourceFile(
        id=file_id,
        filename=project_file.filename,
        relative_path=project_file.relative_path,
        media_type=project_file.media_type,
        size_bytes=project_file.size_bytes,
        sha256=project_file.sha256,
        parser=parser.name,
        parser_version=PARSER_VERSION,
        status=raw.status,
        license_manifest_id=(
            project_file.license_manifest.asset_id if project_file.license_manifest else None
        ),
        warnings=tuple(warnings),
    )
    return source, sections, paragraphs, tables, code, text


def _assemble_statistical_code(file_id: str, raw: RawDocument) -> list[StatisticalCodeArtifact]:
    artifacts: list[StatisticalCodeArtifact] = []
    for item in raw.statistical_code:
        artifact_id = stable_id("code", file_id, item.sha256, item.language)
        candidates = tuple(
            StatisticalCodeCandidate(
                id=stable_id(
                    "code-candidate",
                    artifact_id,
                    candidate.cluster_expression,
                    candidate.start,
                    candidate.end,
                ),
                artifact_id=artifact_id,
                cluster_expression=candidate.cluster_expression,
                declaration=candidate.declaration,
                start=candidate.start,
                end=candidate.end,
                line_start=candidate.line_start,
                line_end=candidate.line_end,
            )
            for candidate in item.candidates
        )
        artifacts.append(
            StatisticalCodeArtifact(
                id=artifact_id,
                file_id=file_id,
                language=StatisticalCodeLanguage(item.language),
                text=item.text,
                sha256=item.sha256,
                start=item.start,
                end=item.end,
                line_start=item.line_start,
                line_end=item.line_end,
                candidates=candidates,
            )
        )
    return artifacts


def _assemble_text(
    file_id: str, raw: RawDocument, warnings: list[str]
) -> tuple[list[Section], list[Paragraph], str]:
    """Concatena i blocchi in un testo unico e assegna sezioni con offset reali."""
    groups: list[tuple[str, int, list[RawBlock]]] = []
    current_title = ""
    current_level = 0
    current: list[RawBlock] = []
    for block in raw.blocks:
        if block.kind == "heading":
            if current or current_title:
                groups.append((current_title, current_level, current))
            current_title = block.text
            current_level = max(block.level, 1)
            current = []
        else:
            current.append(block)
    if current or current_title:
        groups.append((current_title, current_level, current))

    sections: list[Section] = []
    paragraphs: list[Paragraph] = []
    pieces: list[str] = []
    cursor = 0
    # Stack dei ruoli aperti: una sottosezione senza titolo riconoscibile eredita
    # il ruolo della sezione che la contiene ("Diet" dentro "Materials and Methods").
    open_roles: list[tuple[int, SectionRole]] = []

    for index, (title, level, blocks) in enumerate(groups):
        section_title = title or "(senza titolo)"
        role, confidence, origin = (
            classify_heading(title) if title else (SectionRole.OTHER, 0.2, "no_heading")
        )
        if role is SectionRole.OTHER and title:
            inherited = next(
                (
                    r
                    for lvl, r in reversed(open_roles)
                    if lvl < level and r is not SectionRole.OTHER
                ),
                None,
            )
            if inherited is not None:
                role, confidence, origin = inherited, 0.7, "inherited_from_parent_section"
        open_roles = [(lvl, r) for lvl, r in open_roles if lvl < level]
        open_roles.append((level, role))
        section_id = make_section_id(file_id, index, section_title)
        section_start = cursor

        if title:
            pieces.append(title)
            cursor += len(title) + 2  # titolo + separatore "\n\n"

        paragraph_ids: list[str] = []
        for p_index, block in enumerate(blocks):
            start = cursor
            end = start + len(block.text)
            paragraph_id = make_paragraph_id(section_id, p_index, start)
            paragraphs.append(
                Paragraph(
                    id=paragraph_id,
                    file_id=file_id,
                    section_id=section_id,
                    index=p_index,
                    text=block.text,
                    start=start,
                    end=end,
                )
            )
            paragraph_ids.append(paragraph_id)
            pieces.append(block.text)
            cursor = end + 2

        sections.append(
            Section(
                id=section_id,
                file_id=file_id,
                role=role,
                title=section_title,
                index=index,
                start=section_start,
                end=max(section_start, cursor - 2),
                paragraph_ids=tuple(paragraph_ids),
                role_confidence=confidence,
                role_origin=origin,
            )
        )

    text = "\n\n".join(pieces)
    sections = _apply_fallback_roles(sections, warnings)
    return sections, paragraphs, text


def _apply_fallback_roles(sections: list[Section], warnings: list[str]) -> list[Section]:
    """Se nessuna sezione di disegno e riconosciuta, il file viene trattato come
    Methods a bassa confidenza. La scelta e dichiarata, non silenziosa (FR-006)."""
    if any(s.role in DESIGN_RELEVANT_SECTIONS for s in sections):
        return sections
    if not sections:
        return sections
    warnings.append(
        "nessuna intestazione di sezione riconosciuta: il contenuto e trattato come "
        "Methods con confidenza 0.4"
    )
    return [
        s.model_copy(
            update={
                "role": SectionRole.METHODS,
                "role_confidence": 0.4,
                "role_origin": "fallback_no_headings",
            }
        )
        if s.role is SectionRole.OTHER
        else s
        for s in sections
    ]


def _assemble_tables(file_id: str, raw: RawDocument) -> list[Table]:
    tables: list[Table] = []
    for raw_table in raw.tables:
        tables.append(_convert(file_id, raw_table))
    return tables


def _convert(file_id: str, raw_table: RawTable) -> Table:
    table_id = make_table_id(file_id, raw_table.name, raw_table.sheet)
    return Table(
        id=table_id,
        file_id=file_id,
        name=raw_table.name,
        sheet=raw_table.sheet,
        columns=tuple(raw_table.columns),
        rows=tuple(dict(r) for r in raw_table.rows),
        caption=raw_table.caption,
        warnings=tuple(raw_table.warnings),
    )
