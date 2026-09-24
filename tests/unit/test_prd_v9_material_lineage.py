"""PRD v9 MaterialLineage typed events and count-identity invariants."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ntruth.schemas.material_lineage import (
    AssignmentRelation,
    ContinuityState,
    IdentityBasis,
    LineageRelation,
    MaterialLineageEvent,
    MaterialLineageKind,
    MixingState,
    count_identity_after,
    experimental_unit_multiplier,
    validate_lineage_graph,
)


def _event(**overrides: Any) -> MaterialLineageEvent:
    payload: dict[str, Any] = {
        "event_id": "EVT-SPLIT-01",
        "kind": MaterialLineageKind.SPLIT,
        "parent_ids": ("culture_01",),
        "child_ids": ("well_A", "well_B"),
        "reference_event_id": None,
        "relation": LineageRelation.UNKNOWN,
        "mixing_state": MixingState.NONE,
        "continuity_state": ContinuityState.SHARED_PARENT_HISTORY,
        "assignment_relation": AssignmentRelation.UNKNOWN,
        "evidence_refs": ("EV-10",),
        "identity_basis": IdentityBasis.SINGLE_PARENT,
    }
    payload.update(overrides)
    return MaterialLineageEvent(**payload)


def test_split_after_assignment_one_eu_remains_one() -> None:
    split = _event(
        assignment_relation=AssignmentRelation.POST_ASSIGNMENT,
        relation=LineageRelation.AFTER,
        identity_basis=IdentityBasis.SINGLE_PARENT,
    )
    assert experimental_unit_multiplier(split) == 1
    assert count_identity_after((split,), 1) == 1


def test_split_before_assignment_increases_only_when_identity_basis_allows() -> None:
    """PRE_ASSIGNMENT may raise candidate assignment units only if identity is preserved.

    ``identity_basis=DISTINCT_ASSIGNMENT_UNIT`` with non-complete mixing allows the
    two children to become candidate assignment units. ``SINGLE_PARENT`` traces
    both children to the same parent and does not invent independence.
    """

    allowed = _event(
        event_id="EVT-SPLIT-PRE-ALLOWED",
        assignment_relation=AssignmentRelation.PRE_ASSIGNMENT,
        relation=LineageRelation.BEFORE,
        identity_basis=IdentityBasis.DISTINCT_ASSIGNMENT_UNIT,
    )
    denied = _event(
        event_id="EVT-SPLIT-PRE-DENIED",
        assignment_relation=AssignmentRelation.PRE_ASSIGNMENT,
        relation=LineageRelation.BEFORE,
        identity_basis=IdentityBasis.SINGLE_PARENT,
    )
    assert experimental_unit_multiplier(allowed) == 2
    assert count_identity_after((allowed,), 1) == 2
    assert experimental_unit_multiplier(denied) == 1
    assert count_identity_after((denied,), 1) == 1


def test_pool_of_two_assigned_units_does_not_become_two_plus_two() -> None:
    pool = _event(
        event_id="EVT-POOL-01",
        kind=MaterialLineageKind.POOL,
        parent_ids=("well_A", "well_B"),
        child_ids=("pool_01",),
        relation=LineageRelation.AFTER,
        mixing_state=MixingState.COMPLETE,
        continuity_state=ContinuityState.MIXED,
        assignment_relation=AssignmentRelation.POST_ASSIGNMENT,
        identity_basis=IdentityBasis.MIXED_PARENTS,
    )
    assert pool.identity_basis is IdentityBasis.MIXED_PARENTS
    assert pool.mixing_state is MixingState.COMPLETE
    assert experimental_unit_multiplier(pool) == 1
    after = count_identity_after((pool,), 2)
    assert after == 2
    assert after != 4


def test_lineage_cycle_rejected() -> None:
    forward = _event(
        event_id="EVT-A",
        parent_ids=("mat_A",),
        child_ids=("mat_B",),
    )
    backward = _event(
        event_id="EVT-B",
        parent_ids=("mat_B",),
        child_ids=("mat_A",),
    )
    with pytest.raises(ValueError, match="lineage cycle"):
        validate_lineage_graph((forward, backward))


def test_passage_and_replate_post_assignment_do_not_multiply_eu() -> None:
    passage = _event(
        event_id="EVT-PASSAGE-01",
        kind=MaterialLineageKind.PASSAGE,
        parent_ids=("culture_01",),
        child_ids=("culture_01_p2",),
        relation=LineageRelation.AFTER,
        assignment_relation=AssignmentRelation.POST_ASSIGNMENT,
        identity_basis=IdentityBasis.SINGLE_PARENT,
    )
    replate = _event(
        event_id="EVT-REPLATE-01",
        kind=MaterialLineageKind.REPLATE,
        parent_ids=("culture_01_p2",),
        child_ids=("plate_01_well_A", "plate_01_well_B"),
        relation=LineageRelation.AFTER,
        assignment_relation=AssignmentRelation.POST_ASSIGNMENT,
        identity_basis=IdentityBasis.SINGLE_PARENT,
    )
    assert experimental_unit_multiplier(passage) == 1
    assert experimental_unit_multiplier(replate) == 1
    assert count_identity_after((passage, replate), 1) == 1


def test_empty_parent_or_child_ids_forbidden() -> None:
    with pytest.raises(ValidationError, match="parent_ids"):
        _event(parent_ids=())
    with pytest.raises(ValidationError, match="child_ids"):
        _event(child_ids=())


def test_self_parent_forbidden() -> None:
    with pytest.raises(ValidationError, match="self-parent forbidden"):
        _event(parent_ids=("mat_A",), child_ids=("mat_A", "mat_B"))


def test_split_does_not_create_independence() -> None:
    with pytest.raises(ValidationError, match="SPLIT does not create independence"):
        _event(continuity_state=ContinuityState.INDEPENDENT)


def test_pool_complete_mixing_rejects_single_parent_identity() -> None:
    with pytest.raises(ValidationError, match="single-parent identity_basis"):
        _event(
            event_id="EVT-POOL-BAD",
            kind=MaterialLineageKind.POOL,
            parent_ids=("well_A", "well_B"),
            child_ids=("pool_01",),
            mixing_state=MixingState.COMPLETE,
            continuity_state=ContinuityState.MIXED,
            assignment_relation=AssignmentRelation.POST_ASSIGNMENT,
            identity_basis=IdentityBasis.SINGLE_PARENT,
        )


def test_missing_reference_event_rejected() -> None:
    split = _event(reference_event_id="EVT-MISSING")
    with pytest.raises(ValueError, match="missing reference_event_id"):
        validate_lineage_graph((split,))
