"""Fail-closed projection from the canonical Reality Gate to training readiness."""

from __future__ import annotations

import pytest

from ntruth.reality_gate import (
    GatePredicateName,
    GatePurpose,
    GateValue,
    PredicateEvidence,
    RealityGatePredicate,
    ScientificValidation,
    ScientificValidationEvidence,
    evaluate_reality_gate,
)
from ntruth.training.readiness import (
    OverallReadiness,
    ReadinessStatus,
    project_small_model_training_readiness,
)


def _predicate(name: GatePredicateName) -> RealityGatePredicate:
    return RealityGatePredicate(
        name=name,
        value=GateValue.TRUE,
        evidence=PredicateEvidence(basis="independent unit-test evidence"),
    )


def _open_root_gate():
    predicates = tuple(
        _predicate(name)
        for name in (
            GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES,
            GatePredicateName.NO_BLOCKING_SCHEMA_GAPS,
            GatePredicateName.REAL_ANCHOR_AVAILABLE,
            GatePredicateName.LICENCE_SCOPE_VERIFIED,
            GatePredicateName.PROTECTED_SPLIT_FROZEN,
            GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED,
            GatePredicateName.DECISIVE_FIELDS_REVIEWED,
            GatePredicateName.REAL_BASELINE_EXECUTED,
            GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED,
        )
    )
    return evaluate_reality_gate(
        predicates,
        purpose=GatePurpose.SUBSTANTIVE_TRAINING,
        scientific_validation=ScientificValidationEvidence(
            status=ScientificValidation.VALIDATED,
            evidence_basis="independent scientific challenge completed",
            independent_challenge_ref="challenge://unit-test/frozen",
        ),
    )


def test_root_hold_cannot_be_promoted_by_training_projection() -> None:
    root_gate = evaluate_reality_gate((), purpose=GatePurpose.SUBSTANTIVE_TRAINING)

    projection = project_small_model_training_readiness(root_gate)

    assert projection.substantive_training_allowed is False
    assert projection.overall is OverallReadiness.NOT_READY
    assert projection.scientific.status is ReadinessStatus.FAIL
    assert projection.dataset.status is ReadinessStatus.FAIL
    assert projection.apple_silicon_feasibility.status is ReadinessStatus.PASS
    assert projection.normative_target == "PRD_V9"
    assert projection.implemented_root_contract == "PRD_V7"
    assert projection.v9_schema_conformance == "BLOCKED_PENDING_CANONICAL_REGISTRY"
    assert projection.root_reality_gate.checksum
    assert any(
        blocker.code == "ROOT_SUBSTANTIVE_TRAINING_BLOCKED"
        for blocker in projection.overall_blockers
    )


def test_open_root_gate_remains_conditional_until_v9_and_model_selection_close() -> None:
    projection = project_small_model_training_readiness(_open_root_gate())

    assert projection.substantive_training_allowed is True
    assert projection.scientific.status is ReadinessStatus.PASS
    assert projection.dataset.status is ReadinessStatus.PASS
    assert projection.evaluation.status is ReadinessStatus.PASS
    assert projection.reproducibility.status is ReadinessStatus.PASS
    assert projection.schema_readiness.status is ReadinessStatus.PARTIAL
    assert projection.infrastructure.status is ReadinessStatus.PARTIAL
    assert projection.model_selection_status is ReadinessStatus.PARTIAL
    assert projection.overall is OverallReadiness.READY_WITH_CONDITIONS


def test_machine_output_keeps_structured_evidence_blockers_and_model_roles() -> None:
    projection = project_small_model_training_readiness(
        evaluate_reality_gate((), purpose=GatePurpose.SUBSTANTIVE_TRAINING)
    )

    payload = projection.as_machine_readable()

    assert payload["schema"]["status"] == "FAIL"
    assert "schema_readiness" not in payload
    assert payload["scientific"]["evidence"][0]["code"] == "ROOT_SCIENTIFIC_VALIDATION"
    assert payload["dataset"]["blockers"]
    infrastructure_blocker_codes = {
        blocker["code"] for blocker in payload["infrastructure"]["blockers"]
    }
    overall_blocker_codes = {blocker["code"] for blocker in payload["overall_blockers"]}
    assert "anonymous_unlinked_inherited_fd_runner" in infrastructure_blocker_codes
    assert "anonymous_unlinked_inherited_fd_runner" in overall_blocker_codes
    roles = {candidate["model_id"]: candidate["role"] for candidate in payload["models"]}
    assert roles == {
        "ibm-granite/granite-4.1-3b": "PROVISIONAL_PRIMARY",
        "Qwen/Qwen3-4B-Instruct-2507": "CHALLENGER",
        "microsoft/Phi-4-mini-instruct": "CHALLENGER",
        "answerdotai/ModernBERT-base": "SPECIALIST_BASELINE",
    }


def test_machine_serialization_revalidates_fail_closed_invariants() -> None:
    projection = project_small_model_training_readiness(
        evaluate_reality_gate((), purpose=GatePurpose.SUBSTANTIVE_TRAINING)
    )
    invalid_copy = projection.model_copy(update={"overall": OverallReadiness.READY})

    with pytest.raises(ValueError, match="root Reality Gate blocks substantive training"):
        invalid_copy.as_machine_readable()
