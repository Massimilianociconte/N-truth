"""Regressioni numeriche del modulo power (audit 2026-09-23).

Ancore indipendenti: G*Power 3.1, Connor (1987) per McNemar, Chernick & Liu
(2002) per la potenza a dente di sega dei test esatti.
"""

from __future__ import annotations

import math

import pytest

from ntruth.power import calculator as calc
from ntruth.power import distributions as dist
from ntruth.power.planner import build_power_plan
from ntruth.power.schema import (
    EndpointType,
    PowerFamily,
    PowerPlanInput,
    SesoiRecord,
    SesoiSource,
    Tail,
)
from ntruth.schemas.factor_role import ContrastType, FactorRole


def test_t_ppf_lower_tail_is_symmetric() -> None:
    for df in (1.0, 4.0, 30.0):
        for p in (0.001, 0.05, 0.3):
            assert dist.t_ppf(df, p) == pytest.approx(-dist.t_ppf(df, 1.0 - p), abs=1e-9)
    with pytest.raises(ValueError):
        dist.t_ppf(5.0, 0.0)


def test_nct_quantile_cache_is_keyed_by_exact_df() -> None:
    dist._CHI2_QUANTILE_CACHE.clear()
    fresh = dist.nct_cdf(17.0, 2.0, 2.1)
    dist._CHI2_QUANTILE_CACHE.clear()
    dist.nct_cdf(17.3, 2.0, 2.1)
    after_non_integer = dist.nct_cdf(17.0, 2.0, 2.1)
    assert after_non_integer == fresh


def test_two_sample_ratio_one_is_always_balanced() -> None:
    # G*Power: d=2, alpha .05 bilaterale, potenza .8 -> 6 per gruppo (0.8764).
    result = calc.solve_n_t_two_sample(2.0, 0.05, 0.8, True)
    assert result.n_per_group == (6, 6)
    assert result.achieved_power == pytest.approx(0.8764, abs=1e-3)


@pytest.mark.parametrize("ratio", [0.5, 2.0, 3.0])
def test_two_sample_allocation_ratio_is_honored(ratio: float) -> None:
    result = calc.solve_n_t_two_sample(0.5, 0.05, 0.9, True, allocation_ratio=ratio)
    n1, n2 = result.n_per_group
    assert n2 == max(2, math.ceil(ratio * n1 - 1e-9))
    assert result.achieved_power >= 0.9
    smaller = calc.power_t_two_sample(
        n1 - 1, max(2, math.ceil(ratio * (n1 - 1) - 1e-9)), 0.5, 0.05, True
    )
    assert smaller.power < 0.9


def test_mcnemar_matches_connor_1987() -> None:
    # psi=0.3, OR=2 -> delta=0.1; Connor: n = 233.09 -> 234 coppie.
    psi, delta = 0.3, 0.1
    z_alpha, z_beta = dist.norm_ppf(0.975), dist.norm_ppf(0.8)
    connor = (z_alpha * math.sqrt(psi) + z_beta * math.sqrt(psi - delta**2)) ** 2 / delta**2
    required = math.ceil(connor)
    assert calc.power_mcnemar(required, psi, 2.0, 0.05).power >= 0.8
    assert calc.power_mcnemar(required - 1, psi, 2.0, 0.05).power < 0.8


@pytest.mark.parametrize("ratio", [0.25, 0.5, 1.0, 2.0])
def test_poisson_allocation_reaches_target_power(ratio: float) -> None:
    result = calc.solve_n_poisson_rate(1.5, 2.0, 1.0, 0.05, 0.8, True, ratio)
    n1, n2 = result.n_per_group
    mu0, mu1 = 2.0, 3.0
    se = math.sqrt(1.0 / (n1 * mu0) + 1.0 / (n2 * mu1))
    power = dist.norm_cdf(abs(math.log(1.5)) / se - dist.norm_ppf(0.975))
    assert power >= 0.8
    assert result.achieved_power == pytest.approx(power)


