"""Ricalcolo rules-only dopo una correzione umana (PRD FR-026)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from time import perf_counter

from ntruth.calibration.abstention import enforce_evidence_floor, evaluate_abstention
from ntruth.corrections.engine import CorrectionLedger
from ntruth.design import compile_experiment_block
from ntruth.graph.builder import materialize_inferential_graph
from ntruth.graph.determinability import derive_determinability
from ntruth.graph.units import resolve_units
from ntruth.graph.validation import assert_valid_experiment_block
from ntruth.pipeline import BlockAnalysis
from ntruth.rules.engine import apply_rules
from ntruth.schemas.rules import Ruleset


@dataclass(frozen=True, slots=True)
class CorrectionRecalculation:
    """Blocco aggiornato e tempo del solo percorso deterministico post-patch."""

    analysis: BlockAnalysis
    elapsed_ms: float


def recalculate_corrected_block(
    original: BlockAnalysis,
    ledger: CorrectionLedger,
    ruleset: Ruleset,
    *,
    lang: str = "it",
) -> CorrectionRecalculation:
    """Ricostruisce unità, regole e astensione senza ripetere parser/estrazione.

    Tutti gli input correggibili, inclusi fatti di modello e processo, provengono
    dal blocco materializzato dal ledger. Nessun fatto scientifico o output
    derivato precedente viene reintrodotto dal BuildResult originale.
    """

    started = perf_counter()
    current = ledger.current_block
    hierarchy = materialize_inferential_graph(
        current.hierarchy,
        block_id=current.id,
        inference_targets=current.inference_targets,
        estimands=current.estimands,
    )
    build = replace(
        original.build,
        hierarchy=hierarchy,
        factors=current.factors,
        contrasts=current.contrasts,
        endpoints=current.endpoints,
        inference_targets=current.inference_targets,
        estimands=current.estimands,
        models=current.models,
        processes=current.processes,
        n_statements=current.n_statements,
        contradictions=current.contradictions,
        questions=original.build.questions,
    )

    candidate = current.model_copy(
        update={
            "hierarchy": hierarchy,
            "unit_assessments": (),
            "alerts": (),
            "questions": (),
        }
    )
    assert_valid_experiment_block(candidate)
    assessments, resolver_questions = resolve_units(current.id, build)
    assessments = enforce_evidence_floor(assessments, original.document)
    rule_run = apply_rules(current.id, build, assessments, ruleset, lang=lang)
    abstention = evaluate_abstention(original.document, build, rule_run.assessments)
    questions = tuple(
        {
            question.id: question
            for question in (*build.questions, *resolver_questions, *rule_run.questions)
        }.values()
    )
    block = candidate.model_copy(
        update={
            "unit_assessments": rule_run.assessments,
            "alerts": rule_run.alerts,
            "questions": questions,
            "data_sufficiency": abstention.sufficiency,
        }
    )
    assert_valid_experiment_block(block)
    compilation = compile_experiment_block(block)
    block = block.model_copy(update={"determinability": derive_determinability(block, compilation)})
    elapsed_ms = (perf_counter() - started) * 1000
    return CorrectionRecalculation(
        analysis=BlockAnalysis(
            document=original.document,
            block=block,
            build=build,
            abstention=abstention,
            evaluations=rule_run.evaluations,
            compilation=compilation,
            rule_warnings=rule_run.warnings,
        ),
        elapsed_ms=elapsed_ms,
    )
