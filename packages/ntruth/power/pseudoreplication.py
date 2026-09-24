"""Tasso reale di falsi positivi di un'analisi pseudoreplicata.

Scenario: G gruppi, K unita sperimentali (cluster) in totale, m osservazioni per
unita, intercetto casuale per unita con ICC ``rho``, varianza totale costante e
nessun effetto del trattamento (H0). L'analisi "naive" tratta le K*m
osservazioni come indipendenti: t di Student a due campioni (G = 2) oppure ANOVA
a una via (G >= 2) sulle osservazioni. E il caso classico di pseudoreplicazione
(Hurlbert 1984; Lazic 2010; Aarts et al. 2014).

Derivazione esatta per disegno bilanciato nelle osservazioni per unita::

    SS_gruppi / sigma^2  ~ DEFF * chi2_{G-1}
    SS_unita  / sigma^2  ~ DEFF * chi2_a,        a = K - G
    SS_resid  / sigma^2  ~ (1 - rho) * chi2_b,   b = K (m - 1)

indipendenti, con DEFF = 1 + (m - 1) rho e nu = a + b = K m - G gradi di
liberta del denominatore naive. Con V = chi2_a + chi2_b ~ chi2_nu e
R = chi2_a / V ~ Beta(a/2, b/2), indipendenti per la proprieta beta-gamma, la
statistica naive vale::

    F_naive = DEFF * F_{G-1, nu} / g(R),   g(R) = (1 - rho) + m rho R

e condizionando su F si ottiene un integrale monodimensionale su [lo, c]::

    alpha_reale = [1 - F_cdf(c)] + int_lo^c I_{x(f)}(a/2, b/2) dF(f)
    x(f) = (DEFF f / c - (1 - rho)) / (m rho),  lo = c (1 - rho) / DEFF

dove c e il valore critico naive. Per rho = 0 l'integrale e vuoto e
alpha_reale = alpha: e il controllo interno della formula. Il test t
unilaterale e la meta del bilaterale con c = t_{1-alpha, nu}^2.

Con m non intero (dimensione media dei cluster) la formula usa gradi di
liberta reali: e un'approssimazione per cluster sbilanciati, dichiarata come
tale. Il risultato e una diagnostica di rischio, mai un conteggio di EU.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass

from ntruth.power import distributions as dist
from ntruth.power.calculator import PowerComputationError
from ntruth.power.schema import (
    DEFAULT_ICC_GRID,
    NaiveFalsePositiveRow,
    PseudoreplicationRiskInput,
    PseudoreplicationRiskResult,
    Tail,
)


@dataclass(frozen=True, slots=True)
class NaiveFalsePositiveRate:
    """Tasso di errore di I tipo effettivo dell'analisi sulle osservazioni."""

    alpha_nominal: float
    alpha_actual: float
    inflation_factor: float
    icc: float
    design_effect: float
    total_units: int
    mean_obs_per_unit: float
    groups: int
    one_sided: bool
    naive_df: float
    exact_for_balanced_design: bool


def _log_f_pdf(d1: float, d2: float, x: float) -> float:
    return (
        0.5 * (d1 * math.log(d1 * x) + d2 * math.log(d2) - (d1 + d2) * math.log(d1 * x + d2))
        - math.log(x)
        - (math.lgamma(d1 / 2.0) + math.lgamma(d2 / 2.0) - math.lgamma((d1 + d2) / 2.0))
    )


