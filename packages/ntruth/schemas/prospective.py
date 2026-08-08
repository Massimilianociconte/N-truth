"""Immutable prospective plan and executed-design records for PRD v8.

The planned snapshot is never rewritten by reconciliation.  Every execution
links to the exact content-addressed plan and may therefore coexist with other
executions of the same plan.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.core import content_checksum
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CountLifecyclePhase,
)
from ntruth.schemas.events import EventRegistry
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import SourceContext, SourceRecord

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DeviationType(StrEnum):
    SUBSTITUTION = "SUBSTITUTION"
    EXCLUSION = "EXCLUSION"
    POOLING = "POOLING"
    LOST_SAMPLE = "LOST_SAMPLE"
    TREATMENT_CHANGE = "TREATMENT_CHANGE"
    OTHER_REVIEW_REQUIRED = "OTHER_REVIEW_REQUIRED"


class ReconciliationStatus(StrEnum):
    NO_RECORDED_DEVIATION = "NO_RECORDED_DEVIATION"
    DEVIATIONS_RECORDED = "DEVIATIONS_RECORDED"


class DeviationRecord(KernelModel):
    deviation_id: NonBlankStr
    affected_query_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    field_path: NonBlankStr
    planned_value: KnowledgeValue[JsonValue]
    executed_value: KnowledgeValue[JsonValue]
    deviation_type: DeviationType
    evidence_refs: tuple[NonBlankStr, ...] = Field(min_length=1)
    rationale: NonBlankStr

    @model_validator(mode="after")
    def _values_are_distinct_and_supported(self) -> Self:
        if len(set(self.affected_query_ids)) != len(self.affected_query_ids):
            raise ValueError("affected_query_ids contains duplicates")
        if self.planned_value.model_dump(mode="json") == self.executed_value.model_dump(
            mode="json"
        ):
            raise ValueError("a deviation requires distinct planned and executed values")
        if not set(self.executed_value.evidence_ids).issubset(self.evidence_refs):
            raise ValueError("executed deviation evidence must be declared in evidence_refs")
        affected = set(self.affected_query_ids)
        for label, value in (
            ("planned_value", self.planned_value),
            ("executed_value", self.executed_value),
        ):
            if value.query_scope_id is not None and value.query_scope_id not in affected:
                raise ValueError(f"{label} query scope must be named in affected_query_ids")
        return self


class PlannedDesignRecord(KernelModel):
    plan_id: NonBlankStr
    content_checksum: Sha256
    experiment_block_id: NonBlankStr
    inferential_query_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    sources: tuple[SourceRecord, ...] = Field(min_length=1)
    event_registry: EventRegistry
    count_records: tuple[CanonicalCountRecord, ...] = Field(min_length=1)
    sample_sheet_ref: NonBlankStr
    methods_draft_ref: NonBlankStr
    user_confirmation_scopes: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _plan_contract(self) -> Self:
        if len(set(self.inferential_query_ids)) != len(self.inferential_query_ids):
            raise ValueError("inferential_query_ids contains duplicates")
        if len(set(self.user_confirmation_scopes)) != len(self.user_confirmation_scopes):
            raise ValueError("user_confirmation_scopes contains duplicates")
        if any(source.source_context is not SourceContext.PLANNED for source in self.sources):
            raise ValueError("PlannedDesignRecord accepts only planned source context")
        if any(
            event.experiment_block_id != self.experiment_block_id
            for event in self.event_registry.events
        ):
            raise ValueError("all planned events must reference experiment_block_id")
        query_ids = set(self.inferential_query_ids)
        counts_by_query = {query_id: 0 for query_id in query_ids}
        for count in self.count_records:
            if count.kind is not CanonicalCountKind.PLANNED_UNIT_COUNT:
                raise ValueError("planned design counts must use planned_unit_count")
            if count.scope.query_id not in query_ids:
                raise ValueError("planned_unit_count scope must reference a plan query")
            counts_by_query[count.scope.query_id] += 1
            lifecycle = count.scope.lifecycle_phase
            if (
                lifecycle.knowledge_state is not KnowledgeState.PRESENT
                or lifecycle.value is not CountLifecyclePhase.PLANNED
            ):
                raise ValueError("planned_unit_count requires explicit planned lifecycle scope")
        if any(count != 1 for count in counts_by_query.values()):
            raise ValueError("each inferential query requires exactly one planned_unit_count")
        expected_checksum = _record_checksum(self)
        if self.content_checksum != expected_checksum:
            raise ValueError("planned design content checksum mismatch")
        if self.plan_id != f"PLAN-{expected_checksum[:20]}":
            raise ValueError("planned design ID must be derived from its content checksum")
        return self


class ExecutedDesignRecord(KernelModel):
    execution_id: NonBlankStr
    content_checksum: Sha256
    planned_design_id: NonBlankStr
    planned_design_checksum: Sha256
    experiment_block_id: NonBlankStr
    inferential_query_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    sources: tuple[SourceRecord, ...] = Field(min_length=1)
    event_registry: EventRegistry
    count_records: tuple[CanonicalCountRecord, ...] = Field(min_length=1)
    deviations: KnowledgeValue[tuple[DeviationRecord, ...]]
    final_sample_sheet_ref: NonBlankStr
    execution_log_refs: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _execution_contract(self) -> Self:
        if len(set(self.inferential_query_ids)) != len(self.inferential_query_ids):
            raise ValueError("inferential_query_ids contains duplicates")
        if any(source.source_context is not SourceContext.EXECUTED for source in self.sources):
            raise ValueError("ExecutedDesignRecord accepts only executed source context")
        if any(
            event.experiment_block_id != self.experiment_block_id
            for event in self.event_registry.events
        ):
            raise ValueError("all executed events must reference experiment_block_id")
        query_ids = set(self.inferential_query_ids)
        for count in self.count_records:
            if count.kind is CanonicalCountKind.PLANNED_UNIT_COUNT:
                raise ValueError("executed design cannot restate planned_unit_count")
            if count.scope.query_id not in query_ids:
                raise ValueError("executed count scope must reference a plan query")
        if self.deviations.knowledge_state is KnowledgeState.PRESENT:
            if self.deviations.value is None:
                raise ValueError("present deviations require deviation records")
            for deviation in self.deviations.value:
                if not set(deviation.affected_query_ids).issubset(query_ids):
                    raise ValueError("deviation references a query outside the executed design")
        elif self.deviations.knowledge_state is not KnowledgeState.ABSENT_EXPLICIT:
            raise ValueError("execution deviations must be present or explicitly absent")
        expected_checksum = _record_checksum(self)
        if self.content_checksum != expected_checksum:
            raise ValueError("executed design content checksum mismatch")
        if self.execution_id != f"EXECUTION-{expected_checksum[:20]}":
            raise ValueError("execution ID must be derived from its content checksum")
        return self


class PlanExecutionReconciliation(KernelModel):
    reconciliation_id: NonBlankStr
    content_checksum: Sha256
    planned_design_id: NonBlankStr
    planned_design_checksum: Sha256
    executed_design_id: NonBlankStr
    executed_design_checksum: Sha256
    status: ReconciliationStatus
    deviations: KnowledgeValue[tuple[DeviationRecord, ...]]

    @model_validator(mode="after")
    def _reconciliation_contract(self) -> Self:
        expected_status = (
            ReconciliationStatus.DEVIATIONS_RECORDED
            if self.deviations.knowledge_state is KnowledgeState.PRESENT
            else ReconciliationStatus.NO_RECORDED_DEVIATION
        )
        if self.status is not expected_status:
            raise ValueError("reconciliation status conflicts with deviation state")
        expected_checksum = _record_checksum(self)
        if self.content_checksum != expected_checksum:
            raise ValueError("reconciliation content checksum mismatch")
        if self.reconciliation_id != f"RECONCILIATION-{expected_checksum[:20]}":
            raise ValueError("reconciliation ID must be derived from its content checksum")
        return self


def _record_checksum(record: KernelModel) -> str:
    return content_checksum(
        record.model_dump(
            mode="json",
            exclude={
                "plan_id",
                "execution_id",
                "reconciliation_id",
                "content_checksum",
            },
        )
    )


def _build_addressed[T: KernelModel](
    model: type[T],
    *,
    id_field: str,
    id_prefix: str,
    fields: dict[str, Any],
) -> T:
    draft_payload: Any = {
        **fields,
        id_field: f"{id_prefix}-PENDING",
        "content_checksum": "0" * 64,
    }
    draft = model.model_construct(**draft_payload)
    checksum = _record_checksum(draft)
    final_payload: Any = {
        **fields,
        id_field: f"{id_prefix}-{checksum[:20]}",
        "content_checksum": checksum,
    }
    return model.model_validate(final_payload)


def build_planned_design(
    *,
    experiment_block_id: str,
    inferential_query_ids: tuple[str, ...],
    sources: tuple[SourceRecord, ...],
    event_registry: EventRegistry,
    count_records: tuple[CanonicalCountRecord, ...],
    sample_sheet_ref: str,
    methods_draft_ref: str,
    user_confirmation_scopes: tuple[str, ...],
) -> PlannedDesignRecord:
    """Freeze one immutable, content-addressed prospective plan."""

    return _build_addressed(
        PlannedDesignRecord,
        id_field="plan_id",
        id_prefix="PLAN",
        fields={
            "experiment_block_id": experiment_block_id,
            "inferential_query_ids": inferential_query_ids,
            "sources": sources,
            "event_registry": event_registry,
            "count_records": count_records,
            "sample_sheet_ref": sample_sheet_ref,
            "methods_draft_ref": methods_draft_ref,
            "user_confirmation_scopes": user_confirmation_scopes,
        },
    )


def build_executed_design(
    *,
    planned_design: PlannedDesignRecord,
    sources: tuple[SourceRecord, ...],
    event_registry: EventRegistry,
    count_records: tuple[CanonicalCountRecord, ...],
    deviations: tuple[DeviationRecord, ...],
    final_sample_sheet_ref: str,
    execution_log_refs: tuple[str, ...],
) -> ExecutedDesignRecord:
    """Create a new execution linked to, but never overwriting, a frozen plan."""

    PlannedDesignRecord.model_validate(planned_design.model_dump(mode="python"))
    deviation_state: KnowledgeValue[tuple[DeviationRecord, ...]]
    if deviations:
        deviation_state = KnowledgeValue[tuple[DeviationRecord, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=deviations,
            evidence_ids=tuple(
                sorted({evidence for item in deviations for evidence in item.evidence_refs})
            ),
        )
    else:
        deviation_state = KnowledgeValue[tuple[DeviationRecord, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=execution_log_refs,
        )
    return _build_addressed(
        ExecutedDesignRecord,
        id_field="execution_id",
        id_prefix="EXECUTION",
        fields={
            "planned_design_id": planned_design.plan_id,
            "planned_design_checksum": planned_design.content_checksum,
            "experiment_block_id": planned_design.experiment_block_id,
            "inferential_query_ids": planned_design.inferential_query_ids,
            "sources": sources,
            "event_registry": event_registry,
            "count_records": count_records,
            "deviations": deviation_state,
            "final_sample_sheet_ref": final_sample_sheet_ref,
            "execution_log_refs": execution_log_refs,
        },
    )


def reconcile_plan_execution(
    planned_design: PlannedDesignRecord,
    executed_design: ExecutedDesignRecord,
) -> PlanExecutionReconciliation:
    """Produce an immutable diff for one exact plan/execution pair."""

    if executed_design.planned_design_id != planned_design.plan_id:
        raise ValueError("executed design references a different plan ID")
    if executed_design.planned_design_checksum != planned_design.content_checksum:
        raise ValueError("executed design references a different plan checksum")
    if executed_design.experiment_block_id != planned_design.experiment_block_id:
        raise ValueError("plan and execution use different experiment blocks")
    PlannedDesignRecord.model_validate(planned_design.model_dump(mode="python"))
    ExecutedDesignRecord.model_validate(executed_design.model_dump(mode="python"))
    status = (
        ReconciliationStatus.DEVIATIONS_RECORDED
        if executed_design.deviations.knowledge_state is KnowledgeState.PRESENT
        else ReconciliationStatus.NO_RECORDED_DEVIATION
    )
    return _build_addressed(
        PlanExecutionReconciliation,
        id_field="reconciliation_id",
        id_prefix="RECONCILIATION",
        fields={
            "planned_design_id": planned_design.plan_id,
            "planned_design_checksum": planned_design.content_checksum,
            "executed_design_id": executed_design.execution_id,
            "executed_design_checksum": executed_design.content_checksum,
            "status": status,
            "deviations": executed_design.deviations,
        },
    )


__all__ = [
    "DeviationRecord",
    "DeviationType",
    "ExecutedDesignRecord",
    "PlanExecutionReconciliation",
    "PlannedDesignRecord",
    "ReconciliationStatus",
    "build_executed_design",
    "build_planned_design",
    "reconcile_plan_execution",
]
