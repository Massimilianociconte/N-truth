"""Distribuzioni centrali/noncentrali in sola stdlib, deterministiche.

Formule verificate contro G*Power 3.1 (Faul et al. 2007/2009, manuale HHU):
sotto H0 distribuzioni centrali esatte; sotto H1 noncentrali della stessa
famiglia (miste di Poisson sommate dalla moda per chi2/F, senza
approssimazione normale; quadratura deterministica su quantili chi2 per la
t noncentrale, tolleranza ~5e-4). Nessun RNG, nessun seed globale: ogni
funzione e pura e bit-riproducibile.

Riferimenti:
- https://www.psychologie.hhu.de/en/arbeitsgruppen/allgemeine-psychologie-und-arbeitspsychologie/gpower
- Faul et al. 2007, doi:10.3758/BF03193146
- Faul et al. 2009, doi:10.3758/BRM.41.4.1149
"""

from __future__ import annotations

import math
from collections.abc import Callable
from statistics import NormalDist

_STD_NORMAL = NormalDist()

# Cache deterministica dei quantili chi2 per la quadratura t-noncentrale:
# chiave (df esatto, punti). Nessuno stato casuale.
_CHI2_QUANTILE_CACHE: dict[tuple[float, int], tuple[float, ...]] = {}


def norm_cdf(x: float) -> float:
    """CDF normale standard via erf (pura, monotona)."""

    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def norm_ppf(p: float) -> float:
    """Quantile normale standard; fail-closed fuori (0, 1)."""

    if not 0.0 < p < 1.0:
        raise ValueError(f"norm_ppf richiede p in (0, 1); ricevuto {p!r}")
    return _STD_NORMAL.inv_cdf(p)


def _gammainc_lower(a: float, x: float) -> float:
    """Gamma incompleta regolarizzata P(a, x); Numerical Recipes gser/gcf."""

    if a <= 0.0:
        raise ValueError(f"gammainc richiede a > 0; ricevuto {a!r}")
    if x < 0.0:
        raise ValueError(f"gammainc richiede x >= 0; ricevuto {x!r}")
    if x == 0.0:
        return 0.0
    if x < a + 1.0:
        term = 1.0 / a
        total = term
        n = 1
        while n <= 1000:
            term *= x / (a + n)
            total += term
            if abs(term) < abs(total) * 1e-14:
                break
            n += 1
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if abs(b) > tiny else 1.0 / tiny
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = c * d
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return max(0.0, min(1.0, 1.0 - q))


def _beta_cf(a: float, b: float, x: float) -> float:
    """Frazione continua per la beta incompleta (betacf, Numerical Recipes)."""

    tiny = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def beta_inc(a: float, b: float, x: float) -> float:
    """Beta incompleta regolarizzata I_x(a, b); fail-closed sui domini."""

    if a <= 0.0 or b <= 0.0:
        raise ValueError(f"beta_inc richiede a, b > 0; ricevuto {a!r}, {b!r}")
    if not 0.0 <= x <= 1.0:
        raise ValueError(f"beta_inc richiede x in [0, 1]; ricevuto {x!r}")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    # Fattore x^a (1-x)^b / B(a, b) in spazio logaritmico: con a, b grandi i
    # singoli fattori andrebbero in overflow/underflow pur avendo prodotto finito.
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        value = front / a * _beta_cf(a, b, x)
    else:
        value = 1.0 - front / b * _beta_cf(b, a, 1.0 - x)
    return max(0.0, min(1.0, value))


def chi2_cdf(df: float, x: float) -> float:
    """CDF chi2 centrale: P(df/2, x/2)."""

    if df <= 0.0:
        raise ValueError(f"chi2_cdf richiede df > 0; ricevuto {df!r}")
    if x <= 0.0:
        return 0.0
    return _gammainc_lower(df / 2.0, x / 2.0)


def f_cdf(df1: float, df2: float, f: float) -> float:
    """CDF F centrale via beta: I_w(df1/2, df2/2), w = df1*f/(df1*f+df2)."""

    if df1 <= 0.0 or df2 <= 0.0:
        raise ValueError(f"f_cdf richiede df > 0; ricevuto {df1!r}, {df2!r}")
    if f <= 0.0:
        return 0.0
    w = (df1 * f) / (df1 * f + df2)
    return beta_inc(df1 / 2.0, df2 / 2.0, w)


def t_cdf(df: float, t: float) -> float:
    """CDF t centrale via beta: x = df/(df+t^2)."""

    if df <= 0.0:
        raise ValueError(f"t_cdf richiede df > 0; ricevuto {df!r}")
    x = df / (df + t * t)
    ib = beta_inc(df / 2.0, 0.5, x)
    if t >= 0.0:
        return 1.0 - 0.5 * ib
    return 0.5 * ib


