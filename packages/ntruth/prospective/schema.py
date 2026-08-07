"""Contratti di ingresso/uscita del compiler prospettico Core Profile D0.

Gli alias camelCase esistono soltanto al confine API per il client desktop. Gli
oggetti canonici e gli export usano sempre snake_case e gli enum normativi.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import AliasChoices, ConfigDict, Field, field_validator, model_validator

from ntruth.capabilities import CapabilityReason, CapabilityStatus
from ntruth.design.schema import DesignCompilation
from ntruth.sample_sheet.schema import SampleLifecycleStatus, SampleSheetSpec
from ntruth.schemas.core import Determinability, NTruthModel
from ntruth.schemas.experiment import (
    ExclusionPhase,
    ExperimentBlock,
    TriState,
)
from ntruth.schemas.graph import NodeType
from ntruth.schemas.rules import RuleEvaluation
from ntruth.verifier.hard import HardVerificationResult

PROSPECTIVE_D0_CONTRACT_VERSION: Final[Literal["1.0.0"]] = "1.0.0"
MAX_PROSPECTIVE_D0_ROWS: Final[int] = 10_000
MAX_PROSPECTIVE_D0_BODY_BYTES: Final[int] = 8 * 1024 * 1024
MAX_PROSPECTIVE_D0_EXTRA_FIELDS: Final[int] = 64
_VACUOUS_INDEPENDENCE_MECHANISMS: Final[frozenset[str]] = frozenset(
    {
        "yes",
        "true",
        "independent",
        "independently assigned",
        "unknown",
        "not applicable",
        "n/a",
        "na",
        "none",
    }
)


class _ProspectiveInput(NTruthModel):
    """Base fail-closed che accetta il naming del client senza perpetuarlo."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, use_enum_values=False)


class ProspectiveIssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ProspectiveD0Issue(NTruthModel):
    code: str
    message: str
    severity: ProspectiveIssueSeverity
    row: int | None = None
    field: str | None = None


class ProspectiveEstimandDraft(_ProspectiveInput):
    """Estimand minimo esplicitamente fornito dal ricercatore."""

    effect_measure: str = Field(
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("effect_measure", "effectMeasure"),
    )
    target_population_or_unit: str = Field(
        min_length=1,
        max_length=2000,
        validation_alias=AliasChoices("target_population_or_unit", "targetPopulationOrUnit"),
    )
    generalization_level: str = Field(
        min_length=1,
        max_length=1000,
        validation_alias=AliasChoices("generalization_level", "generalizationLevel"),
    )
    timepoint: str | None = Field(default=None, max_length=500)
    condition: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "effect_measure",
        "target_population_or_unit",
        "generalization_level",
        "timepoint",
        "condition",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None


