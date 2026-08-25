"""PRD v9 B02/M06: assignment-anchored EU and ContrastSupport contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.contrast_support import (
    ContrastSupportClaim,
    ContrastSupportStatus,
    ExperimentalUnitClaim,
    ExposurePartitionClaim,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.scientific.assignment_anchor import (
    apply_interference_to_claims,
    evaluate_contrast_support,
    reject_eu_from_exposure_only,
)


def _eu(
    *,
    unit_type: str,
    assignment_event_id: str,
    query_id: str = "IQ-001",
    factor_id: str = "treatment",
    value: str | None = None,
) -> ExperimentalUnitClaim:
    return ExperimentalUnitClaim(
        query_id=query_id,
        unit_type=unit_type,
        assignment_event_id=assignment_event_id,
        factor_id=factor_id,
        value=value or unit_type,
    )


def test_assignment_after_split_shared_bath_leaves_eu_unchanged() -> None:
    eu = _eu(unit_type="well", assignment_event_id="EVT-ASSIGN-WELL-01")

    unchanged, status = apply_interference_to_claims(
        eu_claim=eu,
        shared_exposure=True,
        exposure_collapses_separability=True,
    )

    assert unchanged is eu
    assert unchanged.assignment_event_id == "EVT-ASSIGN-WELL-01"
    assert unchanged.unit_type == "well"
    assert status is ContrastSupportStatus.EXPOSURE_MAPPING_INADEQUATE
    assert status in {
        ContrastSupportStatus.EXPOSURE_MAPPING_INADEQUATE,
        ContrastSupportStatus.PARTIALLY_SUPPORTED,
    }


def test_assignment_before_split_eu_stays_assignment_unit() -> None:
    eu = _eu(unit_type="culture", assignment_event_id="EVT-ASSIGN-CULTURE-01")

    unchanged, status = apply_interference_to_claims(
        eu_claim=eu,
        shared_exposure=False,
        exposure_collapses_separability=False,
    )

    assert unchanged.assignment_event_id == "EVT-ASSIGN-CULTURE-01"
    assert unchanged.unit_type == "culture"
    assert status is ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN


def test_treatment_equals_plate_aliasing_is_structurally_aliased() -> None:
    status = evaluate_contrast_support(
        levels_present=True,
        within_block_variation=False,
        fully_aliased=True,
        exposure_separable=True,
        information_sufficient=True,
    )
    claim = ContrastSupportClaim(
        query_id="IQ-001",
        factor_id="treatment",
        status=status,
        level_presence=True,
        within_block_variation=False,
        aliasing_factors=("plate_id",),
        proof_refs=("PRF-ALIAS-PLATE",),
    )

    assert status is ContrastSupportStatus.STRUCTURALLY_ALIASED
    assert claim.aliasing_factors == ("plate_id",)


def test_missing_level_variation_is_no_level_variation() -> None:
    status = evaluate_contrast_support(
        levels_present=False,
        within_block_variation=False,
        fully_aliased=False,
        exposure_separable=True,
        information_sufficient=True,
    )

    assert status is ContrastSupportStatus.NO_LEVEL_VARIATION


def test_cannot_construct_eu_without_assignment_event_id() -> None:
    with pytest.raises(ValidationError, match="assignment_event_id"):
        ExperimentalUnitClaim.model_validate(
            {
                "query_id": "IQ-001",
                "unit_type": "well",
                "factor_id": "treatment",
                "value": "well",
            }
        )
    with pytest.raises(ValueError, match="assignment_event_id"):
        reject_eu_from_exposure_only(None, "bath-cluster-01")
    with pytest.raises(ValueError, match="assignment_event_id"):
        reject_eu_from_exposure_only("", None)
    reject_eu_from_exposure_only("EVT-ASSIGN-WELL-01", "bath-cluster-01")


def test_eu_claim_forbids_exposure_cluster_as_identity_field() -> None:
    with pytest.raises(ValidationError):
        ExperimentalUnitClaim.model_validate(
            {
                "query_id": "IQ-001",
                "unit_type": "well",
                "assignment_event_id": "EVT-ASSIGN-WELL-01",
                "factor_id": "treatment",
                "value": "well",
                "exposure_cluster": "bath-cluster-01",
            }
        )


def test_shared_bath_records_exposure_partition_not_eu() -> None:
    eu = _eu(unit_type="well", assignment_event_id="EVT-ASSIGN-WELL-01")
    partition = ExposurePartitionClaim(
        id="XP-BATH-01",
        unit_ids=("well-01", "well-02"),
        pathway="shared_bath",
        shared_exposure=KnowledgeValue[bool](
            knowledge_state=KnowledgeState.PRESENT,
            value=True,
            evidence_ids=("EV-BATH-01",),
            query_scope_id="IQ-001",
        ),
    )
    unchanged, status = apply_interference_to_claims(
        eu_claim=eu,
        shared_exposure=True,
        exposure_collapses_separability=False,
    )

    assert partition.pathway == "shared_bath"
    assert unchanged.assignment_event_id == eu.assignment_event_id
    assert unchanged.unit_type == eu.unit_type
    assert status is ContrastSupportStatus.PARTIALLY_SUPPORTED


def test_evaluate_contrast_support_table_is_deterministic() -> None:
    assert (
        evaluate_contrast_support(
            levels_present=True,
            within_block_variation=True,
            fully_aliased=False,
            exposure_separable=True,
            information_sufficient=True,
        )
        is ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN
    )
    assert (
        evaluate_contrast_support(
            levels_present=True,
            within_block_variation=True,
            fully_aliased=False,
            exposure_separable=False,
            information_sufficient=True,
        )
        is ContrastSupportStatus.EXPOSURE_MAPPING_INADEQUATE
    )
    assert (
        evaluate_contrast_support(
            levels_present=True,
            within_block_variation=True,
            fully_aliased=False,
            exposure_separable=None,
            information_sufficient=False,
        )
        is ContrastSupportStatus.INSUFFICIENT_INFORMATION
    )
