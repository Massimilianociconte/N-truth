"""Reality Gate fail-closed behaviour (PRD v7 §0.7)."""

from __future__ import annotations

import pytest

from ntruth.reality_gate import (
    DataReadiness,
    GatePredicateName,
    GatePurpose,
    GateValue,
    PredicateEvidence,
    RealityGatePredicate,
    ScientificValidation,
    ScientificValidationEvidence,
    evaluate_reality_gate,
    human_blocker_report,
    machine_readable_result,
)
from ntruth.reality_gate.gate import EXPECTED_CURRENT_STATE
from ntruth.reality_gate.predicates import normalize_predicate_name, predicate_for_mvt_a


def _p(name: GatePredicateName, value: GateValue) -> RealityGatePredicate:
    return RealityGatePredicate(
        name=name, value=value, evidence=PredicateEvidence(basis="unit-test")
    )


def test_empty_predicates_block_data_readiness() -> None:
    result = evaluate_reality_gate(())
    assert result.data_readiness.status == DataReadiness.BLOCKED.value
    assert result.substantive_training_allowed is False
    assert result.ai_claims_allowed is False
    assert result.data_readiness.blockers


def test_missing_required_predicates_materialized_as_unknown() -> None:
    result = evaluate_reality_gate(
        (_p(GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES, GateValue.TRUE),)
    )
    names = {p.name for p in result.data_readiness.predicates}
    assert GatePredicateName.REAL_ANCHOR_AVAILABLE in names
    assert any("UNKNOWN" in b for b in result.data_readiness.blockers)


def test_duplicate_predicate_names_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_reality_gate(
            (
                _p(GatePredicateName.REAL_ANCHOR_AVAILABLE, GateValue.TRUE),
                _p(GatePredicateName.REAL_ANCHOR_AVAILABLE, GateValue.FALSE),
            )
        )


def test_validated_without_predicates_still_blocks_training_and_claims() -> None:
    result = evaluate_reality_gate(
        (),
        purpose=GatePurpose.SUPPORTED_AI_RELEASE,
        scientific_validation=ScientificValidationEvidence(
            status=ScientificValidation.VALIDATED,
            evidence_basis="claimed without challenge artefact",
            independent_challenge_ref=None,
        ),
    )
    assert result.substantive_training_allowed is False
    assert result.ai_claims_allowed is False


def test_in_progress_never_allows_ai_claims() -> None:
    preds = tuple(
        _p(name, GateValue.TRUE)
        for name in (
            GatePredicateName.REAL_ANCHOR_AVAILABLE,
            GatePredicateName.LICENCE_SCOPE_VERIFIED,
            GatePredicateName.PROTECTED_SPLIT_FROZEN,
            GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED,
            GatePredicateName.DECISIVE_FIELDS_REVIEWED,
            GatePredicateName.REAL_BASELINE_EXECUTED,
            GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES,
            GatePredicateName.NO_BLOCKING_SCHEMA_GAPS,
            GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED,
        )
    )
    result = evaluate_reality_gate(
        preds,
        purpose=GatePurpose.SUBSTANTIVE_TRAINING,
        scientific_validation=ScientificValidationEvidence(
            status=ScientificValidation.IN_PROGRESS, evidence_basis="pilot started"
        ),
    )
    assert result.ai_claims_allowed is False


def test_no_blocking_schema_gaps_true_means_satisfied() -> None:
    assert _p(GatePredicateName.NO_BLOCKING_SCHEMA_GAPS, GateValue.TRUE).blocks() is False
    assert _p(GatePredicateName.NO_BLOCKING_SCHEMA_GAPS, GateValue.FALSE).blocks() is True


def test_legacy_blocking_schema_gaps_alias() -> None:
    assert (
        normalize_predicate_name("blocking_schema_gaps")
        is GatePredicateName.NO_BLOCKING_SCHEMA_GAPS
    )


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
        preds,
        scientific_validation=ScientificValidationEvidence(
            status=ScientificValidation.NOT_STARTED, evidence_basis="default"
        ),
    )
    machine = machine_readable_result(result)
    assert "engineering_readiness" in machine
    assert "data_readiness" in machine
    assert "scientific_validation" in machine
    report = human_blocker_report(result)
    assert "BLOCK" in report.upper() or "UNKNOWN" in report


def test_unknown_blocks_like_false() -> None:
    preds = (
        _p(GatePredicateName.REAL_ANCHOR_AVAILABLE, GateValue.UNKNOWN),
        _p(GatePredicateName.LICENCE_SCOPE_VERIFIED, GateValue.TRUE),
        _p(GatePredicateName.PROTECTED_SPLIT_FROZEN, GateValue.TRUE),
        _p(GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED, GateValue.TRUE),
        _p(GatePredicateName.DECISIVE_FIELDS_REVIEWED, GateValue.TRUE),
        _p(GatePredicateName.REAL_BASELINE_EXECUTED, GateValue.TRUE),
        _p(GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES, GateValue.TRUE),
        _p(GatePredicateName.NO_BLOCKING_SCHEMA_GAPS, GateValue.TRUE),
        _p(GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED, GateValue.TRUE),
    )
    result = evaluate_reality_gate(preds, purpose=GatePurpose.SUBSTANTIVE_TRAINING)
    assert result.data_readiness.status == DataReadiness.BLOCKED.value
    assert result.substantive_training_allowed is False


def test_expected_current_state_constants() -> None:
    assert EXPECTED_CURRENT_STATE["data_readiness"] == "BLOCKED"
    assert EXPECTED_CURRENT_STATE["scientific_validation"] == "NOT_STARTED"
    assert EXPECTED_CURRENT_STATE["substantive_training"] == "HOLD_PENDING_REAL_ANCHOR"
