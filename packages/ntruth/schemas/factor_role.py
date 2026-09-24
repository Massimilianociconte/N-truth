"""PRD v9 FactorRole / ContrastType eligibility gate.

Core may emit Experimental Unit claims only when an assigned intervention is
paired with an assigned-intervention effect. UNKNOWN, intrinsic, time, batch
and other non-assigned roles deny EU and route to comparison, source or
trajectory claim families.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.kernel import NonBlankStr

CLAIM_FAMILY_EXPERIMENTAL_UNIT = "experimental_unit"
CLAIM_FAMILY_COMPARISON = "comparison"
CLAIM_FAMILY_SOURCE = "source"
CLAIM_FAMILY_TRAJECTORY = "trajectory"
CLAIM_FAMILY_DESCRIPTIVE = "descriptive"
CLAIM_FAMILY_DIAGNOSTIC = "diagnostic"
CLAIM_FAMILY_CONTRAST_SUPPORT = "contrast_support"
CLAIM_FAMILY_ROUTING = "routing"

EU_ELIGIBLE_ROLE = "ASSIGNED_INTERVENTION"
EU_ELIGIBLE_CONTRAST = "ASSIGNED_INTERVENTION_EFFECT"


class FactorRole(StrEnum):
    """Canonical factor role; independent of the factor display name."""

    ASSIGNED_INTERVENTION = "ASSIGNED_INTERVENTION"
    OBSERVATIONAL_EXPOSURE = "OBSERVATIONAL_EXPOSURE"
    INTRINSIC_ATTRIBUTE = "INTRINSIC_ATTRIBUTE"
    BLOCKING_FACTOR = "BLOCKING_FACTOR"
    BATCH_NUISANCE = "BATCH_NUISANCE"
    REPEATED_MEASURE_INDEX = "REPEATED_MEASURE_INDEX"
    MEASUREMENT_CONDITION = "MEASUREMENT_CONDITION"
    UNKNOWN = "UNKNOWN"


class ContrastType(StrEnum):
    """Canonical contrast / question type for a query-scoped claim family."""

    ASSIGNED_INTERVENTION_EFFECT = "ASSIGNED_INTERVENTION_EFFECT"
    OBSERVATIONAL_ASSOCIATION = "OBSERVATIONAL_ASSOCIATION"
    INTRINSIC_ATTRIBUTE_COMPARISON = "INTRINSIC_ATTRIBUTE_COMPARISON"
    WITHIN_UNIT_REPEATED_CONTRAST = "WITHIN_UNIT_REPEATED_CONTRAST"
    NUISANCE_OR_BATCH_COMPARISON = "NUISANCE_OR_BATCH_COMPARISON"
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    UNKNOWN = "UNKNOWN"


_COMPATIBLE_PAIRS: frozenset[tuple[FactorRole, ContrastType]] = frozenset(
    {
        (FactorRole.ASSIGNED_INTERVENTION, ContrastType.ASSIGNED_INTERVENTION_EFFECT),
        (FactorRole.ASSIGNED_INTERVENTION, ContrastType.DESCRIPTIVE_ONLY),
        (FactorRole.OBSERVATIONAL_EXPOSURE, ContrastType.OBSERVATIONAL_ASSOCIATION),
        (FactorRole.OBSERVATIONAL_EXPOSURE, ContrastType.DESCRIPTIVE_ONLY),
        (FactorRole.INTRINSIC_ATTRIBUTE, ContrastType.INTRINSIC_ATTRIBUTE_COMPARISON),
        (FactorRole.INTRINSIC_ATTRIBUTE, ContrastType.DESCRIPTIVE_ONLY),
        (FactorRole.BLOCKING_FACTOR, ContrastType.NUISANCE_OR_BATCH_COMPARISON),
        (FactorRole.BLOCKING_FACTOR, ContrastType.DESCRIPTIVE_ONLY),
        (FactorRole.BATCH_NUISANCE, ContrastType.NUISANCE_OR_BATCH_COMPARISON),
        (FactorRole.BATCH_NUISANCE, ContrastType.DESCRIPTIVE_ONLY),
        (FactorRole.REPEATED_MEASURE_INDEX, ContrastType.WITHIN_UNIT_REPEATED_CONTRAST),
        (FactorRole.REPEATED_MEASURE_INDEX, ContrastType.DESCRIPTIVE_ONLY),
        (FactorRole.MEASUREMENT_CONDITION, ContrastType.DESCRIPTIVE_ONLY),
        (FactorRole.MEASUREMENT_CONDITION, ContrastType.NUISANCE_OR_BATCH_COMPARISON),
    }
)

_ROLE_CLAIM_FAMILIES: dict[FactorRole, frozenset[str]] = {
    FactorRole.ASSIGNED_INTERVENTION: frozenset(
        {CLAIM_FAMILY_EXPERIMENTAL_UNIT, CLAIM_FAMILY_CONTRAST_SUPPORT}
    ),
    FactorRole.OBSERVATIONAL_EXPOSURE: frozenset(
        {
            CLAIM_FAMILY_COMPARISON,
            CLAIM_FAMILY_SOURCE,
            CLAIM_FAMILY_CONTRAST_SUPPORT,
            CLAIM_FAMILY_DIAGNOSTIC,
        }
    ),
    FactorRole.INTRINSIC_ATTRIBUTE: frozenset(
        {CLAIM_FAMILY_COMPARISON, CLAIM_FAMILY_SOURCE, CLAIM_FAMILY_CONTRAST_SUPPORT}
    ),
    FactorRole.BLOCKING_FACTOR: frozenset({CLAIM_FAMILY_COMPARISON, CLAIM_FAMILY_DIAGNOSTIC}),
    FactorRole.BATCH_NUISANCE: frozenset(
        {CLAIM_FAMILY_COMPARISON, CLAIM_FAMILY_SOURCE, CLAIM_FAMILY_DIAGNOSTIC}
    ),
    FactorRole.REPEATED_MEASURE_INDEX: frozenset(
        {CLAIM_FAMILY_TRAJECTORY, CLAIM_FAMILY_COMPARISON, CLAIM_FAMILY_CONTRAST_SUPPORT}
    ),
    FactorRole.MEASUREMENT_CONDITION: frozenset({CLAIM_FAMILY_COMPARISON, CLAIM_FAMILY_DIAGNOSTIC}),
    FactorRole.UNKNOWN: frozenset({CLAIM_FAMILY_ROUTING}),
}

_CONTRAST_CLAIM_FAMILIES: dict[ContrastType, frozenset[str]] = {
    ContrastType.ASSIGNED_INTERVENTION_EFFECT: frozenset(
        {CLAIM_FAMILY_EXPERIMENTAL_UNIT, CLAIM_FAMILY_CONTRAST_SUPPORT}
    ),
    ContrastType.OBSERVATIONAL_ASSOCIATION: frozenset(
        {CLAIM_FAMILY_COMPARISON, CLAIM_FAMILY_SOURCE, CLAIM_FAMILY_DIAGNOSTIC}
    ),
    ContrastType.INTRINSIC_ATTRIBUTE_COMPARISON: frozenset(
        {CLAIM_FAMILY_COMPARISON, CLAIM_FAMILY_SOURCE}
    ),
    ContrastType.WITHIN_UNIT_REPEATED_CONTRAST: frozenset(
        {CLAIM_FAMILY_TRAJECTORY, CLAIM_FAMILY_COMPARISON}
    ),
    ContrastType.NUISANCE_OR_BATCH_COMPARISON: frozenset(
        {CLAIM_FAMILY_COMPARISON, CLAIM_FAMILY_DIAGNOSTIC}
    ),
    ContrastType.DESCRIPTIVE_ONLY: frozenset({CLAIM_FAMILY_DESCRIPTIVE}),
    ContrastType.UNKNOWN: frozenset({CLAIM_FAMILY_ROUTING}),
}


def _coerce_role(role: FactorRole | str) -> FactorRole:
    if isinstance(role, FactorRole):
        return role
    try:
        return FactorRole(role)
    except ValueError as error:
        raise ValueError(f"unknown FactorRole token: {role!r}") from error


def _coerce_contrast_type(contrast_type: ContrastType | str) -> ContrastType:
    if isinstance(contrast_type, ContrastType):
        return contrast_type
    try:
        return ContrastType(contrast_type)
    except ValueError as error:
        raise ValueError(f"unknown ContrastType token: {contrast_type!r}") from error


def pair_compatible(
    role: FactorRole | str,
    contrast_type: ContrastType | str,
) -> bool:
    """Return whether the role/type pair is a coherent v9 pairing."""

    return (
        _coerce_role(role),
        _coerce_contrast_type(contrast_type),
    ) in _COMPATIBLE_PAIRS


def eu_claim_permitted(
    role: FactorRole | str,
    contrast_type: ContrastType | str,
) -> bool:
    """Return whether Core may emit an Experimental Unit claim for this pair."""

    resolved_role = _coerce_role(role)
    resolved_contrast = _coerce_contrast_type(contrast_type)
    return (
        resolved_role is FactorRole.ASSIGNED_INTERVENTION
        and resolved_contrast is ContrastType.ASSIGNED_INTERVENTION_EFFECT
    )


def permitted_claim_families(
    role: FactorRole | str,
    contrast_type: ContrastType | str,
) -> frozenset[str]:
    """Return the claim families Core may emit for this role/type pair."""

    resolved_role = _coerce_role(role)
    resolved_contrast = _coerce_contrast_type(contrast_type)
    if resolved_role is FactorRole.UNKNOWN or resolved_contrast is ContrastType.UNKNOWN:
        return frozenset({CLAIM_FAMILY_ROUTING})
    if not pair_compatible(resolved_role, resolved_contrast):
        return frozenset()

    families = set(_ROLE_CLAIM_FAMILIES[resolved_role]) | set(
        _CONTRAST_CLAIM_FAMILIES[resolved_contrast]
    )
    if not eu_claim_permitted(resolved_role, resolved_contrast):
        families.discard(CLAIM_FAMILY_EXPERIMENTAL_UNIT)
    return frozenset(families)


def require_eu_eligibility(
    role: FactorRole | str,
    contrast_type: ContrastType | str,
) -> None:
    """Raise when Core is not allowed to emit an Experimental Unit claim."""

    resolved_role = _coerce_role(role)
    resolved_contrast = _coerce_contrast_type(contrast_type)
    if eu_claim_permitted(resolved_role, resolved_contrast):
        return
    raise ValueError(
        "Il Core può emettere ExperimentalUnitClaim solo quando "
        f"FactorRole={EU_ELIGIBLE_ROLE} e ContrastType={EU_ELIGIBLE_CONTRAST}; "
        f"ricevuto {resolved_role.value}/{resolved_contrast.value}."
    )


class FactorContrastClassification(FrozenModel):
    """Query-scoped FactorRole and ContrastType with fail-closed rationale."""

    role: FactorRole
    contrast_type: ContrastType
    rationale: NonBlankStr | None = None

    @model_validator(mode="after")
    def _rationale_when_unknown_or_incompatible(self) -> Self:
        unknown = self.role is FactorRole.UNKNOWN or self.contrast_type is ContrastType.UNKNOWN
        compatible = pair_compatible(self.role, self.contrast_type)
        if (unknown or not compatible) and self.rationale is None:
            raise ValueError(
                "rationale is required when FactorRole or ContrastType is UNKNOWN "
                "or the role/contrast pair is not compatible"
            )
        return self


__all__ = [
    "CLAIM_FAMILY_COMPARISON",
    "CLAIM_FAMILY_CONTRAST_SUPPORT",
    "CLAIM_FAMILY_DESCRIPTIVE",
    "CLAIM_FAMILY_DIAGNOSTIC",
    "CLAIM_FAMILY_EXPERIMENTAL_UNIT",
    "CLAIM_FAMILY_ROUTING",
    "CLAIM_FAMILY_SOURCE",
    "CLAIM_FAMILY_TRAJECTORY",
    "EU_ELIGIBLE_CONTRAST",
    "EU_ELIGIBLE_ROLE",
    "ContrastType",
    "FactorContrastClassification",
    "FactorRole",
    "eu_claim_permitted",
    "pair_compatible",
    "permitted_claim_families",
    "require_eu_eligibility",
]
