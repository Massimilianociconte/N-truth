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
        raw_contracts: set[tuple[str, str, TemporalRelation]] = set()
        pair_contracts: dict[frozenset[str], tuple[str, object]] = {}
        strict_edges: set[tuple[str, str]] = set()
        for timing in self.relative_timings:
            if timing.subject_event_id not in known:
                raise ValueError(f"unknown subject_event_id: {timing.subject_event_id}")
            if timing.reference_event_id not in known:
                raise ValueError(f"unknown reference_event_id: {timing.reference_event_id}")
            if timing.subject_event_id == timing.reference_event_id:
                raise ValueError("temporal relation cannot reference the same event")
            raw_contract = (
                timing.subject_event_id,
                timing.reference_event_id,
                timing.relation,
            )
            if raw_contract in raw_contracts:
                raise ValueError("duplicate temporal relation")
            raw_contracts.add(raw_contract)

            pair = frozenset((timing.subject_event_id, timing.reference_event_id))
            if timing.relation is TemporalRelation.BEFORE:
                normalized: tuple[str, object] = (
                    "STRICT_ORDER",
                    (timing.subject_event_id, timing.reference_event_id),
                )
                strict_edges.add((timing.subject_event_id, timing.reference_event_id))
            elif timing.relation is TemporalRelation.AFTER:
                normalized = (
                    "STRICT_ORDER",
                    (timing.reference_event_id, timing.subject_event_id),
                )
                strict_edges.add((timing.reference_event_id, timing.subject_event_id))
            else:
                normalized = ("SYMMETRIC", timing.relation)
            prior = pair_contracts.get(pair)
            if prior is not None and prior != normalized:
                raise ValueError("conflicting temporal relations for the same event pair")
            pair_contracts[pair] = normalized

        adjacency: dict[str, set[str]] = {event_id: set() for event_id in event_ids}
        incoming: dict[str, int] = {event_id: 0 for event_id in event_ids}
        for subject, reference in strict_edges:
            if reference not in adjacency[subject]:
                adjacency[subject].add(reference)
                incoming[reference] += 1
        ready = [event_id for event_id, degree in incoming.items() if degree == 0]
        visited = 0
        while ready:
            event_id = ready.pop()
            visited += 1
            for reference in adjacency[event_id]:
                incoming[reference] -= 1
                if incoming[reference] == 0:
                    ready.append(reference)
        if visited != len(event_ids):
            raise ValueError("temporal strict-order cycle")
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
