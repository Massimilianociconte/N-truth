"""Bootstrap Core v7: required-or-unknown (PRD v7 §8.2A, App. X.1)."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.causal_context import CausalDesignContext, IndependenceProfile, TriState
from ntruth.schemas.core import FrozenModel, stable_id
from ntruth.schemas.counts import CountRecord
from ntruth.schemas.determinability_v7 import DeterminabilityStateV7
from ntruth.schemas.inferential_query import InferentialQuery
from ntruth.schemas.relations import REGISTERED_RELATION_VALUES, canonical_relation

BOOTSTRAP_CORE_SCHEMA_VERSION: Literal["7.0.0"] = "7.0.0"
TriStateRequired = Literal["TRUE", "FALSE", "UNKNOWN"]


class CoreUnit(FrozenModel):
    id: str
    type: str
    label: str = ""


class CoreRelation(FrozenModel):
    source: str
    type: str
    target: str


class CoreSourceRef(FrozenModel):
    source_id: str
    evidence_ids: tuple[str, ...] = ()
    license_status: str = "unknown"


class MissingDecisiveFact(FrozenModel):
    predicate: str
    rationale: str = ""


class BootstrapCoreRecord(FrozenModel):
    schema_version: Literal["7.0.0"] = BOOTSTRAP_CORE_SCHEMA_VERSION
    experiment_block_id: str
    profile: str = "bootstrap_core"
    domain: str = "simple_cell_culture"
    sources: tuple[CoreSourceRef, ...] = Field(min_length=1)
    units: tuple[CoreUnit, ...] = Field(min_length=1)
    relations: tuple[CoreRelation, ...] = Field(min_length=1)
    factor_id: str
    factor_levels: tuple[str, ...] = Field(min_length=2)
    endpoint_id: str
    primary_contrast_id: str
    allocation_level: str = "unknown"
    application_level: str | None = None
    independently_assigned: TriStateRequired = "UNKNOWN"
    source_preparation_id: str = "unknown"
    independence: IndependenceProfile = Field(default_factory=IndependenceProfile)
    causal_context: CausalDesignContext | None = None
    counts: tuple[CountRecord, ...] = ()
    missing_decisive_fact: MissingDecisiveFact | None = None
    primary_question: str = ""
    inferential_query: InferentialQuery | None = None
    determinability_derived: DeterminabilityStateV7 | None = None
    determinability_reviewed: bool = False
    determinability_review_event_id: str | None = None

    @model_validator(mode="after")
    def _core_invariants(self) -> Self:
        if not self.experiment_block_id.strip():
            raise ValueError("bootstrap core senza experiment_block_id")
        unit_ids = {u.id for u in self.units}
        for relation in self.relations:
            if relation.source not in unit_ids or relation.target not in unit_ids:
                raise ValueError(f"relazione {relation.type} riferita a unita non dichiarate")
            try:
                rel = canonical_relation(relation.type)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
            if rel.value not in REGISTERED_RELATION_VALUES:
                raise ValueError(f"relazione non registrata: {relation.type}")
        for count in self.counts:
            if count.factor_id is not None and count.factor_id != self.factor_id:
                raise ValueError("conteggio riferito a un fattore fuori dal bootstrap core")
        nested = self.independence.independently_assigned
        top = TriState(self.independently_assigned)
        if nested is not top:
            raise ValueError(
                "independently_assigned top-level e independence.independently_assigned non coincidono"
            )
        if self.independently_assigned == "TRUE" and self.independence.evidence_ids == ():
            raise ValueError("independently_assigned=TRUE richiede evidenza esplicita")
        if (
            self.source_preparation_id not in ("unknown", "")
            and self.source_preparation_id not in unit_ids
        ):
            raise ValueError("source_preparation_id non riferisce un'unita dichiarata")
        if self.causal_context is not None and self.causal_context.factor_id != self.factor_id:
            raise ValueError("causal_context.factor_id diverso dal factor_id del bootstrap")
        if self.inferential_query is not None:
            iq = self.inferential_query
            if iq.factor_id != self.factor_id:
                raise ValueError("inferential_query.factor_id non allineato")
            if iq.endpoint_id != self.endpoint_id:
                raise ValueError("inferential_query.endpoint_id non allineato")
            for level in iq.compared_levels:
                if level not in self.factor_levels:
                    raise ValueError(f"livello {level!r} assente da factor_levels")
        if self.determinability_reviewed:
            if self.determinability_derived is None:
                raise ValueError("revisione registrata senza stato derivato")
            if not self.determinability_review_event_id:
                raise ValueError(
                    "determinability_reviewed richiede determinability_review_event_id"
                )
        return self


def make_block_id(domain: str, label: str) -> str:
    return stable_id("eb", domain, label.strip().lower())
