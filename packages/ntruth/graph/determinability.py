"""Derivazione deterministica della tabella ``DeterminabilityState`` v6."""

from __future__ import annotations

from ntruth.design.schema import DesignCompilation
from ntruth.graph.validation import blocking_violations, validate_experiment_block
from ntruth.schemas.core import Determinability, EvidenceType, ProvenanceKind
from ntruth.schemas.experiment import ExperimentBlock, GraphStatus, Inferability, TriState


def derive_determinability(
    block: ExperimentBlock,
    compilation: DesignCompilation,
    *,
    supported_profile: bool | None = None,
) -> Determinability:
    """Applica la tabella normativa v6 senza usare confidence come fatto.

    La precedenza e: grafo invalido, profilo non supportato, conflitto, rami
    condizionali enumerabili, grafi alternativi, informazione insufficiente e
    infine determinate. ``DETERMINATE`` descrive completezza strutturale; non
    certifica validita, qualita o generalizzabilita scientifica.
    """

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

    if (
        not block.unit_assessments
        or compilation.abstained
        or any(
            assessment.inferability is not Inferability.INFERABLE
            for assessment in block.unit_assessments
        )
        or not _decisive_core_is_complete(block)
        or _author_assertion_is_only_decisive_support(block)
    ):
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
