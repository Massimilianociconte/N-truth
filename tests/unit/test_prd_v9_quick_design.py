"""PRD v9 Quick Design: FactorRole and ContrastType before levels, n, or sheet."""

from __future__ import annotations

import json

import pytest

from ntruth.quick_design.v9 import (
    STEPS,
    ContrastType,
    FactorRole,
    advance,
    can_emit_experimental_unit,
    primary_question,
    start_session,
    statistical_handoff,
)


def test_steps_are_role_and_type_before_levels_assignment_sheet_or_n() -> None:
    assert STEPS == (
        "factor_role",
        "contrast_type",
        "source_preparation",
        "assignment",
        "levels_endpoint",
        "lineage_exposure",
        "sample_sheet",
        "safe_methods",
        "handoff",
    )
    assert STEPS.index("factor_role") < STEPS.index("levels_endpoint")
    assert STEPS.index("contrast_type") < STEPS.index("assignment")
    assert STEPS.index("contrast_type") < STEPS.index("sample_sheet")


def test_start_session_emits_no_n() -> None:
    state = start_session()
    assert state.step == "factor_role"
    assert state.n is None
    assert state.factor_role is FactorRole.UNKNOWN
    assert state.contrast_type is ContrastType.UNKNOWN
    assert state.factor_role_classified is False
    assert state.assignment_recorded is False
    assert can_emit_experimental_unit(state) is False
    with pytest.raises(ValueError, match="does not emit n"):
        advance(state, n=6)
    with pytest.raises(ValueError, match="does not emit"):
        advance(state, experimental_unit_count=6)


def test_primary_question_when_role_unknown_is_about_role_not_n() -> None:
    question = primary_question(start_session())
    lowered = question.lower()
    assert "role" in lowered
    assert "n=" not in lowered
    assert "sample size" not in lowered
    assert "how many" not in lowered
    assert "experimental_unit_count" not in lowered
    assert "planned_n" not in lowered


def test_cannot_advance_to_sample_sheet_without_role_and_type() -> None:
    state = start_session()
    with pytest.raises(ValueError, match="sample_sheet"):
        advance(state, step="sample_sheet")
    with pytest.raises(ValueError, match="sample_sheet"):
        advance(state, sample_sheet="sample_id,factor_level\nS1,vehicle\n")
    with pytest.raises(ValueError, match="FactorRole and ContrastType"):
        advance(state, assignment={"unit": "well"})
    with pytest.raises(ValueError, match="FactorRole and ContrastType"):
        advance(state, levels_endpoint={"levels": ("vehicle", "drug"), "endpoint": "viability"})
    classified_role = advance(state, factor_role=FactorRole.ASSIGNED_INTERVENTION)
    with pytest.raises(ValueError, match="sample_sheet"):
        advance(classified_role, step="sample_sheet")


def test_intrinsic_genotype_never_can_emit_experimental_unit() -> None:
    state = start_session()
    state = advance(state, factor_role=FactorRole.INTRINSIC_ATTRIBUTE, factor_name="genotype")
    state = advance(state, contrast_type=ContrastType.INTRINSIC_ATTRIBUTE_COMPARISON)
    state = advance(state, assignment={"unit": "animal", "mechanism": "not_assigned"})
    assert state.factor_role is FactorRole.INTRINSIC_ATTRIBUTE
    assert state.assignment_recorded is True
    assert can_emit_experimental_unit(state) is False
    handoff = statistical_handoff(state)
    assert handoff["can_emit_experimental_unit"] is False


def test_assigned_intervention_with_assignment_recorded_can_emit_experimental_unit() -> None:
    state = start_session()
    state = advance(state, factor_role=FactorRole.ASSIGNED_INTERVENTION)
    state = advance(state, contrast_type=ContrastType.ASSIGNED_INTERVENTION_EFFECT)
    assert can_emit_experimental_unit(state) is False
    state = advance(state, assignment={"unit": "well", "mechanism": "random"})
    assert state.assignment_recorded is True
    assert can_emit_experimental_unit(state) is True
    assert state.n is None


def test_handoff_is_handoff_only() -> None:
    empty = statistical_handoff(start_session())
    assigned = start_session()
    assigned = advance(assigned, factor_role=FactorRole.ASSIGNED_INTERVENTION)
    assigned = advance(assigned, contrast_type=ContrastType.ASSIGNED_INTERVENTION_EFFECT)
    assigned = advance(assigned, assignment_recorded=True)
    ready = statistical_handoff(assigned)
    for payload in (empty, ready):
        assert payload["strategy_module_status"] == "HANDOFF_ONLY"
        assert "test_recommendation" not in payload
        assert "recommended_test" not in payload
        assert "recommended_model" not in payload
        text = json.dumps(payload).lower()
        assert "t-test" not in text
        assert "anova" not in text
        assert "welch" not in text
        assert "lmm" not in text
