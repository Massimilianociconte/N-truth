"""Prospective Quick Design orchestration over the verified PRD v8 pipeline.

This module does not implement an alternate scientific resolver.  The wizard
submission is a structured v8 request; claims and adequacy are produced only by
``run_v8_pipeline`` using an explicitly supplied conformance bundle.
"""

from __future__ import annotations

from pydantic import Field, JsonValue, model_validator

from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.pipeline_v8 import (
    V8PipelineRequest,
    V8PipelineResult,
    V8PipelineVerificationError,
    run_v8_pipeline,
)
from ntruth.schemas.core import content_checksum
from ntruth.schemas.count_registry import CanonicalCountKind, CanonicalCountRecord
from ntruth.schemas.events import EventRegistry
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.prospective import PlannedDesignRecord, build_planned_design
from ntruth.schemas.report_bundle import (
    ReportBundle,
    ReportDesignContext,
    ReportDesignRecordContext,
    ReportQuestion,
    StatisticalHandoff,
    build_report_bundle,
)
from ntruth.schemas.support import ConfirmationEvent, SensitivityRecord, SourceContext, SourceRecord


class QuickDesignV8Submission(KernelModel):
    pipeline_request: V8PipelineRequest
    planned_sources: tuple[SourceRecord, ...] = Field(min_length=1)
    planned_event_registry: EventRegistry
    planned_unit_counts: tuple[CanonicalCountRecord, ...] = Field(min_length=1)
    sample_sheet_csv: NonBlankStr
    methods_draft: NonBlankStr
    id_convention: NonBlankStr
    user_confirmation_scopes: tuple[NonBlankStr, ...] = Field(min_length=1)
    ai_candidates: KnowledgeValue[tuple[JsonValue, ...]]
    human_confirmations: KnowledgeValue[tuple[ConfirmationEvent, ...]]
    conflicts: KnowledgeValue[tuple[dict[str, JsonValue], ...]]
    sensitivities: KnowledgeValue[tuple[SensitivityRecord, ...]]
    questions: tuple[ReportQuestion, ...] = Field(min_length=1)
    statistical_handoff: StatisticalHandoff
    inference_limits: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _prospective_scope(self) -> QuickDesignV8Submission:
        query_id = self.pipeline_request.query.id
        if any(
            source.source_context is not SourceContext.PLANNED for source in self.planned_sources
        ):
            raise ValueError("Quick Design v8 accepts only planned source context")
        if self.planned_event_registry != self.pipeline_request.causal_aggregate.event_registry:
            raise ValueError("planned events must be the exact events verified by the v8 request")
        if not self.planned_event_registry.relative_timings:
            raise ValueError("Quick Design v8 requires event-referenced timing, including UNKNOWN")
        if any(
            count.kind is not CanonicalCountKind.PLANNED_UNIT_COUNT
            or count.scope.query_id != query_id
            for count in self.planned_unit_counts
        ):
            raise ValueError("planned counts must be query-scoped planned_unit_count records")
        if len(self.planned_unit_counts) != 1:
            raise ValueError("Quick Design v8 requires exactly one planned_unit_count per query")
        if any(question.inferential_query_id != query_id for question in self.questions):
            raise ValueError("Quick Design questions must share the request query")
        if len(set(self.user_confirmation_scopes)) != len(self.user_confirmation_scopes):
            raise ValueError("user_confirmation_scopes contains duplicates")
        return self


class QuickDesignV8Result(KernelModel):
    planned_design: PlannedDesignRecord
    pipeline_result: V8PipelineResult
    report_bundle: ReportBundle
    sample_sheet_csv: NonBlankStr
    methods_draft: NonBlankStr
    id_convention: NonBlankStr


def _present_reference(
    value: str,
    *,
    evidence_ids: tuple[str, ...],
    query_id: str,
) -> KnowledgeValue[str]:
    return KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=evidence_ids,
        query_scope_id=query_id,
    )


def _not_applicable_reference(rationale: str, *, query_id: str) -> KnowledgeValue[str]:
    return KnowledgeValue[str](
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale=rationale,
        query_scope_id=query_id,
    )


def run_quick_design_v8(
    submission: QuickDesignV8Submission,
    *,
    conformance_bundle: ConformanceBundle,
) -> QuickDesignV8Result:
    """Freeze the plan, execute the canonical v8 lane and emit a neutral report."""

    request = submission.pipeline_request
    if not request.scenario_coverages:
        raise ValueError("Quick Design v8 requires explicit ScenarioCoverage")

    planned_design = build_planned_design(
        experiment_block_id=request.experiment_block_id,
        inferential_query_ids=(request.query.id,),
        sources=submission.planned_sources,
        event_registry=submission.planned_event_registry,
        count_records=submission.planned_unit_counts,
        sample_sheet_ref=f"artifact://sha256/{content_checksum(submission.sample_sheet_csv)}",
        methods_draft_ref=f"artifact://sha256/{content_checksum(submission.methods_draft)}",
        user_confirmation_scopes=submission.user_confirmation_scopes,
    )
    pipeline_result = run_v8_pipeline(
        request,
        conformance_bundle=conformance_bundle,
    )
    query_id = request.query.id
    source_ids = tuple(source.source_id for source in submission.planned_sources)
    design_context = ReportDesignRecordContext(
        mode=ReportDesignContext.PLANNED,
        planned_design_id=_present_reference(
            planned_design.plan_id,
            evidence_ids=source_ids,
            query_id=query_id,
        ),
        executed_design_id=_not_applicable_reference(
            "The experiment has not entered the executed-design lane.",
            query_id=query_id,
        ),
        reconciliation_id=_not_applicable_reference(
            "Plan/execution reconciliation requires an executed design.",
            query_id=query_id,
        ),
        retrospective_source_ids=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="Quick Design is a prospective plan, not a retrospective reconstruction.",
            query_scope_id=query_id,
        ),
    )
    report_bundle = build_report_bundle(
        design_record_context=design_context,
        source_records=submission.planned_sources,
        ai_candidates=submission.ai_candidates,
        human_confirmations=submission.human_confirmations,
        conflicts=submission.conflicts,
        confirmed_graph=request.graph,
        claim_sets=(pipeline_result.claim_set,),
        report_resolution=pipeline_result.report_resolution,
        design_adequacy_evaluations=pipeline_result.design_adequacy_evaluations,
        count_records=(*submission.planned_unit_counts, *request.count_registry.records),
        scenario_coverages=pipeline_result.scenario_coverages,
        sensitivities=submission.sensitivities,
        questions=submission.questions,
        statistical_handoff=submission.statistical_handoff,
        profile_coverage=pipeline_result.profile_coverage,
        inference_limits=submission.inference_limits,
        execution_manifest=pipeline_result.execution_manifest,
    )
    return QuickDesignV8Result(
        planned_design=planned_design,
        pipeline_result=pipeline_result,
        report_bundle=report_bundle,
        sample_sheet_csv=submission.sample_sheet_csv,
        methods_draft=submission.methods_draft,
        id_convention=submission.id_convention,
    )


__all__ = [
    "QuickDesignV8Result",
    "QuickDesignV8Submission",
    "ReportQuestion",
    "StatisticalHandoff",
    "V8PipelineVerificationError",
    "run_quick_design_v8",
]
