"""Distribuzioni del power engine: centrali esatte + noncentrali verificate."""

from __future__ import annotations

import math

import pytest

from ntruth.power import calculator as calc
from ntruth.power import distributions as dist


def test_norm_cdf_matches_known_values() -> None:
    assert dist.norm_cdf(0.0) == pytest.approx(0.5)
    assert dist.norm_cdf(1.959963984540054) == pytest.approx(0.975, abs=1e-9)
    assert dist.norm_cdf(-3.0) == pytest.approx(0.00134989803163, rel=1e-9)


def test_central_distributions_match_known_values() -> None:
    # chi2(1) al 95%: 3.841458820694124.
    assert dist.chi2_cdf(1.0, 3.841458820694124) == pytest.approx(0.95, rel=1e-9)
    # F(1, 1) mediana: 1.0.
    assert dist.f_cdf(1.0, 1.0, 1.0) == pytest.approx(0.5, rel=1e-9)
    # t(1) e Cauchy: CDF(1) = 0.75.
    assert dist.t_cdf(1.0, 1.0) == pytest.approx(0.75, rel=1e-9)
    # t(30) crit bilaterale 5%: 2.042272456.
    assert dist.t_ppf(30.0, 0.975) == pytest.approx(2.042272456, rel=1e-6)


def test_noncentral_reduces_to_central_when_lambda_zero() -> None:
    assert dist.ncx2_cdf(4.0, 0.0, 5.0) == pytest.approx(dist.chi2_cdf(4.0, 5.0))
    assert dist.ncf_cdf(2.0, 20.0, 0.0, 2.0) == pytest.approx(dist.f_cdf(2.0, 20.0, 2.0))
    assert dist.nct_cdf(20.0, 0.0, 1.0) == pytest.approx(dist.t_cdf(20.0, 1.0), abs=5e-4)


def test_noncentral_power_is_monotone_in_effect() -> None:
    small, _ = dist.f_power_from_lambda(3.0, 40.0, 5.0, 0.05)
    large, _ = dist.f_power_from_lambda(3.0, 40.0, 15.0, 0.05)
    assert large > small
    small_t, _ = dist.t_power_from_delta(20.0, 1.0, 0.05, True)
    large_t, _ = dist.t_power_from_delta(20.0, 3.0, 0.05, True)
    assert large_t > small_t


def test_gpower_anchor_two_sample_one_sided() -> None:
    # Faul et al. 2007: d=0.5, alpha=.05, power=.95, 1-sided, q=1 -> 88+88.
    # Il solver minimizza il totale (88+87 ammesso): tolleranza documentata.
    solved = calc.solve_n_t_two_sample(0.5, 0.05, 0.95, False, 1.0)
    assert solved.n_total == pytest.approx(176, abs=1)
    assert solved.achieved_power >= 0.95


def test_gpower_anchor_two_sample_two_sided() -> None:
    # d=0.5, two-sided, power=.8 -> 64+64 = 128.
    solved = calc.solve_n_t_two_sample(0.5, 0.05, 0.8, True, 1.0)
    assert solved.n_total == 128
    assert solved.achieved_power >= 0.8


def test_gpower_anchor_one_sample() -> None:
    # d=0.5, two-sided, power=.8 -> N=34.
    solved = calc.solve_n_t_one_sample(0.5, 0.05, 0.8, True)
    assert solved.n_total == 34
    assert solved.achieved_power >= 0.8


def test_gpower_anchor_anova() -> None:
    # One-way ANOVA f=0.25, k=4, power=.8 -> N=180 bilanciato.
    solved = calc.solve_n_anova(4, 0.25, 0.05, 0.8)
    assert solved.n_total == 180
    assert solved.achieved_power >= 0.8


def test_gpower_anchor_regression_omnibus() -> None:
    # p=5, f2=0.15, power=.8 -> N=92.
    solved = calc.solve_n_regression_omnibus(5, 0.15, 0.05, 0.8)
    assert solved.n_total == 92
    assert solved.achieved_power >= 0.8


def test_gpower_anchor_chi2() -> None:
    # w=0.3, df=1, power=.8 -> N=88.
    solved = calc.solve_n_chi2(0.3, 1, 0.05, 0.8)
    assert solved.n_total == 88
    assert solved.achieved_power >= 0.8


def test_t_delta_uses_correct_allocation_formula() -> None:
    # Bilanciato: delta = d*sqrt(N)/2.
    assert calc.t_two_sample_delta(0.5, 64, 64) == pytest.approx(0.5 * math.sqrt(128) / 2)
    with pytest.raises(ValueError):
        calc.t_two_sample_delta(0.0, 10, 10)


def test_design_effect_is_diagnostic_only() -> None:
    assert calc.design_effect(100.0, 0.05) == pytest.approx(5.95)
    assert calc.effective_n_diagnostic(595, 5.95) == pytest.approx(100.0)
    assert calc.clustered_n_diagnostic(24, 5.95) == 143
    with pytest.raises(ValueError):
        calc.design_effect(1.0, 0.1)
