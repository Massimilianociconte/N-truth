"""PRD v8 inferential-query contract.

The v7 bootstrap model remains in :mod:`ntruth.schemas.inferential_query` as a
legacy input contract.  This module is the versioned v8 kernel representation.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeValue


def _knowledge_scope_key(value: KnowledgeValue[NonBlankStr]) -> tuple[str, str | None]:
    return (value.knowledge_state.value, value.value)


class InferentialQuery(KernelModel):
    """One versioned factor/contrast/endpoint/timepoint inferential scope."""

    id: NonBlankStr
    profile_id: NonBlankStr
    factor_id: NonBlankStr
    contrast_id: NonBlankStr
    compared_levels: tuple[NonBlankStr, ...] = Field(min_length=2)
    endpoint_id: NonBlankStr
    timepoint_id: KnowledgeValue[NonBlankStr]
    effect_measure_or_estimand: KnowledgeValue[NonBlankStr]
    inference_population: KnowledgeValue[NonBlankStr]
    inference_level: KnowledgeValue[NonBlankStr]

    @model_validator(mode="after")
    def _query_invariants(self) -> Self:
        normalized_levels = tuple(level.casefold() for level in self.compared_levels)
        if len(set(normalized_levels)) != len(normalized_levels):
            raise ValueError("compared_levels must be distinct")

        for field_name in (
            "timepoint_id",
            "effect_measure_or_estimand",
            "inference_population",
            "inference_level",
        ):
            value = getattr(self, field_name)
            if value.query_scope_id is not None and value.query_scope_id != self.id:
                raise ValueError(f"{field_name}.query_scope_id must match query id")
        return self

    def scope_key(self) -> tuple[object, ...]:
        """Return an identifier-preserving key; no scientific equivalence is inferred."""

        return (
            self.id,
            self.profile_id,
            self.factor_id,
            self.contrast_id,
            self.compared_levels,
            self.endpoint_id,
            _knowledge_scope_key(self.timepoint_id),
            _knowledge_scope_key(self.effect_measure_or_estimand),
            _knowledge_scope_key(self.inference_population),
            _knowledge_scope_key(self.inference_level),
        )


__all__ = ["InferentialQuery"]
