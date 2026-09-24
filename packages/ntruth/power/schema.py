"""Schemi del power planner: input umani espliciti, output candidate-only.

Ogni numero in output e una funzione deterministica delle assunzioni
dichiarate in input. Il planner non raccomanda test/modelli (HANDOFF_ONLY)
e non certifica validita scientifica (sempre ``not_performed``).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.factor_role import ContrastType, FactorRole
from ntruth.schemas.kernel import NonBlankStr


class Tail(StrEnum):
    """Direzionalita del contrasto pianificato."""

    ONE_SIDED = "ONE_SIDED"
    TWO_SIDED = "TWO_SIDED"


class PowerFamily(StrEnum):
    """Famiglia di calcolo, verificata contro G*Power 3.1 / Faul et al."""

    T_ONE_SAMPLE = "T_ONE_SAMPLE"
    T_PAIRED = "T_PAIRED"
    T_TWO_SAMPLE = "T_TWO_SAMPLE"
    Z_TWO_PROPORTIONS = "Z_TWO_PROPORTIONS"
    ANOVA_ONEWAY = "ANOVA_ONEWAY"
    ANOVA_FACTORIAL = "ANOVA_FACTORIAL"
    REGRESSION_OMNIBUS = "REGRESSION_OMNIBUS"
    REGRESSION_INCREASE = "REGRESSION_INCREASE"
    CHI2_GOF = "CHI2_GOF"
    CHI2_CONTINGENCY = "CHI2_CONTINGENCY"
    BINOMIAL_EXACT = "BINOMIAL_EXACT"
    FISHER_OR_TWO_PROPORTIONS = "FISHER_OR_TWO_PROPORTIONS"
    MCNEMAR = "MCNEMAR"
    LOGISTIC_WALD = "LOGISTIC_WALD"
    POISSON_RATE = "POISSON_RATE"


class EndpointType(StrEnum):
    """Tipo di endpoint dichiarato dall'umano per il contrasto."""

    CONTINUOUS = "CONTINUOUS"
    BINARY = "BINARY"
    COUNT = "COUNT"
    CATEGORICAL = "CATEGORICAL"


class SesoiSource(StrEnum):
    """Fonte della SESOI, in ordine di precedenza decrescente."""

    DECLARED_SESOI = "DECLARED_SESOI"
    BIOLOGICAL_PRIOR = "BIOLOGICAL_PRIOR"
    META_ANALYSIS = "META_ANALYSIS"
    EXTERNAL_PILOT = "EXTERNAL_PILOT"
    INTERNAL_PILOT = "INTERNAL_PILOT"
    CONVENTIONAL_COHEN = "CONVENTIONAL_COHEN"


class PowerMethod(StrEnum):
    """Metodo numerico usato; mai una validazione scientifica."""

    CLOSED_FORM_NONCENTRAL_T = "CLOSED_FORM_NONCENTRAL_T"
    CLOSED_FORM_NONCENTRAL_F = "CLOSED_FORM_NONCENTRAL_F"
    CLOSED_FORM_NONCENTRAL_CHI2 = "CLOSED_FORM_NONCENTRAL_CHI2"
    EXACT_ENUMERATION = "EXACT_ENUMERATION"
    NORMAL_APPROXIMATION = "NORMAL_APPROXIMATION"
    MONTE_CARLO_HIERARCHICAL = "MONTE_CARLO_HIERARCHICAL"


class SesoiRecord(FrozenModel):
    """Smallest effect size of interest per (contrasto, endpoint)."""

    source: SesoiSource
    value: float = Field(gt=0)
    effect_scale: str = Field(min_length=1, max_length=64)
    endpoint_id: str = Field(min_length=1, max_length=200)
    contrast_id: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=8, max_length=4000)
    evidence_ids: tuple[str, ...] = ()


class ClusterInfo(FrozenModel):
    """Struttura di clustering dichiarata; serve solo per la diagnostica DEFF."""

    mean_obs_per_cluster: float = Field(gt=1)
    icc: float | None = Field(default=None, ge=0, le=1)
    description: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _icc_or_explicit_unknown(self) -> Self:
        return self


class PowerAssumption(FrozenModel):
    """Assunzione esplicita che condiziona ogni numero del piano."""

    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=8, max_length=2000)
    blocking: bool = False


