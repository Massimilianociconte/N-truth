"""Neutral, content-addressed PRD v8 ReportBundle contract.

The bundle stores determinability, evidence support, design findings and
coverage as independent axes.  It deliberately exposes a statistical handoff,
never an analysis-strategy recommendation or design-approval verdict.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.adequacy import DesignAdequacyEvaluation
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.core import content_checksum
from ntruth.schemas.count_registry import CanonicalCountRecord
from ntruth.schemas.coverage import ProfileCoverageStatement, ScenarioCoverage
from ntruth.schemas.execution import V8ExecutionManifest
from ntruth.schemas.graph_v8 import V8ExperimentGraph
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.report_resolution import ReportResolutionOutcome
from ntruth.schemas.support import ConfirmationEvent, SensitivityRecord, SourceRecord

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

RETROSPECTIVE_EPISTEMIC_BOUNDARY = (
    "N-Truth ha valutato i record e le conferme disponibili; non ha osservato "
    "direttamente l'esperimento e non può recuperare deviazioni non registrate."
)


class StrategyModuleStatus(StrEnum):
    """Only the Bootstrap Core state is valid until external validation closes."""

    HANDOFF_ONLY = "HANDOFF_ONLY"


class ReportDesignContext(StrEnum):
    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"
    RECONCILED = "RECONCILED"
    UNVERIFIED_RETROSPECTIVE = "UNVERIFIED_RETROSPECTIVE"


class ReportDesignRecordContext(KernelModel):
    """Select one source-history lane so planned and executed facts never blend."""

    mode: ReportDesignContext
    planned_design_id: KnowledgeValue[NonBlankStr]
    executed_design_id: KnowledgeValue[NonBlankStr]
    reconciliation_id: KnowledgeValue[NonBlankStr]
    retrospective_source_ids: KnowledgeValue[tuple[NonBlankStr, ...]]

    @model_validator(mode="after")
    def _mode_contract(self) -> Self:
        states = {
            "planned": self.planned_design_id.knowledge_state,
            "executed": self.executed_design_id.knowledge_state,
            "reconciliation": self.reconciliation_id.knowledge_state,
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
        return self


class ReportQuestion(KernelModel):
    question_id: NonBlankStr
    inferential_query_id: NonBlankStr
    text: NonBlankStr
    evidence_required: tuple[NonBlankStr, ...] = Field(min_length=1)
    primary: bool


class StatisticalHandoff(KernelModel):
    strategy_module_status: Literal[StrategyModuleStatus.HANDOFF_ONLY] = (
        StrategyModuleStatus.HANDOFF_ONLY
    )
    structural_requirements: tuple[NonBlankStr, ...] = Field(min_length=1)
    unresolved_questions: tuple[NonBlankStr, ...] = Field(min_length=1)


class ReportBundle(KernelModel):
    report_id: NonBlankStr
    content_checksum: Sha256
    design_record_context: ReportDesignRecordContext
    source_records: tuple[SourceRecord, ...] = Field(min_length=1)
    ai_candidates: KnowledgeValue[tuple[JsonValue, ...]]
    human_confirmations: KnowledgeValue[tuple[ConfirmationEvent, ...]]
    conflicts: KnowledgeValue[tuple[dict[str, JsonValue], ...]]
    confirmed_graph: V8ExperimentGraph
    claim_sets: tuple[DerivedClaimSet, ...] = Field(min_length=1)
    report_resolution: ReportResolutionOutcome
    design_adequacy_evaluations: tuple[DesignAdequacyEvaluation, ...] = Field(min_length=1)
    count_records: tuple[CanonicalCountRecord, ...] = Field(min_length=1)
    scenario_coverages: tuple[ScenarioCoverage, ...] = Field(min_length=1)
    sensitivities: KnowledgeValue[tuple[SensitivityRecord, ...]]
    questions: tuple[ReportQuestion, ...] = Field(min_length=1)
    statistical_handoff: StatisticalHandoff
    strategy_module_status: Literal[StrategyModuleStatus.HANDOFF_ONLY] = (
        StrategyModuleStatus.HANDOFF_ONLY
    )
    profile_coverage: ProfileCoverageStatement
    inference_limits: tuple[NonBlankStr, ...] = Field(min_length=1)
    epistemic_boundary: NonBlankStr = RETROSPECTIVE_EPISTEMIC_BOUNDARY
    execution_manifest: V8ExecutionManifest

    @model_validator(mode="after")
    def _neutral_cross_contract_integrity(self) -> Self:
        source_ids = [source.source_id for source in self.source_records]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("ReportBundle contains duplicate source records")
        query_ids = [claim_set.inferential_query_id for claim_set in self.claim_sets]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("ReportBundle contains duplicate claim sets for a query")
        known_queries = set(query_ids)
        if self.design_record_context.mode is ReportDesignContext.UNVERIFIED_RETROSPECTIVE:
            retrospective_ids = set(self.design_record_context.retrospective_source_ids.value or ())
            if not retrospective_ids.issubset(source_ids):
                raise ValueError("retrospective design context references an unknown source")
        if any(
            evaluation.inferential_query_id not in known_queries
            for evaluation in self.design_adequacy_evaluations
        ):
            raise ValueError("adequacy evaluation is outside the report claim queries")
        if any(count.scope.query_id not in known_queries for count in self.count_records):
            raise ValueError("count record is outside the report claim queries")
        if any(question.inferential_query_id not in known_queries for question in self.questions):
            raise ValueError("question is outside the report claim queries")
        if any(
            coverage.profile_id != self.profile_coverage.profile_id
            for coverage in self.scenario_coverages
        ):
            raise ValueError("scenario and profile coverage must name the same profile")
        resolution_scope = self.report_resolution.resolution.query_scope_id
        if len(known_queries) > 1 and resolution_scope is not None:
            raise ValueError(
                "SRR-V8-014: a query-local resolution cannot be presented as a global "
                "multi-query report resolution"
            )
        if resolution_scope is not None and resolution_scope not in known_queries:
            raise ValueError("report resolution is outside the report claim queries")
        if self.strategy_module_status is not self.statistical_handoff.strategy_module_status:
            raise ValueError("ReportBundle and statistical handoff strategy status differ")
        if self.epistemic_boundary != RETROSPECTIVE_EPISTEMIC_BOUNDARY:
            raise ValueError("ReportBundle must retain the PRD v8 epistemic boundary")
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
    design_record_context: ReportDesignRecordContext,
    source_records: tuple[SourceRecord, ...],
    ai_candidates: KnowledgeValue[Any],
    human_confirmations: KnowledgeValue[Any],
    conflicts: KnowledgeValue[Any],
    confirmed_graph: V8ExperimentGraph,
    claim_sets: tuple[DerivedClaimSet, ...],
    report_resolution: ReportResolutionOutcome,
    design_adequacy_evaluations: tuple[DesignAdequacyEvaluation, ...],
    count_records: tuple[CanonicalCountRecord, ...],
    scenario_coverages: tuple[ScenarioCoverage, ...],
    sensitivities: KnowledgeValue[Any],
    questions: tuple[ReportQuestion, ...],
    statistical_handoff: StatisticalHandoff,
    profile_coverage: ProfileCoverageStatement,
    inference_limits: tuple[str, ...],
    execution_manifest: V8ExecutionManifest,
) -> ReportBundle:
    """Build the canonical neutral report and content-address every field."""

    fields: dict[str, Any] = {
        "design_record_context": design_record_context,
        "source_records": source_records,
        "ai_candidates": ai_candidates,
        "human_confirmations": human_confirmations,
        "conflicts": conflicts,
        "confirmed_graph": confirmed_graph,
        "claim_sets": claim_sets,
        "report_resolution": report_resolution,
        "design_adequacy_evaluations": design_adequacy_evaluations,
        "count_records": count_records,
        "scenario_coverages": scenario_coverages,
        "sensitivities": sensitivities,
        "questions": questions,
        "statistical_handoff": statistical_handoff,
        "strategy_module_status": StrategyModuleStatus.HANDOFF_ONLY,
        "profile_coverage": profile_coverage,
        "inference_limits": inference_limits,
        "epistemic_boundary": RETROSPECTIVE_EPISTEMIC_BOUNDARY,
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
    "RETROSPECTIVE_EPISTEMIC_BOUNDARY",
    "ReportBundle",
    "ReportDesignContext",
    "ReportDesignRecordContext",
    "ReportQuestion",
    "StatisticalHandoff",
    "StrategyModuleStatus",
    "build_report_bundle",
    "explicit_absence",
]
