"""Deterministic guided-input builder for the canonical PRD v8 Quick Design lane.

The builder records only reviewed user declarations.  It deliberately leaves
scientific consequences such as experimental-unit identity, independence,
interference and design adequacy unresolved for the verified Theory pipeline.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.derivation_theory.runtime import load_runtime_bundle
from ntruth.pipeline_v8 import V8PipelineRequest
from ntruth.quick_design.v8 import (
    QuickDesignScientificReviewRequired,
    QuickDesignV8Result,
    QuickDesignV8Submission,
    run_quick_design_v8,
    validate_raw_wizard_submission,
)
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.causal_context import (
    InterferenceStatus,
    QueryCausalContext,
    QueryCausalEventAggregate,
)
from ntruth.schemas.core import content_checksum, stable_id
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CanonicalCountRegistry,
    CountLifecyclePhase,
    CountOrigin,
    CountQuantifier,
    CountScope,
)
from ntruth.schemas.coverage import (
    PROFILE_COVERAGE_REVIEW_ISSUE_ID,
    ProfileCoverageStatement,
    ScenarioCoverage,
    ScenarioCoverageStatus,
)
from ntruth.schemas.events import (
    ApplicationEvent,
    AssignmentEvent,
    EventRegistry,
    ExposureEvent,
    RelativeTiming,
    TemporalRelation,
)
from ntruth.schemas.graph_v8 import V8ExperimentGraph, V8GraphNode, V8GraphNodeType
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.prospective import (
    ConfirmationRelationKind,
    ConfirmationTarget,
    ProspectiveArtifact,
    ProspectiveArtifactKind,
    SupportBindingScope,
    SupportEvidenceBinding,
    build_prospective_artifact,
    build_prospective_input_ledger,
)
from ntruth.schemas.query import InferentialQuery
from ntruth.schemas.report_bundle import (
    HandoffItemCategory,
    HandoffItemOrigin,
    ReportQuestion,
    StatisticalHandoff,
    build_handoff_item,
)
from ntruth.schemas.support import (
    SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
    ConfirmationEvent,
    EvidenceBasis,
    EvidenceRecord,
    EvidenceTypeV8,
    ScientificReviewRequirement,
    SourceClassRef,
    SourceContext,
    SourceRecord,
    SupportDescriptor,
    SupportGrade,
)


class GuidedAnswerStatus(StrEnum):
    PROVIDED = "PROVIDED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class GuidedBuildAction(StrEnum):
    PREVIEW = "PREVIEW"
    CONFIRM = "CONFIRM"


class GuidedBuildState(StrEnum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BUILT = "BUILT"


class GuidedInterferenceStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    POSSIBLE = "POSSIBLE"


class GuidedTextAnswer(KernelModel):
    """One user answer whose missing state is explicit and reasoned."""

    status: GuidedAnswerStatus
    value: NonBlankStr | None = None
    rationale: NonBlankStr | None = None

    @model_validator(mode="after")
    def _status_contract(self) -> Self:
        if self.status is GuidedAnswerStatus.PROVIDED:
            if self.value is None or self.rationale is not None:
                raise ValueError("PROVIDED guided answers require value and no missing rationale")
        elif self.value is not None or self.rationale is None:
            raise ValueError("NOT_AVAILABLE guided answers require rationale and no value")
        return self


class GuidedTimingAnswer(KernelModel):
    status: GuidedAnswerStatus
    relation: TemporalRelation | None = None
    rationale: NonBlankStr | None = None

    @model_validator(mode="after")
    def _status_contract(self) -> Self:
        if self.status is GuidedAnswerStatus.PROVIDED:
            if self.relation is None or self.relation is TemporalRelation.UNKNOWN:
                raise ValueError("PROVIDED timing requires an event-relative relation")
            if self.rationale is not None:
                raise ValueError("PROVIDED timing does not use a missing rationale")
        elif self.relation is not None or self.rationale is None:
            raise ValueError("NOT_AVAILABLE timing requires rationale and no relation")
        return self


class GuidedIdSetAnswer(KernelModel):
    """One explicitly reviewed unit-ID set for exactly one causal axis."""

    status: GuidedAnswerStatus
    values: tuple[NonBlankStr, ...] = ()
    rationale: NonBlankStr | None = None

    @model_validator(mode="after")
    def _status_contract(self) -> Self:
        if self.status is GuidedAnswerStatus.PROVIDED:
            if not self.values or self.rationale is not None:
                raise ValueError("PROVIDED unit IDs require values and no missing rationale")
            if len(set(self.values)) != len(self.values):
                raise ValueError("provided unit IDs must be unique")
        elif self.values or self.rationale is None:
            raise ValueError("NOT_AVAILABLE unit IDs require rationale and no values")
        return self


class GuidedInterferenceAnswer(KernelModel):
    """User-reviewed status only; it never selects an experimental unit."""

    status: GuidedInterferenceStatus
    rationale: NonBlankStr


class GuidedPlannedGroup(KernelModel):
    group_id: NonBlankStr
    factor_level: NonBlankStr
    planned_count: int = Field(strict=True, ge=1)


class GuidedQuickDesignDraft(KernelModel):
    template_id: Literal["simple_cell_culture"] = "simple_cell_culture"
    block_title: NonBlankStr
    source_description: GuidedTextAnswer
    preparation_description: GuidedTextAnswer
    biological_source_unit_type: GuidedTextAnswer
    candidate_unit_type: GuidedTextAnswer
    factor_id: NonBlankStr
    factor_levels: tuple[NonBlankStr, ...] = Field(min_length=2)
    contrast_id: NonBlankStr
    endpoint_id: NonBlankStr
    timepoint_id: NonBlankStr
    estimand: NonBlankStr
    population_scope: NonBlankStr
    inference_level: NonBlankStr
    assignment_unit_type: GuidedTextAnswer
    assignment_unit_ids: GuidedIdSetAnswer
    application_unit_type: GuidedTextAnswer
    application_unit_ids: GuidedIdSetAnswer
    intervention_id: GuidedTextAnswer
    effective_exposure_unit_type: GuidedTextAnswer
    exposed_unit_ids: GuidedIdSetAnswer
    exposure_pathway: GuidedTextAnswer
    exposure_container: GuidedTextAnswer
    interference: GuidedInterferenceAnswer
    assignment_to_application_timing: GuidedTimingAnswer
    planned_unit_type: GuidedTextAnswer
    planned_groups: tuple[GuidedPlannedGroup, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _planned_query_scope(self) -> Self:
        normalized_levels = tuple(item.casefold() for item in self.factor_levels)
        if len(normalized_levels) != len(set(normalized_levels)):
            raise ValueError("factor_levels must be distinct")
        group_ids = tuple(group.group_id for group in self.planned_groups)
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("planned group IDs must be unique")
        group_levels = tuple(group.factor_level.casefold() for group in self.planned_groups)
        if len(group_levels) != len(set(group_levels)) or set(group_levels) != set(
            normalized_levels
        ):
            raise ValueError("planned groups must map one-to-one to the declared factor levels")
        return self


class GuidedQuickDesignConfirmation(KernelModel):
    preview_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_predicate_id: NonBlankStr
    actor_role: NonBlankStr
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("confirmed_at requires a timezone offset")
        return value


class GuidedQuickDesignBuildRequest(KernelModel):
    action: GuidedBuildAction
    draft: GuidedQuickDesignDraft
    confirmation: GuidedQuickDesignConfirmation | None = None

    @model_validator(mode="after")
    def _action_contract(self) -> Self:
        if self.action is GuidedBuildAction.PREVIEW and self.confirmation is not None:
            raise ValueError("PREVIEW cannot carry a confirmation")
        if self.action is GuidedBuildAction.CONFIRM and self.confirmation is None:
            raise ValueError("CONFIRM requires the reviewed preview confirmation")
        return self


class GuidedTheoryQuestion(KernelModel):
    question_id: NonBlankStr
    predicate_id: NonBlankStr
    theory_clause_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    required_predicate_rationales: tuple[NonBlankStr, ...] = Field(min_length=1)
    known_gap_rationales: tuple[NonBlankStr, ...] = ()
    text: NonBlankStr
    evidence_required: tuple[NonBlankStr, ...] = Field(min_length=1)


class GuidedQuickDesignSummary(KernelModel):
    experiment_block_id: NonBlankStr
    inferential_query_id: NonBlankStr
    provided_field_ids: tuple[NonBlankStr, ...]
    unknown_field_ids: tuple[NonBlankStr, ...]
    planned_group_count: int = Field(ge=2)
    planned_unit_total: int = Field(ge=2)
    scenario_coverage_status: Literal["NON_EXHAUSTIVE"] = "NON_EXHAUSTIVE"
    strategy_module_status: Literal["HANDOFF_ONLY"] = "HANDOFF_ONLY"


class GuidedQuickDesignBuildResponse(KernelModel):
    contract_code: Literal["NTRUTH_QUICK_DESIGN_GUIDED_V8"] = "NTRUTH_QUICK_DESIGN_GUIDED_V8"
    contract_version: Literal["8.0.0"] = "8.0.0"
    action: GuidedBuildAction
    state: GuidedBuildState
    next_endpoint: Literal["/v8/quick-design"] = "/v8/quick-design"
    preview_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: GuidedQuickDesignSummary
    visible_questions: tuple[GuidedTheoryQuestion, ...] = Field(max_length=3)
    question_queue: tuple[GuidedTheoryQuestion, ...] = Field(min_length=1)
    artifact_previews: tuple[ProspectiveArtifact, ...] = Field(min_length=3, max_length=3)
    submission: KnowledgeValue[QuickDesignV8Submission]

    @model_validator(mode="after")
    def _preview_or_submission(self) -> Self:
        if self.visible_questions != self.question_queue[:3]:
            raise ValueError("visible questions must be the first three retained queue entries")
        state = self.submission.knowledge_state
        if self.action is GuidedBuildAction.PREVIEW:
            if (
                state is not KnowledgeState.UNKNOWN
                or self.state is not GuidedBuildState.REVIEW_REQUIRED
            ):
                raise ValueError("PREVIEW must retain REVIEW_REQUIRED without a submission")
        elif state is not KnowledgeState.PRESENT or self.state is not GuidedBuildState.BUILT:
            raise ValueError("CONFIRM must emit a BUILT reviewed canonical submission")
        return self


def _answer_knowledge(
    answer: GuidedTextAnswer,
    *,
    field_name: str,
    evidence_id: str,
    query_id: str,
) -> KnowledgeValue[Any]:
    if answer.status is GuidedAnswerStatus.PROVIDED:
        return KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=answer.value,
            evidence_ids=(evidence_id,),
            query_scope_id=query_id,
        )
    return KnowledgeValue(
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=f"{field_name}: {answer.rationale}",
        evidence_ids=(evidence_id,),
        query_scope_id=query_id,
    )


def _id_set_knowledge(
    answer: GuidedIdSetAnswer,
    *,
    field_name: str,
    evidence_id: str,
    query_id: str,
) -> KnowledgeValue[tuple[str, ...]]:
    if answer.status is GuidedAnswerStatus.PROVIDED:
        return KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=answer.values,
            evidence_ids=(evidence_id,),
            query_scope_id=query_id,
        )
    return KnowledgeValue(
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=f"{field_name}: {answer.rationale}",
        evidence_ids=(evidence_id,),
        query_scope_id=query_id,
    )


def _interference_knowledge(
    answer: GuidedInterferenceAnswer,
    *,
    evidence_id: str,
    query_id: str,
) -> KnowledgeValue[InterferenceStatus]:
    if answer.status is GuidedInterferenceStatus.POSSIBLE:
        return KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=InterferenceStatus.POSSIBLE,
            evidence_ids=(evidence_id,),
            query_scope_id=query_id,
        )
    return KnowledgeValue(
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=f"interference_status: {answer.rationale}",
        evidence_ids=(evidence_id,),
        query_scope_id=query_id,
    )


def _present(value: Any, *, evidence_id: str, query_id: str) -> KnowledgeValue[Any]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence_id,),
        query_scope_id=query_id,
    )


def _unknown(field_name: str, *, evidence_id: str, query_id: str) -> KnowledgeValue[Any]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=(
            f"{field_name} was not established by the reviewed guided draft; "
            "the server does not infer it."
        ),
        evidence_ids=(evidence_id,),
        query_scope_id=query_id,
    )


def _not_applicable(
    rationale: str,
    *,
    query_id: str,
) -> KnowledgeValue[Any]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale=rationale,
        query_scope_id=query_id,
    )


def _draft_ids(draft: GuidedQuickDesignDraft) -> tuple[str, str]:
    block_id = stable_id("BLOCK-QD", draft.template_id, draft.block_title)
    query_id = stable_id(
        "IQ-QD",
        block_id,
        draft.factor_id,
        draft.contrast_id,
        draft.endpoint_id,
        draft.timepoint_id,
        draft.estimand,
        draft.population_scope,
        draft.inference_level,
    )
    return block_id, query_id


def _question_queue(
    bundle: ConformanceBundle,
    predicate_values: dict[str, KnowledgeValue[Any]],
) -> tuple[GuidedTheoryQuestion, ...]:
    clause_ids_by_predicate: dict[str, list[str]] = {}
    rationales_by_predicate: dict[str, list[str]] = {}
    known_gap_rationales_by_predicate: dict[str, list[str]] = {}
    for clause in bundle.theory.clauses:
        for requirement in clause.required_predicates:
            clause_ids_by_predicate.setdefault(requirement.predicate_id, []).append(
                clause.clause_id
            )
            rationales_by_predicate.setdefault(requirement.predicate_id, []).append(
                requirement.rationale
            )
            known_gap_rationales_by_predicate.setdefault(requirement.predicate_id, []).extend(
                review.rationale for review in clause.review_requirements
            )
    questions: list[GuidedTheoryQuestion] = []
    for predicate_id in bundle.profile_closure.candidate_predicate_ids:
        value = predicate_values.get(predicate_id)
        if value is None or value.knowledge_state is KnowledgeState.PRESENT:
            continue
        clause_ids = tuple(clause_ids_by_predicate.get(predicate_id, ()))
        if not clause_ids:
            continue
        required_rationales = tuple(dict.fromkeys(rationales_by_predicate[predicate_id]))
        known_gap_rationales = tuple(dict.fromkeys(known_gap_rationales_by_predicate[predicate_id]))
        questions.append(
            GuidedTheoryQuestion(
                question_id=stable_id(
                    "QUESTION-QD",
                    bundle.theory.declared_checksum,
                    predicate_id,
                ),
                predicate_id=predicate_id,
                theory_clause_ids=clause_ids,
                required_predicate_rationales=required_rationales,
                known_gap_rationales=known_gap_rationales,
                text=" ".join(required_rationales),
                evidence_required=required_rationales,
            )
        )
    if not questions:
        raise QuickDesignScientificReviewRequired(
            "the guided profile emitted no unresolved Theory predicate for primary review"
        )
    return tuple(questions)


def _artifact_previews(
    draft: GuidedQuickDesignDraft,
    block_id: str,
) -> tuple[ProspectiveArtifact, ...]:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "sample_id",
            "experiment_block_id",
            "factor_id",
            "factor_level",
            "planned_unit_type",
            "endpoint_id",
            "timepoint_id",
            "lifecycle_status",
        )
    )
    planned_unit = draft.planned_unit_type.value or "UNKNOWN"
    for group in draft.planned_groups:
        for index in range(1, group.planned_count + 1):
            writer.writerow(
                (
                    f"{group.group_id}-{index:03d}",
                    block_id,
                    draft.factor_id,
                    group.factor_level,
                    planned_unit,
                    draft.endpoint_id,
                    draft.timepoint_id,
                    "planned",
                )
            )
    source = draft.source_description.value or f"UNKNOWN ({draft.source_description.rationale})"
    preparation = draft.preparation_description.value or (
        f"UNKNOWN ({draft.preparation_description.rationale})"
    )
    assignment = draft.assignment_unit_type.value or "UNKNOWN"
    application = draft.application_unit_type.value or "UNKNOWN"
    exposure = draft.effective_exposure_unit_type.value or "UNKNOWN"
    assignment_ids = ", ".join(draft.assignment_unit_ids.values) or "UNKNOWN"
    application_ids = ", ".join(draft.application_unit_ids.values) or "UNKNOWN"
    exposed_ids = ", ".join(draft.exposed_unit_ids.values) or "UNKNOWN"
    intervention = draft.intervention_id.value or "UNKNOWN"
    pathway = draft.exposure_pathway.value or "UNKNOWN"
    container = draft.exposure_container.value or "UNKNOWN"
    timing = (
        draft.assignment_to_application_timing.relation.value
        if draft.assignment_to_application_timing.relation is not None
        else "UNKNOWN"
    )
    methods = (
        "# Prospective Methods draft\n\n"
        f"Source/preparation (user reviewed): {source}; {preparation}.\n\n"
        f"Planned factor `{draft.factor_id}` compares "
        f"{', '.join(draft.factor_levels)} for endpoint `{draft.endpoint_id}` at "
        f"`{draft.timepoint_id}`.\n\n"
        f"Assignment unit: {assignment}. Application unit: {application}. "
        f"Effective exposure unit: {exposure}. Assignment relative to application: "
        f"{timing}.\n\n"
        f"Assignment unit IDs: {assignment_ids}. Application unit IDs: {application_ids}. "
        f"Exposed unit IDs: {exposed_ids}.\n\n"
        f"Intervention: {intervention}. Exposure pathway: {pathway}. Exposure container: "
        f"{container}. User-reviewed interference status: {draft.interference.status.value} "
        f"({draft.interference.rationale}).\n\n"
        "Experimental-unit identity, independence, interference consequences and design "
        "adequacy are not inferred by this draft. Counts below are planned counts only.\n"
    )
    convention = f"{block_id} / <group_id>-<three-digit planned index>"
    return (
        build_prospective_artifact(
            kind=ProspectiveArtifactKind.SAMPLE_SHEET,
            media_type="text/csv",
            content=stream.getvalue(),
        ),
        build_prospective_artifact(
            kind=ProspectiveArtifactKind.METHODS_DRAFT,
            media_type="text/markdown",
            content=methods,
        ),
        build_prospective_artifact(
            kind=ProspectiveArtifactKind.ID_CONVENTION,
            media_type="text/plain",
            content=convention,
        ),
    )


def _predicate_preview(
    draft: GuidedQuickDesignDraft,
    *,
    evidence_id: str,
    query_id: str,
    assignment_event_id: str,
) -> dict[str, KnowledgeValue[Any]]:
    values: dict[str, KnowledgeValue[Any]] = {
        "factor": _present(draft.factor_id, evidence_id=evidence_id, query_id=query_id),
        "factor_levels": _present(draft.factor_levels, evidence_id=evidence_id, query_id=query_id),
        "assignment_event_or_equivalent_mechanism": _present(
            assignment_event_id, evidence_id=evidence_id, query_id=query_id
        ),
        "candidate_unit": _answer_knowledge(
            draft.candidate_unit_type,
            field_name="candidate_unit",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
        "relevant_treatment_assignment": _present(
            assignment_event_id, evidence_id=evidence_id, query_id=query_id
        ),
        "inferential_query": _present(query_id, evidence_id=evidence_id, query_id=query_id),
        "contrast_scope": _present(draft.contrast_id, evidence_id=evidence_id, query_id=query_id),
        "lifecycle_phase": _present(
            CountLifecyclePhase.PLANNED.value,
            evidence_id=evidence_id,
            query_id=query_id,
        ),
        "biological_source_unit_type": _answer_knowledge(
            draft.biological_source_unit_type,
            field_name="biological_source_unit_type",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
    }
    unknown_fields = (
        "assignment_separability_support",
        "realized_treatment_application_or_exposure",
        "assignment_separability",
        "realized_exposure_separability",
        "experimental_unit_instances",
        "group_or_paired_set",
        "confirmed_biological_provenance",
        "biological_source_instances",
        "claim_no_interference_dependency",
        "analytical_grouping",
        "repeated_measure_status",
        "measurement_process",
        "source_diversity",
        "protocol_scope",
        "external_replication",
        "exposure_interference",
        "profile_coverage",
        "count_cohort_id",
        "count_condition",
        "biological_source_independence",
    )
    values.update(
        {
            field_name: _unknown(field_name, evidence_id=evidence_id, query_id=query_id)
            for field_name in unknown_fields
        }
    )
    values["interference_status"] = _interference_knowledge(
        draft.interference,
        evidence_id=evidence_id,
        query_id=query_id,
    )
    return values


def _build_preview_parts(
    draft: GuidedQuickDesignDraft,
    bundle: ConformanceBundle,
) -> tuple[
    str,
    str,
    str,
    tuple[ProspectiveArtifact, ...],
    dict[str, KnowledgeValue[Any]],
    tuple[GuidedTheoryQuestion, ...],
    GuidedQuickDesignSummary,
]:
    block_id, query_id = _draft_ids(draft)
    assignment_event_id = stable_id("EVT-ASSIGN-QD", block_id, draft.factor_id)
    preview_evidence_id = stable_id(
        "EV-QD-PREVIEW",
        content_checksum(draft.model_dump(mode="json")),
    )
    predicates = _predicate_preview(
        draft,
        evidence_id=preview_evidence_id,
        query_id=query_id,
        assignment_event_id=assignment_event_id,
    )
    queue = _question_queue(bundle, predicates)
    artifacts = _artifact_previews(draft, block_id)
    provided = tuple(
        sorted(
            predicate_id
            for predicate_id, value in predicates.items()
            if value.knowledge_state is KnowledgeState.PRESENT
        )
    )
    unknown = tuple(
        sorted(
            predicate_id
            for predicate_id, value in predicates.items()
            if value.knowledge_state is KnowledgeState.UNKNOWN
        )
    )
    summary = GuidedQuickDesignSummary(
        experiment_block_id=block_id,
        inferential_query_id=query_id,
        provided_field_ids=provided,
        unknown_field_ids=unknown,
        planned_group_count=len(draft.planned_groups),
        planned_unit_total=sum(group.planned_count for group in draft.planned_groups),
    )
    preview_checksum = content_checksum(
        {
            "draft": draft.model_dump(mode="json"),
            "theory_checksum": bundle.theory.declared_checksum,
            "questions": [question.model_dump(mode="json") for question in queue],
            "artifacts": [artifact.content_checksum for artifact in artifacts],
            "summary": summary.model_dump(mode="json"),
        }
    )
    return (
        preview_checksum,
        block_id,
        query_id,
        artifacts,
        predicates,
        queue,
        summary,
    )


def _count_scope(
    *,
    query: InferentialQuery,
    unit_type: KnowledgeValue[Any],
    group_id: KnowledgeValue[Any],
    cohort_id: KnowledgeValue[Any],
    condition: KnowledgeValue[Any],
    lifecycle_phase: KnowledgeValue[Any],
    evidence_id: str,
) -> CountScope:
    return CountScope(
        query_id=query.id,
        unit_type=unit_type,
        factor_id=_present(query.factor_id, evidence_id=evidence_id, query_id=query.id),
        contrast_id=_present(query.contrast_id, evidence_id=evidence_id, query_id=query.id),
        group_id=group_id,
        endpoint_id=_present(query.endpoint_id, evidence_id=evidence_id, query_id=query.id),
        timepoint_id=query.timepoint_id,
        cohort_id=cohort_id,
        lifecycle_phase=lifecycle_phase,
        population_scope=query.inference_population,
        condition=condition,
    )


def _build_submission(
    *,
    request: GuidedQuickDesignBuildRequest,
    bundle: ConformanceBundle,
    preview_checksum: str,
    block_id: str,
    query_id: str,
    artifact_previews: tuple[ProspectiveArtifact, ...],
    question_queue: tuple[GuidedTheoryQuestion, ...],
) -> QuickDesignV8Submission:
    confirmation = request.confirmation
    if confirmation is None:  # guarded by the request validator
        raise ValueError("CONFIRM requires a confirmation")
    draft = request.draft
    if confirmation.preview_checksum != preview_checksum:
        raise ValueError("preview checksum differs from the recomputed guided draft")
    unresolved_ids = {question.predicate_id for question in question_queue}
    if confirmation.primary_predicate_id not in unresolved_ids:
        raise ValueError("primary predicate must be selected from the retained Theory queue")
    if draft.planned_unit_type.status is not GuidedAnswerStatus.PROVIDED:
        raise QuickDesignScientificReviewRequired(
            "planned_unit_count requires a user-provided unit type and fully resolved scope"
        )

    evidence_id = stable_id("EV-QD-REVIEW", preview_checksum)
    source_id = stable_id("SOURCE-QD-REVIEW", preview_checksum)
    assignment_event_id = stable_id("EVT-ASSIGN-QD", block_id, draft.factor_id)
    application_event_id = stable_id("EVT-APPLY-QD", block_id, draft.factor_id)
    exposure_event_id = stable_id("EVT-EXPOSURE-QD", block_id, draft.factor_id)
    predicates = _predicate_preview(
        draft,
        evidence_id=evidence_id,
        query_id=query_id,
        assignment_event_id=assignment_event_id,
    )
    query = InferentialQuery(
        id=query_id,
        profile_id=bundle.theory.profile_id,
        factor_id=draft.factor_id,
        contrast_id=draft.contrast_id,
        compared_levels=draft.factor_levels,
        endpoint_id=draft.endpoint_id,
        timepoint_id=_present(draft.timepoint_id, evidence_id=evidence_id, query_id=query_id),
        effect_measure_or_estimand=_present(
            draft.estimand, evidence_id=evidence_id, query_id=query_id
        ),
        inference_population=_present(
            draft.population_scope, evidence_id=evidence_id, query_id=query_id
        ),
        inference_level=_present(draft.inference_level, evidence_id=evidence_id, query_id=query_id),
    )
    assignment_unit = _answer_knowledge(
        draft.assignment_unit_type,
        field_name="assignment_unit_type",
        evidence_id=evidence_id,
        query_id=query_id,
    )
    application_unit = _answer_knowledge(
        draft.application_unit_type,
        field_name="application_unit_type",
        evidence_id=evidence_id,
        query_id=query_id,
    )
    exposure_unit = _answer_knowledge(
        draft.effective_exposure_unit_type,
        field_name="effective_exposure_unit_type",
        evidence_id=evidence_id,
        query_id=query_id,
    )
    assignment = AssignmentEvent(
        event_id=assignment_event_id,
        experiment_block_id=block_id,
        evidence_refs=(evidence_id,),
        factor_id=draft.factor_id,
        assigned_unit_type=assignment_unit,
        assigned_unit_ids=_id_set_knowledge(
            draft.assignment_unit_ids,
            field_name="assigned_unit_ids",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
    )
    application = ApplicationEvent(
        event_id=application_event_id,
        experiment_block_id=block_id,
        evidence_refs=(evidence_id,),
        factor_id=draft.factor_id,
        intervention_id=_answer_knowledge(
            draft.intervention_id,
            field_name="intervention_id",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
        application_unit_type=application_unit,
        application_unit_ids=_id_set_knowledge(
            draft.application_unit_ids,
            field_name="application_unit_ids",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
    )
    exposure = ExposureEvent(
        event_id=exposure_event_id,
        experiment_block_id=block_id,
        evidence_refs=(evidence_id,),
        exposure_pathway=_answer_knowledge(
            draft.exposure_pathway,
            field_name="exposure_pathway",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
        exposure_container=_answer_knowledge(
            draft.exposure_container,
            field_name="exposure_container",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
        effective_exposure_unit=exposure_unit,
        exposed_unit_ids=_id_set_knowledge(
            draft.exposed_unit_ids,
            field_name="exposed_unit_ids",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
    )
    timing_answer = draft.assignment_to_application_timing
    timing = RelativeTiming(
        subject_event_id=assignment_event_id,
        reference_event_id=application_event_id,
        relation=(
            timing_answer.relation
            if timing_answer.status is GuidedAnswerStatus.PROVIDED
            and timing_answer.relation is not None
            else TemporalRelation.UNKNOWN
        ),
        evidence_refs=(evidence_id,) if timing_answer.status is GuidedAnswerStatus.PROVIDED else (),
        rationale=(
            None if timing_answer.status is GuidedAnswerStatus.PROVIDED else timing_answer.rationale
        ),
    )
    event_registry = EventRegistry(
        events=(assignment, application, exposure),
        relative_timings=(timing,),
    )
    causal_aggregate = QueryCausalEventAggregate(
        experiment_block_id=block_id,
        event_registry=event_registry,
        causal_context=QueryCausalContext(
            inferential_query_id=query_id,
            assignment_event_id=_present(
                assignment_event_id, evidence_id=evidence_id, query_id=query_id
            ),
            application_event_id=_present(
                application_event_id, evidence_id=evidence_id, query_id=query_id
            ),
            exposure_event_id=_present(
                exposure_event_id, evidence_id=evidence_id, query_id=query_id
            ),
            assignment_unit_type=assignment_unit,
            application_unit_type=application_unit,
            effective_exposure_unit_type=exposure_unit,
            experimental_unit_type=_unknown(
                "experimental_unit_type", evidence_id=evidence_id, query_id=query_id
            ),
            biological_source_unit_type=_answer_knowledge(
                draft.biological_source_unit_type,
                field_name="biological_source_unit_type",
                evidence_id=evidence_id,
                query_id=query_id,
            ),
            interference_status=_interference_knowledge(
                draft.interference,
                evidence_id=evidence_id,
                query_id=query_id,
            ),
        ),
    )
    lifecycle = predicates["lifecycle_phase"]
    unknown_group = predicates["group_or_paired_set"]
    unknown_cohort = predicates["count_cohort_id"]
    unknown_condition = predicates["count_condition"]
    eu_count = CanonicalCountRecord(
        count_id=stable_id("COUNT-EU-QD", query_id),
        kind=CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT,
        value=_unknown("experimental_unit_count", evidence_id=evidence_id, query_id=query_id),
        quantifier=CountQuantifier.UNKNOWN,
        scope=_count_scope(
            query=query,
            unit_type=predicates["candidate_unit"],
            group_id=unknown_group,
            cohort_id=unknown_cohort,
            condition=unknown_condition,
            lifecycle_phase=lifecycle,
            evidence_id=evidence_id,
        ),
        source_evidence=(evidence_id,),
        origin=CountOrigin.HUMAN_CONFIRMATION,
    )
    source_count = CanonicalCountRecord(
        count_id=stable_id("COUNT-SOURCE-QD", query_id),
        kind=CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT,
        value=_unknown("biological_source_count", evidence_id=evidence_id, query_id=query_id),
        quantifier=CountQuantifier.UNKNOWN,
        scope=_count_scope(
            query=query,
            unit_type=predicates["biological_source_unit_type"],
            group_id=unknown_group,
            cohort_id=unknown_cohort,
            condition=unknown_condition,
            lifecycle_phase=lifecycle,
            evidence_id=evidence_id,
        ),
        source_evidence=(evidence_id,),
        origin=CountOrigin.HUMAN_CONFIRMATION,
    )
    planned_unit_value = _answer_knowledge(
        draft.planned_unit_type,
        field_name="planned_unit_type",
        evidence_id=evidence_id,
        query_id=query_id,
    )
    planned_counts = tuple(
        CanonicalCountRecord(
            count_id=stable_id("COUNT-PLANNED-QD", query_id, group.group_id),
            kind=CanonicalCountKind.PLANNED_UNIT_COUNT,
            value=_present(group.planned_count, evidence_id=evidence_id, query_id=query_id),
            quantifier=CountQuantifier.EXACT,
            scope=_count_scope(
                query=query,
                unit_type=planned_unit_value,
                group_id=_present(group.group_id, evidence_id=evidence_id, query_id=query_id),
                cohort_id=_present(group.group_id, evidence_id=evidence_id, query_id=query_id),
                condition=_present(group.factor_level, evidence_id=evidence_id, query_id=query_id),
                lifecycle_phase=lifecycle,
                evidence_id=evidence_id,
            ),
            source_evidence=(evidence_id,),
            origin=CountOrigin.HUMAN_CONFIRMATION,
        )
        for group in draft.planned_groups
    )
    required_predicate_ids = tuple(
        sorted(
            {
                requirement.predicate_id
                for clause in bundle.theory.clauses
                for requirement in clause.required_predicates
            }
        )
    )
    review_requirement = ScientificReviewRequirement(
        issue_id=PROFILE_COVERAGE_REVIEW_ISSUE_ID,
        rationale="Predicate closure remains under profile governance review.",
    )
    profile_coverage = ProfileCoverageStatement(
        statement_id=stable_id("PCS-QD", query_id, bundle.theory.declared_checksum),
        profile_id=bundle.theory.profile_id,
        profile_version=bundle.theory.profile_version,
        theory_version=bundle.theory.theory_version,
        predicate_closure_argument_id=bundle.profile_closure.asset_id,
        covered_predicate_ids=required_predicate_ids,
        known_gap_ids=(PROFILE_COVERAGE_REVIEW_ISSUE_ID,),
        contract_review=review_requirement,
    )
    unresolved_required = tuple(
        sorted(
            predicate_id
            for predicate_id in required_predicate_ids
            if predicates[predicate_id].knowledge_state is not KnowledgeState.PRESENT
        )
    )
    scenario_coverage = ScenarioCoverage(
        status=ScenarioCoverageStatus.NON_EXHAUSTIVE,
        profile_id=bundle.theory.profile_id,
        theory_version=bundle.theory.theory_version,
        emitting_clause_ids=tuple(clause.clause_id for clause in bundle.theory.clauses),
        omitted_dimensions=_present(
            tuple(f"unresolved_predicate:{item}" for item in unresolved_required),
            evidence_id=evidence_id,
            query_id=query_id,
        ),
        caveat=_present(
            "The guided draft does not exhaust all scientifically plausible scenarios.",
            evidence_id=evidence_id,
            query_id=query_id,
        ),
    )
    support = SupportDescriptor(
        source_class=SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="clarification",
        ),
        authority_type=AuthorityType.USER_CONFIRMATION,
        evidence_basis=EvidenceBasis.AUTHOR_ASSERTED,
        support_grade=SupportGrade(
            vocabulary_id=SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
            token="ASSERTION_ONLY",
        ),
    )
    pipeline_request = V8PipelineRequest(
        experiment_block_id=block_id,
        graph=V8ExperimentGraph(
            nodes=(
                V8GraphNode(node_id=block_id, node_type=V8GraphNodeType.EXPERIMENT_BLOCK),
                V8GraphNode(node_id=query_id, node_type=V8GraphNodeType.INFERENTIAL_QUERY),
            )
        ),
        query=query,
        causal_aggregate=causal_aggregate,
        predicate_values=predicates,
        support_by_clause={clause.clause_id: support for clause in bundle.theory.clauses},
        profile_coverage=profile_coverage,
        scenario_coverages=(scenario_coverage,),
        count_registry=CanonicalCountRegistry(records=(eu_count, source_count, *planned_counts)),
        experimental_unit_count_record_id=eu_count.count_id,
        biological_source_count_record_id=source_count.count_id,
        runtime_ruleset_version=(
            f"{bundle.rulebook.rulebook_id}-{bundle.rulebook.rulebook_version}"
        ),
    )
    source = SourceRecord(
        source_id=source_id,
        source_class=support.source_class,
        source_context=SourceContext.PLANNED,
        source_version=f"sha256:{content_checksum(draft.model_dump(mode='json'))}",
    )
    evidence = EvidenceRecord(
        evidence_id=evidence_id,
        source_id=source_id,
        evidence_type=EvidenceTypeV8.USER_CONFIRMATION,
        locator=f"guided-review://{preview_checksum}",
        original_text=json.dumps(draft.model_dump(mode="json"), sort_keys=True, ensure_ascii=False),
    )
    confirmation_events = tuple(
        ConfirmationEvent(
            event_id=stable_id("CONF-QD", preview_checksum, predicate_id),
            support=support,
            evidence_refs=(evidence_id,),
            scope_id=predicate_id,
            confirmed_value=KnowledgeValue[JsonValue].model_validate(value.model_dump(mode="json")),
            actor_role=confirmation.actor_role,
            review_independent=False,
            created_at=confirmation.confirmed_at,
        )
        for predicate_id, value in predicates.items()
    )
    confirmation_by_predicate = {event.scope_id: event for event in confirmation_events}
    clause_bindings = tuple(
        SupportEvidenceBinding(
            scope_kind=SupportBindingScope.THEORY_CLAUSE,
            scope_id=clause.clause_id,
            support=support,
            source_ids=(source_id,),
            evidence_record_ids=(evidence_id,),
        )
        for clause in bundle.theory.clauses
    )
    predicate_bindings = tuple(
        SupportEvidenceBinding(
            scope_kind=SupportBindingScope.PREDICATE,
            scope_id=predicate_id,
            support=support,
            source_ids=(source_id,),
            evidence_record_ids=(evidence_id,),
            confirmation_event_ids=(confirmation_by_predicate[predicate_id].event_id,),
            confirmation_target=ConfirmationTarget(
                relation_kind=ConfirmationRelationKind.PREDICATE_VALUE,
                query_id=query_id,
                target_id=predicate_id,
            ),
        )
        for predicate_id in predicates
    )
    ledger = build_prospective_input_ledger(
        request=pipeline_request,
        sources=(source,),
        evidence_records=(evidence,),
        confirmation_events=confirmation_events,
        artifacts=artifact_previews,
        support_bindings=(*clause_bindings, *predicate_bindings),
    )
    questions = tuple(
        ReportQuestion(
            question_id=question.question_id,
            inferential_query_id=query_id,
            text=question.text,
            evidence_required=question.evidence_required,
            primary=question.predicate_id == confirmation.primary_predicate_id,
        )
        for question in question_queue
    )
    theory_required_predicates = {
        requirement.predicate_id
        for clause in bundle.theory.clauses
        for requirement in clause.required_predicates
    }
    present_predicates = tuple(
        sorted(
            predicate_id
            for predicate_id, value in predicates.items()
            if value.knowledge_state is KnowledgeState.PRESENT
            and predicate_id in theory_required_predicates
        )
    )
    handoff = StatisticalHandoff(
        items=(
            build_handoff_item(
                category=HandoffItemCategory.STRUCTURAL_CONSTRAINT,
                origin=HandoffItemOrigin.VERIFIED_RECORD,
                authority=AuthorityType.USER_CONFIRMATION,
                evidence_refs=(evidence_id,),
                inferential_query_id=query_id,
                predicate_ids=present_predicates,
            ),
            build_handoff_item(
                category=HandoffItemCategory.UNRESOLVED_QUESTION,
                origin=HandoffItemOrigin.VERIFIED_RECORD,
                authority=AuthorityType.USER_CONFIRMATION,
                evidence_refs=(evidence_id,),
                inferential_query_id=query_id,
                question_ids=tuple(question.question_id for question in questions),
            ),
        )
    )
    artifacts_by_kind = {artifact.kind: artifact.content for artifact in artifact_previews}
    submission = QuickDesignV8Submission(
        pipeline_request=pipeline_request,
        input_ledger=ledger,
        planned_event_registry=event_registry,
        planned_unit_counts=planned_counts,
        sample_sheet_csv=artifacts_by_kind[ProspectiveArtifactKind.SAMPLE_SHEET],
        methods_draft=artifacts_by_kind[ProspectiveArtifactKind.METHODS_DRAFT],
        id_convention=artifacts_by_kind[ProspectiveArtifactKind.ID_CONVENTION],
        user_confirmation_scopes=tuple(predicates),
        ai_candidates=KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="The guided prospective flow uses no parser AI.",
            query_scope_id=query_id,
        ),
        conflicts=KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_REPORTED,
            rationale="The reviewed draft did not report a source conflict.",
            source_scope_ids=(source_id,),
            query_scope_id=query_id,
        ),
        sensitivities=KnowledgeValue(
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Sensitivity consequences require Theory-derived claims after review.",
            evidence_ids=(evidence_id,),
            query_scope_id=query_id,
        ),
        questions=questions,
        statistical_handoff=handoff,
        inference_limits=(
            "This is a reviewed prospective draft, not an executed experiment.",
            "Experimental-unit identity, interference consequences and design adequacy remain "
            "Theory-governed outputs.",
            "ScenarioCoverage is NON_EXHAUSTIVE under SRR-V8-008.",
        ),
    )
    validate_raw_wizard_submission(submission)
    return submission


def build_guided_quick_design(
    request: GuidedQuickDesignBuildRequest,
    *,
    conformance_bundle: ConformanceBundle | None = None,
) -> GuidedQuickDesignBuildResponse:
    """Preview or confirm one deterministic guided draft without a legacy resolver."""

    request = GuidedQuickDesignBuildRequest.model_validate(request.model_dump(mode="python"))
    bundle = conformance_bundle or load_runtime_bundle()
    (
        preview_checksum,
        block_id,
        query_id,
        artifact_previews,
        _preview_predicates,
        question_queue,
        summary,
    ) = _build_preview_parts(request.draft, bundle)
    if request.action is GuidedBuildAction.PREVIEW:
        submission: KnowledgeValue[QuickDesignV8Submission] = KnowledgeValue(
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="The user has not confirmed this exact guided preview checksum.",
            query_scope_id=query_id,
        )
    else:
        built = _build_submission(
            request=request,
            bundle=bundle,
            preview_checksum=preview_checksum,
            block_id=block_id,
            query_id=query_id,
            artifact_previews=artifact_previews,
            question_queue=question_queue,
        )
        evidence_ids = tuple(record.evidence_id for record in built.input_ledger.evidence_records)
        submission = KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=built,
            evidence_ids=evidence_ids,
            query_scope_id=query_id,
        )
    return GuidedQuickDesignBuildResponse(
        action=request.action,
        state=(
            GuidedBuildState.REVIEW_REQUIRED
            if request.action is GuidedBuildAction.PREVIEW
            else GuidedBuildState.BUILT
        ),
        preview_checksum=preview_checksum,
        summary=summary,
        visible_questions=question_queue[:3],
        question_queue=question_queue,
        artifact_previews=artifact_previews,
        submission=submission,
    )


def run_confirmed_guided_quick_design(
    response: GuidedQuickDesignBuildResponse,
    *,
    conformance_bundle: ConformanceBundle | None = None,
) -> QuickDesignV8Result:
    """Exercise the canonical endpoint-equivalent lane for a confirmed builder response."""

    response = GuidedQuickDesignBuildResponse.model_validate(response.model_dump(mode="python"))
    if (
        response.action is not GuidedBuildAction.CONFIRM
        or response.submission.knowledge_state is not KnowledgeState.PRESENT
        or response.submission.value is None
    ):
        raise ValueError("only a confirmed guided response can enter the canonical lane")
    validate_raw_wizard_submission(response.submission.value)
    return run_quick_design_v8(
        response.submission.value,
        conformance_bundle=conformance_bundle or load_runtime_bundle(),
    )


__all__ = [
    "GuidedAnswerStatus",
    "GuidedBuildAction",
    "GuidedBuildState",
    "GuidedIdSetAnswer",
    "GuidedInterferenceAnswer",
    "GuidedInterferenceStatus",
    "GuidedPlannedGroup",
    "GuidedQuickDesignBuildRequest",
    "GuidedQuickDesignBuildResponse",
    "GuidedQuickDesignConfirmation",
    "GuidedQuickDesignDraft",
    "GuidedQuickDesignSummary",
    "GuidedTextAnswer",
    "GuidedTheoryQuestion",
    "GuidedTimingAnswer",
    "build_guided_quick_design",
    "run_confirmed_guided_quick_design",
]