def _invert_cdf(cdf: Callable[[float], float], p: float, lo: float, hi: float) -> float:
    """Inversione per bisezione; la CDF deve essere monotona crescente."""

    func = cdf
    if not 0.0 < p < 1.0:
        raise ValueError(f"inversione richiede p in (0, 1); ricevuto {p!r}")
    low, high = lo, hi
    while func(high) < p:
        high = high * 2.0 + 1.0
        if high > 1e12:
            raise ValueError("inversione CDF: coda non convergente")
    for _ in range(200):
        mid = 0.5 * (low + high)
        if func(mid) < p:
            low = mid
        else:
            high = mid
        if high - low <= max(1e-12, abs(mid) * 1e-12):
            break
    return 0.5 * (low + high)


def chi2_ppf(df: float, p: float) -> float:
    """Quantile chi2 centrale con avvio Wilson-Hilferty + bisezione."""

    if df <= 0.0:
        raise ValueError(f"chi2_ppf richiede df > 0; ricevuto {df!r}")
    if not 0.0 < p < 1.0:
        raise ValueError(f"chi2_ppf richiede p in (0, 1); ricevuto {p!r}")
    z = _STD_NORMAL.inv_cdf(p)
    h = 2.0 / (9.0 * df)
    start = df * (1.0 - h + z * math.sqrt(h)) ** 3
    lo = max(1e-12, start * 0.25)
    hi = max(start * 2.0 + 1.0, df + 10.0 * math.sqrt(2.0 * df) + 1.0)
    low, high = lo, hi
    while chi2_cdf(df, high) < p:
        high = high * 2.0 + 1.0
    while chi2_cdf(df, low) > p:
        low = max(1e-12, low * 0.5)
    return _invert_cdf(lambda v: chi2_cdf(df, v), p, low, high)


def f_ppf(df1: float, df2: float, p: float) -> float:
    """Quantile F centrale per bisezione."""

    return _invert_cdf(lambda v: f_cdf(df1, df2, v), p, 1e-12, 1.0)


def t_ppf(df: float, p: float) -> float:
    """Quantile t centrale per bisezione (simmetrico, avvio normale)."""

    if not 0.0 < p < 1.0:
        raise ValueError(f"t_ppf richiede p in (0, 1); ricevuto {p!r}")
    if p == 0.5:
        return 0.0
    if p > 0.5:
        return _invert_cdf(lambda v: t_cdf(df, v), p, 0.0, 1.0)
    # Simmetria: F^-1(p) = -F^-1(1 - p); la bisezione richiede una CDF crescente.
    return -t_ppf(df, 1.0 - p)


#: Peso di Poisson sotto il quale un termine della mistura e trascurabile.
_POISSON_WEIGHT_FLOOR = 1e-17


def _poisson_mixture(half: float, term: Callable[[int], float]) -> float:
    """Somma ``sum_k Pois(k; half) * term(k)`` partendo dalla moda.

    I pesi sono calcolati in spazio logaritmico alla moda e propagati verso
    l'alto e verso il basso: nessun underflow di ``exp(-half)`` per lambda
    grandi e nessuna approssimazione normale. ``term`` e limitato in [0, 1].
    """

    mode = math.floor(half)
    mode_weight = math.exp(-half + mode * math.log(half) - math.lgamma(mode + 1.0))
    total = mode_weight * term(mode)
    weight = mode_weight
    k = mode
    while weight > _POISSON_WEIGHT_FLOOR:
        k += 1
        weight *= half / k
        total += weight * term(k)
    weight = mode_weight
    k = mode
    while k > 0 and weight > _POISSON_WEIGHT_FLOOR:
        weight *= k / half
        k -= 1
        total += weight * term(k)
    return total


def ncx2_cdf(df: float, noncentrality: float, x: float) -> float:
    """CDF chi2 noncentrale come mista di Poisson di chi2 centrali.

    P(X <= x) = sum_k e^{-l/2}(l/2)^k/k! * P_chi2(df+2k, x), sommata dalla
    moda della Poisson: esatta anche per lambda grandi.
    """

    if df <= 0.0:
        raise ValueError(f"ncx2_cdf richiede df > 0; ricevuto {df!r}")
    if noncentrality < 0.0:
        raise ValueError(f"ncx2 richiede lambda >= 0; ricevuto {noncentrality!r}")
    if x <= 0.0:
        return 0.0
    if noncentrality == 0.0:
        return chi2_cdf(df, x)
    total = _poisson_mixture(noncentrality / 2.0, lambda k: chi2_cdf(df + 2.0 * k, x))
    return max(0.0, min(1.0, total))


