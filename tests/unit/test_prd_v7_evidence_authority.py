"""Evidence support levels: authority boundaries (PRD v7 §9.5)."""

from __future__ import annotations

from ntruth.schemas.core import EvidenceType
from ntruth.schemas.evidence_levels import (
    NON_CONCLUSIVE_LEVELS,
    EvidenceSupportLevel,
    default_level_for_type,
    statistical_code_closes_determinability,
    statistical_code_level,
)


def test_statistical_code_is_not_direct_and_does_not_close() -> None:
    level = default_level_for_type(EvidenceType.STATISTICAL_CODE)
    assert level is EvidenceSupportLevel.STRUCTURED_DIRECT
    assert level is not EvidenceSupportLevel.DIRECT
    assert statistical_code_level() is EvidenceSupportLevel.STRUCTURED_DIRECT
    assert statistical_code_closes_determinability() is False
    assert statistical_code_level() in NON_CONCLUSIVE_LEVELS


def test_derived_fact_not_source_evidence() -> None:
    assert (
        default_level_for_type(EvidenceType.DERIVED_FACT) is EvidenceSupportLevel.INFERRED_CANDIDATE
    )


def test_user_confirmation_type_alone_not_confirmed() -> None:
    level = default_level_for_type(EvidenceType.USER_CONFIRMATION)
    assert level is EvidenceSupportLevel.INFERRED_CANDIDATE
    assert level is not EvidenceSupportLevel.CONFIRMED
