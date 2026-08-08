"""Causal Design Context: strato descrittivo, non motore causale (PRD v7 §2.4, App. Y).

Regole vincolanti:
- nessun campo viene inferito come verita dal modello AI;
- ``comparability_basis`` non autorizza mai ``exchangeable=true``;
- l'assenza di reporting sull'interferenza equivale a UNKNOWN, mai a "nessuna
  interferenza" (NFR-26);
- ogni conclusione va associata a una InferentialQuery.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.events import (
    ApplicationEvent,
    AssignmentEvent,
    EventRecord,
    EventRegistry,
    ExposureEvent,
)
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


class AssignmentLevel(StrEnum):
    WELL = "well"
    CULTURE = "culture"
    PLATE = "plate"
    ANIMAL = "animal"
    UNKNOWN = "unknown"


class AssignmentMethod(StrEnum):
    RANDOM = "random"
    BLOCKED_RANDOM = "blocked_random"
    MATCHED = "matched"
    MANUAL = "manual"
    CONVENIENCE = "convenience"
    UNKNOWN = "unknown"


class SplitTiming(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    SAME_EVENT = "same_event"
    UNKNOWN = "unknown"


class AssignmentMechanism(FrozenModel):
    """Come e quando i livelli del fattore sono assegnati (PRD v7 §2.4, §7.7)."""

    level: AssignmentLevel = AssignmentLevel.UNKNOWN
    method: AssignmentMethod = AssignmentMethod.UNKNOWN
    timing_relative_to_split: SplitTiming = SplitTiming.UNKNOWN
    randomization_unit: str | None = None  # unit type o null


class InterferenceStatus(StrEnum):
    NO_KNOWN_PATH = "no_known_path"
    POSSIBLE = "possible"
    DOCUMENTED = "documented"
    UNKNOWN = "unknown"


class InterferenceAssessment(FrozenModel):
    """Valutazione dell'esposizione condivisa (PRD v7 §2.6).

    ``no_known_path`` richiede evidenza positiva documentata: il silenzio della
    fonte non e mai una prova di assenza di interferenza.
    """

    status: InterferenceStatus = InterferenceStatus.UNKNOWN
    exposure_unit: str | None = None  # well|plate|bath|cage|co_culture|unknown
    shared_environment: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_known_path_requires_evidence(self) -> Self:
        if self.status is InterferenceStatus.NO_KNOWN_PATH and not self.evidence_ids:
            raise ValueError("no_known_path richiede evidenza positiva: il silenzio vale UNKNOWN")
        return self


class ComparabilityStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class ComparabilityBasisEvidence(StrEnum):
    RANDOMIZATION = "randomization"
    BLOCKING = "blocking"
    MATCHING = "matching"
    BASELINE_COVARIATES = "baseline_covariates"


class ComparabilityBasis(FrozenModel):
    """Base documentata per la comparabilita; mai un'etichetta di exchangeability."""

    status: ComparabilityStatus = ComparabilityStatus.UNKNOWN
    evidence_basis: tuple[ComparabilityBasisEvidence, ...] = ()
    notes: str = ""

    @property
    def exchangeable(self) -> None:
        """Vietato emettere exchangeable=true come fatto automatico (PRD v7 §2.4)."""
        raise AttributeError(
            "exchangeable non e un fatto derivabile: registrare solo la base documentata"
        )


class CausalDesignContext(FrozenModel):
    """Estensione descrittiva per fattore (PRD v7 §8.2C)."""

    factor_id: str
    assignment_mechanism: AssignmentMechanism = Field(default_factory=AssignmentMechanism)
    interference_assessment: InterferenceAssessment = Field(default_factory=InterferenceAssessment)
    comparability_basis: ComparabilityBasis = Field(default_factory=ComparabilityBasis)

    @model_validator(mode="after")
    def _factor_required(self) -> Self:
        if not self.factor_id.strip():
            raise ValueError("causal context senza factor_id")
        return self