def ncf_cdf(df1: float, df2: float, noncentrality: float, f: float) -> float:
    """CDF F noncentrale come mista di Poisson di beta regolarizzate."""

    if df1 <= 0.0 or df2 <= 0.0:
        raise ValueError(f"ncf_cdf richiede df > 0; ricevuto {df1!r}, {df2!r}")
    if noncentrality < 0.0:
        raise ValueError(f"ncf richiede lambda >= 0; ricevuto {noncentrality!r}")
    if f <= 0.0:
        return 0.0
    if noncentrality == 0.0:
        return f_cdf(df1, df2, f)
    w = (df1 * f) / (df1 * f + df2)
    total = _poisson_mixture(noncentrality / 2.0, lambda k: beta_inc(df1 / 2.0 + k, df2 / 2.0, w))
    return max(0.0, min(1.0, total))


def _chi2_midpoint_quantiles(df: float, points: int) -> tuple[float, ...]:
    """Quantili chi2 ai midpoint di una griglia uniforme; cached, deterministici."""

    # La chiave e il df esatto: arrotondarlo farebbe riusare i quantili di un
    # df non intero (es. 17.3) per un altro df (17) con errore sulla CDF.
    key = (float(df), points)
    cached = _CHI2_QUANTILE_CACHE.get(key)
    if cached is not None:
        return cached
    values = tuple(chi2_ppf(df, (i + 0.5) / points) for i in range(points))
    _CHI2_QUANTILE_CACHE[key] = values
    return values


def nct_cdf(df: float, delta: float, t: float, points: int = 192) -> float:
    """CDF t noncentrale via quadratura deterministica sui quantili chi2.

    T = (Z + delta)/sqrt(V/df): si integra Phi(t*sqrt(v/df) - delta) su
    V ~ chi2(df) con regola del midpoint su griglia uniforme di
    probabilita. Tolleranza documentata ~5e-4 contro G*Power; la soglia
    critica resta sempre dalla t centrale esatta.
    """

    if df <= 0.0:
        raise ValueError(f"nct_cdf richiede df > 0; ricevuto {df!r}")
    if points < 32:
        raise ValueError(f"nct_cdf richiede points >= 32; ricevuto {points!r}")
    quantiles = _chi2_midpoint_quantiles(df, points)
    scale = 1.0 / points
    total = 0.0
    for v in quantiles:
        total += norm_cdf(t * math.sqrt(v / df) - delta)
    return max(0.0, min(1.0, total * scale))


def t_power_from_delta(
    df: float, delta: float, alpha: float, two_sided: bool, points: int = 192
) -> tuple[float, float]:
    """Potenza del t test da delta noncentrale; ritorna (potenza, t_crit)."""

    if two_sided:
        crit = t_ppf(df, 1.0 - alpha / 2.0)
        upper = 1.0 - nct_cdf(df, delta, crit, points)
        lower = nct_cdf(df, delta, -crit, points)
        return max(0.0, min(1.0, upper + lower)), crit
    crit = t_ppf(df, 1.0 - alpha)
    return max(0.0, min(1.0, 1.0 - nct_cdf(df, delta, crit, points))), crit


def f_power_from_lambda(
    df1: float, df2: float, noncentrality: float, alpha: float
) -> tuple[float, float]:
    """Potenza F da lambda noncentrale; ritorna (potenza, f_crit)."""

    crit = f_ppf(df1, df2, 1.0 - alpha)
    power = 1.0 - ncf_cdf(df1, df2, noncentrality, crit)
    return max(0.0, min(1.0, power)), crit


def chi2_power_from_lambda(df: float, noncentrality: float, alpha: float) -> tuple[float, float]:
    """Potenza chi2 da lambda noncentrale; ritorna (potenza, chi2_crit)."""

    crit = chi2_ppf(df, 1.0 - alpha)
    power = 1.0 - ncx2_cdf(df, noncentrality, crit)
    return max(0.0, min(1.0, power)), crit


__all__ = [
    "beta_inc",
    "chi2_cdf",
    "chi2_power_from_lambda",
    "chi2_ppf",
    "f_cdf",
    "f_power_from_lambda",
    "f_ppf",
    "ncf_cdf",
    "nct_cdf",
    "ncx2_cdf",
    "norm_cdf",
    "norm_ppf",
    "t_cdf",
    "t_power_from_delta",
    "t_ppf",
]
