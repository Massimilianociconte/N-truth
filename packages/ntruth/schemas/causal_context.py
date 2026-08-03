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
            raise ValueError(
                "no_known_path richiede evidenza positiva: il silenzio vale UNKNOWN"
            )
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
    interference_assessment: InterferenceAssessment = Field(
        default_factory=InterferenceAssessment
    )
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
