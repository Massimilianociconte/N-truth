"""PRD v9 section 17.2 canonical complexity tiers C0-C4 and legacy mapping."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.complexity import (
    CanonicalComplexityTier,
    ComplexityTier,
    SchemaBurdenGate,
    canonical_to_legacy_tier,
    legacy_to_canonical_tiers,
)
from ntruth.complexity.tiers import TierBurdenReport


def test_canonical_tier_members_match_prd_v9_17_2() -> None:
    assert [tier.value for tier in CanonicalComplexityTier] == [
        "C0_SINGLE_SOURCE_EXPLICIT_ASSIGNMENT",
        "C1_SIMPLE_MULTI_SOURCE_EXPLICIT_APPLICATION",
        "C2_IMPLICIT_ASSIGNMENT_LIFECYCLE_CONFLICTS",
        "C3_MULTI_BLOCK_POOLING_INTERFERENCE",
        "C4_ADVANCED_PROFILE_OOD",
    ]


def test_legacy_mapping_covers_every_legacy_tier() -> None:
    assert legacy_to_canonical_tiers(ComplexityTier.SIMPLE) == (
        CanonicalComplexityTier.C0_SINGLE_SOURCE_EXPLICIT_ASSIGNMENT,
        CanonicalComplexityTier.C1_SIMPLE_MULTI_SOURCE_EXPLICIT_APPLICATION,
    )
    assert legacy_to_canonical_tiers(ComplexityTier.MODERATE) == (
        CanonicalComplexityTier.C2_IMPLICIT_ASSIGNMENT_LIFECYCLE_CONFLICTS,
    )
    assert legacy_to_canonical_tiers(ComplexityTier.COMPLEX) == (
        CanonicalComplexityTier.C3_MULTI_BLOCK_POOLING_INTERFERENCE,
    )
    assert legacy_to_canonical_tiers(ComplexityTier.OUT_OF_PROFILE) == (
        CanonicalComplexityTier.C4_ADVANCED_PROFILE_OOD,
    )


def test_reverse_mapping_is_total_and_unique() -> None:
    for canonical in CanonicalComplexityTier:
        assert canonical_to_legacy_tier(canonical) in set(ComplexityTier)
    assert (
        canonical_to_legacy_tier(CanonicalComplexityTier.C0_SINGLE_SOURCE_EXPLICIT_ASSIGNMENT)
        is ComplexityTier.SIMPLE
    )
    assert (
        canonical_to_legacy_tier(
            CanonicalComplexityTier.C1_SIMPLE_MULTI_SOURCE_EXPLICIT_APPLICATION
        )
        is ComplexityTier.SIMPLE
    )
    assert (
        canonical_to_legacy_tier(CanonicalComplexityTier.C2_IMPLICIT_ASSIGNMENT_LIFECYCLE_CONFLICTS)
        is ComplexityTier.MODERATE
    )
    assert (
        canonical_to_legacy_tier(CanonicalComplexityTier.C3_MULTI_BLOCK_POOLING_INTERFERENCE)
        is ComplexityTier.COMPLEX
    )
    assert (
        canonical_to_legacy_tier(CanonicalComplexityTier.C4_ADVANCED_PROFILE_OOD)
        is ComplexityTier.OUT_OF_PROFILE
    )


def test_legacy_names_are_unchanged_for_existing_callers() -> None:
    assert [tier.value for tier in ComplexityTier] == [
        "SIMPLE",
        "MODERATE",
        "COMPLEX",
        "OUT_OF_PROFILE",
    ]
    report = TierBurdenReport(tier=ComplexityTier.MODERATE)
    assert report.tier is ComplexityTier.MODERATE
    assert report.minutes_total == 0.0


def test_round_trip_through_both_vocabularies() -> None:
    for legacy in ComplexityTier:
        for canonical in legacy_to_canonical_tiers(legacy):
            assert canonical_to_legacy_tier(canonical) is legacy


def test_unknown_canonical_tier_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown canonical"):
        canonical_to_legacy_tier("C9_NOT_A_TIER")  # type: ignore[arg-type]


def test_burden_gate_still_validates_against_legacy_tiers() -> None:
    gate = SchemaBurdenGate(profile="D0", tier=ComplexityTier.SIMPLE, blocking=False)
    assert gate.blocking is False
    with pytest.raises(ValidationError):
        SchemaBurdenGate.model_validate(
            {"profile": "D0", "tier": "C4_ADVANCED_PROFILE_OOD", "blocking": True}
        )
