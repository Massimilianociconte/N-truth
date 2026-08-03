"""Authority ledger and conflict invariants (PRD v7 §0.3-0.4, NFR-25)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ntruth.schemas.authority import (
    AuthorityLedger,
    AuthorityType,
    ConfirmationEvent,
    ConflictRecord,
    higher_authority_wins,
    make_confirmation_id,
    make_conflict_id,
)


def _ts() -> datetime:
    return datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_rule_derivation_cannot_be_confirmation_source() -> None:
    with pytest.raises(ValidationError):
        ConfirmationEvent(
            id="c1",
            authority_type=AuthorityType.RULE_DERIVATION,
            actor_role="system",
            scope="independent_n",
            statement="derived",
            created_at=_ts(),
        )


def test_append_only_ledger_rejects_duplicate_event() -> None:
    event = ConfirmationEvent(
        id=make_confirmation_id("field", AuthorityType.USER_CONFIRMATION, "user", "ok"),
        authority_type=AuthorityType.USER_CONFIRMATION,
        actor_role="user",
        scope="allocation_level",
        statement="well",
        created_at=_ts(),
    )
    ledger = AuthorityLedger(ledger_id="led-1").append_confirmation(event)
    with pytest.raises(ValueError, match="append-only"):
        ledger.append_confirmation(event)


def test_unresolved_decisive_conflict_blocks_determinate() -> None:
    conflict = ConflictRecord(
        id=make_conflict_id("allocation_level", ("paper", "author")),
        field="allocation_level",
        sources=("paper", "author"),
        status="unresolved",
    )
    ledger = AuthorityLedger(ledger_id="led-1").append_conflict(conflict)
    assert ledger.blocks_determinate(frozenset({"allocation_level"}))
    assert not ledger.blocks_determinate(frozenset({"endpoint_id"}))


def test_resolution_keeps_conflict_record() -> None:
    conflict = ConflictRecord(
        id=make_conflict_id("allocation_level", ("paper", "author")),
        field="allocation_level",
        sources=("paper", "author"),
        status="unresolved",
    )
    resolution = ConfirmationEvent(
        id="res-1",
        authority_type=AuthorityType.EXPERT_ADJUDICATION,
        actor_role="domain_expert",
        scope="allocation_level",
        statement="well",
        rationale="figure S1 shows well-level dosing",
        created_at=_ts(),
    )
    ledger = AuthorityLedger(ledger_id="led-1").append_conflict(conflict)
    ledger = ledger.resolve_conflict(
        conflict.id, resolution, decision="well", rationale="figure S1"
    )
    assert len(ledger.conflicts) == 1
    assert ledger.conflicts[0].status == "resolved_with_rationale"
    assert ledger.conflicts[0].resolution_event_id == "res-1"
    assert not ledger.blocks_determinate(frozenset({"allocation_level"}))


def test_higher_authority_wins_ranking() -> None:
    assert (
        higher_authority_wins(AuthorityType.USER_CONFIRMATION, AuthorityType.AUTHOR_CLARIFICATION)
        is AuthorityType.AUTHOR_CLARIFICATION
    )
    assert (
        higher_authority_wins(AuthorityType.SYSTEM_INFERENCE, AuthorityType.SYSTEM_INFERENCE)
        is None
    )


def test_expert_adjudication_requires_rationale() -> None:
    with pytest.raises(ValidationError):
        ConfirmationEvent(
            id="c2",
            authority_type=AuthorityType.EXPERT_ADJUDICATION,
            actor_role="expert",
            scope="n",
            statement="n=6",
            rationale="",
            created_at=_ts(),
        )
