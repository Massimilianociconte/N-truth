"""Output positivo prudente del compilatore di disegni (PRD v6, sez. 20).

Il modulo non sceglie un test, non costruisce formule e non certifica il
disegno. Trasforma soltanto fatti e inferenze gia presenti nel report in una
vista utile, evidence-linked e chiaramente condizionale quando necessario.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ntruth.design.schema import DesignCompilation
from ntruth.schemas.core import (
    Determinability,
    EvidenceType,
    ProvenanceKind,
    Severity,
    stable_id,
)
from ntruth.schemas.experiment import (
    CountKind,
    CountRecord,
    ExperimentBlock,
    Inferability,
    UnitAssessment,
)
from ntruth.schemas.report import (
    BlockPositiveOutput,
    ChecklistStatus,
    DriverChecklistItem,
    MethodsStatement,
    NTableRow,
    PositivePathStatus,
    ReportStatement,
    StatementLayer,
)
from ntruth.verifier.output_policy import apply_output_policy

DRIVER_BASE = "https://nc3rs.org.uk/3rs-resources/driver-recommendations"

_DRIVER_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("DRIVER-1", "Experimental unit", f"{DRIVER_BASE}/experimental-unit"),
    ("DRIVER-2", "Risk of bias", f"{DRIVER_BASE}/risk-bias"),
    ("DRIVER-3", "Experimental model", f"{DRIVER_BASE}/experimental-model"),
    ("DRIVER-4", "Experimental procedures", f"{DRIVER_BASE}/experimental-procedures"),
    (
        "DRIVER-5",
        "Experimental groups and exclusions",
        f"{DRIVER_BASE}/experimental-groups-and-exclusions",
    ),
    (
        "DRIVER-6",
        "Data availability and presentation",
        f"{DRIVER_BASE}/data-availability-and-presentation",
    ),
)


def build_positive_output(
    block: ExperimentBlock,
    *,
    language: str = "it",
    limits: Iterable[str] = (),
    compilation: DesignCompilation | None = None,
) -> BlockPositiveOutput:
    """Costruisce una vista utile senza oltrepassare l'evidenza del blocco."""

    block = apply_output_policy(block)
    path_status, status_reason = _path_status(block, language, compilation=compilation)
    n_table = tuple(_n_row(assessment) for assessment in block.unit_assessments)
    statements = _statements(block, limits=limits, language=language)
    methods = _methods_statement(block, path_status=path_status, language=language)
    published_counts, diagnostic_counts, suppressed_count_ids = _published_count_records(block)
    compiler_questions = compilation.elicitation.questions if compilation is not None else ()
    questions_by_id = {
        question.id: question for question in (*block.questions, *compiler_questions)
    }
    questions = sorted(
        questions_by_id.values(),
        key=lambda question: (
            not bool(getattr(question, "decisive", False)),
            -int(getattr(question, "priority", 0)),
            question.id,
        ),
    )
    plausible_graph_set = (
        block.plausible_graph_set
        if block.determinability is Determinability.MULTIPLE_PLAUSIBLE_GRAPHS
        else None
    )
    discriminating_question = (
        next(
            (
                question
                for question in block.questions
                if question.id == plausible_graph_set.discriminating_question_id
            ),
            None,
        )
        if plausible_graph_set is not None
        else None
    )
    return BlockPositiveOutput(
        block_id=block.id,
        determinability=block.determinability,
        path_status=path_status,
        status_reason=status_reason,
        methods_statement=methods,
        n_table=n_table,
        count_records=published_counts,
        diagnostic_count_records=diagnostic_counts,
        suppressed_count_record_ids=suppressed_count_ids,
        exclusion_records=block.exclusion_records,
        contradictions=block.contradictions,
        plausible_graph_set=plausible_graph_set,
        discriminating_question=discriminating_question,
        driver_checklist=_driver_checklist(block, language=language),
        statements=statements,
        candidate_analysis_strategies=_candidate_strategies(block, language=language),
        decisive_question_ids=tuple(
            question.id for question in questions if bool(getattr(question, "decisive", False))
        ),
    )


