"""Regression probes for the fifth PRD v8 Task 6 review round."""

from __future__ import annotations

from typing import Any

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture
import test_prd_v8_task6_contracts as task6_fixture
import test_prd_v8_task6_fix2_regressions as fix2_fixture
import test_prd_v8_task6_fix4_regressions as fix4_fixture
from fastapi.testclient import TestClient

import ntruth.schemas.report_bundle as report_schema
from ntruth.api.app import create_app
from ntruth.quick_design.v8 import (
    QuickDesignV8Submission,
    run_quick_design_v8,
    validate_raw_wizard_submission,
)
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.count_registry import CanonicalCountKind, CountLifecyclePhase
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.prospective import (
    SupportBindingScope,
    build_executed_design,
    build_prospective_input_ledger,
    reconcile_plan_execution,
)
from ntruth.schemas.report_bundle import ConflictRecord, ReportBundle, build_report_bundle
from ntruth.schemas.support import EvidenceBasis, EvidenceTypeV8


def _lifecycle_value(
    state: KnowledgeState,
    *,
    query_id: str,
) -> KnowledgeValue[CountLifecyclePhase]:
    common: dict[str, Any] = {"knowledge_state": state, "query_scope_id": query_id}
    if state is KnowledgeState.PRESENT:
        common.update(
            value=CountLifecyclePhase.OBSERVED,
            evidence_ids=("EV-EXEC",),
            source_scope_ids=("SOURCE-executed",),
        )
    elif state is KnowledgeState.ABSENT_EXPLICIT:
        common["evidence_ids"] = ("EV-EXEC",)
    elif state is KnowledgeState.NOT_REPORTED:
        common["source_scope_ids"] = ("SOURCE-executed",)
    elif state is KnowledgeState.UNKNOWN:
        common["rationale"] = "The observed lifecycle phase is not established."
    elif state is KnowledgeState.NOT_APPLICABLE:
        common["rationale"] = "No reviewed basis makes lifecycle inapplicable here."
    elif state is KnowledgeState.CONFLICTING:
        common.update(
            conflicting_values=(CountLifecyclePhase.OBSERVED, CountLifecyclePhase.ANALYZED),
            evidence_ids=("EV-EXEC", "EV-EXEC-Q2"),
        )
    return KnowledgeValue[CountLifecyclePhase](**common)


@pytest.mark.parametrize("state", tuple(KnowledgeState))
def test_observed_count_reconciles_only_with_present_observed_lifecycle(
    state: KnowledgeState,
) -> None:
    """Catches filtering lifecycle state before the reviewed kind/phase check."""

    plan = task6_fixture._plan()
    ledger = task6_fixture._execution_ledger(f"fix5-lifecycle-{state.value.lower()}")
    observed = fix4_fixture._executed_count(CanonicalCountKind.OBSERVED_UNIT_COUNT)
    scope = observed.scope.model_copy(
        update={
            "lifecycle_phase": _lifecycle_value(
                state,
                query_id=observed.scope.query_id,
            )
        }
    )
    execution = build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(),
        count_records=(observed.model_copy(update={"scope": scope}),),
        deviations=task6_fixture._deviation_absent(),
        final_sample_sheet_ref=task6_fixture._sample_sheet().artifact_id,
        execution_log_refs=(ledger.artifacts[1].artifact_id,),
    )

    reconciliation = reconcile_plan_execution(plan, execution)

    if state is KnowledgeState.PRESENT:
        assert reconciliation.status.value == "NO_RECORDED_DEVIATION"
        assert reconciliation.review_requirement is None
    else:
        assert reconciliation.status.value == "SCIENTIFIC_REVIEW_REQUIRED"
        assert reconciliation.deviations.knowledge_state is KnowledgeState.UNKNOWN
        assert reconciliation.review_requirement is not None
        assert reconciliation.review_requirement.issue_id == "SRR-V8-011"


