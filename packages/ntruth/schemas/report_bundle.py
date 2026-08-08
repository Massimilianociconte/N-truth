"""Neutral, content-addressed PRD v8 ReportBundle contract.

The bundle stores determinability, evidence support, design findings and
coverage as independent axes.  It deliberately exposes a statistical handoff,
never an analysis-strategy recommendation or design-approval verdict.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.adequacy import DesignAdequacyEvaluation
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.core import content_checksum
from ntruth.schemas.count_registry import CanonicalCountRecord, CanonicalCountRegistry
from ntruth.schemas.coverage import ProfileCoverageStatement, ScenarioCoverage
from ntruth.schemas.execution import V8ExecutionManifest
from ntruth.schemas.graph_v8 import V8ExperimentGraph
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
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
    text: NonBlankStr
    text_checksum: Sha256

    @model_validator(mode="after")
    def _no_generated_strategy_recommendation(self) -> Self:
        if self.text_checksum != content_checksum(self.text):
            raise ValueError("handoff item text checksum mismatch")
        if self.origin is HandoffItemOrigin.USER_SUPPLIED and self.authority in {
            AuthorityType.SYSTEM_INFERENCE,
            AuthorityType.RULE_DERIVATION,
        }:
            raise ValueError("user-supplied handoff must retain human authority")
        return self


def build_handoff_item(
    *,
    category: HandoffItemCategory,
    origin: HandoffItemOrigin,
    authority: AuthorityType,
    evidence_refs: tuple[str, ...],
    text: str,
) -> HandoffItem:
    return HandoffItem(
        category=category,
        origin=origin,
        authority=authority,
        evidence_refs=evidence_refs,
        text=text,
        text_checksum=content_checksum(text),
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
    evidence_record_ids: tuple[NonBlankStr, ...] = Field(min_length=2)
    retained_values: tuple[JsonValue, ...] = Field(min_length=2)
    rationale: NonBlankStr

    @model_validator(mode="after")
    def _retains_distinct_supported_alternatives(self) -> Self:
        if len(set(self.inferential_query_ids)) != len(self.inferential_query_ids):
            raise ValueError("conflict query IDs contain duplicates")
        if len(set(self.evidence_record_ids)) != len(self.evidence_record_ids):
            raise ValueError("conflict evidence IDs contain duplicates")
        if len({content_checksum(value) for value in self.retained_values}) < 2:
            raise ValueError("conflict requires at least two distinct retained values")
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
        if self.profile_coverage.profile_id != self.inferential_query.profile_id:
            raise ValueError("query section profile coverage belongs to another profile")
        if any(
            item.profile_id != self.inferential_query.profile_id for item in self.scenario_coverages
        ):
            raise ValueError("query section scenario coverage belongs to another profile")
        return self


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
    query_ids = [item.inferential_query_id for item in claim_sets]
    if len(set(query_ids)) != len(query_ids):
        raise ValueError("report resolution contains duplicate query claim sets")
    if len(claim_sets) == 1:
        outcome = TrivialExplicitReportResolutionPolicy().resolve(claim_sets[0])
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
    ai_candidates: KnowledgeValue[tuple[JsonValue, ...]]
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
        evidence_by_id = {record.evidence_id: record for record in self.evidence_records}
        if any(record.source_id not in known_sources for record in self.evidence_records):
            raise ValueError("ReportBundle evidence references an unknown source")
        for label, value in (
            ("prospective_input_ledgers", self.prospective_input_ledgers),
            ("ai_candidates", self.ai_candidates),
            ("human_confirmations", self.human_confirmations),
            ("conflicts", self.conflicts),
            ("sensitivities", self.sensitivities),
        ):
            if not set(value.evidence_ids).issubset(known_evidence):
                raise ValueError(f"ReportBundle {label} has dangling evidence IDs")
            if not set(value.source_scope_ids).issubset(known_sources):
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
            ledger_confirmations = _ordered_addressed_union(
                tuple(ledger.confirmation_events for ledger in ledgers),
                identifier="event_id",
                label="confirmation",
            )
            if self.source_records != ledger_sources or self.evidence_records != ledger_evidence:
                raise ValueError("report source/evidence projection differs from input ledgers")
            if ledger_confirmations:
                if (
                    self.human_confirmations.knowledge_state is not KnowledgeState.PRESENT
                    or self.human_confirmations.value != ledger_confirmations
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
            execution = self.design_record_context.executed_design_record.value
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
                if not {source.source_id for source in execution.sources}.issubset(
                    source.source_id for source in ledger_sources
                ):
                    raise ValueError("embedded execution sources differ from input ledgers")
                if not {record.evidence_id for record in execution.evidence_records}.issubset(
                    record.evidence_id for record in ledger_evidence
                ):
                    raise ValueError("embedded execution evidence differs from input ledgers")
        if self.human_confirmations.knowledge_state is KnowledgeState.PRESENT and any(
            not set(event.evidence_refs).issubset(known_evidence)
            for event in self.human_confirmations.value or ()
        ):
            raise ValueError("ReportBundle confirmation has dangling evidence refs")
        if self.conflicts.knowledge_state is KnowledgeState.PRESENT and any(
            not set(conflict.evidence_record_ids).issubset(known_evidence)
            for conflict in self.conflicts.value or ()
        ):
            raise ValueError("ReportBundle conflict has dangling evidence refs")
        if any(
            not set(item.evidence_refs).issubset(known_evidence)
            for item in self.statistical_handoff.items
        ):
            raise ValueError("ReportBundle handoff item has dangling evidence refs")
        for item in self.statistical_handoff.items:
            if item.origin is HandoffItemOrigin.VERIFIED_RECORD and not any(
                evidence_by_id[evidence_id].original_text == item.text
                for evidence_id in item.evidence_refs
            ):
                raise ValueError(
                    "verified handoff text must exactly match a referenced EvidenceRecord"
                )
        query_ids = [claim_set.inferential_query_id for claim_set in self.claim_sets]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("ReportBundle contains duplicate claim sets for a query")
        known_queries = set(query_ids)
        known_claim_ids = {
            claim.claim_id for claim_set in self.claim_sets for claim in claim_set.claims
        }
        if self.sensitivities.knowledge_state is KnowledgeState.PRESENT and any(
            record.derived_claim_id not in known_claim_ids
            for record in self.sensitivities.value or ()
        ):
            raise ValueError("ReportBundle sensitivity references an unknown derived claim")
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
        for context, section in zip(
            self.verified_pipeline_contexts, self.query_sections, strict=True
        ):
            expected_count_ids = tuple(
                item.count_id
                for item in self.count_registry.records_for_query(context.request.query.id)
            )
            if (
                section.inferential_query != context.request.query
                or section.claim_set != context.result.claim_set
                or section.adequacy_evaluations != context.result.design_adequacy_evaluations
                or section.count_record_ids != expected_count_ids
                or section.scenario_coverages != context.result.scenario_coverages
                or section.profile_coverage != context.result.profile_coverage
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
    ai_candidates: KnowledgeValue[Any],
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

    graph = contexts[0].request.graph
    count_registry = contexts[0].request.count_registry
    execution_manifest = contexts[0].result.execution_manifest
    if any(context.request.graph != graph for context in contexts[1:]):
        raise ValueError("verified pipeline contexts do not share one confirmed graph")
    if any(context.request.count_registry != count_registry for context in contexts[1:]):
        raise ValueError("verified pipeline contexts do not share one canonical count registry")
    if any(context.result.execution_manifest != execution_manifest for context in contexts[1:]):
        raise ValueError("verified pipeline contexts do not share one execution manifest")

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

    claim_sets = tuple(context.result.claim_set for context in contexts)
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
        "ai_candidates": ai_candidates,
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
