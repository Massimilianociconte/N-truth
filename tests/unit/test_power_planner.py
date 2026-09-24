"""Planner a priori: gate EU, SESOI, applicabilita, candidate-only."""

from __future__ import annotations

import pytest

from ntruth.power.planner import PowerBlockedError, build_power_plan
from ntruth.power.schema import (
    ClusterInfo,
    EndpointType,
    PowerFamily,
    PowerPlanInput,
    SesoiRecord,
    SesoiSource,
    Tail,
)
from ntruth.schemas.factor_role import ContrastType, FactorRole


def _sesoi(
    value: float = 0.5,
    scale: str = "d",
    source: SesoiSource = SesoiSource.DECLARED_SESOI,
) -> SesoiRecord:
    return SesoiRecord(
        source=source,
        value=value,
        effect_scale=scale,
        endpoint_id="viability",
        contrast_id="control_vs_treated",
        rationale="SESOI dichiarata dal team su prior biologico documentato.",
        evidence_ids=("EV-1",),
    )


def _base(**overrides) -> PowerPlanInput:
    payload: dict[str, object] = {
        "query_id": "IQ-1",
        "factor_id": "treatment",
        "contrast_id": "control_vs_treated",
        "endpoint_id": "viability",
        "endpoint_type": EndpointType.CONTINUOUS,
        "family": PowerFamily.T_TWO_SAMPLE,
        "tail": Tail.TWO_SIDED,
        "alpha": 0.05,
        "target_power": 0.8,
        "factor_role": FactorRole.ASSIGNED_INTERVENTION,
        "contrast_type": ContrastType.ASSIGNED_INTERVENTION_EFFECT,
        "assignment_event_id": "ASSIGN-1",
        "experimental_unit_type": "independent culture",
        "sesoi": _sesoi(),
        "cohen_d": 0.5,
    }
    payload.update(overrides)
    return PowerPlanInput.model_validate(payload)


def test_happy_path_two_sample_counts_independent_eu() -> None:
    plan = build_power_plan(_base())
    assert plan.required_total_eu == 128
    assert plan.required_per_group == (64, 64)
    assert plan.achieved_power >= 0.8
    assert plan.method.value == "CLOSED_FORM_NONCENTRAL_T"
    assert plan.strategy == "HANDOFF_ONLY"
    assert plan.scientific_validation_status == "not_performed"
    assert "independent culture" in plan.eu_statement
    assert "64, 64" in plan.eu_statement
    assert len(plan.input_checksum) == 64
    assert plan.plan_id.startswith("pp-")
    assert len(plan.sensitivity) == 3
    codes = {item.code for item in plan.assumptions}
    assert {"independent_eu_count", "handoff_only_no_test_selected"} <= codes


def test_eu_gate_denied_without_assigned_intervention() -> None:
    payload = _base(
        factor_role=FactorRole.OBSERVATIONAL_EXPOSURE,
        contrast_type=ContrastType.OBSERVATIONAL_ASSOCIATION,
    )
    with pytest.raises(PowerBlockedError, match="eu_gate_denied"):
        build_power_plan(payload)


def test_eu_gate_denied_without_assignment_event() -> None:
    payload = _base(assignment_event_id=None, exposure_cluster="well-A")
    with pytest.raises(PowerBlockedError, match="eu_gate_denied"):
        build_power_plan(payload)


def test_endpoint_mismatch_is_fail_closed() -> None:
    payload = _base(endpoint_type=EndpointType.BINARY)
    with pytest.raises(PowerBlockedError, match="endpoint_mismatch"):
        build_power_plan(payload)


def test_sesoi_scale_mismatch_is_fail_closed() -> None:
    payload = _base(sesoi=_sesoi(scale="f"))
    with pytest.raises(PowerBlockedError, match="sesoi_mismatch"):
        build_power_plan(payload)


def test_cohen_convention_is_flagged_weak() -> None:
    payload = _base(sesoi=_sesoi(source=SesoiSource.CONVENTIONAL_COHEN))
    plan = build_power_plan(payload)
    codes = {item.code for item in plan.assumptions}
    assert "conventional_cohen_weak_assumption" in codes
    assert plan.required_total_eu == 128


def test_repeated_measures_requires_simulation() -> None:
    payload = _base(repeated_measures=True)
    with pytest.raises(PowerBlockedError, match="simulation_required"):
        build_power_plan(payload)