class SensitivityRow(FrozenModel):
    """Riga della sensitivity: stesso piano, effetto variato, N ricalcolato."""

    effect_value: float = Field(gt=0)
    required_total_eu: int = Field(gt=0)
    required_per_group: tuple[int, ...] = ()
    achieved_power: float = Field(gt=0, lt=1)


class PowerPlanInput(FrozenModel):
    """Input interamente umano/biostatistico; nessun campo e inferito."""

    query_id: NonBlankStr
    factor_id: NonBlankStr
    contrast_id: NonBlankStr
    endpoint_id: NonBlankStr
    endpoint_type: EndpointType
    family: PowerFamily
    tail: Tail = Tail.TWO_SIDED
    alpha: float = Field(gt=0, lt=1)
    target_power: float = Field(gt=0, lt=1)
    allocation_ratio: float = Field(default=1.0, gt=0)
    factor_role: FactorRole = FactorRole.ASSIGNED_INTERVENTION
    contrast_type: ContrastType = ContrastType.ASSIGNED_INTERVENTION_EFFECT
    assignment_event_id: str | None = Field(default=None, max_length=200)
    exposure_cluster: str | None = Field(default=None, max_length=200)
    experimental_unit_type: str = Field(min_length=1, max_length=200)
    sesoi: SesoiRecord
    # Parametri di effetto / disegno richiesti per famiglia (almeno uno).
    cohen_d: float | None = Field(default=None, gt=0)
    cohen_f: float | None = Field(default=None, gt=0)
    cohen_f2: float | None = Field(default=None, gt=0)
    cohen_w: float | None = Field(default=None, gt=0)
    p0: float | None = Field(default=None, gt=0, lt=1)
    p1: float | None = Field(default=None, gt=0, lt=1)
    p2: float | None = Field(default=None, gt=0, lt=1)
    odds_ratio: float | None = Field(default=None, gt=0)
    rate_ratio: float | None = Field(default=None, gt=0)
    base_rate: float | None = Field(default=None, gt=0)
    n_groups_k: int | None = Field(default=None, gt=1)
    n_predictors_p: int | None = Field(default=None, gt=0)
    n_tested_q: int | None = Field(default=None, gt=0)
    chi2_df: int | None = Field(default=None, gt=0)
    r2_other: float | None = Field(default=None, ge=0, lt=1)
    p_discordant: float | None = Field(default=None, gt=0, lt=1)
    exposure: float | None = Field(default=None, gt=0)
    paired_correlation: float | None = Field(default=None, gt=-1, lt=1)
    cluster: ClusterInfo | None = None
    dropout_rate: float = Field(default=0.0, ge=0, lt=1)
    multiplicity_m: int = Field(default=1, ge=1)
    repeated_measures: bool = False
    hierarchical_depth: int = Field(default=1, ge=1)
    reviewer_role: str = Field(default="researcher", min_length=2, max_length=64)
    sensitivity_multipliers: tuple[float, ...] = (0.75, 1.0, 1.25)


#: Griglia di ICC per la sensitivity quando l'ICC reale e incerta.
DEFAULT_ICC_GRID: tuple[float, ...] = (0.01, 0.05, 0.1, 0.2, 0.5)


class NaiveFalsePositiveRow(FrozenModel):
    """Alpha effettiva dell'analisi sulle osservazioni a un dato ICC."""

    icc: float = Field(ge=0, le=1)
    alpha_actual: float = Field(ge=0, le=1)


class PseudoreplicationRiskInput(FrozenModel):
    """Struttura dichiarata di un'analisi sulle osservazioni annidate.

    ``total_units`` sono le unita sperimentali (per esempio animali o colture)
    su tutti i gruppi, ``mean_obs_per_unit`` le osservazioni per unita trattate
    come indipendenti dall'analisi. Nessun campo e inferito.
    """

    total_units: int = Field(ge=2, le=1_000_000)
    mean_obs_per_unit: float = Field(ge=1, le=10_000_000)
    groups: int = Field(default=2, ge=2, le=1000)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    tail: Tail = Tail.TWO_SIDED
    icc: float | None = Field(default=None, ge=0, le=1)
    icc_grid: tuple[float, ...] = Field(default=DEFAULT_ICC_GRID, min_length=1, max_length=25)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.total_units < self.groups:
            raise ValueError("total_units deve essere >= groups")
        if self.tail is Tail.ONE_SIDED and self.groups != 2:
            raise ValueError("il test unilaterale richiede groups = 2")
        if any(not 0.0 <= icc <= 1.0 for icc in self.icc_grid):
            raise ValueError("ogni ICC della griglia deve stare in [0, 1]")
        return self


