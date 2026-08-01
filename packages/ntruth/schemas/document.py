"""Document IR: rappresentazione immutabile e con coordinate delle fonti.

Invariante PRD 11.3: il Document IR e immutabile e conserva coordinate di
testo e celle. Tutto cio che viene dopo (estrazione, grafo, regole) puo solo
leggerlo e citarlo, mai riscriverlo.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from ntruth.schemas.core import EvidenceType, FrozenModel, stable_id


class SectionRole(StrEnum):
    """Ruolo di una sezione (PRD FR-008: Methods, stats, legends, sample description)."""

    TITLE = "title"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    METHODS = "methods"
    STATISTICS = "statistics"
    RESULTS = "results"
    FIGURE_LEGEND = "figure_legend"
    TABLE_CAPTION = "table_caption"
    SAMPLE_DESCRIPTION = "sample_description"
    EXCLUSION = "exclusion"
    SUPPLEMENT = "supplement"
    DISCUSSION = "discussion"
    REFERENCES = "references"
    OTHER = "other"


#: Sezioni che portano informazione sul disegno. Le altre non vengono estratte.
DESIGN_RELEVANT_SECTIONS: frozenset[SectionRole] = frozenset(
    {
        SectionRole.METHODS,
        SectionRole.STATISTICS,
        SectionRole.FIGURE_LEGEND,
        SectionRole.TABLE_CAPTION,
        SectionRole.SAMPLE_DESCRIPTION,
        SectionRole.EXCLUSION,
        SectionRole.SUPPLEMENT,
        SectionRole.RESULTS,
    }
)


class ParserStatus(StrEnum):
    """Esito del parsing. Nessun fallimento silenzioso (PRD FR-006)."""

    OK = "ok"
    PARTIAL = "partial"
    DEGRADED = "degraded"  # es. PDF con testo di bassa qualita
    FAILED = "failed"
    IGNORED = "ignored"  # tipo non supportato, dichiarato esplicitamente


class StatisticalCodeLanguage(StrEnum):
    """Linguaggi ammessi per import testuale non esecutivo (PRD FR-005)."""

    R = "r"
    PYTHON = "python"
    R_MARKDOWN = "r_markdown"


class EvidenceTier(StrEnum):
    """Qualita dell'evidenza di parsing; il codice resta sempre silver."""

    SILVER = "silver"


class StatisticalCodeCandidate(FrozenModel):
    """Clustering dichiarato sintatticamente in R/Python.

    Non e una relazione di allocazione: il tipo letterale ``False`` impedisce
    che un consumer possa promuoverlo accidentalmente a tale ruolo.
    """

    id: str
    artifact_id: str
    cluster_expression: str = Field(min_length=1)
    declaration: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    evidence_tier: EvidenceTier = EvidenceTier.SILVER
    source_kind: EvidenceType = EvidenceType.STATISTICAL_CODE
    is_allocation: Literal[False] = False

    @model_validator(mode="after")
    def _valid_coordinates(self) -> StatisticalCodeCandidate:
        if self.end <= self.start:
            raise ValueError("statistical code candidate: end deve essere > start")
        if self.line_end < self.line_start:
            raise ValueError("statistical code candidate: line_end < line_start")
        return self


class StatisticalCodeArtifact(FrozenModel):
    """Snapshot immutabile di uno script importato senza esecuzione."""

    id: str
    file_id: str
    language: StatisticalCodeLanguage
    text: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start: int = Field(default=0, ge=0)
    end: int = Field(ge=1)
    line_start: int = Field(default=1, ge=1)
    line_end: int = Field(ge=1)
    execution_policy: Literal["never_execute"] = "never_execute"
    candidates: tuple[StatisticalCodeCandidate, ...] = ()

    @model_validator(mode="after")
    def _validate_artifact(self) -> StatisticalCodeArtifact:
        if self.end - self.start != len(self.text):
            raise ValueError("coordinate del codice non coerenti con il testo")
        if any(candidate.artifact_id != self.id for candidate in self.candidates):
            raise ValueError("candidate di codice riferita a un altro artifact_id")
        return self


class SourceFile(FrozenModel):
    """File ingerito, con checksum e stato del parser (PRD FR-007)."""

    id: str
    filename: str
    relative_path: str
    media_type: str
    size_bytes: int
    sha256: str
    parser: str
    parser_version: str
    status: ParserStatus
    license_manifest_id: str | None = None
    warnings: tuple[str, ...] = ()
    ignored_reason: str | None = None


class Paragraph(FrozenModel):
    """Blocco di testo con offset assoluti nel testo del file."""

    id: str
    file_id: str
    section_id: str
    index: int
    text: str
    start: int
    end: int


class Section(FrozenModel):
    """Sezione tipizzata del documento."""

    id: str
    file_id: str
    role: SectionRole
    title: str
    index: int
    start: int
    end: int
    paragraph_ids: tuple[str, ...] = ()
    role_confidence: float = 1.0
    role_origin: str = "heading_match"


class Table(FrozenModel):
    """Tabella o foglio: header + righe come dizionari, con coordinate per cella."""

    id: str
    file_id: str
    name: str
    sheet: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[dict[str, str], ...] = ()
    caption: str | None = None
    warnings: tuple[str, ...] = ()

    def cell(self, row: int, column: str) -> str | None:
        if row < 0 or row >= len(self.rows):
            return None
        return self.rows[row].get(column)

    def values(self, column: str) -> list[str]:
        return [r.get(column, "") for r in self.rows]


class DocumentIR(FrozenModel):
    """Rappresentazione intermedia immutabile di tutte le fonti di un blocco."""

    id: str
    files: tuple[SourceFile, ...] = ()
    sections: tuple[Section, ...] = ()
    paragraphs: tuple[Paragraph, ...] = ()
    tables: tuple[Table, ...] = ()
    statistical_code: tuple[StatisticalCodeArtifact, ...] = ()
    texts: dict[str, str] = Field(default_factory=dict)  # file_id -> testo completo
    parser_version: str = "0.0.0"

    def section(self, section_id: str) -> Section | None:
        return next((s for s in self.sections if s.id == section_id), None)

    def table(self, table_id: str) -> Table | None:
        return next((t for t in self.tables if t.id == table_id), None)

    def file(self, file_id: str) -> SourceFile | None:
        return next((f for f in self.files if f.id == file_id), None)

    def sections_by_role(self, *roles: SectionRole) -> list[Section]:
        wanted = set(roles)
        return [s for s in self.sections if s.role in wanted]

    def paragraphs_of(self, section_id: str) -> list[Paragraph]:
        return [p for p in self.paragraphs if p.section_id == section_id]

    def design_text(self) -> list[tuple[Section, str]]:
        """Testo delle sole sezioni rilevanti per il disegno, in ordine stabile."""
        out: list[tuple[Section, str]] = []
        for section in self.sections:
            if section.role not in DESIGN_RELEVANT_SECTIONS:
                continue
            body = "\n".join(p.text for p in self.paragraphs_of(section.id))
            if body.strip():
                out.append((section, body))
        return out

    def snippet(self, file_id: str, start: int, end: int, pad: int = 0) -> str:
        text = self.texts.get(file_id, "")
        lo = max(0, start - pad)
        hi = min(len(text), end + pad)
        return text[lo:hi]


def make_section_id(file_id: str, index: int, title: str) -> str:
    return stable_id("sec", file_id, index, title)


def make_paragraph_id(section_id: str, index: int, start: int) -> str:
    return stable_id("par", section_id, index, start)


def make_table_id(file_id: str, name: str, sheet: str | None) -> str:
    return stable_id("tbl", file_id, name, sheet)
