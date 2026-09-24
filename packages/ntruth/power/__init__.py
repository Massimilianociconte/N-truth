"""A-priori power planner prospettico (PRD v9, sidecar separato).

Questo package e un sidecar prospettico puro, deterministico e offline
(stdlib-only): NON fa parte della statistical strategy (che resta
``HANDOFF_ONLY``), NON seleziona test o modelli, NON modifica EU, fatti,
claim o gate esistenti. Produce solo ``PowerPlanCandidate``: conteggi di
unita sperimentali indipendenti richiesti + assunzioni esplicite +
analisi di sensibilita, da confermare da un umano/biostatistico.

Direzione di import one-way: questo package puo leggere DTO di
``ntruth.schemas``/``ntruth.scientific``; nessun modulo esistente deve
importare ``ntruth.power`` (la closure dell'evaluator resta intatta).
"""

from ntruth.power.gating import (
    Applicability,
    ApplicabilityDecision,
    EuGateDecision,
    applicability_gate,
    eu_gate,
)
from ntruth.power.planner import PowerBlockedError, build_power_plan, build_simulation_power_plan
from ntruth.power.pseudoreplication import (
    naive_type_i_error,
    naive_type_i_error_grid,
    pseudoreplication_risk,
)
from ntruth.power.schema import (
    ClusterInfo,
    EndpointType,
    PowerAssumption,
    PowerFamily,
    PowerMethod,
    PowerPlanCandidate,
    PowerPlanInput,
    PseudoreplicationRiskInput,
    PseudoreplicationRiskResult,
    SensitivityRow,
    SesoiRecord,
    SesoiSource,
    Tail,
)
from ntruth.power.sesoi import (
    SESOI_PRECEDENCE,
    cohen_conventional_assumption,
    require_sesoi,
    sesoi_rank,
)
from ntruth.power.simulation import (
    GenerativeModel,
    HierarchyLevel,
    MissingMechanism,
    SimulatedPowerRequest,
    SimulationDecisionRule,
    SimulationInput,
    SimulationResult,
    SimulationTemplate,
    VarianceMode,
    simulate_power,
    simulation_input_from_plan,
    solve_n_eu_by_simulation,
)

__all__ = [
    "SESOI_PRECEDENCE",
    "Applicability",
    "ApplicabilityDecision",
    "ClusterInfo",
    "EndpointType",
    "EuGateDecision",
    "GenerativeModel",
    "HierarchyLevel",
    "MissingMechanism",
    "PowerAssumption",
    "PowerBlockedError",
    "PowerFamily",
    "PowerMethod",
    "PowerPlanCandidate",
    "PowerPlanInput",
    "PseudoreplicationRiskInput",
    "PseudoreplicationRiskResult",
    "SensitivityRow",
    "SesoiRecord",
    "SesoiSource",
    "SimulatedPowerRequest",
    "SimulationDecisionRule",
    "SimulationInput",
    "SimulationResult",
    "SimulationTemplate",
    "Tail",
    "VarianceMode",
    "applicability_gate",
    "build_power_plan",
    "build_simulation_power_plan",
    "cohen_conventional_assumption",
    "eu_gate",
    "naive_type_i_error",
    "naive_type_i_error_grid",
    "pseudoreplication_risk",
    "require_sesoi",
    "sesoi_rank",
    "simulate_power",
    "simulation_input_from_plan",
    "solve_n_eu_by_simulation",
]
