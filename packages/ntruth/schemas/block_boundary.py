"""Experiment Block boundary records for PRD v8 §8.6.

A parser may propose a candidate boundary, but only an evidence-linked confirmation
event can produce ``CONFIRMED``. Conflicting boundary bases remain explicit and a
split or merge is represented as a separate append-only change record.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import EpistemicEventLedger

if TYPE_CHECKING:
    from ntruth.parser_ai.contract import ParserCandidateOutput


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FIGURE_CHANGED_ONLY_BASIS = "figure_changed_only"


def _basis_token(value: str) -> str:
    return "_".join(value.casefold().replace("-", " ").split())


def _figure_change_is_the_only_basis(values: tuple[str, ...] | list[str]) -> bool:
    return {_basis_token(value) for value in values} == {FIGURE_CHANGED_ONLY_BASIS}


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
        if len(set(self.boundary_basis.evidence_ids)) != len(self.boundary_basis.evidence_ids):
            raise ValueError("Experiment Block boundary basis evidence_ids must be unique")
        if self.boundary_basis.evidence_ids != self.source_refs:
            raise ValueError("boundary basis evidence must match source_refs exactly")
        if len(set(self.confirmation_event_ids)) != len(self.confirmation_event_ids):
            raise ValueError("boundary confirmation_event_ids must be unique")

        state = self.boundary_basis.knowledge_state
        if self.status is BlockBoundaryStatus.CONFIRMED:
            if state is not KnowledgeState.PRESENT or not self.confirmation_event_ids:
                raise ValueError(
                    "CONFIRMED boundary requires a PRESENT basis and confirmation event"
                )
            if self.boundary_basis.value is not None and _figure_change_is_the_only_basis(
                self.boundary_basis.value
            ):
                raise ValueError(
                    "figure_changed_only is insufficient to confirm an Experiment Block boundary"
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


class BoundaryChangeReference(KernelModel):
    change_id: NonBlankStr
    sha256: Sha256


class ExperimentBlockBoundaryChangeRecord(KernelModel):
    change_id: NonBlankStr
    record_checksum: Sha256
    sequence: int = Field(ge=1)
    parent_change: KnowledgeValue[BoundaryChangeReference]
    change_kind: BlockBoundaryChangeKind
    prior_block_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    resulting_block_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    boundary_basis: tuple[NonBlankStr, ...] = Field(min_length=1)
    source_refs: tuple[NonBlankStr, ...] = Field(min_length=1)
    rationale: NonBlankStr
    confirmation_event_ids: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _typed_change_shape(self) -> Self:
        for label, values in (
            ("prior_block_ids", self.prior_block_ids),
            ("resulting_block_ids", self.resulting_block_ids),
            ("boundary_basis", self.boundary_basis),
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
        if _figure_change_is_the_only_basis(self.boundary_basis):
            raise ValueError("figure_changed_only is insufficient for a boundary split or merge")
        if self.sequence == 1:
            if self.parent_change.knowledge_state is not KnowledgeState.NOT_APPLICABLE:
                raise ValueError("initial boundary change requires an explicit root parent state")
        elif (
            self.parent_change.knowledge_state is not KnowledgeState.PRESENT
            or self.parent_change.value is None
        ):
            raise ValueError("non-initial boundary change requires a content-addressed parent")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"change_id", "record_checksum"})
        )
        if self.record_checksum != expected:
            raise ValueError("Experiment Block boundary change checksum mismatch")
        if self.change_id != f"BLOCK-BOUNDARY-CHANGE-{expected[:20]}":
            raise ValueError("Experiment Block boundary change ID mismatch")
        return self


class ExperimentBlockBoundaryChangeLedger(KernelModel):
    ledger_id: NonBlankStr
    content_checksum: Sha256
    head_change: BoundaryChangeReference
    changes: tuple[ExperimentBlockBoundaryChangeRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _append_only_content_addressed_chain(self) -> Self:
        change_ids = tuple(change.change_id for change in self.changes)
        if len(change_ids) != len(set(change_ids)):
            raise ValueError("boundary change ledger contains duplicate change IDs")
        for expected_sequence, change in enumerate(self.changes, start=1):
            if change.sequence != expected_sequence:
                raise ValueError("boundary change ledger sequence is not contiguous")
            if expected_sequence == 1:
                if change.parent_change.knowledge_state is not KnowledgeState.NOT_APPLICABLE:
                    raise ValueError("initial boundary change must declare the root parent")
                continue
            previous = self.changes[expected_sequence - 2]
            expected_parent = BoundaryChangeReference(
                change_id=previous.change_id,
                sha256=previous.record_checksum,
            )
            if (
                change.parent_change.knowledge_state is not KnowledgeState.PRESENT
                or change.parent_change.value != expected_parent
            ):
                raise ValueError("boundary change parent does not resolve the previous version")
        last = self.changes[-1]
        expected_head = BoundaryChangeReference(
            change_id=last.change_id,
            sha256=last.record_checksum,
        )
        if self.head_change != expected_head:
            raise ValueError("boundary change ledger head does not resolve the final version")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Experiment Block boundary change ledger checksum mismatch")
        if self.ledger_id != f"BLOCK-BOUNDARY-LEDGER-{expected[:20]}":
            raise ValueError("Experiment Block boundary change ledger ID mismatch")
        return self


def build_experiment_block_boundary_change(
    *,
    change_kind: BlockBoundaryChangeKind,
    prior_block_ids: tuple[str, ...],
    resulting_block_ids: tuple[str, ...],
    boundary_basis: tuple[str, ...],
    source_refs: tuple[str, ...],
    rationale: str,
    confirmation_event_ids: tuple[str, ...],
    previous: ExperimentBlockBoundaryChangeRecord | None = None,
) -> ExperimentBlockBoundaryChangeRecord:
    """Build one immutable change whose identity includes its exact parent version."""

    if previous is None:
        sequence = 1
        parent_change = KnowledgeValue[BoundaryChangeReference](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="This is the root of the Experiment Block boundary change chain.",
            claim_scope_id="EXPERIMENT-BLOCK-BOUNDARY-CHANGE-ROOT",
        )
    else:
        sequence = previous.sequence + 1
        parent_change = KnowledgeValue[BoundaryChangeReference](
            knowledge_state=KnowledgeState.PRESENT,
            value=BoundaryChangeReference(
                change_id=previous.change_id,
                sha256=previous.record_checksum,
            ),
            evidence_ids=(previous.change_id,),
            claim_scope_id="EXPERIMENT-BLOCK-BOUNDARY-CHANGE-CHAIN",
        )
    fields: dict[str, Any] = {
        "sequence": sequence,
        "parent_change": parent_change,
        "change_kind": change_kind,
        "prior_block_ids": prior_block_ids,
        "resulting_block_ids": resulting_block_ids,
        "boundary_basis": boundary_basis,
        "source_refs": source_refs,
        "rationale": rationale,
        "confirmation_event_ids": confirmation_event_ids,
    }
    draft = ExperimentBlockBoundaryChangeRecord.model_construct(
        change_id="BLOCK-BOUNDARY-CHANGE-PENDING",
        record_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"change_id", "record_checksum"})
    )
    return ExperimentBlockBoundaryChangeRecord(
        change_id=f"BLOCK-BOUNDARY-CHANGE-{checksum[:20]}",
        record_checksum=checksum,
        **fields,
    )


def build_experiment_block_boundary_change_ledger(
    *,
    changes: tuple[ExperimentBlockBoundaryChangeRecord, ...],
) -> ExperimentBlockBoundaryChangeLedger:
    """Build a self-contained content-addressed chain; missing prefixes fail closed."""

    if not changes:
        raise ValueError("boundary change ledger requires at least one change")
    last = changes[-1]
    head = BoundaryChangeReference(change_id=last.change_id, sha256=last.record_checksum)
    fields: dict[str, Any] = {"head_change": head, "changes": changes}
    draft = ExperimentBlockBoundaryChangeLedger.model_construct(
        ledger_id="BLOCK-BOUNDARY-LEDGER-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
    )
    return ExperimentBlockBoundaryChangeLedger(
        ledger_id=f"BLOCK-BOUNDARY-LEDGER-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def append_experiment_block_boundary_change_ledger(
    previous: ExperimentBlockBoundaryChangeLedger,
    change: ExperimentBlockBoundaryChangeRecord,
) -> ExperimentBlockBoundaryChangeLedger:
    """Append exactly one already-addressed successor without rewriting history."""

    if change.change_id in {item.change_id for item in previous.changes}:
        raise ValueError("boundary change already exists: append-only")
    return build_experiment_block_boundary_change_ledger(changes=(*previous.changes, change))


def experiment_block_boundary_change_confirmation_value(
    change: ExperimentBlockBoundaryChangeRecord,
) -> dict[str, Any]:
    """Canonical factual payload that a change-scoped ConfirmationEvent must confirm."""

    return {
        "change_kind": change.change_kind.value,
        "prior_block_ids": list(change.prior_block_ids),
        "resulting_block_ids": list(change.resulting_block_ids),
        "boundary_basis": list(change.boundary_basis),
    }


def verify_candidate_experiment_block_boundaries(
    bundle: ParserCandidateOutput,
) -> ParserCandidateOutput:
    """Hard-gate router proposals without converting them into scientific verdicts."""

    block_ids = tuple(block.block_id for block in bundle.experiment_blocks)
    boundary_block_ids = tuple(boundary.block_id for boundary in bundle.block_boundaries)
    if len(boundary_block_ids) != len(set(boundary_block_ids)):
        raise ValueError("candidate Experiment Block boundaries must be unique")
    if set(boundary_block_ids) != set(block_ids):
        raise ValueError("every candidate Experiment Block requires exactly one boundary")
    for candidate in bundle.block_boundaries:
        if _figure_change_is_the_only_basis(list(candidate.boundary_basis_candidates)):
            raise ValueError(
                "figure_changed_only is insufficient to promote an Experiment Block boundary"
            )
    return bundle


def verify_experiment_block_boundaries(
    records: tuple[ExperimentBlockBoundaryRecord, ...],
    *,
    ledger: EpistemicEventLedger,
) -> tuple[ExperimentBlockBoundaryRecord, ...]:
    """Resolve only CONFIRMED boundaries against the immutable event ledger."""

    block_ids = tuple(record.block_id for record in records)
    if len(set(block_ids)) != len(block_ids):
        raise ValueError("Experiment Block boundary records require unique block_id")
    evidence_ids = {record.evidence_id for record in ledger.evidence_records}
    confirmations = {event.event_id: event for event in ledger.confirmation_events}
    for record in records:
        missing_sources = set(record.source_refs) - evidence_ids
        if missing_sources:
            raise ValueError(
                f"boundary references unknown source evidence: {sorted(missing_sources)}"
            )
        for event_id in record.confirmation_event_ids:
            event = confirmations.get(event_id)
            if event is None:
                raise ValueError(f"boundary references unknown confirmation event: {event_id}")
            if event.scope_id != record.block_id:
                raise ValueError("boundary confirmation scope does not match block_id")
            if event.evidence_refs != record.source_refs:
                raise ValueError("boundary confirmation evidence does not match source_refs")
            if event.confirmed_value.knowledge_state is not KnowledgeState.PRESENT:
                raise ValueError("boundary confirmation must retain a PRESENT value")
            if event.confirmed_value.evidence_ids != record.boundary_basis.evidence_ids:
                raise ValueError(
                    "boundary confirmed_value evidence must exactly match boundary basis evidence"
                )
            if len(set(event.confirmed_value.evidence_ids)) != len(
                event.confirmed_value.evidence_ids
            ):
                raise ValueError("boundary confirmed_value evidence IDs must be unique")
            confirmed_value = event.confirmed_value.value
            if (
                not isinstance(confirmed_value, (list, tuple))
                or tuple(confirmed_value) != record.boundary_basis.value
            ):
                raise ValueError("boundary confirmation value does not match boundary basis")
    return records


def verify_experiment_block_boundary_change_ledger(
    change_ledger: ExperimentBlockBoundaryChangeLedger,
    *,
    ledger: EpistemicEventLedger,
) -> ExperimentBlockBoundaryChangeLedger:
    """Resolve every change against exact evidence and change-scoped confirmations."""

    change_ledger = ExperimentBlockBoundaryChangeLedger.model_validate(change_ledger)
    ledger = EpistemicEventLedger.model_validate(ledger)
    evidence_ids = {record.evidence_id for record in ledger.evidence_records}
    confirmations = {event.event_id: event for event in ledger.confirmation_events}
    for change in change_ledger.changes:
        missing_sources = set(change.source_refs) - evidence_ids
        if missing_sources:
            raise ValueError(
                f"boundary change references unknown source evidence: {sorted(missing_sources)}"
            )
        scoped_confirmation_ids = {
            event.event_id
            for event in ledger.confirmation_events
            if event.scope_id == change.change_id
        }
        if scoped_confirmation_ids != set(change.confirmation_event_ids):
            raise ValueError(
                "boundary change confirmation references do not exactly resolve its scope"
            )
        expected_value = experiment_block_boundary_change_confirmation_value(change)
        for event_id in change.confirmation_event_ids:
            event = confirmations.get(event_id)
            if event is None:
                raise ValueError(
                    f"boundary change references unknown confirmation event: {event_id}"
                )
            if event.scope_id != change.change_id:
                raise ValueError("boundary change confirmation scope does not match change_id")
            if event.evidence_refs != change.source_refs:
                raise ValueError(
                    "boundary change confirmation evidence does not exactly match source_refs"
                )
            if event.confirmed_value.knowledge_state is not KnowledgeState.PRESENT:
                raise ValueError("boundary change confirmation must retain a PRESENT value")
            if event.confirmed_value.evidence_ids != change.source_refs:
                raise ValueError(
                    "boundary change confirmed_value evidence must exactly match source_refs"
                )
            if len(set(event.confirmed_value.evidence_ids)) != len(
                event.confirmed_value.evidence_ids
            ):
                raise ValueError("boundary change confirmed_value evidence IDs must be unique")
            if event.confirmed_value.value != expected_value:
                raise ValueError(
                    "boundary change confirmation value does not match the addressed change"
                )
    return change_ledger


__all__ = [
    "FIGURE_CHANGED_ONLY_BASIS",
    "BlockBoundaryChangeKind",
    "BlockBoundaryStatus",
    "BoundaryChangeReference",
    "ExperimentBlockBoundaryChangeLedger",
    "ExperimentBlockBoundaryChangeRecord",
    "ExperimentBlockBoundaryRecord",
    "append_experiment_block_boundary_change_ledger",
    "build_experiment_block_boundary_change",
    "build_experiment_block_boundary_change_ledger",
    "experiment_block_boundary_change_confirmation_value",
    "verify_candidate_experiment_block_boundaries",
    "verify_experiment_block_boundaries",
    "verify_experiment_block_boundary_change_ledger",
]
