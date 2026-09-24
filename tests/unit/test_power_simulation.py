"""Simulazione gerarchica: convergenza, determinismo, fail-closed, delega."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from ntruth.power import calculator as calc
from ntruth.power.errors import PowerBlockedError
from ntruth.power.planner import build_power_plan
from ntruth.power.schema import (
    EndpointType,
    PowerFamily,
    PowerPlanInput,
    SesoiRecord,
    SesoiSource,
    Tail,
)
from ntruth.power.simulation import (
    GenerativeModel,
    HierarchyLevel,
    SimulationInput,
    SimulationTemplate,
    VarianceMode,
    required_n_sim_for_mcse,
    simulate_power,
    solve_n_eu_by_simulation,
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


def _degenerate_generative(effect: float = 0.5) -> GenerativeModel:
    return GenerativeModel(
        levels=(HierarchyLevel(level_name="culture", counts_per_parent=(1,)),),
        variance_mode=VarianceMode.VARIANCE_COMPONENTS,
        sigma2_by_level=(0.0,),
        sigma2_residual=1.0,
        intercept=0.0,
        treatment_effect=effect,
        assignment_level="culture",
    )


def _degenerate_input(
    n: int = 16, effect: float = 0.5, n_sim: int = 2000, seed: str = "test-seed-1234"
) -> SimulationInput:
    template = SimulationTemplate(
        generative=_degenerate_generative(effect),
        n_sim=n_sim,
        mcse_target=0.02,
        seed_root=seed,
    )
    return SimulationInput(
        template=template,
        sesoi=_sesoi(value=effect),
        n_eu_per_group=(n, n),
        alpha=0.05,
    )


def test_degenerate_simulation_converges_to_closed_form() -> None:
    result = simulate_power(_degenerate_input())
    reference = calc.power_t_two_sample(16, 16, 0.5, 0.05, True)
    assert abs(result.power_estimate - reference.power) <= max(0.05, 3 * result.mcse)
    assert result.method.value == "MONTE_CARLO_HIERARCHICAL"
    assert result.strategy == "HANDOFF_ONLY"


def test_simulation_is_bit_deterministic() -> None:
    payload = _degenerate_input()
    first = simulate_power(payload)
    second = simulate_power(payload)
    assert first == second
    assert first.result_id == second.result_id


def test_different_seed_changes_provenance() -> None:
    first = simulate_power(_degenerate_input(seed="test-seed-1234"))
    second = simulate_power(_degenerate_input(seed="test-seed-5678"))
    assert first.result_id != second.result_id
    assert first.input_checksum != second.input_checksum


def test_mcse_formula_is_reported() -> None:
    result = simulate_power(_degenerate_input())
    expected = math.sqrt(result.power_estimate * (1.0 - result.power_estimate) / 2000)
    assert result.mcse == pytest.approx(expected)
    assert result.ci95_lo <= result.power_estimate <= result.ci95_hi


def test_required_n_sim_for_mcse() -> None:
    assert required_n_sim_for_mcse(0.01) == 2500
    assert required_n_sim_for_mcse(0.005) == 10000
    with pytest.raises(PowerBlockedError, match="mcse_invalid"):
        required_n_sim_for_mcse(0.0)


def test_binary_endpoint_is_fail_closed() -> None:
    with pytest.raises(ValidationError, match="endpoint_not_simulated_v1"):
        GenerativeModel(
            levels=(HierarchyLevel(level_name="culture", counts_per_parent=(1,)),),
            variance_mode=VarianceMode.VARIANCE_COMPONENTS,
            sigma2_by_level=(0.0,),
            sigma2_residual=1.0,
            intercept=0.0,
            treatment_effect=0.5,
            assignment_level="culture",
            endpoint_type=EndpointType.BINARY,
        )


def test_inconsistent_icc_is_fail_closed() -> None:
    with pytest.raises(ValidationError, match="variance_icc_inconsistent"):
        GenerativeModel(
            levels=(
                HierarchyLevel(level_name="culture", counts_per_parent=(1,)),
                HierarchyLevel(level_name="well", counts_per_parent=(2,)),
            ),
            variance_mode=VarianceMode.ICC,
            icc_by_level=(0.6, 0.5),
            total_sd=1.0,
            intercept=0.0,
            treatment_effect=0.5,
            assignment_level="culture",
        )


def test_treatment_below_eu_is_fail_closed() -> None:
    with pytest.raises(ValidationError, match="treatment_below_eu"):
        GenerativeModel(
            levels=(
                HierarchyLevel(level_name="culture", counts_per_parent=(1,)),
                HierarchyLevel(level_name="well", counts_per_parent=(2,)),
            ),
            variance_mode=VarianceMode.VARIANCE_COMPONENTS,
            sigma2_by_level=(0.1, 0.1),
            sigma2_residual=0.8,
            intercept=0.0,
            treatment_effect=0.5,
            assignment_level="well",
        )


def test_n_sim_below_precision_is_fail_closed() -> None:
    with pytest.raises(ValidationError, match="n_sim_below_precision"):
        SimulationTemplate(generative=_degenerate_generative(), n_sim=1000)


def test_planner_delegates_to_simulation_when_required() -> None:
    payload = _base(repeated_measures=True)
    with pytest.raises(PowerBlockedError, match="simulation_required"):
        build_power_plan(payload)
    template = SimulationTemplate(
        generative=_degenerate_generative(0.8),
        n_sim=1000,
        mcse_target=0.02,
        seed_root="plan-sim-01",
    )
    plan = build_power_plan(payload, simulation=template)
    assert plan.method.value == "MONTE_CARLO_HIERARCHICAL"
    assert plan.simulation_n == 1000
    assert plan.simulation_mcse is not None and plan.simulation_mcse >= 0
    assert plan.simulation_seed_root == "plan-sim-01"
    assert plan.strategy == "HANDOFF_ONLY"
    codes = {item.code for item in plan.assumptions}
    assert {
        "simulation_conditional_on_declared_analysis",
        "monte_carlo_frequency_not_calibrated",
        "eu_aggregate_only_no_pseudoreplication",
    } <= codes


def test_planner_rejects_unsupported_family_for_simulation() -> None:
    payload = _base(
        family=PowerFamily.ANOVA_FACTORIAL,
        sesoi=_sesoi(value=0.25, scale="f"),
        cohen_d=None,
        cohen_f=0.25,
        n_groups_k=4,
        n_tested_q=3,
        repeated_measures=True,
    )
    template = SimulationTemplate(
        generative=_degenerate_generative(0.5),
        n_sim=1000,
        mcse_target=0.02,
        seed_root="plan-sim-02",
    )
    with pytest.raises(PowerBlockedError, match="family_not_simulated_v1"):
        build_power_plan(payload, simulation=template)


def test_solve_by_simulation_matches_closed_form_order() -> None:
    template = SimulationTemplate(
        generative=_degenerate_generative(1.2),
        n_sim=3000,
        mcse_target=0.02,
        seed_root="solve-sim-01",
    )
    starter = SimulationInput(
        template=template, sesoi=_sesoi(value=1.2), n_eu_per_group=(2, 2), alpha=0.05
    )
    per_group, confirmed = solve_n_eu_by_simulation(starter, 0.8)
    reference = calc.solve_n_t_two_sample(1.2, 0.05, 0.8, True, 1.0)
    assert abs((per_group[0] + per_group[1]) - reference.n_total) <= 4
    assert confirmed.power_estimate - 1.64 * confirmed.mcse >= 0.8 - 0.05


def test_no_network_in_simulation_module() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "packages" / "ntruth" / "power" / "simulation.py"
    ).read_text(encoding="utf-8")
    for token in ("socket", "urllib", "requests", "httpx", "http.client", "urlopen"):
        assert token not in source


def test_unbalanced_pattern_follows_the_declared_ordinal_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # HierarchyLevel: parent p -> pattern[p % len]. The pattern was selected by a
    # SHA-256 of the node path (fixed across simulations), so the two arms could
    # receive different cluster-size compositions by chance.
    import ntruth.power.simulation as simulation

    leaves_by_eu: dict[str, int] = {}
    original = simulation._sim_randn

    def counting(**kwargs: object) -> float:
        stream = str(kwargs["stream"])
        if stream.startswith("resid:"):
            eu = stream.rsplit(":", 1)[1]
            leaves_by_eu[eu] = leaves_by_eu.get(eu, 0) + 1
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(simulation, "_sim_randn", counting)
    generative = GenerativeModel(
        levels=(
            HierarchyLevel(level_name="culture", counts_per_parent=(1,)),
            HierarchyLevel(level_name="well", counts_per_parent=(1, 3)),
        ),
        variance_mode=VarianceMode.VARIANCE_COMPONENTS,
        sigma2_by_level=(0.0, 0.5),
        sigma2_residual=1.0,
        intercept=0.0,
        treatment_effect=0.5,
        assignment_level="culture",
    )
    payload = SimulationInput(
        template=SimulationTemplate(
            generative=generative, n_sim=1000, mcse_target=0.02, seed_root="ordinal-seed"
        ),
        sesoi=_sesoi(value=0.5),
        n_eu_per_group=(4, 4),
        alpha=0.05,
    )
    simulate_power(payload)
    per_sim = {eu: count // 1000 for eu, count in leaves_by_eu.items()}
    control = [per_sim[f"eu{index}"] for index in range(4)]
    treated = [per_sim[f"eu{4 + index}"] for index in range(4)]
    assert control == treated == [1, 3, 1, 3]
