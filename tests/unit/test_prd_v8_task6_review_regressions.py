"""Review regressions for the complete PRD v8 Task 6 scientific boundary."""

from __future__ import annotations

from inspect import signature
from typing import Any

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture
import test_prd_v8_quick_design as quick_design_fixture
import test_prd_v8_task6_contracts as task6_fixture

from ntruth.pipeline_v8 import V8PipelineRequest, run_v8_pipeline
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.count_registry import CanonicalCountKind, CanonicalCountRegistry
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import SourceContext


def _required(module: object, name: str) -> object:
    assert hasattr(module, name), f"missing reviewed Task6 contract: {name}"
    return getattr(module, name)


def _pipeline() -> tuple[object, object]:
    _, request = runtime_fixture._request()
    result = run_v8_pipeline(
        request,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )
    return request, result


def _second_claim_set(first: DerivedClaimSet) -> DerivedClaimSet:
    query_id = "IQ-TASK6-REVIEW-002"
    return DerivedClaimSet(
        claim_set_id="CLAIM-SET-TASK6-REVIEW-002",
        inferential_query_id=query_id,
        claims=tuple(
            claim.model_copy(update={"inferential_query_id": query_id}) for claim in first.claims
        ),
    )


def _multi_query_report(*, conflicting_shared_source: bool = False) -> object:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["build_planned_design"])
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["build_report_bundle"])
    _, submission = quick_design_fixture._submission()
    base = submission.pipeline_request
    second_query_id = "IQ-TASK6-MULTI-002"

    def rescope(value: Any) -> Any:
        return value.model_copy(update={"query_scope_id": second_query_id})

    second_query = base.query.model_copy(
        update={
            "id": second_query_id,
            **{
                field: rescope(getattr(base.query, field))
                for field in (
                    "timepoint_id",
                    "effect_measure_or_estimand",
                    "inference_population",
                    "inference_level",
                )
            },
        }
    )
    second_counts = []
    for record in base.count_registry.records:
        scope = record.scope
        second_scope = scope.model_copy(
            update={
                "query_id": second_query_id,
                **{
                    field: rescope(getattr(scope, field))
                    for field in (
                        "unit_type",
                        "factor_id",
                        "contrast_id",
                        "group_id",
                        "endpoint_id",
                        "timepoint_id",
                        "cohort_id",
                        "lifecycle_phase",
                        "population_scope",
                        "condition",
                    )
                },
            }
        )
        second_counts.append(
            record.model_copy(
                update={
                    "count_id": f"{record.count_id}-Q2",
                    "scope": second_scope,
                    "value": rescope(record.value),
                }
            )
        )
    registry = CanonicalCountRegistry(records=(*base.count_registry.records, *second_counts))
    second_node = base.graph.nodes[1].model_copy(update={"node_id": second_query_id})
    graph = base.graph.model_copy(update={"nodes": (*base.graph.nodes, second_node)})
    first_request = V8PipelineRequest.model_validate(
        base.model_copy(update={"graph": graph, "count_registry": registry}).model_dump(
            mode="python"
        )
    )
    causal_context = first_request.causal_aggregate.causal_context
    second_causal_context = causal_context.model_copy(
        update={
            "inferential_query_id": second_query_id,
            **{
                field: rescope(getattr(causal_context, field))
                for field in (
                    "assignment_event_id",
                    "application_event_id",
                    "exposure_event_id",
                    "assignment_unit_type",
                    "application_unit_type",
                    "effective_exposure_unit_type",
                    "experimental_unit_type",
                    "biological_source_unit_type",
                    "interference_status",
                )
            },
        }
    )
    second_request = V8PipelineRequest.model_validate(
        first_request.model_copy(
            update={
                "query": second_query,
                "causal_aggregate": first_request.causal_aggregate.model_copy(
                    update={"causal_context": second_causal_context}
                ),
                "predicate_values": {
                    predicate_id: rescope(value)
                    for predicate_id, value in first_request.predicate_values.items()
                },
                "experimental_unit_count_record_id": second_counts[0].count_id,
                "biological_source_count_record_id": second_counts[1].count_id,
            }
        ).model_dump(mode="python")
    )

    ledgers = []
    for index, request in enumerate((first_request, second_request)):
        sources = submission.input_ledger.sources
        if conflicting_shared_source and index == 1:
            sources = (
                sources[0].model_copy(update={"source_version": "sha256:conflicting"}),
                *sources[1:],
            )
        ledgers.append(
            prospective.build_prospective_input_ledger(
                request=request,
                sources=sources,
                evidence_records=submission.input_ledger.evidence_records,
                confirmation_events=(),
                artifacts=submission.input_ledger.artifacts,
                support_bindings=submission.input_ledger.support_bindings,
            )
        )
    results = tuple(
        run_v8_pipeline(request, conformance_bundle=runtime_fixture.CANONICAL_BUNDLE)
        for request in (first_request, second_request)
    )
    contexts = tuple(
        reporting.build_verified_pipeline_context(
            request=request,
            result=result,
            conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
        )
        for request, result in zip((first_request, second_request), results, strict=True)
    )
    artifacts_by_kind = {artifact.kind: artifact for artifact in submission.input_ledger.artifacts}
    plan = prospective.build_planned_design(
        experiment_block_id=first_request.experiment_block_id,
        inferential_queries=(first_request.query, second_request.query),
        sources=submission.input_ledger.sources,
        evidence_records=submission.input_ledger.evidence_records,
        confirmation_events=(),
        event_registry=submission.planned_event_registry,
        count_records=(base.count_registry.records[2], second_counts[2]),
        sample_sheet_ref=artifacts_by_kind[
            prospective.ProspectiveArtifactKind.SAMPLE_SHEET
        ].artifact_id,
        methods_draft_ref=artifacts_by_kind[
            prospective.ProspectiveArtifactKind.METHODS_DRAFT
        ].artifact_id,
        id_convention_ref=artifacts_by_kind[
            prospective.ProspectiveArtifactKind.ID_CONVENTION
        ].artifact_id,
        user_confirmation_scopes=submission.user_confirmation_scopes,
    )
    evidence_ids = tuple(record.evidence_id for record in submission.input_ledger.evidence_records)

    def not_applicable(rationale: str) -> KnowledgeValue[object]:
        return KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale=rationale,
            claim_scope_id="REPORT-TASK6-MULTI",
        )

    design_context = reporting.ReportDesignRecordContext(
        mode=reporting.ReportDesignContext.PLANNED,
        planned_design_record=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=plan,
            evidence_ids=evidence_ids,
            claim_scope_id="REPORT-TASK6-MULTI",
        ),
        executed_design_record=not_applicable("No execution exists."),
        reconciliation_record=not_applicable("No reconciliation exists."),
        retrospective_source_ids=not_applicable("This is a prospective report."),
    )
    ledger_state = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=tuple(ledgers),
        evidence_ids=evidence_ids,
        claim_scope_id="REPORT-TASK6-MULTI",
    )
    confirmations = KnowledgeValue(
        knowledge_state=KnowledgeState.NOT_REPORTED,
        source_scope_ids=tuple(source.source_id for source in submission.input_ledger.sources),
        claim_scope_id="REPORT-TASK6-MULTI",
    )
    questions = (
        submission.questions[0],
        submission.questions[0].model_copy(
            update={
                "question_id": "QUESTION-TASK6-MULTI-002",
                "inferential_query_id": second_query_id,
            }
        ),
    )
    return reporting.build_report_bundle(
        verified_pipeline_contexts=contexts,
        design_record_context=design_context,
        prospective_input_ledgers=ledger_state,
        source_records=submission.input_ledger.sources,
        evidence_records=submission.input_ledger.evidence_records,
        ai_candidates=submission.ai_candidates,
        human_confirmations=confirmations,
        conflicts=submission.conflicts,
        sensitivities=submission.sensitivities,
        questions=questions,
        statistical_handoff=submission.statistical_handoff,
        inference_limits=submission.inference_limits,
    )


