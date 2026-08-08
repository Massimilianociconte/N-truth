"""Regressions for the third PRD v8 Task 6 scientific-boundary review."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import test_prd_v8_quick_design as quick_design_fixture
import test_prd_v8_task5_review_regressions as parser_fixture
import test_prd_v8_task6_contracts as task6_fixture
import test_prd_v8_task6_fix2_regressions as fix2_fixture
import test_prd_v8_task6_review_regressions as review_fixture
from typer.testing import CliRunner

from ntruth.cli.main import app
from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.count_registry import CanonicalCountKind
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.prospective import (
    SupportBindingScope,
    build_executed_design,
    build_executed_input_ledger,
    build_prospective_input_ledger,
    reconcile_plan_execution,
)
from ntruth.schemas.report_bundle import (
    ConflictPredicateProofBinding,
    ConflictRecord,
    ConflictScientificReviewRequired,
    ReportBundle,
    build_report_bundle,
)
from ntruth.schemas.support import (
    ConfirmationEvent,
    EvidenceRecord,
    EvidenceTypeV8,
    SourceContext,
    SourceRecord,
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


def _empty_candidate(*, suffix: str) -> ParserCandidateOutput:
    payload = parser_fixture._candidate_payload()
    for field in (
        "experiment_blocks",
        "block_boundaries",
        "evidence_spans",
        "candidate_nodes",
        "candidate_edges",
        "factors",
        "endpoints",
        "contrasts",
        "candidate_estimands",
        "candidate_counts",
        "candidate_events",
        "candidate_graphs",
        "alternatives",
        "clarification_questions",
        "missing_predicates",
    ):
        payload[field] = []
    payload["model_metadata"]["model_name"] = f"candidate-only-{suffix}"
    return ParserCandidateOutput.model_validate(payload)


def _candidate_state(
    *, query_id: str, evidence_id: str, candidate: ParserCandidateOutput
) -> KnowledgeValue[tuple[ParserCandidateOutput, ...]]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(candidate,),
        evidence_ids=(evidence_id,),
        query_scope_id=query_id,
    )


def test_raw_cli_rejects_self_issued_privileged_authority_before_writing(
    tmp_path: Path,
) -> None:
    submission = fix2_fixture._submission_with_authority(AuthorityType.EXPERT_ADJUDICATION)
    submission_path = tmp_path / "privileged.json"
    submission_path.write_text(
        json.dumps(submission.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "out"

    result = CliRunner().invoke(
        app,
        ["quick-design", "run", str(submission_path), "--out", str(output)],
    )

    assert result.exit_code == 2
    assert "authority" in result.output.lower()
    assert not output.exists()


def test_support_binding_rejects_descriptor_source_class_mismatch() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = submission.input_ledger
    metadata_source = ledger.sources[-1]
    mismatched = metadata_source.model_copy(update={"source_class": ledger.sources[0].source_class})

    with pytest.raises(ValueError, match=r"source class|source_class"):
        build_prospective_input_ledger(
            request=submission.pipeline_request,
            sources=(*ledger.sources[:-1], mismatched),
            evidence_records=ledger.evidence_records,
            confirmation_events=ledger.confirmation_events,
            artifacts=ledger.artifacts,
            support_bindings=ledger.support_bindings,
        )


def test_support_binding_rejects_extra_source_not_induced_by_bound_evidence() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = submission.input_ledger
    binding = ledger.support_bindings[0]
    bindings = (
        binding.model_copy(
            update={"source_ids": (*binding.source_ids, ledger.sources[0].source_id)}
        ),
        *ledger.support_bindings[1:],
    )

    with pytest.raises(ValueError, match=r"exact|source.*evidence|evidence.*source"):
        build_prospective_input_ledger(
            request=submission.pipeline_request,
            sources=ledger.sources,
            evidence_records=ledger.evidence_records,
            confirmation_events=ledger.confirmation_events,
            artifacts=ledger.artifacts,
            support_bindings=bindings,
        )


def test_support_binding_rejects_mixed_source_classes_but_accepts_exact_same_class() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = submission.input_ledger
    binding = ledger.support_bindings[0]
    metadata_source = ledger.sources[-1]
    same_class_source = SourceRecord(
        source_id="SOURCE-QD-METADATA-SECOND",
        source_class=metadata_source.source_class,
        source_context=SourceContext.PLANNED,
        source_version="sha256:metadata-second",
    )
    same_class_evidence = EvidenceRecord(
        evidence_id="EV-QD-METADATA-SECOND",
        source_id=same_class_source.source_id,
        evidence_type=EvidenceTypeV8.STRUCTURAL_FACT,
        locator="fixture://metadata-second",
        original_text="A second metadata record corroborates this clause.",
    )
    exact_binding = binding.model_copy(
        update={
            "source_ids": (*binding.source_ids, same_class_source.source_id),
            "evidence_record_ids": (
                *binding.evidence_record_ids,
                same_class_evidence.evidence_id,
            ),
        }
    )
    rebuilt = build_prospective_input_ledger(
        request=submission.pipeline_request,
        sources=(*ledger.sources, same_class_source),
        evidence_records=(*ledger.evidence_records, same_class_evidence),
        confirmation_events=ledger.confirmation_events,
        artifacts=ledger.artifacts,
        support_bindings=(exact_binding, *ledger.support_bindings[1:]),
    )
    assert rebuilt.support_bindings[0].source_ids == exact_binding.source_ids

    mixed_evidence = same_class_evidence.model_copy(
        update={
            "evidence_id": "EV-QD-SAMPLE-SHEET-SECOND",
            "source_id": ledger.sources[0].source_id,
        }
    )
    mixed_binding = binding.model_copy(
        update={
            "source_ids": (*binding.source_ids, ledger.sources[0].source_id),
            "evidence_record_ids": (*binding.evidence_record_ids, mixed_evidence.evidence_id),
        }
    )
    with pytest.raises(ValueError, match=r"source class|source_class"):
        build_prospective_input_ledger(
            request=submission.pipeline_request,
            sources=ledger.sources,
            evidence_records=(*ledger.evidence_records, mixed_evidence),
            confirmation_events=ledger.confirmation_events,
            artifacts=ledger.artifacts,
            support_bindings=(mixed_binding, *ledger.support_bindings[1:]),
        )


def test_unbound_confirmation_event_is_rejected_by_bidirectional_closure() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = submission.input_ledger
    binding = next(
        item for item in ledger.support_bindings if item.scope_kind is SupportBindingScope.PREDICATE
    )
    event = fix2_fixture._confirmation_for(
        submission,
        binding,
        scope_id=binding.scope_id,
        value=submission.pipeline_request.predicate_values[binding.scope_id].value,
    )

    with pytest.raises(ValueError, match=r"unbound|exact.*confirmation|bidirectional"):
        build_prospective_input_ledger(
            request=submission.pipeline_request,
            sources=ledger.sources,
            evidence_records=ledger.evidence_records,
            confirmation_events=(event,),
            artifacts=ledger.artifacts,
            support_bindings=ledger.support_bindings,
        )


def test_executed_confirmation_without_typed_binding_fails_closed() -> None:
    _, submission = quick_design_fixture._submission()
    ledger = task6_fixture._execution_ledger("fix3-unbound-confirmation")
    event = ConfirmationEvent(
        event_id="CONF-TASK6-FIX3-EXECUTED-UNBOUND",
        support=submission.input_ledger.support_bindings[0].support,
        evidence_refs=("EV-RUNTIME-001",),
        scope_id="executed-assignment-separability",
        confirmed_value=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=True,
            evidence_ids=("EV-RUNTIME-001",),
            query_scope_id=task6_fixture.QUERY_ID,
        ),
        actor_role="execution-reviewer",
        review_independent=True,
        created_at=datetime(2026, 8, 8, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match=r"SCIENTIFIC_REVIEW_REQUIRED|typed support"):
        build_executed_input_ledger(
            sources=ledger.sources,
            evidence_records=ledger.evidence_records,
            confirmation_events=(event,),
            artifacts=ledger.artifacts,
        )


def test_reconciliation_fails_closed_for_an_executed_only_semantic_count_scope() -> None:
    plan = task6_fixture._plan()
    ledger = task6_fixture._execution_ledger("fix3-extra-scope")
    matching = task6_fixture._count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4)
    extra = matching.model_copy(
        update={
            "count_id": "COUNT-TASK6-FIX3-EXECUTED-ONLY",
            "scope": matching.scope.model_copy(
                update={"group_id": task6_fixture._present("vehicle")}
            ),
        }
    )
    execution = build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(),
        count_records=(matching, extra),
        deviations=task6_fixture._deviation_absent(),
        final_sample_sheet_ref=task6_fixture._sample_sheet().artifact_id,
        execution_log_refs=(ledger.artifacts[1].artifact_id,),
    )

    reconciliation = reconcile_plan_execution(plan, execution)

    assert reconciliation.status.value == "SCIENTIFIC_REVIEW_REQUIRED"
    assert reconciliation.deviations.knowledge_state is KnowledgeState.UNKNOWN
    assert reconciliation.review_requirement is not None
    assert "executed" in reconciliation.review_requirement.rationale.lower()


def test_material_conflict_without_conflicting_claim_state_fails_closed() -> None:
    _, result = fix2_fixture._quick_result()
    report = result.report_bundle
    claim = report.claim_sets[0].claims[0]
    proof_step = claim.proof_trace[0]
    evidence_ids = tuple(record.evidence_id for record in report.evidence_records[:2])
    conflict = ConflictRecord(
        conflict_id="CONFLICT-TASK6-FIX3-MATERIAL",
        inferential_query_ids=(claim.inferential_query_id,),
        affected_claim_ids=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=(claim.claim_id,),
            evidence_ids=evidence_ids,
            claim_scope_id="CONFLICT-TASK6-FIX3-MATERIAL",
        ),
        evidence_record_ids=evidence_ids,
        predicate_bindings=(
            ConflictPredicateProofBinding(
                inferential_query_id=claim.inferential_query_id,
                derived_claim_id=claim.claim_id,
                proof_step_id=proof_step.step_id,
                predicate_id=proof_step.predicate_references[0].predicate_id,
                predicate_value=KnowledgeValue(
                    knowledge_state=KnowledgeState.CONFLICTING,
                    conflicting_values=(
                        "assignment-before-split",
                        "assignment-after-split",
                    ),
                    evidence_ids=evidence_ids,
                    query_scope_id=claim.inferential_query_id,
                ),
            ),
        ),
        retained_values=("assignment-before-split", "assignment-after-split"),
        rationale="The material assignment timing remains unresolved.",
    )
    conflict_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(conflict,),
        evidence_ids=evidence_ids,
        query_scope_id=claim.inferential_query_id,
    )

    with pytest.raises(ValueError, match=r"SCIENTIFIC_REVIEW_REQUIRED|conflict.*claim"):
        _rebuild_report(report, conflicts=conflict_state)


def test_legacy_caller_declared_irrelevant_conflict_fails_without_reviewed_artifact() -> None:
    _, result = fix2_fixture._quick_result()
    report = result.report_bundle
    query_id = report.claim_sets[0].inferential_query_id
    evidence_ids = tuple(record.evidence_id for record in report.evidence_records[:2])
    conflict = ConflictRecord(
        conflict_id="CONFLICT-TASK6-FIX3-IRRELEVANT",
        inferential_query_ids=(query_id,),
        affected_claim_ids=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=evidence_ids,
        ),
        evidence_record_ids=evidence_ids,
        retained_values=("metadata-label-a", "metadata-label-b"),
        rationale="Reviewed as irrelevant to every requested derived claim.",
    )
    conflict_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=(conflict,),
        evidence_ids=evidence_ids,
        query_scope_id=query_id,
    )

    with pytest.raises(
        ConflictScientificReviewRequired,
        match=r"SRR-V8-010|reviewed materiality artifact",
    ):
        _rebuild_report(report, conflicts=conflict_state)


def test_public_resolver_revalidates_claim_sets_and_rejects_global_claim_id_reuse() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["resolve_report_claim_sets"])
    _, pipeline_result = review_fixture._pipeline()
    first = pipeline_result.claim_set
    invalid_claim = first.claims[0].model_copy(
        update={"inferential_query_id": "IQ-TAMPERED-OUTSIDE-SET"}
    )
    invalid_set = first.model_copy(update={"claims": (invalid_claim, *first.claims[1:])})
    with pytest.raises(ValueError, match=r"query|claim set"):
        reporting.resolve_report_claim_sets((invalid_set,))

    duplicate_query_id = "IQ-TASK6-FIX3-DUPLICATE-CLAIMS"
    duplicate_ids = type(first)(
        claim_set_id="CLAIM-SET-TASK6-FIX3-DUPLICATE-CLAIMS",
        inferential_query_id=duplicate_query_id,
        claims=tuple(
            claim.model_copy(update={"inferential_query_id": duplicate_query_id})
            for claim in first.claims
        ),
    )
    with pytest.raises(ValueError, match=r"global|duplicate.*claim"):
        reporting.resolve_report_claim_sets((first, duplicate_ids))


def test_multi_query_report_uses_two_present_query_scoped_candidate_sets() -> None:
    report = review_fixture._multi_query_report()
    query_ids = tuple(section.inferential_query.id for section in report.query_sections)
    evidence_id = report.evidence_records[0].evidence_id
    candidate_sets = tuple(
        _candidate_state(
            query_id=query_id,
            evidence_id=evidence_id,
            candidate=_empty_candidate(suffix=str(index)),
        )
        for index, query_id in enumerate(query_ids, start=1)
    )

    rebuilt = _rebuild_report(report, ai_candidates=candidate_sets)

    assert tuple(item.query_scope_id for item in rebuilt.ai_candidates) == query_ids
    assert tuple(section.ai_candidates for section in rebuilt.query_sections) == candidate_sets


def test_multi_query_report_rejects_candidate_id_collision_across_outputs() -> None:
    report = review_fixture._multi_query_report()
    query_ids = tuple(section.inferential_query.id for section in report.query_sections)
    evidence_id = report.evidence_records[0].evidence_id
    candidate = ParserCandidateOutput.model_validate(parser_fixture._candidate_payload())
    candidate_sets = tuple(
        _candidate_state(query_id=query_id, evidence_id=evidence_id, candidate=candidate)
        for query_id in query_ids
    )

    with pytest.raises(ValueError, match=r"candidate.*global|duplicate.*candidate|collision"):
        _rebuild_report(report, ai_candidates=candidate_sets)


def test_html_renders_field_level_support_lineage_without_false_completeness_claim() -> None:
    from ntruth.reporting.v8 import render_report_bundle_html

    submission, result = fix2_fixture._quick_result()
    html = render_report_bundle_html(result.report_bundle)
    binding = submission.input_ledger.support_bindings[0]

    assert "Support binding lineage" in html
    for expected in (
        binding.scope_kind.value,
        binding.scope_id,
        binding.support.source_class.token,
        binding.support.authority_type.value,
        binding.support.evidence_basis.value,
        binding.support.support_grade.vocabulary_id,
        binding.support.support_grade.token,
        *binding.source_ids,
        *binding.evidence_record_ids,
    ):
        assert expected in html
    assert "Full source/authority/evidence/support lineage is retained" not in html
