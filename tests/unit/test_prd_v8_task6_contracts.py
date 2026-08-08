"""PRD v8 Task 6 prospective-design and neutral-report contract regressions."""

from __future__ import annotations

import json

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture
from pydantic import ValidationError

from ntruth.schemas.claims import DerivedClaim, DerivedClaimSet, DeterminabilityState
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CountLifecyclePhase,
    CountOrigin,
    CountQuantifier,
    CountScope,
)
from ntruth.schemas.events import (
    AssignmentEvent,
    EventRegistry,
    RelativeTiming,
    SplitEvent,
    TemporalRelation,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.report_resolution import TrivialExplicitReportResolutionPolicy
from ntruth.schemas.support import SourceClassRef, SourceContext, SourceRecord

QUERY_ID = "IQ-TASK6-001"
BLOCK_ID = "BLOCK-TASK6-001"


def _present(
    value: object,
    evidence: str = "EV-TASK6-001",
    *,
    query_id: str = QUERY_ID,
) -> KnowledgeValue[object]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence,),
        query_scope_id=query_id,
    )


def _not_applicable(rationale: str) -> KnowledgeValue[object]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale=rationale,
        query_scope_id=QUERY_ID,
    )


def _event_registry(*, executed: bool = False) -> EventRegistry:
    suffix = "EXEC" if executed else "PLAN"
    split = SplitEvent(
        event_id=f"EVT-SPLIT-{suffix}",
        experiment_block_id=BLOCK_ID,
        evidence_refs=(f"EV-{suffix}",),
        source_unit_ids=_present(("culture-1",), f"EV-{suffix}"),
        resulting_unit_ids=_present(("well-1", "well-2"), f"EV-{suffix}"),
    )
    assignment = AssignmentEvent(
        event_id=f"EVT-ASSIGN-{suffix}",
        experiment_block_id=BLOCK_ID,
        evidence_refs=(f"EV-{suffix}",),
        factor_id="factor-treatment",
        assigned_unit_type=_present("well", f"EV-{suffix}"),
        assigned_unit_ids=_present(("well-1", "well-2"), f"EV-{suffix}"),
    )
    return EventRegistry(
        events=(split, assignment),
        relative_timings=(
            RelativeTiming(
                subject_event_id=assignment.event_id,
                reference_event_id=split.event_id,
                relation=TemporalRelation.AFTER,
                evidence_refs=(f"EV-{suffix}",),
            ),
        ),
    )


def _scope(phase: CountLifecyclePhase, *, query_id: str = QUERY_ID) -> CountScope:
    return CountScope(
        query_id=query_id,
        unit_type=_present("well", query_id=query_id),
        factor_id=_present("factor-treatment", query_id=query_id),
        contrast_id=_present("vehicle-vs-drug", query_id=query_id),
        group_id=_present("drug", query_id=query_id),
        endpoint_id=_present("viability", query_id=query_id),
        timepoint_id=_present("T48H", query_id=query_id),
        cohort_id=_present("cohort-task6", query_id=query_id),
        lifecycle_phase=_present(phase, query_id=query_id),
        population_scope=_present("cultures-under-protocol", query_id=query_id),
        condition=_present("included", query_id=query_id),
    )


def _count(
    kind: CanonicalCountKind,
    value: int,
    *,
    query_id: str = QUERY_ID,
) -> CanonicalCountRecord:
    phase = {
        CanonicalCountKind.PLANNED_UNIT_COUNT: CountLifecyclePhase.PLANNED,
        CanonicalCountKind.OBSERVED_UNIT_COUNT: CountLifecyclePhase.OBSERVED,
    }[kind]
    return CanonicalCountRecord(
        count_id=f"COUNT-{query_id}-{kind.value}-{value}",
        kind=kind,
        value=_present(value, query_id=query_id),
        quantifier=CountQuantifier.EXACT,
        scope=_scope(phase, query_id=query_id),
        source_evidence=("EV-TASK6-COUNT",),
        origin=CountOrigin.SOURCE_DECLARATION,
    )


def _source(context: SourceContext) -> SourceRecord:
    return SourceRecord(
        source_id=f"SOURCE-{context.value}",
        source_class=SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="sample_sheet",
        ),
        source_context=context,
        source_version="sha256:task6-fixture",
    )


