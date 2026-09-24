"""Power via simulazione gerarchica Monte Carlo (endpoint continuo, v1).

Esegue il modello generativo dichiarato dall'umano su gerarchie nested
arbitrarie (donor->culture->well->field->cell) e applica la regola di
decisione preregistrata — solo aggregati a livello EU, mai pseudoreplicazione.
Il motore non sceglie analisi, non raccomanda test, non certifica validita:
la potenza e una frequenza Monte Carlo condizionata al modello dichiarato
(ADR-0016: UNQUALIFIED, mai probabilita calibrata).

Determinismo: ogni draw deriva da ``sha256(seed_root, checksum, sim, stream,
counter)`` con ordine di attraversamento fisso — niente RNG globale, niente
numpy, niente clock. Stesso input => bit-identico.

Riferimenti: Morris-White-Crowther 2019 (ADEMP/MCSE), Hemming 2011 (cluster
RCT), Eldridge-Ashby-Kerry 2006 (sbilanciamento), Hurlbert 1984.
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.power import distributions as dist
from ntruth.power.errors import PowerBlockedError
from ntruth.power.schema import (
    EndpointType,
    PowerMethod,
    PowerPlanInput,
    SesoiRecord,
    Tail,
)
from ntruth.schemas.core import FrozenModel
from ntruth.schemas.kernel import NonBlankStr

SIM_SEED_VERSION = "ntruth-sim-v1"
SIM_METHOD_ID = "hierarchical-sim-sha256-v1"
N_SIM_MIN = 1000
N_SIM_DEFAULT = 10000
N_SIM_MAX = 200_000
MCSE_TARGET_DEFAULT = 0.01
MAX_HIERARCHY_DEPTH = 6
MAX_LEAVES_PER_EU = 50_000
MAX_TOTAL_LEAF_DRAWS = 50_000_000


class VarianceMode(StrEnum):
    """Parametrizzazione delle varianze gerarchiche dichiarate."""

    VARIANCE_COMPONENTS = "VARIANCE_COMPONENTS"
    ICC = "ICC"


class MissingMechanism(StrEnum):
    """Meccanismo di missingness; v1 solo MCAR (MAR fuori scope)."""

    MCAR = "MCAR"


class SimulationDecisionRule(StrEnum):
    """Regola di decisione preregistrata su aggregati EU; altro vietato."""

    EU_MEAN_STUDENT_T = "EU_MEAN_STUDENT_T"
    EU_MEAN_WELCH_T = "EU_MEAN_WELCH_T"
    EU_MEAN_CI_VS_SESOI = "EU_MEAN_CI_VS_SESOI"


class HierarchyLevel(FrozenModel):
    """Un livello gerarchico con numerosita figli dichiarata per parent."""

    level_name: NonBlankStr
    counts_per_parent: tuple[int, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _counts_positive(self) -> Self:
        if any(item < 1 for item in self.counts_per_parent):
            raise ValueError("counts_per_parent richiede interi >= 1")
        return self

    def children_of(self, parent_index: int) -> int:
        """Pattern sbilanciato dichiarato: parent p -> pattern[p % len]."""

        return self.counts_per_parent[parent_index % len(self.counts_per_parent)]


class GenerativeModel(FrozenModel):
    """Modello generativo a intercette casuali nested, interamente dichiarato."""

    levels: tuple[HierarchyLevel, ...] = Field(min_length=1, max_length=MAX_HIERARCHY_DEPTH)
    variance_mode: VarianceMode
    sigma2_by_level: tuple[float, ...] | None = None
    sigma2_residual: float | None = None
    icc_by_level: tuple[float, ...] | None = None
    total_sd: float | None = None
    intercept: float
    treatment_effect: float
    assignment_level: str = Field(min_length=1, max_length=200)
    endpoint_type: EndpointType = EndpointType.CONTINUOUS
    eu_dropout_rate: float = Field(default=0.0, ge=0, lt=1)
    leaf_missing_rate: float = Field(default=0.0, ge=0, lt=1)
    missing_mechanism: MissingMechanism = MissingMechanism.MCAR

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        names = [item.level_name for item in self.levels]
        if len(set(names)) != len(names):
            raise ValueError("levels richiede nomi unici")
        if self.endpoint_type is not EndpointType.CONTINUOUS:
            raise PowerBlockedError(
                "endpoint_not_simulated_v1",
                f"Simulazione v1 solo CONTINUOUS; ricevuto {self.endpoint_type.value}.",
            )
        if self.treatment_effect == 0.0:
            raise PowerBlockedError("null_effect", "treatment_effect = 0: nessun effetto.")
        if not math.isfinite(self.intercept) or not math.isfinite(self.treatment_effect):
            raise PowerBlockedError(
                "nonfinite_generative", "intercept/effect devono essere finiti."
            )
        if self.assignment_level != self.levels[0].level_name:
            raise PowerBlockedError(
                "treatment_below_eu",
                "Il trattamento deve essere assegnato al livello EU "
                f"({self.levels[0].level_name!r}); ricevuto {self.assignment_level!r}.",
            )
        if self.variance_mode is VarianceMode.VARIANCE_COMPONENTS:
            if self.sigma2_by_level is None or self.sigma2_residual is None:
                raise PowerBlockedError(
                    "variance_incomplete", "VARIANCE_COMPONENTS richiede sigma2_by_level+residual."
                )
            if len(self.sigma2_by_level) != len(self.levels):
                raise PowerBlockedError(
                    "variance_incomplete", "sigma2_by_level deve coprire i livelli."
                )
            if any(item < 0 or not math.isfinite(item) for item in self.sigma2_by_level):
                raise PowerBlockedError("variance_incomplete", "Varianze >= 0 e finite.")
            if self.sigma2_residual <= 0 or not math.isfinite(self.sigma2_residual):
                raise PowerBlockedError("variance_incomplete", "sigma2_residual deve essere > 0.")
            if self.icc_by_level is not None or self.total_sd is not None:
                raise PowerBlockedError(
                    "variance_incomplete", "Modo varianze: icc/total_sd vietati."
                )
        else:
            if self.icc_by_level is None or self.total_sd is None:
                raise PowerBlockedError(
                    "variance_incomplete", "ICC richiede icc_by_level+total_sd."
                )
            if len(self.icc_by_level) != len(self.levels):
                raise PowerBlockedError(
                    "variance_incomplete", "icc_by_level deve coprire i livelli."
                )
            if any(not 0.0 <= item < 1.0 for item in self.icc_by_level):
                raise PowerBlockedError("variance_incomplete", "ICC deve stare in [0, 1).")
            if self.total_sd is None or self.total_sd <= 0 or not math.isfinite(self.total_sd):
                raise PowerBlockedError("variance_incomplete", "total_sd deve essere > 0.")
            if sum(self.icc_by_level) >= 1.0:
                raise PowerBlockedError(
                    "variance_icc_inconsistent", "Somma ICC >= 1: varianza residua non positiva."
                )
            if self.sigma2_by_level is not None or self.sigma2_residual is not None:
                raise PowerBlockedError("variance_incomplete", "Modo ICC: sigma2_* vietati.")
        if self.missing_mechanism is not MissingMechanism.MCAR:
            raise PowerBlockedError("missing_not_mcar", "Simulazione v1 solo MCAR.")
        return self

    def resolved_variances(self) -> tuple[tuple[float, ...], float]:
        """Ritorna (sigma2 per livello, sigma2 residua) nella forma canonica."""

        if self.variance_mode is VarianceMode.VARIANCE_COMPONENTS:
            assert self.sigma2_by_level is not None and self.sigma2_residual is not None
            return self.sigma2_by_level, self.sigma2_residual
        assert self.icc_by_level is not None and self.total_sd is not None
        total_var = self.total_sd * self.total_sd
        by_level = tuple(item * total_var for item in self.icc_by_level)
        return by_level, total_var * (1.0 - sum(self.icc_by_level))

    def total_variance(self) -> float:
        """Varianza totale implicita (vincolo di coerenza con d di Cohen)."""

        by_level, residual = self.resolved_variances()
        return sum(by_level) + residual

    def expected_leaves_per_eu(self) -> int:
        """Foglie attese per EU sotto il pattern dichiarato (bilanciato=>esatto)."""

        total = 1
        for level in self.levels[1:]:
            mean_children = sum(level.counts_per_parent) / len(level.counts_per_parent)
            total = math.ceil(total * mean_children)
        return total


class SimulationTemplate(FrozenModel):
    """Parte umana della simulazione; N EU e risolto dal planner."""

    generative: GenerativeModel
    decision_rule: SimulationDecisionRule = SimulationDecisionRule.EU_MEAN_STUDENT_T
    n_sim: int = Field(default=N_SIM_DEFAULT, ge=N_SIM_MIN, le=N_SIM_MAX)
    seed_root: str = Field(default=SIM_SEED_VERSION, min_length=8, max_length=128)
    mcse_target: float = Field(default=MCSE_TARGET_DEFAULT, gt=0, lt=0.5)
    raw_sesoi_value: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _precision(self) -> Self:
        required = required_n_sim_for_mcse(self.mcse_target)
        if self.n_sim < required:
            raise PowerBlockedError(
                "n_sim_below_precision",
                f"n_sim={self.n_sim} sotto {required} richiesti per MCSE<={self.mcse_target:g}.",
            )
        if (
            self.decision_rule is SimulationDecisionRule.EU_MEAN_CI_VS_SESOI
            and self.raw_sesoi_value is None
        ):
            raise PowerBlockedError(
                "sesoi_mismatch",
                "EU_MEAN_CI_VS_SESOI richiede raw_sesoi_value sulla scala grezza.",
            )
        return self


class SimulationInput(FrozenModel):
    """Input completo di una corsa: template + N EU dichiarati."""

    template: SimulationTemplate
    sesoi: SesoiRecord
    n_eu_per_group: tuple[int, ...] = Field(min_length=1, max_length=2)
    alpha: float = Field(gt=0, lt=1)
    tail: Tail = Tail.TWO_SIDED

    @model_validator(mode="after")
    def _groups_valid(self) -> Self:
        if any(item < 2 for item in self.n_eu_per_group):
            raise PowerBlockedError("groups_too_small", "Ogni gruppo richiede >= 2 EU.")
        return self


class SimulationResult(FrozenModel):
    """Frequenza Monte Carlo condizionata; mai probabilita calibrata."""

    result_id: str = Field(min_length=1, max_length=64)
    input_checksum: str = Field(min_length=16, max_length=128)
    seed_root: str = Field(min_length=8, max_length=128)
    sim_seed_version: str = Field(default=SIM_SEED_VERSION)
    sim_method_id: str = Field(default=SIM_METHOD_ID)
    decision_rule: SimulationDecisionRule
    n_eu_per_group: tuple[int, ...] = ()
    n_sim: int = Field(gt=0)
    n_nonevaluable: int = Field(ge=0)
    power_estimate: float = Field(ge=0, le=1)
    mcse: float = Field(ge=0)
    ci95_lo: float
    ci95_hi: float
    alpha_nominal: float = Field(gt=0, lt=1)
    tail: Tail
    method: PowerMethod = PowerMethod.MONTE_CARLO_HIERARCHICAL
    strategy: str = Field(default="HANDOFF_ONLY")
    scientific_validation_status: str = Field(default="not_performed")


def required_n_sim_for_mcse(mcse_target: float) -> int:
    """N_sim nel caso peggiore (p=0.5): ceil(0.25/mcse^2) (Morris et al.)."""

    if not 0.0 < mcse_target < 0.5:
        raise PowerBlockedError("mcse_invalid", "mcse_target deve stare in (0, 0.5).")
    return math.ceil(0.25 / (mcse_target * mcse_target))


def simulation_checksum(payload: SimulationInput) -> str:
    """Checksum canonica dell'input di simulazione per audit/riproducibilita."""

    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sim_uniform(
    *, seed_root: str, input_checksum: str, sim_index: int, stream: str, counter: int
) -> float:
    """Uniforme(0,1) deterministica da sha256; chiavi ordinamento-indipendenti."""

    material = f"{seed_root}\0{input_checksum}\0{sim_index}\0{stream}\0{counter}".encode()
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    return min(max(value, 1e-12), 1.0 - 1e-12)


