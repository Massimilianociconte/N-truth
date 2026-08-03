"""Predicati del Reality Gate (PRD v7 §0.7).

Ogni predicato supporta TRUE / FALSE / UNKNOWN / NOT_APPLICABLE. Un gate puo
essere bloccato da UNKNOWN (fail-closed). L'evidenza di ogni predicato deve
essere registrata: corpora pubblici, structured decoding, smoke di engineering
e SYN-G1 NON soddisfano i predicati di real-anchor o di validazione scientifica.
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
    BLOCKING_SCHEMA_GAPS = "blocking_schema_gaps"
    REAL_ANCHOR_AVAILABLE = "real_anchor_available"
    LICENCE_SCOPE_VERIFIED = "licence_scope_verified"
    PROTECTED_SPLIT_FROZEN = "protected_split_frozen"
    DECISIVE_FIELDS_REVIEWED = "decisive_fields_reviewed"
    REAL_BASELINE_EXECUTED = "real_baseline_executed"
    SYNTHETIC_FACTORY_HUMAN_CALIBRATED = "synthetic_factory_human_calibrated"


class PredicateEvidence(FrozenModel):
    """Provenienza del valore di un predicato: niente stati senza prova."""

    basis: str                      # perche il valore e questo (riferimento auditabile)
    artefact_ref: str | None = None # file/registro/hash nel clean checkout, se esiste
    note: str = ""


class RealityGatePredicate(FrozenModel):
    """Stato di un predicato con evidenza e applicabilita."""

    name: GatePredicateName
    value: GateValue = GateValue.UNKNOWN
    evidence: PredicateEvidence
    applicable: bool = True

    def blocks(self) -> bool:
        """Fail-closed: FALSE e UNKNOWN bloccano; NOT_APPLICABLE no."""
        if not self.applicable:
            return False
        return self.value in (GateValue.FALSE, GateValue.UNKNOWN)


#: Il predicato synthetic_factory_human_calibrated si applica solo quando viene
#: richiesta la promozione di synthetic o il fine-tuning sostanziale (ERRATA E-14):
#: per Minimum Viable Train A resta NOT_APPLICABLE.
MVT_A_EXEMPT_PREDICATES: frozenset[GatePredicateName] = frozenset(
    {GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED}
)


def predicate_for_mvt_a(
    name: GatePredicateName, evidence: PredicateEvidence
) -> RealityGatePredicate:
    """Costruisce il predicato nel contesto MVT-A (nessuna promozione synthetic)."""
    applicable = name not in MVT_A_EXEMPT_PREDICATES
    return RealityGatePredicate(
        name=name,
        value=GateValue.NOT_APPLICABLE if not applicable else GateValue.UNKNOWN,
        evidence=evidence,
        applicable=applicable,
    )
