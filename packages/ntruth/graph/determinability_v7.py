"""Derivazione v7 del DeterminabilityState (PRD v7 §10.2, §18.6).

Lo stato e DERIVATO dai fatti del grafo e poi revisionato: non viene scelto
liberamente dall'annotatore. La funzione e conservativa: ogni fatto decisivo
assente, conflitto irrisolto o UNKNOWN di interferenza impedisce DETERMINATE.
"""

from __future__ import annotations

from dataclasses import dataclass

from ntruth.schemas.authority import AuthorityLedger
from ntruth.schemas.determinability_v7 import DeterminabilityStateV7


@dataclass(frozen=True)
class V7GraphFacts:
    """Fatti decisivi richiesti dalla tabella normativa (App. M)."""

    allocation_known: bool = False
    operational_independence_known: bool = False
    contrast_defined: bool = False
    endpoint_defined: bool = False
    counts_sufficient: bool = False
    interference_unknown: bool = True
    graph_invariants_ok: bool = True
    in_scope: bool = True
    alternative_graph_count: int = 0
    missing_predicate: str | None = None
    enumerable_branches: bool = False
    assertion_only: bool = False  # solo AUTHOR_ASSERTION disponibile
    decisive_fields: frozenset[str] = frozenset()


def derive_determinability_v7(
    facts: V7GraphFacts,
    ledger: AuthorityLedger | None = None,
) -> DeterminabilityStateV7:
    """Ordine di precedenza fail-closed (App. M).

    1. invarianti violate -> INVALID_GRAPH;
    2. fuori profilo -> OUT_OF_SCOPE;
    3. conflitto irrisolto su campi decisivi -> CONFLICTING_INFORMATION;
    4. piu grafi compatibili -> MULTIPLE_PLAUSIBLE_GRAPHS;
    5. fatto decisivo assente: rami enumerabili -> CONDITIONALLY_DETERMINATE,
       altrimenti INSUFFICIENT_INFORMATION;
    6. fatti completi -> DETERMINATE (mai con sola AUTHOR_ASSERTION).
    """
    if not facts.graph_invariants_ok:
        return DeterminabilityStateV7.INVALID_GRAPH
    if not facts.in_scope:
        return DeterminabilityStateV7.OUT_OF_SCOPE

    if ledger is not None and ledger.blocks_determinate(facts.decisive_fields):
        return DeterminabilityStateV7.CONFLICTING_INFORMATION

    if facts.alternative_graph_count >= 2:
        return DeterminabilityStateV7.MULTIPLE_PLAUSIBLE_GRAPHS

    complete = (
        facts.allocation_known
        and facts.operational_independence_known
        and facts.contrast_defined
        and facts.endpoint_defined
        and facts.counts_sufficient
        and not facts.interference_unknown
        and facts.missing_predicate is None
    )
    if not complete:
        if facts.missing_predicate is not None and facts.enumerable_branches:
            return DeterminabilityStateV7.CONDITIONALLY_DETERMINATE
        return DeterminabilityStateV7.INSUFFICIENT_INFORMATION

    if facts.assertion_only:
        # AUTHOR_ASSERTION da sola non promuove mai DETERMINATE (PRD v7 §10.2).
        return DeterminabilityStateV7.INSUFFICIENT_INFORMATION
    return DeterminabilityStateV7.DETERMINATE
