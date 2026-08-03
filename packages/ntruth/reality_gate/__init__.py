"""Reality Gate v7: engineering readiness, data readiness, scientific validation.

Le tre dimensioni sono indipendenti e riportate separatamente (PRD v7 §0.7,
Fig. 2): nessun collasso in un singolo booleano senza diagnostica. Il gate e
fail-closed: UNKNOWN blocca come FALSE (NFR-28).
"""

from ntruth.reality_gate.predicates import (
    GatePredicateName,
    GateValue,
    PredicateEvidence,
    RealityGatePredicate,
)
from ntruth.reality_gate.gate import (
    DataReadiness,
    EngineeringReadiness,
    RealityDimension,
    RealityGateResult,
    ScientificValidation,
    evaluate_reality_gate,
)
from ntruth.reality_gate.report import (
    human_blocker_report,
    machine_readable_result,
)

__all__ = [
    "DataReadiness",
    "EngineeringReadiness",
    "GatePredicateName",
    "GateValue",
    "PredicateEvidence",
    "RealityDimension",
    "RealityGatePredicate",
    "RealityGateResult",
    "ScientificValidation",
    "evaluate_reality_gate",
    "human_blocker_report",
    "machine_readable_result",
]
