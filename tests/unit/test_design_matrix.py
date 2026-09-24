"""PRD v9 §11.2: design matrix, aliasing e variazione intra-blocco."""

from __future__ import annotations

import pytest

from ntruth.schemas.contrast_support import ContrastSupportStatus
from ntruth.scientific.assignment_anchor import evaluate_contrast_support
from ntruth.scientific.design_matrix import DesignMatrixCheck, evaluate_design_matrix


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


# --- Audit 2026-09-12 A02/A03: controesempi preservati come regressioni. ---


def _status(check: DesignMatrixCheck, factor_id: str = "treatment") -> ContrastSupportStatus:
    return evaluate_contrast_support(
        **check.gate_inputs_for_factor(factor_id),
        exposure_separable=True,
        information_sufficient=True,
    )


def test_missing_assignment_is_not_level_variation() -> None:
    # b1 contiene solo un control registrato e un'unita senza assegnazione.
    check = evaluate_design_matrix(
        assignments={"u1": {"treatment": "control"}, "u2": {}, "u3": {"treatment": "drug"}},
        declared_levels={"treatment": ("control", "drug")},
        blocks={"u1": "b1", "u2": "b1", "u3": "b2"},
    )
    assert check.within_block_variation["treatment"] is False
    assert check.unassigned_units["treatment"] == ("u2",)
    inputs = check.gate_inputs_for_factor("treatment")
    assert inputs["assignment_complete"] is False
    assert _status(check) is ContrastSupportStatus.PARTIALLY_SUPPORTED


def test_removing_information_never_strengthens_support() -> None:
    complete = {
        "u1": {"treatment": "control"},
        "u2": {"treatment": "drug"},
        "u3": {"treatment": "control"},
        "u4": {"treatment": "drug"},
    }
    blocks = {"u1": "b1", "u2": "b1", "u3": "b2", "u4": "b2"}
    declared = {"treatment": ("control", "drug")}
    full = evaluate_design_matrix(assignments=complete, declared_levels=declared, blocks=blocks)
    assert _status(full) is ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN
    for unit_id in complete:
        degraded = {**complete, unit_id: {}}
        check = evaluate_design_matrix(
            assignments=degraded, declared_levels=declared, blocks=blocks
        )
        assert _status(check) is not ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN


def test_unrelated_nuisance_alias_does_not_alias_the_treatment() -> None:
    # batch e day coincidono, ma il trattamento varia dentro entrambi.
    check = evaluate_design_matrix(
        assignments={
            "u1": {"treatment": "control", "batch": "b1", "day": "d1"},
            "u2": {"treatment": "drug", "batch": "b1", "day": "d1"},
            "u3": {"treatment": "control", "batch": "b2", "day": "d2"},
            "u4": {"treatment": "drug", "batch": "b2", "day": "d2"},
        },
        declared_levels={
            "treatment": ("control", "drug"),
            "batch": ("b1", "b2"),
            "day": ("d1", "d2"),
        },
        blocks={"u1": "b1", "u2": "b1", "u3": "b2", "u4": "b2"},
    )
    assert check.fully_aliased is True
    assert check.aliased_factor_pairs == (("batch", "day"),)
    assert check.aliased_with("treatment") == ()
    assert check.aliased_with("batch") == ("day",)
    assert check.gate_inputs_for_factor("treatment")["fully_aliased"] is False
    assert check.gate_inputs_for_factor("batch")["fully_aliased"] is True
    assert _status(check) is ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN


def test_treatment_constant_within_multi_unit_clusters_caps_support() -> None:
    # Trattamento per gabbia, topi come unita: il contrasto e solo fra gabbie.
    check = evaluate_design_matrix(
        assignments={
            "m1": {"treatment": "control", "cage": "c1"},
            "m2": {"treatment": "control", "cage": "c1"},
            "m3": {"treatment": "control", "cage": "c2"},
            "m4": {"treatment": "drug", "cage": "c3"},
            "m5": {"treatment": "drug", "cage": "c3"},
            "m6": {"treatment": "drug", "cage": "c4"},
        },
        declared_levels={"treatment": ("control", "drug"), "cage": ("c1", "c2", "c3", "c4")},
        blocks={unit: "all" for unit in ("m1", "m2", "m3", "m4", "m5", "m6")},
    )
    assert check.aliased_factor_pairs == ()
    assert check.constant_within_levels_of["treatment"] == ("cage",)
    assert check.gate_inputs_for_factor("treatment")["between_cluster_only"] is True
    assert _status(check) is ContrastSupportStatus.PARTIALLY_SUPPORTED


def test_per_unit_identifier_is_not_a_cluster() -> None:
    # Una gabbia per topo: la gabbia e un identificativo, non un cluster.
    check = evaluate_design_matrix(
        assignments={
            "m1": {"treatment": "control", "cage": "c1"},
            "m2": {"treatment": "control", "cage": "c2"},
            "m3": {"treatment": "drug", "cage": "c3"},
            "m4": {"treatment": "drug", "cage": "c4"},
        },
        declared_levels={"treatment": ("control", "drug"), "cage": ("c1", "c2", "c3", "c4")},
        blocks={unit: "all" for unit in ("m1", "m2", "m3", "m4")},
    )
    assert check.constant_within_levels_of["treatment"] == ()
    assert _status(check) is ContrastSupportStatus.SUPPORTED_WITHIN_RECORDED_DESIGN


def test_design_matrix_is_invariant_to_unit_order() -> None:
    assignments = {
        "u1": {"treatment": "control", "batch": "b1"},
        "u2": {"treatment": "drug", "batch": "b1"},
        "u3": {"treatment": "control", "batch": "b2"},
    }
    declared = {"treatment": ("control", "drug"), "batch": ("b1", "b2")}
    blocks = {"u1": "b1", "u2": "b1", "u3": "b2"}
    forward = evaluate_design_matrix(
        assignments=assignments, declared_levels=declared, blocks=blocks
    )
    backward = evaluate_design_matrix(
        assignments=dict(reversed(list(assignments.items()))),
        declared_levels=declared,
        blocks=dict(reversed(list(blocks.items()))),
    )
    assert forward == backward