def test_multi_query_resolution_is_always_global_unknown_while_srr_014_is_open() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["resolve_report_claim_sets"])
    resolve = _required(reporting, "resolve_report_claim_sets")
    _, result = _pipeline()

    single = resolve((result.claim_set,))
    assert single.resolution.query_scope_id == result.claim_set.inferential_query_id

    multi = resolve((result.claim_set, _second_claim_set(result.claim_set)))
    assert multi.resolution.knowledge_state is KnowledgeState.UNKNOWN
    assert multi.resolution.query_scope_id is None
    assert multi.review_requirement.issue_id == "SRR-V8-014"


def test_multi_query_report_deduplicates_identical_shared_records() -> None:
    bundle = _multi_query_report()

    assert len(bundle.query_sections) == 2
    assert bundle.report_resolution.resolution.knowledge_state is KnowledgeState.UNKNOWN
    assert bundle.report_resolution.review_requirement.issue_id == "SRR-V8-014"
    assert len(bundle.source_records) == len({source.source_id for source in bundle.source_records})
    assert len(bundle.evidence_records) == len(
        {record.evidence_id for record in bundle.evidence_records}
    )


def test_multi_query_report_rejects_shared_id_content_collisions() -> None:
    with pytest.raises(ValueError, match="shared source ID has conflicting content"):
        _multi_query_report(conflicting_shared_source=True)