def _adaptive_simpson(
    fn: Callable[[float], float],
    lo: float,
    hi: float,
    *,
    tol: float,
    panels: int = 32,
    max_evaluations: int = 20_000,
) -> float:
    """Simpson adattivo globale: raffina sempre l'intervallo con errore massimo.

    Il budget di valutazioni rende il costo limitato anche quando l'integrando
    ha un rumore numerico sopra ``tol`` (per esempio la beta incompleta con
    parametri ~1e6, precisa a ~1e-9): la stima resta quella del raffinamento
    raggiunto invece di esplodere esponenzialmente.
    """

    def simpson(a: float, b: float, fa: float, fm: float, fb: float) -> float:
        return (b - a) / 6.0 * (fa + 4.0 * fm + fb)

    heap: list[tuple[float, int, tuple[float, float, float, float, float, float, float]]] = []
    total = 0.0
    error = 0.0
    evaluations = 0
    width = (hi - lo) / panels

    def push(a: float, b: float, fa: float, fm: float, fb: float) -> None:
        nonlocal total, error, evaluations
        mid = (a + b) / 2.0
        fl, fr = fn((a + mid) / 2.0), fn((mid + b) / 2.0)
        evaluations += 2
        whole = simpson(a, b, fa, fm, fb)
        refined = simpson(a, mid, fa, fl, fm) + simpson(mid, b, fm, fr, fb)
        estimate = refined + (refined - whole) / 15.0
        local_error = abs(refined - whole) / 15.0
        total += estimate
        error += local_error
        heapq.heappush(heap, (-local_error, len(heap) + evaluations, (a, b, fa, fl, fm, fr, fb)))

    for index in range(panels):
        a = lo + index * width
        b = hi if index == panels - 1 else a + width
        fa, fm, fb = fn(a), fn((a + b) / 2.0), fn(b)
        evaluations += 3
        push(a, b, fa, fm, fb)

    while heap and error > tol and evaluations < max_evaluations:
        neg_error, _, (a, b, fa, fl, fm, fr, fb) = heapq.heappop(heap)
        mid = (a + b) / 2.0
        whole = simpson(a, mid, fa, fl, fm) + simpson(mid, b, fm, fr, fb)
        # Rimuove il contributo dell'intervallo prima di sostituirlo con le meta.
        total -= whole + (whole - simpson(a, b, fa, fm, fb)) / 15.0
        error += neg_error
        push(a, mid, fa, fl, fm)
        push(mid, b, fm, fr, fb)
    return total


def naive_type_i_error(
    *,
    total_units: int,
    mean_obs_per_unit: float,
    icc: float,
    alpha: float,
    groups: int = 2,
    one_sided: bool = False,
) -> NaiveFalsePositiveRate:
    """Alpha effettiva di un test che tratta osservazioni annidate come indipendenti."""

    if groups < 2:
        raise PowerComputationError("groups deve essere >= 2")
    if one_sided and groups != 2:
        raise PowerComputationError("il test unilaterale e definito solo per due gruppi")
    if total_units < groups:
        raise PowerComputationError("servono almeno tante unita quanti gruppi")
    if mean_obs_per_unit < 1.0:
        raise PowerComputationError("mean_obs_per_unit deve essere >= 1")
    if not 0.0 <= icc <= 1.0:
        raise PowerComputationError("icc deve stare in [0, 1]")
    if not 0.0 < alpha < 1.0:
        raise PowerComputationError("alpha deve stare in (0, 1)")

    k, m, rho = float(total_units), float(mean_obs_per_unit), float(icc)
    d1 = float(groups - 1)
    a = k - groups
    b = k * (m - 1.0)
    nu = a + b
    if nu <= 0.0:
        raise PowerComputationError("gradi di liberta naive non positivi")
    deff = 1.0 + (m - 1.0) * rho
    # Valore critico naive sulla scala F: t^2 per l'unilaterale a due gruppi.
    crit = dist.t_ppf(nu, 1.0 - alpha) ** 2 if one_sided else dist.f_ppf(d1, nu, 1.0 - alpha)

    upper = 1.0 - dist.f_cdf(d1, nu, crit)
    lo = crit * (1.0 - rho) / deff
    if rho == 0.0 or b == 0.0 or lo >= crit:
        two_sided_rate = upper
    elif a == 0.0:
        # Una sola unita per gruppo: R degenere in 0, g(R) = 1 - rho.
        two_sided_rate = 1.0 - dist.f_cdf(d1, nu, lo)
    else:
        p, q = a / 2.0, b / 2.0

        def integrand(s: float) -> float:
            f = s * s
            if f <= 0.0:
                return 0.0
            x = (deff * f / crit - (1.0 - rho)) / (m * rho)
            if x <= 0.0:
                return 0.0
            weight = 1.0 if x >= 1.0 else dist.beta_inc(p, q, x)
            if weight == 0.0:
                return 0.0
            return weight * 2.0 * s * math.exp(_log_f_pdf(d1, nu, f))

        middle = _adaptive_simpson(integrand, math.sqrt(lo), math.sqrt(crit), tol=1e-10)
        two_sided_rate = upper + middle

    rate = 0.5 * two_sided_rate if one_sided else two_sided_rate
    rate = max(0.0, min(1.0, rate))
    return NaiveFalsePositiveRate(
        alpha_nominal=alpha,
        alpha_actual=rate,
        inflation_factor=rate / alpha,
        icc=rho,
        design_effect=deff,
        total_units=total_units,
        mean_obs_per_unit=m,
        groups=groups,
        one_sided=one_sided,
        naive_df=nu,
        exact_for_balanced_design=float(m).is_integer(),
    )