def _sim_randn(
    *, seed_root: str, input_checksum: str, sim_index: int, stream: str, counter: int
) -> float:
    """Normale standard deterministica via quantile esatto (stesso path chiusa)."""

    return dist.norm_ppf(
        _sim_uniform(
            seed_root=seed_root,
            input_checksum=input_checksum,
            sim_index=sim_index,
            stream=stream,
            counter=counter,
        )
    )


def _simulate_eu_mean(
    *,
    generative: GenerativeModel,
    by_level_sd: tuple[float, ...],
    residual_sd: float,
    treated: bool,
    seed_root: str,
    input_checksum: str,
    sim_index: int,
    eu_index: int,
    eu_ordinal: int | None = None,
) -> tuple[float, bool]:
    """Simula una EU e ritorna (media foglie osservabili, valutabile).

    ``eu_index`` identifica gli stream casuali (unico fra i bracci);
    ``eu_ordinal`` e la posizione della EU nel proprio braccio e seleziona il
    pattern sbilanciato dichiarato (parent p -> pattern[p % len]): la EU i del
    controllo e la EU i del trattato hanno la stessa struttura di cluster.
    """

    levels = generative.levels
    counters = {"var": 0, "resid": 0, "miss": 0}
    prefix = f"eu{eu_index}"

    def draw(stream: str, kind: str) -> float:
        value = _sim_randn(
            seed_root=seed_root,
            input_checksum=input_checksum,
            sim_index=sim_index,
            stream=f"{stream}:{prefix}",
            counter=counters[kind],
        )
        counters[kind] += 1
        return value

    # Dropout intera EU (MCAR): decide prima di generare i figli.
    if generative.eu_dropout_rate > 0:
        u = _sim_uniform(
            seed_root=seed_root,
            input_checksum=input_checksum,
            sim_index=sim_index,
            stream=f"drop:{prefix}",
            counter=0,
        )
        if u < generative.eu_dropout_rate:
            return 0.0, False

    base = generative.intercept + (generative.treatment_effect if treated else 0.0)
    leaves: list[float] = []

    def walk(depth: int, node_path: str, inherited: float, ordinal: int) -> None:
        sd = by_level_sd[depth]
        node_effect = inherited + (draw(f"var:L{depth}:{node_path}", "var") * sd if sd > 0 else 0.0)
        if depth == len(levels) - 1:
            # Livello foglia: una osservazione con residuo.
            if generative.leaf_missing_rate > 0:
                u = _sim_uniform(
                    seed_root=seed_root,
                    input_checksum=input_checksum,
                    sim_index=sim_index,
                    stream=f"miss:{node_path}",
                    counter=counters["miss"],
                )
                counters["miss"] += 1
                if u < generative.leaf_missing_rate:
                    return
            leaves.append(base + node_effect + draw(f"resid:{node_path}", "resid") * residual_sd)
            return
        children = levels[depth + 1].children_of(ordinal)
        for child in range(children):
            walk(depth + 1, f"{node_path}c{child}", node_effect, child)

    walk(0, prefix, 0.0, eu_index if eu_ordinal is None else eu_ordinal)
    if not leaves:
        return 0.0, False
    return sum(leaves) / len(leaves), True


