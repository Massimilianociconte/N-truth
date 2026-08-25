"""Explicit compatibility namespace for the historical PRD v7 Reality Gate."""

from ntruth.reality_gate.gate import (
    EXPECTED_CURRENT_STATE as EXPECTED_CURRENT_STATE_V7,
)
from ntruth.reality_gate.gate import (
    DataReadiness as DataReadinessV7,
)
from ntruth.reality_gate.gate import (
    EngineeringReadiness as EngineeringReadinessV7,
)
from ntruth.reality_gate.gate import (
    GatePurpose as GatePurposeV7,
)
from ntruth.reality_gate.gate import (
    RealityDimension as RealityDimensionV7,
)
from ntruth.reality_gate.gate import (
    RealityGateResult as RealityGateResultV7,
)
from ntruth.reality_gate.gate import (
    ScientificValidation as ScientificValidationV7,
)
from ntruth.reality_gate.gate import (
    ScientificValidationEvidence as ScientificValidationEvidenceV7,
)
from ntruth.reality_gate.gate import (
    evaluate_reality_gate as evaluate_reality_gate_v7,
)
from ntruth.reality_gate.predicates import (
    GatePredicateName as GatePredicateNameV7,
)
from ntruth.reality_gate.predicates import (
    GateValue as GateValueV7,
)
from ntruth.reality_gate.predicates import (
    PredicateEvidence as PredicateEvidenceV7,
)
from ntruth.reality_gate.predicates import (
    RealityGatePredicate as RealityGatePredicateV7,
)
from ntruth.reality_gate.predicates import (
    normalize_predicate_name as normalize_predicate_name_v7,
)
from ntruth.reality_gate.predicates import (
    predicate_for_mvt_a as predicate_for_mvt_a_v7,
)
from ntruth.reality_gate.report import (
    human_blocker_report as human_blocker_report_v7,
)
from ntruth.reality_gate.report import (
    machine_readable_result as machine_readable_result_v7,
)

__all__ = [
    "EXPECTED_CURRENT_STATE_V7",
    "DataReadinessV7",
    "EngineeringReadinessV7",
    "GatePredicateNameV7",
    "GatePurposeV7",
    "GateValueV7",
    "PredicateEvidenceV7",
    "RealityDimensionV7",
    "RealityGatePredicateV7",
    "RealityGateResultV7",
    "ScientificValidationEvidenceV7",
    "ScientificValidationV7",
    "evaluate_reality_gate_v7",
    "human_blocker_report_v7",
    "machine_readable_result_v7",
    "normalize_predicate_name_v7",
    "predicate_for_mvt_a_v7",
]
