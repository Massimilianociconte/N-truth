"""Calcoli di potenza a priori per famiglia, stile G*Power 3.1.

Ogni funzione ``power_*`` calcola la potenza per un N dato; ogni funzione
``solve_n_*`` inverte il problema (minimo N intero con potenza >= target,
arrotondato verso l'alto con vincoli di allocazione/bilanciamento, come
G*Power: la potenza effettiva non e mai inferiore alla richiesta).

Le formule sono verificate contro il manuale G*Power 3.1 e Faul et al.
2007 (doi:10.3758/BF03193146) / 2009 (doi:10.3758/BRM.41.4.1149).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from ntruth.power import distributions as dist


@dataclass(frozen=True, slots=True)
class PowerResult:
    """Esito del calcolo di potenza per un N dato."""

    power: float
    critical_value: float
    noncentrality: float
    df: tuple[float, ...]
    actual_alpha: float | None = None


@dataclass(frozen=True, slots=True)
class SolveResult:
    """Minimo N intero che raggiunge la potenza target."""

    n_per_group: tuple[int, ...]
    n_total: int
    achieved_power: float
    critical_value: float
    noncentrality: float
    df: tuple[float, ...]
    actual_alpha: float | None = None


class PowerComputationError(ValueError):
    """Errore fail-closed del calcolatore di potenza."""


def _check_alpha_power(alpha: float, target_power: float) -> None:
    if not 0.0 < alpha < 1.0:
        raise PowerComputationError(f"alpha deve stare in (0, 1); ricevuto {alpha!r}")
    if not 0.0 < target_power < 1.0:
        raise PowerComputationError(f"target_power in (0, 1); ricevuto {target_power!r}")


def _solve_bisection(
    sufficient: Callable[[int], bool], start: int, maximum: int = 10_000_000
) -> int:
    """Minimo N >= start con sufficient(N) vera; fail-closed oltre maximum."""

    low = start
    if sufficient(low):
        return low
    high = max(low + 1, 2)
    while not sufficient(high):
        low = high
        high *= 2
        if high > maximum:
            raise PowerComputationError("potenza target non raggiungibile entro il massimo")
    while high - low > 1:
        mid = (low + high) // 2
        if sufficient(mid):
            high = mid
        else:
            low = mid
    return high


def solve_minimum_n(
    sufficient: Callable[[int], bool], start: int, maximum: int = 10_000_000
) -> int:
    """Minimo N >= start con sufficient(N) vera; fail-closed oltre maximum."""

    return _solve_bisection(sufficient, start, maximum)


# ---------------- t test ----------------


def t_two_sample_delta(d: float, n1: int, n2: int) -> float:
    """delta = d*sqrt(n1*n2/(n1+n2)) (manuale G*Power, t indipendenti)."""

    if d <= 0:
        raise PowerComputationError(f"d deve essere > 0; ricevuto {d!r}")
    if n1 < 2 or n2 < 2:
        raise PowerComputationError(f"n1, n2 >= 2; ricevuto {n1!r}, {n2!r}")
    return d * math.sqrt(n1 * n2 / (n1 + n2))


def power_t_two_sample(n1: int, n2: int, d: float, alpha: float, two_sided: bool) -> PowerResult:
    """Potenza t a due gruppi via t noncentrale, df = n1+n2-2."""

    delta = t_two_sample_delta(d, n1, n2)
    df = float(n1 + n2 - 2)
    power, crit = dist.t_power_from_delta(df, delta, alpha, two_sided)
    return PowerResult(power=power, critical_value=crit, noncentrality=delta, df=(df,))


def _allocated_pair(n1: int, allocation_ratio: float) -> tuple[int, int]:
    """Coppia G*Power: n2 = ceil(ratio * n1), entrambi >= 2.

    Con ratio = 1 i gruppi sono sempre bilanciati; con ratio != 1 il rapporto
    dichiarato e rispettato arrotondando per eccesso il secondo gruppo.
    """

    return n1, max(2, math.ceil(allocation_ratio * n1 - 1e-9))


def solve_n_t_two_sample(
    d: float,
    alpha: float,
    target_power: float,
    two_sided: bool,
    allocation_ratio: float = 1.0,
) -> SolveResult:
    """Minimo n1 con n2 = ceil(ratio * n1) e potenza >= target (G*Power 3.1).

    La ricerca avviene su n1: la potenza e monotona in n1 perche n2 non
    decresce, e la coppia restituita rispetta sempre il rapporto dichiarato
    (bilanciata se ratio = 1).
    """

    _check_alpha_power(alpha, target_power)
    if d <= 0:
        raise PowerComputationError(f"d deve essere > 0; ricevuto {d!r}")
    if allocation_ratio <= 0:
        raise PowerComputationError("allocation_ratio deve essere > 0")

    def sufficient(n1: int) -> bool:
        first, second = _allocated_pair(n1, allocation_ratio)
        return power_t_two_sample(first, second, d, alpha, two_sided).power >= target_power

    n1, n2 = _allocated_pair(_solve_bisection(sufficient, 2), allocation_ratio)
    result = power_t_two_sample(n1, n2, d, alpha, two_sided)
    return SolveResult(
        n_per_group=(n1, n2),
        n_total=n1 + n2,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


def power_t_one_sample(n: int, d: float, alpha: float, two_sided: bool) -> PowerResult:
    """Potenza t a un campione / paired: delta = d*sqrt(N), df = N-1."""

    if d <= 0:
        raise PowerComputationError(f"d deve essere > 0; ricevuto {d!r}")
    if n < 2:
        raise PowerComputationError(f"n >= 2; ricevuto {n!r}")
    delta = d * math.sqrt(n)
    df = float(n - 1)
    power, crit = dist.t_power_from_delta(df, delta, alpha, two_sided)
    return PowerResult(power=power, critical_value=crit, noncentrality=delta, df=(df,))


def solve_n_t_one_sample(
    d: float, alpha: float, target_power: float, two_sided: bool
) -> SolveResult:
    """Minimo N per t a un campione o paired (N = numero di coppie)."""

    _check_alpha_power(alpha, target_power)
    if d <= 0:
        raise PowerComputationError(f"d deve essere > 0; ricevuto {d!r}")

    def sufficient(n: int) -> bool:
        return power_t_one_sample(n, d, alpha, two_sided).power >= target_power

    n = _solve_bisection(sufficient, 2)
    result = power_t_one_sample(n, d, alpha, two_sided)
    return SolveResult(
        n_per_group=(n,),
        n_total=n,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


# ---------------- ANOVA / regressione / chi2 (F / chi2 noncentrali) ----------------


def power_anova(n_total: int, n_groups: int, f: float, alpha: float) -> PowerResult:
    """Potenza ANOVA fixed: lambda = N*f^2, df1 = k-1, df2 = N-k."""

    if f <= 0:
        raise PowerComputationError(f"f deve essere > 0; ricevuto {f!r}")
    if n_total <= n_groups:
        raise PowerComputationError("N deve superare il numero di gruppi")
    lam = n_total * f * f
    df1, df2 = float(n_groups - 1), float(n_total - n_groups)
    power, crit = dist.f_power_from_lambda(df1, df2, lam, alpha)
    return PowerResult(power=power, critical_value=crit, noncentrality=lam, df=(df1, df2))


def solve_n_anova(n_groups: int, f: float, alpha: float, target_power: float) -> SolveResult:
    """Minimo N bilanciato (multiplo di k) per ANOVA one-way fixed."""

    _check_alpha_power(alpha, target_power)
    if f <= 0:
        raise PowerComputationError(f"f deve essere > 0; ricevuto {f!r}")
    if n_groups < 2:
        raise PowerComputationError("ANOVA richiede almeno 2 gruppi")

    def sufficient(n: int) -> bool:
        return power_anova(n, n_groups, f, alpha).power >= target_power

    per_group = 2
    while not sufficient(per_group * n_groups):
        per_group += 1
        if per_group * n_groups > 10_000_000:
            raise PowerComputationError("potenza target non raggiungibile entro il massimo")
    # Bisezione sul numero per gruppo per mantenere il bilanciamento.
    low, high = 2, per_group
    while high - low > 1:
        mid = (low + high) // 2
        if sufficient(mid * n_groups):
            high = mid
        else:
            low = mid
    total = high * n_groups
    result = power_anova(total, n_groups, f, alpha)
    return SolveResult(
        n_per_group=tuple([high] * n_groups),
        n_total=total,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


def power_anova_factorial(
    n_total: int, df1: int, n_cells: int, f: float, alpha: float
) -> PowerResult:
    """Potenza effetto ANOVA fattoriale: lambda = N*f^2, df2 = N - celle."""

    if f <= 0:
        raise PowerComputationError(f"f deve essere > 0; ricevuto {f!r}")
    if n_total <= n_cells:
        raise PowerComputationError("N deve superare il numero di celle")
    lam = n_total * f * f
    df2 = float(n_total - n_cells)
    power, crit = dist.f_power_from_lambda(float(df1), df2, lam, alpha)
    return PowerResult(power=power, critical_value=crit, noncentrality=lam, df=(float(df1), df2))


def power_regression_omnibus(
    n_total: int, n_predictors: int, f2: float, alpha: float
) -> PowerResult:
    """Potenza omnibus R2: lambda = N*f2, df1 = p, df2 = N-p-1 (Faul 2009)."""

    if f2 <= 0:
        raise PowerComputationError(f"f2 deve essere > 0; ricevuto {f2!r}")
    if n_total <= n_predictors + 1:
        raise PowerComputationError("N deve superare p+1")
    lam = n_total * f2
    df1, df2 = float(n_predictors), float(n_total - n_predictors - 1)
    power, crit = dist.f_power_from_lambda(df1, df2, lam, alpha)
    return PowerResult(power=power, critical_value=crit, noncentrality=lam, df=(df1, df2))


def solve_n_regression_omnibus(
    n_predictors: int, f2: float, alpha: float, target_power: float
) -> SolveResult:
    """Minimo N per regressione omnibus fixed."""

    _check_alpha_power(alpha, target_power)

    def sufficient(n: int) -> bool:
        return power_regression_omnibus(n, n_predictors, f2, alpha).power >= target_power

    n = _solve_bisection(sufficient, n_predictors + 2)
    result = power_regression_omnibus(n, n_predictors, f2, alpha)
    return SolveResult(
        n_per_group=(n,),
        n_total=n,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


def power_regression_increase(
    n_total: int, n_predictors_total: int, n_tested: int, f2: float, alpha: float
) -> PowerResult:
    """Potenza incremento R2: df1 = q testati, df2 = N-p-1 (Faul 2009)."""

    if f2 <= 0:
        raise PowerComputationError(f"f2 deve essere > 0; ricevuto {f2!r}")
    if n_total <= n_predictors_total + 1:
        raise PowerComputationError("N deve superare p+1")
    lam = n_total * f2
    df1, df2 = float(n_tested), float(n_total - n_predictors_total - 1)
    power, crit = dist.f_power_from_lambda(df1, df2, lam, alpha)
    return PowerResult(power=power, critical_value=crit, noncentrality=lam, df=(df1, df2))


def power_chi2(n_total: int, w: float, df: int, alpha: float) -> PowerResult:
    """Potenza chi2: lambda = N*w^2 (Cohen cap. 7)."""

    if w <= 0:
        raise PowerComputationError(f"w deve essere > 0; ricevuto {w!r}")
    lam = n_total * w * w
    power, crit = dist.chi2_power_from_lambda(float(df), lam, alpha)
    return PowerResult(power=power, critical_value=crit, noncentrality=lam, df=(float(df),))


def solve_n_chi2(w: float, df: int, alpha: float, target_power: float) -> SolveResult:
    """Minimo N per test chi2 asintotico."""

    _check_alpha_power(alpha, target_power)

    def sufficient(n: int) -> bool:
        return power_chi2(n, w, df, alpha).power >= target_power

    n = _solve_bisection(sufficient, max(2, df + 1))
    result = power_chi2(n, w, df, alpha)
    return SolveResult(
        n_per_group=(n,),
        n_total=n,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


# ---------------- Test esatti: binomiale / proporzioni ----------------


def _binom_pmf(n: int, p: float) -> list[float]:
    """PMF binomiale per ricorrenza stabile (nessun overflow da comb)."""

    probs = [0.0] * (n + 1)
    probs[0] = (1.0 - p) ** n
    ratio = p / (1.0 - p) if p < 1.0 else float("inf")
    for k in range(1, n + 1):
        probs[k] = probs[k - 1] * (n - k + 1) / k * ratio
    return probs


def _binom_sf_tail(probs: list[float], lo: int, hi: int) -> float:
    return sum(probs[lo : hi + 1])


def power_binomial_exact(
    n: int, p0: float, p1: float, alpha: float, two_sided: bool
) -> PowerResult:
    """Potenza esatta per enumerazione Bin(N, p); default centrale alpha/2."""

    if not 0.0 < p0 < 1.0:
        raise PowerComputationError(f"p0 deve stare in (0, 1); ricevuto {p0!r}")
    if not 0.0 < p1 < 1.0:
        raise PowerComputationError(f"p1 deve stare in (0, 1); ricevuto {p1!r}")
    null = _binom_pmf(n, p0)
    alt = _binom_pmf(n, p1)
    if two_sided:
        lower = 0
        cumulative = 0.0
        while lower <= n and cumulative + null[lower] <= alpha / 2.0:
            cumulative += null[lower]
            lower += 1
        lower -= 1
        upper = n
        cumulative_u = 0.0
        while upper >= 0 and cumulative_u + null[upper] <= alpha / 2.0:
            cumulative_u += null[upper]
            upper -= 1
        upper += 1
        actual_alpha = _binom_sf_tail(null, 0, lower) + _binom_sf_tail(null, upper, n)
        power = _binom_sf_tail(alt, 0, lower) + _binom_sf_tail(alt, upper, n)
        crit = float(upper)
    elif p1 > p0:
        threshold = n + 1
        cumulative = 0.0
        for k in range(n, -1, -1):
            if cumulative + null[k] > alpha:
                break
            cumulative += null[k]
            threshold = k
        actual_alpha = _binom_sf_tail(null, threshold, n)
        power = _binom_sf_tail(alt, threshold, n)
        crit = float(threshold)
    else:
        threshold = -1
        cumulative = 0.0
        for k in range(n + 1):
            if cumulative + null[k] > alpha:
                break
            cumulative += null[k]
            threshold = k
        actual_alpha = _binom_sf_tail(null, 0, threshold)
        power = _binom_sf_tail(alt, 0, threshold)
        crit = float(threshold)
    return PowerResult(
        power=max(0.0, min(1.0, power)),
        critical_value=crit,
        noncentrality=abs(p1 - p0),
        df=(),
        actual_alpha=actual_alpha,
    )


#: Oltre questa soglia la scansione lineare costerebbe troppo; la potenza
#: esatta resta a dente di sega e il planner lo dichiara comunque.
BINOMIAL_LINEAR_SCAN_LIMIT = 2000
#: Finestra per la stabilita: potenza >= target per ogni N' in [N, N + finestra).
BINOMIAL_STABILITY_WINDOW = 30


def solve_n_binomial_exact(
    p0: float, p1: float, alpha: float, target_power: float, two_sided: bool
) -> SolveResult:
    """Minimo N esatto per il test binomiale (actual alpha <= nominale).

    La potenza esatta non e monotona in N (dente di sega, Chernick & Liu
    2002): la bisezione trova solo un N sufficiente, quindi il minimo viene
    cercato per scansione lineare fino a quel limite superiore.
    """

    _check_alpha_power(alpha, target_power)

    def sufficient(n: int) -> bool:
        return power_binomial_exact(n, p0, p1, alpha, two_sided).power >= target_power

    n = _solve_bisection(sufficient, 2, maximum=100_000)
    if n <= BINOMIAL_LINEAR_SCAN_LIMIT:
        n = next(candidate for candidate in range(2, n + 1) if sufficient(candidate))
    result = power_binomial_exact(n, p0, p1, alpha, two_sided)
    return SolveResult(
        n_per_group=(n,),
        n_total=n,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
        actual_alpha=result.actual_alpha,
    )


def binomial_stable_n(
    p0: float,
    p1: float,
    alpha: float,
    target_power: float,
    two_sided: bool,
    *,
    start: int,
    window: int = BINOMIAL_STABILITY_WINDOW,
    maximum: int = BINOMIAL_LINEAR_SCAN_LIMIT,
) -> int | None:
    """Minimo N >= start con potenza >= target per ogni N' in [N, N + window).

    Utile quando N effettivo puo crescere (unita aggiuntive): sopra il minimo
    la potenza esatta puo ricadere sotto il target. None oltre ``maximum``.
    """

    candidate = start
    while candidate <= maximum:
        failing = next(
            (
                size
                for size in range(candidate, candidate + window)
                if power_binomial_exact(size, p0, p1, alpha, two_sided).power < target_power
            ),
            None,
        )
        if failing is None:
            return candidate
        candidate = failing + 1
    return None


def power_z_two_proportions(
    n1: int, n2: int, p1: float, p2: float, alpha: float, two_sided: bool
) -> PowerResult:
    """Potenza z a due proporzioni (pooled sotto H0, unpooled sotto H1)."""

    if n1 < 2 or n2 < 2:
        raise PowerComputationError("n1, n2 >= 2")
    pooled = (n1 * p1 + n2 * p2) / (n1 + n2)
    se0 = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2))
    se1 = math.sqrt(p1 * (1.0 - p1) / n1 + p2 * (1.0 - p2) / n2)
    if se0 <= 0 or se1 <= 0:
        raise PowerComputationError("proporzioni degeneri per l'approssimazione z")
    diff = abs(p2 - p1)
    if two_sided:
        crit = dist.norm_ppf(1.0 - alpha / 2.0)
        power = dist.norm_cdf((diff - crit * se0) / se1) + dist.norm_cdf((-diff - crit * se0) / se1)
    else:
        crit = dist.norm_ppf(1.0 - alpha)
        power = 1.0 - dist.norm_cdf((crit * se0 - diff) / se1)
    return PowerResult(
        power=max(0.0, min(1.0, power)),
        critical_value=crit,
        noncentrality=diff / se1,
        df=(),
    )


def solve_n_z_two_proportions(
    p1: float,
    p2: float,
    alpha: float,
    target_power: float,
    two_sided: bool,
    allocation_ratio: float = 1.0,
) -> SolveResult:
    """Minimo n1 con n2 = ceil(ratio * n1) per z a due proporzioni."""

    _check_alpha_power(alpha, target_power)
    if allocation_ratio <= 0:
        raise PowerComputationError("allocation_ratio deve essere > 0")

    def sufficient(n1: int) -> bool:
        first, second = _allocated_pair(n1, allocation_ratio)
        return power_z_two_proportions(first, second, p1, p2, alpha, two_sided).power >= (
            target_power
        )

    n1, n2 = _allocated_pair(_solve_bisection(sufficient, 2), allocation_ratio)
    result = power_z_two_proportions(n1, n2, p1, p2, alpha, two_sided)
    return SolveResult(
        n_per_group=(n1, n2),
        n_total=n1 + n2,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


def fisher_exact_validation(
    n1: int, n2: int, p1: float, p2: float, alpha: float
) -> dict[str, float]:
    """Validazione esatta incondizionata (Barnard/Fisher) per piccoli N.

    Enumera tutte le tabelle (x1, x2) con pesi Bin(x1;n1,p1)*Bin(x2;n2,p2)
    e rigetta sulle code della statistica z non corretta. Solo per N
    piccoli (n1*n2 <= 3600); sopra, fail-closed con metodo normale.
    """

    if n1 * n2 > 3600:
        raise PowerComputationError(
            "enumerazione Fisher valida solo per n1*n2 <= 3600; usare z asintotico"
        )
    grid1 = _binom_pmf(n1, p1)
    grid2 = _binom_pmf(n2, p2)
    null1 = _binom_pmf(n1, (n1 * p1 + n2 * p2) / (n1 + n2))
    null2 = _binom_pmf(n2, (n1 * p1 + n2 * p2) / (n1 + n2))
    pooled = (n1 * p1 + n2 * p2) / (n1 + n2)
    se0 = math.sqrt(max(1e-12, pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2)))
    crit = dist.norm_ppf(1.0 - alpha / 2.0)
    power = 0.0
    actual = 0.0
    for x1 in range(n1 + 1):
        for x2 in range(n2 + 1):
            z = abs(x1 / n1 - x2 / n2) / se0
            if z >= crit:
                power += grid1[x1] * grid2[x2]
                actual += null1[x1] * null2[x2]
    return {"power": power, "actual_alpha": actual, "crit_z": crit}


def power_mcnemar(
    n_pairs: int, p_discordant: float, odds_ratio: float, alpha: float
) -> PowerResult:
    """Potenza McNemar bilaterale, approssimazione normale di Connor (1987).

    psi = quota di coppie discordanti, delta = p12 - p21:
    z_beta = (|delta| sqrt(N) - z_{1-alpha/2} sqrt(psi)) / sqrt(psi - delta^2)
    (Biometrics 43:207-211). La varianza sotto H0 (psi) e quella sotto H1
    (psi - delta^2) differiscono: usarne una sola sovrastima la potenza.
    """

    if n_pairs < 1:
        raise PowerComputationError("n_pairs deve essere >= 1")
    if not 0.0 < p_discordant < 1.0:
        raise PowerComputationError("p_discordant deve stare in (0, 1)")
    if odds_ratio <= 0:
        raise PowerComputationError("odds_ratio deve essere > 0")
    p12 = p_discordant * odds_ratio / (1.0 + odds_ratio)
    p21 = p_discordant / (1.0 + odds_ratio)
    diff = abs(p12 - p21)
    se_alternative = math.sqrt(p_discordant - diff * diff)
    crit = dist.norm_ppf(1.0 - alpha / 2.0)
    root_n = math.sqrt(n_pairs)
    upper = (diff * root_n - crit * math.sqrt(p_discordant)) / se_alternative
    lower = (-diff * root_n - crit * math.sqrt(p_discordant)) / se_alternative
    power = dist.norm_cdf(upper) + dist.norm_cdf(lower)
    return PowerResult(
        power=max(0.0, min(1.0, power)),
        critical_value=crit,
        noncentrality=diff * root_n / se_alternative,
        df=(),
    )


def solve_n_logistic_hsieh(
    odds_ratio: float,
    p1: float,
    alpha: float,
    target_power: float,
    two_sided: bool,
    r2_other: float = 0.0,
) -> SolveResult:
    """N per regressione logistica, correzione Hsieh et al. 1998.

    Approssimazione large-sample (Demidenko/Whittemore per verifica):
    N = (z_{1-a} + z_{potenza})^2 / (p1(1-p1) beta^2 (1-R2)).
    """

    _check_alpha_power(alpha, target_power)
    if odds_ratio <= 0:
        raise PowerComputationError("odds_ratio deve essere > 0")
    if not 0.0 < p1 < 1.0:
        raise PowerComputationError("p1 deve stare in (0, 1)")
    if not 0.0 <= r2_other < 1.0:
        raise PowerComputationError("r2_other deve stare in [0, 1)")
    beta = math.log(odds_ratio)
    if beta == 0.0:
        raise PowerComputationError("odds_ratio = 1: nessun effetto da pianificare")
    z_alpha = dist.norm_ppf(1.0 - alpha / 2.0) if two_sided else dist.norm_ppf(1.0 - alpha)
    z_beta = dist.norm_ppf(target_power)
    n_raw = ((z_alpha + z_beta) ** 2) / (p1 * (1.0 - p1) * beta * beta * (1.0 - r2_other))
    n = max(10, math.ceil(n_raw))
    noncentrality = abs(beta) * math.sqrt(n * p1 * (1.0 - p1) * (1.0 - r2_other))
    return SolveResult(
        n_per_group=(n,),
        n_total=n,
        # Potenza dell'N arrotondato sotto la stessa approssimazione (>= target).
        achieved_power=min(1.0, dist.norm_cdf(noncentrality - z_alpha)),
        critical_value=z_alpha,
        noncentrality=noncentrality,
        df=(),
    )


def solve_n_poisson_rate(
    rate_ratio: float,
    base_rate: float,
    exposure: float,
    alpha: float,
    target_power: float,
    two_sided: bool,
    allocation_ratio: float = 1.0,
) -> SolveResult:
    """N per confronto di tassi Poisson via approssimazione normale su log(RR)."""

    _check_alpha_power(alpha, target_power)
    if rate_ratio <= 0 or base_rate <= 0 or exposure <= 0:
        raise PowerComputationError("rate_ratio, base_rate, exposure devono essere > 0")
    log_rr = math.log(rate_ratio)
    if log_rr == 0.0:
        raise PowerComputationError("rate_ratio = 1: nessun effetto da pianificare")
    z_alpha = dist.norm_ppf(1.0 - alpha / 2.0) if two_sided else dist.norm_ppf(1.0 - alpha)
    z_beta = dist.norm_ppf(target_power)
    if allocation_ratio <= 0:
        raise PowerComputationError("allocation_ratio deve essere > 0")
    mu0 = base_rate * exposure
    mu1 = base_rate * rate_ratio * exposure
    # Var[log RR] = 1/(n1 mu0) + 1/(n2 mu1) con n2 = ratio * n1: la varianza
    # per unita del gruppo 1 dipende dall'allocazione (ratio < 1 la aumenta).
    var_per_n1 = 1.0 / mu0 + 1.0 / (allocation_ratio * mu1)
    n_raw = ((z_alpha + z_beta) ** 2) * var_per_n1 / (log_rr**2)
    n1, n2 = _allocated_pair(max(2, math.ceil(n_raw)), allocation_ratio)
    noncentrality = abs(log_rr) / math.sqrt(1.0 / (n1 * mu0) + 1.0 / (n2 * mu1))
    return SolveResult(
        n_per_group=(n1, n2),
        n_total=n1 + n2,
        achieved_power=min(1.0, dist.norm_cdf(noncentrality - z_alpha)),
        critical_value=z_alpha,
        noncentrality=noncentrality,
        df=(),
    )


# ---------------- Aggiustamenti: design effect, dropout, molteplicita ----------------


def design_effect(mean_cluster_size: float, icc: float) -> float:
    """DE = 1 + (m-1)*rho; diagnostica di varianza, mai ridefinizione di EU."""

    if mean_cluster_size <= 1.0:
        raise PowerComputationError("mean_cluster_size deve essere > 1")
    if not 0.0 <= icc <= 1.0:
        raise PowerComputationError("icc deve stare in [0, 1]")
    return 1.0 + (mean_cluster_size - 1.0) * icc


def effective_n_diagnostic(n_total: float, deff: float) -> float:
    """N efficace diagnostico N/DE; non e un conteggio di EU.

    ``n_total`` e un numero di osservazioni (per esempio EU x osservazioni per
    EU): dividere un numero di EU per DE non ha significato.
    """

    if deff <= 0:
        raise PowerComputationError("design effect deve essere > 0")
    return n_total / deff


def clustered_n_diagnostic(n_independent: int, deff: float) -> int:
    """N osservato per preservare potenza sotto clustering (diagnostica)."""

    if deff <= 0:
        raise PowerComputationError("design effect deve essere > 0")
    return math.ceil(n_independent * deff)


def apply_dropout(n_total: int, dropout_rate: float) -> int:
    """Gonfia N per dropout atteso: ceil(N/(1-tasso))."""

    if not 0.0 <= dropout_rate < 1.0:
        raise PowerComputationError("dropout_rate deve stare in [0, 1)")
    if n_total < 1:
        raise PowerComputationError("n_total deve essere >= 1")
    return math.ceil(n_total / (1.0 - dropout_rate))


def apply_bonferroni(alpha: float, multiplicity_m: int) -> float:
    """Alpha corretta Bonferroni; m deve essere dichiarato esplicitamente."""

    if multiplicity_m < 1:
        raise PowerComputationError("multiplicity_m deve essere >= 1")
    return alpha / multiplicity_m


__all__ = [
    "PowerComputationError",
    "PowerResult",
    "SolveResult",
    "apply_bonferroni",
    "apply_dropout",
    "binomial_stable_n",
    "clustered_n_diagnostic",
    "design_effect",
    "effective_n_diagnostic",
    "fisher_exact_validation",
    "power_anova",
    "power_anova_factorial",
    "power_binomial_exact",
    "power_chi2",
    "power_mcnemar",
    "power_regression_increase",
    "power_regression_omnibus",
    "power_t_one_sample",
    "power_t_two_sample",
    "power_z_two_proportions",
    "solve_minimum_n",
    "solve_n_anova",
    "solve_n_binomial_exact",
    "solve_n_chi2",
    "solve_n_logistic_hsieh",
    "solve_n_poisson_rate",
    "solve_n_regression_omnibus",
    "solve_n_t_one_sample",
    "solve_n_t_two_sample",
    "solve_n_z_two_proportions",
    "t_two_sample_delta",
]