def _published_count_records(
    block: ExperimentBlock,
) -> tuple[tuple[CountRecord, ...], tuple[CountRecord, ...], tuple[str, ...]]:
    """Filtra la vista positiva senza cancellare i fatti dal blocco sorgente."""

    published: list[CountRecord] = []
    diagnostic: list[CountRecord] = []
    suppressed: list[str] = []
    for count in block.count_records:
        if count.diagnostic_only or count.kind is CountKind.EFFECTIVE_N:
            diagnostic.append(count)
            continue
        numeric = any(
            value is not None for value in (count.value, count.lower_bound, count.upper_bound)
        )
        if (
            block.determinability is not Determinability.DETERMINATE
            and count.kind is CountKind.INDEPENDENT_N
            and numeric
        ):
            suppressed.append(count.count_id)
        else:
            published.append(count)
    return tuple(published), tuple(diagnostic), tuple(suppressed)


def _path_status(
    block: ExperimentBlock,
    language: str,
    *,
    compilation: DesignCompilation | None,
) -> tuple[PositivePathStatus, str]:
    if block.determinability is Determinability.MULTIPLE_PLAUSIBLE_GRAPHS:
        return (
            PositivePathStatus.INCOMPLETE,
            (
                "Sono conservati piu grafi compatibili con le evidenze: nessuna alternativa e selezionata automaticamente."
                if language == "it"
                else "Multiple graphs remain compatible with the evidence: no alternative is selected automatically."
            ),
        )
    if block.determinability is not Determinability.DETERMINATE:
        state_label = block.determinability.value
        return (
            (
                PositivePathStatus.CONDITIONAL
                if block.determinability is Determinability.CONDITIONALLY_DETERMINATE
                else PositivePathStatus.INCOMPLETE
            ),
            (
                f"Stato {state_label}: unita sperimentale e n singoli non sono pubblicabili."
                if language == "it"
                else (f"State {state_label}: a single experimental unit and n cannot be published.")
            ),
        )
    if compilation is not None and compilation.abstained:
        return (
            PositivePathStatus.INCOMPLETE,
            (
                "Il compilatore si astiene finche non sono risolti i campi decisivi del disegno e dell'estimando."
                if language == "it"
                else "The compiler abstains until decisive design and estimand fields are resolved."
            ),
        )
    unresolved = any(item.status == "unresolved" for item in block.contradictions)
    blocking_alert = any(
        alert.severity in {Severity.CRITICAL, Severity.HIGH, Severity.INSUFFICIENT}
        for alert in block.alerts
    )
    has_independent_n = any(
        assessment.n_independent is not None for assessment in block.unit_assessments
    )
    conditional = any(
        assessment.inferability in {Inferability.CONDITIONAL, Inferability.REQUIRES_CONFIRMATION}
        or bool(getattr(assessment, "conditional_scenarios", ()))
        for assessment in block.unit_assessments
    )
    if not block.unit_assessments or not has_independent_n:
        return (
            PositivePathStatus.INCOMPLETE,
            (
                "Mancano elementi sufficienti per una bozza Methods completa."
                if language == "it"
                else "There is not enough information for a complete Methods draft."
            ),
        )
    if unresolved or blocking_alert or conditional:
        return (
            PositivePathStatus.CONDITIONAL,
            (
                "La ricostruzione e utilizzabile soltanto con le condizioni e domande indicate."
                if language == "it"
                else "The reconstruction is usable only under the stated conditions and questions."
            ),
        )
    return (
        PositivePathStatus.READY_FOR_REVIEW,
        (
            "Bozza deterministica pronta per revisione umana; non e una certificazione."
            if language == "it"
            else "Deterministic draft ready for human review; this is not a certification."
        ),
    )


def _n_row(assessment: UnitAssessment) -> NTableRow:
    scenarios: list[dict[str, object]] = []
    for scenario in getattr(assessment, "conditional_scenarios", ()):
        if hasattr(scenario, "model_dump"):
            scenarios.append(scenario.model_dump(mode="json"))
        elif isinstance(scenario, dict):
            scenarios.append(dict(scenario))
    return NTableRow(
        assessment_id=assessment.id,
        scope=assessment.scope.describe(),
        biological_unit=_enum_text(assessment.biological_unit),
        experimental_unit=_enum_text(assessment.experimental_unit),
        observational_unit=_enum_text(assessment.observational_unit),
        analytical_unit=_enum_text(assessment.analytical_unit),
        n_planned=assessment.n_planned,
        n_declared=assessment.n_declared,
        n_observational=assessment.n_observational,
        n_analytical=assessment.n_analytical,
        n_independent=assessment.n_independent,
        n_allocated=assessment.n_allocated,
        n_treated=assessment.n_treated,
        n_observed=assessment.n_observed,
        n_excluded=assessment.n_excluded,
        n_analysed=assessment.n_analysed,
        n_analyzed=assessment.n_analysed,
        biological_source_count=assessment.biological_source_count,
        # La tabella primaria dei conteggi non pubblica effective_n: il valore
        # diagnostico, se presente, vive esclusivamente nei count_records con
        # diagnostic_only=true e non puo "sanare" la replicazione.
        effective_n=None,
        inferability=assessment.inferability.value,
        conditional_scenarios=tuple(scenarios),
        evidence_ids=assessment.evidence_ids,
    )