def _plan() -> object:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["build_planned_design"])
    return prospective.build_planned_design(
        experiment_block_id=BLOCK_ID,
        inferential_query_ids=(QUERY_ID,),
        sources=(_source(SourceContext.PLANNED),),
        event_registry=_event_registry(),
        count_records=(_count(CanonicalCountKind.PLANNED_UNIT_COUNT, 4),),
        sample_sheet_ref="artifact://sample-sheet/planned-v1",
        methods_draft_ref="artifact://methods/planned-v1",
        user_confirmation_scopes=("assignment_event", "planned_unit_count"),
    )


def test_planned_design_is_immutable_content_addressed_and_event_referenced() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["PlannedDesignRecord"])
    plan = _plan()

    assert plan.plan_id == f"PLAN-{plan.content_checksum[:20]}"
    assert plan.count_records[0].kind is CanonicalCountKind.PLANNED_UNIT_COUNT
    assert plan.count_records[0].scope.query_id == QUERY_ID
    assert plan.event_registry.relative_timings[0].reference_event_id == "EVT-SPLIT-PLAN"
    prospective.PlannedDesignRecord.model_validate(plan.model_dump(mode="python"))

    with pytest.raises(ValidationError):
        plan.sample_sheet_ref = "artifact://silently-rewritten"


def test_planned_design_rejects_global_timing_and_non_planned_counts() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["PlannedDesignRecord"])
    plan = _plan()
    global_timing = plan.model_dump(mode="python") | {"timing_relative_to_split": "before"}
    with pytest.raises(ValidationError, match="timing_relative_to_split"):
        prospective.PlannedDesignRecord.model_validate(global_timing)

    with pytest.raises(ValueError, match="planned_unit_count"):
        prospective.build_planned_design(
            experiment_block_id=BLOCK_ID,
            inferential_query_ids=(QUERY_ID,),
            sources=(_source(SourceContext.PLANNED),),
            event_registry=_event_registry(),
            count_records=(_count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 3),),
            sample_sheet_ref="artifact://sample-sheet/planned-v1",
            methods_draft_ref="artifact://methods/planned-v1",
            user_confirmation_scopes=("assignment_event",),
        )


def test_two_executions_reconcile_to_same_exact_plan_without_rewriting_it() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["DeviationRecord"])
    plan = _plan()
    execution_a = prospective.build_executed_design(
        planned_design=plan,
        sources=(_source(SourceContext.EXECUTED),),
        event_registry=_event_registry(executed=True),
        count_records=(_count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),),
        deviations=(),
        final_sample_sheet_ref="artifact://sample-sheet/executed-a",
        execution_log_refs=("artifact://log/a",),
    )
    execution_b = prospective.build_executed_design(
        planned_design=plan,
        sources=(_source(SourceContext.EXECUTED),),
        event_registry=_event_registry(executed=True),
        count_records=(_count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 3),),
        deviations=(
            prospective.DeviationRecord(
                deviation_id="DEV-LOST-WELL-001",
                affected_query_ids=(QUERY_ID,),
                field_path="counts/observed_unit_count",
                planned_value=_present(4),
                executed_value=_present(3, "EV-EXEC"),
                deviation_type=prospective.DeviationType.LOST_SAMPLE,
                evidence_refs=("EV-EXEC",),
                rationale="One planned well was lost before observation.",
            ),
        ),
        final_sample_sheet_ref="artifact://sample-sheet/executed-b",
        execution_log_refs=("artifact://log/b",),
    )

    assert execution_a.planned_design_id == execution_b.planned_design_id == plan.plan_id
    assert execution_a.planned_design_checksum == plan.content_checksum
    assert execution_b.planned_design_checksum == plan.content_checksum
    assert execution_a.execution_id != execution_b.execution_id
    assert plan.count_records[0].value.value == 4

    reconciliation_a = prospective.reconcile_plan_execution(plan, execution_a)
    reconciliation_b = prospective.reconcile_plan_execution(plan, execution_b)
    assert reconciliation_a.deviations.knowledge_state is KnowledgeState.ABSENT_EXPLICIT
    assert reconciliation_b.deviations.value[0].deviation_type is (
        prospective.DeviationType.LOST_SAMPLE
    )


