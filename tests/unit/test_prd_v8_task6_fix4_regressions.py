"""Regression probes for the fourth PRD v8 Task 6 review round."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture
import test_prd_v8_quick_design as quick_design_fixture
import test_prd_v8_quick_design_cli_api as cli_fixture
import test_prd_v8_task6_contracts as task6_fixture
import test_prd_v8_task6_fix2_regressions as fix2_fixture

from ntruth.derivation_theory.runtime import V8DerivationInput
from ntruth.pipeline_v8 import V8PipelineRequest, run_v8_pipeline
from ntruth.quick_design.v8 import (
    QuickDesignV8Submission,
    run_quick_design_v8,
    validate_raw_wizard_submission,
)
from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CountLifecyclePhase,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.prospective import (
    SupportBindingScope,
    build_executed_design,
    build_prospective_input_ledger,
    reconcile_plan_execution,
)
from ntruth.schemas.report_bundle import (
    ConflictPredicateProofBinding,
    ConflictRecord,
    ReportBundle,
    ReportDesignContext,
    ReportDesignRecordContext,
    build_report_bundle,
)
from ntruth.schemas.support import ConfirmationEvent, EvidenceRecord


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


def _not_applicable(*, query_id: str, rationale: str) -> KnowledgeValue[object]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale=rationale,
        query_scope_id=query_id,
    )


def test_unverified_retrospective_confirmation_without_typed_binding_fails_closed() -> None:
    submission, result = fix2_fixture._quick_result()
    report = result.report_bundle
    query_id = report.claim_sets[0].inferential_query_id
    evidence_id = "EV-RUNTIME-001"
    confirmation = ConfirmationEvent(
        event_id="CONF-TASK6-FIX4-RETROSPECTIVE-UNBOUND",
        support=submission.input_ledger.support_bindings[0].support,
        evidence_refs=(evidence_id,),
        scope_id="PREDICATE-NOT-IN-REQUEST",
        confirmed_value=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=True,
            evidence_ids=(evidence_id,),
            query_scope_id=query_id,
        ),
        actor_role="retrospective-reviewer",
        review_independent=True,
        created_at=datetime(2026, 8, 8, tzinfo=UTC),
    )
    design_context = ReportDesignRecordContext(
        mode=ReportDesignContext.UNVERIFIED_RETROSPECTIVE,
        planned_design_record=_not_applicable(
            query_id=query_id,
            rationale="No content-addressed prospective plan is available.",
        ),
        executed_design_record=_not_applicable(
            query_id=query_id,
            rationale="No content-addressed executed design is available.",
        ),
        reconciliation_record=_not_applicable(
            query_id=query_id,
            rationale="Retrospective reconstruction cannot imply reconciliation.",
        ),
        retrospective_source_ids=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=(report.source_records[-1].source_id,),
            evidence_ids=(evidence_id,),
            query_scope_id=query_id,
        ),
    )
    ledger_state = KnowledgeValue(
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale="No prospective input ledger exists for this reconstruction.",
        query_scope_id=query_id,
    )
    confirmation_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(confirmation,),
        evidence_ids=(evidence_id,),
        query_scope_id=query_id,
    )

    with pytest.raises(
        ValueError,
        match=r"SCIENTIFIC_REVIEW_REQUIRED|retrospective.*confirmation|typed.*binding",
    ):
        _rebuild_report(
            report,
            design_record_context=design_context,
            prospective_input_ledgers=ledger_state,
            human_confirmations=confirmation_state,
        )


_EXECUTED_LIFECYCLE_PHASE = {
    CanonicalCountKind.ALLOCATED_UNIT_COUNT: CountLifecyclePhase.ALLOCATED,
    CanonicalCountKind.TREATED_UNIT_COUNT: CountLifecyclePhase.TREATED,
    CanonicalCountKind.OBSERVED_UNIT_COUNT: CountLifecyclePhase.OBSERVED,
    CanonicalCountKind.EXCLUDED_UNIT_COUNT: CountLifecyclePhase.EXCLUDED,
    CanonicalCountKind.ANALYZED_UNIT_COUNT: CountLifecyclePhase.ANALYZED,
}


def _executed_count(kind: CanonicalCountKind) -> CanonicalCountRecord:
    base = task6_fixture._count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4)
    lifecycle_phase = _EXECUTED_LIFECYCLE_PHASE.get(kind)
    scope = base.scope
    if lifecycle_phase is not None:
        scope = scope.model_copy(
            update={"lifecycle_phase": task6_fixture._present(lifecycle_phase)}
        )
    return CanonicalCountRecord.model_validate(
        base.model_copy(
            update={
                "count_id": f"COUNT-TASK6-FIX4-{kind.value}",
                "kind": kind,
                "scope": scope,
            }
        ).model_dump(mode="python")
    )


@pytest.mark.parametrize(
    "executed_kind",
    tuple(
        kind
        for kind in CanonicalCountKind
        if kind
        not in {
            CanonicalCountKind.PLANNED_UNIT_COUNT,
            CanonicalCountKind.OBSERVED_UNIT_COUNT,
        }
    ),
)
def test_reconciliation_kind_matrix_fails_closed_for_non_observed_counterparts(
    executed_kind: CanonicalCountKind,
) -> None:
    plan = task6_fixture._plan()
    ledger = task6_fixture._execution_ledger(f"fix4-{executed_kind.value}")
    execution = build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(),
        count_records=(_executed_count(executed_kind),),
        deviations=task6_fixture._deviation_absent(),
        final_sample_sheet_ref=task6_fixture._sample_sheet().artifact_id,
        execution_log_refs=(ledger.artifacts[1].artifact_id,),
    )

    reconciliation = reconcile_plan_execution(plan, execution)

    assert reconciliation.status.value == "SCIENTIFIC_REVIEW_REQUIRED"
    assert reconciliation.deviations.knowledge_state is KnowledgeState.UNKNOWN
    assert reconciliation.review_requirement is not None
    assert reconciliation.review_requirement.issue_id == "SRR-V8-011"
    assert executed_kind.value in reconciliation.review_requirement.rationale


def test_reconciliation_accepts_only_reviewed_observed_counterpart() -> None:
    plan = task6_fixture._plan()
    ledger = task6_fixture._execution_ledger("fix4-observed-positive")
    execution = build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(),
        count_records=(_executed_count(CanonicalCountKind.OBSERVED_UNIT_COUNT),),
        deviations=task6_fixture._deviation_absent(),
        final_sample_sheet_ref=task6_fixture._sample_sheet().artifact_id,
        execution_log_refs=(ledger.artifacts[1].artifact_id,),
    )

    reconciliation = reconcile_plan_execution(plan, execution)

    assert reconciliation.status.value == "NO_RECORDED_DEVIATION"
    assert reconciliation.deviations.knowledge_state is KnowledgeState.ABSENT_EXPLICIT
    assert reconciliation.review_requirement is None


def test_reconciliation_scope_identity_ignores_provenance_but_not_semantics() -> None:
    plan = task6_fixture._plan()
    ledger = task6_fixture._execution_ledger("fix4-provenance")
    observed = _executed_count(CanonicalCountKind.OBSERVED_UNIT_COUNT)
    executed_scope = observed.scope.model_copy(
        update={
            "unit_type": observed.scope.unit_type.model_copy(
                update={
                    "evidence_ids": ("EV-EXEC",),
                    "source_scope_ids": ("SOURCE-executed",),
                }
            )
        }
    )
    execution = build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(),
        count_records=(observed.model_copy(update={"scope": executed_scope}),),
        deviations=task6_fixture._deviation_absent(),
        final_sample_sheet_ref=task6_fixture._sample_sheet().artifact_id,
        execution_log_refs=(ledger.artifacts[1].artifact_id,),
    )

    reconciliation = reconcile_plan_execution(plan, execution)

    assert reconciliation.status.value == "NO_RECORDED_DEVIATION"
    assert reconciliation.deviations.knowledge_state is KnowledgeState.ABSENT_EXPLICIT


def _material_conflict_with_explicit_absence(report: ReportBundle) -> ConflictRecord:
    query_id = report.claim_sets[0].inferential_query_id
    evidence_ids = ("EV-QD-PLAN-001", "EV-RUNTIME-001")
    return ConflictRecord(
        conflict_id="CONFLICT-TASK6-FIX4-MATERIALITY-DOWNGRADE",
        inferential_query_ids=(query_id,),
        affected_claim_ids=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=evidence_ids,
            claim_scope_id="CONFLICT-TASK6-FIX4-MATERIALITY-DOWNGRADE",
        ),
        evidence_record_ids=evidence_ids,
        retained_values=("assignment-before-split", "assignment-after-split"),
        rationale="Caller-declared absence cannot establish conflict materiality.",
    )


def test_claim_proof_conflict_cannot_self_declare_no_affected_claims() -> None:
    _, result = fix2_fixture._quick_result()
    report = result.report_bundle
    conflict = _material_conflict_with_explicit_absence(report)
    conflict_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(conflict,),
        evidence_ids=conflict.evidence_record_ids,
        query_scope_id=report.claim_sets[0].inferential_query_id,
    )

    with pytest.raises(
        ValueError,
        match=r"SCIENTIFIC_REVIEW_REQUIRED|materiality|affected.*claim",
    ):
        _rebuild_report(report, conflicts=conflict_state)


def test_raw_wizard_cannot_self_issue_explicitly_absent_conflict_materiality() -> None:
    payload = cli_fixture._submission_payload(raw_wizard=True)
    submission = QuickDesignV8Submission.model_validate(payload)
    conflict = _material_conflict_with_explicit_absence(
        run_quick_design_v8(
            submission,
            conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
        ).report_bundle
    )
    conflict_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(conflict,),
        evidence_ids=conflict.evidence_record_ids,
        query_scope_id=submission.pipeline_request.query.id,
    )
    raw_with_downgrade = QuickDesignV8Submission.model_validate(
        submission.model_copy(update={"conflicts": conflict_state}).model_dump(mode="python")
    )

    with pytest.raises(ValueError, match=r"materiality|affected.*claim|raw.*conflict"):
        validate_raw_wizard_submission(raw_with_downgrade)


def _submission_with_conflicting_predicate() -> tuple[
    QuickDesignV8Submission,
    tuple[str, ...],
]:
    _, submission = quick_design_fixture._submission()
    query_id = submission.pipeline_request.query.id
    second_evidence = EvidenceRecord(
        evidence_id="EV-RUNTIME-002",
        source_id="SOURCE-QD-METADATA-001",
        evidence_type=submission.input_ledger.evidence_records[-1].evidence_type,
        locator="fixture://runtime/predicate-conflict",
        original_text="Assignment separability is explicitly contradicted.",
    )
    predicate_id = "assignment_separability_support"
    predicates = dict(submission.pipeline_request.predicate_values)
    predicates[predicate_id] = KnowledgeValue(
        knowledge_state=KnowledgeState.CONFLICTING,
        conflicting_values=(True, False),
        evidence_ids=("EV-RUNTIME-001", second_evidence.evidence_id),
        query_scope_id=query_id,
    )
    request = V8PipelineRequest.model_validate(
        submission.pipeline_request.model_copy(update={"predicate_values": predicates}).model_dump(
            mode="python"
        )
    )
    bindings = tuple(
        binding.model_copy(
            update={
                "evidence_record_ids": (
                    *binding.evidence_record_ids,
                    second_evidence.evidence_id,
                )
            }
        )
        if binding.scope_kind is SupportBindingScope.PREDICATE and binding.scope_id == predicate_id
        else binding
        for binding in submission.input_ledger.support_bindings
    )
    ledger = build_prospective_input_ledger(
        request=V8DerivationInput.model_validate(request.model_dump(mode="python")),
        sources=submission.input_ledger.sources,
        evidence_records=(*submission.input_ledger.evidence_records, second_evidence),
        confirmation_events=(),
        artifacts=submission.input_ledger.artifacts,
        support_bindings=bindings,
    )
    pipeline_result = run_v8_pipeline(
        request,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )
    affected_claim_ids = tuple(
        claim.claim_id
        for claim in pipeline_result.claim_set.claims
        if claim.determinability_state is DeterminabilityState.CONFLICTING_INFORMATION
    )
    assert affected_claim_ids
    exact_proof_evidence = ("EV-RUNTIME-001", "EV-RUNTIME-002")
    for claim in pipeline_result.claim_set.claims:
        if claim.claim_id not in affected_claim_ids:
            continue
        assert {
            evidence_id
            for step in claim.proof_trace
            for reference in step.predicate_references
            for evidence_id in reference.predicate_value.evidence_ids
        } == set(exact_proof_evidence)
    predicate_bindings = tuple(
        ConflictPredicateProofBinding(
            inferential_query_id=claim.inferential_query_id,
            derived_claim_id=claim.claim_id,
            proof_step_id=step.step_id,
            predicate_id=reference.predicate_id,
            predicate_value=reference.predicate_value,
        )
        for claim in pipeline_result.claim_set.claims
        if claim.claim_id in affected_claim_ids
        for step in claim.proof_trace
        for reference in step.predicate_references
        if reference.predicate_value.knowledge_state is KnowledgeState.CONFLICTING
    )
    assert {binding.derived_claim_id for binding in predicate_bindings} == set(affected_claim_ids)
    conflict = ConflictRecord(
        conflict_id="CONFLICT-TASK6-FIX4-EXACT-PROOF",
        inferential_query_ids=(query_id,),
        affected_claim_ids=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=affected_claim_ids,
            evidence_ids=exact_proof_evidence,
            claim_scope_id="CONFLICT-TASK6-FIX4-EXACT-PROOF",
        ),
        evidence_record_ids=exact_proof_evidence,
        predicate_bindings=predicate_bindings,
        retained_values=(True, False),
        rationale="The predicate proof retains both contradictory supported values.",
    )
    conflict_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(conflict,),
        evidence_ids=exact_proof_evidence,
        query_scope_id=query_id,
    )
    rebuilt = QuickDesignV8Submission.model_validate(
        submission.model_copy(
            update={
                "pipeline_request": request,
                "input_ledger": ledger,
                "conflicts": conflict_state,
            }
        ).model_dump(mode="python")
    )
    return rebuilt, exact_proof_evidence


def test_conflict_exactly_closes_over_affected_claim_predicate_proof_evidence() -> None:
    submission, exact_proof_evidence = _submission_with_conflicting_predicate()

    result = run_quick_design_v8(
        submission,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )

    assert result.report_bundle.conflicts.value is not None
    assert result.report_bundle.conflicts.value[0].evidence_record_ids == exact_proof_evidence


def test_conflict_rejects_evidence_extraneous_to_affected_claim_predicate_proofs() -> None:
    submission, exact_proof_evidence = _submission_with_conflicting_predicate()
    conflict = submission.conflicts.value[0]
    extraneous_evidence = (*exact_proof_evidence, "EV-HANDOFF-QUESTION")
    forged = conflict.model_copy(
        update={
            "evidence_record_ids": extraneous_evidence,
            "affected_claim_ids": conflict.affected_claim_ids.model_copy(
                update={"evidence_ids": extraneous_evidence}
            ),
        }
    )
    forged_state = submission.conflicts.model_copy(
        update={"value": (forged,), "evidence_ids": extraneous_evidence}
    )
    forged_submission = QuickDesignV8Submission.model_validate(
        submission.model_copy(update={"conflicts": forged_state}).model_dump(mode="python")
    )

    with pytest.raises(ValueError, match=r"conflict.*evidence|predicate proof|exact"):
        run_quick_design_v8(
            forged_submission,
            conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
        )
