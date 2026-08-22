"""PRD v9 ContrastSupport / ExposurePartition / assignment-anchored EU claims.

These contracts are a v9 sidecar. They are not the v8 binding kernel and do not
rewrite experimental-unit identity from realized exposure or shared baths.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, ValidationInfo, field_validator, model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.kernel import NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

AssignmentAnchoredValue = KnowledgeValue[NonBlankStr] | KnowledgeState | NonBlankStr


class ContrastSupportStatus(StrEnum):
    SUPPORTED_WITHIN_RECORDED_DESIGN = "SUPPORTED_WITHIN_RECORDED_DESIGN"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    STRUCTURALLY_ALIASED = "STRUCTURALLY_ALIASED"
    NO_LEVEL_VARIATION = "NO_LEVEL_VARIATION"
    EXPOSURE_MAPPING_INADEQUATE = "EXPOSURE_MAPPING_INADEQUATE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


def _unique_ids(items: tuple[NonBlankStr, ...], label: str) -> tuple[NonBlankStr, ...]:
    if len(set(items)) != len(items):
        raise ValueError(f"{label} contains duplicates")
    return items


class ContrastSupportClaim(FrozenModel):
    """Whether recorded levels, block variation and separability support a contrast."""

    query_id: NonBlankStr
    factor_id: NonBlankStr
    status: ContrastSupportStatus
    level_presence: bool
    within_block_variation: bool
    aliasing_factors: tuple[NonBlankStr, ...] = ()
    exposure_partition_id: NonBlankStr | None = None
    missing_predicates: tuple[NonBlankStr, ...] = ()
    proof_refs: tuple[NonBlankStr, ...] = ()

    @field_validator("aliasing_factors", "missing_predicates", "proof_refs")
    @classmethod
    def _unique_string_tuples(
        cls, value: tuple[NonBlankStr, ...], info: ValidationInfo
    ) -> tuple[NonBlankStr, ...]:
        return _unique_ids(value, info.field_name or "ids")


class ExposurePartitionClaim(FrozenModel):
    """Units that share a realized exposure pathway; never an experimental unit."""

    id: NonBlankStr
    unit_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    pathway: NonBlankStr
    shared_exposure: KnowledgeValue[bool]

    @field_validator("unit_ids")
    @classmethod
    def _unique_units(cls, value: tuple[NonBlankStr, ...]) -> tuple[NonBlankStr, ...]:
        return _unique_ids(value, "unit_ids")


class ExperimentalUnitClaim(FrozenModel):
    """Assignment-history identity for an assigned-intervention experimental unit.

    ``assignment_event_id`` is required. Exposure clusters, shared baths and
    interference neighborhoods are not fields of this claim.
    """

    query_id: NonBlankStr
    unit_type: NonBlankStr
    assignment_event_id: NonBlankStr
    factor_id: NonBlankStr
    value: AssignmentAnchoredValue

    @field_validator("assignment_event_id")
    @classmethod
    def _assignment_event_required(cls, value: NonBlankStr) -> NonBlankStr:
        if not value.strip():
            raise ValueError("ExperimentalUnitClaim requires assignment_event_id")
        return value

    @model_validator(mode="after")
    def _value_matches_state(self) -> Self:
        value = self.value
        if (
            isinstance(value, KnowledgeValue)
            and value.query_scope_id is not None
            and value.query_scope_id != self.query_id
        ):
            raise ValueError("value.query_scope_id must match query_id")
        return self


__all__ = [
    "AssignmentAnchoredValue",
    "ContrastSupportClaim",
    "ContrastSupportStatus",
    "ExperimentalUnitClaim",
    "ExposurePartitionClaim",
]
