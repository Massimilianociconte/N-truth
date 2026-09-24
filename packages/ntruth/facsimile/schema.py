"""Projection schema for automated record-to-facsimile invariant gates.

The models in this module do not implement a renderer and do not make a view
authoritative. They validate the scientific subset a future renderer is allowed
to display, while the canonical ExperimentBlock/training record remains the
source of truth.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from ntruth.governance.lineage import CorpusSplit, validate_split_eligibility
from ntruth.schemas.core import Determinability, EvidenceType, FrozenModel
from ntruth.schemas.experiment import CountKind, CountRecord

FACSIMILE_SCIENTIFIC_PROJECTION_VERSION: Literal["1.0.0"] = "1.0.0"


class FacsimileReviewDimension(StrEnum):
    """Dimensioni separate: portata del claim non equivale ad allocation."""

    INFERENCE_SCOPE = "inference_scope"
    ALLOCATION_VALIDITY = "allocation_validity"


class FacsimileReviewStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    LIMITED = "LIMITED"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


class FacsimileReviewField(FrozenModel):
    """Campo scientifico visualizzabile con dimensione ed evidenza esplicite."""

    field_id: str
    dimension: FacsimileReviewDimension
    status: FacsimileReviewStatus
    statement: str
    evidence_ids: tuple[str, ...] = ()

    @field_validator("field_id", "statement")
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("campo facsimile con testo obbligatorio vuoto")
        return normalized

    @field_validator("evidence_ids")
    @classmethod
    def _unique_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("evidence_ids duplicati nel campo facsimile")
        return values


class FacsimileScientificProjection(FrozenModel):
    """Subset tipizzato che un render puo mostrare senza fondere concetti.

    ``experimental_unit_count`` usa il count canonico ``independent_n``: e il
    numero di unita sperimentali indipendenti nello scope del contrasto. Rimane
    un record semanticamente distinto da ``biological_source_count`` anche
    quando i due valori numerici coincidono.
    """

    schema_version: Literal["1.0.0"] = FACSIMILE_SCIENTIFIC_PROJECTION_VERSION
    source_record_id: str
    source_record_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    family_id: str
    leakage_group_id: str
    split: CorpusSplit
    training_eligible: bool = False
    evaluation_eligible: bool = False
    synthetic_notice: bool
    experimental_unit_count: CountRecord
    biological_source_count: CountRecord
    inference_scope: FacsimileReviewField
    validity_of_allocation: FacsimileReviewField
    determinability: Determinability
    decisive_evidence_types: tuple[EvidenceType, ...] = ()

    @field_validator("source_record_id", "family_id", "leakage_group_id")
    @classmethod
    def _required_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("projection facsimile con identificatore vuoto")
        return normalized

    @model_validator(mode="after")
    def _semantic_and_governance_gates(self) -> Self:
        validate_split_eligibility(
            self.split,
            training_eligible=self.training_eligible,
            evaluation_eligible=self.evaluation_eligible,
        )
        if self.experimental_unit_count.kind is not CountKind.INDEPENDENT_N:
            raise ValueError("experimental_unit_count richiede kind=independent_n")
        if self.biological_source_count.kind is not CountKind.BIOLOGICAL_SOURCE_COUNT:
            raise ValueError("biological_source_count richiede kind=biological_source_count")
        if self.experimental_unit_count.count_id == self.biological_source_count.count_id:
            raise ValueError("EU count e biological source count richiedono record distinti")
        if self.inference_scope.dimension is not FacsimileReviewDimension.INFERENCE_SCOPE:
            raise ValueError("inference_scope richiede dimension=inference_scope")
        if (
            self.validity_of_allocation.dimension
            is not FacsimileReviewDimension.ALLOCATION_VALIDITY
        ):
            raise ValueError("validity_of_allocation richiede dimension=allocation_validity")
        if len(self.decisive_evidence_types) != len(set(self.decisive_evidence_types)):
            raise ValueError("decisive_evidence_types duplicati")
        if self.determinability is Determinability.DETERMINATE and (
            not self.decisive_evidence_types
            or set(self.decisive_evidence_types) == {EvidenceType.AUTHOR_ASSERTION}
        ):
            raise ValueError("AUTHOR_ASSERTION da sola non chiude determinability")
        return self


__all__ = [
    "FACSIMILE_SCIENTIFIC_PROJECTION_VERSION",
    "FacsimileReviewDimension",
    "FacsimileReviewField",
    "FacsimileReviewStatus",
    "FacsimileScientificProjection",
]