class PseudoreplicationRiskResult(FrozenModel):
    """Alpha effettiva dell'analisi naive; diagnostica, mai conteggio di EU."""

    alpha_nominal: float = Field(gt=0, lt=1)
    declared: NaiveFalsePositiveRow | None = None
    sensitivity: tuple[NaiveFalsePositiveRow, ...] = ()
    naive_df: float = Field(gt=0)
    method: str = Field(min_length=1, max_length=120)
    caveats: tuple[str, ...] = ()


class ClusterAdjustment(FrozenModel):
    """Diagnostica DEFF: aggiusta varianza/potenza, mai l'identita EU.

    I conteggi diagnostici sono in osservazioni: ``clustered_total_diagnostic``
    e il totale di osservazioni prodotte da n EU con m osservazioni ciascuna,
    ``effective_n_diagnostic`` il numero di osservazioni indipendenti con la
    stessa informazione (n*m/DEFF, sempre compreso tra n e n*m). Nessuno dei
    due e un numero di EU. ``naive_false_positive_rate`` e l'alpha effettiva
    di un'analisi che tratta le n*m osservazioni come indipendenti
    (pseudoreplicazione), calcolata in forma esatta per t a due campioni e
    ANOVA a una via; ``None`` per le altre famiglie.
    """

    design_effect: float = Field(gt=0)
    effective_n_diagnostic: float = Field(gt=0)
    clustered_total_diagnostic: int = Field(gt=0)
    naive_false_positive_rate: float | None = Field(default=None, ge=0, le=1)
    naive_false_positive_sensitivity: tuple[NaiveFalsePositiveRow, ...] = ()
    warning: str = Field(min_length=8, max_length=2000)


class PowerPlanCandidate(FrozenModel):
    """Piano candidate-only: richiede conferma umana/biostatistica."""

    plan_id: str = Field(min_length=1, max_length=64)
    input_checksum: str = Field(min_length=16, max_length=128)
    family: PowerFamily
    method: PowerMethod
    tail: Tail
    alpha_nominal: float = Field(gt=0, lt=1)
    alpha_effective: float = Field(gt=0, lt=1)
    target_power: float = Field(gt=0, lt=1)
    required_per_group: tuple[int, ...] = ()
    required_total_eu: int = Field(gt=0)
    required_total_with_dropout: int = Field(gt=0)
    achieved_power: float = Field(gt=0, lt=1)
    actual_alpha: float | None = Field(default=None, gt=0, lt=1)
    noncentrality: float | None = Field(default=None, ge=0)
    degrees_of_freedom: tuple[float, ...] = ()
    critical_value: float | None = None
    eu_statement: str = Field(min_length=8, max_length=2000)
    assumptions: tuple[PowerAssumption, ...] = ()
    sensitivity: tuple[SensitivityRow, ...] = ()
    cluster_adjustment: ClusterAdjustment | None = None
    strategy: str = Field(default="HANDOFF_ONLY", min_length=1, max_length=64)
    scientific_validation_status: str = Field(default="not_performed")
    input_mode: str = Field(default="HUMAN_DECLARED")
    # Provenienza simulazione (solo ramo MONTE_CARLO_HIERARCHICAL; None altrove).
    simulation_n: int | None = Field(default=None, gt=0)
    simulation_mcse: float | None = Field(default=None, ge=0)
    simulation_seed_root: str | None = Field(default=None, max_length=128)
    simulation_decision_rule: str | None = Field(default=None, max_length=64)
    simulation_version: str | None = Field(default=None, max_length=64)


__all__ = [
    "DEFAULT_ICC_GRID",
    "ClusterAdjustment",
    "ClusterInfo",
    "EndpointType",
    "NaiveFalsePositiveRow",
    "PowerAssumption",
    "PowerFamily",
    "PowerMethod",
    "PowerPlanCandidate",
    "PowerPlanInput",
    "PseudoreplicationRiskInput",
    "PseudoreplicationRiskResult",
    "SensitivityRow",
    "SesoiRecord",
    "SesoiSource",
    "Tail",
]