def test_binomial_exact_returns_the_true_minimum() -> None:
    # Dente di sega: la bisezione restituiva 70, il minimo reale e 65.
    result = calc.solve_n_binomial_exact(0.5, 0.7, 0.05, 0.9, True)
    assert result.n_total == 65
    assert all(calc.power_binomial_exact(n, 0.5, 0.7, 0.05, True).power < 0.9 for n in range(2, 65))
    stable = calc.binomial_stable_n(0.5, 0.7, 0.05, 0.9, True, start=65)
    assert stable is not None and stable >= 65
    assert all(
        calc.power_binomial_exact(n, 0.5, 0.7, 0.05, True).power >= 0.9
        for n in range(stable, stable + calc.BINOMIAL_STABILITY_WINDOW)
    )


def _plan(family: PowerFamily, scale: str, **effect: object) -> PowerPlanInput:
    payload: dict[str, object] = {
        "query_id": "IQ-1",
        "factor_id": "treatment",
        "contrast_id": "control_vs_treated",
        "endpoint_id": "response",
        "endpoint_type": EndpointType.BINARY,
        "family": family,
        "tail": Tail.TWO_SIDED,
        "alpha": 0.05,
        "target_power": 0.9,
        "factor_role": FactorRole.ASSIGNED_INTERVENTION,
        "contrast_type": ContrastType.ASSIGNED_INTERVENTION_EFFECT,
        "assignment_event_id": "ASSIGN-1",
        "experimental_unit_type": "independent culture",
        "sesoi": SesoiRecord(
            source=SesoiSource.DECLARED_SESOI,
            value=float(effect.pop("sesoi_value")),  # type: ignore[arg-type]
            effect_scale=scale,
            endpoint_id="response",
            contrast_id="control_vs_treated",
            rationale="SESOI dichiarata dal team su prior biologico documentato.",
            evidence_ids=("EV-1",),
        ),
    }
    payload.update(effect)
    return PowerPlanInput.model_validate(payload)


def test_binomial_plan_declares_sawtooth_power() -> None:
    plan = build_power_plan(_plan(PowerFamily.BINOMIAL_EXACT, "g", p0=0.5, p1=0.7, sesoi_value=0.2))
    codes = {assumption.code for assumption in plan.assumptions}
    assert "exact_power_sawtooth" in codes
    assert plan.required_total_eu == 65


def test_logistic_plan_states_covariate_semantics() -> None:
    plan = build_power_plan(
        _plan(PowerFamily.LOGISTIC_WALD, "or", odds_ratio=1.5, p1=0.3, sesoi_value=1.5)
    )
    codes = {assumption.code for assumption in plan.assumptions}
    assert "logistic_continuous_covariate" in codes
    assert plan.achieved_power >= 0.9


# Valori di riferimento congelati da scipy 1.18 (stats.ncx2/ncf, special.betainc):
# l'ambiente di test resta stdlib-only.
@pytest.mark.parametrize(
    ("df", "noncentrality", "x", "expected"),
    [
        (1.0, 3000.0, 3100.0, 0.8173700322481311),
        (30.0, 401.0, 500.0, 0.9505985268779247),
        (5.0, 50.0, 60.0, 0.6568844160049281),
    ],
)
def test_noncentral_chi2_is_exact_for_large_lambda(
    df: float, noncentrality: float, x: float, expected: float
) -> None:
    # Prima: approssimazione normale per lambda > 400 (errore ~4e-3).
    assert dist.ncx2_cdf(df, noncentrality, x) == pytest.approx(expected, abs=1e-10)


@pytest.mark.parametrize(
    ("df1", "df2", "noncentrality", "f", "expected"),
    [
        (30.0, 1000.0, 4000.0, 150.0, 0.9772274541314564),
        (3.0, 100.0, 30.0, 4.0, 0.014510811810548224),
    ],
)
def test_noncentral_f_has_no_underflow_for_large_lambda(
    df1: float, df2: float, noncentrality: float, f: float, expected: float
) -> None:
    # Prima: exp(-lambda/2) andava a zero oltre lambda ~ 1490 e beta_inc
    # andava in overflow con parametri grandi.
    assert dist.ncf_cdf(df1, df2, noncentrality, f) == pytest.approx(expected, abs=1e-10)


def test_regularized_beta_is_stable_for_large_parameters() -> None:
    assert dist.beta_inc(3000.0, 500.0, 0.86) == pytest.approx(0.6823254453687391, abs=1e-10)
    assert dist.beta_inc(1000.0, 2000.0, 0.33) == pytest.approx(0.3506326761342108, abs=1e-10)
