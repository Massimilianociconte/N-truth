"""PRD v9 Appendix AG.1 external challenge lifecycle state machine.

The machine is deliberately fail-closed: illegal transitions raise, item-level
feedback is rejected while a challenge version is ACTIVE, and activation is
blocked unless every required item carries a readable contamination attestation
(PRD v9 section 14.10).  The attestation contract stays read-only here.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.kernel import NonBlankStr

if TYPE_CHECKING:
    from ntruth.governance.contamination import ContaminationAttestationV8


class ChallengeLifecycleError(ValueError):
    """Raised on any illegal lifecycle operation (fail-closed)."""


class ChallengeLifecycleState(StrEnum):
    DRAFT = "DRAFT"
    FROZEN = "FROZEN"
    ACTIVE = "ACTIVE"
    RETIRED_DIAGNOSTIC = "RETIRED_DIAGNOSTIC"
    PUBLIC_ARCHIVE = "PUBLIC_ARCHIVE"


class ItemLevelFeedbackPolicy(StrEnum):
    PROHIBITED_WHILE_ACTIVE = "PROHIBITED_WHILE_ACTIVE"


_ALLOWED_TRANSITIONS: dict[ChallengeLifecycleState, frozenset[ChallengeLifecycleState]] = {
    ChallengeLifecycleState.DRAFT: frozenset({ChallengeLifecycleState.FROZEN}),
    ChallengeLifecycleState.FROZEN: frozenset({ChallengeLifecycleState.ACTIVE}),
    # Scheduled retirement and early retirement (leakage, exposure or overuse
    # per PRD v9 section 14.10) share the same edge.
    ChallengeLifecycleState.ACTIVE: frozenset({ChallengeLifecycleState.RETIRED_DIAGNOSTIC}),
    ChallengeLifecycleState.RETIRED_DIAGNOSTIC: frozenset({ChallengeLifecycleState.PUBLIC_ARCHIVE}),
    ChallengeLifecycleState.PUBLIC_ARCHIVE: frozenset(),
}


class ChallengeVersionRecord(FrozenModel):
    """One custodied challenge version and its lifecycle position."""

    challenge_id: NonBlankStr
    version: NonBlankStr
    custodian_actor_id: NonBlankStr
    custodian_external: Literal[True] = True
    retirement_policy_id: NonBlankStr
    access_log_required: Literal[True] = True
    item_level_feedback: ItemLevelFeedbackPolicy = ItemLevelFeedbackPolicy.PROHIBITED_WHILE_ACTIVE
    lifecycle_state: ChallengeLifecycleState = ChallengeLifecycleState.DRAFT
    frozen_at: datetime | None = None

    @model_validator(mode="after")
    def _freeze_consistency(self) -> Self:
        if self.frozen_at is not None and (
            self.frozen_at.tzinfo is None or self.frozen_at.utcoffset() is None
        ):
            raise ValueError("challenge freeze timestamp must include a timezone")
        post_draft = {
            ChallengeLifecycleState.FROZEN,
            ChallengeLifecycleState.ACTIVE,
            ChallengeLifecycleState.RETIRED_DIAGNOSTIC,
            ChallengeLifecycleState.PUBLIC_ARCHIVE,
        }
        if self.lifecycle_state in post_draft and self.frozen_at is None:
            raise ValueError("challenge versions past DRAFT must record frozen_at")
        return self


def can_transition(current: ChallengeLifecycleState, target: ChallengeLifecycleState) -> bool:
    return target in _ALLOWED_TRANSITIONS[current]


def require_transition(current: ChallengeLifecycleState, target: ChallengeLifecycleState) -> None:
    if not can_transition(current, target):
        raise ChallengeLifecycleError(
            f"illegal challenge lifecycle transition {current.value} -> {target.value}"
        )


def apply_transition(
    record: ChallengeVersionRecord,
    target: ChallengeLifecycleState,
    *,
    occurred_at: datetime,
    future_use_policy_updated: bool = False,
) -> ChallengeVersionRecord:
    """Return the record moved to ``target``; raise on anything illegal."""
    require_transition(record.lifecycle_state, target)
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("lifecycle timestamp must include a timezone")
    updates: dict[str, Any] = {"lifecycle_state": target}
    if target is ChallengeLifecycleState.FROZEN:
        updates["frozen_at"] = occurred_at
    if target is ChallengeLifecycleState.PUBLIC_ARCHIVE and not future_use_policy_updated:
        raise ChallengeLifecycleError(
            "public archive requires the contamination risk and future-use "
            "policy to be updated first"
        )
    return record.model_copy(update=updates)


def item_level_feedback_permitted(record: ChallengeVersionRecord) -> bool:
    """Item-level answers exist only in the public archive.

    ACTIVE forbids them outright; DRAFT/FROZEN are inaccessible or locked;
    RETIRED_DIAGNOSTIC may expose aggregated diagnostics only.
    """
    return record.lifecycle_state is ChallengeLifecycleState.PUBLIC_ARCHIVE


def reject_item_level_feedback_while_active(record: ChallengeVersionRecord) -> None:
    """Fail closed if item-level feedback is requested while ACTIVE."""
    if record.item_level_feedback is ItemLevelFeedbackPolicy.PROHIBITED_WHILE_ACTIVE and (
        record.lifecycle_state is ChallengeLifecycleState.ACTIVE
    ):
        raise ChallengeLifecycleError(
            "item-level feedback is prohibited while the challenge version is ACTIVE"
        )


def _load_contestation_type() -> type[Any] | None:
    try:
        from ntruth.governance.contamination import ContaminationAttestationV8
    except ImportError:
        return None
    return ContaminationAttestationV8


def activation_blockers(
    attestations: Sequence[ContaminationAttestationV8],
    *,
    required_item_ids: Collection[str],
) -> tuple[str, ...]:
    """Reasons the FROZEN -> ACTIVE move must stay blocked; empty means go.

    Read-only over :class:`ContaminationAttestationV8`.  If the contamination
    module cannot be imported at all every item reports a blocker.
    """
    attestation_type = _load_contestation_type()
    if attestation_type is None:
        return tuple(
            f"contamination_module_unavailable:{item_id}" for item_id in sorted(required_item_ids)
        )
    blockers: list[str] = []
    by_item: dict[str, list[Any]] = {}
    for attestation in attestations:
        if isinstance(attestation, attestation_type):
            by_item.setdefault(attestation.challenge_item_id, []).append(attestation)
    for item_id in sorted(required_item_ids):
        candidates = by_item.get(item_id, ())
        if not candidates:
            blockers.append(f"missing_contamination_attestation:{item_id}")
            continue
        item_blockers: list[str] = []
        satisfied = False
        for candidate in candidates:
            residual = candidate.residual_risk
            if str(residual.knowledge_state) != "PRESENT":
                continue
            risk_value = getattr(residual.value, "value", residual.value)
            if risk_value is None:
                continue
            risk = str(risk_value)
            if risk in {"HIGH", "UNKNOWN"}:
                item_blockers.append(f"residual_risk_{risk.lower()}:{item_id}")
            else:
                satisfied = True
        if not satisfied:
            if not item_blockers:
                item_blockers.append(f"unresolved_residual_risk:{item_id}")
            blockers.extend(item_blockers)
    return tuple(blockers)


def require_activation_ready(
    attestations: Sequence[ContaminationAttestationV8],
    *,
    required_item_ids: Collection[str],
) -> None:
    blockers = activation_blockers(attestations, required_item_ids=required_item_ids)
    if blockers:
        raise ChallengeLifecycleError(f"challenge activation blocked: {'; '.join(blockers)}")


__all__ = [
    "ChallengeLifecycleError",
    "ChallengeLifecycleState",
    "ChallengeVersionRecord",
    "ItemLevelFeedbackPolicy",
    "activation_blockers",
    "apply_transition",
    "can_transition",
    "item_level_feedback_permitted",
    "reject_item_level_feedback_while_active",
    "require_activation_ready",
    "require_transition",
]
