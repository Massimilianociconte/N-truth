"""Combined PRD v9 fail-closed gate: role, assignment, contrast support.

This sidecar does not replace the v8 derivation runtime. It is the writer-facing
check that an Experimental Unit claim may be emitted under v9.
"""

from __future__ import annotations

from dataclasses import dataclass

from ntruth.schemas.contrast_support import ContrastSupportStatus, ExperimentalUnitClaim
from ntruth.schemas.factor_role import (
    ContrastType,
    FactorRole,
    eu_claim_permitted,
    require_eu_eligibility,
)
from ntruth.scientific.assignment_anchor import (
    apply_interference_to_claims,
    evaluate_contrast_support,
    reject_eu_from_exposure_only,
)


@dataclass(frozen=True, slots=True)
class V9ClaimGateDecision:
    """Deterministic EU/contrast decision; never a scientific validation."""

    eu_emitted: bool
    eu_claim: ExperimentalUnitClaim | None
    contrast_status: ContrastSupportStatus
    denial_reason: str | None


def gate_experimental_unit_claim(
    *,
    query_id: str,
    factor_id: str,
    unit_type: str,
    role: FactorRole,
    contrast_type: ContrastType,
    assignment_event_id: str | None,
    levels_present: bool,
    within_block_variation: bool,
    fully_aliased: bool,
    exposure_separable: bool | None,
    information_sufficient: bool,
    shared_exposure: bool = False,
    exposure_collapses_separability: bool = False,
    exposure_cluster: str | None = None,
) -> V9ClaimGateDecision:
    """Permit an assignment-anchored EU only when role, type and assignment hold.

    Interference may downgrade ContrastSupport; it never changes EU identity.
    """

    if not eu_claim_permitted(role, contrast_type):
        try:
            require_eu_eligibility(role, contrast_type)
        except ValueError as exc:
            return V9ClaimGateDecision(
                eu_emitted=False,
                eu_claim=None,
                contrast_status=ContrastSupportStatus.OUT_OF_SCOPE,
                denial_reason=str(exc),
            )
    try:
        reject_eu_from_exposure_only(assignment_event_id, exposure_cluster)
    except ValueError as exc:
        return V9ClaimGateDecision(
            eu_emitted=False,
            eu_claim=None,
            contrast_status=ContrastSupportStatus.INSUFFICIENT_INFORMATION,
            denial_reason=str(exc),
        )
    assert assignment_event_id is not None
    eu = ExperimentalUnitClaim(
        query_id=query_id,
        factor_id=factor_id,
        unit_type=unit_type,
        assignment_event_id=assignment_event_id,
        value=unit_type,
    )
    status = evaluate_contrast_support(
        levels_present=levels_present,
        within_block_variation=within_block_variation,
        fully_aliased=fully_aliased,
        exposure_separable=exposure_separable,
        information_sufficient=information_sufficient,
    )
    eu_after, interference_status = apply_interference_to_claims(
        eu_claim=eu,
        shared_exposure=shared_exposure,
        exposure_collapses_separability=exposure_collapses_separability,
    )
    return V9ClaimGateDecision(
        eu_emitted=True,
        eu_claim=eu_after,
        contrast_status=_stricter_contrast_status(status, interference_status),
        denial_reason=None,
    )


_CONTRAST_SEVERITY: dict[ContrastSupportStatus, int] = {
    ContrastSupportStatus.INSUFFICIENT_INFORMATION: 70,
    ContrastSupportStatus.OUT_OF_SCOPE: 60,
    ContrastSupportStatus.STRUCTURALLY_ALIASED: 50,
    ContrastSupportStatus.NO_LEVEL_VARIATION: 40,
    ContrastSupportStatus.EXPOSURE_MAPPING_INADEQUATE: 30,
    ContrastSupportStatus.PARTIALLY_SUPPORTED: 20,
    ContrastSupportStatus.NOT_APPLICABLE: 15,
    ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN: 10,
}


def _stricter_contrast_status(
    first: ContrastSupportStatus,
    second: ContrastSupportStatus,
) -> ContrastSupportStatus:
    """Keep the more restrictive of two independently derived statuses."""

    if _CONTRAST_SEVERITY[second] > _CONTRAST_SEVERITY[first]:
        return second
    return first
