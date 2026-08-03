"""Profile-relative data roles with fail-closed defaults."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

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


class AnnotationAuthority(FrozenModel):
    role: str
    protocol_id: str | None = None
    decisive_fields_second_review: bool = False
    authority_event_ref: str | None = None


class GoldEligibility(FrozenModel):
    complete_provenance: bool = False
    decisive_fields_second_review: bool = False
    expert_adjudication: bool = False
    approved_gold_protocol: bool = False
    split_leakage_clear: bool = False

    @property
    def satisfied(self) -> bool:
        return all(
            (
                self.complete_provenance,
                self.decisive_fields_second_review,
                self.expert_adjudication,
                self.approved_gold_protocol,
                self.split_leakage_clear,
            )
        )


class CrossDomainRoleDecision(FrozenModel):
    source_domain: str
    source_profile: str
    target_profile: str
    annotation_authority: AnnotationAuthority
    allowed_roles: tuple[DataRole, ...]
    forbidden_roles: tuple[DataRole, ...]
    chosen_role: DataRole = DataRole.UNDECIDED
    access_before_role_decision: bool = False
    licence_use_decision: str = "unknown"
    train_dev_test_isolation: bool = True
    gold_eligibility: GoldEligibility = Field(default_factory=GoldEligibility)
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
        if self.chosen_role is DataRole.GOLD:
            if (
                self.annotation_authority.role == "annotator"
                and not self.gold_eligibility.satisfied
            ):
                raise ValueError(
                    "annotator authority alone is insufficient for GOLD; full eligibility required"
                )
            if not self.gold_eligibility.satisfied:
                raise ValueError(
                    "GOLD requires complete provenance, second review, adjudication, "
                    "approved gold protocol and split/leakage eligibility"
                )
            if not self.annotation_authority.protocol_id:
                raise ValueError("GOLD requires annotation_authority.protocol_id")
        return self


def decide_cross_domain_role(
    *,
    source_domain: str,
    source_profile: str,
    target_profile: str,
    annotation_authority: AnnotationAuthority | str,
    licence_use_decision: str = "unknown",
    preferred_role: DataRole = DataRole.UNDECIDED,
    gold_eligibility: GoldEligibility | None = None,
) -> CrossDomainRoleDecision:
    if isinstance(annotation_authority, str):
        annotation_authority = AnnotationAuthority(role=annotation_authority)
    eligibility = gold_eligibility or GoldEligibility()
    same = source_profile == target_profile
    if same:
        allowed: tuple[DataRole, ...] = (
            DataRole.GOLD,
            DataRole.SILVER,
            DataRole.AUXILIARY,
            DataRole.HELD_OUT_CHALLENGE,
            DataRole.SCHEMA_ALIGNMENT,
        )
        forbidden: tuple[DataRole, ...] = (DataRole.CROSS_DOMAIN_STRESS,)
    else:
        allowed = (
            DataRole.AUXILIARY,
            DataRole.HELD_OUT_CHALLENGE,
            DataRole.SCHEMA_ALIGNMENT,
            DataRole.CROSS_DOMAIN_STRESS,
        )
        forbidden = (DataRole.GOLD, DataRole.SILVER)

    chosen = preferred_role
    if chosen is not DataRole.UNDECIDED and chosen in forbidden:
        chosen = DataRole.UNDECIDED
    if licence_use_decision in ("unknown", "denied") and chosen in (
        DataRole.GOLD,
        DataRole.SILVER,
    ):
        chosen = DataRole.UNDECIDED
    if chosen is DataRole.GOLD and not eligibility.satisfied:
        chosen = DataRole.UNDECIDED

    return CrossDomainRoleDecision(
        source_domain=source_domain,
        source_profile=source_profile,
        target_profile=target_profile,
        annotation_authority=annotation_authority,
        allowed_roles=allowed,
        forbidden_roles=forbidden,
        chosen_role=chosen,
        access_before_role_decision=False,
        licence_use_decision=licence_use_decision,
        train_dev_test_isolation=True,
        gold_eligibility=eligibility,
        rationale=(
            "same-profile transfer"
            if same
            else "cross-profile: gold forbidden; use stress/alignment/challenge only"
        ),
    )