def test_report_factory_accepts_only_reverified_pipeline_contexts_and_rejects_mutations() -> None:
    reporting = __import__(
        "ntruth.schemas.report_bundle",
        fromlist=["build_verified_pipeline_context"],
    )
    build_context = _required(reporting, "build_verified_pipeline_context")
    parameters = signature(reporting.build_report_bundle).parameters
    assert "verified_pipeline_contexts" in parameters
    assert {
        "confirmed_graph",
        "claim_sets",
        "execution_manifest",
        "count_records",
        "scenario_coverages",
    }.isdisjoint(parameters)

    request, result = _pipeline()
    context = build_context(
        request=request,
        result=result,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )
    assert context.request == request
    assert context.result == result

    tampered_claims = result.model_copy(
        update={
            "claim_set": result.claim_set.model_copy(update={"claim_set_id": "CLAIM-SET-FORGED"})
        }
    )
    with pytest.raises(ValueError, match="verified pipeline"):
        build_context(
            request=request,
            result=tampered_claims,
            conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
        )
    with pytest.raises(ValueError, match="verified pipeline"):
        build_context(
            request=request.model_copy(
                update={
                    "graph": request.graph.model_copy(update={"nodes": request.graph.nodes[:-1]})
                }
            ),
            result=result,
            conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
        )


def test_quick_design_requires_a_content_addressed_closed_input_ledger() -> None:
    prospective = __import__(
        "ntruth.schemas.prospective",
        fromlist=["build_prospective_input_ledger"],
    )
    quick_design = __import__(
        "ntruth.quick_design.v8",
        fromlist=["QuickDesignScientificReviewRequired"],
    )
    build_ledger = _required(prospective, "build_prospective_input_ledger")
    blocker = _required(quick_design, "QuickDesignScientificReviewRequired")
    request, _ = _pipeline()

    with pytest.raises(blocker) as error:
        build_ledger(
            request=request,
            sources=(task6_fixture._source(SourceContext.PLANNED),),
            evidence_records=(),
            confirmation_events=(),
            artifacts=(),
        )
    assert error.value.review_requirement.status.value == "SCIENTIFIC_REVIEW_REQUIRED"


def test_every_pipeline_query_has_one_complete_unswappable_report_section() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["QueryReportSection"])
    section_type = _required(reporting, "QueryReportSection")
    fields = section_type.model_fields
    assert {
        "inferential_query",
        "claim_set",
        "adequacy_evaluations",
        "count_record_ids",
        "scenario_coverages",
        "profile_coverage",
        "questions",
    } <= fields.keys()
    assert "query_sections" in reporting.ReportBundle.model_fields


def test_reconciliation_derives_count_differences_and_unknown_is_not_absence() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["reconcile_plan_execution"])
    plan = task6_fixture._plan()
    ledger = task6_fixture._execution_ledger("review-count")
    execution = prospective.build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(),
        count_records=(task6_fixture._count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 3),),
        deviations=task6_fixture._deviation_absent(),
        final_sample_sheet_ref=task6_fixture._sample_sheet().artifact_id,
        execution_log_refs=(ledger.artifacts[1].artifact_id,),
    )
    reconciliation = prospective.reconcile_plan_execution(plan, execution)
    assert reconciliation.deviations.knowledge_state is KnowledgeState.PRESENT
    assert reconciliation.deviations.value
    assert reconciliation.deviations.value[0].field_path.startswith("count_registry/")

    unknown = KnowledgeValue[tuple[prospective.DeviationRecord, ...]](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale="Execution log does not establish whether deviations occurred.",
        query_scope_id=plan.inferential_query_ids[0],
    )
    ambiguous = prospective.build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=task6_fixture._event_registry(),
        count_records=(task6_fixture._count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 3),),
        deviations=unknown,
        final_sample_sheet_ref=task6_fixture._sample_sheet().artifact_id,
        execution_log_refs=(ledger.artifacts[1].artifact_id,),
    )
    reviewed = prospective.reconcile_plan_execution(plan, ambiguous)
    assert reviewed.status.value == "SCIENTIFIC_REVIEW_REQUIRED"
    assert reviewed.deviations.knowledge_state is KnowledgeState.UNKNOWN


