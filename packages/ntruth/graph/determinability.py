"""Determinabilita' claim-specific (PRD v8.0 §7.16) e aggregazione v6 deprecata.

La fonte degli stati e' claim-specific: ogni dimensione (EU, EU count, source
count) ha il proprio ``DeterminabilityState`` calcolato dallo stesso nucleo di
derivazione. L'aggregato block-level v6 (``derive_determinability``) resta
chiamabile ed e' DEPRECATO: e' una proiezione degli stati claim-specific che
deve restare byte-identica ai pin ``tests/regression/block_level_pins.json``.

Una dimensione sconosciuta non pertinente a un claim non lo blocca (§7.16):
gli stati claim-specific dipendono solo dai campi/predicati richiesti dalla
propria famiglia di clausole, mai dalle dimensioni altrui.
"""

from __future__ import annotations

from ntruth.design.schema import DesignCompilation
from ntruth.graph.validation import blocking_violations, validate_experiment_block
from ntruth.schemas.core import Determinability, EvidenceType, ProvenanceKind
from ntruth.schemas.experiment import (
    ExperimentBlock,
    GraphStatus,
    Inferability,
    TriState,
    UnitAssessment,
)


def claim_value_state(assessment: UnitAssessment, *, has_value: bool) -> Determinability:
    """Stato claim-specific di una singola dimensione del nucleo di derivazione.

    DETERMINATE descrive risolubilita' strutturale del valore, non qualita' o
    adeguatezza del disegno (§7.18). Gli stati dipendono solo dall'assessment
    della dimensione: mai da dimensioni non pertinenti al claim (§7.16).
    """
    if assessment.conditional_scenarios:
        return Determinability.CONDITIONALLY_DETERMINATE
    if not has_value:
        return Determinability.INSUFFICIENT_INFORMATION
    if assessment.inferability is Inferability.INFERABLE:
        return Determinability.DETERMINATE
    return Determinability.INSUFFICIENT_INFORMATION


def claim_specific_states(block: ExperimentBlock) -> dict[str, tuple[Determinability, ...]]:
    """Stati claim-specific per assessment: (EU, EU count, source count).

    Il source count e' DETERMINATE anche quando la dimensione non e'
    applicabile allo scope (nessuna unita biologica): un'assenza dichiarata
    non e' informazione insufficiente (Appendice AC).
    """
    states: dict[str, tuple[Determinability, ...]] = {}
    for assessment in block.unit_assessments:
        if assessment.biological_source_count is not None or assessment.biological_unit is None:
            source_state = Determinability.DETERMINATE
        else:
            source_state = Determinability.INSUFFICIENT_INFORMATION
        states[assessment.id] = (
            claim_value_state(assessment, has_value=assessment.experimental_unit is not None),
            claim_value_state(assessment, has_value=assessment.n_independent is not None),
            source_state,
        )
    return states


def derive_determinability(
    block: ExperimentBlock,
    compilation: DesignCompilation,
    *,
    supported_profile: bool | None = None,
) -> Determinability:
    """DEPRECATO: aggregazione block-level v6 degli stati claim-specific.

    Conservata byte-identica come guardia di cutover (pin in
    ``tests/regression``): i nuovi consumer usano gli stati claim-specific di
    ``DerivedClaim`` e ``ReportResolutionState`` (§10.2/§10.4), mai questo
    riassunto. La precedenza e: grafo invalido, profilo non supportato,
    conflitto, rami condizionali enumerabili, grafi alternativi, informazione
    insufficiente e infine determinate. ``DETERMINATE`` descrive completezza
    strutturale; non certifica validita, qualita o generalizzabilita
    scientifica (§7.18).
    """
    structural = _structural_state(block, supported_profile)
    if structural is not None:
        return structural
    return _aggregate_claim_states(block, compilation)


