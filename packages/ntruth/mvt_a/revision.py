"""Human revision patch and burden metrics for MVT-A (PRD v7 §4.2, §15).

Records time/burden, false certainty and decisive corrections without claiming
scientific validation thresholds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import Field, field_validator, model_validator

from ntruth.schemas.core import FrozenModel


class BurdenRecord(FrozenModel):
    """Minutes and free-text dependency; no hard-coded 2-8h norms."""

    minutes_total: float = Field(ge=0.0)
    minutes_per_field: dict[str, float] = Field(default_factory=dict)
    free_text_fields: tuple[str, ...] = ()
    unknown_field_count: int = Field(default=0, ge=0)
    disagreement_count: int = Field(default=0, ge=0)
    adjudication_required: bool = False


class FalseCertaintyRecord(FrozenModel):
    """A place where a candidate claimed certainty that review rejected."""

    field: str
    candidate_value: str
    corrected_value: str
    rationale: str


class DecisiveCorrection(FrozenModel):
    field: str
    before: str
    after: str
    affects_determinability: bool = True


class HumanRevisionPatch(FrozenModel):
    """Append-only style patch from human review of MVT-A candidates."""

    patch_id: str
    stage_id: str
    actor_role: str  # role only, never personal identity
    created_at: datetime
    corrections: tuple[DecisiveCorrection, ...] = ()
    false_certainty: tuple[FalseCertaintyRecord, ...] = ()
    burden: BurdenRecord | None = None
    notes: str = ""

    @field_validator("created_at")
    @classmethod
    def _tz(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at deve includere il fuso orario")
        return value

    @model_validator(mode="after")
    def _role(self) -> Self:
        if not self.actor_role.strip():
            raise ValueError("revision patch senza actor_role")
        return self

    @property
    def decisive_correction_count(self) -> int:
        return sum(1 for c in self.corrections if c.affects_determinability)
