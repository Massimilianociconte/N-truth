"""Predicati del Reality Gate (PRD v7 §0.7).

Ogni predicato supporta TRUE / FALSE / UNKNOWN / NOT_APPLICABLE. Un gate puo
essere bloccato da UNKNOWN (fail-closed). Predicati assenti sono materializzati
come UNKNOWN. Corpora pubblici, structured decoding e SYN-G1 NON soddisfano
i predicati di real-anchor o di validazione scientifica.
"""

from __future__ import annotations

from enum import StrEnum

from ntruth.schemas.core import FrozenModel


class GateValue(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class GatePredicateName(StrEnum):
    SCHEMA_STABLE_ON_REAL_CASES = "schema_stable_on_real_cases"
    HUMAN_SECOND_REVIEW_COMPLETED = "human_second_review_completed"
    NO_BLOCKING_SCHEMA_GAPS = "no_blocking_schema_gaps"
    REAL_ANCHOR_AVAILABLE = "real_anchor_available"
    LICENCE_SCOPE_VERIFIED = "licence_scope_verified"
    PROTECTED_SPLIT_FROZEN = "protected_split_frozen"
    DECISIVE_FIELDS_REVIEWED = "decisive_fields_reviewed"
    REAL_BASELINE_EXECUTED = "real_baseline_executed"
    SYNTHETIC_FACTORY_HUMAN_CALIBRATED = "synthetic_factory_human_calibrated"
    # Legacy ambiguous name retained only for migration helpers.
    BLOCKING_SCHEMA_GAPS = "blocking_schema_gaps"


PREDICATE_ALIASES: dict[str, GatePredicateName] = {
    "blocking_schema_gaps": GatePredicateName.NO_BLOCKING_SCHEMA_GAPS,
    "no_blocking_schema_gaps": GatePredicateName.NO_BLOCKING_SCHEMA_GAPS,
}


def normalize_predicate_name(raw: str | GatePredicateName) -> GatePredicateName:
    if isinstance(raw, GatePredicateName):
        if raw is GatePredicateName.BLOCKING_SCHEMA_GAPS:
            return GatePredicateName.NO_BLOCKING_SCHEMA_GAPS
        return raw
    key = raw.strip().lower()
    if key in PREDICATE_ALIASES:
        return PREDICATE_ALIASES[key]
    return GatePredicateName(key)


class PredicateEvidence(FrozenModel):
    basis: str
    artefact_ref: str | None = None
    note: str = ""


class RealityGatePredicate(FrozenModel):
    name: GatePredicateName
    value: GateValue = GateValue.UNKNOWN
    evidence: PredicateEvidence
    applicable: bool = True

    def blocks(self) -> bool:
        if not self.applicable or self.value is GateValue.NOT_APPLICABLE:
            return False
        return self.value in (GateValue.FALSE, GateValue.UNKNOWN)


MVT_A_EXEMPT_PREDICATES: frozenset[GatePredicateName] = frozenset(
    {GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED}
)


def predicate_for_mvt_a(
    name: GatePredicateName, evidence: PredicateEvidence
) -> RealityGatePredicate:
    canonical = normalize_predicate_name(name)
    applicable = canonical not in MVT_A_EXEMPT_PREDICATES
    return RealityGatePredicate(
        name=canonical,
        value=GateValue.NOT_APPLICABLE if not applicable else GateValue.UNKNOWN,
        evidence=evidence,
        applicable=applicable,
    )


def missing_predicate(name: GatePredicateName) -> RealityGatePredicate:
    return RealityGatePredicate(
        name=normalize_predicate_name(name),
        value=GateValue.UNKNOWN,
        evidence=PredicateEvidence(basis="predicate not supplied: fail-closed UNKNOWN"),
        applicable=True,
    )