def _welch_df(var1: float, n1: int, var2: float, n2: int) -> float:
    """df Welch-Satterthwaite; fail-closed su varianze degeneri."""

    term1 = var1 / n1 if n1 > 0 else 0.0
    term2 = var2 / n2 if n2 > 0 else 0.0
    denom = (term1 * term1) / max(1, n1 - 1) + (term2 * term2) / max(1, n2 - 1)
    if denom <= 0:
        raise PowerBlockedError("degenerate_simulation", "Varianze simulate degeneri.")
    return (term1 + term2) ** 2 / denom


def _apply_decision_rule(
    *,
    rule: SimulationDecisionRule,
    means0: list[float],
    means1: list[float],
    alpha: float,
    two_sided: bool,
    raw_sesoi: float | None,
) -> bool:
    """Applica la regola dichiarata alle medie EU; mai su osservazioni pooled."""

    n0, n1 = len(means0), len(means1)
    mean0 = sum(means0) / n0
    mean1 = sum(means1) / n1
    var0 = sum((item - mean0) ** 2 for item in means0) / max(1, n0 - 1) if n0 > 1 else 0.0
    var1 = sum((item - mean1) ** 2 for item in means1) / max(1, n1 - 1) if n1 > 1 else 0.0
    diff = mean1 - mean0
    if rule is SimulationDecisionRule.EU_MEAN_WELCH_T:
        se = math.sqrt(var0 / n0 + var1 / n1)
        if se <= 0:
            return False
        stat = diff / se
        df = _welch_df(var0, n0, var1, n1)
    else:
        pooled = ((n0 - 1) * var0 + (n1 - 1) * var1) / max(1, n0 + n1 - 2)
        se = math.sqrt(max(0.0, pooled) * (1.0 / n0 + 1.0 / n1))
        if se <= 0:
            return False
        stat = diff / se
        df = float(n0 + n1 - 2)
    if rule is SimulationDecisionRule.EU_MEAN_CI_VS_SESOI:
        assert raw_sesoi is not None and raw_sesoi > 0
        crit = dist.t_ppf(df, 1.0 - alpha / 2.0) if two_sided else dist.t_ppf(df, 1.0 - alpha)
        return (diff - crit * se) > raw_sesoi
    if two_sided:
        return abs(stat) > dist.t_ppf(df, 1.0 - alpha / 2.0)
    return stat > dist.t_ppf(df, 1.0 - alpha)


