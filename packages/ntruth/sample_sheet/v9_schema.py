"""SampleSheetSpec iniziale v9 (PRD v9, Appendice O).

Ogni colonna scientifica usa un valore tipizzato con KnowledgeState esplicito:
una cella vuota senza stato e invalida, e l'assenza viene sempre distinta tra
sconosciuta, non riportata, non applicabile o esplicitamente assente. Gli ID
restano chiavi locali non semantiche: la loro presenza o costanza non costituisce
mai evidenza di allocazione o indipendenza.

La v6 (`ntruth.sample_sheet.schema`) resta immutata: questo contratto coesiste
con essa per il percorso di migrazione v6 -> v9.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.factor_role import FactorRole
from ntruth.schemas.knowledge import KnowledgeState

SAMPLE_SHEET_V9_SCHEMA_VERSION = "9.0"

_SUFFIX_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TIMEPOINT_UNIT_RE = re.compile(r"^[A-Za-z]+$")

_ASSIGNED_ROLE = FactorRole.ASSIGNED_INTERVENTION.value


class UnitType(StrEnum):
    """Tipo di unita rappresentata dalla riga (well/culture/donor/ecc.)."""

    WELL = "WELL"
    CULTURE = "CULTURE"
    DONOR = "DONOR"
    ANIMAL = "ANIMAL"
    SUBJECT = "SUBJECT"
    ALIQUOT = "ALIQUOT"
    OTHER = "OTHER"


class RowLifecycleStatus(StrEnum):
    """Stato di lifecycle della riga (Appendice O, v9)."""

    PLANNED = "PLANNED"
    ALLOCATED = "ALLOCATED"
    TREATED = "TREATED"
    OBSERVED = "OBSERVED"
    EXCLUDED = "EXCLUDED"
    ANALYZED = "ANALYZED"


class PlannedOrExecutedContext(StrEnum):
    """Contesto della riga rispetto al piano (Appendice O)."""

    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"


LIFECYCLE_RANK: dict[RowLifecycleStatus, int] = {
    RowLifecycleStatus.PLANNED: 0,
    RowLifecycleStatus.ALLOCATED: 1,
    RowLifecycleStatus.TREATED: 2,
    RowLifecycleStatus.OBSERVED: 3,
    RowLifecycleStatus.EXCLUDED: 4,
    RowLifecycleStatus.ANALYZED: 5,
}


class TypedValue(FrozenModel):
    """Valore scientifico con stato di conoscenza esplicito (Appendice O).

    Il wrapper resta minimale per l'uso tabellare: il contratto completo
    ``KnowledgeValue`` (v8 kernel) richiede evidence/scope id che una cella di
    sample sheet iniziale non ha ancora. ``CONFLICTING`` richiede alternative
    trattenute e quindi non e rappresentabile qui.
    """

    knowledge_state: KnowledgeState
    value: str | None = None
    rationale: str | None = None

    @field_validator("value", "rationale", mode="before")
    @classmethod
    def _blank_is_none(cls, raw: object) -> object:
        if isinstance(raw, str) and not raw.strip():
            return None
        return raw

    @model_validator(mode="after")
    def _state_matches_value(self) -> Self:
        if self.knowledge_state is KnowledgeState.CONFLICTING:
            raise ValueError("TypedValue non supporta CONFLICTING: servono alternative trattenute")
        if self.knowledge_state is KnowledgeState.PRESENT:
            if self.value is None:
                raise ValueError("PRESENT richiede un valore non vuoto")
            if self.rationale is not None:
                raise ValueError("PRESENT non ammette rationale")
            return self
        if self.value is not None:
            raise ValueError(f"{self.knowledge_state.value} non puo portare un valore")
        return self


class TimepointValue(FrozenModel):
    """Timepoint tipizzato: valore numerico con unita temporale esplicita."""

    knowledge_state: KnowledgeState
    value: float | None = Field(default=None, ge=0)
    unit: str | None = None
    rationale: str | None = None

    @field_validator("unit", "rationale", mode="before")
    @classmethod
    def _blank_is_none(cls, raw: object) -> object:
        if isinstance(raw, str) and not raw.strip():
            return None
        return raw

    @field_validator("unit")
    @classmethod
    def _unit_is_symbolic(cls, value: str | None) -> str | None:
        if value is not None and _TIMEPOINT_UNIT_RE.fullmatch(value) is None:
            raise ValueError("l'unita temporale deve essere simbolica (es. 'h', 'd')")
        return value

    @model_validator(mode="after")
    def _state_matches_value(self) -> Self:
        if self.knowledge_state is KnowledgeState.CONFLICTING:
            raise ValueError(
                "TimepointValue non supporta CONFLICTING: servono alternative trattenute"
            )
        if self.knowledge_state is KnowledgeState.PRESENT:
            if self.value is None:
                raise ValueError("timepoint PRESENT richiede un valore numerico")
            if self.unit is None:
                raise ValueError("timepoint PRESENT richiede un'unita temporale esplicita")
            if self.rationale is not None:
                raise ValueError("PRESENT non ammette rationale")
            return self
        if self.value is not None or self.unit is not None:
            raise ValueError(f"{self.knowledge_state.value} non puo portare un valore")
        return self


def present(value: str) -> TypedValue:
    """Cella presente e osservata."""

    return TypedValue(knowledge_state=KnowledgeState.PRESENT, value=value)


def unknown(rationale: str) -> TypedValue:
    """Cella dichiaratamente sconosciuta con rationale."""

    return TypedValue(knowledge_state=KnowledgeState.UNKNOWN, rationale=rationale)


def not_reported() -> TypedValue:
    """Cella assente perche non riportata dalla fonte."""

    return TypedValue(knowledge_state=KnowledgeState.NOT_REPORTED)


def not_applicable(rationale: str) -> TypedValue:
    """Cella non applicabile al contesto della riga."""

    return TypedValue(knowledge_state=KnowledgeState.NOT_APPLICABLE, rationale=rationale)


class SampleSheetFactorColumnsV9(FrozenModel):
    """Colonne condizionali suffissate per un fattore usato nella riga.

    La chiave del dizionario ``factors`` e il suffisso dopo ``factor_id_`` /
    ``factor_role_`` / ``factor_level_`` / ``contrast_id_`` /
    ``assignment_event_id_`` nell'header della colonna (Appendice O).
    """

    factor_id: TypedValue
    factor_role: TypedValue
    factor_level: TypedValue
    contrast_id: TypedValue | None = None
    assignment_event_id: TypedValue | None = None

    @field_validator("factor_role")
    @classmethod
    def _role_is_canonical(cls, value: TypedValue) -> TypedValue:
        if value.knowledge_state is KnowledgeState.PRESENT and (
            value.value not in {member.value for member in FactorRole}
        ):
            raise ValueError(f"factor_role non canonico: {value.value!r}")
        return value

    @model_validator(mode="after")
    def _assignment_only_for_assigned(self) -> Self:
        role_value = self.factor_role.value
        assignment = self.assignment_event_id
        if (
            assignment is not None
            and assignment.knowledge_state is KnowledgeState.PRESENT
            and role_value != _ASSIGNED_ROLE
        ):
            raise ValueError(
                "assignment_event_id e consentito solo per fattori "
                f"{_ASSIGNED_ROLE}, trovato {role_value!r}"
            )
        if role_value == _ASSIGNED_ROLE and assignment is None:
            raise ValueError(
                f"fattore {_ASSIGNED_ROLE} richiede assignment_event_id (presente o UNKNOWN)"
            )
        return self


class SampleSheetRowV9(FrozenModel):
    """Riga canonica v9 indipendente dalla rappresentazione CSV."""

    row_id: str
    experiment_block_id: str
    unit_instance_id: str
    unit_type: UnitType
    parent_unit_id: TypedValue | None = None
    source_instance_id: TypedValue
    preparation_id: TypedValue
    lineage_event_id: TypedValue | None = None
    factors: dict[str, SampleSheetFactorColumnsV9] = Field(default_factory=dict)
    application_event_id: TypedValue | None = None
    exposure_partition_id: TypedValue | None = None
    plate_id: TypedValue | None = None
    well_id: TypedValue | None = None
    batch_id: TypedValue | None = None
    day_id: TypedValue | None = None
    endpoint_id: TypedValue | None = None
    timepoint_id: TimepointValue | None = None
    lifecycle_status: RowLifecycleStatus
    exclusion_reason: TypedValue | None = None
    file_ref: TypedValue | None = None
    planned_or_executed_context: PlannedOrExecutedContext

    @field_validator("row_id", "experiment_block_id", "unit_instance_id")
    @classmethod
    def _identifier_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("gli identificatori di riga non possono essere vuoti")
        return stripped

    @field_validator("factors")
    @classmethod
    def _factor_suffixes_valid(
        cls, value: dict[str, SampleSheetFactorColumnsV9]
    ) -> dict[str, SampleSheetFactorColumnsV9]:
        for suffix in value:
            if _SUFFIX_RE.fullmatch(suffix) is None:
                raise ValueError(f"suffisso fattore non valido: {suffix!r}")
        return value

    @field_validator("source_instance_id", "preparation_id")
    @classmethod
    def _required_or_unknown(cls, value: TypedValue) -> TypedValue:
        if value.knowledge_state is KnowledgeState.UNKNOWN and not value.rationale:
            raise ValueError(
                f"{value.knowledge_state.value} su source/preparation richiede un rationale"
            )
        if value.knowledge_state not in {
            KnowledgeState.PRESENT,
            KnowledgeState.UNKNOWN,
        }:
            raise ValueError(
                "source_instance_id/preparation_id sono required-or-unknown: "
                f"stato {value.knowledge_state.value} non ammesso"
            )
        return value

    @field_validator("lineage_event_id")
    @classmethod
    def _lineage_declared_or_none(cls, value: TypedValue | None) -> TypedValue | None:
        if value is not None and value.knowledge_state is KnowledgeState.NOT_APPLICABLE:
            raise ValueError("lineage_event_id NOT_APPLICABLE: lasciare la colonna assente")
        return value

    @model_validator(mode="after")
    def _exclusion_contract(self) -> Self:
        if self.lifecycle_status is RowLifecycleStatus.EXCLUDED:
            reason = self.exclusion_reason
            if reason is None or reason.knowledge_state is not KnowledgeState.PRESENT:
                raise ValueError(
                    "exclusion_reason PRESENT e obbligatorio quando "
                    "lifecycle_status=EXCLUDED (actor/timing/evidence)"
                )
        elif self.exclusion_reason is not None:
            raise ValueError("exclusion_reason e consentito solo quando lifecycle_status=EXCLUDED")
        return self


class SampleSheetSpecV9(FrozenModel):
    """Sample sheet v9 validato (Appendice O): righe, blocco e monotonia."""

    schema_version: str = SAMPLE_SHEET_V9_SCHEMA_VERSION
    experiment_block_id: str
    rows: tuple[SampleSheetRowV9, ...] = Field(min_length=1)
    content_sha256: str | None = None

    @field_validator("experiment_block_id")
    @classmethod
    def _block_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("experiment_block_id non puo essere vuoto")
        return stripped

    @field_validator("content_sha256")
    @classmethod
    def _sha256_shape(cls, value: str | None) -> str | None:
        if value is not None and _SHA256_RE.fullmatch(value) is None:
            raise ValueError("content_sha256 deve essere un digest esadecimale sha256")
        return value

    @model_validator(mode="after")
    def _validate_rows(self) -> Self:
        row_ids = [row.row_id for row in self.rows]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("row_id deve essere univoco nel foglio")

        foreign = sorted(
            {
                row.experiment_block_id
                for row in self.rows
                if row.experiment_block_id != self.experiment_block_id
            }
        )
        if foreign:
            raise ValueError(
                "righe fuori dal boundary dell'experiment block: " + ", ".join(foreign)
            )

        grouped: dict[str, list[SampleSheetRowV9]] = {}
        for row in self.rows:
            grouped.setdefault(row.unit_instance_id, []).append(row)
        for unit_id, unit_rows in grouped.items():
            _validate_unit_lifecycle(unit_id, unit_rows)
        return self


def validate_lifecycle_progression(
    previous: RowLifecycleStatus,
    following: RowLifecycleStatus,
) -> None:
    """Transizione ammessa tra due righe consecutive della stessa unita.

    La monotonia vale solo dentro la stessa coorte/unit (P.4): nessun vincolo
    cross-endpoint o cross-unit-type e assunto. EXCLUDED e terminale.
    """

    previous_rank = LIFECYCLE_RANK[previous]
    following_rank = LIFECYCLE_RANK[following]
    if previous is RowLifecycleStatus.EXCLUDED:
        raise ValueError("nessuna riga puo seguire EXCLUDED per la stessa unit")
    if previous_rank > following_rank:
        raise ValueError(
            f"lifecycle non monotonico per la stessa unit: {previous.value} -> {following.value}"
        )


def _validate_unit_lifecycle(unit_id: str, rows: list[SampleSheetRowV9]) -> None:
    if len(rows) < 2:
        return
    observed_seen = False
    previous: SampleSheetRowV9 | None = None
    for row in rows:
        if previous is not None:
            try:
                validate_lifecycle_progression(previous.lifecycle_status, row.lifecycle_status)
            except ValueError as error:
                raise ValueError(f"unit {unit_id}: {error}") from error
        if row.lifecycle_status is RowLifecycleStatus.ANALYZED and not observed_seen:
            raise ValueError(
                f"unit {unit_id}: ANALYZED richiede una riga OBSERVED precedente "
                "(analyzed <= observed)"
            )
        if row.lifecycle_status is RowLifecycleStatus.OBSERVED:
            observed_seen = True
        previous = row


def sample_sheet_v9_json_schema() -> dict[str, object]:
    """Schema JSON pubblico del contratto SampleSheetSpec v9."""

    return SampleSheetSpecV9.model_json_schema()


__all__ = [
    "LIFECYCLE_RANK",
    "SAMPLE_SHEET_V9_SCHEMA_VERSION",
    "PlannedOrExecutedContext",
    "RowLifecycleStatus",
    "SampleSheetFactorColumnsV9",
    "SampleSheetRowV9",
    "SampleSheetSpecV9",
    "TimepointValue",
    "TypedValue",
    "UnitType",
    "not_applicable",
    "not_reported",
    "present",
    "sample_sheet_v9_json_schema",
    "unknown",
    "validate_lifecycle_progression",
]
