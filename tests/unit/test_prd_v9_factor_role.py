"""PRD v9 FactorRole / ContrastType EU eligibility gate."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.factor_role import (
    CLAIM_FAMILY_COMPARISON,
    CLAIM_FAMILY_EXPERIMENTAL_UNIT,
    CLAIM_FAMILY_ROUTING,
    CLAIM_FAMILY_SOURCE,
    CLAIM_FAMILY_TRAJECTORY,
    ContrastType,
    FactorContrastClassification,
    FactorRole,
    eu_claim_permitted,
    pair_compatible,
    permitted_claim_families,
    require_eu_eligibility,
)


def test_assigned_intervention_drug_treatment_permits_eu() -> None:
    role = FactorRole.ASSIGNED_INTERVENTION
    contrast = ContrastType.ASSIGNED_INTERVENTION_EFFECT

    assert eu_claim_permitted(role, contrast) is True
    assert eu_claim_permitted("ASSIGNED_INTERVENTION", "ASSIGNED_INTERVENTION_EFFECT") is True
    families = permitted_claim_families(role, contrast)
    assert CLAIM_FAMILY_EXPERIMENTAL_UNIT in families
    require_eu_eligibility(role, contrast)
    classification = FactorContrastClassification(role=role, contrast_type=contrast)
    assert classification.role is role
    assert classification.contrast_type is contrast
    assert classification.rationale is None


def test_genotype_intrinsic_attribute_denies_eu() -> None:
    role = FactorRole.INTRINSIC_ATTRIBUTE
    contrast = ContrastType.INTRINSIC_ATTRIBUTE_COMPARISON

    assert eu_claim_permitted(role, contrast) is False
    families = permitted_claim_families(role, contrast)
    assert CLAIM_FAMILY_EXPERIMENTAL_UNIT not in families
    assert CLAIM_FAMILY_COMPARISON in families
    assert CLAIM_FAMILY_SOURCE in families
    with pytest.raises(ValueError, match="ASSIGNED_INTERVENTION"):
        require_eu_eligibility(role, contrast)


def test_time_repeated_measure_index_denies_eu() -> None:
    role = FactorRole.REPEATED_MEASURE_INDEX
    contrast = ContrastType.WITHIN_UNIT_REPEATED_CONTRAST

    assert eu_claim_permitted(role, contrast) is False
    families = permitted_claim_families(role, contrast)
    assert CLAIM_FAMILY_EXPERIMENTAL_UNIT not in families
    assert CLAIM_FAMILY_TRAJECTORY in families
    with pytest.raises(ValueError, match="ExperimentalUnitClaim"):
        require_eu_eligibility(role, contrast)


def test_batch_nuisance_denies_eu() -> None:
    role = FactorRole.BATCH_NUISANCE
    contrast = ContrastType.NUISANCE_OR_BATCH_COMPARISON

    assert eu_claim_permitted(role, contrast) is False
    families = permitted_claim_families(role, contrast)
    assert CLAIM_FAMILY_EXPERIMENTAL_UNIT not in families
    assert CLAIM_FAMILY_COMPARISON in families
    with pytest.raises(ValueError, match="BATCH_NUISANCE"):
        require_eu_eligibility(role, contrast)


@pytest.mark.parametrize(
    ("role", "contrast"),
    (
        (FactorRole.UNKNOWN, ContrastType.ASSIGNED_INTERVENTION_EFFECT),
        (FactorRole.ASSIGNED_INTERVENTION, ContrastType.UNKNOWN),
        (FactorRole.UNKNOWN, ContrastType.UNKNOWN),
    ),
)
def test_unknown_role_or_type_denies_eu(role: FactorRole, contrast: ContrastType) -> None:
    assert eu_claim_permitted(role, contrast) is False
    assert permitted_claim_families(role, contrast) == frozenset({CLAIM_FAMILY_ROUTING})
    with pytest.raises(ValueError, match="UNKNOWN"):
        require_eu_eligibility(role, contrast)


def test_require_eu_eligibility_raises_for_observational_exposure() -> None:
    with pytest.raises(ValueError, match="OBSERVATIONAL_EXPOSURE"):
        require_eu_eligibility(
            FactorRole.OBSERVATIONAL_EXPOSURE,
            ContrastType.OBSERVATIONAL_ASSOCIATION,
        )


def test_incompatible_pair_denies_eu_and_requires_rationale() -> None:
    role = FactorRole.INTRINSIC_ATTRIBUTE
    contrast = ContrastType.ASSIGNED_INTERVENTION_EFFECT

    assert pair_compatible(role, contrast) is False
    assert eu_claim_permitted(role, contrast) is False
    assert permitted_claim_families(role, contrast) == frozenset()
    with pytest.raises(ValidationError, match="rationale"):
        FactorContrastClassification(role=role, contrast_type=contrast)
    classified = FactorContrastClassification(
        role=role,
        contrast_type=contrast,
        rationale="GENOTYPE is an intrinsic attribute, not an assigned intervention.",
    )
    assert classified.rationale is not None


def test_unknown_classification_requires_rationale() -> None:
    with pytest.raises(ValidationError, match="UNKNOWN"):
        FactorContrastClassification(
            role=FactorRole.UNKNOWN,
            contrast_type=ContrastType.UNKNOWN,
        )
    classified = FactorContrastClassification(
        role=FactorRole.UNKNOWN,
        contrast_type=ContrastType.UNKNOWN,
        rationale="Methods do not state whether treatment or genotype is the query factor.",
    )
    assert classified.role is FactorRole.UNKNOWN


def test_unknown_tokens_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown FactorRole"):
        eu_claim_permitted("NOT_A_ROLE", ContrastType.ASSIGNED_INTERVENTION_EFFECT)
    with pytest.raises(ValueError, match="unknown ContrastType"):
        permitted_claim_families(FactorRole.ASSIGNED_INTERVENTION, "NOT_A_TYPE")
