"""PRD v9 multidimensional SupportProfile.

This is a writer increment, not the v8 binding kernel. ``SupportGrade`` in
``ntruth.schemas.support`` stays the read-only v8 compatibility object. This
module does not map axes onto SupportGrade tokens (SRR-V8-001).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import ConfigDict

from ntruth.schemas.core import FrozenModel

SUPPORT_PROFILE_DIMENSIONS: Final[tuple[str, ...]] = (
    "directness",
    "execution_proximity",
    "corroboration",
    "authority",
    "independence_of_sources",
    "conflict",
)

_GRADE_OR_LABEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "SupportGrade",
        "derived_display_label",
        "support_display_label",
        "support_grade",
        "ux_label",
    }
)
_OUTCOME_KEYS: Final[frozenset[str]] = frozenset(
    {
        "adequacy",
        "adequacy_assessment",
        "design_adequacy",
        "determinability",
        "determinability_state",
        "determines_determinability",
        "is_adequate",
    }
)
_TOTAL_AUTHORITY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "is_total_authority",
        "total_authority",
    }
)
_OUTCOME_VALUES: Final[frozenset[str]] = frozenset(
    {
        "ADEQUATE",
        "CONDITIONALLY_DETERMINATE",
        "DETERMINATE",
        "INADEQUATE",
    }
)
_METADATA_KEYS: Final[frozenset[str]] = frozenset({"schema_version"})


class Directness(StrEnum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    UNKNOWN = "UNKNOWN"


class ExecutionProximity(StrEnum):
    EXECUTED_RECORD = "EXECUTED_RECORD"
    PLANNED_ONLY = "PLANNED_ONLY"
    RETROSPECTIVE_ASSERTION = "RETROSPECTIVE_ASSERTION"
    UNKNOWN = "UNKNOWN"


class Corroboration(StrEnum):
    INDEPENDENT_MULTI_SOURCE = "INDEPENDENT_MULTI_SOURCE"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class SupportAuthority(StrEnum):
    ADJUDICATOR = "ADJUDICATOR"
    DOMAIN_EXPERT = "DOMAIN_EXPERT"
    USER = "USER"
    AUTHOR = "AUTHOR"
    MODEL = "MODEL"
    SYSTEM = "SYSTEM"
    UNKNOWN = "UNKNOWN"


class IndependenceOfSources(StrEnum):
    INDEPENDENT = "INDEPENDENT"
    SAME_ACTOR = "SAME_ACTOR"
    UNKNOWN = "UNKNOWN"


class SupportConflict(StrEnum):
    NONE = "NONE"
    RETAINED_UNRESOLVED = "RETAINED_UNRESOLVED"
    UNKNOWN = "UNKNOWN"


class SupportProfile(FrozenModel):
    """Six required axes. ``ux_label`` is optional display only."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        use_enum_values=False,
    )

    directness: Directness
    execution_proximity: ExecutionProximity
    corroboration: Corroboration
    authority: SupportAuthority
    independence_of_sources: IndependenceOfSources
    conflict: SupportConflict
    ux_label: str | None = None

    def scientific_axes(self) -> tuple[StrEnum, ...]:
        return (
            self.directness,
            self.execution_proximity,
            self.corroboration,
            self.authority,
            self.independence_of_sources,
            self.conflict,
        )

    def determines_determinability(self) -> bool:
        return False

    def is_total_authority(self) -> bool:
        return False


def support_profile_from_parts(
    *,
    directness: Directness,
    execution_proximity: ExecutionProximity,
    corroboration: Corroboration,
    authority: SupportAuthority,
    independence_of_sources: IndependenceOfSources,
    conflict: SupportConflict,
    ux_label: str | None = None,
) -> SupportProfile:
    """Construct a profile from explicit axes. No SupportGrade mapping is applied."""

    return SupportProfile(
        directness=directness,
        execution_proximity=execution_proximity,
        corroboration=corroboration,
        authority=authority,
        independence_of_sources=independence_of_sources,
        conflict=conflict,
        ux_label=ux_label,
    )


def determines_determinability(profile: SupportProfile) -> bool:
    if not isinstance(profile, SupportProfile):
        raise TypeError("determines_determinability requires a SupportProfile")
    return False


def is_total_authority(profile: SupportProfile) -> bool:
    if not isinstance(profile, SupportProfile):
        raise TypeError("is_total_authority requires a SupportProfile")
    return False


def legacy_support_grade_is_read_only(profile: SupportProfile) -> bool:
    if not isinstance(profile, SupportProfile):
        raise TypeError("legacy SupportGrade read-only applies to SupportProfile")
    return True


def profiles_with_same_legacy_label_may_differ(a: SupportProfile, b: SupportProfile) -> bool:
    """Same ``ux_label`` does not imply the same evidence vector."""

    if not isinstance(a, SupportProfile) or not isinstance(b, SupportProfile):
        raise TypeError("both arguments must be SupportProfile")
    return a.scientific_axes() != b.scientific_axes()


def reject_support_grade_as_total_authority(payload: dict[str, object]) -> None:
    """Reject determinability or adequacy set from SupportGrade or ux_label alone."""

    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    keys = _collect_keys(payload)
    uses_grade_or_label = bool(keys & _GRADE_OR_LABEL_KEYS)
    has_dimensions = _has_all_dimensions(payload)
    sets_outcome = bool(keys & _OUTCOME_KEYS) or _contains_outcome_value(payload)
    claims_total = bool(keys & _TOTAL_AUTHORITY_KEYS) or any(
        payload.get(key) is True for key in _TOTAL_AUTHORITY_KEYS
    )
    grade_only = uses_grade_or_label and not has_dimensions
    only_grade_keys = bool(keys) and keys <= (_GRADE_OR_LABEL_KEYS | _METADATA_KEYS)
    if grade_only and (sets_outcome or claims_total or only_grade_keys):
        raise ValueError(
            "SupportGrade and ux_label cannot set determinability or adequacy "
            "and are not total authority (SRR-V8-001)"
        )


def _has_all_dimensions(payload: dict[str, object]) -> bool:
    carriers: list[dict[str, object]] = [payload]
    for key in ("profile", "support", "support_profile"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            carriers.append(nested)
    return any(
        all(dimension in carrier for dimension in SUPPORT_PROFILE_DIMENSIONS)
        for carrier in carriers
    )


def _collect_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                keys.add(key)
            keys.update(_collect_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(_collect_keys(item))
    return keys


def _contains_outcome_value(value: object) -> bool:
    if isinstance(value, str):
        return value in _OUTCOME_VALUES
    if isinstance(value, dict):
        return any(_contains_outcome_value(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_outcome_value(item) for item in value)
    return False


__all__ = [
    "SUPPORT_PROFILE_DIMENSIONS",
    "Corroboration",
    "Directness",
    "ExecutionProximity",
    "IndependenceOfSources",
    "SupportAuthority",
    "SupportConflict",
    "SupportProfile",
    "determines_determinability",
    "is_total_authority",
    "legacy_support_grade_is_read_only",
    "profiles_with_same_legacy_label_may_differ",
    "reject_support_grade_as_total_authority",
    "support_profile_from_parts",
]