def _methods_statement(
    block: ExperimentBlock,
    *,
    path_status: PositivePathStatus,
    language: str,
) -> MethodsStatement:
    clauses: list[str] = []
    evidence_ids: list[str] = []
    for assessment in block.unit_assessments:
        if assessment.experimental_unit is None:
            continue
        factor = block.factor(assessment.scope.factor_id) if assessment.scope.factor_id else None
        endpoint = (
            block.endpoint(assessment.scope.endpoint_id) if assessment.scope.endpoint_id else None
        )
        scope = " / ".join(
            value
            for value in (factor.name if factor else "", endpoint.name if endpoint else "")
            if value
        )
        n_text = (
            str(assessment.n_independent)
            if assessment.n_independent is not None
            else ("non determinabile" if language == "it" else "not determinable")
        )
        if language == "it":
            clause = (
                f"Per lo scope {scope or assessment.scope.describe()}, l'unita sperimentale "
                f"candidata e {assessment.experimental_unit}; il numero di unita indipendenti "
                f"e {n_text}."
            )
            if (
                assessment.observational_unit is not None
                and assessment.observational_unit != assessment.experimental_unit
            ):
                clause += (
                    f" Le misure su {assessment.observational_unit} sono osservazioni interne "
                    "all'unita sperimentale e non repliche indipendenti aggiuntive."
                )
        else:
            clause = (
                f"For {scope or assessment.scope.describe()}, the candidate experimental unit "
                f"is {assessment.experimental_unit}; the number of independent units is {n_text}."
            )
            if (
                assessment.observational_unit is not None
                and assessment.observational_unit != assessment.experimental_unit
            ):
                clause += (
                    f" Measurements on {assessment.observational_unit} are observations within "
                    "the experimental unit and do not add independent replicates."
                )
        clauses.append(clause)
        evidence_ids.extend(assessment.evidence_ids)

    if not clauses:
        clauses.append(
            "Bozza non generata: l'unita sperimentale non e determinabile dai materiali disponibili."
            if language == "it"
            else "Draft not generated: the experimental unit cannot be determined from the available material."
        )

    limitations: list[str] = []
    if path_status is not PositivePathStatus.READY_FOR_REVIEW:
        limitations.append(
            "Il testo resta condizionale e richiede la risoluzione delle domande aperte."
            if language == "it"
            else "The text remains conditional and requires resolution of the open questions."
        )
    limitations.append(
        "La bozza descrive il disegno ricostruito; non attesta validita statistica o conformita."
        if language == "it"
        else "The draft describes the reconstructed design; it does not attest statistical validity or compliance."
    )
    return MethodsStatement(
        text=" ".join(clauses),
        language=language,
        evidence_ids=tuple(dict.fromkeys(evidence_ids)),
        status=path_status,
        limitations=tuple(limitations),
    )


