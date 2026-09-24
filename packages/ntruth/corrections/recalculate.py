"""Ricalcolo rules-only dopo una correzione umana (PRD FR-026)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from time import perf_counter

from ntruth.calibration.abstention import enforce_evidence_floor, evaluate_abstention
from ntruth.corrections.engine import CorrectionLedger
from ntruth.design import compile_experiment_block, finalize_experiment_block_compilation
from ntruth.graph.builder import materialize_design_graph
from ntruth.graph.determinability import derive_determinability
from ntruth.graph.units import resolve_units
from ntruth.graph.validation import assert_valid_experiment_block
from ntruth.pipeline import BlockAnalysis, _exclusion_records, _supported_by_release_profile
from ntruth.rules.engine import apply_rules
from ntruth.schemas.core import Determinability, EvidenceSpan, stable_id
from ntruth.schemas.document import DocumentIR
from ntruth.schemas.experiment import (
    CountRecord,
    ExclusionRecord,
    ExperimentBlock,
    GraphStatus,
    ProcessFact,
    Question,
    TriState,
)
from ntruth.schemas.graph import GraphViolation
from ntruth.schemas.rules import Ruleset
from ntruth.verifier import apply_output_policy, verify_block


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
    changed_roots = set(ledger.active_changed_roots)

    count_records = current.count_records
    n_statements = current.n_statements
    if "count_records" in changed_roots:
        # CountRecord e il contratto v6 autorevole. Il resolver usa ancora un
        # adapter NStatement, dal quale effective_n resta intenzionalmente fuori.
        n_statements = tuple(
            statement for count in count_records if (statement := count.to_legacy()) is not None
        )
    elif "n_statements" in changed_roots:
        # Compatibilita con patch create prima del contratto canonico v6.
        projected = tuple(CountRecord.from_legacy(item) for item in n_statements)
        projected_by_id = {item.count_id: item for item in projected}
        legacy_managed_ids = {
            *(item.id for item in original.block.n_statements),
            *(item.id for item in n_statements),
        }
        merged: list[CountRecord] = []
        emitted: set[str] = set()
        for count in count_records:
            if count.count_id in legacy_managed_ids:
                replacement = projected_by_id.get(count.count_id)
                if replacement is not None:
                    merged.append(replacement)
                    emitted.add(replacement.count_id)
                continue
            # Record v6 non rappresentabili nel legacy (in particolare
            # effective_n diagnostico) non vengono cancellati da una patch a
            # un altro NStatement.
            merged.append(count)
            emitted.add(count.count_id)
        merged.extend(item for item in projected if item.count_id not in emitted)
        count_records = tuple(merged)
    elif count_records and not n_statements:
        n_statements = tuple(
            statement for count in count_records if (statement := count.to_legacy()) is not None
        )

    exclusion_records = current.exclusion_records
    processes = current.processes
    if "exclusion_records" in changed_roots:
        # ExclusionRecord e il contratto v6 autorevole. I predicati usano
        # ancora ProcessFact: rigeneriamo soltanto il sottoinsieme exclusion,
        # preservando pooling, blinding, batch e gli altri processi.
        processes = (
            *(item for item in processes if "exclusion" not in item.kind.casefold()),
            *_processes_from_exclusion_records(exclusion_records, current),
        )

    hierarchy = materialize_design_graph(
        current.hierarchy,
        block_id=current.id,
        factors=current.factors,
        contrasts=current.contrasts,
        endpoints=current.endpoints,
        models=current.models,
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
        processes=processes,
        n_statements=n_statements,
        contradictions=current.contradictions,
        questions=_open_builder_questions(original.build.questions, current),
    )

    if "processes" in changed_roots and "exclusion_records" not in changed_roots:
        exclusion_records = _exclusion_records(build)

    candidate = current.model_copy(
        update={
            "hierarchy": hierarchy,
            "n_statements": n_statements,
            "count_records": count_records,
            "exclusion_records": exclusion_records,
            "processes": processes,
            "unit_assessments": (),
            "alerts": (),
            "questions": (),
        }
    )

    # Alcune violazioni del builder descrivono candidate facts scartati prima
    # che possano essere materializzati nel grafo (per esempio un'assegnazione
    # tabulare senza istanza). Una patch sul blocco non puo riparare quei fatti:
    # devono quindi rimanere bloccanti finche le fonti non vengono corrette e
    # reimportate. Le violazioni strutturali del blocco, invece, vengono
    # ricalcolate sullo snapshot corretto e possono essere realmente risolte.
    source_violations = (
        *original.build.violations,
        *_evidence_locator_violations(current.evidence, original.document),
    )
    preflight = verify_block(
        candidate,
        check_output_policy=False,
        additional_violations=source_violations,
    )
    if preflight.violations:
        invalid_block = apply_output_policy(
            candidate.model_copy(
                update={
                    "graph_status": GraphStatus.INVALID,
                    "determinability": Determinability.INVALID_GRAPH,
                }
            )
        )
        abstention = evaluate_abstention(original.document, build, ())
        verification = verify_block(
            invalid_block,
            check_output_policy=False,
            # ``apply_output_policy`` rimuove il fatto illecito dal payload
            # pubblico, non la causa hard gia dimostrata dal preflight.
            additional_violations=preflight.violations,
        )
        compilation = finalize_experiment_block_compilation(
            invalid_block,
            supported_profile=_supported_by_release_profile(
                invalid_block,
                original.release_profile,
            ),
            verification_valid=not verification.violations,
        )
        elapsed_ms = (perf_counter() - started) * 1000
        return CorrectionRecalculation(
            analysis=BlockAnalysis(
                document=original.document,
                block=invalid_block,
                build=build,
                abstention=abstention,
                evaluations=(),
                compilation=compilation,
                verification=verification,
                release_profile=original.release_profile,
                rule_warnings=(
                    "Regole non eseguite: il verificatore hard ha rifiutato il grafo corretto.",
                ),
            ),
            elapsed_ms=elapsed_ms,
        )

    # Una riparazione umana che elimina tutte le violazioni strutturali non
    # deve restare artificialmente INVALID_GRAPH solo perche l'editor non ha
    # scritto anche un campo derivato. La transizione e auditabile nel ledger.
    if candidate.graph_status is GraphStatus.INVALID and ledger.active_correction_ids:
        candidate = candidate.model_copy(update={"graph_status": GraphStatus.HUMAN_CONFIRMED})
    assert_valid_experiment_block(candidate)
    assessments, resolver_questions = resolve_units(current.id, build)
    assessments = enforce_evidence_floor(assessments, original.document)
    rule_run = apply_rules(
        current.id,
        build,
        assessments,
        ruleset,
        lang=lang,
        evidence_by_id={item.id: item for item in current.evidence},
    )
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
    preliminary_compilation = compile_experiment_block(block)
    supported_profile = _supported_by_release_profile(block, original.release_profile)
    block = block.model_copy(
        update={
            "determinability": derive_determinability(
                block,
                preliminary_compilation,
                supported_profile=supported_profile,
            )
        }
    )
    block = apply_output_policy(block)
    verification = verify_block(block, additional_violations=source_violations)
    compilation = finalize_experiment_block_compilation(
        block,
        supported_profile=supported_profile,
        verification_valid=not verification.violations,
    )
    elapsed_ms = (perf_counter() - started) * 1000
    return CorrectionRecalculation(
        analysis=BlockAnalysis(
            document=original.document,
            block=block,
            build=build,
            abstention=abstention,
            evaluations=rule_run.evaluations,
            compilation=compilation,
            verification=verification,
            release_profile=original.release_profile,
            rule_warnings=rule_run.warnings,
        ),
        elapsed_ms=elapsed_ms,
    )


_EXCLUDED_COUNT = re.compile(r"(?:^|\b)excluded_count\s*=\s*(?P<value>\d+)(?:\b|$)")


def _processes_from_exclusion_records(
    records: tuple[ExclusionRecord, ...],
    block: ExperimentBlock,
) -> tuple[ProcessFact, ...]:
    """Adatta il registro canonico ai predicati legacy del rules engine."""

    endpoint_names = {item.id: item.name for item in block.endpoints}
    processes: list[ProcessFact] = []
    for record in records:
        count_match = _EXCLUDED_COUNT.search(record.impact or "")
        processes.append(
            ProcessFact(
                id=stable_id("prc", "canonical-exclusion", record.id),
                kind="exclusion",
                detail=record.reason or "reason not reported",
                node_type=record.unit_type,
                value=(int(count_match.group("value")) if count_match is not None else None),
                endpoint_hint=endpoint_names.get(record.endpoint_id or ""),
                group_hint=record.group,
                evidence_ids=record.evidence_ids,
                provenance=record.provenance,
            )
        )
    return tuple(processes)


_SCOPED_FIELD = re.compile(
    r"^(?P<object>factor|endpoint|n_statement)\[(?P<key>[^]]+)]\.(?P<field>.+)$"
)
_COLLECTION_FIELD = re.compile(r"^(?P<object>count|exclusions)\[(?P<key>[^]]+)]$")


def _open_builder_questions(
    questions: tuple[Question, ...],
    block: ExperimentBlock,
) -> tuple[Question, ...]:
    """Rimuove soltanto i gap che una patch ha reso esplicitamente risolti.

    Le domande del builder sono state create prima della correzione e non
    possono essere copiate alla cieca. I missing-field non riconosciuti restano
    conservativamente aperti.
    """

    return tuple(
        question
        for question in questions
        if not _missing_field_is_satisfied(question.missing_field, block)
    )


def _missing_field_is_satisfied(
    missing_field: str | None,
    block: ExperimentBlock,
) -> bool:
    if not missing_field:
        return False
    if missing_field == "factors":
        return bool(block.factors)
    if missing_field == "contrast.endpoint_ids":
        return bool(block.contrasts) and all(contrast.endpoint_ids for contrast in block.contrasts)
    if missing_field == "factor.independently_assigned":
        return bool(block.factors) and all(
            factor.independently_assigned is not TriState.UNKNOWN for factor in block.factors
        )
    if missing_field == "n_statement.value":
        return not any(item.status == "unresolved" for item in block.contradictions) and any(
            statement.value is not None for statement in block.n_statements
        )
    if missing_field == "n_statement.entity_type":
        # Il builder legacy non include l'ID della menzione nella domanda.
        # Si chiude quindi soltanto quando tutte le menzioni sono state legate
        # esplicitamente a un livello del grafo.
        return bool(block.n_statements) and all(
            statement.node_type is not None or statement.scope.unit_type is not None
            for statement in block.n_statements
        )

    collection_match = _COLLECTION_FIELD.fullmatch(missing_field)
    if collection_match is not None:
        key = collection_match.group("key").casefold()
        if collection_match.group("object") == "count":
            if any(item.status == "unresolved" for item in block.contradictions):
                return False
            return any(
                count.scope.unit_type is not None
                and str(count.scope.unit_type).casefold() == key
                and any(
                    value is not None
                    for value in (count.value, count.lower_bound, count.upper_bound)
                )
                for count in block.count_records
            )
        matching_exclusions = tuple(
            exclusion
            for exclusion in block.exclusion_records
            if str(exclusion.unit_type).casefold() == key
        )
        return bool(matching_exclusions) and all(
            exclusion.endpoint_id is not None
            and any((exclusion.factor_id, exclusion.contrast_id, exclusion.group))
            for exclusion in matching_exclusions
        )

    match = _SCOPED_FIELD.fullmatch(missing_field)
    if match is None:
        return False
    object_kind = match.group("object")
    key = match.group("key").casefold()
    field_name = match.group("field")
    if object_kind == "factor":
        factor = next(
            (
                item
                for item in block.factors
                if item.id.casefold() == key or item.name.casefold() == key
            ),
            None,
        )
        if factor is None:
            return False
        if field_name == "independently_assigned":
            return factor.independently_assigned is not TriState.UNKNOWN
        if field_name in {"allocation_level", "application_level"}:
            return getattr(factor, field_name) is not None
        return False
    if object_kind == "endpoint":
        endpoint = next(
            (
                item
                for item in block.endpoints
                if item.id.casefold() == key or item.name.casefold() == key
            ),
            None,
        )
        return (
            endpoint is not None
            and field_name == "measured_on"
            and endpoint.measured_on is not None
        )
    statement = next(
        (item for item in block.n_statements if item.id.casefold() == key),
        None,
    )
    if statement is None:
        return False
    if field_name == "scope.endpoint_id":
        return statement.scope.endpoint_id is not None
    if field_name == "scope.factor_id":
        return statement.scope.factor_id is not None
    return False


def _evidence_locator_violations(
    evidence_spans: tuple[EvidenceSpan, ...],
    document: DocumentIR,
) -> tuple[GraphViolation, ...]:
    """Verifica gli overlay umani contro il Document IR immutabile."""

    known_files = {item.id for item in document.files}
    sections = {(item.file_id, item.id): item for item in document.sections}
    tables = {(item.file_id, item.id): item for item in document.tables}
    violations: list[GraphViolation] = []
    for span in evidence_spans:
        span_id = span.id
        file_id = span.file_id
        text = span.text
        start = span.start
        end = span.end
        section_id = span.section_id
        cell = span.cell
        if file_id not in known_files:
            violations.append(
                GraphViolation(
                    code="evidence_unknown_file",
                    message=f"evidence {span_id}: file_id sconosciuto {file_id}",
                )
            )
            continue
        # Una cella vuota e comunque un locator sorgente verificabile: il
        # confronto esatto con il Document IR avviene sotto. Per gli span
        # testuali, invece, una stringa vuota non puo provare alcun fatto.
        if not text and cell is None:
            violations.append(
                GraphViolation(
                    code="evidence_empty_text",
                    message=f"evidence {span_id}: il testo originale non puo essere vuoto",
                )
            )
        has_offsets = start is not None and end is not None
        has_section_locator = section_id is not None or bool(span.section_title)
        if cell is None and not has_offsets and not has_section_locator:
            violations.append(
                GraphViolation(
                    code="evidence_missing_verifiable_locator",
                    message=(
                        f"evidence {span_id}: file_id o page senza offset, cella o "
                        "sezione verificabile non bastano"
                    ),
                )
            )
        if (start is None) != (end is None):
            violations.append(
                GraphViolation(
                    code="evidence_incomplete_offsets",
                    message=f"evidence {span_id}: start/end devono essere presenti insieme",
                )
            )
        elif start is not None and end is not None:
            source = document.texts.get(file_id, "")
            if end > len(source) or source[start:end] != text:
                violations.append(
                    GraphViolation(
                        code="evidence_text_mismatch",
                        message=f"evidence {span_id}: testo e coordinate non coincidono",
                    )
                )
        # I fogli usano table/cell come locator autorevole. ``section_title``
        # ne e soltanto l'etichetta visuale (nome sheet/tabella) e non deve
        # essere confrontata con le Section del testo lineare.
        if section_id is not None and cell is None:
            section = sections.get((file_id, section_id))
            if section is None:
                violations.append(
                    GraphViolation(
                        code="evidence_unknown_section",
                        message=f"evidence {span_id}: section_id non appartiene al file",
                    )
                )
            elif (
                start is not None
                and end is not None
                and (start < section.start or end > section.end)
            ):
                violations.append(
                    GraphViolation(
                        code="evidence_outside_section",
                        message=f"evidence {span_id}: coordinate fuori dalla section",
                    )
                )
            elif span.section_title is not None and span.section_title != section.title:
                violations.append(
                    GraphViolation(
                        code="evidence_section_title_mismatch",
                        message=f"evidence {span_id}: section_title non coincide con la fonte",
                    )
                )
            elif (
                not has_offsets
                and text not in document.texts.get(file_id, "")[section.start : section.end]
            ):
                violations.append(
                    GraphViolation(
                        code="evidence_text_mismatch",
                        message=(f"evidence {span_id}: testo assente dalla section dichiarata"),
                    )
                )
        elif span.section_title and cell is None:
            matching_sections = [
                section
                for (candidate_file_id, _), section in sections.items()
                if candidate_file_id == file_id and section.title == span.section_title
            ]
            matching_text = [
                section
                for section in matching_sections
                if text in document.texts.get(file_id, "")[section.start : section.end]
            ]
            if len(matching_text) != 1:
                violations.append(
                    GraphViolation(
                        code="evidence_section_title_mismatch",
                        message=(
                            f"evidence {span_id}: section_title non identifica una sezione "
                            "univoca contenente il testo"
                        ),
                    )
                )
        if cell is not None:
            table = tables.get((file_id, cell.table_id))
            if (
                table is None
                or cell.row >= len(table.rows)
                or cell.column not in table.columns
                or table.rows[cell.row].get(cell.column, "") != text
            ):
                violations.append(
                    GraphViolation(
                        code="evidence_cell_mismatch",
                        message=f"evidence {span_id}: cella non coincide con il Document IR",
                    )
                )
    return tuple(violations)