def _rebuild_report(bundle: ReportBundle, **updates: object) -> ReportBundle:
    fields: dict[str, object] = {
        "verified_pipeline_contexts": bundle.verified_pipeline_contexts,
        "design_record_context": bundle.design_record_context,
        "prospective_input_ledgers": bundle.prospective_input_ledgers,
        "source_records": bundle.source_records,
        "evidence_records": bundle.evidence_records,
        "ai_candidates": bundle.ai_candidates,
        "human_confirmations": bundle.human_confirmations,
        "conflicts": bundle.conflicts,
        "sensitivities": bundle.sensitivities,
        "questions": bundle.questions,
        "statistical_handoff": bundle.statistical_handoff,
        "inference_limits": bundle.inference_limits,
    }
    fields.update(updates)
    return build_report_bundle(**fields)  # type: ignore[arg-type]


def _nonproof_evidence(report: ReportBundle) -> tuple[str, str]:
    proof_evidence = {
        evidence_id
        for claim_set in report.claim_sets
        for claim in claim_set.claims
        for step in claim.proof_trace
        for reference in step.predicate_references
        for evidence_id in reference.predicate_value.evidence_ids
    }
    candidates = tuple(
        record.evidence_id
        for record in report.evidence_records
        if record.evidence_id not in proof_evidence
    )
    assert len(candidates) >= 2
    return candidates[0], candidates[1]


@pytest.mark.parametrize(
    "affected_state",
    (KnowledgeState.ABSENT_EXPLICIT, KnowledgeState.UNKNOWN),
)
def test_conflict_materiality_without_reviewed_artifact_always_fails_closed(
    affected_state: KnowledgeState,
) -> None:
    """Catches treating evidence non-overlap as a reviewed materiality decision."""

    _, result = fix2_fixture._quick_result()
    report = result.report_bundle
    query_id = report.claim_sets[0].inferential_query_id
    evidence_ids = _nonproof_evidence(report)
    affected_kwargs: dict[str, object] = {
        "knowledge_state": affected_state,
        "claim_scope_id": "CONFLICT-TASK6-FIX5-NO-MATERIALITY-ARTIFACT",
    }
    if affected_state is KnowledgeState.ABSENT_EXPLICIT:
        affected_kwargs["evidence_ids"] = evidence_ids
    else:
        affected_kwargs["rationale"] = "No reviewed materiality artifact exists."
    conflict = ConflictRecord(
        conflict_id="CONFLICT-TASK6-FIX5-NO-MATERIALITY-ARTIFACT",
        inferential_query_ids=(query_id,),
        affected_claim_ids=KnowledgeValue[tuple[str, ...]](**affected_kwargs),
        evidence_record_ids=evidence_ids,
        retained_values=("metadata-label-a", "metadata-label-b"),
        rationale="A caller statement is not a reviewed materiality artifact.",
    )
    state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(conflict,),
        evidence_ids=evidence_ids,
        query_scope_id=query_id,
    )

    with pytest.raises(report_schema.ConflictScientificReviewRequired) as caught:
        _rebuild_report(report, conflicts=state)

    assert caught.value.review_requirement.issue_id == "SRR-V8-010"


def _forged_conflicting_submission() -> QuickDesignV8Submission:
    submission, _ = fix4_fixture._submission_with_conflicting_predicate()
    conflict = submission.conflicts.value[0]
    forged_values = ("not-the-true-value-one", "not-the-true-value-two")
    updates: dict[str, object] = {"retained_values": forged_values}
    if hasattr(conflict, "predicate_bindings"):
        updates["predicate_bindings"] = tuple(
            binding.model_copy(
                update={
                    "predicate_value": binding.predicate_value.model_copy(
                        update={"conflicting_values": forged_values}
                    )
                }
            )
            for binding in conflict.predicate_bindings
        )
    forged = conflict.model_copy(update=updates)
    forged_state = submission.conflicts.model_copy(update={"value": (forged,)})
    return QuickDesignV8Submission.model_validate(
        submission.model_copy(update={"conflicts": forged_state}).model_dump(mode="python")
    )