def _statements(
    block: ExperimentBlock,
    *,
    limits: Iterable[str],
    language: str,
) -> tuple[ReportStatement, ...]:
    result: list[ReportStatement] = []
    evidence_by_id = {evidence.id: evidence for evidence in block.evidence}
    for statement in block.n_statements:
        layer, source = _n_statement_classification(
            statement,
            evidence_by_id=evidence_by_id,
        )
        text = statement.raw_text.strip() or (
            f"n dichiarato: {statement.value} {statement.entity_type}"
            if language == "it"
            else f"declared n: {statement.value} {statement.entity_type}"
        )
        result.append(
            ReportStatement(
                id=stable_id("rst", block.id, layer.value, statement.id),
                layer=layer,
                text=text,
                evidence_ids=statement.evidence_ids,
                source=source,
            )
        )
    for assessment in block.unit_assessments:
        if assessment.rationale.strip():
            result.append(
                ReportStatement(
                    id=stable_id("rst", block.id, "inference", assessment.id),
                    layer=StatementLayer.INFERENCE,
                    text=assessment.rationale.strip(),
                    evidence_ids=assessment.evidence_ids,
                )
            )
        for index, scenario in enumerate(getattr(assessment, "conditional_scenarios", ())):
            assumption = _scenario_assumption(scenario)
            if assumption:
                result.append(
                    ReportStatement(
                        id=stable_id("rst", block.id, "hypothesis", assessment.id, index),
                        layer=StatementLayer.HYPOTHESIS,
                        text=assumption,
                        evidence_ids=tuple(getattr(scenario, "evidence_ids", ())),
                    )
                )
    for index, limit in enumerate(dict.fromkeys(limits)):
        result.append(
            ReportStatement(
                id=stable_id("rst", block.id, "limit", index, limit),
                layer=StatementLayer.LIMITATION,
                text=limit,
                source="report_limit",
            )
        )
    return tuple(result)


def _n_statement_classification(
    statement: Any,
    *,
    evidence_by_id: dict[str, Any],
) -> tuple[StatementLayer, str]:
    """Classifica un count senza trasformare un'autovalutazione in fatto.

    ``AUTHOR_ASSERTION`` ha precedenza anche in presenza di evidenze miste. In
    assenza di un tipo osservazionale esplicito il fallback e prudente: una
    frase estratta dalla fonte resta un'asserzione, non una verita biologica.
    """

    evidence_types = {
        evidence.evidence_type
        for evidence_id in statement.evidence_ids
        if (evidence := evidence_by_id.get(evidence_id)) is not None
        and evidence.evidence_type is not None
    }
    if EvidenceType.CONFLICTING_EVIDENCE in evidence_types:
        return StatementLayer.ASSERTION, "conflicting_evidence"
    if EvidenceType.USER_CONFIRMATION in evidence_types:
        return StatementLayer.ASSERTION, "user_confirmation"
    if EvidenceType.REVIEW_COMMENT in evidence_types:
        return StatementLayer.ASSERTION, "review_comment"
    if EvidenceType.AUTHOR_ASSERTION in evidence_types:
        return StatementLayer.ASSERTION, "author_assertion"
    if evidence_types & {EvidenceType.MODEL_INFERENCE}:
        return StatementLayer.HYPOTHESIS, "model_inference"
    if evidence_types & {EvidenceType.DERIVED_FACT}:
        return StatementLayer.INFERENCE, "derived_fact"
    if evidence_types and evidence_types <= {
        EvidenceType.STRUCTURAL_FACT,
        EvidenceType.PROCEDURAL_EVENT,
        EvidenceType.SAMPLE_METADATA,
        EvidenceType.IMAGE_METADATA,
        EvidenceType.STATISTICAL_CODE,
    }:
        source = "+".join(sorted(item.value.casefold() for item in evidence_types))
        return StatementLayer.FACT, source

    origin = statement.provenance.origin
    if origin is ProvenanceKind.MODEL:
        return StatementLayer.HYPOTHESIS, "model_inference"
    if origin in {ProvenanceKind.DERIVED, ProvenanceKind.RULE}:
        return StatementLayer.INFERENCE, "deterministic_derivation"
    if origin is ProvenanceKind.USER:
        return StatementLayer.ASSERTION, "user_confirmation"
    if origin is ProvenanceKind.ADJUDICATION:
        return StatementLayer.ASSERTION, "adjudication"
    return StatementLayer.ASSERTION, "untyped_source_assertion"


