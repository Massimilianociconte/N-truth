"""PRD v9 MaterialLineage typed events and count-identity invariants.

This increment records split/pool/passage history. It does not rename the v8
kernel and never invents experimental-unit independence from a new material ID.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel


class MaterialLineageKind(StrEnum):
    """Minimum typed material transformations (PRD v9 §7.8)."""

    SPLIT = "SPLIT"
    ALIQUOT = "ALIQUOT"
    POOL = "POOL"
    REPLATE = "REPLATE"
    PASSAGE = "PASSAGE"
    THAW = "THAW"
    MERGE = "MERGE"
    SUBSAMPLE = "SUBSAMPLE"
    DERIVE = "DERIVE"


class LineageRelation(StrEnum):
    """Event-referenced timing (PRD v9 §7.9 / Appendix P.6)."""

    BEFORE = "BEFORE"
    AFTER = "AFTER"
    SAME_EVENT = "SAME_EVENT"
    OVERLAPS = "OVERLAPS"
    UNKNOWN = "UNKNOWN"


class MixingState(StrEnum):
    """Whether parent materials remain separable after the event."""

    NONE = "NONE"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"


class ContinuityState(StrEnum):
    """Whether child identity continues a parent history."""

    SHARED_PARENT_HISTORY = "SHARED_PARENT_HISTORY"
    PRESERVED = "PRESERVED"
    MIXED = "MIXED"
    BROKEN = "BROKEN"
    INDEPENDENT = "INDEPENDENT"
    UNKNOWN = "UNKNOWN"


class AssignmentRelation(StrEnum):
    """Whether the event is before or after assignment of the relevant factor."""

    PRE_ASSIGNMENT = "PRE_ASSIGNMENT"
    POST_ASSIGNMENT = "POST_ASSIGNMENT"
    UNKNOWN = "UNKNOWN"


class IdentityBasis(StrEnum):
    """How child identity is grounded for count logic.

    DISTINCT_ASSIGNMENT_UNIT is the only basis that may increase *candidate*
    assignment units, and only together with PRE_ASSIGNMENT. SINGLE_PARENT
    preserves traceability without inventing independence. MIXED_PARENTS marks
    multi-parent provenance after pooling.
    """

    SINGLE_PARENT = "SINGLE_PARENT"
    DISTINCT_ASSIGNMENT_UNIT = "DISTINCT_ASSIGNMENT_UNIT"
    MIXED_PARENTS = "MIXED_PARENTS"
    UNTRACEABLE = "UNTRACEABLE"
    UNKNOWN = "UNKNOWN"


_IDENTITY_PRESERVING = frozenset({IdentityBasis.DISTINCT_ASSIGNMENT_UNIT})
_NON_DESTROYING_MIX = frozenset({MixingState.NONE, MixingState.PARTIAL})


def _require_non_blank(label: str, value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"blank {label}")
    return stripped


class MaterialLineageEvent(FrozenModel):
    """One typed material transformation with fail-closed count identity."""

    event_id: str
    kind: MaterialLineageKind
    parent_ids: tuple[str, ...] = Field(min_length=1)
    child_ids: tuple[str, ...] = Field(min_length=1)
    reference_event_id: str | None = None
    relation: LineageRelation
    mixing_state: MixingState
    continuity_state: ContinuityState
    assignment_relation: AssignmentRelation
    evidence_refs: tuple[str, ...]
    identity_basis: IdentityBasis

    @model_validator(mode="after")
    def _fail_closed_invariants(self) -> Self:
        _require_non_blank("event_id", self.event_id)
        if self.reference_event_id is not None:
            _require_non_blank("reference_event_id", self.reference_event_id)
        parent_ids = tuple(_require_non_blank("parent_ids", item) for item in self.parent_ids)
        child_ids = tuple(_require_non_blank("child_ids", item) for item in self.child_ids)
        if not parent_ids:
            raise ValueError("empty parent_ids")
        if not child_ids:
            raise ValueError("empty child_ids")
        if set(parent_ids) & set(child_ids):
            raise ValueError("self-parent forbidden")
        for ref in self.evidence_refs:
            _require_non_blank("evidence_refs", ref)

        if self.kind is MaterialLineageKind.SPLIT:
            if self.continuity_state is ContinuityState.INDEPENDENT:
                raise ValueError("SPLIT does not create independence")
            if self.identity_basis not in {
                IdentityBasis.SINGLE_PARENT,
                IdentityBasis.DISTINCT_ASSIGNMENT_UNIT,
                IdentityBasis.UNKNOWN,
            }:
                raise ValueError("SPLIT does not create independence")

        if (
            self.kind is MaterialLineageKind.POOL
            and len(set(parent_ids)) > 1
            and self.mixing_state is MixingState.COMPLETE
            and self.identity_basis is IdentityBasis.SINGLE_PARENT
        ):
            raise ValueError("POOL complete mixing destroys single-parent identity_basis")
        return self

    def distinct_child_ids(self) -> tuple[str, ...]:
        """Return child IDs in first-seen order, without duplicates."""

        seen: set[str] = set()
        ordered: list[str] = []
        for child_id in self.child_ids:
            if child_id not in seen:
                seen.add(child_id)
                ordered.append(child_id)
        return tuple(ordered)

    def identity_preserved(self) -> bool:
        """True only when distinct assignable child identities remain."""

        return (
            self.identity_basis in _IDENTITY_PRESERVING and self.mixing_state in _NON_DESTROYING_MIX
        )


def experimental_unit_multiplier(event: MaterialLineageEvent) -> int:
    """Return the count-identity multiplier for one lineage event.

    Fail-closed rule, never invent independence:

    * ``POST_ASSIGNMENT`` descendants never multiply experimental-unit count
      (always ``1``), including SPLIT, PASSAGE, REPLATE, ALIQUOT, THAW,
      SUBSAMPLE, MERGE, DERIVE and POOL.
    * ``PRE_ASSIGNMENT`` may increase *candidate assignment units* only when
      ``identity_basis`` is ``DISTINCT_ASSIGNMENT_UNIT`` (identity preserved)
      and mixing is not ``COMPLETE``/``UNKNOWN``. The multiplier is then the
      number of distinct identity-bearing children.
    * ``SINGLE_PARENT``, ``MIXED_PARENTS``, ``UNTRACEABLE``, ``UNKNOWN``
      identity, ``UNKNOWN`` assignment, and complete mixing all return ``1``.
    * SPLIT does not create independence by itself. A pre-assignment split
      increases candidates only through the ``identity_basis`` rule above.
    """

    if event.assignment_relation is AssignmentRelation.POST_ASSIGNMENT:
        return 1
    if (
        event.assignment_relation is AssignmentRelation.PRE_ASSIGNMENT
        and event.identity_preserved()
    ):
        n_children = len(event.distinct_child_ids())
        return n_children if n_children > 0 else 1
    return 1


def validate_lineage_graph(events: tuple[MaterialLineageEvent, ...]) -> None:
    """Reject cyclic material graphs and missing event references."""

    event_ids = [event.event_id for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("duplicate event_id")
    known = set(event_ids)
    for event in events:
        if event.reference_event_id is None:
            continue
        if event.reference_event_id == event.event_id:
            raise ValueError("reference_event_id cannot reference the same event")
        if event.reference_event_id not in known:
            raise ValueError(f"missing reference_event_id: {event.reference_event_id}")

    adjacency: dict[str, set[str]] = {}
    nodes: set[str] = set()
    for event in events:
        for parent_id in event.parent_ids:
            nodes.add(parent_id)
            adjacency.setdefault(parent_id, set()).update(event.child_ids)
        for child_id in event.child_ids:
            nodes.add(child_id)
            adjacency.setdefault(child_id, set())

    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise ValueError("lineage cycle")
        visiting.add(node)
        for successor in adjacency.get(node, ()):
            _visit(successor)
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        _visit(node)


def count_identity_after(
    events: tuple[MaterialLineageEvent, ...],
    initial_eu: int,
) -> int:
    """Apply a lineage sequence to an experimental-unit count.

    ``POST_ASSIGNMENT`` events never increase the count: a split, passage or
    replate after assignment leaves 1 EU as 1, and a pool of two assigned
    units does not become 2+2. ``PRE_ASSIGNMENT`` events replace the distinct
    parent identities they consume with ``experimental_unit_multiplier``.
    """

    if initial_eu < 0:
        raise ValueError("initial_eu must be non-negative")
    validate_lineage_graph(events)
    current = initial_eu
    for event in events:
        multiplier = experimental_unit_multiplier(event)
        if event.assignment_relation is not AssignmentRelation.PRE_ASSIGNMENT:
            continue
        n_parents = len(set(event.parent_ids))
        current = current - n_parents + multiplier if current >= n_parents else multiplier
    return current


__all__ = [
    "AssignmentRelation",
    "ContinuityState",
    "IdentityBasis",
    "LineageRelation",
    "MaterialLineageEvent",
    "MaterialLineageKind",
    "MixingState",
    "count_identity_after",
    "experimental_unit_multiplier",
    "validate_lineage_graph",
]