def test_reconciliation_rejects_wrong_plan_id_or_checksum() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["reconcile_plan_execution"])
    plan = _plan()
    execution = prospective.build_executed_design(
        planned_design=plan,
        sources=(_source(SourceContext.EXECUTED),),
        event_registry=_event_registry(executed=True),
        count_records=(_count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),),
        deviations=(),
        final_sample_sheet_ref="artifact://sample-sheet/executed-a",
        execution_log_refs=("artifact://log/a",),
    )

    wrong_id = execution.model_copy(update={"planned_design_id": "PLAN-WRONG"})
    with pytest.raises(ValueError, match="plan ID"):
        prospective.reconcile_plan_execution(plan, wrong_id)
    wrong_hash = execution.model_copy(update={"planned_design_checksum": "0" * 64})
    with pytest.raises(ValueError, match="plan checksum"):
        prospective.reconcile_plan_execution(plan, wrong_hash)


def test_multi_query_deviations_have_explicit_scopes_without_first_query_default() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["DeviationRecord"])
    second_query = "IQ-TASK6-002"
    plan = prospective.build_planned_design(
        experiment_block_id=BLOCK_ID,
        inferential_query_ids=(QUERY_ID, second_query),
        sources=(_source(SourceContext.PLANNED),),
        event_registry=_event_registry(),
        count_records=(
            _count(CanonicalCountKind.PLANNED_UNIT_COUNT, 4),
            _count(
                CanonicalCountKind.PLANNED_UNIT_COUNT,
                6,
                query_id=second_query,
            ),
        ),
        sample_sheet_ref="artifact://sample-sheet/planned-multi-query",
        methods_draft_ref="artifact://methods/planned-multi-query",
        user_confirmation_scopes=("assignment_event", "planned_unit_count"),
    )
    deviation = prospective.DeviationRecord(
        deviation_id="DEV-QUERY-2-001",
        affected_query_ids=(second_query,),
        field_path="counts/observed_unit_count",
        planned_value=_present(6, query_id=second_query),
        executed_value=_present(5, "EV-EXEC-Q2", query_id=second_query),
        deviation_type=prospective.DeviationType.LOST_SAMPLE,
        evidence_refs=("EV-EXEC-Q2",),
        rationale="One unit was lost only for the second endpoint cohort.",
    )
    execution = prospective.build_executed_design(
        planned_design=plan,
        sources=(_source(SourceContext.EXECUTED),),
        event_registry=_event_registry(executed=True),
        count_records=(
            _count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),
            _count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 5, query_id=second_query),
        ),
        deviations=(deviation,),
        final_sample_sheet_ref="artifact://sample-sheet/executed-multi-query",
        execution_log_refs=("artifact://log/multi-query",),
    )

    assert execution.deviations.query_scope_id is None
    assert execution.deviations.value[0].affected_query_ids == (second_query,)


def test_plan_requires_exactly_one_planned_unit_count_for_each_query() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["build_planned_design"])
    second_query = "IQ-TASK6-002"

    with pytest.raises(ValueError, match="exactly one planned_unit_count"):
        prospective.build_planned_design(
            experiment_block_id=BLOCK_ID,
            inferential_query_ids=(QUERY_ID, second_query),
            sources=(_source(SourceContext.PLANNED),),
            event_registry=_event_registry(),
            count_records=(_count(CanonicalCountKind.PLANNED_UNIT_COUNT, 4),),
            sample_sheet_ref="artifact://sample-sheet/incomplete-plan",
            methods_draft_ref="artifact://methods/incomplete-plan",
            user_confirmation_scopes=("planned_unit_count",),
        )


def _determinate_claim_set(source: DerivedClaimSet) -> DerivedClaimSet:
    original = source.claims[0]
    proof = tuple(
        step.model_copy(
            update={
                "predicate_references": tuple(
                    reference.model_copy(
                        update={
                            "predicate_value": runtime_fixture._present(
                                "reviewed-required-predicate"
                            )
                        }
                    )
                    for reference in step.predicate_references
                )
            }
        )
        for step in original.proof_trace
    )
    payload = original.model_dump(mode="python")
    payload.update(
        {
            "value": runtime_fixture._present("well"),
            "determinability_state": DeterminabilityState.DETERMINATE,
            "proof_trace": proof,
            "state_contract_review": None,
        }
    )
    determinate = DerivedClaim.model_validate(payload)
    return DerivedClaimSet(
        claim_set_id="CLAIM-SET-TASK6-MIXED",
        inferential_query_id=source.inferential_query_id,
        claims=(determinate, *source.claims[1:]),
    )