class IndependenceDimension(StrEnum):
    """Le quattro dimensioni di indipendenza (PRD v7 §2.3, §7.12)."""

    ASSIGNMENT = "assignment"
    BIOLOGICAL_SOURCE = "biological_source"
    EXPOSURE_INTERFERENCE = "exposure_interference"
    ANALYTICAL = "analytical"


class TriState(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class IndependenceProfile(FrozenModel):
    """Profilo delle quattro indipendenze: nessuna proxy automatica tra dimensioni.

    - assignment -> ``independently_assigned`` (tri-state);
    - biological_source -> ``biological_source_independence`` (tri-state);
    - exposure/interference -> ``interference_assessment`` (mai "assente" da silenzio);
    - analytical -> struttura di grouping/repeated-measure, non un booleano.
    """

    independently_assigned: TriState = TriState.UNKNOWN
    biological_source_independence: TriState = TriState.UNKNOWN
    interference_status: InterferenceStatus = InterferenceStatus.UNKNOWN
    analytical_grouping: tuple[str, ...] = ()  # livelli di clustering dichiarati
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _true_requires_mechanism_evidence(self) -> Self:
        if self.independently_assigned is TriState.TRUE and not self.evidence_ids:
            raise ValueError("independently_assigned=TRUE richiede evidenza esplicita")
        return self

    def proxy_forbidden(self) -> None:
        """Promemoria normativo: nessuna dimensione e proxy di un'altra."""
        return None


class QueryCausalContext(KernelModel):
    """Query-scoped v8 causal roles, stored without a scientific resolver.

    Assignment, application, effective exposure, experimental and biological-source
    units are separate facts even when their reported labels happen to match.
    """

    inferential_query_id: NonBlankStr
    assignment_event_id: KnowledgeValue[NonBlankStr]
    application_event_id: KnowledgeValue[NonBlankStr]
    exposure_event_id: KnowledgeValue[NonBlankStr]
    assignment_unit_type: KnowledgeValue[NonBlankStr]
    application_unit_type: KnowledgeValue[NonBlankStr]
    effective_exposure_unit_type: KnowledgeValue[NonBlankStr]
    experimental_unit_type: KnowledgeValue[NonBlankStr]
    biological_source_unit_type: KnowledgeValue[NonBlankStr]
    interference_status: KnowledgeValue[InterferenceStatus]

    @model_validator(mode="after")
    def _query_scopes_match(self) -> Self:
        for field_name in (
            "assignment_event_id",
            "application_event_id",
            "exposure_event_id",
            "assignment_unit_type",
            "application_unit_type",
            "effective_exposure_unit_type",
            "experimental_unit_type",
            "biological_source_unit_type",
            "interference_status",
        ):
            value = getattr(self, field_name)
            if (
                value.query_scope_id is not None
                and value.query_scope_id != self.inferential_query_id
            ):
                raise ValueError(f"{field_name}.query_scope_id must match inferential query")
        return self


class QueryCausalEventAggregate(KernelModel):
    """Resolve causal event references and block boundaries without deriving consequences."""

    experiment_block_id: NonBlankStr
    event_registry: EventRegistry
    causal_context: QueryCausalContext

    @model_validator(mode="after")
    def _resolve_typed_event_references(self) -> Self:
        expected_types: tuple[
            tuple[str, type[EventRecord]],
            ...,
        ] = (
            ("assignment_event_id", AssignmentEvent),
            ("application_event_id", ApplicationEvent),
            ("exposure_event_id", ExposureEvent),
        )
        for field_name, expected_type in expected_types:
            reference = getattr(self.causal_context, field_name)
            if reference.knowledge_state is not KnowledgeState.PRESENT:
                continue
            event_id = reference.value
            try:
                event = self.event_registry.event(event_id)
            except KeyError as error:
                raise ValueError(f"dangling {field_name}: {event_id}") from error
            if not isinstance(event, expected_type):
                raise ValueError(f"{field_name} requires {expected_type.__name__}")
            if event.experiment_block_id != self.experiment_block_id:
                raise ValueError(
                    f"cross-block {field_name}: {event.experiment_block_id} != "
                    f"{self.experiment_block_id}"
                )
        return self
