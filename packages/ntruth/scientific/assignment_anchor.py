"""Assignment-anchored EU identity and contrast-support evaluation (PRD v9 B02/M06)."""

from __future__ import annotations

from ntruth.schemas.contrast_support import ContrastSupportStatus, ExperimentalUnitClaim


def evaluate_contrast_support(
    *,
    levels_present: bool,
    within_block_variation: bool,
    fully_aliased: bool,
    exposure_separable: bool | None,
    information_sufficient: bool,
) -> ContrastSupportStatus:
    """Map recorded design facts to ContrastSupportStatus. Deterministic; no ML."""

    if not information_sufficient:
        return ContrastSupportStatus.INSUFFICIENT_INFORMATION
    if fully_aliased:
        return ContrastSupportStatus.STRUCTURALLY_ALIASED
    if not levels_present:
        return ContrastSupportStatus.NO_LEVEL_VARIATION
    if exposure_separable is False:
        return ContrastSupportStatus.EXPOSURE_MAPPING_INADEQUATE
    if not within_block_variation or exposure_separable is None:
        return ContrastSupportStatus.PARTIALLY_SUPPORTED
    return ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN


def apply_interference_to_claims(
    *,
    eu_claim: ExperimentalUnitClaim,
    shared_exposure: bool,
    exposure_collapses_separability: bool,
) -> tuple[ExperimentalUnitClaim, ContrastSupportStatus]:
    """Keep EU assignment identity; emit contrast-support consequences only."""

    if exposure_collapses_separability:
        exposure_separable: bool | None = False
    elif shared_exposure:
        exposure_separable = None
    else:
        exposure_separable = True
    status = evaluate_contrast_support(
        levels_present=True,
        within_block_variation=True,
        fully_aliased=False,
        exposure_separable=exposure_separable,
        information_sufficient=True,
    )
    return eu_claim, status


def reject_eu_from_exposure_only(
    assignment_event_id: str | None,
    exposure_cluster: str | None,
) -> None:
    """Forbid minting an experimental unit from an exposure cluster alone."""

    assignment = (assignment_event_id or "").strip()
    cluster = (exposure_cluster or "").strip()
    if assignment:
        return
    if cluster:
        raise ValueError(
            "cannot mint ExperimentalUnitClaim from an exposure cluster without assignment_event_id"
        )
    raise ValueError("ExperimentalUnitClaim requires assignment_event_id")


__all__ = [
    "apply_interference_to_claims",
    "evaluate_contrast_support",
    "reject_eu_from_exposure_only",
]
