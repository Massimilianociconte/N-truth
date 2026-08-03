"""Bootstrap Core v7: sottoinsieme minimo required-or-unknown (PRD v7 §8.2A, App. X.1).

Distinto dal Full Scientific Record: nessun lifecycle esteso, nessuna
alternative multipla obbligatoria. Ogni campo mancante e UNKNOWN, mai
sottinteso. Il parser produce soltanto candidati; i campi decisivi richiedono
conferma umana prima del rules engine.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.causal_context import CausalDesignContext, IndependenceProfile
from ntruth.schemas.core import FrozenModel, stable_id
from ntruth.schemas.counts import CountRecord
from ntruth.schemas.inferential_query import InferentialQuery

BOOTSTRAP_CORE_SCHEMA_VERSION: Literal["7.0.0"] = "7.0.0"

TriStateRequired = Literal["TRUE", "FALSE", "UNKNOWN"]


class CoreUnit(FrozenModel):
    """Istanza minima di unita nel Bootstrap Core."""

    id: str
    type: str
    label: str = ""


class CoreRelation(FrozenModel):
    """Relazione esplicita tra unita (derived_from/nested_in minimi)."""

    source: str
    type: str
    target: str


class CoreSourceRef(FrozenModel):
    """Riferimento a fonte ed evidenza decisiva."""

    source_id: str
    evidence_ids: tuple[str, ...] = ()
    license_status: str = "unknown"  # fail-closed: verified solo se registrato


class MissingDecisiveFact(FrozenModel):
    """Fatto decisivo assente che impedisce la chiusura (PRD v7 §8.2A)."""

    predicate: str
    rationale: str = ""


class BootstrapCoreRecord(FrozenModel):
    """Record Bootstrap Core v7 per il micro-dominio simple_cell_culture.

    Campi required-or-unknown (App. X.1): experiment block, fonti/evidenza,
    unita/relazioni, fattore/livelli, endpoint/contrasto, allocation/application,
    timing di assegnazione, preparazione sorgente, independently_assigned,
    conteggi chiave, fatto mancante/domanda, determinabilita derivata.
    """

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
    allocation_level: str = "unknown"      # required-or-UNKNOWN
    application_level: str | None = None   # optional-or-UNKNOWN
    independently_assigned: TriStateRequired = "UNKNOWN"
    source_preparation_id: str = "unknown"  # required-or-UNKNOWN
    independence: IndependenceProfile = Field(default_factory=IndependenceProfile)
    causal_context: CausalDesignContext | None = None
    counts: tuple[CountRecord, ...] = ()
    missing_decisive_fact: MissingDecisiveFact | None = None
    primary_question: str = ""
    inferential_query: InferentialQuery | None = None
    determinability_derived: str | None = None   # derivata dal ruleset, mai libera
    determinability_reviewed: bool = False       # revisione umana registrata

    @model_validator(mode="after")
    def _core_invariants(self) -> Self:
        if not self.experiment_block_id.strip():
            raise ValueError("bootstrap core senza experiment_block_id")
        unit_ids = {u.id for u in self.units}
        for relation in self.relations:
            if relation.source not in unit_ids or relation.target not in unit_ids:
                raise ValueError(f"relazione {relation.type} riferita a unita non dichiarate")
        for count in self.counts:
            if count.factor_id is not None and count.factor_id != self.factor_id:
                raise ValueError("conteggio riferito a un fattore fuori dal bootstrap core")
        if self.independently_assigned == "TRUE" and self.independence.evidence_ids == ():
            raise ValueError("independently_assigned=TRUE richiede evidenza esplicita")
        if self.determinability_reviewed and self.determinability_derived is None:
            raise ValueError("revisione registrata senza stato derivato")
        return self


def make_block_id(domain: str, label: str) -> str:
    return stable_id("eb", domain, label.strip().lower())