def test_neutral_report_keeps_determinability_adequacy_and_coverage_independent() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["ReportBundle"])
    runtime = __import__("ntruth.pipeline_v8", fromlist=["ScenarioCoverage"])
    coverage = runtime.ScenarioCoverage(
        status=runtime.ScenarioCoverageStatus.NON_EXHAUSTIVE,
        profile_id=runtime_fixture.PROFILE_ID,
        theory_version=runtime_fixture.CANONICAL_BUNDLE.theory.theory_version,
        emitting_clause_ids=("DT-E-INTERFERENCE-ESTIMAND",),
        omitted_dimensions=runtime_fixture._present(("unreviewed_interference_topology",)),
        caveat=runtime_fixture._present("Additional exposure topologies may exist."),
    )
    runtime, request = runtime_fixture._request(
        interference=runtime_fixture.InterferenceStatus.DOCUMENTED,
        overrides={
            "interference_status": runtime_fixture._present("documented"),
            "exposure_interference": runtime_fixture._present("documented"),
        },
        scenario_coverages=(coverage,),
    )
    pipeline = runtime.run_v8_pipeline(
        request,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )
    claims = _determinate_claim_set(pipeline.claim_set)
    resolution = TrivialExplicitReportResolutionPolicy().resolve(claims)
    design_record_context = reporting.ReportDesignRecordContext(
        mode=reporting.ReportDesignContext.UNVERIFIED_RETROSPECTIVE,
        planned_design_id=_not_applicable("No prospective plan was supplied."),
        executed_design_id=_not_applicable("No executed-design record was supplied."),
        reconciliation_id=_not_applicable("No plan/execution pair was supplied."),
        retrospective_source_ids=_present(("SOURCE-executed",)),
    )
    bundle = reporting.build_report_bundle(
        design_record_context=design_record_context,
        source_records=(_source(SourceContext.EXECUTED),),
        ai_candidates=_not_applicable("Quick Design used no parser AI."),
        human_confirmations=_not_applicable("No confirmation event in this fixture."),
        conflicts=_not_applicable("No source conflict record in this fixture."),
        confirmed_graph=request.graph,
        claim_sets=(claims,),
        report_resolution=resolution,
        design_adequacy_evaluations=pipeline.design_adequacy_evaluations,
        count_records=request.count_registry.records,
        scenario_coverages=pipeline.scenario_coverages,
        sensitivities=_not_applicable("No self-report sensitivity in this fixture."),
        questions=(
            reporting.ReportQuestion(
                question_id="QUESTION-TASK6-001",
                inferential_query_id=request.query.id,
                text="Could shared exposure alter treatment realization?",
                evidence_required=("execution_log", "exposure_event"),
                primary=True,
            ),
        ),
        statistical_handoff=reporting.StatisticalHandoff(
            strategy_module_status=reporting.StrategyModuleStatus.HANDOFF_ONLY,
            structural_requirements=("Model the documented exposure grouping explicitly.",),
            unresolved_questions=("How many independently exposed clusters were realized?",),
        ),
        profile_coverage=pipeline.profile_coverage,
        inference_limits=("No claim beyond the declared query population.",),
        execution_manifest=pipeline.execution_manifest,
    )

    assert any(
        claim.determinability_state is DeterminabilityState.DETERMINATE
        for claim_set in bundle.claim_sets
        for claim in claim_set.claims
    )
    assert bundle.design_adequacy_evaluations[0].finding_type == "INTERFERENCE_DOCUMENTED"
    assert bundle.scenario_coverages[0].status.value == "NON_EXHAUSTIVE"
    assert bundle.strategy_module_status is reporting.StrategyModuleStatus.HANDOFF_ONLY
    assert bundle.design_record_context.mode is (
        reporting.ReportDesignContext.UNVERIFIED_RETROSPECTIVE
    )
    assert bundle.epistemic_boundary == reporting.RETROSPECTIVE_EPISTEMIC_BOUNDARY

    serialized = json.dumps(bundle.model_dump(mode="json"), sort_keys=True).lower()
    assert "candidate_analysis_strategies" not in serialized
    assert '"approval"' not in serialized
    assert '"approved"' not in serialized
    assert '"good_design"' not in serialized