def naive_type_i_error_grid(
    *,
    total_units: int,
    mean_obs_per_unit: float,
    alpha: float,
    groups: int = 2,
    one_sided: bool = False,
    iccs: tuple[float, ...] = DEFAULT_ICC_GRID,
) -> tuple[NaiveFalsePositiveRate, ...]:
    """Sensitivity sull'ICC: l'ICC reale e raramente nota a priori."""

    return tuple(
        naive_type_i_error(
            total_units=total_units,
            mean_obs_per_unit=mean_obs_per_unit,
            icc=icc,
            alpha=alpha,
            groups=groups,
            one_sided=one_sided,
        )
        for icc in iccs
    )


def pseudoreplication_risk(request: PseudoreplicationRiskInput) -> PseudoreplicationRiskResult:
    """Alpha effettiva dell'analisi naive all'ICC dichiarata e sulla griglia."""

    one_sided = request.tail is Tail.ONE_SIDED

    def rate(icc: float) -> NaiveFalsePositiveRate:
        return naive_type_i_error(
            total_units=request.total_units,
            mean_obs_per_unit=request.mean_obs_per_unit,
            icc=icc,
            alpha=request.alpha,
            groups=request.groups,
            one_sided=one_sided,
        )

    grid = sorted({*request.icc_grid, *(() if request.icc is None else (request.icc,))})
    rows = {icc: rate(icc) for icc in grid}
    declared = rows[request.icc] if request.icc is not None else None
    reference = next(iter(rows.values()))
    exact = reference.exact_for_balanced_design
    caveats = [
        "Modello: intercetto casuale per unita, normalita, varianza omogenea, nessun "
        "effetto (H0); analisi naive = t a due campioni o ANOVA a una via sulle "
        "osservazioni.",
        "Diagnostica di rischio: non misura la validita dell'analisi eseguita e non "
        "trasforma osservazioni in unita sperimentali indipendenti.",
    ]
    if request.icc is None:
        caveats.append("ICC non dichiarata: riportata solo la sensitivity, mai ICC = 0.")
    if not exact:
        caveats.append("Osservazioni per unita non intere: approssimazione bilanciata con m medio.")
    return PseudoreplicationRiskResult(
        alpha_nominal=request.alpha,
        declared=(
            NaiveFalsePositiveRow(icc=declared.icc, alpha_actual=declared.alpha_actual)
            if declared is not None
            else None
        ),
        sensitivity=tuple(
            NaiveFalsePositiveRow(icc=icc, alpha_actual=row.alpha_actual)
            for icc, row in rows.items()
        ),
        naive_df=reference.naive_df,
        method=("EXACT_BALANCED_RANDOM_INTERCEPT" if exact else "BALANCED_APPROXIMATION_MEAN_M"),
        caveats=tuple(caveats),
    )


__all__ = [
    "DEFAULT_ICC_GRID",
    "NaiveFalsePositiveRate",
    "naive_type_i_error",
    "naive_type_i_error_grid",
    "pseudoreplication_risk",
]
