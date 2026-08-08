"""TDD regressions for the PRD v8 Quick Design prospective lane."""

from __future__ import annotations

from inspect import Parameter, signature

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture

from ntruth.derivation_theory.loader import load_canonical_bundle
from ntruth.quick_design import QuickDesignAnswers, freeze_plan, run_quick_design_session
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CountLifecyclePhase,
    CountOrigin,
    CountQuantifier,
)
from ntruth.schemas.coverage import ScenarioCoverage, ScenarioCoverageStatus
from ntruth.schemas.events import RelativeTiming, TemporalRelation
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import SourceClassRef, SourceContext, SourceRecord


def _non_exhaustive() -> ScenarioCoverage:
    return ScenarioCoverage(
        status=ScenarioCoverageStatus.NON_EXHAUSTIVE,
        profile_id=runtime_fixture.PROFILE_ID,
        theory_version=runtime_fixture.CANONICAL_BUNDLE.theory.theory_version,
        emitting_clause_ids=("DT-E-INTERFERENCE-ESTIMAND",),
        omitted_dimensions=runtime_fixture._present(("unreviewed_interference_topology",)),
        caveat=runtime_fixture._present("Additional exposure topologies may exist."),
    )


def _planned_count(request: object) -> CanonicalCountRecord:
    scope = runtime_fixture._count_scope(unit_type="well").model_copy(
        update={
            "lifecycle_phase": runtime_fixture._present(CountLifecyclePhase.PLANNED),
        }
    )
    return CanonicalCountRecord(
        count_id="COUNT-PLANNED-QD-V8-001",
        kind=CanonicalCountKind.PLANNED_UNIT_COUNT,
        value=runtime_fixture._present(4),
        quantifier=CountQuantifier.EXACT,
        scope=scope,
        source_evidence=("EV-QD-PLAN-001",),
        origin=CountOrigin.SOURCE_DECLARATION,
    )


def _not_applicable(query_id: str, rationale: str) -> KnowledgeValue[object]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale=rationale,
        query_scope_id=query_id,
    )


def _submission(*, include_coverage: bool = True) -> tuple[object, object]:
    module = __import__("ntruth.quick_design.v8", fromlist=["QuickDesignV8Submission"])
    coverages = (_non_exhaustive(),) if include_coverage else ()
    _, request = runtime_fixture._request(scenario_coverages=coverages)
    registry = request.causal_aggregate.event_registry.model_copy(
        update={
            "relative_timings": (
                RelativeTiming(
                    subject_event_id="EVT-ASSIGN-001",
                    reference_event_id="EVT-APPLY-001",
                    relation=TemporalRelation.UNKNOWN,
                    rationale=(
                        "The plan has not yet established assignment timing relative to "
                        "application."
                    ),
                ),
            )
        }
    )
    request = request.model_copy(
        update={
            "causal_aggregate": request.causal_aggregate.model_copy(
                update={"event_registry": registry}
            )
        }
    )
    query_id = request.query.id
    source = SourceRecord(
        source_id="SOURCE-QD-PLAN-001",
        source_class=SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="sample_sheet",
        ),
        source_context=SourceContext.PLANNED,
        source_version="sha256:quick-design-plan-fixture",
    )
    submission = module.QuickDesignV8Submission(
        pipeline_request=request,
        planned_sources=(source,),
        planned_event_registry=registry,
        planned_unit_counts=(_planned_count(request),),
        sample_sheet_csv=(
            "sample_id,factor_level,endpoint_id,lifecycle_status\n"
            "well-1,vehicle,viability,planned\n"
            "well-2,drug,viability,planned\n"
        ),
        methods_draft=(
            "Treatment assignment EVT-ASSIGN-001 and exposure EVT-EXPOSURE-001 are "
            "recorded as distinct events."
        ),
        id_convention="BLOCK-RUNTIME-001 / well-{index}",
        user_confirmation_scopes=("assignment_event", "planned_unit_count"),
        ai_candidates=_not_applicable(query_id, "The prospective wizard used no parser AI."),
        human_confirmations=_not_applicable(
            query_id, "No separate confirmation event is present in this fixture."
        ),
        conflicts=_not_applicable(query_id, "No conflict is present in this fixture."),
        sensitivities=_not_applicable(query_id, "No self-report sensitivity in this fixture."),
        questions=(
            module.ReportQuestion(
                question_id="QUESTION-QD-V8-001",
                inferential_query_id=query_id,
                text="Could shared exposure alter treatment realization?",
                evidence_required=("execution_log", "exposure_event"),
                primary=True,
            ),
        ),
        statistical_handoff=module.StatisticalHandoff(
            structural_requirements=("Preserve the exposure grouping in handoff.",),
            unresolved_questions=("How many exposure clusters will be realized?",),
        ),
        inference_limits=("This is a planned design, not an executed experiment.",),
    )
    return module, submission


