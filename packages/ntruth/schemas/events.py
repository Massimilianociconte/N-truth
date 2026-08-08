"""PRD v8 event nodes and event-referenced temporal relations."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeValue


class EventType(StrEnum):
    ASSIGNMENT = "AssignmentEvent"
    APPLICATION = "ApplicationEvent"
    EXPOSURE = "ExposureEvent"
    SPLIT = "SplitEvent"
    POOL = "PoolEvent"
    OBSERVATION = "Observation"


class TemporalRelation(StrEnum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    SAME_EVENT = "SAME_EVENT"
    OVERLAPS = "OVERLAPS"
    UNKNOWN = "UNKNOWN"


class EventRecord(KernelModel):
    event_id: NonBlankStr
    experiment_block_id: NonBlankStr
    event_type: EventType
    evidence_refs: tuple[NonBlankStr, ...] = Field(min_length=1)


class AssignmentEvent(EventRecord):
    event_type: Literal[EventType.ASSIGNMENT] = EventType.ASSIGNMENT
    factor_id: NonBlankStr
    assigned_unit_type: KnowledgeValue[NonBlankStr]
    assigned_unit_ids: KnowledgeValue[tuple[NonBlankStr, ...]]


class ApplicationEvent(EventRecord):
    event_type: Literal[EventType.APPLICATION] = EventType.APPLICATION
    factor_id: NonBlankStr
    intervention_id: KnowledgeValue[NonBlankStr]
    application_unit_type: KnowledgeValue[NonBlankStr]
    application_unit_ids: KnowledgeValue[tuple[NonBlankStr, ...]]


class ExposureEvent(EventRecord):
    event_type: Literal[EventType.EXPOSURE] = EventType.EXPOSURE
    exposure_pathway: KnowledgeValue[NonBlankStr]
    exposure_container: KnowledgeValue[NonBlankStr]
    effective_exposure_unit: KnowledgeValue[NonBlankStr]
    exposed_unit_ids: KnowledgeValue[tuple[NonBlankStr, ...]]


class SplitEvent(EventRecord):
    event_type: Literal[EventType.SPLIT] = EventType.SPLIT
    source_unit_ids: KnowledgeValue[tuple[NonBlankStr, ...]]
    resulting_unit_ids: KnowledgeValue[tuple[NonBlankStr, ...]]


class PoolEvent(EventRecord):
    event_type: Literal[EventType.POOL] = EventType.POOL
    source_unit_ids: KnowledgeValue[tuple[NonBlankStr, ...]]
    pooled_unit_id: KnowledgeValue[NonBlankStr]


class ObservationEvent(EventRecord):
    event_type: Literal[EventType.OBSERVATION] = EventType.OBSERVATION
    endpoint_id: NonBlankStr
    measured_on_unit_ids: KnowledgeValue[tuple[NonBlankStr, ...]]
    timepoint_id: KnowledgeValue[NonBlankStr]


DesignEvent = (
    AssignmentEvent | ApplicationEvent | ExposureEvent | SplitEvent | PoolEvent | ObservationEvent
)


class RelativeTiming(KernelModel):
    subject_event_id: NonBlankStr
    reference_event_id: NonBlankStr
    relation: TemporalRelation
    evidence_refs: tuple[NonBlankStr, ...] = ()
    rationale: NonBlankStr | None = None

    @model_validator(mode="after")
    def _timing_support(self) -> Self:
        if self.relation is TemporalRelation.UNKNOWN:
            if self.rationale is None:
                raise ValueError("UNKNOWN timing requires rationale")
        elif not self.evidence_refs:
            raise ValueError(f"{self.relation.value} timing requires evidence_refs")
        return self


class EventRegistry(KernelModel):
    events: tuple[DesignEvent, ...] = Field(min_length=1)
    relative_timings: tuple[RelativeTiming, ...] = ()

    @model_validator(mode="after")
    def _referential_integrity(self) -> Self:
        event_ids = [event.event_id for event in self.events]
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("duplicate event_id")
        known = set(event_ids)
        for timing in self.relative_timings:
            if timing.subject_event_id not in known:
                raise ValueError(f"unknown subject_event_id: {timing.subject_event_id}")
            if timing.reference_event_id not in known:
                raise ValueError(f"unknown reference_event_id: {timing.reference_event_id}")
        return self

    def event(self, event_id: str) -> DesignEvent:
        for event in self.events:
            if event.event_id == event_id:
                return event
        raise KeyError(event_id)


__all__ = [
    "ApplicationEvent",
    "AssignmentEvent",
    "DesignEvent",
    "EventRecord",
    "EventRegistry",
    "EventType",
    "ExposureEvent",
    "ObservationEvent",
    "PoolEvent",
    "RelativeTiming",
    "SplitEvent",
    "TemporalRelation",
]
