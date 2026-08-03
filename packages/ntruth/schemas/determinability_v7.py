"""DeterminabilityState v7: otto stati normativi e output ammessi (PRD v7 §10.2, App. M).

Il modello v3 a quattro stati resta importabile (``Determinability`` in
``schemas/core.py``); questo modulo e il contratto v7 e include la tabella
degli output ammessi e vietati.
"""

from __future__ import annotations

from enum import StrEnum

from ntruth.schemas.core import Determinability


class DeterminabilityStateV7(StrEnum):
    """Stati normativi v7 (PRD §10.2)."""

    DETERMINATE = "DETERMINATE"
    CONDITIONALLY_DETERMINATE = "CONDITIONALLY_DETERMINATE"
    MULTIPLE_PLAUSIBLE_GRAPHS = "MULTIPLE_PLAUSIBLE_GRAPHS"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    CONFLICTING_INFORMATION = "CONFLICTING_INFORMATION"
    INVALID_GRAPH = "INVALID_GRAPH"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


#: Migrazione v3 -> v7 (docs/architecture/prd-v7-migration-map.md §3).
V3_TO_V7_STATE: dict[Determinability, DeterminabilityStateV7] = {
    Determinability.DETERMINATE: DeterminabilityStateV7.DETERMINATE,
    Determinability.MULTIPLE_PLAUSIBLE_GRAPHS: DeterminabilityStateV7.MULTIPLE_PLAUSIBLE_GRAPHS,
    Determinability.INDETERMINATE: DeterminabilityStateV7.INSUFFICIENT_INFORMATION,
    Determinability.CONFLICTING_INFORMATION: DeterminabilityStateV7.CONFLICTING_INFORMATION,
}


def migrate_v3_state(state: Determinability) -> DeterminabilityStateV7:
    """Alias esplicito: nessuna conversione silenziosa."""
    return V3_TO_V7_STATE[state]


#: Output ammessi per stato (App. M). Ogni voce e una descrizione normativa
#: stabile usata dai test e dal reporting.
ALLOWED_OUTPUTS: dict[DeterminabilityStateV7, tuple[str, ...]] = {
    DeterminabilityStateV7.DETERMINATE: (
        "experimental_unit",
        "independent_n",
        "design_replication_class",
        "proof_trace",
    ),
    DeterminabilityStateV7.CONDITIONALLY_DETERMINATE: (
        "condition_record",
        "branch_outputs",
        "primary_question",
    ),
    DeterminabilityStateV7.MULTIPLE_PLAUSIBLE_GRAPHS: (
        "alternative_graphs",
        "scenario_consequences",
        "discriminating_question",
    ),
    DeterminabilityStateV7.INSUFFICIENT_INFORMATION: (
        "null_outputs",
        "reporting_gap",
        "minimal_question",
    ),
    DeterminabilityStateV7.CONFLICTING_INFORMATION: (
        "conflict_record",
        "retained_interpretations",
        "block_notice",
    ),
    DeterminabilityStateV7.INVALID_GRAPH: (
        "structural_errors",
        "required_patch",
    ),
    DeterminabilityStateV7.OUT_OF_SCOPE: ("structural_summary",),
}

#: Output vietati per stato (App. M): la violazione e un release blocker.
FORBIDDEN_OUTPUTS: dict[DeterminabilityStateV7, tuple[str, ...]] = {
    DeterminabilityStateV7.DETERMINATE: ("alternative_unlabeled",),
    DeterminabilityStateV7.CONDITIONALLY_DETERMINATE: ("single_unconditional_n",),
    DeterminabilityStateV7.MULTIPLE_PLAUSIBLE_GRAPHS: ("forced_choice",),
    DeterminabilityStateV7.INSUFFICIENT_INFORMATION: ("eu_or_n_guess",),
    DeterminabilityStateV7.CONFLICTING_INFORMATION: ("automatic_source_override",),
    DeterminabilityStateV7.INVALID_GRAPH: ("scientific_verdict",),
    DeterminabilityStateV7.OUT_OF_SCOPE: ("verdict_or_release_claim",),
}

#: Un singolo n incondizionato e ammesso solo in DETERMINATE.
SINGLE_N_STATES: frozenset[DeterminabilityStateV7] = frozenset({DeterminabilityStateV7.DETERMINATE})


def allows_single_n(state: DeterminabilityStateV7) -> bool:
    return state in SINGLE_N_STATES


def is_non_determinate(state: DeterminabilityStateV7) -> bool:
    """Ogni stato non DETERMINATE deve produrre il contratto di astensione."""
    return state is not DeterminabilityStateV7.DETERMINATE


#: AUTHOR_ASSERTION da sola non promuove mai DETERMINATE (PRD v7 §10.2).
ASSERTION_ONLY_BLOCKED_STATES: frozenset[DeterminabilityStateV7] = frozenset(
    {DeterminabilityStateV7.DETERMINATE}
)
