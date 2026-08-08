"""Experiment Block boundary records for PRD v8 §8.6.

A parser may propose a candidate boundary, but only an evidence-linked confirmation
event can produce ``CONFIRMED``. Conflicting boundary bases remain explicit and a
split or merge is represented as a separate append-only change record.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import EpistemicEventLedger


class BlockBoundaryStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CANDIDATE = "CANDIDATE"
    CONFLICTING = "CONFLICTING"


class BlockBoundaryChangeKind(StrEnum):
    SPLIT = "SPLIT"
    MERGE = "MERGE"


class ExperimentBlockBoundaryRecord(KernelModel):
    block_id: NonBlankStr
    boundary_basis: KnowledgeValue[tuple[NonBlankStr, ...]]
    source_refs: tuple[NonBlankStr, ...] = Field(min_length=1)
    status: BlockBoundaryStatus
    rationale: NonBlankStr
    confirmation_event_ids: tuple[NonBlankStr, ...] = ()

    @model_validator(mode="after")
    def _epistemic_status_and_sources(self) -> Self:
        if len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("Experiment Block boundary source_refs must be unique")
        if set(self.boundary_basis.evidence_ids) != set(self.source_refs):
            raise ValueError("boundary basis evidence must match source_refs exactly")
        if len(set(self.confirmation_event_ids)) != len(self.confirmation_event_ids):
            raise ValueError("boundary confirmation_event_ids must be unique")

        state = self.boundary_basis.knowledge_state
        if self.status is BlockBoundaryStatus.CONFIRMED:
            if state is not KnowledgeState.PRESENT or not self.confirmation_event_ids:
                raise ValueError(
                    "CONFIRMED boundary requires a PRESENT basis and confirmation event"
                )
        elif self.status is BlockBoundaryStatus.CANDIDATE:
            if state is not KnowledgeState.PRESENT or self.confirmation_event_ids:
                raise ValueError(
                    "CANDIDATE boundary requires a PRESENT candidate basis and no confirmation"
                )
        elif state is not KnowledgeState.CONFLICTING or self.confirmation_event_ids:
            raise ValueError(
                "CONFLICTING boundary requires retained alternatives and no confirmation"
            )
        return self


class ExperimentBlockBoundaryChangeRecord(KernelModel):
    change_id: NonBlankStr
    change_kind: BlockBoundaryChangeKind
    prior_block_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    resulting_block_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    source_refs: tuple[NonBlankStr, ...] = Field(min_length=1)
    rationale: NonBlankStr
    confirmation_event_ids: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _typed_change_shape(self) -> Self:
        for label, values in (
            ("prior_block_ids", self.prior_block_ids),
            ("resulting_block_ids", self.resulting_block_ids),
            ("source_refs", self.source_refs),
            ("confirmation_event_ids", self.confirmation_event_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
        if self.change_kind is BlockBoundaryChangeKind.SPLIT and (
            len(self.prior_block_ids) != 1 or len(self.resulting_block_ids) < 2
        ):
            raise ValueError("SPLIT requires one prior block and at least two resulting blocks")
        if self.change_kind is BlockBoundaryChangeKind.MERGE and (
            len(self.prior_block_ids) < 2 or len(self.resulting_block_ids) != 1
        ):
            raise ValueError("MERGE requires at least two prior blocks and one resulting block")
        return self


def verify_experiment_block_boundaries(
    records: tuple[ExperimentBlockBoundaryRecord, ...],
    *,
    ledger: EpistemicEventLedger,
) -> tuple[ExperimentBlockBoundaryRecord, ...]:
    """Resolve only CONFIRMED boundaries against the immutable event ledger."""

    block_ids = tuple(record.block_id for record in records)
    if len(set(block_ids)) != len(block_ids):
        raise ValueError("Experiment Block boundary records require unique block_id")
    confirmations = {event.event_id: event for event in ledger.confirmation_events}
    for record in records:
        for event_id in record.confirmation_event_ids:
            event = confirmations.get(event_id)
            if event is None:
                raise ValueError(f"boundary references unknown confirmation event: {event_id}")
            if event.scope_id != record.block_id:
                raise ValueError("boundary confirmation scope does not match block_id")
            if set(event.evidence_refs) != set(record.source_refs):
                raise ValueError("boundary confirmation evidence does not match source_refs")
            if event.confirmed_value.knowledge_state is not KnowledgeState.PRESENT:
                raise ValueError("boundary confirmation must retain a PRESENT value")
            confirmed_value = event.confirmed_value.value
            if (
                not isinstance(confirmed_value, (list, tuple))
                or tuple(confirmed_value) != record.boundary_basis.value
            ):
                raise ValueError("boundary confirmation value does not match boundary basis")
    return records


__all__ = [
    "BlockBoundaryChangeKind",
    "BlockBoundaryStatus",
    "ExperimentBlockBoundaryChangeRecord",
    "ExperimentBlockBoundaryRecord",
    "verify_experiment_block_boundaries",
]
