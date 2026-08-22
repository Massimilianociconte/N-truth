"""Tipi base condivisi: identita deterministica, evidenza e provenance.

Invariante PRD 7.4: ogni fatto conserva file, sezione, offset o cella, testo
originale, parser e model version. Nessun fatto puo esistere senza provenance.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(StrEnum):
    """Severita di un alert (PRD 20.1). `insufficient` non e un errore: e un esito."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    INFO = "info"
    INSUFFICIENT = "insufficient"


class ProvenanceKind(StrEnum):
    """Origine di un fatto (PRD 7.4)."""

    EXPLICIT = "explicit"  # letto testualmente nella fonte
    TABULAR = "tabular"  # derivato da celle di sample sheet
    DERIVED = "derived"  # dedotto deterministicamente dal grafo
    RULE = "rule"  # prodotto da una regola versionata
    MODEL = "model"  # predizione ML: sempre candidate fact (PRD 11.3)
    USER = "user"  # correzione umana
    ADJUDICATION = "adjudication"  # decisione esperta registrata


class EvidenceType(StrEnum):
    """Classificazione dell'evidenza prevista dal PRD v3, sezione 9.1.

    I valori restano maiuscoli per coincidere con il contratto di scambio del
    parser AI e con i template di annotazione. ``None`` sui modelli che usano
    questo enum e riservato esclusivamente agli artefatti legacy non ancora
    riclassificati.
    """

    STRUCTURAL_FACT = "STRUCTURAL_FACT"
    AUTHOR_ASSERTION = "AUTHOR_ASSERTION"
    SAMPLE_METADATA = "SAMPLE_METADATA"
    STATISTICAL_CODE = "STATISTICAL_CODE"
    USER_CONFIRMATION = "USER_CONFIRMATION"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    DERIVED_FACT = "DERIVED_FACT"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class AlertClass(StrEnum):
    """Le tre dimensioni scientifiche che un alert puo segnalare."""

    DESIGN_REPLICATION = "design_replication"
    ANALYTICAL_DEPENDENCE = "analytical_dependence"
    INFERENCE_SCOPE = "inference_scope"


class Determinability(StrEnum):
    """Stato della ricostruzione del disegno, distinto dalla confidence."""

    DETERMINATE = "DETERMINATE"
    MULTIPLE_PLAUSIBLE_GRAPHS = "MULTIPLE_PLAUSIBLE_GRAPHS"
    INDETERMINATE = "INDETERMINATE"
    CONFLICTING_INFORMATION = "CONFLICTING_INFORMATION"


class Confidence(StrEnum):
    """Etichette qualitative per completezza informativa (PRD 12.3)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class NTruthModel(BaseModel):
    """Base comune: vieta campi non dichiarati per evitare fatti di contrabbando."""

    model_config = ConfigDict(extra="forbid", frozen=False, use_enum_values=False)


class FrozenModel(NTruthModel):
    """Modello immutabile: usato per il Document IR (PRD 11.3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CellRef(FrozenModel):
    """Riferimento a una cella di foglio/tabella."""

    table_id: str
    row: int = Field(ge=0)
    column: str
    sheet: str | None = None

    def as_label(self) -> str:
        prefix = f"{self.sheet}!" if self.sheet else ""
        return f"{prefix}{self.table_id}[{self.row}].{self.column}"


class EvidenceSpan(FrozenModel):
    """Evidenza localizzata. Obbligatoria per ogni alert (PRD FR-024, NFR-03)."""

    id: str
    file_id: str
    section_id: str | None = None
    section_title: str | None = None
    start: int | None = None
    end: int | None = None
    cell: CellRef | None = None
    text: str = ""
    parser_version: str = "0.0.0"
    evidence_type: EvidenceType | None = None
    page: int | None = Field(default=None, ge=1)
    document_version: str | None = None
    extraction_method: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v: int | None, info: Any) -> int | None:
        start = info.data.get("start")
        if v is not None and start is not None and v < start:
            raise ValueError("evidence span: end < start")
        return v

    def locator(self) -> str:
        if self.cell is not None:
            return self.cell.as_label()
        if self.start is not None:
            return f"{self.section_title or self.section_id or 'doc'}:{self.start}-{self.end}"
        return self.section_title or self.section_id or self.file_id


class Provenance(FrozenModel):
    """Da dove viene un fatto e chi lo ha prodotto."""

    origin: ProvenanceKind
    evidence_ids: tuple[str, ...] = ()
    rule_id: str | None = None
    ruleset_version: str | None = None
    model_version: str | None = None
    parser_version: str | None = None
    document_version: str | None = None
    extraction_method: str | None = None
    timestamp: datetime | None = None
    derivation: str | None = None  # spiegazione breve del passaggio deterministico
    actor_role: str | None = None  # ruolo, mai identita personale (PRD 12.4)
    correction_role: str | None = None

    @property
    def is_candidate(self) -> bool:
        """Un output del modello e sempre un candidate fact (PRD 11.3)."""
        return self.origin is ProvenanceKind.MODEL


def stable_id(prefix: str, *parts: Any) -> str:
    """ID deterministico e content-addressed.

    Nessun timestamp e nessun contatore globale: due run sullo stesso input
    devono produrre gli stessi ID (PRD NFR-02).
    """
    payload = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def content_checksum(payload: Any) -> str:
    """SHA-256 di una struttura serializzabile, per manifest e report (FR-007)."""
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
