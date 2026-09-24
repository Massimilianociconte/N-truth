"""Orchestrazione del piano a priori: gate -> calcolo -> sensitivity.

Pipeline: EuGate -> SESOI -> ApplicabilityGate -> solver per famiglia ->
dropout/molteplicita/cluster -> SensitivityRow -> PowerPlanCandidate.

Ogni numero resta funzione deterministica degli input umani dichiarati.
Il piano non seleziona test o modelli e non certifica validita.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from ntruth.power import calculator as calc
from ntruth.power.calculator import PowerComputationError, SolveResult
from ntruth.power.errors import PowerBlockedError
from ntruth.power.gating import Applicability, applicability_gate, eu_gate
from ntruth.power.pseudoreplication import (
    DEFAULT_ICC_GRID,
    naive_type_i_error,
)
from ntruth.power.pseudoreplication import (
    NaiveFalsePositiveRate as NaiveFalseRate,
)
from ntruth.power.schema import (
    ClusterAdjustment,
    EndpointType,
    NaiveFalsePositiveRow,
    PowerAssumption,
    PowerFamily,
    PowerMethod,
    PowerPlanCandidate,
    PowerPlanInput,
    SensitivityRow,
    Tail,
)
from ntruth.power.sesoi import (
    cohen_conventional_assumption,
    is_weak_sesoi,
    require_sesoi,
)

if TYPE_CHECKING:
    from ntruth.power.simulation import SimulationTemplate

# Re-export: la classe vive in ntruth.power.errors (anti-ciclo con simulation).
__all__ = ["PowerBlockedError", "build_power_plan", "build_simulation_power_plan", "solved_method"]


# Scala di effetto attesa per famiglia (per controllo SESOI).
_EFFECT_SCALE: dict[PowerFamily, str] = {
    PowerFamily.T_ONE_SAMPLE: "d",
    PowerFamily.T_PAIRED: "dz",
    PowerFamily.T_TWO_SAMPLE: "d",
    PowerFamily.Z_TWO_PROPORTIONS: "p_diff",
    PowerFamily.ANOVA_ONEWAY: "f",
    PowerFamily.ANOVA_FACTORIAL: "f",
    PowerFamily.REGRESSION_OMNIBUS: "f2",
    PowerFamily.REGRESSION_INCREASE: "f2",
    PowerFamily.CHI2_GOF: "w",
    PowerFamily.CHI2_CONTINGENCY: "w",
    PowerFamily.BINOMIAL_EXACT: "g",
    PowerFamily.FISHER_OR_TWO_PROPORTIONS: "p_diff",
    PowerFamily.MCNEMAR: "or",
    PowerFamily.LOGISTIC_WALD: "or",
    PowerFamily.POISSON_RATE: "rr",
}

# Endpoint compatibili per famiglia (fail-closed contro mismatch scientifici).
_COMPATIBLE_ENDPOINTS: dict[PowerFamily, frozenset[EndpointType]] = {
    PowerFamily.T_ONE_SAMPLE: frozenset({EndpointType.CONTINUOUS}),
    PowerFamily.T_PAIRED: frozenset({EndpointType.CONTINUOUS}),
    PowerFamily.T_TWO_SAMPLE: frozenset({EndpointType.CONTINUOUS}),
    PowerFamily.Z_TWO_PROPORTIONS: frozenset({EndpointType.BINARY}),
    PowerFamily.ANOVA_ONEWAY: frozenset({EndpointType.CONTINUOUS}),
    PowerFamily.ANOVA_FACTORIAL: frozenset({EndpointType.CONTINUOUS}),
    PowerFamily.REGRESSION_OMNIBUS: frozenset({EndpointType.CONTINUOUS}),
    PowerFamily.REGRESSION_INCREASE: frozenset({EndpointType.CONTINUOUS}),
    PowerFamily.CHI2_GOF: frozenset({EndpointType.CATEGORICAL, EndpointType.BINARY}),
    PowerFamily.CHI2_CONTINGENCY: frozenset({EndpointType.CATEGORICAL, EndpointType.BINARY}),
    PowerFamily.BINOMIAL_EXACT: frozenset({EndpointType.BINARY}),
    PowerFamily.FISHER_OR_TWO_PROPORTIONS: frozenset({EndpointType.BINARY}),
    PowerFamily.MCNEMAR: frozenset({EndpointType.BINARY}),
    PowerFamily.LOGISTIC_WALD: frozenset({EndpointType.BINARY}),
    PowerFamily.POISSON_RATE: frozenset({EndpointType.COUNT}),
}

_FAMILY_METHOD: dict[PowerFamily, PowerMethod] = {
    PowerFamily.T_ONE_SAMPLE: PowerMethod.CLOSED_FORM_NONCENTRAL_T,
    PowerFamily.T_PAIRED: PowerMethod.CLOSED_FORM_NONCENTRAL_T,
    PowerFamily.T_TWO_SAMPLE: PowerMethod.CLOSED_FORM_NONCENTRAL_T,
    PowerFamily.Z_TWO_PROPORTIONS: PowerMethod.NORMAL_APPROXIMATION,
    PowerFamily.ANOVA_ONEWAY: PowerMethod.CLOSED_FORM_NONCENTRAL_F,
    PowerFamily.ANOVA_FACTORIAL: PowerMethod.CLOSED_FORM_NONCENTRAL_F,
    PowerFamily.REGRESSION_OMNIBUS: PowerMethod.CLOSED_FORM_NONCENTRAL_F,
    PowerFamily.REGRESSION_INCREASE: PowerMethod.CLOSED_FORM_NONCENTRAL_F,
    PowerFamily.CHI2_GOF: PowerMethod.CLOSED_FORM_NONCENTRAL_CHI2,
    PowerFamily.CHI2_CONTINGENCY: PowerMethod.CLOSED_FORM_NONCENTRAL_CHI2,
    PowerFamily.BINOMIAL_EXACT: PowerMethod.EXACT_ENUMERATION,
    PowerFamily.FISHER_OR_TWO_PROPORTIONS: PowerMethod.NORMAL_APPROXIMATION,
    PowerFamily.MCNEMAR: PowerMethod.NORMAL_APPROXIMATION,
    PowerFamily.LOGISTIC_WALD: PowerMethod.NORMAL_APPROXIMATION,
    PowerFamily.POISSON_RATE: PowerMethod.NORMAL_APPROXIMATION,
}


def _canonical_checksum(payload: PowerPlanInput) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _primary_effect(payload: PowerPlanInput) -> float:
    """Magnitudine primaria per sensitivity, per famiglia."""

    family = payload.family
    if family in {
        PowerFamily.T_ONE_SAMPLE,
        PowerFamily.T_PAIRED,
        PowerFamily.T_TWO_SAMPLE,
    }:
        if payload.cohen_d is None:
            raise PowerBlockedError("missing_effect", "cohen_d richiesto per il t test.")
        return payload.cohen_d
    if family in {PowerFamily.ANOVA_ONEWAY, PowerFamily.ANOVA_FACTORIAL}:
        if payload.cohen_f is None:
            raise PowerBlockedError("missing_effect", "cohen_f richiesto per ANOVA.")
        return payload.cohen_f
    if family in {PowerFamily.REGRESSION_OMNIBUS, PowerFamily.REGRESSION_INCREASE}:
        if payload.cohen_f2 is None:
            raise PowerBlockedError("missing_effect", "cohen_f2 richiesto per regressione.")
        return payload.cohen_f2
    if family in {PowerFamily.CHI2_GOF, PowerFamily.CHI2_CONTINGENCY}:
        if payload.cohen_w is None:
            raise PowerBlockedError("missing_effect", "cohen_w richiesto per chi2.")
        return payload.cohen_w
    if family is PowerFamily.BINOMIAL_EXACT:
        if payload.p0 is None or payload.p1 is None:
            raise PowerBlockedError("missing_effect", "p0 e p1 richiesti per il binomiale.")
        return abs(payload.p1 - payload.p0)
    if family in {PowerFamily.Z_TWO_PROPORTIONS, PowerFamily.FISHER_OR_TWO_PROPORTIONS}:
        if payload.p1 is None or payload.p2 is None:
            raise PowerBlockedError("missing_effect", "p1 e p2 richiesti per le proporzioni.")
        if payload.p1 == payload.p2:
            raise PowerBlockedError("null_effect", "p1 == p2: nessun effetto da pianificare.")
        return abs(payload.p2 - payload.p1)
    if family in {PowerFamily.MCNEMAR, PowerFamily.LOGISTIC_WALD}:
        if payload.odds_ratio is None:
            raise PowerBlockedError("missing_effect", "odds_ratio richiesto.")
        return payload.odds_ratio
    if family is PowerFamily.POISSON_RATE:
        if payload.rate_ratio is None:
            raise PowerBlockedError("missing_effect", "rate_ratio richiesto.")
        return payload.rate_ratio
    raise PowerBlockedError("unknown_family", f"Famiglia non gestita: {family.value}")


def _solve_with_scaled_effect(payload: PowerPlanInput, effect: float) -> SolveResult:
    """Risolve N sostituendo la magnitudine primaria con `effect`."""

    family = payload.family
    alpha = _effective_alpha(payload)
    two_sided = payload.tail.value == "TWO_SIDED"
    target = payload.target_power
    ratio = payload.allocation_ratio
    try:
        if family in {
            PowerFamily.T_ONE_SAMPLE,
            PowerFamily.T_PAIRED,
        }:
            return calc.solve_n_t_one_sample(effect, alpha, target, two_sided)
        if family is PowerFamily.T_TWO_SAMPLE:
            return calc.solve_n_t_two_sample(effect, alpha, target, two_sided, ratio)
        if family is PowerFamily.ANOVA_ONEWAY:
            if payload.n_groups_k is None:
                raise PowerBlockedError("missing_design", "n_groups_k richiesto per ANOVA.")
            return calc.solve_n_anova(payload.n_groups_k, effect, alpha, target)
        if family is PowerFamily.ANOVA_FACTORIAL:
            if payload.n_groups_k is None or payload.n_tested_q is None:
                raise PowerBlockedError(
                    "missing_design",
                    "n_groups_k (celle) e n_tested_q (df numeratore) richiesti.",
                )
            return _solve_n_factorial(payload.n_groups_k, payload.n_tested_q, effect, alpha, target)
        if family is PowerFamily.REGRESSION_OMNIBUS:
            if payload.n_predictors_p is None:
                raise PowerBlockedError("missing_design", "n_predictors_p richiesto.")
            return calc.solve_n_regression_omnibus(payload.n_predictors_p, effect, alpha, target)
        if family is PowerFamily.REGRESSION_INCREASE:
            if payload.n_predictors_p is None or payload.n_tested_q is None:
                raise PowerBlockedError("missing_design", "n_predictors_p e n_tested_q richiesti.")
            return _solve_n_regression_increase(
                payload.n_predictors_p, payload.n_tested_q, effect, alpha, target
            )
        if family in {PowerFamily.CHI2_GOF, PowerFamily.CHI2_CONTINGENCY}:
            if payload.chi2_df is None:
                raise PowerBlockedError("missing_design", "chi2_df richiesto per chi2.")
            return calc.solve_n_chi2(effect, payload.chi2_df, alpha, target)
        if family is PowerFamily.BINOMIAL_EXACT:
            if payload.p0 is None:
                raise PowerBlockedError("missing_effect", "p0 richiesto.")
            p1_scaled = _shift_proportion(payload.p0, payload.p1 or 0.0, effect)
            return calc.solve_n_binomial_exact(payload.p0, p1_scaled, alpha, target, two_sided)
        if family in {PowerFamily.Z_TWO_PROPORTIONS, PowerFamily.FISHER_OR_TWO_PROPORTIONS}:
            p1, p2 = _scaled_pair(payload, effect)
            return calc.solve_n_z_two_proportions(p1, p2, alpha, target, two_sided, ratio)
        if family is PowerFamily.MCNEMAR:
            if payload.p_discordant is None:
                raise PowerBlockedError("missing_effect", "p_discordant richiesto per McNemar.")
            return _solve_n_mcnemar(payload.p_discordant, effect, alpha, target)
        if family is PowerFamily.LOGISTIC_WALD:
            if payload.p1 is None:
                raise PowerBlockedError("missing_effect", "p1 richiesto per la logistica.")
            return calc.solve_n_logistic_hsieh(
                effect, payload.p1, alpha, target, two_sided, payload.r2_other or 0.0
            )
        if family is PowerFamily.POISSON_RATE:
            if payload.base_rate is None or payload.exposure is None:
                raise PowerBlockedError("missing_effect", "base_rate ed exposure richiesti.")
            return calc.solve_n_poisson_rate(
                effect, payload.base_rate, payload.exposure, alpha, target, two_sided, ratio
            )
    except PowerComputationError as exc:
        raise PowerBlockedError("computation_failed", str(exc)) from exc
    raise PowerBlockedError("unknown_family", f"Famiglia non gestita: {family.value}")


def _shift_proportion(p0: float, p1: float, scaled_gap: float) -> float:
    direction = 1.0 if p1 >= p0 else -1.0
    candidate = p0 + direction * scaled_gap
    if not 0.0 < candidate < 1.0:
        raise PowerBlockedError(
            "sensitivity_out_of_range",
            f"Sensitivity fuori (0, 1): p0={p0:g}, gap scalato={scaled_gap:g}.",
        )
    return candidate


def _scaled_pair(payload: PowerPlanInput, scaled_gap: float) -> tuple[float, float]:
    if payload.p1 is None or payload.p2 is None:
        raise PowerBlockedError("missing_effect", "p1 e p2 richiesti.")
    direction = 1.0 if payload.p2 >= payload.p1 else -1.0
    center = (payload.p1 + payload.p2) / 2.0
    half = scaled_gap / 2.0
    low, high = center - half, center + half
    if direction < 0:
        low, high = high, low
    if not 0.0 < low < 1.0 and not 0.0 < high < 1.0:
        raise PowerBlockedError("sensitivity_out_of_range", "Sensitivity fuori (0, 1).")
    low = min(max(low, 1e-6), 1.0 - 1e-6)
    high = min(max(high, 1e-6), 1.0 - 1e-6)
    first, second = (low, high) if direction > 0 else (high, low)
    return first, second


def _solve_n_factorial(
    n_cells: int, df1: int, f: float, alpha: float, target: float
) -> SolveResult:
    def sufficient(n: int) -> bool:
        return calc.power_anova_factorial(n, df1, n_cells, f, alpha).power >= target

    n = calc.solve_minimum_n(sufficient, n_cells + 1)
    result = calc.power_anova_factorial(n, df1, n_cells, f, alpha)
    return SolveResult(
        n_per_group=(n,),
        n_total=n,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


def _solve_n_regression_increase(
    p_total: int, q_tested: int, f2: float, alpha: float, target: float
) -> SolveResult:
    def sufficient(n: int) -> bool:
        return calc.power_regression_increase(n, p_total, q_tested, f2, alpha).power >= target

    n = calc.solve_minimum_n(sufficient, p_total + 2)
    result = calc.power_regression_increase(n, p_total, q_tested, f2, alpha)
    return SolveResult(
        n_per_group=(n,),
        n_total=n,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


def _solve_n_mcnemar(
    p_discordant: float, odds_ratio: float, alpha: float, target: float
) -> SolveResult:
    def sufficient(n: int) -> bool:
        return calc.power_mcnemar(n, p_discordant, odds_ratio, alpha).power >= target

    n = calc.solve_minimum_n(sufficient, 4)
    result = calc.power_mcnemar(n, p_discordant, odds_ratio, alpha)
    return SolveResult(
        n_per_group=(n,),
        n_total=n,
        achieved_power=result.power,
        critical_value=result.critical_value,
        noncentrality=result.noncentrality,
        df=result.df,
    )


def _effective_alpha(payload: PowerPlanInput) -> float:
    return calc.apply_bonferroni(payload.alpha, payload.multiplicity_m)


def build_power_plan(
    payload: PowerPlanInput, *, simulation: SimulationTemplate | None = None
) -> PowerPlanCandidate:
    """Costruisce il PowerPlanCandidate; fail-closed su ogni gate negato.

    Quando l'applicability gate richiede simulazione, il piano viene delegato
    al motore Monte Carlo solo se e fornito un SimulationTemplate dichiarato;
    altrimenti resta il blocco 409 simulation_required (retrocompatibile).
    """

    compatible = _COMPATIBLE_ENDPOINTS[payload.family]
    if payload.endpoint_type not in compatible:
        raise PowerBlockedError(
            "endpoint_mismatch",
            f"Famiglia {payload.family.value} incompatibile con endpoint "
            f"{payload.endpoint_type.value}: attesi "
            + ", ".join(sorted(item.value for item in compatible)),
        )
    gate = eu_gate(
        payload.factor_role,
        payload.contrast_type,
        payload.assignment_event_id,
        payload.exposure_cluster,
    )
    if not gate.eu_countable:
        raise PowerBlockedError("eu_gate_denied", gate.denial_reason or "EU non conteggiabile.")
    scale = _EFFECT_SCALE[payload.family]
    try:
        require_sesoi(payload.sesoi, scale)
    except ValueError as exc:
        raise PowerBlockedError("sesoi_mismatch", str(exc)) from exc
    cluster_known = payload.cluster is None or payload.cluster.icc is not None
    applicability = applicability_gate(
        payload.family,
        repeated_measures=payload.repeated_measures,
        hierarchical_depth=payload.hierarchical_depth,
        cluster_icc_known=cluster_known,
        has_clustering=payload.cluster is not None,
    )
    if applicability.applicability is Applicability.BLOCKED:
        raise PowerBlockedError("applicability_blocked", applicability.reason)
    if applicability.applicability is Applicability.SIMULATION_REQUIRED:
        if simulation is None:
            raise PowerBlockedError("simulation_required", applicability.reason)
        return build_simulation_power_plan(payload, simulation, applicability.reason)

    assumptions: list[PowerAssumption] = [
        PowerAssumption(
            code="independent_eu_count",
            message=(
                f"Il piano conta EU indipendenti di tipo {payload.experimental_unit_type!r}, "
                f"ancorate a assignment_event_id={payload.assignment_event_id!r}. "
                "Misure dentro la stessa EU non aggiungono replicazione."
            ),
        ),
        PowerAssumption(
            code="handoff_only_no_test_selected",
            message=(
                "Nessun test o modello statistico e raccomandato: la famiglia "
                f"{payload.family.value} e solo l'ipotesi di pianificazione dichiarata "
                f"da {payload.reviewer_role}; la scelta resta al biostatistico (HANDOFF_ONLY)."
            ),
        ),
    ]
    if is_weak_sesoi(payload.sesoi):
        assumptions.append(cohen_conventional_assumption(payload.sesoi))
    if payload.multiplicity_m > 1:
        assumptions.append(
            PowerAssumption(
                code="bonferroni_multiplicity",
                message=(
                    f"Correzione Bonferroni su m={payload.multiplicity_m}: "
                    f"alpha effettiva={_effective_alpha(payload):.6g}."
                ),
            )
        )
    if payload.dropout_rate > 0:
        assumptions.append(
            PowerAssumption(
                code="dropout_inflation",
                message=(
                    f"Dropout atteso {payload.dropout_rate:.2%}: N gonfiato come "
                    "N/(1-tasso); rivalutare se il dropout e informativo."
                ),
            )
        )
    if payload.tail.value == "ONE_SIDED":
        assumptions.append(
            PowerAssumption(
                code="one_sided_direction_preregistered",
                message=(
                    "Contrasto unidirezionale: la direzione deve essere preregistrata; "
                    "ogni cambio post hoc invalida il piano."
                ),
            )
        )
    if applicability.applicability is Applicability.CLOSED_FORM_WITH_CLUSTER_DIAGNOSTIC:
        assumptions.append(
            PowerAssumption(
                code="cluster_diagnostic_only",
                message=(
                    "Diagnostica DEFF sul clustering: aggiusta varianza/potenza, "
                    "non crea replicazione di assegnazione. " + applicability.reason
                ),
            )
        )
    if _FAMILY_METHOD[payload.family] is PowerMethod.NORMAL_APPROXIMATION:
        assumptions.append(
            PowerAssumption(
                code="large_sample_approximation",
                message=(
                    "Metodo in approssimazione large-sample (normale/Hsieh): per N "
                    "piccoli convalidare con enumerazione esatta prima di impegnare risorse."
                ),
            )
        )
    if payload.family is PowerFamily.FISHER_OR_TWO_PROPORTIONS:
        assumptions.append(
            PowerAssumption(
                code="exact_validation_when_small",
                message=(
                    "Pianificazione via z asintotico; per piccoli N convalidare con "
                    "enumerazione esatta (fisher_exact_validation) fissando la stessa "
                    "statistica che sara usata nell'analisi."
                ),
            )
        )

    primary = _primary_effect(payload)
    solved = _solve_with_scaled_effect(payload, primary)
    with_dropout = calc.apply_dropout(solved.n_total, payload.dropout_rate)
    assumptions.extend(_family_caveats(payload, solved))

    sensitivity: list[SensitivityRow] = []
    for multiplier in payload.sensitivity_multipliers:
        scaled = _scale_effect(payload.family, primary, multiplier)
        if scaled is None:
            continue
        try:
            row = _solve_with_scaled_effect(payload, scaled)
        except PowerBlockedError:
            continue
        sensitivity.append(
            SensitivityRow(
                effect_value=scaled,
                required_total_eu=row.n_total,
                required_per_group=row.n_per_group,
                achieved_power=row.achieved_power,
            )
        )

    cluster_adjustment = _cluster_adjustment(payload, solved.n_total)
    checksum = _canonical_checksum(payload)
    plan_id = f"pp-{checksum[:12]}"
    per_group_text = ", ".join(str(item) for item in solved.n_per_group)
    eu_statement = (
        f"EU indipendenti richieste ({payload.experimental_unit_type}): "
        f"{per_group_text} per gruppo, totale {solved.n_total} "
        f"(+dropout: {with_dropout}). Potenza target {payload.target_power:g} "
        f"su scala {scale}={primary:g}, alpha {_effective_alpha(payload):.6g} "
        f"({payload.tail.value}). Metodo {solved_method(payload)}; da confermare "
        f"con {payload.reviewer_role} prima dell'esecuzione."
    )
    return PowerPlanCandidate(
        plan_id=plan_id,
        input_checksum=checksum,
        family=payload.family,
        method=_FAMILY_METHOD[payload.family],
        tail=payload.tail,
        alpha_nominal=payload.alpha,
        alpha_effective=_effective_alpha(payload),
        target_power=payload.target_power,
        required_per_group=solved.n_per_group,
        required_total_eu=solved.n_total,
        required_total_with_dropout=with_dropout,
        achieved_power=solved.achieved_power,
        actual_alpha=solved.actual_alpha,
        noncentrality=solved.noncentrality,
        degrees_of_freedom=solved.df,
        critical_value=solved.critical_value,
        eu_statement=eu_statement,
        assumptions=tuple(assumptions),
        sensitivity=tuple(sensitivity),
        cluster_adjustment=cluster_adjustment,
    )


def _family_caveats(payload: PowerPlanInput, solved: SolveResult) -> list[PowerAssumption]:
    """Limiti di validita specifici della famiglia, mai impliciti nel numero."""

    caveats: list[PowerAssumption] = []
    if payload.family is PowerFamily.BINOMIAL_EXACT and payload.p0 is not None:
        stable = calc.binomial_stable_n(
            payload.p0,
            payload.p1 or 0.0,
            _effective_alpha(payload),
            payload.target_power,
            payload.tail.value == "TWO_SIDED",
            start=solved.n_total,
        )
        stable_text = (
            f"N stabile (potenza >= target per ogni N in [{stable}, "
            f"{stable + calc.BINOMIAL_STABILITY_WINDOW - 1}]) = {stable}"
            if stable is not None
            else "N stabile non calcolato oltre il limite di scansione"
        )
        caveats.append(
            PowerAssumption(
                code="exact_power_sawtooth",
                message=(
                    "La potenza del test esatto non e monotona in N: il minimo "
                    f"N = {solved.n_total} non garantisce la potenza per N maggiori "
                    f"(es. dopo aggiunte o dropout); {stable_text}. Verificare la "
                    "potenza per l'N effettivamente usato."
                ),
            )
        )
    if payload.family is PowerFamily.LOGISTIC_WALD:
        caveats.append(
            PowerAssumption(
                code="logistic_continuous_covariate",
                message=(
                    "Formula di Hsieh et al. (1998) per una covariata continua "
                    "normalmente distribuita: odds_ratio e per 1 deviazione standard, "
                    "p1 e la probabilita dell'evento alla media della covariata. Non e "
                    "valida per un'esposizione binaria (trattato vs controllo): usare "
                    "le famiglie a due proporzioni."
                ),
            )
        )
    if payload.paired_correlation is not None:
        caveats.append(
            PowerAssumption(
                code="paired_correlation_not_used",
                message=(
                    "paired_correlation e registrato ma non entra nel calcolo: la "
                    "potenza usa l'effetto dichiarato sulla propria scala (per il "
                    "paired, dz = d / sqrt(2(1 - r)) va fornito direttamente)."
                ),
            )
        )
    if payload.family is PowerFamily.POISSON_RATE:
        caveats.append(
            PowerAssumption(
                code="poisson_no_overdispersion",
                message=(
                    "Varianza di Poisson senza sovradispersione: conteggi biologici "
                    "sono spesso sovradispersi e richiederebbero piu unita "
                    "(binomiale negativa o simulazione dichiarata)."
                ),
            )
        )
    return caveats


def solved_method(payload: PowerPlanInput) -> str:
    """Nome metodo per lo statement EU (stesso mapping dell'output)."""

    return _FAMILY_METHOD[payload.family].value


def _scale_effect(family: PowerFamily, primary: float, multiplier: float) -> float | None:
    if family in {PowerFamily.MCNEMAR, PowerFamily.LOGISTIC_WALD, PowerFamily.POISSON_RATE}:
        # Scala sul logaritmo per OR/rapporti (simmetria moltiplicativa).
        candidate = math.exp(math.log(primary) * multiplier)
        return candidate if candidate > 0 else None
    candidate = primary * multiplier
    return candidate if candidate > 0 else None


#: Famiglie per cui l'alpha dell'analisi naive sulle osservazioni e esatta.
_NAIVE_RATE_GROUPS: dict[PowerFamily, Callable[[PowerPlanInput], int | None]] = {
    PowerFamily.T_TWO_SAMPLE: lambda _: 2,
    PowerFamily.ANOVA_ONEWAY: lambda payload: payload.n_groups_k,
}


def _naive_false_positive(
    payload: PowerPlanInput, n_total: int, mean_obs: float, icc: float
) -> NaiveFalseRate | None:
    groups_of = _NAIVE_RATE_GROUPS.get(payload.family)
    groups = groups_of(payload) if groups_of is not None else None
    if groups is None or n_total < groups:
        return None
    one_sided = payload.tail.value == "ONE_SIDED"
    if one_sided and groups != 2:
        return None
    return naive_type_i_error(
        total_units=n_total,
        mean_obs_per_unit=mean_obs,
        icc=icc,
        alpha=_effective_alpha(payload),
        groups=groups,
        one_sided=one_sided,
    )


def _cluster_adjustment(payload: PowerPlanInput, n_total: int) -> ClusterAdjustment | None:
    cluster = payload.cluster
    if cluster is None:
        return None
    if cluster.icc is None:
        return None
    m = cluster.mean_obs_per_cluster
    deff = calc.design_effect(m, cluster.icc)
    observations = n_total * m
    naive = _naive_false_positive(payload, n_total, m, cluster.icc)
    sensitivity: tuple[NaiveFalsePositiveRow, ...] = ()
    if naive is not None:
        grid = sorted({*DEFAULT_ICC_GRID, cluster.icc})
        sensitivity = tuple(
            NaiveFalsePositiveRow(icc=icc, alpha_actual=rate.alpha_actual)
            for icc in grid
            if (rate := _naive_false_positive(payload, n_total, m, icc)) is not None
        )
    naive_text = (
        f" Se le {observations:g} osservazioni fossero analizzate come indipendenti "
        f"(pseudoreplicazione), l'alpha effettiva sarebbe {naive.alpha_actual:.3f} "
        f"invece di {naive.alpha_nominal:g} (x{naive.inflation_factor:.1f})."
        if naive is not None
        else ""
    )
    return ClusterAdjustment(
        design_effect=deff,
        effective_n_diagnostic=calc.effective_n_diagnostic(observations, deff),
        clustered_total_diagnostic=math.ceil(observations),
        naive_false_positive_rate=naive.alpha_actual if naive is not None else None,
        naive_false_positive_sensitivity=sensitivity,
        warning=(
            f"DE={deff:.3f} con m={m:g}, "
            f"ICC={cluster.icc:g}: diagnostica di varianza su "
            f"{cluster.description or 'clustering dichiarato'}. Non trasforma misure "
            "in replicati di assegnazione: il numero di EU resta "
            f"{n_total}; le {observations:g} osservazioni equivalgono a "
            f"{observations / deff:.1f} osservazioni indipendenti." + naive_text
        ),
    )


# Famiglie coperte dal ramo simulato v1 (modello generativo a due gruppi).
_SIMULATED_FAMILIES: frozenset[PowerFamily] = frozenset({PowerFamily.T_TWO_SAMPLE})


def build_simulation_power_plan(
    payload: PowerPlanInput, template: SimulationTemplate, gate_reason: str
) -> PowerPlanCandidate:
    """Piano via simulazione gerarchica sul modello dichiarato (candidate-only)."""

    from ntruth.power.simulation import (
        simulation_input_from_plan,
        solve_n_eu_by_simulation,
    )

    if payload.family is PowerFamily.ANOVA_ONEWAY and payload.n_groups_k == 2:
        pass
    elif payload.family not in _SIMULATED_FAMILIES:
        raise PowerBlockedError(
            "family_not_simulated_v1",
            f"Simulazione v1 solo per T_TWO_SAMPLE (o ANOVA a 2 gruppi); "
            f"ricevuto {payload.family.value}.",
        )
    base_assumptions: list[PowerAssumption] = [
        PowerAssumption(
            code="independent_eu_count",
            message=(
                f"Il piano conta EU indipendenti di tipo {payload.experimental_unit_type!r}, "
                f"ancorate a assignment_event_id={payload.assignment_event_id!r}. "
                "Misure dentro la stessa EU non aggiungono replicazione."
            ),
        ),
        PowerAssumption(
            code="handoff_only_no_test_selected",
            message=(
                "Nessun test o modello statistico e raccomandato: la regola "
                f"{template.decision_rule.value} e solo l'analisi dichiarata da "
                f"{payload.reviewer_role} per la simulazione; la scelta resta al "
                "biostatistico (HANDOFF_ONLY)."
            ),
        ),
        PowerAssumption(
            code="simulation_conditional_on_declared_analysis",
            message=(
                "Potenza simulata condizionata al modello generativo dichiarato da "
                f"{payload.reviewer_role} (checksum input in output); nessuna selezione "
                "automatica. Motivo del ramo simulato: " + gate_reason
            ),
        ),
        PowerAssumption(
            code="monte_carlo_frequency_not_calibrated",
            message=(
                "Frequenza Monte Carlo ±MCSE, non probabilita calibrata "
                "(ADR-0016 UNQUALIFIED); non e la probabilita di successo dello studio."
            ),
        ),
        PowerAssumption(
            code="eu_aggregate_only_no_pseudoreplication",
            message=(
                "La regola di decisione aggrega a medie EU prima di ogni statistica: "
                "nessun grado di liberta scala con conteggi sub-EU. "
                "Non trasforma misure in replicati di assegnazione."
            ),
        ),
        PowerAssumption(
            code="balanced_groups_simulation_v1",
            message="Ricerca N su gruppi bilanciati (n, n); allocazioni sbilanciate fuori scope v1.",
        ),
    ]
    if is_weak_sesoi(payload.sesoi):
        base_assumptions.append(cohen_conventional_assumption(payload.sesoi))
    if payload.dropout_rate > 0:
        base_assumptions.append(
            PowerAssumption(
                code="dropout_inflation",
                message=(
                    f"Dropout atteso {payload.dropout_rate:.2%}: N gonfiato come "
                    "N/(1-tasso); rivalutare se il dropout e informativo."
                ),
            )
        )
    if payload.tail is not Tail.TWO_SIDED:
        base_assumptions.append(
            PowerAssumption(
                code="one_sided_direction_preregistered",
                message=(
                    "Contrasto unidirezionale: la direzione deve essere preregistrata; "
                    "ogni cambio post hoc invalida il piano."
                ),
            )
        )
    starter = simulation_input_from_plan(payload, template, (2, 2))
    per_group, confirmed = solve_n_eu_by_simulation(starter, payload.target_power)
    total = per_group[0] + per_group[1]
    with_dropout = calc.apply_dropout(total, payload.dropout_rate)
    checksum = _canonical_checksum(payload)
    plan_id = f"pp-{checksum[:12]}"
    eu_statement = (
        f"EU indipendenti richieste ({payload.experimental_unit_type}): "
        f"{per_group[0]}, {per_group[1]} per gruppo, totale {total} "
        f"(+dropout: {with_dropout}). Potenza simulata {confirmed.power_estimate:.4f} "
        f"±{confirmed.mcse:.4f} (target {payload.target_power:g}, N_sim={confirmed.n_sim}, "
        f"seed {confirmed.seed_root!r}, regola {confirmed.decision_rule.value}). "
        "Da confermare con biostatistico prima dell'esecuzione."
    )
    return PowerPlanCandidate(
        plan_id=plan_id,
        input_checksum=checksum,
        family=payload.family,
        method=PowerMethod.MONTE_CARLO_HIERARCHICAL,
        tail=payload.tail,
        alpha_nominal=payload.alpha,
        alpha_effective=_effective_alpha(payload),
        target_power=payload.target_power,
        required_per_group=per_group,
        required_total_eu=total,
        required_total_with_dropout=with_dropout,
        achieved_power=confirmed.power_estimate,
        actual_alpha=None,
        noncentrality=None,
        degrees_of_freedom=(),
        critical_value=None,
        eu_statement=eu_statement,
        assumptions=tuple(base_assumptions),
        sensitivity=(),
        cluster_adjustment=_cluster_adjustment(payload, total),
        simulation_n=confirmed.n_sim,
        simulation_mcse=confirmed.mcse,
        simulation_seed_root=confirmed.seed_root,
        simulation_decision_rule=confirmed.decision_rule.value,
        simulation_version=confirmed.sim_seed_version,
    )
