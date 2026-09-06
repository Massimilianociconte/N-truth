"""PRD v9 §11.2: design matrix, aliasing e variazione intra-blocco."""

from __future__ import annotations

import pytest

from ntruth.scientific.design_matrix import evaluate_design_matrix


def _assignments(treatment: dict[str, str], batch: dict[str, str] | None = None):
    units: dict[str, dict[str, str]] = {}
    for unit_id, level in treatment.items():
        entry = {"treatment": level}
        if batch is not None:
            entry["batch"] = batch[unit_id]
        units[unit_id] = entry
    return units


DECLARED = {
    "treatment": ("control", "drug"),
    "batch": ("b1", "b2"),
}


def test_perfect_confounding_is_structural_aliasing() -> None:
    # Tutti i controlli nel batch b1, tutti i trattati nel b2: alias perfetto.
    units = _assignments(
        {"u1": "control", "u2": "control", "u3": "drug", "u4": "drug"},
        {"u1": "b1", "u2": "b1", "u3": "b2", "u4": "b2"},
    )
    check = evaluate_design_matrix(
        assignments=units,
        declared_levels=DECLARED,
        blocks={unit_id: f"cage-{index % 2}" for index, unit_id in enumerate(sorted(units))},
    )
    assert check.fully_aliased
    assert ("batch", "treatment") in check.aliased_factor_pairs
    inputs = check.gate_inputs_for_factor("treatment")
    assert inputs["fully_aliased"] is True
    assert inputs["levels_present"] is True


def test_crossover_assignment_is_not_aliased() -> None:
    units = _assignments(
        {"u1": "control", "u2": "drug", "u3": "control", "u4": "drug"},
        {"u1": "b1", "u2": "b1", "u3": "b2", "u4": "b2"},
    )
    check = evaluate_design_matrix(assignments=units, declared_levels=DECLARED)
    assert not check.fully_aliased
    assert check.aliased_factor_pairs == ()


def test_declared_level_without_units_is_detected() -> None:
    units = _assignments({"u1": "control", "u2": "control"})
    check = evaluate_design_matrix(
        assignments=units,
        declared_levels={"treatment": ("control", "drug")},
    )
    assert ("treatment", "drug") in check.levels_without_units
    assert check.gate_inputs_for_factor("treatment")["levels_present"] is False


def test_within_block_variation_requires_mixed_levels_in_a_block() -> None:
    mixed = _assignments(
        {"u1": "control", "u2": "drug", "u3": "control", "u4": "drug"},
    )
    blocks = {"u1": "week-1", "u2": "week-1", "u3": "week-2", "u4": "week-2"}
    check = evaluate_design_matrix(
        assignments=mixed, declared_levels={"treatment": ("control", "drug")}, blocks=blocks
    )
    assert check.within_block_variation["treatment"] is True
    assert check.blocks_count == 2
    assert check.smallest_block_size == 2

    homogeneous_blocks = {"u1": "week-1", "u2": "week-1", "u3": "week-2", "u4": "week-2"}
    homogeneous = _assignments(
        {"u1": "control", "u2": "control", "u3": "drug", "u4": "drug"},
    )
    check = evaluate_design_matrix(
        assignments=homogeneous,
        declared_levels={"treatment": ("control", "drug")},
        blocks=homogeneous_blocks,
    )
    assert check.within_block_variation["treatment"] is False


def test_without_blocks_variation_is_not_assessable() -> None:
    units = _assignments({"u1": "control", "u2": "drug"})
    check = evaluate_design_matrix(
        assignments=units, declared_levels={"treatment": ("control", "drug")}
    )
    assert check.within_block_variation["treatment"] is None
    assert check.blocks_count is None
    # Il gate consuma False: non valutabile non puo sostenere un claim positivo.
    assert check.gate_inputs_for_factor("treatment")["within_block_variation"] is False


def test_undeclared_factors_and_levels_fail_closed() -> None:
    units = _assignments({"u1": "control"})
    with pytest.raises(ValueError, match="not declared in the design matrix"):
        evaluate_design_matrix(
            assignments={"u1": {"dose": "low"}},
            declared_levels={"treatment": ("control", "drug")},
        )
    with pytest.raises(ValueError, match="undeclared level"):
        evaluate_design_matrix(
            assignments={"u1": {"treatment": "high"}},
            declared_levels={"treatment": ("control", "drug")},
        )
    with pytest.raises(ValueError, match="must not be empty"):
        evaluate_design_matrix(assignments={}, declared_levels=DECLARED)
    with pytest.raises(ValueError, match="without a block assignment"):
        evaluate_design_matrix(
            assignments=units,
            declared_levels={"treatment": ("control", "drug")},
            blocks={"u2": "b1"},
        )
