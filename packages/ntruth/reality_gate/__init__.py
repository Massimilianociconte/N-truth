"""Reality Gate v7: engineering, data and scientific dimensions (fail-closed)."""

from ntruth.reality_gate.gate import (
    DataReadiness,
    EngineeringReadiness,
    GatePurpose,
    RealityDimension,
    RealityGateResult,
    ScientificValidation,
    ScientificValidationEvidence,
    evaluate_reality_gate,
)
from ntruth.reality_gate.predicates import (
    GatePredicateName,
    GateValue,
    PredicateEvidence,
    RealityGatePredicate,
    normalize_predicate_name,
    predicate_for_mvt_a,
)
from ntruth.reality_gate.report import human_blocker_report, machine_readable_result

__all__ = [
    "DataReadiness",
    "EngineeringReadiness",
    "GatePredicateName",
    "GatePurpose",
    "GateValue",
    "PredicateEvidence",
    "RealityDimension",
    "RealityGatePredicate",
    "RealityGateResult",
    "ScientificValidation",
    "ScientificValidationEvidence",
    "evaluate_reality_gate",
    "human_blocker_report",
    "machine_readable_result",
    "normalize_predicate_name",
    "predicate_for_mvt_a",
]