def _structural_state(
    block: ExperimentBlock, supported_profile: bool | None
) -> Determinability | None:
    """Stati strutturali del blocco che precedono qualunque claim (§7.16)."""
    if block.graph_status is GraphStatus.INVALID or blocking_violations(
        validate_experiment_block(block)
    ):
        return Determinability.INVALID_GRAPH

    if supported_profile is False:
        return Determinability.OUT_OF_SCOPE

    if any(item.status == "unresolved" for item in block.contradictions):
        return Determinability.CONFLICTING_INFORMATION

    if any(assessment.conditional_scenarios for assessment in block.unit_assessments):
        return Determinability.CONDITIONALLY_DETERMINATE

    if _has_materialized_plausible_graphs(block):
        return Determinability.MULTIPLE_PLAUSIBLE_GRAPHS

    # Il marker storico, da solo, non materializza due grafi. Impedisce inoltre
    # che un blocco dichiarato condizionale cada accidentalmente in DETERMINATE.
    if block.graph_status is GraphStatus.CONDITIONAL:
        return Determinability.INSUFFICIENT_INFORMATION

    return None


def _aggregate_claim_states(
    block: ExperimentBlock, compilation: DesignCompilation
) -> Determinability:
    """Aggregazione v6: DETERMINATE solo se ogni claim decisivo e' chiuso.

    I claim considerati dall'aggregato storico sono EU e EU count (il core
    decisivo v6); il source count qualifica lo scope ma non chiude il
    verdetto block-level (§7.15 D).
    """
    if not block.unit_assessments or compilation.abstained:
        return Determinability.INSUFFICIENT_INFORMATION

    states = claim_specific_states(block)
    for eu_state, count_state, _source_state in states.values():
        if eu_state is not Determinability.DETERMINATE:
            return Determinability.INSUFFICIENT_INFORMATION
        if count_state is not Determinability.DETERMINATE:
            return Determinability.INSUFFICIENT_INFORMATION

    if not _decisive_core_is_complete(block) or _author_assertion_is_only_decisive_support(block):
        return Determinability.INSUFFICIENT_INFORMATION

    return Determinability.DETERMINATE


def _has_materialized_plausible_graphs(block: ExperimentBlock) -> bool:
    graph_set = block.plausible_graph_set
    if graph_set is None or block.graph_status is not GraphStatus.CONDITIONAL:
        return False
    if len(graph_set.alternatives) < 2:
        return False
    signatures = {item.scientific_signature() for item in graph_set.alternatives}
    return len(signatures) == len(graph_set.alternatives)


def _decisive_core_is_complete(block: ExperimentBlock) -> bool:
    """Controlla i campi che autorizzano un singolo EU/n nel Core Profile."""

    factors = {factor.id: factor for factor in block.factors}
    for assessment in block.unit_assessments:
        scope = assessment.scope
        factor = factors.get(scope.factor_id or "")
        if factor is None:
            return False
        if factor.allocation_level is None:
            return False
        if factor.independently_assigned is not TriState.TRUE:
            return False
        if scope.contrast_id is None or scope.endpoint_id is None:
            return False
        if assessment.experimental_unit is None or assessment.n_independent is None:
            return False
        human_confirmed = factor.provenance.origin in {
            ProvenanceKind.USER,
            ProvenanceKind.ADJUDICATION,
        }
        if not assessment.evidence_ids:
            return False
        if not human_confirmed and (
            not factor.allocation_evidence_ids or not factor.independence_evidence_ids
        ):
            return False
    return True


def _author_assertion_is_only_decisive_support(block: ExperimentBlock) -> bool:
    """Impedisce che un'assertion dell'autore chiuda da sola il verdict."""

    evidence_by_id = {item.id: item for item in block.evidence}
    for assessment in block.unit_assessments:
        factor = block.factor(assessment.scope.factor_id or "")
        if factor is None:
            return True
        if {
            assessment.provenance.origin,
            factor.provenance.origin,
        } & {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION}:
            continue

        # Allocation e indipendenza sono due premesse diverse. Evidenza strutturale
        # dell'una non puo legittimare l'altra e un fatto umano su un altro scope
        # non puo chiudere questo assessment.
        for decisive_ids in (
            factor.allocation_evidence_ids,
            factor.independence_evidence_ids,
        ):
            decisive_spans = [
                evidence_by_id[evidence_id]
                for evidence_id in decisive_ids
                if evidence_id in evidence_by_id
            ]
            if (
                not decisive_ids
                or len(decisive_spans) != len(decisive_ids)
                or any(span.evidence_type is None for span in decisive_spans)
                or all(
                    span.evidence_type is EvidenceType.AUTHOR_ASSERTION for span in decisive_spans
                )
            ):
                return True
    return False
