"""Reality Gate fail-closed behaviour (PRD v7 §0.7)."""

from __future__ import annotations

from ntruth.reality_gate import (
    DataReadiness,
    GatePredicateName,
    GateValue,
    PredicateEvidence,
    RealityGatePredicate,
    ScientificValidation,
    evaluate_reality_gate,
    human_blocker_report,
    machine_readable_result,
)
from ntruth.reality_gate.gate import EXPECTED_CURRENT_STATE
from ntruth.reality_gate.predicates import predicate_for_mvt_a


def _p(name: GatePredicateName, value: GateValue) -> RealityGatePredicate:
    return RealityGatePredicate(
        name=name,
        value=value,
        evidence=PredicateEvidence(basis="unit-test"),
    )


def test_unknown_blocks_like_false() -> None:
    preds = (
        _p(GatePredicateName.REAL_ANCHOR_AVAILABLE, GateValue.UNKNOWN),
        _p(GatePredicateName.LICENCE_SCOPE_VERIFIED, GateValue.TRUE),
        _p(GatePredicateName.PROTECTED_SPLIT_FROZEN, GateValue.TRUE),
        _p(GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED, GateValue.TRUE),
        _p(GatePredicateName.DECISIVE_FIELDS_REVIEWED, GateValue.TRUE),
        _p(GatePredicateName.REAL_BASELINE_EXECUTED, GateValue.TRUE),
        _p(GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES, GateValue.TRUE),
        _p(GatePredicateName.BLOCKING_SCHEMA_GAPS, GateValue.TRUE),
    )
    result = evaluate_reality_gate(preds)
    assert result.data_readiness.status == DataReadiness.BLOCKED.value
    assert any("real_anchor_available" in b for b in result.data_readiness.blockers)
    assert result.substantive_training_allowed is False


def test_not_applicable_does_not_block() -> None:
    p = predicate_for_mvt_a(
        GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED,
        PredicateEvidence(basis="MVT-A exempt E-14"),
    )
    assert p.value is GateValue.NOT_APPLICABLE
    assert p.blocks() is False


def test_three_dimensions_not_collapsed() -> None:
    preds = (
        _p(GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES, GateValue.UNKNOWN),
        _p(GatePredicateName.REAL_ANCHOR_AVAILABLE, GateValue.FALSE),
    )
    result = evaluate_reality_gate(
        preds, scientific_validation_status=ScientificValidation.NOT_STARTED
    )
    machine = machine_readable_result(result)
    assert "engineering_readiness" in machine
    assert "data_readiness" in machine
    assert "scientific_validation" in machine
    assert result.scientific_validation.status == ScientificValidation.NOT_STARTED.value
    report = human_blocker_report(result)
    assert "BLOCK" in report.upper() or "block" in report.lower() or "UNKNOWN" in report


def test_expected_current_state_constants() -> None:
    assert EXPECTED_CURRENT_STATE["data_readiness"] == "BLOCKED"
    assert EXPECTED_CURRENT_STATE["scientific_validation"] == "NOT_STARTED"
    assert EXPECTED_CURRENT_STATE["substantive_training"] == "HOLD_PENDING_REAL_ANCHOR"
    assert EXPECTED_CURRENT_STATE["modernbert_training"] == "HOLD"
    assert EXPECTED_CURRENT_STATE["granite_promotion"] == "HOLD"
