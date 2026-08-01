"""Costruisce contesti grafici sintetici espliciti per le fixture NFR-12.

Le fixture verificano che ogni regola possa scattare, non scattare, astenersi quando previsto e
rispettare le eccezioni dichiarate. Non validano la correttezza biologica della regola: quella
richiede casi adjudicati da biostatistico e domain expert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, cast

from ntruth.extract.facts import ProcessFact, StatisticalModelFact
from ntruth.graph.builder import BuildResult
from ntruth.rules.engine import apply_rules
from ntruth.rules.predicates import resolve_type
from ntruth.schemas.core import Confidence, Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    Contradiction,
    Contrast,
    DataSufficiency,
    Endpoint,
    Factor,
    Hierarchy,
    Inferability,
    NKind,
    NScope,
    NStatement,
    RiskLabel,
    UnitAssessment,
)
from ntruth.schemas.graph import (
    GraphNode,
    GraphRelation,
    NodeType,
    RelationType,
    make_node_id,
    make_relation_id,
)
from ntruth.schemas.rules import Rule, RuleOutcome, Ruleset

_CALL = re.compile(r"^(?P<negated>not\s+)?(?P<name>[a-z_][a-z0-9_]*)\((?P<args>.*)\)$")
FactorKind = Literal["treatment", "genotype", "dose", "time", "diet", "other"]
ScalarValue = str | int | float | bool | None
_FACTOR_KINDS = {"treatment", "genotype", "dose", "time", "diet", "other"}


@dataclass
class _Spec:
    counts: dict[NodeType, int | None] = field(default_factory=dict)
    relations: set[tuple[RelationType, NodeType, NodeType]] = field(default_factory=set)
    attributes: dict[NodeType, dict[str, ScalarValue]] = field(default_factory=dict)
    experimental_unit: NodeType | None = None
    observational_unit: NodeType | None = None
    analytical_unit: NodeType | None = None
    n_declared: int | None = None
    n_observational: int | None = None
    n_independent: int | None = None
    factor_kind: FactorKind = "treatment"
    processes: set[str] = field(default_factory=set)
    model_kind: str | None = None
    model_levels: set[NodeType] = field(default_factory=set)
    unresolved_conflict: bool = False
    ambiguous_n: bool = False
    global_n: bool = False
    endpoint_count: int = 1
    endpoint_linked: bool = True
    sufficiency: dict[str, Confidence] = field(
        default_factory=lambda: {
            "intervention_level": Confidence.HIGH,
            "source_independence": Confidence.HIGH,
            "exclusions": Confidence.HIGH,
            "aggregation": Confidence.HIGH,
            "statistical_model": Confidence.HIGH,
        }
    )

    def add(self, node_type: NodeType, count: int | None = None) -> None:
        self.counts.setdefault(node_type, count)
        if count is not None:
            self.counts[node_type] = count


def evaluate_fixture(rule: Rule, scenario: str) -> RuleOutcome:
    """Esegue una fixture dichiarata e restituisce l'outcome auditabile."""
    spec = _scenario(rule, scenario)
    build, assessment = _materialize(spec)
    ruleset = Ruleset(ruleset_id="fixture", version="1.0.0", rules=(rule,))
    result = apply_rules("blk-fixture", build, (assessment,), ruleset)
    evaluations = [item for item in result.evaluations if item.rule_id == rule.rule_id]
    if len(evaluations) != 1:
        raise AssertionError(f"{rule.rule_id}/{scenario}: valutazioni={len(evaluations)}")
    return evaluations[0].outcome


def _scenario(rule: Rule, scenario: str) -> _Spec:
    if scenario == "negative":
        spec = _Spec()
        if rule.rule_id == "GEN-010":
            spec.n_independent = 2
        return spec

    spec = _Spec()
    for expression in rule.normalized_preconditions():
        _set_expression(spec, expression, True)
    for expression in rule.normalized_exceptions():
        _set_expression(spec, expression, False)
    for expression in rule.normalized_abstentions():
        _set_expression(spec, expression, False)

    if scenario == "positive":
        return spec
    if scenario == "ambiguous":
        if rule.abstain_if:
            _set_expression(spec, rule.normalized_abstentions()[0], True)
            return spec
        return _scenario(rule, "negative")
    if scenario == "exception":
        if rule.exceptions:
            _set_expression(spec, rule.normalized_exceptions()[0], True)
            return spec
        return _scenario(rule, "negative")
    raise ValueError(f"scenario fixture sconosciuto: {scenario}")


