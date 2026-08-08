"""PRD v8 Task 6 prospective-design and neutral-report contract regressions."""

from __future__ import annotations

import json

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture
import test_prd_v8_quick_design as quick_design_fixture
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
from ntruth.schemas.support import (
    EvidenceRecord,
    EvidenceTypeV8,
    SourceClassRef,
    SourceContext,
    SourceRecord,
)

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


def _query(query_id: str = QUERY_ID) -> object:
    _, request = runtime_fixture._request()
    return request.query.model_copy(
        update={
            "id": query_id,
            "timepoint_id": request.query.timepoint_id.model_copy(
                update={"query_scope_id": query_id}
            ),
            "effect_measure_or_estimand": request.query.effect_measure_or_estimand.model_copy(
                update={"query_scope_id": query_id}
            ),
            "inference_population": request.query.inference_population.model_copy(
                update={"query_scope_id": query_id}
            ),
            "inference_level": request.query.inference_level.model_copy(
                update={"query_scope_id": query_id}
            ),
        }
    )


def _plan_evidence(*, include_executed: bool = False) -> tuple[EvidenceRecord, ...]:
    identifiers = {
        "EV-RUNTIME-001",
        "EV-PLAN",
        "EV-TASK6-001",
        "EV-TASK6-COUNT",
    }
    if include_executed:
        identifiers.add("EV-EXEC")
    return tuple(
        EvidenceRecord(
            evidence_id=identifier,
            source_id="SOURCE-planned",
            evidence_type=EvidenceTypeV8.SAMPLE_METADATA_PLANNED,
            locator=f"fixture://{identifier}",
            original_text=f"Frozen fixture evidence {identifier}",
        )
        for identifier in sorted(identifiers)
    )


def _execution_evidence() -> tuple[EvidenceRecord, ...]:
    return tuple(
        EvidenceRecord(
            evidence_id=identifier,
            source_id="SOURCE-executed",
            evidence_type=EvidenceTypeV8.SAMPLE_METADATA_EXECUTED,
            locator=f"fixture://{identifier}",
            original_text=f"Frozen execution evidence {identifier}",
        )
        for identifier in (
            "EV-EXEC",
            "EV-EXEC-Q2",
            "EV-PLAN",
            "EV-TASK6-001",
            "EV-TASK6-COUNT",
        )
    )


def _sample_sheet() -> object:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["ProspectiveArtifactKind"])
    return prospective.build_prospective_artifact(
        kind=prospective.ProspectiveArtifactKind.SAMPLE_SHEET,
        media_type="text/csv",
        content="sample_id,status\nwell-1,planned\n",
    )


def _execution_ledger(suffix: str) -> object:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["ProspectiveArtifactKind"])
    execution_log = prospective.build_prospective_artifact(
        kind=prospective.ProspectiveArtifactKind.EXECUTION_LOG,
        media_type="text/plain",
        content=f"execution log {suffix}",
    )
    planned_evidence = _plan_evidence()
    planned_evidence_ids = {record.evidence_id for record in planned_evidence}
    return prospective.build_executed_input_ledger(
        sources=(_source(SourceContext.PLANNED), _source(SourceContext.EXECUTED)),
        evidence_records=(
            *planned_evidence,
            *(
                record
                for record in _execution_evidence()
                if record.evidence_id not in planned_evidence_ids
            ),
        ),
        confirmation_events=(),
        artifacts=(_sample_sheet(), execution_log),
    )


def _deviation_absent(*, query_id: str = QUERY_ID) -> KnowledgeValue[object]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
        evidence_ids=("EV-EXEC",),
        query_scope_id=query_id,
    )


def _plan() -> object:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["build_planned_design"])
    return prospective.build_planned_design(
        experiment_block_id=BLOCK_ID,
        inferential_queries=(_query(),),
        sources=(_source(SourceContext.PLANNED),),
        evidence_records=_plan_evidence(),
        confirmation_events=(),
        event_registry=_event_registry(),
        count_records=(_count(CanonicalCountKind.PLANNED_UNIT_COUNT, 4),),
        sample_sheet_ref=_sample_sheet().artifact_id,
        methods_draft_ref="artifact://methods/planned-v1",
        id_convention_ref="artifact://id-convention/planned-v1",
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
            inferential_queries=(_query(),),
            sources=(_source(SourceContext.PLANNED),),
            evidence_records=_plan_evidence(),
            confirmation_events=(),
            event_registry=_event_registry(),
            count_records=(_count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 3),),
            sample_sheet_ref="artifact://sample-sheet/planned-v1",
            methods_draft_ref="artifact://methods/planned-v1",
            id_convention_ref="artifact://id-convention/planned-v1",
            user_confirmation_scopes=("assignment_event",),
        )


