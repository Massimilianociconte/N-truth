"""Neutral, content-addressed PRD v8 ReportBundle contract.

The bundle stores determinability, evidence support, design findings and
coverage as independent axes.  It deliberately exposes a statistical handoff,
never an analysis-strategy recommendation or design-approval verdict.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.schemas.adequacy import DesignAdequacyEvaluation
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.claims import DerivedClaimSet, DeterminabilityState
from ntruth.schemas.core import content_checksum
from ntruth.schemas.count_registry import CanonicalCountRecord, CanonicalCountRegistry
from ntruth.schemas.coverage import ProfileCoverageStatement, ScenarioCoverage
from ntruth.schemas.execution import V8ExecutionManifest
from ntruth.schemas.graph_v8 import V8ExperimentGraph
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import (
    KnowledgeState,
    KnowledgeValue,
    ensure_unambiguous_scientific_payload,
)
from ntruth.schemas.prospective import (
    ExecutedDesignRecord,
    PlanExecutionReconciliation,
    PlannedDesignRecord,
    ProspectiveInputLedger,
)
from ntruth.schemas.query import InferentialQuery
from ntruth.schemas.report_resolution import (
    REPORT_AGGREGATION_REVIEW_ISSUE_ID,
    ReportResolutionOutcome,
    TrivialExplicitReportResolutionPolicy,
)
from ntruth.schemas.support import (
    ConfirmationEvent,
    EvidenceRecord,
    SensitivityRecord,
    SourceRecord,
)

if TYPE_CHECKING:
    from ntruth.derivation_theory.contracts import ConformanceBundle
    from ntruth.pipeline_v8 import V8PipelineRequest, V8PipelineResult

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

RETROSPECTIVE_EPISTEMIC_BOUNDARY = (
    "N-Truth ha valutato i record e le conferme disponibili; non ha osservato "
    "direttamente l'esperimento e non può recuperare deviazioni non registrate."
)
PLANNED_EPISTEMIC_BOUNDARY = (
    "N-Truth ha valutato un piano e le evidenze disponibili; non ha osservato "
    "l'esecuzione e non presenta fatti pianificati come fatti realizzati."
)
EXECUTED_EPISTEMIC_BOUNDARY = (
    "N-Truth ha valutato i record di piano ed esecuzione disponibili; eventuali "
    "deviazioni non registrate restano fuori dalla conoscenza del sistema."
)
RECONCILED_EPISTEMIC_BOUNDARY = (
    "N-Truth ha riconciliato i record pianificati ed eseguiti forniti; la riconciliazione "
    "non prova l'assenza di eventi o deviazioni non registrati."
)
MULTI_QUERY_POLICY_VERSION = "ntruth-report-resolution-multi-query-unreviewed-v8-0.1.0"


class StrategyModuleStatus(StrEnum):
    """Only the Bootstrap Core state is valid until external validation closes."""

    HANDOFF_ONLY = "HANDOFF_ONLY"


class HandoffItemCategory(StrEnum):
    STRUCTURAL_CONSTRAINT = "STRUCTURAL_CONSTRAINT"
    UNRESOLVED_QUESTION = "UNRESOLVED_QUESTION"
    USER_NOTE = "USER_NOTE"


class HandoffItemOrigin(StrEnum):
    VERIFIED_RECORD = "VERIFIED_RECORD"
    USER_SUPPLIED = "USER_SUPPLIED"


class HandoffItem(KernelModel):
    category: HandoffItemCategory
    origin: HandoffItemOrigin
    authority: AuthorityType
    evidence_refs: tuple[NonBlankStr, ...] = Field(min_length=1)
    inferential_query_id: NonBlankStr
    predicate_ids: tuple[NonBlankStr, ...] = ()
    question_ids: tuple[NonBlankStr, ...] = ()
    user_note: NonBlankStr | None = None

    @model_validator(mode="after")
    def _structured_lineage_only(self) -> Self:
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("handoff evidence refs contain duplicates")
        if len(set(self.predicate_ids)) != len(self.predicate_ids):
            raise ValueError("handoff predicate IDs contain duplicates")
        if len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError("handoff question IDs contain duplicates")
        if self.category is HandoffItemCategory.USER_NOTE:
            if self.origin is not HandoffItemOrigin.USER_SUPPLIED or self.authority in {
                AuthorityType.SYSTEM_INFERENCE,
                AuthorityType.RULE_DERIVATION,
            }:
                raise ValueError("USER_NOTE must retain human user-supplied authority")
            if self.user_note is None or self.predicate_ids or self.question_ids:
                raise ValueError("USER_NOTE carries only explicitly human-supplied text")
            return self
        if self.origin is not HandoffItemOrigin.VERIFIED_RECORD:
            raise ValueError("structured handoff constraints require VERIFIED_RECORD origin")
        if self.user_note is not None:
            raise ValueError("verified handoff items cannot carry free text")
        if self.category is HandoffItemCategory.STRUCTURAL_CONSTRAINT:
            if not self.predicate_ids or self.question_ids:
                raise ValueError("structural handoff requires only verified predicate IDs")
        elif self.category is HandoffItemCategory.UNRESOLVED_QUESTION and (
            not self.question_ids or self.predicate_ids
        ):
            raise ValueError("unresolved handoff requires only report question IDs")
        return self


def build_handoff_item(
    *,
    category: HandoffItemCategory,
    origin: HandoffItemOrigin,
    authority: AuthorityType,
    evidence_refs: tuple[str, ...],
    inferential_query_id: str,
    predicate_ids: tuple[str, ...] = (),
    question_ids: tuple[str, ...] = (),
    user_note: str | None = None,
) -> HandoffItem:
    return HandoffItem(
        category=category,
        origin=origin,
        authority=authority,
        evidence_refs=evidence_refs,
        inferential_query_id=inferential_query_id,
        predicate_ids=predicate_ids,
        question_ids=question_ids,
        user_note=user_note,
    )


class ReportDesignContext(StrEnum):
    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"
    RECONCILED = "RECONCILED"
    UNVERIFIED_RETROSPECTIVE = "UNVERIFIED_RETROSPECTIVE"


class ReportDesignRecordContext(KernelModel):
    """Select one source-history lane so planned and executed facts never blend."""

    mode: ReportDesignContext
    planned_design_record: KnowledgeValue[PlannedDesignRecord]
    executed_design_record: KnowledgeValue[ExecutedDesignRecord]
    reconciliation_record: KnowledgeValue[PlanExecutionReconciliation]
    retrospective_source_ids: KnowledgeValue[tuple[NonBlankStr, ...]]

    @model_validator(mode="after")
    def _mode_contract(self) -> Self:
        states = {
            "planned": self.planned_design_record.knowledge_state,
            "executed": self.executed_design_record.knowledge_state,
            "reconciliation": self.reconciliation_record.knowledge_state,
            "retrospective": self.retrospective_source_ids.knowledge_state,
        }
        present = KnowledgeState.PRESENT
        not_applicable = KnowledgeState.NOT_APPLICABLE
        expected = {
            ReportDesignContext.PLANNED: {
                "planned": present,
                "executed": not_applicable,
                "reconciliation": not_applicable,
                "retrospective": not_applicable,
            },
            ReportDesignContext.EXECUTED: {
                "planned": present,
                "executed": present,
                "reconciliation": not_applicable,
                "retrospective": not_applicable,
            },
            ReportDesignContext.RECONCILED: {
                "planned": present,
                "executed": present,
                "reconciliation": present,
                "retrospective": not_applicable,
            },
            ReportDesignContext.UNVERIFIED_RETROSPECTIVE: {
                "planned": not_applicable,
                "executed": not_applicable,
                "reconciliation": not_applicable,
                "retrospective": present,
            },
        }[self.mode]
        if states != expected:
            raise ValueError(f"report design references conflict with {self.mode.value} mode")
        plan = self.planned_design_record.value
        execution = self.executed_design_record.value
        reconciliation = self.reconciliation_record.value
        if plan is not None:
            PlannedDesignRecord.model_validate(plan.model_dump(mode="python"))
        if execution is not None:
            ExecutedDesignRecord.model_validate(execution.model_dump(mode="python"))
        if reconciliation is not None:
            PlanExecutionReconciliation.model_validate(reconciliation.model_dump(mode="python"))
        if (
            plan is not None
            and execution is not None
            and (
                execution.planned_design_id != plan.plan_id
                or execution.planned_design_checksum != plan.content_checksum
            )
        ):
            raise ValueError("executed report record does not pin the embedded plan")
        if reconciliation is not None and (
            plan is None
            or execution is None
            or reconciliation.planned_design_id != plan.plan_id
            or reconciliation.planned_design_checksum != plan.content_checksum
            or reconciliation.executed_design_id != execution.execution_id
            or reconciliation.executed_design_checksum != execution.content_checksum
        ):
            raise ValueError("reconciliation report record does not pin its embedded records")
        return self


def epistemic_boundary_for_context(mode: ReportDesignContext) -> str:
    return {
        ReportDesignContext.PLANNED: PLANNED_EPISTEMIC_BOUNDARY,
        ReportDesignContext.EXECUTED: EXECUTED_EPISTEMIC_BOUNDARY,
        ReportDesignContext.RECONCILED: RECONCILED_EPISTEMIC_BOUNDARY,
        ReportDesignContext.UNVERIFIED_RETROSPECTIVE: RETROSPECTIVE_EPISTEMIC_BOUNDARY,
    }[mode]


def _ordered_addressed_union[T](
    groups: tuple[tuple[T, ...], ...],
    *,
    identifier: str,
    label: str,
) -> tuple[T, ...]:
    ordered: list[T] = []
    by_id: dict[object, T] = {}
    for group in groups:
        for item in group:
            item_id = getattr(item, identifier)
            previous = by_id.get(item_id)
            if previous is None:
                by_id[item_id] = item
                ordered.append(item)
            elif previous != item:
                raise ValueError(f"shared {label} ID has conflicting content: {item_id}")
    return tuple(ordered)


class ReportQuestion(KernelModel):
    question_id: NonBlankStr
    inferential_query_id: NonBlankStr
    text: NonBlankStr
    evidence_required: tuple[NonBlankStr, ...] = Field(min_length=1)
    primary: bool


class ConflictRecord(KernelModel):
    """Unresolved evidence conflict retained without selecting a preferred value."""

    conflict_id: NonBlankStr
    inferential_query_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    affected_claim_ids: KnowledgeValue[tuple[NonBlankStr, ...]]
    evidence_record_ids: tuple[NonBlankStr, ...] = Field(min_length=2)
    retained_values: tuple[JsonValue, ...] = Field(min_length=2)
    rationale: NonBlankStr

    @model_validator(mode="after")
    def _retains_distinct_supported_alternatives(self) -> Self:
        if len(set(self.inferential_query_ids)) != len(self.inferential_query_ids):
            raise ValueError("conflict query IDs contain duplicates")
        if self.affected_claim_ids.knowledge_state not in {
            KnowledgeState.PRESENT,
            KnowledgeState.ABSENT_EXPLICIT,
            KnowledgeState.UNKNOWN,
        }:
            raise ValueError(
                "conflict affected claims must be PRESENT, explicitly absent, or UNKNOWN"
            )
        affected_claim_ids = self.affected_claim_ids.value or ()
        if len(set(affected_claim_ids)) != len(affected_claim_ids):
            raise ValueError("conflict affected claim IDs contain duplicates")
        if len(set(self.evidence_record_ids)) != len(self.evidence_record_ids):
            raise ValueError("conflict evidence IDs contain duplicates")
        if not set(self.affected_claim_ids.evidence_ids).issubset(self.evidence_record_ids):
            raise ValueError("conflict affected-claim evidence is outside the conflict record")
        if len({content_checksum(value) for value in self.retained_values}) < 2:
            raise ValueError("conflict requires at least two distinct retained values")
        for value in self.retained_values:
            ensure_unambiguous_scientific_payload(value)
        return self


class VerifiedPipelineContext(KernelModel):
    """Content-addressed request/result pair re-executed at report construction."""

    context_id: NonBlankStr
    content_checksum: Sha256
    request_payload: dict[NonBlankStr, JsonValue]
    result_payload: dict[NonBlankStr, JsonValue]
    conformance_bundle_payload: dict[NonBlankStr, JsonValue]
    conformance_bundle_checksum: Sha256

    @property
    def request(self) -> V8PipelineRequest:
        from ntruth.pipeline_v8 import V8PipelineRequest

        return V8PipelineRequest.model_validate(self.request_payload)

    @property
    def result(self) -> V8PipelineResult:
        from ntruth.pipeline_v8 import V8PipelineResult

        return V8PipelineResult.model_validate(self.result_payload)

    @property
    def conformance_bundle(self) -> ConformanceBundle:
        from ntruth.derivation_theory.contracts import ConformanceBundle

        return ConformanceBundle.model_validate(self.conformance_bundle_payload)

    @model_validator(mode="after")
    def _addressed_context(self) -> Self:
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"context_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("verified pipeline context checksum mismatch")
        if self.context_id != f"PIPELINE-CONTEXT-{expected[:20]}":
            raise ValueError("verified pipeline context ID mismatch")
        expected_bundle_checksum = content_checksum(self.conformance_bundle.model_dump(mode="json"))
        if self.conformance_bundle_checksum != expected_bundle_checksum:
            raise ValueError("verified pipeline context conformance bundle checksum mismatch")
        from ntruth.pipeline_v8 import run_v8_pipeline

        try:
            verified = run_v8_pipeline(
                self.request,
                conformance_bundle=self.conformance_bundle,
            )
        except ValueError as exc:
            raise ValueError("verified pipeline context request failed Task4 verification") from exc
        if verified != self.result:
            raise ValueError("verified pipeline context result differs from Task4 re-execution")
        return self


class QueryReportSection(KernelModel):
    """Complete query-local projection; no axis may be borrowed from another query."""

    inferential_query: InferentialQuery
    claim_set: DerivedClaimSet
    adequacy_evaluations: tuple[DesignAdequacyEvaluation, ...] = Field(min_length=1)
    count_record_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    scenario_coverages: tuple[ScenarioCoverage, ...] = Field(min_length=1)
    profile_coverage: ProfileCoverageStatement
    ai_candidates: KnowledgeValue[tuple[ParserCandidateOutput, ...]]
    human_confirmations: KnowledgeValue[tuple[ConfirmationEvent, ...]]
    conflicts: KnowledgeValue[tuple[ConflictRecord, ...]]
    sensitivities: KnowledgeValue[tuple[SensitivityRecord, ...]]
    questions: tuple[ReportQuestion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_query_only(self) -> Self:
        query_id = self.inferential_query.id
        if self.claim_set.inferential_query_id != query_id:
            raise ValueError("query section claim set belongs to another query")
        if any(item.inferential_query_id != query_id for item in self.adequacy_evaluations):
            raise ValueError("query section adequacy belongs to another query")
        if any(item.inferential_query_id != query_id for item in self.questions):
            raise ValueError("query section question belongs to another query")
        if sum(question.primary for question in self.questions) != 1:
            raise ValueError("each query section requires exactly one primary question")
        for label, value in (
            ("AI candidate", self.ai_candidates),
            ("confirmation", self.human_confirmations),
            ("conflict", self.conflicts),
            ("sensitivity", self.sensitivities),
        ):
            if value.query_scope_id != query_id:
                raise ValueError(f"query section {label} scope belongs to another query")
        if self.profile_coverage.profile_id != self.inferential_query.profile_id:
            raise ValueError("query section profile coverage belongs to another profile")
        if any(
            item.profile_id != self.inferential_query.profile_id for item in self.scenario_coverages
        ):
            raise ValueError("query section scenario coverage belongs to another profile")
        return self


def _empty_or_scoped_knowledge[T](
    value: KnowledgeValue[tuple[T, ...]],
    *,
    query_id: str,
    selected: tuple[T, ...] | None = None,
    selected_evidence_ids: tuple[str, ...] | None = None,
) -> KnowledgeValue[tuple[T, ...]]:
    """Create an exact query-local projection without inventing missing evidence."""

    if value.knowledge_state is KnowledgeState.PRESENT:
        items = value.value or () if selected is None else selected
        if not items:
            raise ValueError(f"PRESENT report axis has no records for inferential query {query_id}")
        payload = value.model_dump(mode="python")
        payload.update(value=items, query_scope_id=query_id, claim_scope_id=None)
        if selected_evidence_ids is not None:
            payload["evidence_ids"] = selected_evidence_ids
        return KnowledgeValue[tuple[T, ...]].model_validate(payload)
    if value.knowledge_state is KnowledgeState.CONFLICTING:
        raise ValueError("CONFLICTING aggregate axes require a reviewed query projection")
    payload = value.model_dump(mode="python")
    payload["query_scope_id"] = query_id
    payload["claim_scope_id"] = None
    return KnowledgeValue[tuple[T, ...]].model_validate(payload)


def _parser_candidate_identity_ids(candidate: ParserCandidateOutput) -> tuple[str, ...]:
    """Return every identity-bearing parser record ID without deriving science."""

    return (
        *(item.block_id for item in candidate.experiment_blocks),
        *(item.evidence_id for item in candidate.evidence_spans),
        *(item.node_id for item in candidate.candidate_nodes),
        *(item.edge_id for item in candidate.candidate_edges),
        *(item.factor_id for item in candidate.factors),
        *(item.endpoint_id for item in candidate.endpoints),
        *(item.contrast_id for item in candidate.contrasts),
        *(item.estimand_id for item in candidate.candidate_estimands),
        *(item.count_id for item in candidate.candidate_counts),
        *(item.event_id for item in candidate.candidate_events),
        *(item.graph_id for item in candidate.candidate_graphs),
        *(item.alternative_id for item in candidate.alternatives),
        *(item.question_id for item in candidate.clarification_questions),
    )


def _normalize_query_candidate_sets(
    value: (
        KnowledgeValue[tuple[ParserCandidateOutput, ...]]
        | tuple[KnowledgeValue[tuple[ParserCandidateOutput, ...]], ...]
    ),
    *,
    query_ids: tuple[str, ...],
) -> tuple[KnowledgeValue[tuple[ParserCandidateOutput, ...]], ...]:
    """Normalize the legacy single-query wrapper into exact query-keyed records."""

    raw_items = (value,) if isinstance(value, KnowledgeValue) else value
    checked = tuple(
        KnowledgeValue[tuple[ParserCandidateOutput, ...]].model_validate(
            item.model_dump(mode="python")
        )
        for item in raw_items
    )
    candidate_query_ids = tuple(item.query_scope_id for item in checked)
    if candidate_query_ids != query_ids:
        raise ValueError(
            "AI candidate sets must map one-to-one and in order to every inferential query"
        )
    identity_ids = tuple(
        identity_id
        for item in checked
        for candidate in item.value or ()
        for identity_id in _parser_candidate_identity_ids(candidate)
    )
    if len(identity_ids) != len(set(identity_ids)):
        raise ValueError("candidate IDs must be globally unique across query-scoped outputs")
    return checked


class StatisticalHandoff(KernelModel):
    strategy_module_status: Literal[StrategyModuleStatus.HANDOFF_ONLY] = (
        StrategyModuleStatus.HANDOFF_ONLY
    )
    items: tuple[HandoffItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _has_question_and_structure(self) -> Self:
        categories = {item.category for item in self.items}
        if HandoffItemCategory.STRUCTURAL_CONSTRAINT not in categories:
            raise ValueError("statistical handoff requires a structural constraint")
        if HandoffItemCategory.UNRESOLVED_QUESTION not in categories:
            raise ValueError("statistical handoff requires an unresolved question")
        return self


def build_verified_pipeline_context(
    *,
    request: V8PipelineRequest,
    result: V8PipelineResult,
    conformance_bundle: ConformanceBundle,
) -> VerifiedPipelineContext:
    """Re-execute Task 4 and bind the exact request/result bytes or fail closed."""

    from ntruth.pipeline_v8 import run_v8_pipeline

    try:
        verified = run_v8_pipeline(request, conformance_bundle=conformance_bundle)
    except ValueError as exc:
        raise ValueError("verified pipeline context request failed Task4 verification") from exc
    if verified != result:
        raise ValueError("verified pipeline context result differs from Task4 re-execution")
    fields: dict[str, Any] = {
        "request_payload": request.model_dump(mode="json"),
        "result_payload": result.model_dump(mode="json"),
        "conformance_bundle_payload": conformance_bundle.model_dump(
            mode="json", exclude_unset=True
        ),
        "conformance_bundle_checksum": content_checksum(conformance_bundle.model_dump(mode="json")),
    }
    draft = VerifiedPipelineContext.model_construct(
        context_id="PIPELINE-CONTEXT-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"context_id", "content_checksum"})
    )
    return VerifiedPipelineContext(
        context_id=f"PIPELINE-CONTEXT-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def resolve_report_claim_sets(
    claim_sets: tuple[DerivedClaimSet, ...],
) -> ReportResolutionOutcome:
    """Resolve one query only; multi-query aggregation remains SRR-V8-014."""

    if not claim_sets:
        raise ValueError("report resolution requires at least one claim set")
    checked_claim_sets = tuple(
        DerivedClaimSet.model_validate(item.model_dump(mode="python")) for item in claim_sets
    )
    query_ids = [item.inferential_query_id for item in checked_claim_sets]
    if len(set(query_ids)) != len(query_ids):
        raise ValueError("report resolution contains duplicate query claim sets")
    claim_ids = [claim.claim_id for claim_set in checked_claim_sets for claim in claim_set.claims]
    if len(set(claim_ids)) != len(claim_ids):
        raise ValueError("report resolution contains globally duplicate claim IDs")
    if len(checked_claim_sets) == 1:
        outcome = TrivialExplicitReportResolutionPolicy().resolve(checked_claim_sets[0])
        if outcome.resolution.query_scope_id != query_ids[0]:
            raise ValueError("single-query resolution must retain its exact query scope")
        return outcome
    from ntruth.schemas.support import ScientificReviewRequirement

    return ReportResolutionOutcome(
        policy_version=MULTI_QUERY_POLICY_VERSION,
        resolution=KnowledgeValue(
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=(
                "No reviewed evaluator exists for aggregation across multiple "
                "InferentialQuery claim sets."
            ),
            claim_scope_id="REPORT-GLOBAL-MULTI-QUERY",
        ),
        review_requirement=ScientificReviewRequirement(
            issue_id=REPORT_AGGREGATION_REVIEW_ISSUE_ID,
            rationale="Global multi-query report resolution requires scientific review.",
        ),
    )


class ReportBundle(KernelModel):
    report_id: NonBlankStr
    content_checksum: Sha256
    verified_pipeline_contexts: tuple[VerifiedPipelineContext, ...] = Field(min_length=1)
    query_sections: tuple[QueryReportSection, ...] = Field(min_length=1)
    design_record_context: ReportDesignRecordContext
    prospective_input_ledgers: KnowledgeValue[tuple[ProspectiveInputLedger, ...]]
    source_records: tuple[SourceRecord, ...] = Field(min_length=1)
    evidence_records: tuple[EvidenceRecord, ...] = Field(min_length=1)
    ai_candidates: tuple[KnowledgeValue[tuple[ParserCandidateOutput, ...]], ...] = Field(
        min_length=1
    )
    human_confirmations: KnowledgeValue[tuple[ConfirmationEvent, ...]]
    conflicts: KnowledgeValue[tuple[ConflictRecord, ...]]
    confirmed_graph: V8ExperimentGraph
    claim_sets: tuple[DerivedClaimSet, ...] = Field(min_length=1)
    report_resolution: ReportResolutionOutcome
    design_adequacy_evaluations: tuple[DesignAdequacyEvaluation, ...] = Field(min_length=1)
    count_registry: CanonicalCountRegistry
    scenario_coverages: tuple[ScenarioCoverage, ...] = Field(min_length=1)
    sensitivities: KnowledgeValue[tuple[SensitivityRecord, ...]]
    questions: tuple[ReportQuestion, ...] = Field(min_length=1)
    statistical_handoff: StatisticalHandoff
    strategy_module_status: Literal[StrategyModuleStatus.HANDOFF_ONLY] = (
        StrategyModuleStatus.HANDOFF_ONLY
    )
    profile_coverage: ProfileCoverageStatement
    inference_limits: tuple[NonBlankStr, ...] = Field(min_length=1)
    epistemic_boundary: NonBlankStr
    execution_manifest: V8ExecutionManifest

    @property
    def count_records(self) -> tuple[CanonicalCountRecord, ...]:
        """Read-only compatibility projection; the registry is the sole stored contract."""

        return self.count_registry.records

    @field_validator("ai_candidates", mode="before")
    @classmethod
    def _migrate_single_query_candidate_wrapper(cls, value: object) -> object:
        """Accept the pre-fix single-query shape only as an explicit one-item migration."""

        if isinstance(value, KnowledgeValue):
            return (value,)
        if isinstance(value, dict) and "knowledge_state" in value:
            return (value,)
        return value

    @model_validator(mode="after")
    def _neutral_cross_contract_integrity(self) -> Self:
        for context in self.verified_pipeline_contexts:
            VerifiedPipelineContext.model_validate(context.model_dump(mode="python"))
        source_ids = [source.source_id for source in self.source_records]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("ReportBundle contains duplicate source records")
        evidence_ids = [record.evidence_id for record in self.evidence_records]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("ReportBundle contains duplicate evidence records")
        known_sources = set(source_ids)
        known_evidence = set(evidence_ids)
        if any(record.source_id not in known_sources for record in self.evidence_records):
            raise ValueError("ReportBundle evidence references an unknown source")
        for label, value in (
            ("prospective_input_ledgers", self.prospective_input_ledgers),
            ("human_confirmations", self.human_confirmations),
            ("conflicts", self.conflicts),
            ("sensitivities", self.sensitivities),
        ):
            if not set(value.evidence_ids).issubset(known_evidence):
                raise ValueError(f"ReportBundle {label} has dangling evidence IDs")
            if not set(value.source_scope_ids).issubset(known_sources):
                raise ValueError(f"ReportBundle {label} has dangling source-scope IDs")
        for candidate_set in self.ai_candidates:
            if not set(candidate_set.evidence_ids).issubset(known_evidence):
                raise ValueError("ReportBundle ai_candidates has dangling evidence IDs")
            if not set(candidate_set.source_scope_ids).issubset(known_sources):
                raise ValueError("ReportBundle ai_candidates has dangling source-scope IDs")
        for label, design_value in (
            ("planned_design_record", self.design_record_context.planned_design_record),
            ("executed_design_record", self.design_record_context.executed_design_record),
            ("reconciliation_record", self.design_record_context.reconciliation_record),
            ("retrospective_source_ids", self.design_record_context.retrospective_source_ids),
        ):
            if not set(design_value.evidence_ids).issubset(known_evidence):
                raise ValueError(f"ReportBundle {label} has dangling evidence IDs")
            if not set(design_value.source_scope_ids).issubset(known_sources):
                raise ValueError(f"ReportBundle {label} has dangling source-scope IDs")
        if self.design_record_context.mode is ReportDesignContext.UNVERIFIED_RETROSPECTIVE:
            if self.prospective_input_ledgers.knowledge_state is not KnowledgeState.NOT_APPLICABLE:
                raise ValueError("retrospective report cannot imply a prospective input ledger")
        else:
            if self.prospective_input_ledgers.knowledge_state is not KnowledgeState.PRESENT:
                raise ValueError("planned/executed report requires addressed input ledgers")
            ledgers = self.prospective_input_ledgers.value or ()
            if len(ledgers) != len(self.verified_pipeline_contexts):
                raise ValueError("every verified pipeline context requires one input ledger")
            for ledger, context in zip(ledgers, self.verified_pipeline_contexts, strict=True):
                checked = ProspectiveInputLedger.model_validate(ledger.model_dump(mode="python"))
                if checked.request != context.request:
                    raise ValueError("input ledger request differs from verified Task4 context")
            ledger_sources = _ordered_addressed_union(
                tuple(ledger.sources for ledger in ledgers),
                identifier="source_id",
                label="source",
            )
            ledger_evidence = _ordered_addressed_union(
                tuple(ledger.evidence_records for ledger in ledgers),
                identifier="evidence_id",
                label="evidence",
            )
            if set(self.prospective_input_ledgers.evidence_ids) != {
                record.evidence_id for record in ledger_evidence
            }:
                raise ValueError("prospective ledger evidence projection is not exact")
            ledger_confirmations = _ordered_addressed_union(
                tuple(ledger.confirmation_events for ledger in ledgers),
                identifier="event_id",
                label="confirmation",
            )
            execution = self.design_record_context.executed_design_record.value
            if execution is not None:
                checked_execution = ExecutedDesignRecord.model_validate(
                    execution.model_dump(mode="python")
                )
                executed_ledger = checked_execution.executed_input_ledger
                report_sources = _ordered_addressed_union(
                    (ledger_sources, executed_ledger.sources),
                    identifier="source_id",
                    label="source",
                )
                report_evidence = _ordered_addressed_union(
                    (ledger_evidence, executed_ledger.evidence_records),
                    identifier="evidence_id",
                    label="evidence",
                )
                report_confirmations = _ordered_addressed_union(
                    (ledger_confirmations, executed_ledger.confirmation_events),
                    identifier="event_id",
                    label="confirmation",
                )
            else:
                report_sources = ledger_sources
                report_evidence = ledger_evidence
                report_confirmations = ledger_confirmations
            if self.source_records != report_sources or self.evidence_records != report_evidence:
                raise ValueError("report source/evidence projection differs from input ledgers")
            if report_confirmations:
                if (
                    self.human_confirmations.knowledge_state is not KnowledgeState.PRESENT
                    or self.human_confirmations.value != report_confirmations
                ):
                    raise ValueError("report confirmations differ from input ledgers")
            elif self.human_confirmations.knowledge_state is KnowledgeState.PRESENT:
                raise ValueError("report invents confirmations absent from input ledgers")
            plan = self.design_record_context.planned_design_record.value
            if plan is None:
                raise ValueError("non-retrospective report requires an embedded plan")
            if (
                plan.experiment_block_id
                != self.verified_pipeline_contexts[0].request.experiment_block_id
            ):
                raise ValueError("embedded plan uses a different Experiment Block")
            if plan.inferential_queries != tuple(
                context.request.query for context in self.verified_pipeline_contexts
            ):
                raise ValueError("embedded plan queries differ from verified Task4 requests")
            if any(
                plan.event_registry != context.request.causal_aggregate.event_registry
                for context in self.verified_pipeline_contexts
            ):
                raise ValueError("embedded plan events differ from verified Task4 requests")
            registry_by_id = {record.count_id: record for record in self.count_registry.records}
            if any(registry_by_id.get(record.count_id) != record for record in plan.count_records):
                raise ValueError("embedded planned counts differ from the verified registry")
            if (
                plan.sources != ledger_sources
                or plan.evidence_records != ledger_evidence
                or plan.confirmation_events != ledger_confirmations
            ):
                raise ValueError("embedded plan provenance differs from input ledgers")
            artifact_ids = {
                artifact.artifact_id for ledger in ledgers for artifact in ledger.artifacts
            }
            if not {
                plan.sample_sheet_ref,
                plan.methods_draft_ref,
                plan.id_convention_ref,
            }.issubset(artifact_ids):
                raise ValueError("embedded plan artifact pins differ from input ledgers")
            if execution is not None:
                if any(
                    execution.event_registry != context.request.causal_aggregate.event_registry
                    for context in self.verified_pipeline_contexts
                ):
                    raise ValueError("embedded execution events differ from Task4 requests")
                if any(
                    registry_by_id.get(record.count_id) != record
                    for record in execution.count_records
                ):
                    raise ValueError("embedded execution counts differ from verified registry")
                if (
                    execution.sources != execution.executed_input_ledger.sources
                    or execution.evidence_records
                    != execution.executed_input_ledger.evidence_records
                ):
                    raise ValueError("embedded execution differs from its addressed ledger")
        if self.human_confirmations.knowledge_state is KnowledgeState.PRESENT and any(
            not set(event.evidence_refs).issubset(known_evidence)
            for event in self.human_confirmations.value or ()
        ):
            raise ValueError("ReportBundle confirmation has dangling evidence refs")
        if self.human_confirmations.knowledge_state is KnowledgeState.PRESENT and (
            self.human_confirmations.evidence_ids
            != tuple(
                dict.fromkeys(
                    evidence_id
                    for event in self.human_confirmations.value or ()
                    for evidence_id in event.evidence_refs
                )
            )
        ):
            raise ValueError("ReportBundle confirmation evidence projection is not exact")
        if self.conflicts.knowledge_state is KnowledgeState.PRESENT and any(
            not set(conflict.evidence_record_ids).issubset(known_evidence)
            for conflict in self.conflicts.value or ()
        ):
            raise ValueError("ReportBundle conflict has dangling evidence refs")
        if self.conflicts.knowledge_state is KnowledgeState.PRESENT and (
            self.conflicts.evidence_ids
            != tuple(
                dict.fromkeys(
                    evidence_id
                    for conflict in self.conflicts.value or ()
                    for evidence_id in conflict.evidence_record_ids
                )
            )
        ):
            raise ValueError("ReportBundle conflict evidence projection is not exact")
        if any(
            not set(item.evidence_refs).issubset(known_evidence)
            for item in self.statistical_handoff.items
        ):
            raise ValueError("ReportBundle handoff item has dangling evidence refs")
        query_ids = [claim_set.inferential_query_id for claim_set in self.claim_sets]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("ReportBundle contains duplicate claim sets for a query")
        checked_candidate_sets = _normalize_query_candidate_sets(
            self.ai_candidates,
            query_ids=tuple(query_ids),
        )
        if checked_candidate_sets != self.ai_candidates:
            raise ValueError("ReportBundle AI candidate sets are not canonical")
        known_queries = set(query_ids)
        all_claims = tuple(claim for claim_set in self.claim_sets for claim in claim_set.claims)
        claims_by_id = {claim.claim_id: claim for claim in all_claims}
        if len(claims_by_id) != len(all_claims):
            raise ValueError("ReportBundle contains globally duplicate claim IDs")
        if self.conflicts.knowledge_state is KnowledgeState.PRESENT and any(
            not set(record.inferential_query_ids).issubset(known_queries)
            for record in self.conflicts.value or ()
        ):
            raise ValueError("ReportBundle conflict references a query outside the report")
        if self.conflicts.knowledge_state is KnowledgeState.PRESENT:
            conflict_ids = [record.conflict_id for record in self.conflicts.value or ()]
            if len(set(conflict_ids)) != len(conflict_ids):
                raise ValueError("ReportBundle contains duplicate conflict IDs")
            linked_conflict_claim_ids: set[str] = set()
            for conflict_record in self.conflicts.value or ():
                affected_state = conflict_record.affected_claim_ids.knowledge_state
                if affected_state is KnowledgeState.ABSENT_EXPLICIT:
                    continue
                if affected_state is not KnowledgeState.PRESENT:
                    raise ValueError(
                        "SCIENTIFIC_REVIEW_REQUIRED: conflict-to-claim materiality is UNKNOWN"
                    )
                affected_claim_ids = conflict_record.affected_claim_ids.value or ()
                unknown_claim_ids = set(affected_claim_ids) - claims_by_id.keys()
                if unknown_claim_ids:
                    raise ValueError("ReportBundle conflict references an unknown derived claim")
                affected_claims = tuple(claims_by_id[claim_id] for claim_id in affected_claim_ids)
                affected_queries = {claim.inferential_query_id for claim in affected_claims}
                if affected_queries != set(conflict_record.inferential_query_ids):
                    raise ValueError(
                        "ReportBundle conflict query IDs differ from its exact affected-claim "
                        "projection"
                    )
                if any(
                    claim.determinability_state is not DeterminabilityState.CONFLICTING_INFORMATION
                    for claim in affected_claims
                ):
                    raise ValueError(
                        "SCIENTIFIC_REVIEW_REQUIRED: material conflicts must drive every "
                        "affected claim to CONFLICTING_INFORMATION before report resolution"
                    )
                linked_conflict_claim_ids.update(affected_claim_ids)
            conflicting_claim_ids = {
                claim.claim_id
                for claim in all_claims
                if claim.determinability_state is DeterminabilityState.CONFLICTING_INFORMATION
            }
            if linked_conflict_claim_ids != conflicting_claim_ids:
                raise ValueError(
                    "ReportBundle conflict-to-claim linkage is not exact and bidirectional"
                )
        elif any(
            claim.determinability_state is DeterminabilityState.CONFLICTING_INFORMATION
            for claim in all_claims
        ):
            raise ValueError(
                "SCIENTIFIC_REVIEW_REQUIRED: conflicting claims require typed ConflictRecord "
                "lineage"
            )
        sensitivity_by_id = {
            record.sensitivity_id: record for record in self.sensitivities.value or ()
        }
        if len(sensitivity_by_id) != len(self.sensitivities.value or ()):
            raise ValueError("ReportBundle contains duplicate sensitivity IDs")
        if self.human_confirmations.knowledge_state is KnowledgeState.PRESENT and any(
            not set(event.sensitivity_record_ids).issubset(sensitivity_by_id)
            for event in self.human_confirmations.value or ()
        ):
            raise ValueError("ReportBundle confirmation has dangling sensitivity refs")
        if self.sensitivities.knowledge_state is KnowledgeState.PRESENT:
            for record in self.sensitivities.value or ():
                claim = claims_by_id.get(record.derived_claim_id)
                if claim is None:
                    raise ValueError("ReportBundle sensitivity references an unknown derived claim")
                traced_predicates = {
                    reference.predicate_id
                    for step in claim.proof_trace
                    for reference in step.predicate_references
                }
                if record.decisive_predicate_id not in (
                    set(claim.required_predicates) & traced_predicates
                ):
                    raise ValueError(
                        "sensitivity decisive predicate is not in the derived claim proof"
                    )
                if record.sensitivity_id not in claim.sensitivity_records:
                    raise ValueError("sensitivity lacks bidirectional derived-claim linkage")
        for claim in claims_by_id.values():
            for sensitivity_id in claim.sensitivity_records:
                linked_record = sensitivity_by_id.get(sensitivity_id)
                if linked_record is None or linked_record.derived_claim_id != claim.claim_id:
                    raise ValueError("derived claim has dangling bidirectional sensitivity")
        context_query_ids = [item.request.query.id for item in self.verified_pipeline_contexts]
        section_query_ids = [item.inferential_query.id for item in self.query_sections]
        if query_ids != context_query_ids or query_ids != section_query_ids:
            raise ValueError("claim, verified-context and query-section order must match exactly")
        if any(
            context.result.claim_set != claim_set
            for context, claim_set in zip(
                self.verified_pipeline_contexts, self.claim_sets, strict=True
            )
        ):
            raise ValueError("report claims differ from verified pipeline lineage")
        if any(
            context.request.graph != self.confirmed_graph
            for context in self.verified_pipeline_contexts
        ):
            raise ValueError("report graph differs from verified pipeline lineage")
        if any(
            context.request.count_registry != self.count_registry
            for context in self.verified_pipeline_contexts
        ):
            raise ValueError("report count registry differs from verified pipeline lineage")
        if any(
            context.result.execution_manifest != self.execution_manifest
            for context in self.verified_pipeline_contexts
        ):
            raise ValueError("report execution manifest differs from verified pipeline lineage")
        expected_adequacy = tuple(
            evaluation
            for context in self.verified_pipeline_contexts
            for evaluation in context.result.design_adequacy_evaluations
        )
        expected_scenarios = tuple(
            coverage
            for context in self.verified_pipeline_contexts
            for coverage in context.result.scenario_coverages
        )
        if self.design_adequacy_evaluations != expected_adequacy:
            raise ValueError("report adequacy differs from verified pipeline lineage")
        if self.scenario_coverages != expected_scenarios:
            raise ValueError("report scenario coverage differs from verified pipeline lineage")
        candidates_by_query = {item.query_scope_id: item for item in self.ai_candidates}
        for context, section in zip(
            self.verified_pipeline_contexts, self.query_sections, strict=True
        ):
            query_id = context.request.query.id
            expected_count_ids = tuple(
                item.count_id for item in self.count_registry.records_for_query(query_id)
            )
            expected_candidates = candidates_by_query[query_id]
            expected_confirmations = _empty_or_scoped_knowledge(
                self.human_confirmations,
                query_id=query_id,
                selected=tuple(
                    event
                    for event in self.human_confirmations.value or ()
                    if event.confirmed_value.query_scope_id == query_id
                ),
                selected_evidence_ids=tuple(
                    dict.fromkeys(
                        evidence_id
                        for event in self.human_confirmations.value or ()
                        if event.confirmed_value.query_scope_id == query_id
                        for evidence_id in event.evidence_refs
                    )
                ),
            )
            expected_conflicts = _empty_or_scoped_knowledge(
                self.conflicts,
                query_id=query_id,
                selected=tuple(
                    item
                    for item in self.conflicts.value or ()
                    if query_id in item.inferential_query_ids
                ),
                selected_evidence_ids=tuple(
                    dict.fromkeys(
                        evidence_id
                        for item in self.conflicts.value or ()
                        if query_id in item.inferential_query_ids
                        for evidence_id in item.evidence_record_ids
                    )
                ),
            )
            expected_sensitivities = _empty_or_scoped_knowledge(
                self.sensitivities,
                query_id=query_id,
                selected=tuple(
                    item
                    for item in self.sensitivities.value or ()
                    if claims_by_id.get(item.derived_claim_id) is not None
                    and claims_by_id[item.derived_claim_id].inferential_query_id == query_id
                ),
            )
            expected_questions = tuple(
                question for question in self.questions if question.inferential_query_id == query_id
            )
            if section.questions != expected_questions:
                raise ValueError("query questions differ from the exact global projection")
            if (
                section.inferential_query != context.request.query
                or section.claim_set != context.result.claim_set
                or section.adequacy_evaluations != context.result.design_adequacy_evaluations
                or section.count_record_ids != expected_count_ids
                or section.scenario_coverages != context.result.scenario_coverages
                or section.profile_coverage != context.result.profile_coverage
                or section.ai_candidates != expected_candidates
                or section.human_confirmations != expected_confirmations
                or section.conflicts != expected_conflicts
                or section.sensitivities != expected_sensitivities
            ):
                raise ValueError("query report section differs from its verified context")
        if self.design_record_context.mode is ReportDesignContext.UNVERIFIED_RETROSPECTIVE:
            retrospective_ids = set(self.design_record_context.retrospective_source_ids.value or ())
            if not retrospective_ids.issubset(source_ids):
                raise ValueError("retrospective design context references an unknown source")
        addressed_design_sources: set[str] = set()
        for reference in (
            self.design_record_context.planned_design_record,
            self.design_record_context.executed_design_record,
        ):
            if reference.knowledge_state is KnowledgeState.PRESENT and reference.value is not None:
                addressed_design_sources.update(
                    source.source_id for source in reference.value.sources
                )
        if not addressed_design_sources.issubset(known_sources):
            raise ValueError("embedded design record references a source outside the report")
        if any(
            evaluation.inferential_query_id not in known_queries
            for evaluation in self.design_adequacy_evaluations
        ):
            raise ValueError("adequacy evaluation is outside the report claim queries")
        if any(count.scope.query_id not in known_queries for count in self.count_registry.records):
            raise ValueError("count record is outside the report claim queries")
        if any(question.inferential_query_id not in known_queries for question in self.questions):
            raise ValueError("question is outside the report claim queries")
        question_ids = [question.question_id for question in self.questions]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("ReportBundle contains duplicate question IDs")
        if any(
            sum(
                question.primary
                for question in self.questions
                if question.inferential_query_id == query_id
            )
            != 1
            for query_id in known_queries
        ):
            raise ValueError("each inferential query requires exactly one primary question")
        questions_by_id = {question.question_id: question for question in self.questions}
        predicates_by_query = {
            query_id: {
                predicate_id
                for claim_set in self.claim_sets
                if claim_set.inferential_query_id == query_id
                for claim in claim_set.claims
                for predicate_id in claim.required_predicates
            }
            for query_id in known_queries
        }
        predicate_evidence_by_query = {
            query_id: {
                predicate_id: {
                    evidence_id
                    for claim_set in self.claim_sets
                    if claim_set.inferential_query_id == query_id
                    for claim in claim_set.claims
                    for step in claim.proof_trace
                    for reference in step.predicate_references
                    if reference.predicate_id == predicate_id
                    for evidence_id in reference.predicate_value.evidence_ids
                }
                for predicate_id in predicates_by_query[query_id]
            }
            for query_id in known_queries
        }
        for item in self.statistical_handoff.items:
            if item.inferential_query_id not in known_queries:
                raise ValueError("handoff item references a query outside the report")
            if not set(item.predicate_ids).issubset(predicates_by_query[item.inferential_query_id]):
                raise ValueError("handoff structural constraint lacks verified predicate lineage")
            predicate_evidence = {
                evidence_id
                for predicate_id in item.predicate_ids
                for evidence_id in predicate_evidence_by_query[item.inferential_query_id][
                    predicate_id
                ]
            }
            if item.predicate_ids and not set(item.evidence_refs).issubset(predicate_evidence):
                raise ValueError(
                    "handoff structural evidence differs from verified predicate proof"
                )
            if any(
                question_id not in questions_by_id
                or questions_by_id[question_id].inferential_query_id != item.inferential_query_id
                for question_id in item.question_ids
            ):
                raise ValueError("handoff unresolved question lacks exact report-question lineage")
        if any(
            coverage.profile_id != self.profile_coverage.profile_id
            for coverage in self.scenario_coverages
        ):
            raise ValueError("scenario and profile coverage must name the same profile")
        expected_resolution = resolve_report_claim_sets(self.claim_sets)
        if self.report_resolution != expected_resolution:
            raise ValueError(
                "SRR-V8-014: report resolution is not the canonical fail-closed result"
            )
        if self.strategy_module_status is not self.statistical_handoff.strategy_module_status:
            raise ValueError("ReportBundle and statistical handoff strategy status differ")
        if self.epistemic_boundary != epistemic_boundary_for_context(
            self.design_record_context.mode
        ):
            raise ValueError("ReportBundle epistemic boundary conflicts with its source mode")
        expected_checksum = _report_checksum(self)
        if self.content_checksum != expected_checksum:
            raise ValueError("ReportBundle content checksum mismatch")
        if self.report_id != f"REPORT-{expected_checksum[:20]}":
            raise ValueError("ReportBundle ID must be derived from its content checksum")
        return self


def _report_checksum(report: ReportBundle) -> str:
    return content_checksum(
        report.model_dump(mode="json", exclude={"report_id", "content_checksum"})
    )


def build_report_bundle(
    *,
    verified_pipeline_contexts: tuple[VerifiedPipelineContext, ...],
    design_record_context: ReportDesignRecordContext,
    prospective_input_ledgers: KnowledgeValue[tuple[ProspectiveInputLedger, ...]],
    source_records: tuple[SourceRecord, ...],
    evidence_records: tuple[EvidenceRecord, ...],
    ai_candidates: (
        KnowledgeValue[tuple[ParserCandidateOutput, ...]]
        | tuple[KnowledgeValue[tuple[ParserCandidateOutput, ...]], ...]
    ),
    human_confirmations: KnowledgeValue[tuple[ConfirmationEvent, ...]],
    conflicts: KnowledgeValue[tuple[ConflictRecord, ...]],
    sensitivities: KnowledgeValue[tuple[SensitivityRecord, ...]],
    questions: tuple[ReportQuestion, ...],
    statistical_handoff: StatisticalHandoff,
    inference_limits: tuple[str, ...],
) -> ReportBundle:
    """Build a report exclusively from Task4 results reverified at this boundary."""

    if not verified_pipeline_contexts:
        raise ValueError("ReportBundle requires at least one verified pipeline context")
    contexts = tuple(
        VerifiedPipelineContext.model_validate(context.model_dump(mode="python"))
        for context in verified_pipeline_contexts
    )
    query_ids = tuple(context.request.query.id for context in contexts)
    if len(set(query_ids)) != len(query_ids):
        raise ValueError("verified pipeline contexts contain duplicate queries")
    candidate_sets = _normalize_query_candidate_sets(
        ai_candidates,
        query_ids=query_ids,
    )
    candidates_by_query = {item.query_scope_id: item for item in candidate_sets}

    graph = contexts[0].request.graph
    count_registry = contexts[0].request.count_registry
    execution_manifest = contexts[0].result.execution_manifest
    if any(context.request.graph != graph for context in contexts[1:]):
        raise ValueError("verified pipeline contexts do not share one confirmed graph")
    if any(context.request.count_registry != count_registry for context in contexts[1:]):
        raise ValueError("verified pipeline contexts do not share one canonical count registry")
    if any(context.result.execution_manifest != execution_manifest for context in contexts[1:]):
        raise ValueError("verified pipeline contexts do not share one execution manifest")

    if prospective_input_ledgers.knowledge_state is KnowledgeState.PRESENT:
        checked_ledgers = tuple(
            ProspectiveInputLedger.model_validate(item.model_dump(mode="python"))
            for item in prospective_input_ledgers.value or ()
        )
        planned_sources = _ordered_addressed_union(
            tuple(item.sources for item in checked_ledgers),
            identifier="source_id",
            label="source",
        )
        planned_evidence = _ordered_addressed_union(
            tuple(item.evidence_records for item in checked_ledgers),
            identifier="evidence_id",
            label="evidence",
        )
        execution = design_record_context.executed_design_record.value
        if execution is not None:
            checked_execution = ExecutedDesignRecord.model_validate(
                execution.model_dump(mode="python")
            )
            expected_sources = _ordered_addressed_union(
                (planned_sources, checked_execution.executed_input_ledger.sources),
                identifier="source_id",
                label="source",
            )
            expected_evidence = _ordered_addressed_union(
                (planned_evidence, checked_execution.executed_input_ledger.evidence_records),
                identifier="evidence_id",
                label="evidence",
            )
        else:
            expected_sources = planned_sources
            expected_evidence = planned_evidence
        if source_records != expected_sources or evidence_records != expected_evidence:
            raise ValueError("report source/evidence projection differs from addressed ledgers")

    questions_by_query = {
        query_id: tuple(
            question for question in questions if question.inferential_query_id == query_id
        )
        for query_id in query_ids
    }
    if any(not items for items in questions_by_query.values()):
        raise ValueError("every verified query requires at least one report question")
    if any(question.inferential_query_id not in query_ids for question in questions):
        raise ValueError("report question references an unverified query")
    if any(
        sum(question.primary for question in questions_by_query[query_id]) != 1
        for query_id in query_ids
    ):
        raise ValueError("every verified query requires exactly one primary question")

    claim_sets = tuple(context.result.claim_set for context in contexts)
    claims_by_id = {claim.claim_id: claim for claim_set in claim_sets for claim in claim_set.claims}
    if conflicts.knowledge_state is KnowledgeState.PRESENT and any(
        not set(item.inferential_query_ids).issubset(query_ids) for item in conflicts.value or ()
    ):
        raise ValueError("report conflict references a query outside verified queries")
    if sensitivities.knowledge_state is KnowledgeState.PRESENT and any(
        item.derived_claim_id not in claims_by_id for item in sensitivities.value or ()
    ):
        raise ValueError("report sensitivity references an unknown derived claim")
    adequacy_evaluations = tuple(
        evaluation
        for context in contexts
        for evaluation in context.result.design_adequacy_evaluations
    )
    scenario_coverages = tuple(
        coverage for context in contexts for coverage in context.result.scenario_coverages
    )
    query_sections = tuple(
        QueryReportSection(
            inferential_query=context.request.query,
            claim_set=context.result.claim_set,
            adequacy_evaluations=context.result.design_adequacy_evaluations,
            count_record_ids=tuple(
                item.count_id for item in count_registry.records_for_query(context.request.query.id)
            ),
            scenario_coverages=context.result.scenario_coverages,
            profile_coverage=context.result.profile_coverage,
            ai_candidates=candidates_by_query[context.request.query.id],
            human_confirmations=_empty_or_scoped_knowledge(
                human_confirmations,
                query_id=context.request.query.id,
                selected=tuple(
                    event
                    for event in human_confirmations.value or ()
                    if event.confirmed_value.query_scope_id == context.request.query.id
                ),
                selected_evidence_ids=tuple(
                    dict.fromkeys(
                        evidence_id
                        for event in human_confirmations.value or ()
                        if event.confirmed_value.query_scope_id == context.request.query.id
                        for evidence_id in event.evidence_refs
                    )
                ),
            ),
            conflicts=_empty_or_scoped_knowledge(
                conflicts,
                query_id=context.request.query.id,
                selected=tuple(
                    item
                    for item in conflicts.value or ()
                    if context.request.query.id in item.inferential_query_ids
                ),
                selected_evidence_ids=tuple(
                    dict.fromkeys(
                        evidence_id
                        for item in conflicts.value or ()
                        if context.request.query.id in item.inferential_query_ids
                        for evidence_id in item.evidence_record_ids
                    )
                ),
            ),
            sensitivities=_empty_or_scoped_knowledge(
                sensitivities,
                query_id=context.request.query.id,
                selected=tuple(
                    item
                    for item in sensitivities.value or ()
                    if claims_by_id.get(item.derived_claim_id) is not None
                    and claims_by_id[item.derived_claim_id].inferential_query_id
                    == context.request.query.id
                ),
            ),
            questions=questions_by_query[context.request.query.id],
        )
        for context in contexts
    )
    profile_coverage = contexts[0].result.profile_coverage
    if any(context.result.profile_coverage != profile_coverage for context in contexts[1:]):
        raise ValueError(
            "multiple profile coverage statements require a reviewed global report contract"
        )

    fields: dict[str, Any] = {
        "verified_pipeline_contexts": contexts,
        "query_sections": query_sections,
        "design_record_context": design_record_context,
        "prospective_input_ledgers": prospective_input_ledgers,
        "source_records": source_records,
        "evidence_records": evidence_records,
        "ai_candidates": candidate_sets,
        "human_confirmations": human_confirmations,
        "conflicts": conflicts,
        "confirmed_graph": graph,
        "claim_sets": claim_sets,
        "report_resolution": resolve_report_claim_sets(claim_sets),
        "design_adequacy_evaluations": adequacy_evaluations,
        "count_registry": count_registry,
        "scenario_coverages": scenario_coverages,
        "sensitivities": sensitivities,
        "questions": questions,
        "statistical_handoff": statistical_handoff,
        "strategy_module_status": StrategyModuleStatus.HANDOFF_ONLY,
        "profile_coverage": profile_coverage,
        "inference_limits": inference_limits,
        "epistemic_boundary": epistemic_boundary_for_context(design_record_context.mode),
        "execution_manifest": execution_manifest,
    }
    draft = ReportBundle.model_construct(
        report_id="REPORT-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = _report_checksum(draft)
    return ReportBundle(
        report_id=f"REPORT-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def explicit_absence[T](
    *,
    evidence_ids: tuple[str, ...],
    query_scope_id: str,
) -> KnowledgeValue[tuple[T, ...]]:
    """Represent a reviewed empty report section without an ambiguous bare list."""

    return KnowledgeValue[tuple[T, ...]](
        knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
        evidence_ids=evidence_ids,
        query_scope_id=query_scope_id,
    )


__all__ = [
    "EXECUTED_EPISTEMIC_BOUNDARY",
    "MULTI_QUERY_POLICY_VERSION",
    "PLANNED_EPISTEMIC_BOUNDARY",
    "RECONCILED_EPISTEMIC_BOUNDARY",
    "RETROSPECTIVE_EPISTEMIC_BOUNDARY",
    "ConflictRecord",
    "HandoffItem",
    "HandoffItemCategory",
    "HandoffItemOrigin",
    "QueryReportSection",
    "ReportBundle",
    "ReportDesignContext",
    "ReportDesignRecordContext",
    "ReportQuestion",
    "StatisticalHandoff",
    "StrategyModuleStatus",
    "VerifiedPipelineContext",
    "build_handoff_item",
    "build_report_bundle",
    "build_verified_pipeline_context",
    "epistemic_boundary_for_context",
    "explicit_absence",
    "resolve_report_claim_sets",
]
