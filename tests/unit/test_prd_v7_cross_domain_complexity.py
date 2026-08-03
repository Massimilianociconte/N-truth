"""Cross-domain roles and complexity/burden structures."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.complexity import ComplexityTier, FieldBurden, SchemaBurdenGate, TierBurdenReport
from ntruth.cross_domain import DataRole, decide_cross_domain_role
from ntruth.cross_domain.roles import CrossDomainRoleDecision


def test_cross_profile_gold_forbidden() -> None:
    decision = decide_cross_domain_role(
        source_domain="in_vivo",
        source_profile="animal",
        target_profile="simple_cell_culture",
        annotation_authority="expert",
        licence_use_decision="verified",
        preferred_role=DataRole.HELD_OUT_CHALLENGE,
    )
    assert DataRole.GOLD in decision.forbidden_roles
    assert decision.chosen_role is DataRole.HELD_OUT_CHALLENGE


def test_same_profile_gold_requires_licence() -> None:
    with pytest.raises(ValidationError):
        CrossDomainRoleDecision(
            source_domain="in_vitro",
            source_profile="simple_cell_culture",
            target_profile="simple_cell_culture",
            annotation_authority="annotator",
            allowed_roles=(DataRole.GOLD,),
            forbidden_roles=(),
            chosen_role=DataRole.GOLD,
            licence_use_decision="unknown",
        )


def test_access_before_role_decision_forbidden() -> None:
    with pytest.raises(ValidationError):
        CrossDomainRoleDecision(
            source_domain="x",
            source_profile="a",
            target_profile="b",
            annotation_authority="r",
            allowed_roles=(DataRole.AUXILIARY,),
            forbidden_roles=(DataRole.GOLD,),
            access_before_role_decision=True,
        )


def test_burden_has_no_hardcoded_hours_gate() -> None:
    report = TierBurdenReport(
        tier=ComplexityTier.SIMPLE,
        fields=(
            FieldBurden(field="allocation", minutes=5.0, unknown=True),
            FieldBurden(field="endpoint", minutes=2.0),
        ),
    )
    assert report.minutes_total == 7.0
    gate = SchemaBurdenGate(
        profile="simple_cell_culture",
        tier=ComplexityTier.SIMPLE,
        blocking=False,
        provisional_threshold_notes=("IAA cutoffs are PROVISIONAL product hypotheses",),
    )
    assert gate.blocking is False