class ProspectiveD0Draft(_ProspectiveInput):
    """Campi dichiarativi del wizard, distinti dai dati per-campione."""

    experiment_block_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$",
        validation_alias=AliasChoices("experiment_block_id", "experimentBlockId"),
    )
    title: str = Field(default="Prospective D0 experiment", max_length=500)
    question_text: str = Field(
        min_length=3,
        max_length=4000,
        validation_alias=AliasChoices("question_text", "question"),
    )
    population_of_inference: str = Field(
        min_length=2,
        max_length=2000,
        validation_alias=AliasChoices("population_of_inference", "inferenceTarget"),
    )
    factor_name: str = Field(
        min_length=1,
        max_length=300,
        validation_alias=AliasChoices("factor_name", "factorName"),
    )
    factor_kind: Literal["treatment", "genotype", "dose", "time", "diet", "other", "unknown"] = (
        Field(
            default="unknown",
            validation_alias=AliasChoices("factor_kind", "factorKind"),
        )
    )
    level_a: str = Field(
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("level_a", "levelA"),
    )
    level_b: str = Field(
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("level_b", "levelB"),
    )
    endpoint_name: str = Field(
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("endpoint_name", "endpointName"),
    )
    endpoint_id: str = Field(
        min_length=1,
        max_length=300,
        validation_alias=AliasChoices("endpoint_id", "endpointId"),
    )
    measured_on: NodeType | Literal["UNKNOWN"] = Field(
        default="UNKNOWN",
        validation_alias=AliasChoices("measured_on", "measuredOn"),
    )
    allocation_level: NodeType | Literal["UNKNOWN"] = Field(
        default="UNKNOWN",
        validation_alias=AliasChoices("allocation_level", "allocationLevel"),
    )
    application_level: NodeType | Literal["UNKNOWN"] = Field(
        default="UNKNOWN",
        validation_alias=AliasChoices("application_level", "applicationLevel"),
    )
    independently_assigned: TriState = Field(
        default=TriState.UNKNOWN,
        validation_alias=AliasChoices("independently_assigned", "independentlyAssigned"),
    )
    independence_mechanism: str | None = Field(
        default=None,
        max_length=2000,
        validation_alias=AliasChoices("independence_mechanism", "independenceMechanism"),
    )
    shared_environment: tuple[str, ...] = Field(
        default=(),
        max_length=64,
        validation_alias=AliasChoices("shared_environment", "sharedEnvironment"),
    )
    target_biological_unit: NodeType | None = Field(
        default=None,
        validation_alias=AliasChoices("target_biological_unit", "targetBiologicalUnit"),
    )
    cell_population_plan: str | None = Field(
        default=None,
        max_length=2000,
        validation_alias=AliasChoices("cell_population_plan", "cellPopulationPlan"),
    )
    estimand: ProspectiveEstimandDraft | None = None
    reviewer_role: str = Field(
        default="researcher",
        min_length=2,
        max_length=64,
        validation_alias=AliasChoices("reviewer_role", "reviewerRole"),
    )

    @field_validator("shared_environment", mode="before")
    @classmethod
    def _one_environment_string_is_one_observation(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return (stripped,) if stripped else ()
        return value

    @field_validator(
        "experiment_block_id",
        "title",
        "question_text",
        "population_of_inference",
        "factor_name",
        "level_a",
        "level_b",
        "endpoint_name",
        "endpoint_id",
        "independence_mechanism",
        "cell_population_plan",
        "reviewer_role",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _factor_and_independence_are_coherent(self) -> Self:
        if self.level_a.casefold() == self.level_b.casefold():
            raise ValueError("level_a e level_b devono essere distinti")
        if self.independently_assigned is TriState.TRUE:
            mechanism = self.independence_mechanism or ""
            normalized_mechanism = " ".join(mechanism.casefold().split()).strip(" ._-;")
            if len(mechanism) < 12 or normalized_mechanism in _VACUOUS_INDEPENDENCE_MECHANISMS:
                raise ValueError(
                    "independently_assigned=TRUE richiede un independence_mechanism "
                    "operativo e non vacuo"
                )
        if len(self.shared_environment) != len(set(self.shared_environment)):
            raise ValueError("shared_environment contiene valori duplicati")
        uses_cell_population = NodeType.CELL in {
            self.application_level,
            self.measured_on,
            self.target_biological_unit,
        }
        if uses_cell_population and not self.cell_population_plan:
            raise ValueError(
                "i ruoli application/measured/target=Cell richiedono cell_population_plan"
            )
        if self.cell_population_plan and not uses_cell_population:
            raise ValueError("cell_population_plan fornito ma nessun ruolo usa Cell")
        return self


class ProspectiveD0Row(_ProspectiveInput):
    """Riga D0 di ingresso; la compilazione la converte in SampleSheetRow."""

    sample_id: str = Field(
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("sample_id", "sampleId"),
    )
    source_id: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("source_id", "sourceId"),
    )
    preparation_id: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("preparation_id", "preparationId"),
    )
    culture_id: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("culture_id", "cultureId"),
    )
    plate_id: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("plate_id", "plateId"),
    )
    well_id: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("well_id", "wellId"),
    )
    factor_level: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("factor_level", "factorLevel"),
    )
    factor_levels: dict[str, str] | None = Field(
        default=None,
        max_length=2,
        validation_alias=AliasChoices("factor_levels", "factorLevels"),
    )
    batch_id: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("batch_id", "batchId"),
    )
    timepoint: str | None = Field(default=None, max_length=500)
    endpoint_id: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("endpoint_id", "endpointId"),
    )
    lifecycle_status: SampleLifecycleStatus = Field(
        validation_alias=AliasChoices("lifecycle_status", "lifecycleStatus")
    )
    exclusion_reason: str | None = Field(
        default=None,
        max_length=2000,
        validation_alias=AliasChoices("exclusion_reason", "exclusionReason"),
    )
    exclusion_phase: ExclusionPhase | None = Field(
        default=None,
        validation_alias=AliasChoices("exclusion_phase", "exclusionPhase"),
    )
    exclusion_prespecified: TriState = Field(
        default=TriState.UNKNOWN,
        validation_alias=AliasChoices("exclusion_prespecified", "exclusionPrespecified"),
    )
    exclusion_author_role: str | None = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("exclusion_author_role", "exclusionAuthorRole"),
    )
    exclusion_impact: str | None = Field(
        default=None,
        max_length=2000,
        validation_alias=AliasChoices("exclusion_impact", "exclusionImpact"),
    )
    file_ref: str | None = Field(
        default=None,
        max_length=2000,
        validation_alias=AliasChoices("file_ref", "fileRef"),
    )
    extra_fields: dict[str, str | None] = Field(
        default_factory=dict,
        max_length=MAX_PROSPECTIVE_D0_EXTRA_FIELDS,
        validation_alias=AliasChoices("extra_fields", "extraFields"),
    )

    @field_validator("factor_levels", "extra_fields")
    @classmethod
    def _bounded_mapping_cells(
        cls, value: dict[str, str | None] | None
    ) -> dict[str, str | None] | None:
        if value is None:
            return value
        normalized: dict[str, str | None] = {}
        for raw_key, raw_value in value.items():
            key = raw_key.strip()
            if not key or len(key) > 100:
                raise ValueError("chiave mapping vuota o oltre 100 caratteri")
            if raw_value is None:
                normalized[key] = None
                continue
            cell = raw_value.strip()
            if not cell:
                raise ValueError(f"valore vuoto per la chiave '{key}'")
            if len(cell) > 2000:
                raise ValueError(f"valore oltre 2000 caratteri per la chiave '{key}'")
            normalized[key] = cell
        return normalized

    @field_validator(
        "sample_id",
        "source_id",
        "preparation_id",
        "culture_id",
        "plate_id",
        "well_id",
        "factor_level",
        "batch_id",
        "timepoint",
        "endpoint_id",
        "exclusion_reason",
        "exclusion_author_role",
        "exclusion_impact",
        "file_ref",
        mode="before",
    )
    @classmethod
    def _strip_cells(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _one_factor_representation(self) -> Self:
        if (self.factor_level is None) == (self.factor_levels is None):
            raise ValueError("fornire esattamente uno tra factor_level e factor_levels")
        if self.lifecycle_status is SampleLifecycleStatus.EXCLUDED and not self.exclusion_reason:
            raise ValueError("exclusion_reason e obbligatorio per una riga excluded")
        return self


class ProspectiveD0CompileRequest(_ProspectiveInput):
    draft: ProspectiveD0Draft
    rows: tuple[ProspectiveD0Row, ...] = Field(default=(), max_length=MAX_PROSPECTIVE_D0_ROWS)
    language: Literal["it", "en"] = "it"
    # Il server confronta questi valori con l'unico ruleset canonico D0 prima
    # di costruire qualunque path. Restano nel payload per rendere esplicito il
    # contratto richiesto dal client e rifiutare versioni stale con un 4xx.
    ruleset_id: str = Field(
        default="ntruth-core",
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("ruleset_id", "rulesetId"),
    )
    ruleset_version: str = Field(
        default="0.2.0",
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("ruleset_version", "rulesetVersion"),
    )


class ProspectiveCapabilityResult(NTruthModel):
    profile_id: str
    profile_version: str
    profile_reference: str
    status: CapabilityStatus
    supported: bool | None
    reason_codes: tuple[CapabilityReason, ...] = ()
    details: tuple[str, ...] = ()


class ProspectiveD0Compilation(NTruthModel):
    """Artefatto autosufficiente e serializzabile della compilazione locale."""

    contract_version: Literal["1.0.0"] = PROSPECTIVE_D0_CONTRACT_VERSION
    compiler_version: Literal["1.0.0"] = PROSPECTIVE_D0_CONTRACT_VERSION
    compilation_id: str
    ruleset_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    sample_sheet: SampleSheetSpec
    block: ExperimentBlock
    capability: ProspectiveCapabilityResult
    design_compilation: DesignCompilation
    verification: HardVerificationResult
    rule_evaluations: tuple[RuleEvaluation, ...] = ()
    issues: tuple[ProspectiveD0Issue, ...] = ()
    determinability: Determinability
    ready_for_handoff: bool
    scientific_validation_status: Literal["not_performed"] = "not_performed"
    prohibited_outputs: tuple[str, ...] = (
        "statistical_test_selection",
        "model_formula",
        "power_analysis",
        "scientific_validity_certification",
    )


class ProspectiveD0ValidationError(ValueError):
    """Errore cross-row: nessun blocco parziale viene restituito o persistito."""

    def __init__(self, issues: tuple[ProspectiveD0Issue, ...]) -> None:
        self.issues = issues
        detail = "; ".join(item.message for item in issues)
        super().__init__(detail or "input prospettico D0 non valido")


class ProspectiveD0RulesetError(RuntimeError):
    """Ruleset richiesto non ammesso o asset canonico locale non disponibile."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ProspectiveCompileAuditEvent(NTruthModel):
    """Evento append-only di sessione, separato dal core deterministico."""

    id: str
    action: Literal["compile"] = "compile"
    actor_role: str = Field(min_length=2, max_length=64)
    recorded_at: datetime
    input_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("recorded_at")
    @classmethod
    def _timestamp_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at deve includere il fuso orario")
        return value
