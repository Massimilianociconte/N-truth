"""Conservative structural segmentation into ExperimentBlock documents (PRD 12.1).

The segmenter uses only explicit document structure: headings such as
``Experiment 2`` and sample-sheet experiment identifiers.  Material that cannot
be linked unambiguously is reported and left unassigned instead of being copied
across blocks, which would manufacture cross-experiment evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ntruth.schemas.core import stable_id
from ntruth.schemas.document import DocumentIR, Section, Table

_EXPERIMENT_MARKER = re.compile(
    r"^(?:experiment(?:\s+block)?|study|esperimento|studio)\s*"
    r"(?:#|n[.o°]*\s*)?(?P<key>[a-z0-9][a-z0-9_.-]*)\b",
    re.IGNORECASE,
)
_EXPERIMENT_COLUMNS = frozenset(
    {
        "experiment",
        "experiment_id",
        "experiment_block",
        "experiment_block_id",
        "study",
        "study_id",
        "esperimento",
        "esperimento_id",
        "studio",
        "studio_id",
    }
)


@dataclass(frozen=True, slots=True)
class SegmentedDocument:
    key: str
    title: str
    document: DocumentIR


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    blocks: tuple[SegmentedDocument, ...]
    warnings: tuple[str, ...] = ()
    segmented: bool = False


def segment_document_ir(ir: DocumentIR, fallback_title: str) -> SegmentationResult:
    """Split an IR when at least two explicit experiment identifiers are present."""
    sections_by_key: dict[str, list[Section]] = {}
    tables_by_key: dict[str, list[Table]] = {}
    title_by_key: dict[str, str] = {}
    first_seen: dict[str, int] = {}
    warnings: list[str] = []
    seen_counter = 0

    sections_by_file: dict[str, list[Section]] = {}
    for section in ir.sections:
        sections_by_file.setdefault(section.file_id, []).append(section)

    file_anchor_keys: dict[str, set[str]] = {}
    unanchored_sections: dict[str, list[Section]] = {}
    for file_id, file_sections in sections_by_file.items():
        anchors: list[tuple[int, str, str]] = []
        for position, section in enumerate(file_sections):
            marker = _marker(section.title)
            if marker is None:
                continue
            key, title = marker
            anchors.append((position, key, title))
            title_by_key.setdefault(key, title)
            first_seen.setdefault(key, seen_counter)
            seen_counter += 1

        if not anchors:
            unanchored_sections[file_id] = file_sections
            continue

        file_anchor_keys[file_id] = {key for _, key, _ in anchors}
        if anchors[0][0] > 0:
            unanchored_sections[file_id] = file_sections[: anchors[0][0]]
        for index, (start, key, _title) in enumerate(anchors):
            end = anchors[index + 1][0] if index + 1 < len(anchors) else len(file_sections)
            sections_by_key.setdefault(key, []).extend(file_sections[start:end])

    for table in ir.tables:
        assigned = _assign_table(table)
        if assigned:
            for key, sliced in assigned.items():
                tables_by_key.setdefault(key, []).append(sliced)
                title_by_key.setdefault(key, f"Experiment {key}")
                first_seen.setdefault(key, seen_counter)
                seen_counter += 1
            continue

        anchor_keys = file_anchor_keys.get(table.file_id, set())
        if len(anchor_keys) == 1:
            tables_by_key.setdefault(next(iter(anchor_keys)), []).append(table)
        elif len(anchor_keys) > 1:
            warnings.append(
                f"tabella '{table.name}' non assegnata: il file contiene piu ExperimentBlock "
                "e la tabella non ha un identificatore di esperimento"
            )

    all_keys = set(sections_by_key) | set(tables_by_key)
    if len(all_keys) < 2:
        title = _fallback_block_title(ir, fallback_title)
        return SegmentationResult(
            blocks=(SegmentedDocument(key="global", title=title, document=ir),),
            warnings=(
                "Segmentazione conservativa in ExperimentBlock: nessun insieme di almeno due "
                "separatori strutturali espliciti; il materiale resta in un solo blocco.",
            ),
            segmented=False,
        )

    # A file without an explicit marker is attachable only when its filename
    # itself identifies exactly one known experiment.  Otherwise it stays out.
    for file_id, sections in unanchored_sections.items():
        source = ir.file(file_id)
        marker = _marker(source.filename.rsplit(".", 1)[0]) if source else None
        if marker and marker[0] in all_keys:
            sections_by_key.setdefault(marker[0], []).extend(sections)
        elif any(section.paragraph_ids for section in sections):
            warnings.append(
                f"contenuto di '{source.filename if source else file_id}' non assegnato: "
                "manca un collegamento esplicito a uno degli ExperimentBlock"
            )

    ordered_keys = sorted(all_keys, key=lambda key: (first_seen.get(key, 10**9), key))
    blocks = tuple(
        SegmentedDocument(
            key=key,
            title=title_by_key.get(key, f"Experiment {key}"),
            document=_slice_ir(ir, key, sections_by_key.get(key, []), tables_by_key.get(key, [])),
        )
        for key in ordered_keys
    )
    return SegmentationResult(
        blocks=blocks,
        warnings=tuple(dict.fromkeys(warnings)),
        segmented=True,
    )


def _marker(value: str) -> tuple[str, str] | None:
    match = _EXPERIMENT_MARKER.match(value.strip())
    if not match:
        return None
    key = match.group("key").lower()
    if not _looks_like_identifier(key):
        return None
    return key, value.strip()


def _looks_like_identifier(value: str) -> bool:
    """Reject prose labels such as ``Study design`` as experiment identifiers."""
    return (
        any(character.isdigit() for character in value)
        or (len(value) == 1 and value.isalpha())
        or bool(re.fullmatch(r"[ivxlcdm]+", value, re.IGNORECASE))
    )


def _assign_table(table: Table) -> dict[str, Table]:
    marker = _marker(table.sheet or "") or _marker(table.name)
    if marker:
        key, _ = marker
        return {key: table}

    experiment_column = next(
        (
            column
            for column in table.columns
            if column.strip().lower().replace(" ", "_") in _EXPERIMENT_COLUMNS
        ),
        None,
    )
    if experiment_column is None:
        return {}

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in table.rows:
        raw_key = (row.get(experiment_column) or "").strip()
        marker = _marker(raw_key)
        key = marker[0] if marker else raw_key.lower()
        if key:
            grouped.setdefault(key, []).append(dict(row))
    return {
        key: table.model_copy(
            update={
                "id": stable_id("tbl", table.id, key),
                "name": f"{table.name} [{key}]",
                "rows": tuple(rows),
            }
        )
        for key, rows in grouped.items()
    }


def _slice_ir(ir: DocumentIR, key: str, sections: list[Section], tables: list[Table]) -> DocumentIR:
    section_ids = {section.id for section in sections}
    paragraphs = tuple(
        paragraph for paragraph in ir.paragraphs if paragraph.section_id in section_ids
    )
    file_ids = {
        *(section.file_id for section in sections),
        *(table.file_id for table in tables),
    }
    files = tuple(source for source in ir.files if source.id in file_ids)
    selected_sections = tuple(section for section in ir.sections if section.id in section_ids)
    selected_table_ids = {table.id for table in tables}
    selected_tables = tuple(table for table in tables if table.id in selected_table_ids)
    return DocumentIR(
        id=stable_id(
            "docblk",
            ir.id,
            key,
            *(section.id for section in selected_sections),
            *(table.id for table in selected_tables),
        ),
        files=files,
        sections=selected_sections,
        paragraphs=paragraphs,
        tables=selected_tables,
        texts={file_id: ir.texts[file_id] for file_id in file_ids if file_id in ir.texts},
        parser_version=ir.parser_version,
    )


def _fallback_block_title(ir: DocumentIR, fallback: str) -> str:
    for section in ir.sections:
        if section.title and section.title != "(senza titolo)":
            return section.title
    return fallback