def _as_raw_wizard(submission: QuickDesignV8Submission) -> QuickDesignV8Submission:
    supports = {
        clause_id: descriptor.model_copy(
            update={
                "authority_type": AuthorityType.USER_CONFIRMATION,
                "evidence_basis": EvidenceBasis.AUTHOR_ASSERTED,
                "support_grade": descriptor.support_grade.model_copy(
                    update={"token": "ASSERTION_ONLY"}
                ),
            }
        )
        for clause_id, descriptor in submission.pipeline_request.support_by_clause.items()
    }
    request = submission.pipeline_request.model_copy(update={"support_by_clause": supports})
    default_support = next(iter(supports.values()))
    bindings = tuple(
        binding.model_copy(
            update={
                "support": (
                    supports[binding.scope_id]
                    if binding.scope_kind is SupportBindingScope.THEORY_CLAUSE
                    else default_support
                )
            }
        )
        for binding in submission.input_ledger.support_bindings
    )
    evidence_records = tuple(
        record.model_copy(update={"evidence_type": EvidenceTypeV8.AUTHOR_ASSERTION})
        for record in submission.input_ledger.evidence_records
    )
    ledger = build_prospective_input_ledger(
        request=request,
        sources=submission.input_ledger.sources,
        evidence_records=evidence_records,
        confirmation_events=(),
        artifacts=submission.input_ledger.artifacts,
        support_bindings=bindings,
    )
    handoff = submission.statistical_handoff.model_copy(
        update={
            "items": tuple(
                item.model_copy(update={"authority": AuthorityType.USER_CONFIRMATION})
                for item in submission.statistical_handoff.items
            )
        }
    )
    return QuickDesignV8Submission.model_validate(
        submission.model_copy(
            update={
                "pipeline_request": request,
                "input_ledger": ledger,
                "statistical_handoff": handoff,
            }
        ).model_dump(mode="python")
    )


def test_raw_guard_rejects_conflict_values_forged_behind_consistent_local_binding() -> None:
    """Catches trusting a caller-authored binding rather than the request predicate."""

    forged = _as_raw_wizard(_forged_conflicting_submission())

    with pytest.raises(ValueError, match=r"predicate.*value|proof.*value|retained.*value"):
        validate_raw_wizard_submission(forged)


def test_report_rejects_conflict_values_forged_behind_consistent_local_binding() -> None:
    """Catches trusting flat retained values instead of exact claim proof lineage."""

    forged = _forged_conflicting_submission()

    with pytest.raises(ValueError, match=r"predicate.*proof|predicate.*value|retained.*value"):
        run_quick_design_v8(
            forged,
            conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
        )


def test_api_rejects_conflict_values_forged_behind_consistent_local_binding() -> None:
    """Catches the canonical HTTP boundary returning a forged interpretation."""

    forged = _as_raw_wizard(_forged_conflicting_submission())

    response = TestClient(create_app()).post(
        "/v8/quick-design",
        json=forged.model_dump(mode="json"),
    )

    assert response.status_code == 422
    assert any(
        token in response.text.lower()
        for token in ("predicate value", "proof value", "retained value")
    )


def test_positive_conflict_retains_exact_typed_predicate_proof_binding() -> None:
    """Catches dropping the target-specific predicate/value/claim proof binding."""

    submission, _ = fix4_fixture._submission_with_conflicting_predicate()

    result = run_quick_design_v8(
        submission,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )

    conflict = result.report_bundle.conflicts.value[0]
    assert conflict.predicate_bindings
    binding = conflict.predicate_bindings[0]
    claim = next(
        claim
        for claim in result.pipeline_result.claim_set.claims
        if claim.claim_id == binding.derived_claim_id
    )
    proof_reference = next(
        reference
        for step in claim.proof_trace
        if step.step_id == binding.proof_step_id
        for reference in step.predicate_references
        if reference.predicate_id == binding.predicate_id
    )
    assert binding.inferential_query_id == claim.inferential_query_id
    assert binding.predicate_value == proof_reference.predicate_value
    assert tuple(conflict.retained_values) == tuple(binding.predicate_value.conflicting_values)
