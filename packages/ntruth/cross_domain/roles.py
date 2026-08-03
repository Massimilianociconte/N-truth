"""Profile-relative data roles with fail-closed defaults."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import model_validator

from ntruth.schemas.core import FrozenModel


class DataRole(StrEnum):
    GOLD = "gold"
    SILVER = "silver"
    AUXILIARY = "auxiliary"
    HELD_OUT_CHALLENGE = "held_out_challenge"
    SCHEMA_ALIGNMENT = "schema_alignment"
    CROSS_DOMAIN_STRESS = "cross_domain_stress"
    FORBIDDEN = "forbidden"
    UNDECIDED = "undecided"


class CrossDomainRoleDecision(FrozenModel):
    """Role decision before any train/dev/test access."""

    source_domain: str
    source_profile: str
    target_profile: str
    annotation_authority: str
    allowed_roles: tuple[DataRole, ...]
    forbidden_roles: tuple[DataRole, ...]
    chosen_role: DataRole = DataRole.UNDECIDED
    access_before_role_decision: bool = False
    licence_use_decision: str = "unknown"  # verified|restricted|unknown|denied
    train_dev_test_isolation: bool = True
    rationale: str = ""

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        if self.access_before_role_decision:
            raise ValueError(
                "access before role decision is forbidden: decide role first (fail-closed)"
            )
        if self.chosen_role is not DataRole.UNDECIDED:
            if self.chosen_role in self.forbidden_roles:
                raise ValueError(f"role {self.chosen_role} is forbidden for this transfer")
            if self.chosen_role not in self.allowed_roles:
                raise ValueError(f"role {self.chosen_role} not in allowed_roles")
        if self.licence_use_decision in ("unknown", "denied") and self.chosen_role in (
            DataRole.GOLD,
            DataRole.SILVER,
        ):
            raise ValueError("gold/silver require verified licence/use decision")
        if self.source_profile != self.target_profile and self.chosen_role is DataRole.GOLD:
            raise ValueError(
                "cross-profile GOLD is forbidden: high-quality source cannot auto-validate target release"
            )
        return self


def decide_cross_domain_role(
    *,
    source_domain: str,
    source_profile: str,
    target_profile: str,
    annotation_authority: str,
    licence_use_decision: str = "unknown",
    preferred_role: DataRole = DataRole.UNDECIDED,
) -> CrossDomainRoleDecision:
    """Conservative policy: same-profile gold ok; cross-profile never gold."""
    same = source_profile == target_profile
    allowed: tuple[DataRole, ...]
    forbidden: tuple[DataRole, ...]
    if same:
        allowed = (
            DataRole.GOLD,
            DataRole.SILVER,
            DataRole.AUXILIARY,
            DataRole.HELD_OUT_CHALLENGE,
            DataRole.SCHEMA_ALIGNMENT,
        )
        forbidden = (DataRole.CROSS_DOMAIN_STRESS,)
    else:
        allowed = (
            DataRole.AUXILIARY,
            DataRole.HELD_OUT_CHALLENGE,
            DataRole.SCHEMA_ALIGNMENT,
            DataRole.CROSS_DOMAIN_STRESS,
        )
        forbidden = (DataRole.GOLD, DataRole.SILVER)

    chosen = preferred_role
    if chosen is DataRole.UNDECIDED:
        pass
    elif chosen in forbidden:
        chosen = DataRole.FORBIDDEN

    # if licence unknown, force undecided rather than gold/silver
    if licence_use_decision in ("unknown", "denied") and chosen in (
        DataRole.GOLD,
        DataRole.SILVER,
    ):
        chosen = DataRole.UNDECIDED

    return CrossDomainRoleDecision(
        source_domain=source_domain,
        source_profile=source_profile,
        target_profile=target_profile,
        annotation_authority=annotation_authority,
        allowed_roles=allowed,
        forbidden_roles=forbidden,
        chosen_role=chosen if chosen is not DataRole.FORBIDDEN else DataRole.UNDECIDED,
        access_before_role_decision=False,
        licence_use_decision=licence_use_decision,
        train_dev_test_isolation=True,
        rationale=(
            "same-profile transfer"
            if same
            else "cross-profile: gold forbidden; use stress/alignment/challenge only"
        ),
    )
