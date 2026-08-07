"""Rules engine deterministico (PRD 8, FR-018, FR-019, FR-022).

Il motore legge soltanto il grafo validato e gli assessment derivati. Non vede
il testo grezzo e non puo essere sostituito da un prompt. Una regola che non e
valutabile viene riportata come tale: non scatta e non viene ignorata.
"""

from __future__ import annotations

import string
from collections.abc import Mapping
from dataclasses import dataclass, field

from ntruth.graph.builder import BuildResult
from ntruth.graph.index import GraphIndex
from ntruth.rules.predicates import RuleContext, UnknownPredicate, evaluate
from ntruth.schemas.core import (
    AlertClass,
    EvidenceSpan,
    EvidenceType,
    Provenance,
    ProvenanceKind,
    Severity,
    stable_id,
)
from ntruth.schemas.experiment import (
    Alert,
    Factor,
    Question,
    RiskLabel,
    UnitAssessment,
)
from ntruth.schemas.rules import PremiseTrace, Rule, RuleEvaluation, RuleOutcome, Ruleset

#: Mappa severita -> etichetta di rischio dell'assessment (PRD 15.4 layer I).
SEVERITY_TO_RISK: dict[Severity, RiskLabel] = {
    Severity.CRITICAL: RiskLabel.CRITICAL,
    Severity.HIGH: RiskLabel.LIKELY,
    Severity.MEDIUM: RiskLabel.POTENTIAL,
    Severity.INSUFFICIENT: RiskLabel.INSUFFICIENT,
    Severity.INFO: RiskLabel.NO_ISSUE,
}

_RISK_ORDER = [
    RiskLabel.NO_ISSUE,
    RiskLabel.POTENTIAL,
    RiskLabel.INSUFFICIENT,
    RiskLabel.LIKELY,
    RiskLabel.CRITICAL,
]

# ``UnitAssessment.risk`` e una vista legacy e compatta del rischio di
# pseudoreplicazione. Nel modello v3 questo rischio puo nascere sia dal disegno
# della replicazione sia dal trattamento analitico della dipendenza; gli alert
# che riguardano soltanto l'ampiezza dell'inferenza restano invece separati.
PSEUDOREPLICATION_ALERT_CLASSES = frozenset(
    {
        AlertClass.DESIGN_REPLICATION,
        AlertClass.ANALYTICAL_DEPENDENCE,
    }
)

_QUESTION_PRIORITY: dict[Severity, int] = {
    Severity.CRITICAL: 100,
    Severity.HIGH: 80,
    Severity.INSUFFICIENT: 70,
    Severity.MEDIUM: 60,
    Severity.INFO: 40,
}


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "non determinato"


@dataclass
class RuleRunResult:
    """Alert, domande e traccia completa delle valutazioni."""

    alerts: tuple[Alert, ...] = ()
    questions: tuple[Question, ...] = ()
    assessments: tuple[UnitAssessment, ...] = ()
    evaluations: tuple[RuleEvaluation, ...] = ()
    warnings: tuple[str, ...] = field(default=())


