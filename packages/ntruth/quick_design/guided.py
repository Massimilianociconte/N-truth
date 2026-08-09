"""Deterministic guided-input builder for the canonical PRD v8 Quick Design lane.

The builder records only reviewed user declarations.  It deliberately leaves
scientific consequences such as experimental-unit identity, independence,
interference and design adequacy unresolved for the verified Theory pipeline.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum, StrEnum
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator
from pydantic_core import TzInfo

from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.derivation_theory.runtime import (
    load_runtime_bundle,
    require_reviewed_evaluator_bundle,
    verify_runtime_bundle,
)
from ntruth.mvt_a.stage_schema import assert_no_final_scientific_fields
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
    COUNT_RECONCILIATION_REVIEW_ISSUE_ID,
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

GUIDED_SAMPLE_SHEET_MAX_ROWS = 100_000
GUIDED_QUESTION_PRIORITY_REVIEW_ISSUE_ID = "SRR-V8-025"


def _canonical_confirmation_datetime(value: datetime) -> datetime:
    """Normalize only exact, non-overridable timestamp and timezone implementations."""

    if type(value) is not datetime:
        raise ValueError(
            f"confirmed_at must use the exact canonical datetime type, got {type(value).__name__}"
        )
    zone = value.tzinfo
    if zone is None:
        raise ValueError("confirmed_at requires a timezone offset")
    if type(zone) not in {timezone, TzInfo}:
        raise ValueError(
            "confirmed_at must use an exact canonical fixed-offset timezone, "
            f"got {type(zone).__name__}"
        )
    offset = datetime.utcoffset(value)
    if offset is None:
        raise ValueError("confirmed_at requires a timezone offset")
    canonical_zone = timezone(offset)
    return datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
        tzinfo=canonical_zone,
        fold=value.fold,
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


class GuidedQuestionPriorityState(StrEnum):
    """The reviewed Theory assets do not yet define question priority."""

    UNREVIEWED = "UNREVIEWED"


class _GuidedCountScopeScientificReviewRequired(QuickDesignScientificReviewRequired):
    """Typed count-scope blocker using the canonical count-vocabulary issue ID."""

    def __init__(self, rationale: str) -> None:
        self.review_requirement = ScientificReviewRequirement(
            issue_id=COUNT_RECONCILIATION_REVIEW_ISSUE_ID,
            rationale=rationale,
        )
        ValueError.__init__(self, f"SCIENTIFIC_REVIEW_REQUIRED: {rationale}")


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
    cohort_id: GuidedTextAnswer
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
        total_planned_rows = sum(group.planned_count for group in self.planned_groups)
        if (
            any(group.planned_count > GUIDED_SAMPLE_SHEET_MAX_ROWS for group in self.planned_groups)
            or total_planned_rows > GUIDED_SAMPLE_SHEET_MAX_ROWS
        ):
            raise ValueError(
                "planned_count exceeds the operational sample-sheet safety limit of "
                f"{GUIDED_SAMPLE_SHEET_MAX_ROWS} rows; this is an implementation safety "
                "limit, not a scientific threshold"
            )
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


class GuidedQuickDesignReviewSnapshot(KernelModel):
    """Typed review bytes; never an executable Quick Design submission."""

    draft: GuidedQuickDesignDraft
    conformance_bundle_payload: dict[NonBlankStr, JsonValue]
    is_execution_capability: Literal[False] = False

    @property
    def conformance_bundle(self) -> ConformanceBundle:
        return ConformanceBundle.model_validate(self.conformance_bundle_payload)

    @model_validator(mode="after")
    def _verified_review_assets(self) -> Self:
        require_reviewed_evaluator_bundle(self.conformance_bundle)
        report = verify_runtime_bundle(self.conformance_bundle)
        if not report.passed:
            raise ValueError(
                "guided review snapshot conformance bundle/profile failed independent verification"
            )
        return self


class GuidedQuickDesignConfirmation(KernelModel):
    preview_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_focus_predicate_id: NonBlankStr
    actor_role: NonBlankStr
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        return _canonical_confirmation_datetime(value)


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
    priority_state: Literal[GuidedQuestionPriorityState.UNREVIEWED] = (
        GuidedQuestionPriorityState.UNREVIEWED
    )
    priority_review: ScientificReviewRequirement
    evidence_required: KnowledgeValue[tuple[NonBlankStr, ...]]


class GuidedQuickDesignSummary(KernelModel):
    experiment_block_id: NonBlankStr
    inferential_query_id: NonBlankStr
    provided_field_ids: tuple[NonBlankStr, ...]
    unknown_field_ids: tuple[NonBlankStr, ...]
    planned_group_count: int = Field(ge=2)
    planned_unit_total: int = Field(ge=2)
    known_profile_gaps: tuple[NonBlankStr, ...] = Field(min_length=1)
    scenario_coverage_status: Literal["NON_EXHAUSTIVE"] = "NON_EXHAUSTIVE"
    strategy_module_status: Literal["HANDOFF_ONLY"] = "HANDOFF_ONLY"


class GuidedQuickDesignBuildResponse(KernelModel):
    contract_code: Literal["NTRUTH_QUICK_DESIGN_GUIDED_V8"] = "NTRUTH_QUICK_DESIGN_GUIDED_V8"
    contract_version: Literal["8.0.0"] = "8.0.0"
    action: GuidedBuildAction
    state: GuidedBuildState
    preview_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_snapshot: GuidedQuickDesignReviewSnapshot
    summary: GuidedQuickDesignSummary
    visible_questions: tuple[GuidedTheoryQuestion, ...] = Field(max_length=3)
    question_queue: tuple[GuidedTheoryQuestion, ...] = Field(min_length=1)
    artifact_previews: tuple[ProspectiveArtifact, ...] = Field(min_length=3, max_length=3)
    submission_audit_snapshot: KnowledgeValue[QuickDesignV8Submission]
    submission_is_execution_capability: Literal[False] = False
    canonical_result: KnowledgeValue[QuickDesignV8Result]
    confirmed_snapshot_checksum: KnowledgeValue[str]

    @model_validator(mode="after")
    def _preview_or_submission(self) -> Self:
        if self.visible_questions != self.question_queue[:3]:
            raise ValueError("visible questions must be the first three retained queue entries")
        if self.action is GuidedBuildAction.PREVIEW:
            if self.state is not GuidedBuildState.REVIEW_REQUIRED:
                raise ValueError("PREVIEW must retain REVIEW_REQUIRED without an executable result")
            _assert_preview_guided_closure(self)
        elif (
            self.submission_audit_snapshot.knowledge_state is not KnowledgeState.PRESENT
            or self.canonical_result.knowledge_state is not KnowledgeState.PRESENT
            or self.confirmed_snapshot_checksum.knowledge_state is not KnowledgeState.PRESENT
            or self.state is not GuidedBuildState.BUILT
            or self.submission_audit_snapshot.value is None
            or self.canonical_result.value is None
            or self.confirmed_snapshot_checksum.value is None
        ):
            raise ValueError(
                "CONFIRM must atomically emit a BUILT audit snapshot and canonical result"
            )
        elif self.confirmed_snapshot_checksum.value != _confirmed_snapshot_checksum(
            preview_checksum=self.preview_checksum,
            submission=self.submission_audit_snapshot.value,
            result=self.canonical_result.value,
        ):
            raise ValueError("confirmed guided snapshot checksum mismatch")
        else:
            _assert_confirmed_guided_closure(self)
        return self


def _raw_guided_contract_tree(
    value: object,
    *,
    seen: set[int] | None = None,
) -> object:
    """Expose public runtime state before Pydantic can omit invalid extras."""

    if seen is None:
        seen = set()
    tracked = isinstance(value, (BaseModel, Mapping, list, tuple, set, frozenset))
    identity = id(value)
    if tracked:
        if identity in seen:
            raise ValueError("guided runtime tree contains a recursive container cycle")
        seen.add(identity)
    try:
        if isinstance(value, datetime):
            _canonical_confirmation_datetime(value)
            return value
        if isinstance(value, BaseModel):
            raw_values = value.__dict__
            if type(raw_values) is not dict:
                raise ValueError(
                    "guided runtime model state must be exact builtin dict, "
                    f"got {type(raw_values).__name__}"
                )
            declared_fields = type(value).model_fields
            payload: dict[object, object] = {
                field_name: _raw_guided_contract_tree(raw_values[field_name], seen=seen)
                for field_name in declared_fields
                if field_name in raw_values
            }
            for field_name in raw_values:
                if not isinstance(field_name, str):
                    raise ValueError(
                        f"guided runtime model state key {field_name!r} is not canonical"
                    )
                if field_name in declared_fields or field_name.startswith("_"):
                    continue
                raise ValueError(
                    f"guided runtime model has non-canonical undeclared public field {field_name!r}"
                )
            extra_values = value.__pydantic_extra__
            if extra_values is not None:
                if type(extra_values) is not dict:
                    raise ValueError(
                        "guided runtime Pydantic extras must use exact builtin dict, "
                        f"got {type(extra_values).__name__}"
                    )
                if extra_values:
                    extra_field = next(iter(extra_values))
                    raise ValueError(
                        "guided runtime model has non-canonical undeclared Pydantic "
                        f"extra field {extra_field!r}"
                    )
                raise ValueError(
                    "guided runtime model has a non-canonical empty Pydantic extra store"
                )
            return payload
        if isinstance(value, Mapping):
            if type(value) is not dict:
                raise ValueError(
                    "guided runtime container type must be exact builtin dict, "
                    f"got {type(value).__name__}"
                )
            mapping_payload: dict[object, object] = {}
            for key, item in value.items():
                raw_key = _raw_guided_contract_tree(key, seen=seen)
                raw_item = _raw_guided_contract_tree(item, seen=seen)
                try:
                    mapping_payload[raw_key] = raw_item
                except TypeError as exc:
                    raise ValueError("guided runtime mapping key is not canonical") from exc
            return mapping_payload
        if isinstance(value, (list, tuple, set, frozenset)):
            if type(value) not in {list, tuple, set, frozenset}:
                raise ValueError(
                    "guided runtime container type must be an exact builtin, "
                    f"got {type(value).__name__}"
                )
            return tuple(_raw_guided_contract_tree(item, seen=seen) for item in value)
        if isinstance(value, Enum):
            enum_state = value.__dict__
            if type(enum_state) is not dict:
                raise ValueError(
                    "guided runtime enum state must be exact builtin dict, "
                    f"got {type(enum_state).__name__}"
                )
            public_enum_fields = tuple(
                field_name
                for field_name in enum_state
                if not isinstance(field_name, str) or not field_name.startswith("_")
            )
            if public_enum_fields:
                raise ValueError(
                    f"guided runtime enum has non-canonical public state {public_enum_fields!r}"
                )
            return value
        if isinstance(value, (str, int, float, bool, bytes)) and type(value) not in {
            str,
            int,
            float,
            bool,
            bytes,
        }:
            raise ValueError(
                "guided runtime scalar type must be an exact builtin or canonical enum, "
                f"got {type(value).__name__}"
            )
        return value
    finally:
        if tracked:
            seen.remove(identity)


def _assert_exact_guided_model_types(
    actual: object,
    canonical: object,
    *,
    path: str = "$",
    seen: set[tuple[int, int]] | None = None,
) -> None:
    """Reject non-canonical models and container interchange anywhere in a draft."""

    if seen is None:
        seen = set()
    identity = (id(actual), id(canonical))
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(canonical, BaseModel):
        if type(actual) is not type(canonical):
            raise ValueError(
                f"guided runtime type at {path} must be exact canonical "
                f"{type(canonical).__name__}, got {type(actual).__name__}"
            )
        actual_values = actual.__dict__
        canonical_values = canonical.__dict__
        for field_name in type(canonical).model_fields:
            if field_name not in actual_values or field_name not in canonical_values:
                raise ValueError(f"guided runtime field {path}.{field_name} is not canonical")
            _assert_exact_guided_model_types(
                actual_values[field_name],
                canonical_values[field_name],
                path=f"{path}.{field_name}",
                seen=seen,
            )
        return
    if type(canonical) is dict:
        if type(actual) is not dict or len(actual) != len(canonical):
            raise ValueError(f"guided runtime mapping at {path} is not canonical")
        unmatched_mapping_items = list(canonical.items())
        for index, (actual_key, actual_item) in enumerate(actual.items()):
            match_index = next(
                (
                    candidate_index
                    for candidate_index, (canonical_key, _) in enumerate(unmatched_mapping_items)
                    if type(actual_key) is type(canonical_key) and actual_key == canonical_key
                ),
                None,
            )
            if match_index is None:
                raise ValueError(f"guided runtime mapping key at {path} is not canonical")
            canonical_key, canonical_item = unmatched_mapping_items.pop(match_index)
            _assert_exact_guided_model_types(
                actual_key,
                canonical_key,
                path=f"{path}.<key:{index}>",
                seen=seen,
            )
            _assert_exact_guided_model_types(
                actual_item,
                canonical_item,
                path=f"{path}[{canonical_key!r}]",
                seen=seen,
            )
        return
    if type(canonical) in {list, tuple}:
        if type(actual) is not type(canonical):
            raise ValueError(f"guided runtime container at {path} is not canonical")
        actual_sequence = cast(list[object] | tuple[object, ...], actual)
        canonical_sequence = cast(list[object] | tuple[object, ...], canonical)
        if len(actual_sequence) != len(canonical_sequence):
            raise ValueError(f"guided runtime container at {path} is not canonical")
        for index, (actual_item, canonical_item) in enumerate(
            zip(actual_sequence, canonical_sequence, strict=True)
        ):
            _assert_exact_guided_model_types(
                actual_item,
                canonical_item,
                path=f"{path}[{index}]",
                seen=seen,
            )
        return
    if type(canonical) in {set, frozenset}:
        if type(actual) is not type(canonical):
            raise ValueError(f"guided runtime container at {path} is not canonical")
        actual_set = cast(set[object] | frozenset[object], actual)
        canonical_set = cast(set[object] | frozenset[object], canonical)
        if len(actual_set) != len(canonical_set):
            raise ValueError(f"guided runtime container at {path} is not canonical")
        unmatched_set_items = list(canonical_set)
        for index, actual_item in enumerate(actual_set):
            match_index = next(
                (
                    candidate_index
                    for candidate_index, canonical_item in enumerate(unmatched_set_items)
                    if type(actual_item) is type(canonical_item) and actual_item == canonical_item
                ),
                None,
            )
            if match_index is None:
                raise ValueError(f"guided runtime set item at {path}[{index}] is not canonical")
            canonical_item = unmatched_set_items.pop(match_index)
            _assert_exact_guided_model_types(
                actual_item,
                canonical_item,
                path=f"{path}[{index}]",
                seen=seen,
            )
        return
    if type(actual) is not type(canonical):
        raise ValueError(
            f"guided runtime type at {path} must be exact canonical "
            f"{type(canonical).__name__}, got {type(actual).__name__}"
        )


def _canonical_guided_request(
    request: GuidedQuickDesignBuildRequest,
) -> GuidedQuickDesignBuildRequest:
    if type(request) is not GuidedQuickDesignBuildRequest:
        raise ValueError(
            "guided runtime type at $ must be exact canonical "
            f"GuidedQuickDesignBuildRequest, got {type(request).__name__}"
        )
    assert_no_final_scientific_fields(_raw_guided_contract_tree(request))
    try:
        canonical = GuidedQuickDesignBuildRequest.model_validate(
            GuidedQuickDesignBuildRequest.model_dump(
                request,
                mode="python",
                round_trip=True,
                warnings="none",
            )
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"guided runtime tree cannot be canonicalized: {exc}") from exc
    _assert_exact_guided_model_types(request, canonical)
    return canonical


def _confirmed_snapshot_checksum(
    *,
    preview_checksum: str,
    submission: QuickDesignV8Submission,
    result: QuickDesignV8Result,
) -> str:
    return content_checksum(
        {
            "preview_checksum": preview_checksum,
            "submission_audit_snapshot": submission.model_dump(mode="json"),
            "canonical_result": result.model_dump(mode="json"),
        }
    )


def _canonical_review_snapshot(
    snapshot: GuidedQuickDesignReviewSnapshot,
) -> GuidedQuickDesignReviewSnapshot:
    """Revalidate the complete review bytes, including governed bundle/profile assets."""

    try:
        return GuidedQuickDesignReviewSnapshot.model_validate(
            snapshot.model_dump(mode="python", round_trip=True, warnings="none")
        )
    except ValueError as exc:
        raise ValueError("guided review snapshot bundle/profile closure failed") from exc


def _preview_knowledge_envelopes(
    *,
    query_id: str,
) -> tuple[
    KnowledgeValue[QuickDesignV8Submission],
    KnowledgeValue[QuickDesignV8Result],
    KnowledgeValue[str],
]:
    return (
        KnowledgeValue[QuickDesignV8Submission](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="PREVIEW is review-only; no confirmed submission audit snapshot exists.",
            query_scope_id=query_id,
        ),
        KnowledgeValue[QuickDesignV8Result](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="PREVIEW does not execute the canonical Quick Design lane.",
            query_scope_id=query_id,
        ),
        KnowledgeValue[str](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="A confirmed snapshot checksum exists only after atomic CONFIRM.",
            query_scope_id=query_id,
        ),
    )


def _confirmed_knowledge_envelopes(
    *,
    preview_checksum: str,
    query_id: str,
    submission: QuickDesignV8Submission,
    result: QuickDesignV8Result,
) -> tuple[
    KnowledgeValue[QuickDesignV8Submission],
    KnowledgeValue[QuickDesignV8Result],
    KnowledgeValue[str],
]:
    evidence_ids = tuple(record.evidence_id for record in submission.input_ledger.evidence_records)
    return (
        KnowledgeValue[QuickDesignV8Submission](
            knowledge_state=KnowledgeState.PRESENT,
            value=submission,
            evidence_ids=evidence_ids,
            query_scope_id=query_id,
        ),
        KnowledgeValue[QuickDesignV8Result](
            knowledge_state=KnowledgeState.PRESENT,
            value=result,
            evidence_ids=evidence_ids,
            query_scope_id=query_id,
        ),
        KnowledgeValue[str](
            knowledge_state=KnowledgeState.PRESENT,
            value=_confirmed_snapshot_checksum(
                preview_checksum=preview_checksum,
                submission=submission,
                result=result,
            ),
            evidence_ids=evidence_ids,
            query_scope_id=query_id,
        ),
    )


def _build_confirmation_event(
    *,
    support: SupportDescriptor,
    evidence_id: str,
    scope_id: str,
    value: KnowledgeValue[Any],
    actor_role: str,
    created_at: datetime,
) -> ConfirmationEvent:
    confirmed_value = KnowledgeValue[JsonValue].model_validate(value.model_dump(mode="json"))
    body = {
        "support": support.model_dump(mode="json"),
        "evidence_refs": (evidence_id,),
        "scope_id": scope_id,
        "confirmed_value": confirmed_value.model_dump(mode="json"),
        "actor_role": actor_role,
        "review_independent": False,
        "sensitivity_record_ids": (),
        "created_at": created_at.isoformat(),
    }
    body_checksum = content_checksum(body)
    return ConfirmationEvent(
        event_id=f"CONF-QD-{body_checksum[:20]}",
        support=support,
        evidence_refs=(evidence_id,),
        scope_id=scope_id,
        confirmed_value=confirmed_value,
        actor_role=actor_role,
        review_independent=False,
        created_at=created_at,
    )


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
    *,
    query_id: str,
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
                text=(
                    f"Review unresolved predicate `{predicate_id}`. The retained Theory "
                    "requirements are recorded separately; this wording and queue order "
                    "have not received scientific priority review."
                ),
                priority_review=ScientificReviewRequirement(
                    issue_id=GUIDED_QUESTION_PRIORITY_REVIEW_ISSUE_ID,
                    rationale=(
                        "Question/evidence ordering and evidence-request contracts have not "
                        "received independent scientific review; display order is not a "
                        "Theory-derived priority."
                    ),
                ),
                evidence_required=KnowledgeValue[tuple[NonBlankStr, ...]](
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale=(
                        "The reviewed Theory/Profile assets do not define a concrete "
                        "evidence-request contract for this predicate."
                    ),
                    query_scope_id=query_id,
                ),
            )
        )
    if not questions:
        raise QuickDesignScientificReviewRequired(
            "the guided profile emitted no unresolved Theory predicate for review focus"
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
            "cohort_id",
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
                    group.cohort_id.value or "UNKNOWN",
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
        "Lifecycle cohort IDs by planned group (user reviewed): "
        + ", ".join(
            f"{group.group_id}={group.cohort_id.value or 'UNKNOWN'}"
            for group in draft.planned_groups
        )
        + ".\n\n"
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
    queue = _question_queue(bundle, predicates, query_id=query_id)
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
        known_profile_gaps=bundle.profile_closure.known_gaps,
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
    if confirmation.review_focus_predicate_id not in unresolved_ids:
        raise ValueError("review focus must be selected from the retained Theory queue")
    if draft.planned_unit_type.status is not GuidedAnswerStatus.PROVIDED:
        raise QuickDesignScientificReviewRequired(
            "planned_unit_count requires a user-provided unit type and fully resolved scope"
        )
    missing_cohort_groups = tuple(
        group.group_id
        for group in draft.planned_groups
        if group.cohort_id.status is not GuidedAnswerStatus.PROVIDED
    )
    if missing_cohort_groups:
        raise _GuidedCountScopeScientificReviewRequired(
            "planned_unit_count requires an explicit user-declared lifecycle cohort_id "
            "for every group; unresolved groups: " + ", ".join(missing_cohort_groups)
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
                cohort_id=_answer_knowledge(
                    group.cohort_id,
                    field_name=f"planned_group[{group.group_id}].cohort_id",
                    evidence_id=evidence_id,
                    query_id=query_id,
                ),
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
        _build_confirmation_event(
            support=support,
            evidence_id=evidence_id,
            scope_id=predicate_id,
            value=value,
            actor_role=confirmation.actor_role,
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
            evidence_required=(
                "SCIENTIFIC_REVIEW_REQUIRED:"
                f"{question.priority_review.issue_id}:evidence_request_contract_unknown",
            ),
            primary=question.predicate_id == confirmation.review_focus_predicate_id,
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
            "ReportQuestion.primary records only the user-selected review focus; it is not "
            "a Theory-reviewed question priority (SRR-V8-025).",
            *tuple(
                f"Profile known gap: {known_gap}" for known_gap in bundle.profile_closure.known_gaps
            ),
        ),
    )
    validate_raw_wizard_submission(submission)
    return submission


def _rederive_guided_preview(
    response: GuidedQuickDesignBuildResponse,
) -> tuple[
    GuidedQuickDesignReviewSnapshot,
    str,
    str,
    str,
    tuple[ProspectiveArtifact, ...],
    tuple[GuidedTheoryQuestion, ...],
    GuidedQuickDesignSummary,
]:
    """Verify governed review bytes and compare every public preview projection."""

    snapshot = _canonical_review_snapshot(response.review_snapshot)
    try:
        (
            preview_checksum,
            block_id,
            query_id,
            artifact_previews,
            _preview_predicates,
            question_queue,
            summary,
        ) = _build_preview_parts(snapshot.draft, snapshot.conformance_bundle)
    except ValueError as exc:
        raise ValueError("guided preview closure re-derivation failed") from exc
    if response.preview_checksum != preview_checksum:
        raise ValueError("guided preview closure checksum mismatch")
    if response.summary != summary:
        raise ValueError("guided preview closure summary mismatch")
    if response.question_queue != question_queue:
        raise ValueError("guided preview closure question queue mismatch")
    if response.visible_questions != question_queue[:3]:
        raise ValueError("guided preview closure visible question projection mismatch")
    if response.artifact_previews != artifact_previews:
        raise ValueError("guided preview closure artifact projection mismatch")
    return (
        snapshot,
        preview_checksum,
        block_id,
        query_id,
        artifact_previews,
        question_queue,
        summary,
    )


def _assert_preview_guided_closure(response: GuidedQuickDesignBuildResponse) -> None:
    """Keep PREVIEW completely reproducible and incapable of carrying execution output."""

    _, _, _, query_id, _, _, _ = _rederive_guided_preview(response)
    expected = _preview_knowledge_envelopes(query_id=query_id)
    actual = (
        response.submission_audit_snapshot,
        response.canonical_result,
        response.confirmed_snapshot_checksum,
    )
    if actual != expected:
        raise ValueError("guided PREVIEW closure envelope metadata differs from review-only state")


def _assert_confirmed_guided_closure(response: GuidedQuickDesignBuildResponse) -> None:
    """Re-derive every confirmed projection and complete KnowledgeValue envelope."""

    submission = response.submission_audit_snapshot.value
    result = response.canonical_result.value
    if submission is None or result is None:  # guarded by the response state contract
        raise ValueError("guided confirmed closure requires submission and result values")
    (
        snapshot,
        preview_checksum,
        block_id,
        query_id,
        artifact_previews,
        question_queue,
        _summary,
    ) = _rederive_guided_preview(response)
    bundle = snapshot.conformance_bundle

    contexts = result.report_bundle.verified_pipeline_contexts
    if len(contexts) != 1:
        raise ValueError("guided confirmed closure requires exactly one verified pipeline context")
    try:
        result_bundle = contexts[0].conformance_bundle
    except ValueError as exc:
        raise ValueError("guided confirmed closure has an invalid conformance bundle") from exc
    if result_bundle != bundle:
        raise ValueError("guided confirmed closure result uses a different review bundle/profile")

    evidence_records = submission.input_ledger.evidence_records
    if len(evidence_records) != 1:
        raise ValueError("guided confirmed closure requires exactly one guided evidence record")
    evidence = evidence_records[0]
    expected_evidence_id = stable_id("EV-QD-REVIEW", preview_checksum)
    expected_draft_text = json.dumps(
        snapshot.draft.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
    )
    if (
        evidence.evidence_id != expected_evidence_id
        or evidence.locator != f"guided-review://{preview_checksum}"
        or evidence.original_text != expected_draft_text
    ):
        raise ValueError("guided confirmed closure preview/evidence binding mismatch")

    primary_question_ids = tuple(
        question.question_id for question in submission.questions if question.primary
    )
    if len(primary_question_ids) != 1:
        raise ValueError("guided confirmed closure requires exactly one selected review focus")
    focus_predicate_ids = tuple(
        question.predicate_id
        for question in question_queue
        if question.question_id == primary_question_ids[0]
    )
    if len(focus_predicate_ids) != 1:
        raise ValueError("guided confirmed closure review focus differs from the Theory queue")

    confirmation_events = submission.input_ledger.confirmation_events
    if not confirmation_events:
        raise ValueError("guided confirmed closure requires confirmation events")
    actor_role = confirmation_events[0].actor_role
    confirmed_at = _canonical_confirmation_datetime(confirmation_events[0].created_at)
    for event in confirmation_events:
        event_time = _canonical_confirmation_datetime(event.created_at)
        if event.actor_role != actor_role or event_time != confirmed_at:
            raise ValueError(
                "guided confirmed closure requires one actor and timestamp across confirmations"
            )

    reconstructed_request = GuidedQuickDesignBuildRequest(
        action=GuidedBuildAction.CONFIRM,
        draft=snapshot.draft,
        confirmation=GuidedQuickDesignConfirmation(
            preview_checksum=preview_checksum,
            review_focus_predicate_id=focus_predicate_ids[0],
            actor_role=actor_role,
            confirmed_at=confirmed_at,
        ),
    )
    try:
        reconstructed_submission = _build_submission(
            request=reconstructed_request,
            bundle=bundle,
            preview_checksum=preview_checksum,
            block_id=block_id,
            query_id=query_id,
            artifact_previews=artifact_previews,
            question_queue=question_queue,
        )
    except ValueError as exc:
        raise ValueError("guided confirmed closure submission re-derivation failed") from exc
    if reconstructed_submission != submission:
        raise ValueError("guided confirmed closure submission differs from re-derivation")

    try:
        reconstructed_result = run_quick_design_v8(
            reconstructed_submission,
            conformance_bundle=bundle,
        )
    except ValueError as exc:
        raise ValueError("guided confirmed closure canonical re-execution failed") from exc
    if reconstructed_result != result:
        raise ValueError("guided confirmed closure result differs from canonical re-execution")

    expected_envelopes = _confirmed_knowledge_envelopes(
        preview_checksum=preview_checksum,
        query_id=query_id,
        submission=reconstructed_submission,
        result=reconstructed_result,
    )
    actual_envelopes = (
        response.submission_audit_snapshot,
        response.canonical_result,
        response.confirmed_snapshot_checksum,
    )
    for label, actual, expected in zip(
        (
            "submission_audit_snapshot",
            "canonical_result",
            "confirmed_snapshot_checksum",
        ),
        actual_envelopes,
        expected_envelopes,
        strict=True,
    ):
        if actual != expected:
            raise ValueError(
                f"guided confirmed closure {label} complete envelope metadata mismatch"
            )


def build_guided_quick_design(
    request: GuidedQuickDesignBuildRequest,
    *,
    conformance_bundle: ConformanceBundle | None = None,
) -> GuidedQuickDesignBuildResponse:
    """Preview or confirm one deterministic guided draft without a legacy resolver."""

    request = _canonical_guided_request(request)
    review_snapshot = GuidedQuickDesignReviewSnapshot(
        draft=request.draft,
        conformance_bundle_payload=(conformance_bundle or load_runtime_bundle()).model_dump(
            mode="json",
            exclude_unset=True,
        ),
    )
    bundle = review_snapshot.conformance_bundle
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
        (
            submission_audit_snapshot,
            canonical_result,
            confirmed_snapshot_checksum,
        ) = _preview_knowledge_envelopes(
            query_id=query_id,
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
        result = run_quick_design_v8(
            built,
            conformance_bundle=bundle,
        )
        (
            submission_audit_snapshot,
            canonical_result,
            confirmed_snapshot_checksum,
        ) = _confirmed_knowledge_envelopes(
            preview_checksum=preview_checksum,
            query_id=query_id,
            submission=built,
            result=result,
        )
    return GuidedQuickDesignBuildResponse(
        action=request.action,
        state=(
            GuidedBuildState.REVIEW_REQUIRED
            if request.action is GuidedBuildAction.PREVIEW
            else GuidedBuildState.BUILT
        ),
        preview_checksum=preview_checksum,
        review_snapshot=review_snapshot,
        summary=summary,
        visible_questions=question_queue[:3],
        question_queue=question_queue,
        artifact_previews=artifact_previews,
        submission_audit_snapshot=submission_audit_snapshot,
        canonical_result=canonical_result,
        confirmed_snapshot_checksum=confirmed_snapshot_checksum,
    )


def run_confirmed_guided_quick_design(
    response: GuidedQuickDesignBuildResponse,
) -> QuickDesignV8Result:
    """Return the result already executed atomically by guided CONFIRM."""

    response = GuidedQuickDesignBuildResponse.model_validate(response.model_dump(mode="python"))
    if (
        response.action is not GuidedBuildAction.CONFIRM
        or response.canonical_result.knowledge_state is not KnowledgeState.PRESENT
        or response.canonical_result.value is None
    ):
        raise ValueError("only an atomically confirmed guided response has a canonical result")
    return response.canonical_result.value


__all__ = [
    "GUIDED_QUESTION_PRIORITY_REVIEW_ISSUE_ID",
    "GUIDED_SAMPLE_SHEET_MAX_ROWS",
    "GuidedAnswerStatus",
    "GuidedBuildAction",
    "GuidedBuildState",
    "GuidedIdSetAnswer",
    "GuidedInterferenceAnswer",
    "GuidedInterferenceStatus",
    "GuidedPlannedGroup",
    "GuidedQuestionPriorityState",
    "GuidedQuickDesignBuildRequest",
    "GuidedQuickDesignBuildResponse",
    "GuidedQuickDesignConfirmation",
    "GuidedQuickDesignDraft",
    "GuidedQuickDesignReviewSnapshot",
    "GuidedQuickDesignSummary",
    "GuidedTextAnswer",
    "GuidedTheoryQuestion",
    "GuidedTimingAnswer",
    "build_guided_quick_design",
    "run_confirmed_guided_quick_design",
]