def _driver_checklist(block: ExperimentBlock, *, language: str) -> tuple[DriverChecklistItem, ...]:
    evidence = tuple(
        dict.fromkeys(
            evidence_id
            for assessment in block.unit_assessments
            for evidence_id in assessment.evidence_ids
        )
    )
    unit_present = any(
        assessment.experimental_unit is not None and assessment.biological_unit is not None
        for assessment in block.unit_assessments
    )
    allocation_present = any(
        getattr(factor, "allocation_level", None) is not None
        or getattr(factor, "assignment_level", None) is not None
        for factor in block.factors
    )
    application_present = any(
        getattr(factor, "application_level", None) is not None for factor in block.factors
    )
    groups_present = any(factor.levels for factor in block.factors)
    exclusions_present = any("exclusion" in process.kind.casefold() for process in block.processes)

    statuses = (
        ChecklistStatus.PRESENT if unit_present else ChecklistStatus.MISSING,
        ChecklistStatus.PARTIAL if allocation_present else ChecklistStatus.NOT_ASSESSED,
        ChecklistStatus.PARTIAL if unit_present else ChecklistStatus.NOT_ASSESSED,
        ChecklistStatus.PARTIAL if application_present else ChecklistStatus.NOT_ASSESSED,
        ChecklistStatus.PARTIAL
        if groups_present or exclusions_present
        else ChecklistStatus.NOT_ASSESSED,
        ChecklistStatus.NOT_ASSESSED,
    )
    notes_it = (
        "Unita biologica e sperimentale ricostruite; verificare sempre con un esperto.",
        "E valutata solo la struttura di allocazione disponibile; randomizzazione, masking e altre fonti di bias non sono certificati.",
        "Il modello biologico e rappresentato solo per le entita presenti nel bundle.",
        "Il livello di applicazione e riportato separatamente quando disponibile; le procedure non sono validate.",
        "Gruppi ed esclusioni sono riportati solo se espliciti nelle fonti.",
        "Disponibilita, condivisione e presentazione dei dati non sono valutate automaticamente.",
    )
    notes_en = (
        "Biological and experimental units were reconstructed; always verify them with an expert.",
        "Only the available allocation structure is assessed; randomisation, masking and other bias sources are not certified.",
        "The experimental model covers only entities present in the bundle.",
        "Application level is reported separately when available; procedures are not validated.",
        "Groups and exclusions are reported only when explicit in the sources.",
        "Data availability, sharing and presentation are not automatically assessed.",
    )
    notes = notes_it if language == "it" else notes_en
    return tuple(
        DriverChecklistItem(
            item_id=item_id,
            title=title,
            status=status,
            note=note,
            evidence_ids=evidence
            if index < 5 and status is not ChecklistStatus.NOT_ASSESSED
            else (),
            source_url=url,
        )
        for index, ((item_id, title, url), status, note) in enumerate(
            zip(_DRIVER_ITEMS, statuses, notes, strict=True)
        )
    )


def _candidate_strategies(block: ExperimentBlock, *, language: str) -> tuple[str, ...]:
    strategies: list[str] = []
    nested_measurements = any(
        assessment.experimental_unit is not None
        and assessment.observational_unit is not None
        and assessment.experimental_unit != assessment.observational_unit
        for assessment in block.unit_assessments
    )
    clustering_declared = any(
        bool(getattr(model, "declared_clustering", ())) or bool(model.accounts_for)
        for model in block.models
    )
    if nested_measurements:
        strategies.append(
            "Aggregare le misure entro ciascuna unita sperimentale, se coerente con l'estimando."
            if language == "it"
            else "Aggregate measurements within each experimental unit when consistent with the estimand."
        )
        strategies.append(
            "Usare una strategia di analisi che rappresenti esplicitamente la dipendenza gerarchica."
            if language == "it"
            else "Use an analysis strategy that explicitly represents hierarchical dependence."
        )
    if clustering_declared:
        strategies.append(
            "Verificare che il clustering dichiarato nel codice corrisponda al grafo confermato."
            if language == "it"
            else "Verify that clustering declared in code matches the confirmed graph."
        )
    if any(assessment.n_independent is None for assessment in block.unit_assessments):
        strategies.append(
            "Risolvere le domande decisive prima di scegliere qualunque analisi inferenziale."
            if language == "it"
            else "Resolve the decisive questions before choosing any inferential analysis."
        )
    return tuple(dict.fromkeys(strategies))


def _scenario_assumption(scenario: Any) -> str:
    if isinstance(scenario, dict):
        return str(
            scenario.get("conditional_on")
            or scenario.get("assumption")
            or scenario.get("condition")
            or ""
        ).strip()
    return str(
        getattr(scenario, "conditional_on", "")
        or getattr(scenario, "assumption", "")
        or getattr(scenario, "condition", "")
    ).strip()


def _enum_text(value: object | None) -> str | None:
    return str(value) if value is not None else None


__all__ = ["DRIVER_BASE", "build_positive_output"]