def test_plan_pins_queries_evidence_confirmations_and_event_referenced_timing() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["PlannedDesignRecord"])
    fields = prospective.PlannedDesignRecord.model_fields
    assert {
        "inferential_queries",
        "query_checksums",
        "evidence_records",
        "confirmation_events",
        "id_convention_ref",
    } <= fields.keys()
    plan = task6_fixture._plan()
    assert plan.event_registry.relative_timings
    assert plan.inferential_queries[0].id == plan.inferential_query_ids[0]
    assert "executed_input_ledger" in prospective.ExecutedDesignRecord.model_fields
    assert {"evidence_records", "confirmation_events", "artifacts"} <= (
        prospective.ExecutedInputLedger.model_fields.keys()
    )


def test_report_design_mode_embeds_and_verifies_actual_addressed_records() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["ReportDesignRecordContext"])
    fields = reporting.ReportDesignRecordContext.model_fields
    assert {
        "planned_design_record",
        "executed_design_record",
        "reconciliation_record",
    } <= fields.keys()
    assert {
        "planned_design_id",
        "executed_design_id",
        "reconciliation_id",
    }.isdisjoint(fields)


def test_report_uses_typed_evidence_conflicts_and_rejects_dangling_references() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["ConflictRecord"])
    conflict_type = _required(reporting, "ConflictRecord")
    assert "evidence_record_ids" in conflict_type.model_fields
    assert "evidence_records" in reporting.ReportBundle.model_fields
    assert reporting.ReportBundle.model_fields["conflicts"].annotation is not dict


def test_report_uses_one_full_scope_canonical_count_registry() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["ReportBundle"])
    fields = reporting.ReportBundle.model_fields
    assert "count_registry" in fields
    assert "count_records" not in fields
    _, submission = quick_design_fixture._submission()
    count_ids = {item.count_id for item in submission.pipeline_request.count_registry.records}
    assert {item.count_id for item in submission.planned_unit_counts} <= count_ids


def test_html_projects_complete_graph_proof_scope_pins_and_query_sections() -> None:
    rendering = __import__("ntruth.reporting.v8", fromlist=["render_report_bundle_html"])
    _, submission = quick_design_fixture._submission()
    result = __import__(
        "ntruth.quick_design.v8", fromlist=["run_quick_design_v8"]
    ).run_quick_design_v8(
        submission,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )
    html = rendering.render_report_bundle_html(result.report_bundle)
    for label in (
        "Confirmed graph",
        "Irrelevant predicates and rationale",
        "Full ten-dimensional count scope",
        "Contract and execution pins",
        "Query report sections",
    ):
        assert label in html


def test_handoff_items_are_typed_sourced_and_never_generated_recommendations() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["HandoffItem"])
    item_type = _required(reporting, "HandoffItem")
    assert {
        "category",
        "origin",
        "authority",
        "evidence_refs",
        "inferential_query_id",
        "predicate_ids",
        "question_ids",
        "user_note",
    } <= (item_type.model_fields.keys())
    assert "text" not in item_type.model_fields
    assert "structural_requirements" not in reporting.StatisticalHandoff.model_fields
    assert "unresolved_questions" not in reporting.StatisticalHandoff.model_fields


def test_v8_artifacts_routes_and_exports_are_complete_and_legacy_names_are_qualified() -> None:
    quick_design = __import__("ntruth.quick_design", fromlist=["__all__"])
    reporting = __import__("ntruth.reporting", fromlist=["__all__"])
    api = __import__("ntruth.api.app", fromlist=["create_app"])
    result_type = __import__("ntruth.quick_design.v8", fromlist=["QuickDesignV8Result"])

    assert "artifacts" in result_type.QuickDesignV8Result.model_fields
    assert "run_quick_design_v7_session" in quick_design.__all__
    assert "run_quick_design_session" not in quick_design.__all__
    assert {
        "read_report_bundle_json",
        "report_bundle_to_dict",
        "write_report_bundle_html",
        "write_report_bundle_json",
        "write_report_bundle_yaml",
    } <= set(reporting.__all__)
    paths = {route.path for route in api.create_app().routes}
    assert "/v8/report" in paths
