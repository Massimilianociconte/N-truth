"""Alpha effettiva di un'analisi pseudoreplicata (formula esatta).

I valori di riferimento sono stati calcolati con scipy integrando sulla
variabile R ~ Beta(a/2, b/2) (quadratura diversa da quella del modulo) e
confermati con Monte Carlo a 200k repliche; l'accordo misurato e < 2e-11.
"""

from __future__ import annotations

import pytest

from ntruth.power.calculator import PowerComputationError
from ntruth.power.pseudoreplication import naive_type_i_error, naive_type_i_error_grid

# (unita totali, osservazioni per unita, ICC, alpha, gruppi, unilaterale) -> alpha reale
REFERENCE = [
    ((6, 50, 0.05, 0.05, 2, False), 0.2942888837),
    ((6, 50, 0.2, 0.05, 2, False), 0.5637847562),
    ((4, 10, 0.1, 0.05, 2, False), 0.1603068247),
    ((8, 5, 0.3, 0.05, 2, True), 0.1401533228),
    ((12, 20, 0.1, 0.05, 3, False), 0.3620444674),
    ((2, 30, 0.1, 0.05, 2, False), 0.3402454924),
    ((6, 100, 0.5, 0.01, 2, False), 0.7423608565),
    ((20, 8, 0.02, 0.05, 4, False), 0.0767897166),
    ((128, 100, 0.05, 0.05, 2, False), 0.4218360799),
    ((3, 2, 0.9, 0.05, 3, False), 0.6481856919),
    ((10, 3, 1.0, 0.05, 2, False), 0.3054180905),
    ((6, 7.5, 0.1, 0.05, 2, False), 0.1297504774),
    ((2000, 1000, 0.05, 0.05, 2, False), 0.7836407271),
]


@pytest.mark.parametrize(("case", "expected"), REFERENCE, ids=[str(c) for c, _ in REFERENCE])
def test_matches_independent_reference(case: tuple, expected: float) -> None:
    units, obs, icc, alpha, groups, one_sided = case
    result = naive_type_i_error(
        total_units=units,
        mean_obs_per_unit=obs,
        icc=icc,
        alpha=alpha,
        groups=groups,
        one_sided=one_sided,
    )
    assert result.alpha_actual == pytest.approx(expected, abs=1e-8)
    assert result.exact_for_balanced_design is float(obs).is_integer()


@pytest.mark.parametrize("groups", [2, 3, 5])
def test_zero_icc_returns_nominal_alpha(groups: int) -> None:
    result = naive_type_i_error(
        total_units=10, mean_obs_per_unit=20, icc=0.0, alpha=0.05, groups=groups
    )
    assert result.alpha_actual == pytest.approx(0.05, abs=1e-9)
    assert result.inflation_factor == pytest.approx(1.0, abs=1e-7)


def test_one_observation_per_unit_is_not_pseudoreplication() -> None:
    result = naive_type_i_error(total_units=10, mean_obs_per_unit=1, icc=0.5, alpha=0.05)
    assert result.alpha_actual == pytest.approx(0.05, abs=1e-9)


def test_inflation_grows_with_icc_and_cluster_size() -> None:
    by_icc = naive_type_i_error_grid(total_units=8, mean_obs_per_unit=30, alpha=0.05)
    rates = [row.alpha_actual for row in by_icc]
    assert rates == sorted(rates)
    by_size = [
        naive_type_i_error(total_units=8, mean_obs_per_unit=m, icc=0.1, alpha=0.05).alpha_actual
        for m in (2, 5, 20, 100)
    ]
    assert by_size == sorted(by_size)


def test_one_sided_rate_is_inflated_but_bounded() -> None:
    one = naive_type_i_error(
        total_units=8, mean_obs_per_unit=5, icc=0.3, alpha=0.05, one_sided=True
    )
    assert 0.05 < one.alpha_actual < 0.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"total_units": 1, "mean_obs_per_unit": 10, "icc": 0.1, "alpha": 0.05},
        {"total_units": 6, "mean_obs_per_unit": 0.5, "icc": 0.1, "alpha": 0.05},
        {"total_units": 6, "mean_obs_per_unit": 10, "icc": 1.5, "alpha": 0.05},
        {"total_units": 6, "mean_obs_per_unit": 10, "icc": 0.1, "alpha": 0.0},
        {"total_units": 6, "mean_obs_per_unit": 10, "icc": 0.1, "alpha": 0.05, "groups": 1},
        {
            "total_units": 6,
            "mean_obs_per_unit": 10,
            "icc": 0.1,
            "alpha": 0.05,
            "groups": 3,
            "one_sided": True,
        },
    ],
)
def test_invalid_inputs_fail_closed(kwargs: dict) -> None:
    with pytest.raises(PowerComputationError):
        naive_type_i_error(**kwargs)


def test_cli_prints_sensitivity_and_declared_icc() -> None:
    from typer.testing import CliRunner

    from ntruth.cli.main import app

    result = CliRunner().invoke(
        app,
        ["power", "false-positive", "--units", "6", "--obs-per-unit", "50", "--icc", "0.05"],
    )
    assert result.exit_code == 0, result.output
    assert "falsi positivi 0.294" in result.output
    assert "ICC dichiarata" in result.output


def test_cli_rejects_one_sided_multigroup() -> None:
    from typer.testing import CliRunner

    from ntruth.cli.main import app

    result = CliRunner().invoke(
        app,
        [
            "power",
            "false-positive",
            "--units",
            "6",
            "--obs-per-unit",
            "10",
            "--groups",
            "3",
            "--one-sided",
        ],
    )
    assert result.exit_code == 2
