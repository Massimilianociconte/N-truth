"""PRD v9 SupportProfile increment: axes are normative; SupportGrade is read-only."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.support_profile import (
    Corroboration,
    Directness,
    ExecutionProximity,
    IndependenceOfSources,
    SupportAuthority,
    SupportConflict,
    SupportProfile,
    determines_determinability,
    is_total_authority,
    legacy_support_grade_is_read_only,
    profiles_with_same_legacy_label_may_differ,
    reject_support_grade_as_total_authority,
    support_profile_from_parts,
)


def _profile(
    *,
    directness: Directness = Directness.DIRECT,
    execution_proximity: ExecutionProximity = ExecutionProximity.EXECUTED_RECORD,
    corroboration: Corroboration = Corroboration.INDEPENDENT_MULTI_SOURCE,
    authority: SupportAuthority = SupportAuthority.ADJUDICATOR,
    independence_of_sources: IndependenceOfSources = IndependenceOfSources.INDEPENDENT,
    conflict: SupportConflict = SupportConflict.NONE,
    ux_label: str | None = "DIRECT_SINGLE_SOURCE",
) -> SupportProfile:
    return support_profile_from_parts(
        directness=directness,
        execution_proximity=execution_proximity,
        corroboration=corroboration,
        authority=authority,
        independence_of_sources=independence_of_sources,
        conflict=conflict,
        ux_label=ux_label,
    )


def test_same_ux_label_different_evidence_profiles_differ() -> None:
    executed = _profile(
        execution_proximity=ExecutionProximity.EXECUTED_RECORD,
        corroboration=Corroboration.INDEPENDENT_MULTI_SOURCE,
        ux_label="DIRECT_SINGLE_SOURCE",
    )
    planned = _profile(
        execution_proximity=ExecutionProximity.PLANNED_ONLY,
        corroboration=Corroboration.SINGLE_SOURCE,
        authority=SupportAuthority.AUTHOR,
        independence_of_sources=IndependenceOfSources.SAME_ACTOR,
        ux_label="DIRECT_SINGLE_SOURCE",
    )
    assert executed.ux_label == planned.ux_label
    assert legacy_support_grade_is_read_only(executed) is True
    assert legacy_support_grade_is_read_only(planned) is True
    assert profiles_with_same_legacy_label_may_differ(executed, planned) is True


def test_missing_dimension_rejected_by_pydantic() -> None:
    payload = {
        "directness": Directness.DIRECT,
        "execution_proximity": ExecutionProximity.EXECUTED_RECORD,
        "authority": SupportAuthority.USER,
        "independence_of_sources": IndependenceOfSources.INDEPENDENT,
        "conflict": SupportConflict.NONE,
    }
    with pytest.raises(ValidationError) as exc_info:
        SupportProfile.model_validate(payload)
    assert "corroboration" in str(exc_info.value)


def test_ux_label_cannot_close_determinate() -> None:
    profile = _profile(ux_label="ADJUDICATED")
    assert determines_determinability(profile) is False
    assert profile.determines_determinability() is False
    assert is_total_authority(profile) is False
    assert profile.is_total_authority() is False


def test_support_grade_only_payload_rejected_as_total_authority() -> None:
    with pytest.raises(ValueError, match="not total authority"):
        reject_support_grade_as_total_authority(
            {
                "support_grade": "ADJUDICATED",
                "determinability": "DETERMINATE",
            }
        )
    with pytest.raises(ValueError, match="not total authority"):
        reject_support_grade_as_total_authority({"support_grade": "ADJUDICATED"})
    with pytest.raises(ValueError, match="not total authority"):
        reject_support_grade_as_total_authority(
            {
                "ux_label": "CORROBORATED_DIRECT",
                "adequacy": "ADEQUATE",
            }
        )