def apply_rules(
    block_id: str,
    build: BuildResult,
    assessments: tuple[UnitAssessment, ...],
    ruleset: Ruleset,
    *,
    lang: str = "it",
    evidence_by_id: Mapping[str, EvidenceSpan] | None = None,
    index: GraphIndex | None = None,
) -> RuleRunResult:
    """Applica il ruleset a ogni assessment del blocco.

    L'indice del grafo e' accettato pre-costruito (NFR-06/NFR-07): quando
    fornito non viene mai ricostruito; altrimenti il comportamento esistente
    resta invariato.
    """
    graph_index = index if index is not None else GraphIndex(build.hierarchy)
    alerts: dict[str, Alert] = {}
    questions: dict[str, Question] = {}
    evaluations: list[RuleEvaluation] = []
    warnings: list[str] = []
    risk_by_assessment: dict[str, RiskLabel] = {a.id: a.risk for a in assessments}

    for assessment in assessments:
        factor = build_factor_of(build, assessment)
        contrast = next((c for c in build.contrasts if c.id == assessment.scope.contrast_id), None)
        endpoint = next((e for e in build.endpoints if e.id == assessment.scope.endpoint_id), None)
        context = RuleContext(
            index=graph_index,
            build=build,
            assessment=assessment,
            factor=factor,
            contrast=contrast,
            endpoint=endpoint,
            evidence_by_id=evidence_by_id or {},
        )

        for rule in ruleset.rules:
            if not rule.enabled:
                #: audit esplicito: una regola disabilitata non e mai silenziosa
                #: e non viene mai eliminata dal ruleset (PRD v8 §10.11).
                evaluations.append(_disabled_rule_audit(rule, ruleset, context))
                warnings.append(
                    f"regola {rule.rule_id} disabilitata: non valutata (audit esplicito)"
                )
                continue
            evaluation, alert, rule_questions = _apply_rule(
                block_id, rule, ruleset, context, lang=lang
            )
            evaluations.append(evaluation)
            if evaluation.outcome is RuleOutcome.UNEVALUABLE:
                warnings.append(
                    f"regola {rule.rule_id} non valutabile: predicati sconosciuti "
                    f"{', '.join(evaluation.unknown_predicates)}"
                )
            if alert is not None:
                key = alert.id if rule.scope_dimension != "block" else f"{rule.rule_id}:block"
                alerts.setdefault(key, alert)
                if alert.alert_class in PSEUDOREPLICATION_ALERT_CLASSES:
                    risk = SEVERITY_TO_RISK[alert.severity]
                    current = risk_by_assessment[assessment.id]
                    if _RISK_ORDER.index(risk) > _RISK_ORDER.index(current):
                        risk_by_assessment[assessment.id] = risk
            for question in rule_questions:
                questions.setdefault(question.id, question)

    updated = tuple(a.model_copy(update={"risk": risk_by_assessment[a.id]}) for a in assessments)
    return RuleRunResult(
        alerts=tuple(alerts.values()),
        questions=tuple(
            sorted(questions.values(), key=lambda question: (-question.priority, question.id))
        ),
        assessments=updated,
        evaluations=tuple(evaluations),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def build_factor_of(build: BuildResult, assessment: UnitAssessment) -> Factor | None:
    return next((f for f in build.factors if f.id == assessment.scope.factor_id), None)


def _disabled_rule_audit(rule: Rule, ruleset: Ruleset, context: RuleContext) -> RuleEvaluation:
    """Traccia di audit per una regola disabilitata: esclusa, mai ignorata.

    Le regole disabilitate per assenza di clausola theory difendibile restano
    nel ruleset con ``theory_status=SCIENTIFIC_REVIEW_REQUIRED`` e devono
    comparire nella traccia di valutazione (PRD v8 §10.11, NFR-33).
    """
    reason = "rule_disabled"
    if rule.theory_status is not None:
        reason = f"rule_disabled:{rule.theory_status.value}"
    return _evaluation(
        rule,
        ruleset,
        RuleOutcome.NOT_APPLICABLE,
        scope_label=f"{context.assessment.scope.describe()}|{reason}",
    )


def _apply_rule(
    block_id: str,
    rule: Rule,
    ruleset: Ruleset,
    context: RuleContext,
    *,
    lang: str,
) -> tuple[RuleEvaluation, Alert | None, list[Question]]:
    scope_label = context.assessment.scope.describe()
    matched: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    trace: list[PremiseTrace] = []

    for expression in rule.normalized_preconditions():
        try:
            ok = evaluate(expression, context)
        except UnknownPredicate:
            unknown.append(expression)
            trace.append(_premise_trace(expression, None, context))
            continue
        trace.append(_premise_trace(expression, ok, context))
        (matched if ok else failed).append(expression)

    if unknown:
        return (
            _evaluation(
                rule,
                ruleset,
                RuleOutcome.UNEVALUABLE,
                matched=tuple(matched),
                failed=tuple(failed),
                unknown_predicates=tuple(unknown),
                scope_label=scope_label,
                premise_trace=tuple(trace),
            ),
            None,
            [],
        )

    if failed:
        return (
            _evaluation(
                rule,
                ruleset,
                RuleOutcome.NOT_APPLICABLE,
                matched=tuple(matched),
                failed=tuple(failed),
                scope_label=scope_label,
                premise_trace=tuple(trace),
            ),
            None,
            [],
        )

    for expression in rule.normalized_exceptions():
        try:
            result = evaluate(expression, context)
            trace.append(_premise_trace(expression, result, context))
            if result:
                return (
                    _evaluation(
                        rule,
                        ruleset,
                        RuleOutcome.EXCEPTED,
                        matched=tuple(matched),
                        triggered_exception=expression,
                        scope_label=scope_label,
                        premise_trace=tuple(trace),
                    ),
                    None,
                    [],
                )
        except UnknownPredicate:
            unknown.append(expression)
            trace.append(_premise_trace(expression, None, context))

    if unknown:
        return (
            _evaluation(
                rule,
                ruleset,
                RuleOutcome.UNEVALUABLE,
                matched=tuple(matched),
                unknown_predicates=tuple(unknown),
                scope_label=scope_label,
                premise_trace=tuple(trace),
            ),
            None,
            [],
        )

    abstention: str | None = None
    for expression in rule.normalized_abstentions():
        try:
            result = evaluate(expression, context)
        except UnknownPredicate:
            unknown.append(expression)
            trace.append(_premise_trace(expression, None, context))
            continue
        trace.append(_premise_trace(expression, result, context))
        if result:
            abstention = expression
            break

    if unknown:
        return (
            _evaluation(
                rule,
                ruleset,
                RuleOutcome.UNEVALUABLE,
                matched=tuple(matched),
                unknown_predicates=tuple(unknown),
                scope_label=scope_label,
                premise_trace=tuple(trace),
            ),
            None,
            [],
        )

    if abstention is not None:
        questions = _questions_for(block_id, rule, context)
        alert = _alert_for(
            block_id,
            rule,
            ruleset,
            context,
            abstention,
            questions,
            lang=lang,
        )
        return (
            _evaluation(
                rule,
                ruleset,
                RuleOutcome.ABSTAINED,
                matched=tuple(matched),
                scope_label=scope_label,
                triggered_abstention=abstention,
                premise_trace=tuple(trace),
                output_ids=(alert.id,),
            ),
            alert,
            questions,
        )

    evidence_gaps = _required_evidence_gaps(rule, context)
    abstention = (
        "required_evidence_missing(" + ", ".join(evidence_gaps) + ")" if evidence_gaps else None
    )
    questions = _questions_for(block_id, rule, context)
    alert = _alert_for(block_id, rule, ruleset, context, abstention, questions, lang=lang)
    outcome = RuleOutcome.ABSTAINED if evidence_gaps else RuleOutcome.FIRED
    return (
        _evaluation(
            rule,
            ruleset,
            outcome,
            matched=tuple(matched),
            triggered_abstention=abstention,
            scope_label=scope_label,
            premise_trace=tuple(trace),
            evidence_gap=evidence_gaps,
            output_ids=(alert.id,),
        ),
        alert,
        questions,
    )


def _evaluation(
    rule: Rule,
    ruleset: Ruleset,
    outcome: RuleOutcome,
    *,
    matched: tuple[str, ...] = (),
    failed: tuple[str, ...] = (),
    triggered_exception: str | None = None,
    triggered_abstention: str | None = None,
    unknown_predicates: tuple[str, ...] = (),
    scope_label: str = "",
    premise_trace: tuple[PremiseTrace, ...] = (),
    evidence_gap: tuple[str, ...] = (),
    output_ids: tuple[str, ...] = (),
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.version,
        ruleset_checksum=ruleset.checksum(),
        outcome=outcome,
        matched=matched,
        failed=failed,
        triggered_exception=triggered_exception,
        triggered_abstention=triggered_abstention,
        unknown_predicates=unknown_predicates,
        scope_label=scope_label,
        premise_trace=premise_trace,
        evidence_gap=evidence_gap,
        output_ids=output_ids,
    )


def _premise_trace(
    expression: str,
    result: bool | None,
    context: RuleContext,
) -> PremiseTrace:
    facts = [context.assessment.id]
    origins = [context.assessment.provenance.origin.value]
    if context.factor is not None:
        facts.append(context.factor.id)
        origins.append(context.factor.provenance.origin.value)
    if context.contrast is not None:
        facts.append(context.contrast.id)
        origins.append(context.contrast.provenance.origin.value)
    if context.endpoint is not None:
        facts.append(context.endpoint.id)
        origins.append(context.endpoint.provenance.origin.value)
    return PremiseTrace(
        expression=expression,
        result=result,
        fact_ids=tuple(dict.fromkeys(facts)),
        evidence_ids=tuple(dict.fromkeys(context.assessment.evidence_ids)),
        provenance_origins=tuple(dict.fromkeys(origins)),
    )


def _required_evidence_gaps(rule: Rule, context: RuleContext) -> tuple[str, ...]:
    if not rule.requires_evidence:
        return ()
    available_ids = tuple(context.assessment.evidence_ids)
    if not available_ids:
        return ("ANY",)
    if not rule.required_evidence:
        return ()
    available_types = {
        span.evidence_type
        for evidence_id in available_ids
        if (span := context.evidence_by_id.get(evidence_id)) is not None
        and span.evidence_type is not None
    }
    required: set[EvidenceType] = set()
    invalid: list[str] = []
    for value in rule.required_evidence:
        try:
            required.add(EvidenceType(value))
        except ValueError:
            invalid.append(value)
    missing = sorted(item.value for item in required - available_types)
    return tuple(sorted((*invalid, *missing)))


def _alert_for(
    block_id: str,
    rule: Rule,
    ruleset: Ruleset,
    context: RuleContext,
    abstention: str | None,
    questions: list[Question],
    *,
    lang: str,
) -> Alert:
    assessment = context.assessment
    severity = Severity.INSUFFICIENT if abstention else rule.severity
    message = _render(rule.message(lang), context)
    if abstention:
        message = f"{message} Informazione insufficiente per concludere: {_humanize(abstention)}."

    evidence_ids = tuple(assessment.evidence_ids)
    missing: list[str] = []
    if abstention:
        missing.append(_humanize(abstention))
    if not evidence_ids:
        missing.append("nessuna evidenza localizzata disponibile per questo scope")

    conflicts = (
        tuple(c.id for c in context.build.contradictions if c.status == "unresolved")
        if "contradiction_unresolved" in " ".join(rule.normalized_preconditions())
        else ()
    )

    return Alert(
        id=stable_id("alr", block_id, rule.rule_id, assessment.id),
        rule_id=rule.rule_id,
        ruleset_version=ruleset.version,
        alert_class=rule.alert_class,
        severity=severity,
        message=message,
        scope=assessment.scope,
        evidence_ids=evidence_ids,
        missing_information=tuple(dict.fromkeys(missing)),
        conflict_ids=conflicts,
        question_ids=tuple(q.id for q in questions),
        premise_confidence=_premise_confidence(context, abstention),
        requires_human_confirmation=rule.requires_human_confirmation or bool(abstention),
        provenance=Provenance(
            origin=ProvenanceKind.RULE,
            evidence_ids=evidence_ids,
            rule_id=rule.rule_id,
            ruleset_version=ruleset.version,
            derivation=", ".join(rule.normalized_preconditions()),
        ),
    )


def _premise_confidence(context: RuleContext, abstention: str | None) -> float:
    """Confidence dei fatti di ingresso, mai della conseguenza deterministica."""
    if abstention:
        return 0.5
    factor = context.factor
    base = factor.allocation_confidence if factor and factor.allocation_level else 0.6
    node_confidences = [n.confidence for n in context.build.hierarchy.nodes]
    graph_confidence = min(node_confidences) if node_confidences else 0.6
    return round(min(base, graph_confidence), 3)


def _questions_for(block_id: str, rule: Rule, context: RuleContext) -> list[Question]:
    questions: list[Question] = []
    for text in rule.questions:
        rendered = _render(text, context)
        questions.append(
            Question(
                id=stable_id("qst", block_id, rule.rule_id, rendered),
                text=rendered,
                reason=f"richiesta dalla regola {rule.rule_id}",
                scope=context.assessment.scope,
                priority=_QUESTION_PRIORITY[rule.severity],
                decisive=True,
                impact=rule.alert_class.value,
            )
        )
    return questions


def _render(template: str, context: RuleContext) -> str:
    assessment = context.assessment
    values = _SafeDict(
        experimental_unit=assessment.experimental_unit or "non determinata",
        observational_unit=assessment.observational_unit or "non determinata",
        analytical_unit=assessment.analytical_unit or "non determinata",
        biological_unit=assessment.biological_unit or "non determinata",
        n_declared=assessment.n_declared if assessment.n_declared is not None else "non riportato",
        n_observational=assessment.n_observational
        if assessment.n_observational is not None
        else "non determinato",
        n_independent=assessment.n_independent
        if assessment.n_independent is not None
        else "non determinabile",
        factor=context.factor.name if context.factor else "non determinato",
        contrast=context.contrast.label if context.contrast else "non determinato",
        endpoint=context.endpoint.name if context.endpoint else "non determinato",
    )
    try:
        return string.Formatter().vformat(template, (), values)
    except (IndexError, KeyError, ValueError):  # pragma: no cover - template malformato
        return template


def _humanize(expression: str) -> str:
    """Rende leggibile una condizione di astensione nel messaggio."""
    readable = {
        "sufficiency_below(source_independence, medium)": (
            "l'indipendenza delle sorgenti non e stabilita"
        ),
        "sufficiency_below(intervention_level, medium)": (
            "il livello dell'intervento non e identificabile"
        ),
        "assignment_unknown()": "il livello dell'intervento non e identificabile",
        "n_independent_unknown()": "il numero di unita indipendenti non e derivabile",
        "contradiction_unresolved()": "esistono fonti contraddittorie non risolte",
        "count_unknown(culture)": "il numero di colture non e riportato",
    }
    return readable.get(expression, expression)
