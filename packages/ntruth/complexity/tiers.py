"""Complexity and Schema Burden Gate structures."""

from __future__ import annotations

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
