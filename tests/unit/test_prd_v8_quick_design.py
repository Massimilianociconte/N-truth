"""TDD regressions for the PRD v8 Quick Design prospective lane."""

from __future__ import annotations

from inspect import Parameter, signature

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture

from ntruth.derivation_theory.loader import load_canonical_bundle
from ntruth.quick_design import (
    QuickDesignV7Answers,
    freeze_v7_plan,
    run_quick_design_v7_session,
)
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CanonicalCountRegistry,
    CountLifecyclePhase,
    CountOrigin,
    CountQuantifier,
)
from ntruth.schemas.coverage import ScenarioCoverage, ScenarioCoverageStatus
from ntruth.schemas.events import RelativeTiming, TemporalRelation
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.prospective import (
    ProspectiveArtifactKind,
    SupportBindingScope,
    SupportEvidenceBinding,
    build_prospective_artifact,
    build_prospective_input_ledger,
)
from ntruth.schemas.support import (
    EvidenceRecord,
    EvidenceTypeV8,
    SourceClassRef,
    SourceContext,
    SourceRecord,
)


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


def _evidence_refs(value: object) -> set[str]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        result: set[str] = set()
        for key, item in value.items():
            if key in {"evidence_ids", "evidence_refs", "source_evidence"} and isinstance(
                item, (tuple, list)
            ):
                result.update(str(entry) for entry in item)
            else:
                result.update(_evidence_refs(item))
        return result
    if isinstance(value, (tuple, list)):
        result = set()
        for item in value:
            result.update(_evidence_refs(item))
        return result
    return set()


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
    planned_count = _planned_count(request)
    request = request.model_copy(
        update={
            "count_registry": CanonicalCountRegistry(
                records=(*request.count_registry.records, planned_count)
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
    support_source = SourceRecord(
        source_id="SOURCE-QD-METADATA-001",
        source_class=next(iter(request.support_by_clause.values())).source_class,
        source_context=SourceContext.PLANNED,
        source_version="sha256:quick-design-support-fixture",
    )
    handoff_text_by_evidence = {
        "EV-HANDOFF-STRUCTURE": "Recorded exposure grouping must remain explicit in handoff.",
        "EV-HANDOFF-QUESTION": "How many exposure clusters will be realized?",
    }
    evidence_records = tuple(
        EvidenceRecord(
            evidence_id=evidence_id,
            source_id=support_source.source_id,
            evidence_type=EvidenceTypeV8.EXPERT_ADJUDICATION,
            locator=f"fixture://{evidence_id}",
            original_text=handoff_text_by_evidence.get(
                evidence_id, f"Reviewed Quick Design evidence {evidence_id}"
            ),
        )
        for evidence_id in sorted(_evidence_refs(request) | set(handoff_text_by_evidence))
    )
    evidence_ids = {record.evidence_id for record in evidence_records}
    support = next(iter(request.support_by_clause.values()))
    clause_bindings = tuple(
        SupportEvidenceBinding(
            scope_kind=SupportBindingScope.THEORY_CLAUSE,
            scope_id=clause_id,
            support=descriptor,
            source_ids=(support_source.source_id,),
            evidence_record_ids=tuple(sorted(evidence_ids)),
        )
        for clause_id, descriptor in request.support_by_clause.items()
    )
    predicate_bindings = tuple(
        SupportEvidenceBinding(
            scope_kind=SupportBindingScope.PREDICATE,
            scope_id=predicate_id,
            support=support,
            source_ids=(support_source.source_id,),
            evidence_record_ids=tuple(value.evidence_ids),
        )
        for predicate_id, value in request.predicate_values.items()
    )
    sample_sheet_csv = (
        "sample_id,factor_level,endpoint_id,lifecycle_status\n"
        "well-1,vehicle,viability,planned\n"
        "well-2,drug,viability,planned\n"
    )
    methods_draft = (
        "Treatment assignment EVT-ASSIGN-001 and exposure EVT-EXPOSURE-001 are "
        "recorded as distinct events."
    )
    id_convention = "BLOCK-RUNTIME-001 / well-{index}"
    artifacts = (
        build_prospective_artifact(
            kind=ProspectiveArtifactKind.SAMPLE_SHEET,
            media_type="text/csv",
            content=sample_sheet_csv,
        ),
        build_prospective_artifact(
            kind=ProspectiveArtifactKind.METHODS_DRAFT,
            media_type="text/markdown",
            content=methods_draft,
        ),
        build_prospective_artifact(
            kind=ProspectiveArtifactKind.ID_CONVENTION,
            media_type="text/plain",
            content=id_convention,
        ),
    )
    ledger = build_prospective_input_ledger(
        request=request,
        sources=(source, support_source),
        evidence_records=evidence_records,
        confirmation_events=(),
        artifacts=artifacts,
        support_bindings=(*clause_bindings, *predicate_bindings),
    )
    submission = module.QuickDesignV8Submission(
        pipeline_request=request,
        input_ledger=ledger,
        planned_event_registry=registry,
        planned_unit_counts=(planned_count,),
        sample_sheet_csv=sample_sheet_csv,
        methods_draft=methods_draft,
        id_convention=id_convention,
        user_confirmation_scopes=("assignment_event", "planned_unit_count"),
        ai_candidates=_not_applicable(query_id, "The prospective wizard used no parser AI."),
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
            items=(
                module.build_handoff_item(
                    category=module.HandoffItemCategory.STRUCTURAL_CONSTRAINT,
                    origin=module.HandoffItemOrigin.VERIFIED_RECORD,
                    authority="EXPERT_ADJUDICATION",
                    evidence_refs=request.predicate_values[
                        next(iter(request.predicate_values))
                    ].evidence_ids,
                    inferential_query_id=query_id,
                    predicate_ids=(next(iter(request.predicate_values)),),
                ),
                module.build_handoff_item(
                    category=module.HandoffItemCategory.UNRESOLVED_QUESTION,
                    origin=module.HandoffItemOrigin.VERIFIED_RECORD,
                    authority="EXPERT_ADJUDICATION",
                    evidence_refs=("EV-HANDOFF-QUESTION",),
                    inferential_query_id=query_id,
                    question_ids=("QUESTION-QD-V8-001",),
                ),
            ),
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


def test_quick_design_v8_revalidates_tampered_submission_before_task4() -> None:
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

    with pytest.raises(ValueError, match="graph does not contain"):
        module.run_quick_design_v8(
            malformed,
            conformance_bundle=load_canonical_bundle(runtime_fixture.REPOSITORY_ROOT),
        )


def test_v7_freeze_adapter_preserves_user_confirmation_scopes() -> None:
    legacy = run_quick_design_v7_session(
        QuickDesignV7Answers(
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
    assert freeze_v7_plan(legacy).user_confirmation_scopes == legacy.user_confirmation_scopes
