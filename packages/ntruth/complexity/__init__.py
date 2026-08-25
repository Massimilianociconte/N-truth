"""Complexity tiers and burden tracking (PRD v7 §15).

No hard-coded 2-8 hours, IAA 0.60, 70% indeterminacy, or disputed 50% ruleset
coverage thresholds. Those remain PROVISIONAL when referenced in product text.
"""

from ntruth.complexity.tiers import (
    CanonicalComplexityTier,
    ComplexityTier,
    FieldBurden,
    SchemaBurdenGate,
    TierBurdenReport,
    canonical_to_legacy_tier,
    legacy_to_canonical_tiers,
)

__all__ = [
    "CanonicalComplexityTier",
    "ComplexityTier",
    "FieldBurden",
    "SchemaBurdenGate",
    "TierBurdenReport",
    "canonical_to_legacy_tier",
    "legacy_to_canonical_tiers",
]
