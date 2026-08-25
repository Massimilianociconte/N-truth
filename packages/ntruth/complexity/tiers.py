"""Complexity and Schema Burden Gate structures.

PRD v9 section 17.2 introduces canonical tiers C0-C4:

- C0: single source, explicit assignment, no lineage ambiguity;
- C1: simple multi-source, explicit split/application;
- C2: implicit assignment, lifecycle counts, simple conflicts;
- C3: multi-block, pooling/replating, interference or aliasing;
- C4: advanced profile, OOD, complex repeated/multifactor.

The legacy v7 vocabulary maps onto it as SIMPLE -> {C0, C1} (the legacy tier
under-specifies the split), MODERATE -> C2, COMPLEX -> C3 and
OUT_OF_PROFILE -> C4.  Legacy names stay first-class so existing callers are
unaffected; the mapping is total and deterministic in both directions.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from pydantic import Field, computed_field

from ntruth.schemas.core import FrozenModel


class ComplexityTier(StrEnum):
    SIMPLE = "SIMPLE"
    MODERATE = "MODERATE"
    COMPLEX = "COMPLEX"
    OUT_OF_PROFILE = "OUT_OF_PROFILE"


class FieldBurden(FrozenModel):
    field: str
    minutes: float = Field(ge=0.0)
    unknown: bool = False
    free_text: bool = False
    disagreement: bool = False
    adjudication: bool = False
    field_value_note: str = ""


class TierBurdenReport(FrozenModel):
    """Observed burden for a tier - observational, not a hard gate number."""

    tier: ComplexityTier
    fields: tuple[FieldBurden, ...] = ()
    minutes_total_override: float | None = Field(default=None, ge=0.0)
    unknown_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    free_text_dependency_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    disagreement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    adjudication_burden_minutes: float = Field(default=0.0, ge=0.0)
    notes: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def minutes_total(self) -> float:
        if self.minutes_total_override is not None:
            return self.minutes_total_override
        return float(sum(f.minutes for f in self.fields))


class SchemaBurdenGate(FrozenModel):
    """Reporting contract: whether schema burden blocks promotion.

    Threshold fields are optional and must be marked provisional when set.
    """

    profile: str
    tier: ComplexityTier
    blocking: bool = False
    blockers: tuple[str, ...] = ()
    provisional_threshold_notes: tuple[str, ...] = ()
    # Explicitly NOT hard-coded scientific validators:
    # - minutes bounds
    # - IAA cutoffs
    # - indeterminacy percentages
    # - ruleset coverage 50% redirect


class CanonicalComplexityTier(StrEnum):
    C0_SINGLE_SOURCE_EXPLICIT_ASSIGNMENT = "C0_SINGLE_SOURCE_EXPLICIT_ASSIGNMENT"
    C1_SIMPLE_MULTI_SOURCE_EXPLICIT_APPLICATION = "C1_SIMPLE_MULTI_SOURCE_EXPLICIT_APPLICATION"
    C2_IMPLICIT_ASSIGNMENT_LIFECYCLE_CONFLICTS = "C2_IMPLICIT_ASSIGNMENT_LIFECYCLE_CONFLICTS"
    C3_MULTI_BLOCK_POOLING_INTERFERENCE = "C3_MULTI_BLOCK_POOLING_INTERFERENCE"
    C4_ADVANCED_PROFILE_OOD = "C4_ADVANCED_PROFILE_OOD"


_LEGACY_TO_CANONICAL: Mapping[ComplexityTier, tuple[CanonicalComplexityTier, ...]] = {
    ComplexityTier.SIMPLE: (
        CanonicalComplexityTier.C0_SINGLE_SOURCE_EXPLICIT_ASSIGNMENT,
        CanonicalComplexityTier.C1_SIMPLE_MULTI_SOURCE_EXPLICIT_APPLICATION,
    ),
    ComplexityTier.MODERATE: (CanonicalComplexityTier.C2_IMPLICIT_ASSIGNMENT_LIFECYCLE_CONFLICTS,),
    ComplexityTier.COMPLEX: (CanonicalComplexityTier.C3_MULTI_BLOCK_POOLING_INTERFERENCE,),
    ComplexityTier.OUT_OF_PROFILE: (CanonicalComplexityTier.C4_ADVANCED_PROFILE_OOD,),
}

_CANONICAL_TO_LEGACY: Mapping[CanonicalComplexityTier, ComplexityTier] = {
    canonical: legacy
    for legacy, canonicals in _LEGACY_TO_CANONICAL.items()
    for canonical in canonicals
}


def legacy_to_canonical_tiers(tier: ComplexityTier) -> tuple[CanonicalComplexityTier, ...]:
    """Return the canonical candidates; SIMPLE legitimately spans C0 and C1."""
    return _LEGACY_TO_CANONICAL[tier]


def canonical_to_legacy_tier(tier: CanonicalComplexityTier) -> ComplexityTier:
    """Return the unique legacy tier; unknown members fail closed."""
    try:
        return _CANONICAL_TO_LEGACY[tier]
    except KeyError as exc:
        raise ValueError(f"unknown canonical complexity tier: {tier!r}") from exc