def _set_expression(spec: _Spec, expression: str, desired: bool) -> None:
    match = _CALL.match(expression.strip())
    if match is None:
        raise AssertionError(f"espressione non normalizzata: {expression}")
    effective = not desired if match.group("negated") else desired
    name = match.group("name")
    args = [part.strip().strip("'\"") for part in match.group("args").split(",") if part.strip()]

    if name in {"level_present", "multiple_instances", "single_instance", "count_unknown"}:
        node_type = _type(args[0])
        if not effective and name == "level_present":
            spec.counts.pop(node_type, None)
            return
        if name == "multiple_instances":
            spec.add(node_type, 2 if effective else 1)
        elif name == "single_instance":
            spec.add(node_type, 1 if effective else 2)
        elif name == "count_unknown":
            spec.counts[node_type] = None if effective else 2
        elif effective:
            spec.add(node_type)
        return

    if name in {"nested", "derived"}:
        child, parent = _type(args[0]), _type(args[1])
        relation = RelationType.NESTED_IN if name == "nested" else RelationType.DERIVED_FROM
        item = (relation, child, parent)
        if effective:
            spec.add(child)
            spec.add(parent)
            spec.relations.add(item)
        else:
            spec.relations.discard(item)
        return

    if name == "independence_declared":
        node_type = _type(args[0])
        spec.add(node_type)
        spec.attributes.setdefault(node_type, {})["declared_independent"] = effective
        return

    if name in {"assigned_at", "assigned_at_or_above", "assigned_at_or_below"}:
        node_type = _type(args[0])
        spec.add(node_type)
        spec.experimental_unit = node_type if effective else None
        return
    if name == "assignment_unknown":
        spec.experimental_unit = None if effective else NodeType.CELL_CULTURE
        if not effective:
            spec.add(NodeType.CELL_CULTURE, 2)
        return
    if name in {"analyzed_as", "measured_on"}:
        node_type = _type(args[0])
        spec.add(node_type)
        if name == "analyzed_as":
            spec.analytical_unit = node_type if effective else None
        else:
            spec.observational_unit = node_type if effective else None
        return
    if name in {"analysis_finer_than_assignment", "observation_finer_than_assignment"}:
        if effective:
            spec.experimental_unit = NodeType.CELL_CULTURE
            spec.add(NodeType.CELL_CULTURE, 3)
            spec.add(NodeType.CELL, 30)
            if name.startswith("analysis"):
                spec.analytical_unit = NodeType.CELL
            else:
                spec.observational_unit = NodeType.CELL
        else:
            spec.experimental_unit = NodeType.CELL
            spec.analytical_unit = NodeType.CELL
            spec.observational_unit = NodeType.CELL
            spec.add(NodeType.CELL, 3)
        return
    if name == "n_independent_unknown":
        spec.n_independent = None if effective else 2
        return
    if name == "declared_equals_observational":
        spec.n_declared, spec.n_observational = (10, 10) if effective else (10, 5)
        return
    if name == "declared_exceeds_independent":
        spec.n_declared, spec.n_independent = (10, 2) if effective else (2, 10)
        return
    if name == "declared_n_scope_global":
        spec.global_n = effective
        return
    if name == "multiple_scopes":
        spec.endpoint_count = 2 if effective else 1
        return
    if name == "ambiguous_replicate_term":
        spec.ambiguous_n = effective
        return

    if name in {"model_declared", "model_is_mixed", "model_is_simple"}:
        if not effective:
            spec.model_kind = None
        elif name == "model_is_simple":
            spec.model_kind = "simple"
        else:
            spec.model_kind = "mixed"
        return
    if name == "model_accounts_for":
        node_type = _type(args[0])
        spec.model_kind = "mixed"
        if effective:
            spec.model_levels.add(node_type)
        else:
            spec.model_levels.discard(node_type)
        return
    if name == "model_accounts_for_assignment":
        if effective:
            if spec.experimental_unit is None:
                spec.experimental_unit = NodeType.CELL_CULTURE
                spec.add(NodeType.CELL_CULTURE, 2)
            spec.model_kind = "mixed"
            spec.model_levels.add(spec.experimental_unit)
        else:
            spec.model_levels.clear()
        return

    process_by_predicate = {
        "pooling_present": "pooling",
        "aggregation_present": "aggregation",
        "repeated_measures_present": "repeated_measure",
        "exclusions_reported": "exclusion",
        "blinding_reported": "blinding",
        "perfect_confounding": "confounding",
    }
    if name in process_by_predicate:
        process = process_by_predicate[name]
        (spec.processes.add if effective else spec.processes.discard)(process)
        return
    if name == "contradiction_unresolved":
        spec.unresolved_conflict = effective
        return
    if name == "factor_kind":
        candidate = args[0] if effective else "other"
        if candidate not in _FACTOR_KINDS:
            raise AssertionError(f"tipo di fattore sconosciuto nella fixture: {candidate}")
        spec.factor_kind = cast(FactorKind, candidate)
        return
    if name == "endpoint_unlinked":
        spec.endpoint_linked = not effective
        return
    if name in {"sufficiency_below", "sufficiency_at_least"}:
        dimension = args[0]
        threshold = Confidence(args[1] if len(args) > 1 else "medium")
        wants_below = effective if name == "sufficiency_below" else not effective
        spec.sufficiency[dimension] = Confidence.LOW if wants_below else threshold
        return
    if name == "technical_level":
        return
    raise AssertionError(f"fixture factory non supporta il predicato: {name}")


