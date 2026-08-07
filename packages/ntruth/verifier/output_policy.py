"""Matrice normativa ``DeterminabilityState -> output``.

Il parser, il rules engine e la confidence non possono autorizzare un singolo
valore di unita sperimentale o ``n``.  Questa proiezione viene applicata una
sola volta, dopo la derivazione dello stato, prima di qualsiasi serializzazione.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ntruth.schemas.core import Determinability
from ntruth.schemas.experiment import (
    Alert,
    CountKind,
    ExperimentBlock,
    Inferability,
    NKind,
    UnitAssessment,
)
from ntruth.schemas.rules import RuleEvaluation, RuleOutcome

_WITHHELD_EVALUATION_PREFIX = "output_withheld_by_determinability:"
_DECISIVE_ALERT_RULE_IDS = frozenset(
    {
        "GEN-001",
        "GEN-002",
        "GEN-008",
        "GEN-009",
        "CC-002",
        "CC-006",
        "MIC-003",
        "MIC-004",
        "MIC-005",
        "SC-001",
        "SC-002",
        "ANI-001",
        "ANI-002",
        "ANI-003",
    }
)
_DECISIVE_EVALUATION_RE = re.compile(
    r"(?:assigned_at|independently_assigned|experimental_unit|n_independent|"
    r"allocation_level|\bunit[aà]?=|\bunita=)",
    re.IGNORECASE,
)
_DECISIVE_ALERT_TEXT_RE = re.compile(
    r"(?:"
    r"\bexperimental[\s_-]+units?\b|"
    r"\bunit[aà][\s_-]+sperimental[ei]\b|"
    r"\bindependent[\s_-]+n\b|"
    r"\bn[\s_-]+independent\b|"
    r"\bn[\s_-]+indipendente\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class OutputPolicyViolation:
    """Valore autorevole presente in uno stato che non lo consente."""

    code: str
    message: str
    assessment_id: str


def output_policy_violations(block: ExperimentBlock) -> tuple[OutputPolicyViolation, ...]:
    """Valida la tabella v6 senza modificare il blocco."""

    violations: list[OutputPolicyViolation] = []
    if (
        block.determinability
        in {Determinability.DETERMINATE, Determinability.CONDITIONALLY_DETERMINATE}
        and not block.unit_assessments
    ):
        violations.append(
            OutputPolicyViolation(
                code=(
                    "determinate_without_assessments"
                    if block.determinability is Determinability.DETERMINATE
                    else "conditional_without_assessments"
                ),
                message=(
                    f"{block.determinability.value} richiede almeno un assessment scope-aware"
                ),
                assessment_id=block.id,
            )
        )
    if block.determinability is Determinability.CONFLICTING_INFORMATION and not any(
        item.status == "unresolved" for item in block.contradictions
    ):
        violations.append(
            OutputPolicyViolation(
                code="conflicting_state_without_conflict",
                message="CONFLICTING_INFORMATION richiede un conflitto irrisolto materializzato",
                assessment_id=block.id,
            )
        )
    if (
        block.determinability is Determinability.MULTIPLE_PLAUSIBLE_GRAPHS
        and not _has_publishable_alternative_graphs(block)
    ):
        violations.append(
            OutputPolicyViolation(
                code="multiple_graph_state_without_materialized_alternatives",
                message=(
                    "MULTIPLE_PLAUSIBLE_GRAPHS richiede almeno due grafi distinti, "
                    "conseguenze e una domanda discriminante decisiva"
                ),
                assessment_id=block.id,
            )
        )
    if block.determinability is not Determinability.DETERMINATE:
        for alert in block.alerts:
            if _alert_discloses_decisive_output(alert):
                violations.append(
                    OutputPolicyViolation(
                        code="decisive_alert_forbidden_by_state",
                        message=(
                            f"{block.determinability.value} non consente alert con una "
                            "singola unita sperimentale o un singolo n indipendente"
                        ),
                        assessment_id=alert.id,
                    )
                )
        for count in block.count_records:
            if count.kind is CountKind.INDEPENDENT_N and _has_numeric_count(count):
                violations.append(
                    OutputPolicyViolation(
                        code="single_independent_count_forbidden_by_state",
                        message=(
                            f"{block.determinability.value} non consente un CountRecord "
                            "INDEPENDENT_N numerico"
                        ),
                        assessment_id=count.count_id,
                    )
                )
        for statement in block.n_statements:
            if statement.kind is NKind.INDEPENDENT and _has_numeric_count(statement):
                violations.append(
                    OutputPolicyViolation(
                        code="legacy_independent_count_forbidden_by_state",
                        message=(
                            f"{block.determinability.value} non consente un NStatement "
                            "INDEPENDENT numerico"
                        ),
                        assessment_id=statement.id,
                    )
                )
    for assessment in block.unit_assessments:
        if assessment.effective_n is not None:
            violations.append(
                OutputPolicyViolation(
                    code="effective_n_must_use_diagnostic_register",
                    message=(
                        "effective_n deve vivere esclusivamente in "
                        "CountRecord(EFFECTIVE_N, diagnostic_only=true)"
                    ),
                    assessment_id=assessment.id,
                )
            )
        if block.determinability is Determinability.DETERMINATE:
            if assessment.conditional_scenarios:
                violations.append(
                    OutputPolicyViolation(
                        code="determinate_with_conditional_branches",
                        message="DETERMINATE non ammette rami numerici condizionali",
                        assessment_id=assessment.id,
                    )
                )
            if assessment.experimental_unit is None or assessment.n_independent is None:
                violations.append(
                    OutputPolicyViolation(
                        code="determinate_without_single_output",
                        message="DETERMINATE richiede unita sperimentale e n indipendente",
                        assessment_id=assessment.id,
                    )
                )
            continue

        if assessment.experimental_unit is not None:
            violations.append(
                OutputPolicyViolation(
                    code="single_experimental_unit_forbidden_by_state",
                    message=(
                        f"{block.determinability.value} non consente una singola unita sperimentale"
                    ),
                    assessment_id=assessment.id,
                )
            )
        if assessment.n_independent is not None:
            violations.append(
                OutputPolicyViolation(
                    code="single_n_forbidden_by_state",
                    message=(
                        f"{block.determinability.value} non consente un singolo n indipendente"
                    ),
                    assessment_id=assessment.id,
                )
            )
        if assessment.independent_entity_type is not None:
            violations.append(
                OutputPolicyViolation(
                    code="independent_entity_forbidden_by_state",
                    message=(
                        f"{block.determinability.value} non consente un tipo di entita "
                        "indipendente singolo"
                    ),
                    assessment_id=assessment.id,
                )
            )
        if block.determinability is Determinability.CONDITIONALLY_DETERMINATE:
            if not assessment.conditional_scenarios:
                violations.append(
                    OutputPolicyViolation(
                        code="conditional_state_without_branches",
                        message=(
                            "CONDITIONALLY_DETERMINATE richiede alternative esplicite per ramo"
                        ),
                        assessment_id=assessment.id,
                    )
                )
        elif assessment.conditional_scenarios:
            violations.append(
                OutputPolicyViolation(
                    code="branches_forbidden_by_state",
                    message=(
                        f"{block.determinability.value} non consente rami numerici pubblicabili"
                    ),
                    assessment_id=assessment.id,
                )
            )
    return tuple(violations)


def _has_publishable_alternative_graphs(block: ExperimentBlock) -> bool:
    graph_set = block.plausible_graph_set
    if graph_set is None or block.graph_status.value != "conditional":
        return False
    if len(graph_set.alternatives) < 2:
        return False
    if any(not item.hierarchy.nodes or not item.consequences for item in graph_set.alternatives):
        return False
    signatures = {item.scientific_signature() for item in graph_set.alternatives}
    if len(signatures) != len(graph_set.alternatives):
        return False
    question = next(
        (item for item in block.questions if item.id == graph_set.discriminating_question_id),
        None,
    )
    return question is not None and question.decisive


def apply_output_policy(block: ExperimentBlock) -> ExperimentBlock:
    """Rimuove valori puntuali non autorizzati, conservando i fatti osservati.

    I count dichiarati, allocati, osservati e analizzati restano consultabili:
    sono fatti con scope e non vengono trasformati in ``n_independent``.  Negli
    stati non determinati l'unita sperimentale rimane nel proof trace interno,
    ma non viene pubblicata come risposta singola nell'assessment serializzato.
    """

    if block.determinability is Determinability.DETERMINATE:
        projected_assessments = tuple(
            assessment.model_copy(update={"effective_n": None})
            for assessment in block.unit_assessments
        )
        return block.model_copy(update={"unit_assessments": projected_assessments})

    keep_branches = block.determinability is Determinability.CONDITIONALLY_DETERMINATE
    projected_assessments = tuple(
        _project_assessment(assessment, keep_branches=keep_branches)
        for assessment in block.unit_assessments
    )
    projected_alerts = tuple(
        alert for alert in block.alerts if not _alert_discloses_decisive_output(alert)
    )
    projected_counts = tuple(
        count
        for count in block.count_records
        if not (count.kind is CountKind.INDEPENDENT_N and _has_numeric_count(count))
    )
    projected_n_statements = tuple(
        statement
        for statement in block.n_statements
        if not (statement.kind is NKind.INDEPENDENT and _has_numeric_count(statement))
    )
    return block.model_copy(
        update={
            "unit_assessments": projected_assessments,
            "alerts": projected_alerts,
            "count_records": projected_counts,
            "n_statements": projected_n_statements,
        }
    )


def _has_numeric_count(count: object) -> bool:
    return any(
        getattr(count, field_name, None) is not None
        for field_name in ("value", "lower_bound", "upper_bound")
    )


def _alert_discloses_decisive_output(alert: Alert) -> bool:
    # I ruleset locali non sono vincolati agli ID canonici. Il confine pubblico
    # deve quindi riconoscere anche le principali forme IT/EN dei due output
    # decisivi, incluse le chiavi template ``experimental_unit`` e
    # ``n_independent``. Fuori da DETERMINATE si preferisce omettere un alert
    # ambiguo anziche pubblicare un valore unico proveniente da una regola
    # custom non ancora classificata.
    return alert.rule_id in _DECISIVE_ALERT_RULE_IDS or bool(
        _DECISIVE_ALERT_TEXT_RE.search(alert.message)
    )


def apply_rule_evaluation_output_policy(
    block: ExperimentBlock,
    evaluations: tuple[RuleEvaluation, ...],
) -> tuple[RuleEvaluation, ...]:
    """Separa il proof trace interno dalla traccia serializzabile pubblica."""

    if block.determinability is Determinability.DETERMINATE:
        return evaluations
    marker = f"{_WITHHELD_EVALUATION_PREFIX}{block.determinability.value}"
    public_output_ids = {
        *(alert.id for alert in block.alerts),
        *(question.id for question in block.questions),
    }
    projected: list[RuleEvaluation] = []
    for evaluation in evaluations:
        sensitive_trace = evaluation.rule_id in _DECISIVE_ALERT_RULE_IDS or bool(
            set(evaluation.output_ids) - public_output_ids
        )
        trace_strings = (
            *evaluation.matched,
            *evaluation.failed,
            *evaluation.unknown_predicates,
            *(item.expression for item in evaluation.premise_trace),
        )
        sensitive_trace = sensitive_trace or any(
            _DECISIVE_EVALUATION_RE.search(item) for item in trace_strings
        )
        if sensitive_trace:
            public_evidence_gap = tuple(
                item
                for item in evaluation.evidence_gap
                if not item.startswith(_WITHHELD_EVALUATION_PREFIX)
            )
            projected.append(
                evaluation.model_copy(
                    update={
                        "outcome": RuleOutcome.ABSTAINED,
                        "matched": (),
                        "failed": (),
                        "triggered_exception": None,
                        "triggered_abstention": marker,
                        "unknown_predicates": (),
                        "scope_label": "",
                        "premise_trace": (),
                        # ``write_all`` riapplica intenzionalmente la policy al
                        # confine di serializzazione. Sostituire l'eventuale
                        # marker precedente rende la proiezione idempotente e
                        # impedisce che il checksum cambi a ogni export.
                        "evidence_gap": (*public_evidence_gap, marker),
                        "output_ids": (),
                    }
                )
            )
            continue
        projected.append(evaluation.model_copy(update={"scope_label": ""}))
    return tuple(projected)


def _project_assessment(
    assessment: UnitAssessment,
    *,
    keep_branches: bool,
) -> UnitAssessment:
    inferability = assessment.inferability
    if keep_branches and assessment.conditional_scenarios:
        inferability = Inferability.CONDITIONAL
    elif inferability is Inferability.INFERABLE:
        inferability = Inferability.REQUIRES_CONFIRMATION
    return assessment.model_copy(
        update={
            "experimental_unit": None,
            "n_independent": None,
            # effective_n e un diagnostico statistico, non un conteggio fisico
            # e non puo diventare una risposta alternativa quando EU/n non
            # sono pubblicabili. L'eventuale fatto resta nel registro separato
            # CountRecord(diagnostic_only=true).
            "effective_n": None,
            "independent_entity_type": None,
            "conditional_scenarios": (assessment.conditional_scenarios if keep_branches else ()),
            "inferability": inferability,
        }
    )