def simulate_power(payload: SimulationInput) -> SimulationResult:
    """Stima la potenza come frequenza Monte Carlo; pura e deterministica."""

    generative = payload.template.generative
    leaves_per_eu = generative.expected_leaves_per_eu()
    total_draws = payload.template.n_sim * sum(payload.n_eu_per_group) * max(1, leaves_per_eu)
    if leaves_per_eu > MAX_LEAVES_PER_EU or total_draws > MAX_TOTAL_LEAF_DRAWS:
        raise PowerBlockedError(
            "simulation_too_large",
            f"Carico {total_draws} draw oltre il cap: ridurre foglie/EU o n_sim.",
        )
    checksum = simulation_checksum(payload)
    by_level_var, residual_var = generative.resolved_variances()
    by_level_sd = tuple(math.sqrt(item) for item in by_level_var)
    residual_sd = math.sqrt(residual_var)
    two_sided = payload.tail is Tail.TWO_SIDED
    n_groups = payload.n_eu_per_group
    n1 = n_groups[0] if len(n_groups) == 1 else n_groups[1]
    n0 = n_groups[0]
    successes = 0
    nonevaluable = 0
    for sim_index in range(payload.template.n_sim):
        means0: list[float] = []
        means1: list[float] = []
        for eu in range(n0):
            mean, ok = _simulate_eu_mean(
                generative=generative,
                by_level_sd=by_level_sd,
                residual_sd=residual_sd,
                treated=False,
                seed_root=payload.template.seed_root,
                input_checksum=checksum,
                sim_index=sim_index,
                eu_index=eu,
                eu_ordinal=eu,
            )
            if ok:
                means0.append(mean)
            else:
                nonevaluable += 1
        for eu in range(n1):
            mean, ok = _simulate_eu_mean(
                generative=generative,
                by_level_sd=by_level_sd,
                residual_sd=residual_sd,
                treated=True,
                seed_root=payload.template.seed_root,
                input_checksum=checksum,
                sim_index=sim_index,
                eu_index=n0 + eu,
                eu_ordinal=eu,
            )
            if ok:
                means1.append(mean)
            else:
                nonevaluable += 1
        # Replica conservativa: EU non valutabili => decisione negativa.
        if len(means0) < 2 or len(means1) < 2:
            continue
        if _apply_decision_rule(
            rule=payload.template.decision_rule,
            means0=means0,
            means1=means1,
            alpha=payload.alpha,
            two_sided=two_sided,
            raw_sesoi=payload.template.raw_sesoi_value,
        ):
            successes += 1
    n_sim = payload.template.n_sim
    estimate = successes / n_sim
    mcse = math.sqrt(max(0.0, estimate * (1.0 - estimate)) / n_sim)
    seed_hash = hashlib.sha256(f"{checksum}\0{payload.template.seed_root}".encode()).hexdigest()[:6]
    return SimulationResult(
        result_id=f"sim-{checksum[:12]}-{seed_hash}",
        input_checksum=checksum,
        seed_root=payload.template.seed_root,
        decision_rule=payload.template.decision_rule,
        n_eu_per_group=payload.n_eu_per_group,
        n_sim=n_sim,
        n_nonevaluable=nonevaluable,
        power_estimate=estimate,
        mcse=mcse,
        ci95_lo=max(0.0, estimate - 1.96 * mcse),
        ci95_hi=min(1.0, estimate + 1.96 * mcse),
        alpha_nominal=payload.alpha,
        tail=payload.tail,
    )


