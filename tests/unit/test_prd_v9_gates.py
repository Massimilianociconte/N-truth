"""Integrated PRD v9 EU gate: role + assignment + contrast support."""

from __future__ import annotations

from ntruth.schemas.contrast_support import ContrastSupportStatus
from ntruth.schemas.factor_role import ContrastType, FactorRole
from ntruth.schemas.material_lineage import MaterialLineageKind
from ntruth.schemas.v9_registry import ContrastSupportStatus as RegistryContrastSupport
from ntruth.scientific.v9_gates import gate_experimental_unit_claim


def test_assigned_intervention_with_assignment_emits_eu() -> None:
    decision = gate_experimental_unit_claim(
        query_id="IQ-001",
        factor_id="treatment",
        unit_type="well",
        role=FactorRole.ASSIGNED_INTERVENTION,
        contrast_type=ContrastType.ASSIGNED_INTERVENTION_EFFECT,
        assignment_event_id="EVT-ASSIGN-01",
        levels_present=True,
        within_block_variation=True,
        fully_aliased=False,
        exposure_separable=True,
        information_sufficient=True,
    )
    assert decision.eu_emitted is True
    assert decision.eu_claim is not None
    assert decision.eu_claim.assignment_event_id == "EVT-ASSIGN-01"
    assert decision.contrast_status is ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN


def test_genotype_never_emits_eu() -> None:
    decision = gate_experimental_unit_claim(
        query_id="IQ-002",
        factor_id="genotype",
        unit_type="line",
        role=FactorRole.INTRINSIC_ATTRIBUTE,
        contrast_type=ContrastType.INTRINSIC_ATTRIBUTE_COMPARISON,
        assignment_event_id="EVT-ASSIGN-01",
        levels_present=True,
        within_block_variation=True,
        fully_aliased=False,
        exposure_separable=True,
        information_sufficient=True,
    )
    assert decision.eu_emitted is False
    assert decision.eu_claim is None
    assert decision.contrast_status is ContrastSupportStatus.OUT_OF_SCOPE
    assert decision.denial_reason is not None


def test_shared_bath_does_not_rename_eu() -> None:
    decision = gate_experimental_unit_claim(
        query_id="IQ-003",
        factor_id="treatment",
        unit_type="well",
        role=FactorRole.ASSIGNED_INTERVENTION,
        contrast_type=ContrastType.ASSIGNED_INTERVENTION_EFFECT,
        assignment_event_id="EVT-ASSIGN-WELL",
        levels_present=True,
        within_block_variation=True,
        fully_aliased=False,
        exposure_separable=True,
        information_sufficient=True,
        shared_exposure=True,
        exposure_collapses_separability=True,
        exposure_cluster="BATH-01",
    )
    assert decision.eu_emitted is True
    assert decision.eu_claim is not None
    assert decision.eu_claim.unit_type == "well"
    assert decision.eu_claim.assignment_event_id == "EVT-ASSIGN-WELL"
    assert decision.contrast_status is ContrastSupportStatus.EXPOSURE_MAPPING_INADEQUATE


def test_aliasing_is_stricter_than_supported() -> None:
    decision = gate_experimental_unit_claim(
        query_id="IQ-004",
        factor_id="treatment",
        unit_type="well",
        role=FactorRole.ASSIGNED_INTERVENTION,
        contrast_type=ContrastType.ASSIGNED_INTERVENTION_EFFECT,
        assignment_event_id="EVT-ASSIGN-01",
        levels_present=True,
        within_block_variation=False,
        fully_aliased=True,
        exposure_separable=True,
        information_sufficient=True,
    )
    assert decision.eu_emitted is True
    assert decision.contrast_status is ContrastSupportStatus.STRUCTURALLY_ALIASED


def test_registry_contrast_tokens_match_claim_enum() -> None:
    assert {item.value for item in ContrastSupportStatus} == {
        item.value for item in RegistryContrastSupport
    }
    assert MaterialLineageKind.SPLIT.value == "SPLIT"
