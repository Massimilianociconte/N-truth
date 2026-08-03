"""Composizione fail-closed del Reality Gate (PRD v7 §0.7, §25.6).

Predicati mancanti -> UNKNOWN materializzato. Duplicati -> errore.
Le tre dimensioni restano separate. Claim AI supportati solo con VALIDATED
e challenge indipendente documentata.
"""

from __future__ import annotations

from enum import StrEnum

from ntruth.reality_gate.predicates import (
    GatePredicateName,
    GateValue,
    PredicateEvidence,
    RealityGatePredicate,
    missing_predicate,
    normalize_predicate_name,
)
from ntruth.schemas.core import FrozenModel


class EngineeringReadiness(StrEnum):
    PARTIAL_OR_VERIFIED_BY_COMPONENT = "PARTIAL_OR_VERIFIED_BY_COMPONENT"


class DataReadiness(StrEnum):
    BLOCKED = "BLOCKED"
    READY = "READY"


class ScientificValidation(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    VALIDATED = "VALIDATED"


class GatePurpose(StrEnum):
    MVT_A_EXPLORATORY = "MVT_A_EXPLORATORY"
    SUBSTANTIVE_TRAINING = "SUBSTANTIVE_TRAINING"
    SUPPORTED_AI_RELEASE = "SUPPORTED_AI_RELEASE"


ENGINEERING_PREDICATES: tuple[GatePredicateName, ...] = (
    GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES,
    GatePredicateName.NO_BLOCKING_SCHEMA_GAPS,
)

DATA_PREDICATES: tuple[GatePredicateName, ...] = (
    GatePredicateName.REAL_ANCHOR_AVAILABLE,
    GatePredicateName.LICENCE_SCOPE_VERIFIED,
    GatePredicateName.PROTECTED_SPLIT_FROZEN,
    GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED,
    GatePredicateName.DECISIVE_FIELDS_REVIEWED,
    GatePredicateName.REAL_BASELINE_EXECUTED,
    GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED,
)

PURPOSE_REQUIRED: dict[GatePurpose, tuple[GatePredicateName, ...]] = {
    GatePurpose.MVT_A_EXPLORATORY: (
        *ENGINEERING_PREDICATES,
        GatePredicateName.REAL_ANCHOR_AVAILABLE,
        GatePredicateName.LICENCE_SCOPE_VERIFIED,
        GatePredicateName.PROTECTED_SPLIT_FROZEN,
        GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED,
        GatePredicateName.DECISIVE_FIELDS_REVIEWED,
        GatePredicateName.REAL_BASELINE_EXECUTED,
        GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED,
    ),
    GatePurpose.SUBSTANTIVE_TRAINING: (*ENGINEERING_PREDICATES, *DATA_PREDICATES),
    GatePurpose.SUPPORTED_AI_RELEASE: (*ENGINEERING_PREDICATES, *DATA_PREDICATES),
}


class ScientificValidationEvidence(FrozenModel):
    status: ScientificValidation = ScientificValidation.NOT_STARTED
    evidence_basis: str = "not started"
    independent_challenge_ref: str | None = None
    blockers: tuple[str, ...] = ()

    def effective_blockers(self) -> tuple[str, ...]:
        blockers = list(self.blockers)
        if self.status is ScientificValidation.VALIDATED:
            if not self.independent_challenge_ref or not self.independent_challenge_ref.strip():
                blockers.append("VALIDATED without independent_challenge_ref")
            if not self.evidence_basis.strip():
                blockers.append("VALIDATED without evidence_basis")
        return tuple(dict.fromkeys(blockers))


class RealityDimension(FrozenModel):
    name: str
    status: str
    predicates: tuple[RealityGatePredicate, ...] = ()
    blockers: tuple[str, ...] = ()


class RealityGateResult(FrozenModel):
    gate_version: str = "7.0.0"
    purpose: GatePurpose = GatePurpose.MVT_A_EXPLORATORY
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


def _dedupe(
    predicates: tuple[RealityGatePredicate, ...],
) -> dict[GatePredicateName, RealityGatePredicate]:
    by_name: dict[GatePredicateName, RealityGatePredicate] = {}
    for pred in predicates:
        name = normalize_predicate_name(pred.name)
        if name in by_name:
            raise ValueError(f"duplicate Reality Gate predicate: {name.value}")
        by_name[name] = RealityGatePredicate(
            name=name,
            value=pred.value,
            evidence=pred.evidence,
            applicable=pred.applicable,
        )
    return by_name


def evaluate_reality_gate(
    predicates: tuple[RealityGatePredicate, ...],
    *,
    purpose: GatePurpose = GatePurpose.MVT_A_EXPLORATORY,
    scientific_validation: ScientificValidationEvidence | ScientificValidation | None = None,
    scientific_validation_status: ScientificValidation | None = None,
) -> RealityGateResult:
    if scientific_validation is None and scientific_validation_status is not None:
        scientific_validation = ScientificValidationEvidence(
            status=scientific_validation_status,
            evidence_basis="legacy scientific_validation_status argument",
            independent_challenge_ref=(
                "legacy-no-ref"
                if scientific_validation_status is ScientificValidation.VALIDATED
                else None
            ),
        )
    if scientific_validation is None:
        scientific_validation = ScientificValidationEvidence()
    if isinstance(scientific_validation, ScientificValidation):
        status = scientific_validation
        scientific_validation = ScientificValidationEvidence(
            status=status,
            evidence_basis="enum-only (legacy)",
            independent_challenge_ref=(
                "legacy-no-ref" if status is ScientificValidation.VALIDATED else None
            ),
        )

    normalized: list[RealityGatePredicate] = []
    for pred in predicates:
        name = normalize_predicate_name(pred.name)
        value = pred.value
        if pred.name is GatePredicateName.BLOCKING_SCHEMA_GAPS:
            # TRUE "gaps exist" -> NO_BLOCKING_SCHEMA_GAPS = FALSE
            if value is GateValue.TRUE:
                value = GateValue.FALSE
            elif value is GateValue.FALSE:
                value = GateValue.TRUE
            name = GatePredicateName.NO_BLOCKING_SCHEMA_GAPS
        normalized.append(
            RealityGatePredicate(
                name=name,
                value=value,
                evidence=pred.evidence,
                applicable=pred.applicable,
            )
        )

    by_name = _dedupe(tuple(normalized))
    materialised: list[RealityGatePredicate] = []
    for name in PURPOSE_REQUIRED[purpose]:
        if name in by_name:
            materialised.append(by_name[name])
        elif (
            purpose is GatePurpose.MVT_A_EXPLORATORY
            and name is GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED
        ):
            materialised.append(
                RealityGatePredicate(
                    name=name,
                    value=GateValue.NOT_APPLICABLE,
                    evidence=PredicateEvidence(
                        basis="N/A for MVT-A exploratory when synthetic not used (E-14)"
                    ),
                    applicable=False,
                )
            )
        else:
            materialised.append(missing_predicate(name))

    eng = tuple(p for p in materialised if p.name in ENGINEERING_PREDICATES)
    data = tuple(p for p in materialised if p.name in DATA_PREDICATES)

    engineering = _dimension(
        "engineering_readiness",
        eng,
        ready_status=EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT.value,
        not_ready_status=EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT.value,
    )
    data_dim = _dimension(
        "data_readiness",
        data,
        ready_status=DataReadiness.READY.value,
        not_ready_status=DataReadiness.BLOCKED.value,
    )

    sci_blockers = list(scientific_validation.effective_blockers())
    scientific = RealityDimension(
        name="scientific_validation",
        status=scientific_validation.status.value,
        predicates=(),
        blockers=tuple(sci_blockers),
    )

    data_ready = data_dim.status == DataReadiness.READY.value
    training_allowed = (
        purpose in (GatePurpose.SUBSTANTIVE_TRAINING, GatePurpose.SUPPORTED_AI_RELEASE)
        and data_ready
        and not engineering.blockers
    )
    ai_claims_allowed = (
        purpose is GatePurpose.SUPPORTED_AI_RELEASE
        and data_ready
        and not engineering.blockers
        and scientific_validation.status is ScientificValidation.VALIDATED
        and bool(scientific_validation.independent_challenge_ref)
        and not scientific.blockers
    )
    if scientific_validation.status is ScientificValidation.IN_PROGRESS:
        ai_claims_allowed = False

    return RealityGateResult(
        purpose=purpose,
        engineering_readiness=engineering,
        data_readiness=data_dim,
        scientific_validation=scientific,
        substantive_training_allowed=training_allowed,
        ai_claims_allowed=ai_claims_allowed,
        overall_blockers=(*engineering.blockers, *data_dim.blockers, *scientific.blockers),
    )


EXPECTED_CURRENT_STATE = {
    "engineering_readiness": EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT.value,
    "data_readiness": DataReadiness.BLOCKED.value,
    "scientific_validation": ScientificValidation.NOT_STARTED.value,
    "substantive_training": "HOLD_PENDING_REAL_ANCHOR",
    "modernbert_training": "HOLD",
    "granite_promotion": "HOLD",
}