class SimulatedPowerRequest(FrozenModel):
    """Richiesta combinata piano + template simulativo (API/CLI)."""

    plan: PowerPlanInput
    simulation: SimulationTemplate


def simulation_input_from_plan(
    payload: PowerPlanInput,
    template: SimulationTemplate,
    n_eu_per_group: tuple[int, ...],
) -> SimulationInput:
    """Lega il template al piano: coerenza EU/endpoint/SESOI, fail-closed."""

    if template.generative.assignment_level != template.generative.levels[0].level_name:
        raise PowerBlockedError("treatment_below_eu", "Assegnazione non a livello EU.")
    return SimulationInput(
        template=template,
        sesoi=payload.sesoi,
        n_eu_per_group=n_eu_per_group,
        alpha=payload.alpha,
        tail=payload.tail,
    )


def solve_n_eu_by_simulation(
    template_input: SimulationInput,
    target_power: float,
    *,
    n_sim_pilot: int = 2000,
    discriminate_mc: bool = True,
) -> tuple[tuple[int, int], SimulationResult]:
    """Minimo N EU via bisezione pilota + conferma a piena precisione.

    La banda bassa unilaterale (p - 1.64*mcse >= target) evita flip da rumore.
    """

    from ntruth.power.calculator import solve_minimum_n

    if not 0.0 < target_power < 1.0:
        raise PowerBlockedError("target_invalid", "target_power deve stare in (0, 1).")
    pilot_n = max(N_SIM_MIN, min(n_sim_pilot, template_input.template.n_sim))

    def pilot_input(n: int) -> SimulationInput:
        return template_input.model_copy(
            update={
                "n_eu_per_group": (n, n),
                "template": template_input.template.model_copy(update={"n_sim": pilot_n}),
            }
        )

    def sufficient(n: int) -> bool:
        result = simulate_power(pilot_input(n))
        band = result.power_estimate - (1.64 * result.mcse if discriminate_mc else 0.0)
        return band >= target_power

    per_group = solve_minimum_n(sufficient, 2)
    # Conferma a piena precisione; sale finche la banda bassa regge.
    confirmed = simulate_power(
        template_input.model_copy(update={"n_eu_per_group": (per_group, per_group)})
    )
    guard = 0
    while confirmed.power_estimate - 1.64 * confirmed.mcse < target_power and guard < 25:
        per_group += 1
        guard += 1
        confirmed = simulate_power(
            template_input.model_copy(update={"n_eu_per_group": (per_group, per_group)})
        )
    return (per_group, per_group), confirmed


__all__ = [
    "MCSE_TARGET_DEFAULT",
    "N_SIM_DEFAULT",
    "N_SIM_MAX",
    "N_SIM_MIN",
    "SIM_METHOD_ID",
    "SIM_SEED_VERSION",
    "GenerativeModel",
    "HierarchyLevel",
    "MissingMechanism",
    "SimulatedPowerRequest",
    "SimulationDecisionRule",
    "SimulationInput",
    "SimulationResult",
    "SimulationTemplate",
    "VarianceMode",
    "required_n_sim_for_mcse",
    "simulate_power",
    "simulation_checksum",
    "simulation_input_from_plan",
    "solve_n_eu_by_simulation",
]
