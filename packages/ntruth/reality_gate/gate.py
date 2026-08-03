"""Composizione fail-closed del Reality Gate (PRD v7 §0.7, §25.6).

Le tre dimensioni restano separate e riportate per componente:
- engineering_readiness: riportata per componente (nessun singolo booleano);
- data_readiness: bloccata finche manca real anchor, licenze o split protetti;
- scientific_validation: NOT_STARTED finche non esiste valutazione indipendente.
"""

from __future__ import annotations

from enum import StrEnum

from ntruth.reality_gate.predicates import (
    GatePredicateName,
    RealityGatePredicate,
)
from ntruth.schemas.core import FrozenModel


class EngineeringReadiness(StrEnum):
    #: Stato riportato per componente: nessun singolo booleano senza diagnostica.
    PARTIAL_OR_VERIFIED_BY_COMPONENT = "PARTIAL_OR_VERIFIED_BY_COMPONENT"


class DataReadiness(StrEnum):
    BLOCKED = "BLOCKED"
    READY = "READY"  # raggiungibile solo con evidenza registrata


class ScientificValidation(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    VALIDATED = "VALIDATED"  # richiede external challenge reale


class RealityDimension(FrozenModel):
    """Una dimensione del gate con i propri predicati e il proprio stato."""

    name: str
    status: str
    predicates: tuple[RealityGatePredicate, ...] = ()
    blockers: tuple[str, ...] = ()


class RealityGateResult(FrozenModel):
    """Esito machine-readable: tre dimensioni, nessun collasso in un booleano."""

    gate_version: str = "7.0.0"
    engineering_readiness: RealityDimension
    data_readiness: RealityDimension
    scientific_validation: RealityDimension
    substantive_training_allowed: bool = False
    ai_claims_allowed: bool = False
    overall_blockers: tuple[str, ...] = ()


def _dimension(
    name: str,
    predicates: tuple[RealityGatePredicate, ...],
    ready_status: str,
    not_ready_status: str,
) -> RealityDimension:
    blockers = tuple(
        f"{p.name.value}: {p.value.value} ({p.evidence.basis})" for p in predicates if p.blocks()
    )
    status = ready_status if not blockers else not_ready_status
    return RealityDimension(name=name, status=status, predicates=predicates, blockers=blockers)


def evaluate_reality_gate(
    predicates: tuple[RealityGatePredicate, ...],
    *,
    scientific_validation_status: ScientificValidation = ScientificValidation.NOT_STARTED,
) -> RealityGateResult:
    """Compone le tre dimensioni in modo fail-closed.

    Non inventa stati: ogni valore deve arrivare dai predicati forniti, che a
    loro volta richiedono evidenza registrata nel clean checkout.
    """
    by_name = {p.name: p for p in predicates}

    def subset(names: tuple[GatePredicateName, ...]) -> tuple[RealityGatePredicate, ...]:
        return tuple(by_name[n] for n in names if n in by_name)

    engineering_names = (
        GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES,
        GatePredicateName.BLOCKING_SCHEMA_GAPS,
    )
    data_names = (
        GatePredicateName.REAL_ANCHOR_AVAILABLE,
        GatePredicateName.LICENCE_SCOPE_VERIFIED,
        GatePredicateName.PROTECTED_SPLIT_FROZEN,
        GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED,
        GatePredicateName.DECISIVE_FIELDS_REVIEWED,
        GatePredicateName.REAL_BASELINE_EXECUTED,
        GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED,
    )

    engineering = _dimension(
        "engineering_readiness",
        subset(engineering_names),
        ready_status=EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT.value,
        not_ready_status=EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT.value,
    )
    data = _dimension(
        "data_readiness",
        subset(data_names),
        ready_status=DataReadiness.READY.value,
        not_ready_status=DataReadiness.BLOCKED.value,
    )
    scientific = _dimension(
        "scientific_validation",
        (),
        ready_status=scientific_validation_status.value,
        not_ready_status=scientific_validation_status.value,
    )

    training_allowed = (
        not data.blockers and scientific_validation_status is not ScientificValidation.NOT_STARTED
    )
    ai_claims_allowed = training_allowed and not scientific.blockers

    return RealityGateResult(
        engineering_readiness=engineering,
        data_readiness=data,
        scientific_validation=RealityDimension(
            name="scientific_validation",
            status=scientific_validation_status.value,
            predicates=(),
            blockers=(),
        ),
        substantive_training_allowed=training_allowed,
        ai_claims_allowed=ai_claims_allowed,
        overall_blockers=(*engineering.blockers, *data.blockers),
    )


#: Stato atteso del progetto al momento (documento, non claim):
#: engineering REPORTED_BY_COMPONENT, data BLOCKED, scientific NOT_STARTED,
#: training HOLD_PENDING_REAL_ANCHOR.
EXPECTED_CURRENT_STATE = {
    "engineering_readiness": EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT.value,
    "data_readiness": DataReadiness.BLOCKED.value,
    "scientific_validation": ScientificValidation.NOT_STARTED.value,
    "substantive_training": "HOLD_PENDING_REAL_ANCHOR",
    "modernbert_training": "HOLD",
    "granite_promotion": "HOLD",
}