def _type(value: str) -> NodeType:
    node_type = resolve_type(value)
    if node_type is None:
        raise AssertionError(f"tipo sconosciuto nella fixture: {value}")
    return node_type


def _materialize(spec: _Spec) -> tuple[BuildResult, UnitAssessment]:
    provenance = Provenance(origin=ProvenanceKind.DERIVED, derivation="fixture NFR-12")
    nodes = {
        node_type: GraphNode(
            id=make_node_id("blk-fixture", node_type, str(node_type)),
            type=node_type,
            label=str(node_type),
            count=count,
            attributes={
                str(key): value for key, value in spec.attributes.get(node_type, {}).items()
            },
            provenance=provenance,
        )
        for node_type, count in spec.counts.items()
    }
    relations: list[GraphRelation] = []
    for relation_type, child, parent in sorted(
        spec.relations, key=lambda item: (str(item[0]), str(item[1]), str(item[2]))
    ):
        source = nodes[child].id
        target = nodes[parent].id
        relations.append(
            GraphRelation(
                id=make_relation_id(relation_type, source, target),
                type=relation_type,
                source=source,
                target=target,
                provenance=provenance,
            )
        )

    factor = Factor(
        id="fac-fixture",
        name="treatment",
        levels=("control", "treated"),
        kind=spec.factor_kind,
        assignment_level=spec.experimental_unit,
        assignment_confidence=1.0 if spec.experimental_unit is not None else 0.0,
        provenance=provenance,
    )
    endpoints = tuple(
        Endpoint(
            id=f"end-{index}",
            name=f"endpoint-{index}",
            measured_on=NodeType.CELL if spec.endpoint_linked else None,
            provenance=provenance,
        )
        for index in range(spec.endpoint_count)
    )
    contrast = Contrast(
        id="cnt-fixture",
        label="treated_vs_control",
        factor_id=factor.id,
        group_a="treated",
        group_b="control",
        endpoint_ids=tuple(endpoint.id for endpoint in endpoints),
        provenance=provenance,
    )
    statements: tuple[NStatement, ...] = ()
    if spec.global_n or spec.ambiguous_n:
        statements = (
            NStatement(
                id="nst-fixture",
                value=10,
                entity_type="independent experiments" if spec.ambiguous_n else "cell",
                node_type=None if spec.ambiguous_n else NodeType.CELL,
                scope=NScope(is_global=True),
                kind=NKind.DECLARED,
                raw_text="n = 10 independent experiments" if spec.ambiguous_n else "n = 10 cells",
                provenance=provenance,
            ),
        )
    contradictions = (
        (
            Contradiction(
                id="con-fixture",
                description="fixture con alternative non risolte",
            ),
        )
        if spec.unresolved_conflict
        else ()
    )
    models = (
        (
            StatisticalModelFact(
                kind=spec.model_kind or "mixed", accounts_for=tuple(spec.model_levels)
            ),
        )
        if spec.model_kind is not None
        else ()
    )
    processes = tuple(ProcessFact(kind=kind) for kind in sorted(spec.processes))
    build = BuildResult(
        hierarchy=Hierarchy(nodes=tuple(nodes.values()), relations=tuple(relations)),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=endpoints,
        n_statements=statements,
        contradictions=contradictions,
        models=models,
        processes=processes,
    )
    scope = NScope(
        factor_id=factor.id,
        contrast_id=contrast.id,
        endpoint_id=endpoints[0].id if endpoints else None,
    )
    sufficiency = DataSufficiency(**spec.sufficiency)
    assessment = UnitAssessment(
        id="uas-fixture",
        scope=scope,
        experimental_unit=spec.experimental_unit,
        observational_unit=spec.observational_unit,
        analytical_unit=spec.analytical_unit,
        n_declared=spec.n_declared,
        n_observational=spec.n_observational,
        n_independent=spec.n_independent,
        independent_entity_type=(
            str(spec.experimental_unit)
            if spec.n_independent is not None and spec.experimental_unit is not None
            else None
        ),
        inferability=(
            Inferability.INFERABLE if spec.n_independent is not None else Inferability.NOT_INFERABLE
        ),
        risk=RiskLabel.NO_ISSUE,
        data_sufficiency=sufficiency,
        provenance=provenance,
    )
    return build, assessment