def test_two_executions_reconcile_to_same_exact_plan_without_rewriting_it() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["DeviationRecord"])
    plan = _plan()
    ledger_a = _execution_ledger("a")
    ledger_b = _execution_ledger("b")
    execution_a = prospective.build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger_a,
        event_registry=_event_registry(),
        count_records=(_count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),),
        deviations=_deviation_absent(),
        final_sample_sheet_ref=_sample_sheet().artifact_id,
        execution_log_refs=(ledger_a.artifacts[1].artifact_id,),
    )
    execution_b = prospective.build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger_b,
        event_registry=_event_registry(),
        count_records=(_count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 3),),
        deviations=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=(
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
            evidence_ids=("EV-EXEC",),
            query_scope_id=QUERY_ID,
        ),
        final_sample_sheet_ref=_sample_sheet().artifact_id,
        execution_log_refs=(ledger_b.artifacts[1].artifact_id,),
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
    ledger = _execution_ledger("wrong-link")
    execution = prospective.build_executed_design(
        planned_design=plan,
        executed_input_ledger=ledger,
        event_registry=_event_registry(),
        count_records=(_count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),),
        deviations=_deviation_absent(),
        final_sample_sheet_ref=_sample_sheet().artifact_id,
        execution_log_refs=(ledger.artifacts[1].artifact_id,),
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
        inferential_queries=(_query(), _query(second_query)),
        sources=(_source(SourceContext.PLANNED),),
        evidence_records=_plan_evidence(),
        confirmation_events=(),
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
        id_convention_ref="artifact://id-convention/planned-multi-query",
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
        executed_input_ledger=_execution_ledger("multi-query"),
        event_registry=_event_registry(),
        count_records=(
            _count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 4),
            _count(CanonicalCountKind.OBSERVED_UNIT_COUNT, 5, query_id=second_query),
        ),
        deviations=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=(deviation,),
            evidence_ids=("EV-EXEC-Q2",),
            query_scope_id=second_query,
        ),
        final_sample_sheet_ref=_sample_sheet().artifact_id,
        execution_log_refs=(_execution_ledger("multi-query").artifacts[1].artifact_id,),
    )

    assert execution.deviations.query_scope_id == second_query
    assert execution.deviations.value[0].affected_query_ids == (second_query,)


def test_plan_requires_at_least_one_planned_unit_count_for_each_query() -> None:
    prospective = __import__("ntruth.schemas.prospective", fromlist=["build_planned_design"])
    second_query = "IQ-TASK6-002"

    with pytest.raises(ValueError, match="requires a planned_unit_count"):
        prospective.build_planned_design(
            experiment_block_id=BLOCK_ID,
            inferential_queries=(_query(), _query(second_query)),
            sources=(_source(SourceContext.PLANNED),),
            evidence_records=_plan_evidence(),
            confirmation_events=(),
            event_registry=_event_registry(),
            count_records=(_count(CanonicalCountKind.PLANNED_UNIT_COUNT, 4),),
            sample_sheet_ref="artifact://sample-sheet/incomplete-plan",
            methods_draft_ref="artifact://methods/incomplete-plan",
            id_convention_ref="artifact://id-convention/incomplete-plan",
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
    _, submission = quick_design_fixture._submission()
    result = __import__("ntruth.quick_design.v8", fromlist=["run_quick_design_v8"])
    bundle = result.run_quick_design_v8(
        submission,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    ).report_bundle

    assert bundle.claim_sets[0] == bundle.verified_pipeline_contexts[0].result.claim_set
    assert bundle.design_adequacy_evaluations[0].finding_type == "INTERFERENCE_POSSIBLE"
    assert bundle.scenario_coverages[0].status.value == "NON_EXHAUSTIVE"
    assert bundle.strategy_module_status is reporting.StrategyModuleStatus.HANDOFF_ONLY
    assert bundle.design_record_context.mode is (reporting.ReportDesignContext.PLANNED)
    assert bundle.epistemic_boundary == reporting.PLANNED_EPISTEMIC_BOUNDARY

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
    resolution = reporting.resolve_report_claim_sets((first, second))
    assert resolution.resolution.knowledge_state is KnowledgeState.UNKNOWN
    assert resolution.review_requirement.issue_id == "SRR-V8-014"


def test_task6_contracts_are_in_the_canonical_json_schema_export() -> None:
    """Catches runtime-only plan/execution/report contracts hidden from consumers."""

    from ntruth.schemas.kernel import kernel_json_schemas

    assert {
        "planned_design_record",
        "executed_design_record",
        "plan_execution_reconciliation",
        "report_bundle",
    } <= kernel_json_schemas().keys()
