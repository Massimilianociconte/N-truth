"""Prospective Quick Design orchestration over the verified PRD v8 pipeline.

This module does not implement an alternate scientific resolver.  The wizard
submission is a structured v8 request; claims and adequacy are produced only by
``run_v8_pipeline`` using an explicitly supplied conformance bundle.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.pipeline_v8 import (
    V8PipelineRequest,
    V8PipelineResult,
    V8PipelineVerificationError,
    run_v8_pipeline,
)
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.count_registry import CanonicalCountKind, CanonicalCountRecord
from ntruth.schemas.events import EventRegistry
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.prospective import (
    PlannedDesignRecord,
    ProspectiveArtifact,
    ProspectiveArtifactKind,
    ProspectiveInputLedger,
    ProspectiveInputScientificReviewRequired,
    build_planned_design,
)
from ntruth.schemas.report_bundle import (
    ConflictRecord,
    HandoffItem,
    HandoffItemCategory,
    HandoffItemOrigin,
    ReportBundle,
    ReportDesignContext,
    ReportDesignRecordContext,
    ReportQuestion,
    StatisticalHandoff,
    build_handoff_item,
    build_report_bundle,
    build_verified_pipeline_context,
)
from ntruth.schemas.support import (
    ConfirmationEvent,
    EvidenceBasis,
    EvidenceTypeV8,
    SensitivityRecord,
    SourceContext,
)

QuickDesignScientificReviewRequired = ProspectiveInputScientificReviewRequired

RAW_WIZARD_AUTHORITY = AuthorityType.USER_CONFIRMATION
RAW_WIZARD_EVIDENCE_BASES = frozenset({EvidenceBasis.SELF_REPORT, EvidenceBasis.AUTHOR_ASSERTED})
RAW_WIZARD_SUPPORT_GRADES = frozenset(
    {"SELF_REPORT_ONLY", "ASSERTION_ONLY", "DOCUMENT_ASSERTION_ONLY"}
)
RAW_WIZARD_EVIDENCE_TYPES = frozenset(
    {EvidenceTypeV8.AUTHOR_ASSERTION, EvidenceTypeV8.USER_CONFIRMATION}
)


class QuickDesignV8Submission(KernelModel):
    pipeline_request: V8PipelineRequest
    input_ledger: ProspectiveInputLedger
    planned_event_registry: EventRegistry
    planned_unit_counts: tuple[CanonicalCountRecord, ...] = Field(min_length=1)
    sample_sheet_csv: Annotated[str, Field(min_length=1)]
    methods_draft: Annotated[str, Field(min_length=1)]
    id_convention: Annotated[str, Field(min_length=1)]
    user_confirmation_scopes: tuple[NonBlankStr, ...] = Field(min_length=1)
    ai_candidates: KnowledgeValue[tuple[ParserCandidateOutput, ...]]
    conflicts: KnowledgeValue[tuple[ConflictRecord, ...]]
    sensitivities: KnowledgeValue[tuple[SensitivityRecord, ...]]
    questions: tuple[ReportQuestion, ...] = Field(min_length=1)
    statistical_handoff: StatisticalHandoff
    inference_limits: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _prospective_scope(self) -> QuickDesignV8Submission:
        query_id = self.pipeline_request.query.id
        checked_ledger = ProspectiveInputLedger.model_validate(
            self.input_ledger.model_dump(mode="python")
        )
        if checked_ledger.request != self.pipeline_request:
            raise ValueError("Quick Design input ledger does not pin the pipeline request")
        if any(
            source.source_context is not SourceContext.PLANNED for source in checked_ledger.sources
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
        planned_scope_identities: set[tuple[object, ...]] = set()
        for count in self.planned_unit_counts:
            identity = count.semantic_identity()
            if identity is None:
                raise QuickDesignScientificReviewRequired(
                    "planned_unit_count has an unresolved full semantic scope"
                )
            if identity in planned_scope_identities:
                raise ValueError("duplicate planned_unit_count full semantic scope")
            planned_scope_identities.add(identity)
        registry_by_id = {
            count.count_id: count for count in self.pipeline_request.count_registry.records
        }
        if any(registry_by_id.get(count.count_id) != count for count in self.planned_unit_counts):
            raise ValueError(
                "planned_unit_counts must be exact records in the pipeline count registry"
            )
        if any(question.inferential_query_id != query_id for question in self.questions):
            raise ValueError("Quick Design questions must share the request query")
        if len(set(self.user_confirmation_scopes)) != len(self.user_confirmation_scopes):
            raise ValueError("user_confirmation_scopes contains duplicates")
        if any(
            event.scope_id not in self.user_confirmation_scopes
            for event in checked_ledger.confirmation_events
        ):
            raise ValueError("confirmation scope is not frozen in user_confirmation_scopes")
        artifacts_by_kind = {artifact.kind: artifact for artifact in checked_ledger.artifacts}
        expected_contents = {
            ProspectiveArtifactKind.SAMPLE_SHEET: self.sample_sheet_csv,
            ProspectiveArtifactKind.METHODS_DRAFT: self.methods_draft,
            ProspectiveArtifactKind.ID_CONVENTION: self.id_convention,
        }
        if any(
            artifacts_by_kind[kind].content != content
            for kind, content in expected_contents.items()
        ):
            raise ValueError("Quick Design artifact content differs from the input ledger")
        return self


class QuickDesignV8Result(KernelModel):
    planned_design: PlannedDesignRecord
    pipeline_result: V8PipelineResult
    report_bundle: ReportBundle
    artifacts: tuple[ProspectiveArtifact, ...] = Field(min_length=3)


def validate_raw_wizard_submission(submission: QuickDesignV8Submission) -> None:
    """Reject authority claims that a raw API caller cannot independently establish."""

    submission = QuickDesignV8Submission.model_validate(submission.model_dump(mode="python"))
    descriptors = (
        *submission.pipeline_request.support_by_clause.values(),
        *(binding.support for binding in submission.input_ledger.support_bindings),
        *(event.support for event in submission.input_ledger.confirmation_events),
    )
    if any(
        descriptor.authority_type is not RAW_WIZARD_AUTHORITY
        or descriptor.evidence_basis not in RAW_WIZARD_EVIDENCE_BASES
        or descriptor.support_grade.token not in RAW_WIZARD_SUPPORT_GRADES
        for descriptor in descriptors
    ):
        raise ValueError(
            "raw Quick Design wizard authority and support grade are limited to user "
            "self-report/assertion; "
            "expert, adjudicated and system authority require an independently verified "
            "append-only authority envelope outside this endpoint"
        )
    if any(
        record.evidence_type not in RAW_WIZARD_EVIDENCE_TYPES
        for record in submission.input_ledger.evidence_records
    ):
        raise ValueError(
            "raw Quick Design evidence is limited to author assertion/user confirmation; "
            "expert or adjudicated evidence requires an independently verified envelope"
        )
    if any(
        item.authority is not RAW_WIZARD_AUTHORITY for item in submission.statistical_handoff.items
    ):
        raise ValueError("raw Quick Design handoff items must retain user authority")


def run_quick_design_v8(
    submission: QuickDesignV8Submission,
    *,
    conformance_bundle: ConformanceBundle,
) -> QuickDesignV8Result:
    """Freeze the plan, execute the canonical v8 lane and emit a neutral report."""

    submission = QuickDesignV8Submission.model_validate(submission.model_dump(mode="python"))
    request = submission.pipeline_request
    if not request.scenario_coverages:
        raise ValueError("Quick Design v8 requires explicit ScenarioCoverage")

    planned_design = build_planned_design(
        experiment_block_id=request.experiment_block_id,
        inferential_queries=(request.query,),
        sources=submission.input_ledger.sources,
        evidence_records=submission.input_ledger.evidence_records,
        confirmation_events=submission.input_ledger.confirmation_events,
        event_registry=submission.planned_event_registry,
        count_records=submission.planned_unit_counts,
        sample_sheet_ref=next(
            artifact.artifact_id
            for artifact in submission.input_ledger.artifacts
            if artifact.kind is ProspectiveArtifactKind.SAMPLE_SHEET
        ),
        methods_draft_ref=next(
            artifact.artifact_id
            for artifact in submission.input_ledger.artifacts
            if artifact.kind is ProspectiveArtifactKind.METHODS_DRAFT
        ),
        id_convention_ref=next(
            artifact.artifact_id
            for artifact in submission.input_ledger.artifacts
            if artifact.kind is ProspectiveArtifactKind.ID_CONVENTION
        ),
        user_confirmation_scopes=submission.user_confirmation_scopes,
    )
    pipeline_result = run_v8_pipeline(
        request,
        conformance_bundle=conformance_bundle,
    )
    verified_context = build_verified_pipeline_context(
        request=request,
        result=pipeline_result,
        conformance_bundle=conformance_bundle,
    )
    query_id = request.query.id
    evidence_ids = tuple(record.evidence_id for record in submission.input_ledger.evidence_records)
    design_context = ReportDesignRecordContext(
        mode=ReportDesignContext.PLANNED,
        planned_design_record=KnowledgeValue[PlannedDesignRecord](
            knowledge_state=KnowledgeState.PRESENT,
            value=planned_design,
            evidence_ids=evidence_ids,
            query_scope_id=query_id,
        ),
        executed_design_record=KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="The experiment has not entered the executed-design lane.",
            query_scope_id=query_id,
        ),
        reconciliation_record=KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="Plan/execution reconciliation requires an executed design.",
            query_scope_id=query_id,
        ),
        retrospective_source_ids=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="Quick Design is a prospective plan, not a retrospective reconstruction.",
            query_scope_id=query_id,
        ),
    )
    ledger_state = KnowledgeValue[tuple[ProspectiveInputLedger, ...]](
        knowledge_state=KnowledgeState.PRESENT,
        value=(submission.input_ledger,),
        evidence_ids=evidence_ids,
        query_scope_id=query_id,
    )
    if submission.input_ledger.confirmation_events:
        confirmation_state = KnowledgeValue[tuple[ConfirmationEvent, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=submission.input_ledger.confirmation_events,
            evidence_ids=tuple(
                dict.fromkeys(
                    ref
                    for event in submission.input_ledger.confirmation_events
                    for ref in event.evidence_refs
                )
            ),
            query_scope_id=query_id,
        )
    else:
        confirmation_state = KnowledgeValue[tuple[ConfirmationEvent, ...]](
            knowledge_state=KnowledgeState.NOT_REPORTED,
            source_scope_ids=tuple(source.source_id for source in submission.input_ledger.sources),
            query_scope_id=query_id,
        )
    report_bundle = build_report_bundle(
        verified_pipeline_contexts=(verified_context,),
        design_record_context=design_context,
        prospective_input_ledgers=ledger_state,
        source_records=submission.input_ledger.sources,
        evidence_records=submission.input_ledger.evidence_records,
        ai_candidates=submission.ai_candidates,
        human_confirmations=confirmation_state,
        conflicts=submission.conflicts,
        sensitivities=submission.sensitivities,
        questions=submission.questions,
        statistical_handoff=submission.statistical_handoff,
        inference_limits=submission.inference_limits,
    )
    return QuickDesignV8Result(
        planned_design=planned_design,
        pipeline_result=pipeline_result,
        report_bundle=report_bundle,
        artifacts=submission.input_ledger.artifacts,
    )


__all__ = [
    "HandoffItem",
    "HandoffItemCategory",
    "HandoffItemOrigin",
    "QuickDesignScientificReviewRequired",
    "QuickDesignV8Result",
    "QuickDesignV8Submission",
    "ReportQuestion",
    "StatisticalHandoff",
    "V8PipelineVerificationError",
    "build_handoff_item",
    "run_quick_design_v8",
    "validate_raw_wizard_submission",
]