def test_hierarchical_without_icc_is_blocked() -> None:
    payload = _base(
        hierarchical_depth=4,
        cluster=ClusterInfo(mean_obs_per_cluster=100.0, icc=None),
    )
    with pytest.raises(PowerBlockedError, match="applicability_blocked"):
        build_power_plan(payload)


def test_cluster_adjustment_never_redefines_eu() -> None:
    payload = _base(
        hierarchical_depth=3,
        cluster=ClusterInfo(
            mean_obs_per_cluster=100.0, icc=0.05, description="cells within culture"
        ),
    )
    plan = build_power_plan(payload)
    assert plan.cluster_adjustment is not None
    assert plan.cluster_adjustment.design_effect == pytest.approx(5.95)
    assert plan.required_total_eu == 128
    assert "Non trasforma misure in replicati" in plan.cluster_adjustment.warning


def test_cluster_diagnostics_are_counted_in_observations_not_eu() -> None:
    """Regressione: n_eff era n_EU/DEFF (128 colture -> 21.5), un errore di unita."""
    payload = _base(
        hierarchical_depth=3,
        cluster=ClusterInfo(
            mean_obs_per_cluster=100.0, icc=0.05, description="cells within culture"
        ),
    )
    adjustment = build_power_plan(payload).cluster_adjustment
    assert adjustment is not None
    assert adjustment.clustered_total_diagnostic == 12_800
    assert adjustment.effective_n_diagnostic == pytest.approx(12_800 / 5.95)
    # L'informazione di n EU con m osservazioni sta sempre tra n e n*m.
    assert 128 <= adjustment.effective_n_diagnostic <= 12_800


def test_cluster_adjustment_reports_naive_false_positive_rate() -> None:
    payload = _base(
        hierarchical_depth=3,
        cluster=ClusterInfo(mean_obs_per_cluster=100.0, icc=0.05, description="cells"),
    )
    adjustment = build_power_plan(payload).cluster_adjustment
    assert adjustment is not None
    # Valore esatto verificato contro scipy (quadratura sulla variabile Beta).
    assert adjustment.naive_false_positive_rate == pytest.approx(0.4218360799, abs=1e-8)
    grid = {row.icc: row.alpha_actual for row in adjustment.naive_false_positive_sensitivity}
    assert 0.05 in grid
    assert grid[0.05] == adjustment.naive_false_positive_rate
    rates = [grid[icc] for icc in sorted(grid)]
    assert rates == sorted(rates)
    assert "pseudoreplicazione" in adjustment.warning


def test_naive_rate_is_absent_for_families_without_exact_formula() -> None:
    payload = _base(
        family=PowerFamily.T_ONE_SAMPLE,
        hierarchical_depth=3,
        cluster=ClusterInfo(mean_obs_per_cluster=10.0, icc=0.1, description="obs"),
    )
    plan = build_power_plan(payload)
    assert plan.cluster_adjustment is not None
    assert plan.cluster_adjustment.naive_false_positive_rate is None
    assert plan.cluster_adjustment.naive_false_positive_sensitivity == ()


def test_dropout_and_bonferroni_are_explicit() -> None:
    payload = _base(dropout_rate=0.2, multiplicity_m=2)
    plan = build_power_plan(payload)
    assert plan.alpha_effective == pytest.approx(0.025)
    assert plan.required_total_with_dropout >= plan.required_total_eu
    codes = {item.code for item in plan.assumptions}
    assert {"dropout_inflation", "bonferroni_multiplicity"} <= codes


def test_binomial_exact_reports_actual_alpha() -> None:
    payload = _base(
        endpoint_type=EndpointType.BINARY,
        family=PowerFamily.BINOMIAL_EXACT,
        sesoi=_sesoi(value=0.15, scale="g"),
        p0=0.5,
        p1=0.65,
        cohen_d=None,
    )
    plan = build_power_plan(payload)
    assert plan.method.value == "EXACT_ENUMERATION"
    assert plan.actual_alpha is not None
    assert plan.actual_alpha <= 0.05
    assert plan.achieved_power >= 0.8


def test_determinism_same_input_same_plan() -> None:
    first = build_power_plan(_base())
    second = build_power_plan(_base())
    assert first.plan_id == second.plan_id
    assert first.input_checksum == second.input_checksum
    assert first.required_total_eu == second.required_total_eu