def test_quick_design_v8_requires_explicit_conformance_bundle() -> None:
    module, _ = _submission()

    assert signature(module.run_quick_design_v8).parameters["conformance_bundle"].default is (
        Parameter.empty
    )


def test_quick_design_v8_runs_only_through_verified_pipeline_and_freezes_plan() -> None:
    module, submission = _submission()
    result = module.run_quick_design_v8(
        submission,
        conformance_bundle=load_canonical_bundle(runtime_fixture.REPOSITORY_ROOT),
    )

    assert result.planned_design.plan_id.startswith("PLAN-")
    assert result.planned_design.user_confirmation_scopes == (
        "assignment_event",
        "planned_unit_count",
    )
    assert result.pipeline_result.execution_manifest == result.report_bundle.execution_manifest
    assert result.pipeline_result.claim_set == result.report_bundle.claim_sets[0]
    assert result.report_bundle.design_record_context.mode.value == "PLANNED"
    assert result.report_bundle.strategy_module_status.value == "HANDOFF_ONLY"
    assert result.report_bundle.scenario_coverages[0].status is (
        ScenarioCoverageStatus.NON_EXHAUSTIVE
    )
    assert any(
        count.kind is CanonicalCountKind.PLANNED_UNIT_COUNT
        for count in result.report_bundle.count_records
    )
    assert not hasattr(result, "determinability")


def test_quick_design_v8_fails_closed_without_scenario_coverage() -> None:
    module, submission = _submission(include_coverage=False)

    with pytest.raises(ValueError, match="ScenarioCoverage"):
        module.run_quick_design_v8(
            submission,
            conformance_bundle=load_canonical_bundle(runtime_fixture.REPOSITORY_ROOT),
        )


def test_quick_design_v8_propagates_task4_verifier_failure() -> None:
    module, submission = _submission()
    request = submission.pipeline_request
    malformed_graph = request.graph.model_copy(
        update={
            "nodes": tuple(node for node in request.graph.nodes if node.node_id != request.query.id)
        }
    )
    malformed = submission.model_copy(
        update={"pipeline_request": request.model_copy(update={"graph": malformed_graph})}
    )

    with pytest.raises(module.V8PipelineVerificationError):
        module.run_quick_design_v8(
            malformed,
            conformance_bundle=load_canonical_bundle(runtime_fixture.REPOSITORY_ROOT),
        )


def test_v7_freeze_adapter_preserves_user_confirmation_scopes() -> None:
    legacy = run_quick_design_session(
        QuickDesignAnswers(
            source_description="cells",
            allocation_level="well",
            independently_assigned="TRUE",
            assignment_confirmation_event_id="CONF-ASSIGN-001",
            interference_status="POSSIBLE",
            planned_units_per_level=2,
            planned_unit_type="well",
        )
    )

    assert legacy.user_confirmation_scopes
    assert freeze_plan(legacy).user_confirmation_scopes == legacy.user_confirmation_scopes
