"""Independent-review regressions for the second PRD v8 Task 6 hardening."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture
import test_prd_v8_quick_design as quick_design_fixture
import test_prd_v8_task5_review_regressions as parser_fixture
import test_prd_v8_task6_contracts as task6_fixture
import test_prd_v8_task6_review_regressions as task6_review_fixture
from fastapi.testclient import TestClient

from ntruth.api.app import create_app
from ntruth.quick_design.v8 import run_quick_design_v8, validate_raw_wizard_submission
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.core import content_checksum
from ntruth.schemas.count_registry import CanonicalCountKind
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.prospective import (
    ConfirmationRelationKind,
    ConfirmationTarget,
    ExecutedInputLedger,
    ProspectiveArtifactKind,
    ProspectiveInputLedger,
    ProspectiveInputScientificReviewRequired,
    SupportBindingScope,
    build_executed_design,
    build_executed_input_ledger,
    build_planned_design,
    build_prospective_artifact,
    build_prospective_input_ledger,
    reconcile_plan_execution,
)
from ntruth.schemas.report_bundle import (
    ConflictPredicateProofBinding,
    ConflictRecord,
    HandoffItemCategory,
    HandoffItemOrigin,
    ReportBundle,
    ReportDesignContext,
    ReportDesignRecordContext,
    build_handoff_item,
    build_report_bundle,
)
from ntruth.schemas.support import (
    ConfirmationEvent,
    EvidenceBasis,
    EvidenceRecord,
    EvidenceTypeV8,
    SensitivityRecord,
    SourceContext,
    SourceRecord,
)


def _required(module: object, name: str) -> Any:
    assert hasattr(module, name), f"missing reviewed Task6 contract: {name}"
    return getattr(module, name)


def _quick_result() -> tuple[object, object]:
    _, submission = quick_design_fixture._submission()
    result = run_quick_design_v8(
        submission,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )
    return submission, result


def _execution_ledger(*, suffix: str = "FIX2") -> ExecutedInputLedger:
    sample_sheet = build_prospective_artifact(
        kind=ProspectiveArtifactKind.SAMPLE_SHEET,
        media_type="text/csv",
        content=f"sample_id,status\nwell-1,executed-{suffix}\n",
    )
    execution_log = build_prospective_artifact(
        kind=ProspectiveArtifactKind.EXECUTION_LOG,
        media_type="text/plain",
        content=f"execution log {suffix}",
    )
    plan = task6_fixture._plan()
    planned_evidence_ids = {record.evidence_id for record in plan.evidence_records}
    return build_executed_input_ledger(
        sources=(*plan.sources, task6_fixture._source(task6_fixture.SourceContext.EXECUTED)),
        evidence_records=(
            *plan.evidence_records,
            *(
                record
                for record in task6_fixture._execution_evidence()
                if record.evidence_id not in planned_evidence_ids
            ),
        ),
        confirmation_events=(),
        artifacts=(sample_sheet, execution_log),
    )


def _submission_with_authority(authority: AuthorityType) -> object:
    module, submission = quick_design_fixture._submission()
    supports = {
        clause_id: descriptor.model_copy(update={"authority_type": authority})
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
    ledger = build_prospective_input_ledger(
        request=request,
        sources=submission.input_ledger.sources,
        evidence_records=submission.input_ledger.evidence_records,
        confirmation_events=(),
        artifacts=submission.input_ledger.artifacts,
        support_bindings=bindings,
    )
    return module.QuickDesignV8Submission.model_validate(
        submission.model_copy(
            update={"pipeline_request": request, "input_ledger": ledger}
        ).model_dump(mode="python")
    )


def _raw_submission_with_grade(grade_token: str) -> object:
    module, submission = quick_design_fixture._submission()
    supports = {
        clause_id: descriptor.model_copy(
            update={
                "authority_type": AuthorityType.USER_CONFIRMATION,
                "evidence_basis": EvidenceBasis.AUTHOR_ASSERTED,
                "support_grade": descriptor.support_grade.model_copy(update={"token": grade_token}),
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
    ledger = build_prospective_input_ledger(
        request=request,
        sources=submission.input_ledger.sources,
        evidence_records=submission.input_ledger.evidence_records,
        confirmation_events=(),
        artifacts=submission.input_ledger.artifacts,
        support_bindings=bindings,
    )
    return module.QuickDesignV8Submission.model_validate(
        submission.model_copy(
            update={"pipeline_request": request, "input_ledger": ledger}
        ).model_dump(mode="python")
    )


def _confirmation_for(
    submission: object,
    binding: object,
    *,
    scope_id: str,
    value: object,
) -> ConfirmationEvent:
    return ConfirmationEvent(
        event_id=f"CONF-FIX2-{binding.scope_id}",
        support=binding.support,
        evidence_refs=binding.evidence_record_ids,
        scope_id=scope_id,
        confirmed_value=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=value,
            evidence_ids=binding.evidence_record_ids,
            query_scope_id=submission.pipeline_request.query.id,
        ),
        actor_role="independent-reviewer",
        review_independent=True,
        created_at=datetime(2026, 8, 8, tzinfo=UTC),
    )


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


def _executed_report(*, conflicting_source_id: bool = False) -> ReportBundle:
    submission, result = _quick_result()
    report = result.report_bundle
    plan = result.planned_design
    planned_source = plan.sources[0]
    executed_source = SourceRecord(
        source_id=(planned_source.source_id if conflicting_source_id else "SOURCE-EXECUTED-FIX2"),
        source_class=planned_source.source_class,
        source_context=SourceContext.EXECUTED,
        source_version="sha256:executed-fix2",
    )
    executed_evidence = EvidenceRecord(
        evidence_id="EV-EXECUTED-FIX2",
        source_id=executed_source.source_id,
        evidence_type=EvidenceTypeV8.INSTRUMENT_OR_EXECUTION_LOG,
        locator="execution://fix2/log",
        original_text="The execution log records completion.",
    )
    sample_sheet = next(
        item
        for item in submission.input_ledger.artifacts
        if item.kind is ProspectiveArtifactKind.SAMPLE_SHEET
    )
    execution_log = build_prospective_artifact(
        kind=ProspectiveArtifactKind.EXECUTION_LOG,
        media_type="text/plain",
        content="execution completed under the pinned event registry",
    )
    if conflicting_source_id:
        ledger_sources = (executed_source,)
        ledger_evidence = (
            *(
                record.model_copy(update={"source_id": executed_source.source_id})
                for record in plan.evidence_records
            ),
            executed_evidence,
        )
    else:
        ledger_sources = (*plan.sources, executed_source)
        ledger_evidence = (*plan.evidence_records, executed_evidence)
    ledger = build_executed_input_ledger(
        sources=ledger_sources,
        evidence_records=ledger_evidence,
        confirmation_events=(),
        artifacts=(sample_sheet, execution_log),
    )
    executed_count = next(
        item
        for item in report.count_registry.records
        if item.kind is not CanonicalCountKind.PLANNED_UNIT_COUNT
    )
    execution = build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=plan.event_registry,
        count_records=(executed_count,),
        deviations=KnowledgeValue(
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=(executed_evidence.evidence_id,),
            query_scope_id=plan.inferential_query_ids[0],
        ),
        final_sample_sheet_ref=sample_sheet.artifact_id,
        execution_log_refs=(execution_log.artifact_id,),
    )
    context = ReportDesignRecordContext(
        mode=ReportDesignContext.EXECUTED,
        planned_design_record=report.design_record_context.planned_design_record,
        executed_design_record=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=execution,
            evidence_ids=tuple(record.evidence_id for record in ledger_evidence),
            query_scope_id=plan.inferential_query_ids[0],
        ),
        reconciliation_record=report.design_record_context.reconciliation_record,
        retrospective_source_ids=report.design_record_context.retrospective_source_ids,
    )
    return _rebuild_report(
        report,
        design_record_context=context,
        source_records=(
            (executed_source,)
            if conflicting_source_id
            else (*report.source_records, executed_source)
        ),
        evidence_records=(
            ledger_evidence
            if conflicting_source_id
            else (*report.evidence_records, executed_evidence)
        ),
    )


@pytest.mark.parametrize(
    "authority",
    (AuthorityType.EXPERT_ADJUDICATION, AuthorityType.SYSTEM_INFERENCE),
)
def test_raw_quick_design_api_cannot_self_issue_privileged_authority(
    authority: AuthorityType,
) -> None:
    submission = _submission_with_authority(authority)

    response = TestClient(create_app(), base_url="http://127.0.0.1").post(
        "/v8/quick-design",
        json=submission.model_dump(mode="json"),
    )

    assert response.status_code == 422
    assert "authority" in response.text.lower()


def test_raw_quick_design_cannot_self_issue_adjudicated_support_grade() -> None:
    submission = _raw_submission_with_grade("ADJUDICATED")

    with pytest.raises(ValueError, match=r"grade|self-report"):
        validate_raw_wizard_submission(submission)


def test_raw_quick_design_cannot_self_issue_expert_evidence_or_handoff_authority() -> None:
    submission = _raw_submission_with_grade("SELF_REPORT_ONLY")

    with pytest.raises(ValueError, match=r"evidence|handoff|authority"):
        validate_raw_wizard_submission(submission)


def test_predicate_confirmation_requires_exact_scope_and_confirmed_value() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = submission.input_ledger
    binding = next(
        item for item in ledger.support_bindings if item.scope_kind is SupportBindingScope.PREDICATE
    )
    confirmation = _confirmation_for(
        submission,
        binding,
        scope_id="unrelated-predicate",
        value="not-the-requested-value",
    )
    bindings = tuple(
        item.model_copy(
            update={
                "confirmation_event_ids": (confirmation.event_id,),
                "confirmation_target": ConfirmationTarget(
                    relation_kind=ConfirmationRelationKind.PREDICATE_VALUE,
                    query_id=submission.pipeline_request.query.id,
                    target_id=binding.scope_id,
                ),
            }
        )
        if item == binding
        else item
        for item in ledger.support_bindings
    )

    with pytest.raises(ValueError, match=r"scope|confirmed value|predicate"):
        build_prospective_input_ledger(
            request=submission.pipeline_request,
            sources=ledger.sources,
            evidence_records=ledger.evidence_records,
            confirmation_events=(confirmation,),
            artifacts=ledger.artifacts,
            support_bindings=bindings,
        )


def test_clause_confirmation_without_reviewed_semantic_relation_fails_closed() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = submission.input_ledger
    binding = next(
        item
        for item in ledger.support_bindings
        if item.scope_kind is SupportBindingScope.THEORY_CLAUSE
    )
    confirmation = _confirmation_for(
        submission,
        binding,
        scope_id=binding.scope_id,
        value=True,
    )
    bindings = tuple(
        item.model_copy(
            update={
                "confirmation_event_ids": (confirmation.event_id,),
                "confirmation_target": ConfirmationTarget(
                    relation_kind=ConfirmationRelationKind.THEORY_CLAUSE_SUPPORT,
                    query_id=submission.pipeline_request.query.id,
                    target_id=binding.scope_id,
                ),
            }
        )
        if item == binding
        else item
        for item in ledger.support_bindings
    )

    with pytest.raises(ProspectiveInputScientificReviewRequired):
        build_prospective_input_ledger(
            request=submission.pipeline_request,
            sources=ledger.sources,
            evidence_records=ledger.evidence_records,
            confirmation_events=(confirmation,),
            artifacts=ledger.artifacts,
            support_bindings=bindings,
        )


def test_confirmation_is_required_only_for_confirmation_based_support() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = submission.input_ledger
    supports = {
        clause_id: descriptor.model_copy(update={"evidence_basis": EvidenceBasis.SELF_REPORT})
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
        for binding in ledger.support_bindings
    )

    with pytest.raises(ProspectiveInputScientificReviewRequired, match="confirmation"):
        build_prospective_input_ledger(
            request=request,
            sources=ledger.sources,
            evidence_records=ledger.evidence_records,
            confirmation_events=(),
            artifacts=ledger.artifacts,
            support_bindings=bindings,
        )

    author_asserted = _raw_submission_with_grade("ASSERTION_ONLY")
    assert author_asserted.input_ledger.confirmation_events == ()


def test_quick_design_api_rejects_recursive_parser_final_fields() -> None:
    _, submission = quick_design_fixture._submission()
    payload = submission.model_dump(mode="json")
    candidate = parser_fixture._candidate_payload()
    candidate["alternatives"] = [
        {
            "alternative_id": "alt-final-smuggle",
            "block_id": "block-a",
            "description": "candidate only",
            "evidence_ids": ["ev-a"],
            "confidence": 0.4,
            "metadata": {"design_verdict": "adequate"},
        }
    ]
    payload["ai_candidates"] = {
        "knowledge_state": "PRESENT",
        "value": [candidate],
        "evidence_ids": [submission.input_ledger.evidence_records[0].evidence_id],
        "query_scope_id": submission.pipeline_request.query.id,
    }

    response = TestClient(create_app(), base_url="http://127.0.0.1").post("/v8/quick-design", json=payload)

    assert response.status_code == 422
    assert "final field" in response.text.lower()


def test_deviation_absence_must_be_explicit_and_full_reconciliation_detects_event_drift() -> None:
    plan = task6_fixture._plan()
    ledger = _execution_ledger(suffix="EVENT-DRIFT")
    sample_sheet = next(
        item for item in ledger.artifacts if item.kind is ProspectiveArtifactKind.SAMPLE_SHEET
    )
    execution_log = next(
        item for item in ledger.artifacts if item.kind is ProspectiveArtifactKind.EXECUTION_LOG
    )
    with pytest.raises((TypeError, ValueError), match=r"KnowledgeValue|explicit"):
        build_executed_design(
            planned_design=plan,
            executed_input_ledger=ledger,
            event_registry=task6_fixture._event_registry(executed=True),
            count_records=(task6_fixture._count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),),
            deviations=(),
            final_sample_sheet_ref=sample_sheet.artifact_id,
            execution_log_refs=(execution_log.artifact_id,),
        )

    explicit_absence = KnowledgeValue(
        knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
        evidence_ids=("EV-EXEC",),
        query_scope_id=plan.inferential_query_ids[0],
    )
    execution = build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(executed=True),
        count_records=(task6_fixture._count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),),
        deviations=explicit_absence,
        final_sample_sheet_ref=sample_sheet.artifact_id,
        execution_log_refs=(execution_log.artifact_id,),
    )
    reconciliation = reconcile_plan_execution(plan, execution)
    assert reconciliation.status.value == "SCIENTIFIC_REVIEW_REQUIRED"
    assert reconciliation.deviations.knowledge_state is KnowledgeState.UNKNOWN


def test_execution_uses_a_content_addressed_evidence_and_artifact_ledger() -> None:
    prospective = __import__(
        "ntruth.schemas.prospective",
        fromlist=["build_executed_input_ledger"],
    )
    build_ledger = _required(prospective, "build_executed_input_ledger")
    plan = task6_fixture._plan()
    sample_sheet = build_prospective_artifact(
        kind=ProspectiveArtifactKind.SAMPLE_SHEET,
        media_type="text/csv",
        content="sample_id,status\nwell-1,executed\n",
    )
    execution_log = build_prospective_artifact(
        kind=ProspectiveArtifactKind.EXECUTION_LOG,
        media_type="text/plain",
        content="EVT-ASSIGN-EXEC completed",
    )
    planned_evidence_ids = {record.evidence_id for record in plan.evidence_records}
    ledger = build_ledger(
        sources=(*plan.sources, task6_fixture._source(task6_fixture.SourceContext.EXECUTED)),
        evidence_records=(
            *plan.evidence_records,
            *(
                record
                for record in task6_fixture._execution_evidence()
                if record.evidence_id not in planned_evidence_ids
            ),
        ),
        confirmation_events=(),
        artifacts=(sample_sheet, execution_log),
    )
    execution = build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(executed=True),
        count_records=(task6_fixture._count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),),
        deviations=KnowledgeValue(
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=("EV-EXEC",),
            query_scope_id=plan.inferential_query_ids[0],
        ),
        final_sample_sheet_ref=sample_sheet.artifact_id,
        execution_log_refs=(execution_log.artifact_id,),
    )

    assert execution.executed_input_ledger_id == ledger.ledger_id
    assert execution.executed_input_ledger_checksum == ledger.content_checksum


def test_executed_report_retains_addressed_union_of_planned_and_executed_ledgers() -> None:
    from ntruth.reporting.v8 import render_report_bundle_html

    report = _executed_report()
    execution = report.design_record_context.executed_design_record.value

    assert execution is not None
    assert execution.executed_input_ledger_id.startswith("EXECUTED-LEDGER-")
    assert "SOURCE-EXECUTED-FIX2" in {item.source_id for item in report.source_records}
    assert "EV-EXECUTED-FIX2" in {item.evidence_id for item in report.evidence_records}
    html = render_report_bundle_html(report)
    assert execution.executed_input_ledger_id in html
    assert execution.executed_input_ledger_checksum in html
    assert execution.final_sample_sheet_ref in html
    assert execution.execution_log_refs[0] in html


def test_executed_report_rejects_shared_source_id_with_different_context() -> None:
    with pytest.raises(ValueError, match=r"shared source ID.*conflicting content"):
        _executed_report(conflicting_source_id=True)


def test_support_axes_are_orthogonal_but_source_class_is_exactly_bound() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = submission.input_ledger
    source = ledger.sources[-1].model_copy(update={"source_class": ledger.sources[0].source_class})
    sources = (*ledger.sources[:-1], source)
    evidence_records = tuple(
        record.model_copy(update={"evidence_type": EvidenceTypeV8.STRUCTURAL_FACT})
        for record in ledger.evidence_records
    )

    with pytest.raises(ValueError, match=r"source class|source_class"):
        build_prospective_input_ledger(
            request=submission.pipeline_request,
            sources=sources,
            evidence_records=evidence_records,
            confirmation_events=(),
            artifacts=ledger.artifacts,
            support_bindings=ledger.support_bindings,
        )


def test_query_sections_include_all_query_scoped_epistemic_axes() -> None:
    _, result = _quick_result()
    section = result.report_bundle.query_sections[0]

    assert section.ai_candidates == result.report_bundle.ai_candidates[0]
    assert section.human_confirmations == result.report_bundle.human_confirmations
    assert section.conflicts == result.report_bundle.conflicts
    assert section.sensitivities == result.report_bundle.sensitivities


def test_conflicts_and_sensitivities_have_exact_bidirectional_query_closure() -> None:
    _, result = _quick_result()
    report = result.report_bundle
    evidence_ids = tuple(record.evidence_id for record in report.evidence_records[:2])
    claim = report.claim_sets[0].claims[0]
    proof_step = claim.proof_trace[0]
    foreign_conflict = ConflictRecord(
        conflict_id="CONFLICT-FOREIGN-QUERY",
        inferential_query_ids=("IQ-NOT-IN-REPORT",),
        affected_claim_ids=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=(report.claim_sets[0].claims[0].claim_id,),
            evidence_ids=evidence_ids,
            claim_scope_id="CONFLICT-FOREIGN-QUERY",
        ),
        evidence_record_ids=evidence_ids,
        predicate_bindings=(
            ConflictPredicateProofBinding(
                inferential_query_id="IQ-NOT-IN-REPORT",
                derived_claim_id=claim.claim_id,
                proof_step_id=proof_step.step_id,
                predicate_id=proof_step.predicate_references[0].predicate_id,
                predicate_value=KnowledgeValue(
                    knowledge_state=KnowledgeState.CONFLICTING,
                    conflicting_values=("alpha", "beta"),
                    evidence_ids=evidence_ids,
                    query_scope_id="IQ-NOT-IN-REPORT",
                ),
            ),
        ),
        retained_values=("alpha", "beta"),
        rationale="The values remain unresolved.",
    )
    conflict_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(foreign_conflict,),
        evidence_ids=evidence_ids,
        query_scope_id=report.claim_sets[0].inferential_query_id,
    )
    with pytest.raises(ValueError, match=r"conflict.*query|outside.*query"):
        _rebuild_report(report, conflicts=conflict_state)

    claim = report.claim_sets[0].claims[0]
    sensitivity = SensitivityRecord(
        sensitivity_id="SENSITIVITY-UNLINKED",
        derived_claim_id=claim.claim_id,
        decisive_predicate_id="predicate-not-in-claim-proof",
        current_support_grade=claim.support_grade,
        current_value="current",
        counterfactual_value="counterfactual",
        current_output={"candidate_state": "current"},
        counterfactual_output={"candidate_state": "counterfactual"},
        interpretation="This deliberately lacks bidirectional claim linkage.",
    )
    sensitivity_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(sensitivity,),
        evidence_ids=(report.evidence_records[0].evidence_id,),
        query_scope_id=claim.inferential_query_id,
    )
    with pytest.raises(ValueError, match=r"sensitivity|predicate|bidirectional"):
        _rebuild_report(report, sensitivities=sensitivity_state)


def test_sensitivity_outputs_are_candidate_only_and_each_query_has_one_primary_question() -> None:
    _, result = _quick_result()
    report = result.report_bundle
    claim = report.claim_sets[0].claims[0]
    with pytest.raises(ValueError, match="final field"):
        SensitivityRecord(
            sensitivity_id="SENSITIVITY-FINAL-SMUGGLE",
            derived_claim_id=claim.claim_id,
            decisive_predicate_id=claim.required_predicates[0],
            current_support_grade=claim.support_grade,
            current_value="current",
            counterfactual_value="counterfactual",
            current_output={"determinability": "DETERMINATE"},
            counterfactual_output={"candidate_state": "counterfactual"},
            interpretation="A final field is forbidden in candidate output.",
        )

    second_primary = report.questions[0].model_copy(
        update={"question_id": "QUESTION-SECOND-PRIMARY"}
    )
    with pytest.raises(ValueError, match=r"exactly one primary|primary question"):
        _rebuild_report(report, questions=(*report.questions, second_primary))


def test_planned_count_cardinality_is_per_full_semantic_scope() -> None:
    plan = task6_fixture._plan()
    first = plan.count_records[0]
    second = first.model_copy(
        update={
            "count_id": "COUNT-TASK6-FIX2-SECOND-SCOPE",
            "scope": first.scope.model_copy(
                update={
                    "group_id": task6_fixture._present("vehicle"),
                    "cohort_id": task6_fixture._present("cohort-task6-secondary"),
                }
            ),
        }
    )

    rebuilt = build_planned_design(
        experiment_block_id=plan.experiment_block_id,
        inferential_queries=plan.inferential_queries,
        sources=plan.sources,
        evidence_records=plan.evidence_records,
        confirmation_events=plan.confirmation_events,
        event_registry=plan.event_registry,
        count_records=(first, second),
        sample_sheet_ref=plan.sample_sheet_ref,
        methods_draft_ref=plan.methods_draft_ref,
        id_convention_ref=plan.id_convention_ref,
        user_confirmation_scopes=plan.user_confirmation_scopes,
    )

    assert len(rebuilt.count_records) == 2
    assert rebuilt.count_records[0].scope != rebuilt.count_records[1].scope


def test_quick_design_accepts_multiple_planned_counts_for_distinct_full_scopes() -> None:
    _, submission = quick_design_fixture._submission()
    first = submission.planned_unit_counts[0]
    second = first.model_copy(
        update={
            "count_id": "COUNT-PLANNED-QD-V8-SECOND-SCOPE",
            "scope": first.scope.model_copy(
                update={
                    "group_id": first.scope.group_id.model_copy(update={"value": "vehicle"}),
                    "cohort_id": first.scope.cohort_id.model_copy(
                        update={"value": "cohort-quick-design-second"}
                    ),
                }
            ),
        }
    )
    request = submission.pipeline_request.model_copy(
        update={
            "count_registry": submission.pipeline_request.count_registry.model_copy(
                update={"records": (*submission.pipeline_request.count_registry.records, second)}
            )
        }
    )
    ledger = build_prospective_input_ledger(
        request=request,
        sources=submission.input_ledger.sources,
        evidence_records=submission.input_ledger.evidence_records,
        confirmation_events=submission.input_ledger.confirmation_events,
        artifacts=submission.input_ledger.artifacts,
        support_bindings=submission.input_ledger.support_bindings,
    )

    rebuilt = type(submission).model_validate(
        submission.model_copy(
            update={
                "pipeline_request": request,
                "input_ledger": ledger,
                "planned_unit_counts": (first, second),
            }
        ).model_dump(mode="python")
    )

    assert len(rebuilt.planned_unit_counts) == 2


def test_verified_handoff_items_are_structured_lineage_not_free_text() -> None:
    with pytest.raises((TypeError, ValueError)):
        build_handoff_item(
            category=HandoffItemCategory.STRUCTURAL_CONSTRAINT,
            origin=HandoffItemOrigin.VERIFIED_RECORD,
            authority=AuthorityType.EXPERT_ADJUDICATION,
            evidence_refs=("EV-HANDOFF-STRUCTURE",),
            text="Fit a hierarchical model with a random intercept.",
        )

    _, result = _quick_result()
    report = result.report_bundle
    structural = next(
        item
        for item in report.statistical_handoff.items
        if item.category is HandoffItemCategory.STRUCTURAL_CONSTRAINT
    )
    unrelated = report.statistical_handoff.model_copy(
        update={
            "items": tuple(
                item.model_copy(update={"evidence_refs": ("EV-HANDOFF-QUESTION",)})
                if item == structural
                else item
                for item in report.statistical_handoff.items
            )
        }
    )
    with pytest.raises(ValueError, match=r"handoff structural evidence|predicate proof"):
        _rebuild_report(report, statistical_handoff=unrelated)


def test_content_addressed_copies_revalidate_and_query_questions_are_exact() -> None:
    submission, result = _quick_result()
    ledger = submission.input_ledger
    tampered_ledger = ledger.model_copy(update={"content_checksum": "0" * 64})
    with pytest.raises(ValueError, match="checksum"):
        ProspectiveInputLedger.model_validate(tampered_ledger)

    payload = result.report_bundle.model_dump(mode="json")
    payload["query_sections"][0]["questions"][0]["question_id"] = "QUESTION-NOT-IN-GLOBAL-REPORT"
    checksum = content_checksum(
        {
            key: value
            for key, value in payload.items()
            if key not in {"report_id", "content_checksum"}
        }
    )
    payload["report_id"] = f"REPORT-{checksum[:20]}"
    payload["content_checksum"] = checksum
    with pytest.raises(ValueError, match=r"query.*question|questions.*projection"):
        ReportBundle.model_validate(payload)


def test_scientific_values_reject_nested_null_empty_and_blank_artifacts() -> None:
    with pytest.raises(ValueError, match=r"blank|ambiguous"):
        build_prospective_artifact(
            kind=ProspectiveArtifactKind.METHODS_DRAFT,
            media_type="text/plain",
            content="   ",
        )
    with pytest.raises(ValueError, match="ambiguous scientific payload"):
        ConflictRecord(
            conflict_id="CONFLICT-AMBIGUOUS",
            inferential_query_ids=("IQ-RUNTIME-001",),
            affected_claim_ids=KnowledgeValue[tuple[str, ...]](
                knowledge_state=KnowledgeState.PRESENT,
                value=("CLAIM-AMBIGUOUS",),
                evidence_ids=("EV-1", "EV-2"),
                claim_scope_id="CONFLICT-AMBIGUOUS",
            ),
            evidence_record_ids=("EV-1", "EV-2"),
            retained_values=({"nested": None}, {"nested": "known"}),
            rationale="A null is not an open-world state.",
        )


def test_html_exposes_ledgers_review_requirement_and_all_execution_pins() -> None:
    from ntruth.reporting.v8 import render_report_bundle_html

    report = task6_review_fixture._multi_query_report()
    html = render_report_bundle_html(report)
    ledger = report.prospective_input_ledgers.value[0]
    manifest = report.execution_manifest

    for expected in (
        ledger.ledger_id,
        ledger.content_checksum,
        manifest.theory_checksum,
        manifest.rulebook_checksum,
        manifest.fixture_set_id,
        manifest.fixture_set_checksum,
        manifest.reference_registry_id,
        manifest.reference_registry_checksum,
        manifest.evaluator_registry_id,
        manifest.evaluator_registry_checksum,
        "SRR-V8-014",
        "Review requirement",
        "Support binding lineage",
    ):
        assert expected in html


def test_v8_surfaces_are_explicit_and_all_epistemic_boundaries_are_exported() -> None:
    schemas = __import__("ntruth.schemas", fromlist=["__all__"])
    routes = {route.path for route in create_app().routes}

    assert "/v1/quick-design" not in routes
    assert "/v8/quick-design" in routes
    assert {
        "PLANNED_EPISTEMIC_BOUNDARY",
        "EXECUTED_EPISTEMIC_BOUNDARY",
        "RECONCILED_EPISTEMIC_BOUNDARY",
        "RETROSPECTIVE_EPISTEMIC_BOUNDARY",
        "epistemic_boundary_for_context",
    } <= set(schemas.__all__)
