"""InferentialQuery: ogni conclusione e associata a un oggetto versionato (PRD v7 §7.8).

EU e independent_n non possono essere emessi senza factor, contrast, endpoint e
scope osservato. I campi UNKNOWN bloccano generalizzazioni non supportate.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel, stable_id


class InferentialQuery(FrozenModel):
    """Domanda inferenziale versionata (PRD v7 §7.8)."""

    id: str
    factor_id: str
    compared_levels: tuple[str, ...] = Field(min_length=2)
    endpoint_id: str
    effect_measure_or_estimand: str = "unknown"
    inference_population: str = "unknown"
    inference_level: str = "unknown"
    condition_or_timepoint: str | None = None

    @model_validator(mode="after")
    def _minimum(self) -> Self:
        if not self.factor_id.strip():
            raise ValueError("inferential query senza factor_id")
        if not self.endpoint_id.strip():
            raise ValueError("inferential query senza endpoint_id")
        if len(set(self.compared_levels)) != len(self.compared_levels):
            raise ValueError("livelli del contrasto duplicati")
        return self

    @property
    def scope_is_unknown(self) -> bool:
        return self.inference_population == "unknown" or self.inference_level == "unknown"


def make_query_id(factor_id: str, endpoint_id: str, levels: tuple[str, ...]) -> str:
    return stable_id("iq", factor_id, endpoint_id, *sorted(levels))