def test_strategy_module_is_handoff_only_and_report_forbids_approval_fields() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["ReportBundle"])

    assert tuple(reporting.StrategyModuleStatus) == (reporting.StrategyModuleStatus.HANDOFF_ONLY,)
    with pytest.raises(ValueError):
        reporting.StrategyModuleStatus("CANDIDATE_STRATEGY_FAMILIES")
    with pytest.raises(ValidationError, match="candidate_analysis_strategies"):
        reporting.StatisticalHandoff.model_validate(
            {
                "strategy_module_status": "HANDOFF_ONLY",
                "structural_requirements": ["Preserve clustering."],
                "unresolved_questions": ["How many clusters?"],
                "candidate_analysis_strategies": ["mixed model"],
            }
        )


def test_multi_query_report_fails_closed_on_query_local_resolution() -> None:
    reporting = __import__("ntruth.schemas.report_bundle", fromlist=["ReportBundle"])
    runtime, request = runtime_fixture._request()
    pipeline = runtime.run_v8_pipeline(
        request,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )
    first = pipeline.claim_set
    second_query_id = "IQ-TASK6-REPORT-002"
    second = first.model_copy(
        update={
            "claim_set_id": "CLAIM-SET-TASK6-REPORT-002",
            "inferential_query_id": second_query_id,
            "claims": tuple(
                claim.model_copy(update={"inferential_query_id": second_query_id})
                for claim in first.claims
            ),
        }
    )
    context = reporting.ReportDesignRecordContext(
        mode=reporting.ReportDesignContext.UNVERIFIED_RETROSPECTIVE,
        planned_design_id=_not_applicable("No prospective plan was supplied."),
        executed_design_id=_not_applicable("No executed-design record was supplied."),
        reconciliation_id=_not_applicable("No plan/execution pair was supplied."),
        retrospective_source_ids=_present(("SOURCE-executed",)),
    )

    with pytest.raises(ValueError, match="SRR-V8-014"):
        reporting.build_report_bundle(
            design_record_context=context,
            source_records=(_source(SourceContext.EXECUTED),),
            ai_candidates=_not_applicable("No parser AI in this fixture."),
            human_confirmations=_not_applicable("No confirmations in this fixture."),
            conflicts=_not_applicable("No conflicts in this fixture."),
            confirmed_graph=request.graph,
            claim_sets=(first, second),
            report_resolution=pipeline.report_resolution,
            design_adequacy_evaluations=pipeline.design_adequacy_evaluations,
            count_records=request.count_registry.records,
            scenario_coverages=(
                runtime.ScenarioCoverage(
                    status=runtime.ScenarioCoverageStatus.NON_EXHAUSTIVE,
                    profile_id=runtime_fixture.PROFILE_ID,
                    theory_version=runtime_fixture.CANONICAL_BUNDLE.theory.theory_version,
                    emitting_clause_ids=("DT-E-INTERFERENCE-ESTIMAND",),
                    omitted_dimensions=runtime_fixture._present(("other_query",)),
                    caveat=runtime_fixture._present("Second-query aggregation is unreviewed."),
                ),
            ),
            sensitivities=_not_applicable("No sensitivity in this fixture."),
            questions=(
                reporting.ReportQuestion(
                    question_id="QUESTION-TASK6-MULTI",
                    inferential_query_id=request.query.id,
                    text="What is the global report resolution?",
                    evidence_required=("reviewed_aggregation_policy",),
                    primary=True,
                ),
            ),
            statistical_handoff=reporting.StatisticalHandoff(
                structural_requirements=("Keep queries separate.",),
                unresolved_questions=("How should query states aggregate?",),
            ),
            profile_coverage=pipeline.profile_coverage,
            inference_limits=("No global resolution without reviewed aggregation.",),
            execution_manifest=pipeline.execution_manifest,
        )


def test_task6_contracts_are_in_the_canonical_json_schema_export() -> None:
    """Catches runtime-only plan/execution/report contracts hidden from consumers."""

    from ntruth.schemas.kernel import kernel_json_schemas

    assert {
        "planned_design_record",
        "executed_design_record",
        "plan_execution_reconciliation",
        "report_bundle",
    } <= kernel_json_schemas().keys()
