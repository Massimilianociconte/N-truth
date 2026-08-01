"""Graph builder deterministico (PRD 11.3).

Il builder compone i candidate facts in un grafo tipizzato. Non elimina le
alternative contraddittorie: quando due fonti dissentono registra un conflitto
e lascia il valore indeterminato, perche nessuna regola puo produrre un verdetto
su una base che l'utente non ha ancora risolto (PRD GEN-007, UC10).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations, pairwise

from ntruth.extract.facts import (
    EndpointFact,
    EntityFact,
    EntityInstanceFact,
    ExtractionResult,
    FactorFact,
    InstanceAssignmentFact,
    InstanceRelationFact,
    NFact,
    RelationFact,
)
from ntruth.extract.facts import ProcessFact as ExtractedProcessFact
from ntruth.extract.facts import StatisticalModelFact as ExtractedStatisticalModelFact
from ntruth.schemas.core import Provenance, ProvenanceKind, stable_id
from ntruth.schemas.experiment import (
    Contradiction,
    Contrast,
    Endpoint,
    Estimand,
    Factor,
    Hierarchy,
    InferenceTarget,
    InferenceTargetStatus,
    NScope,
    NStatement,
    ProcessFact,
    Question,
    StatisticalModelFact,
)
from ntruth.schemas.graph import (
    CLUSTER_TYPES,
    TECHNICAL_TYPES,
    GraphNode,
    GraphRelation,
    GraphViolation,
    NodeType,
    RelationType,
    make_node_id,
    make_relation_id,
    rank_of,
)

MAX_CONTRASTS_PER_FACTOR = 6


@dataclass
class BuildResult:
    """Grafo e strutture di disegno derivate, con i conflitti aperti."""

    hierarchy: Hierarchy
    factors: tuple[Factor, ...] = ()
    contrasts: tuple[Contrast, ...] = ()
    endpoints: tuple[Endpoint, ...] = ()
    inference_targets: tuple[InferenceTarget, ...] = ()
    estimands: tuple[Estimand, ...] = ()
    n_statements: tuple[NStatement, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    questions: tuple[Question, ...] = ()
    violations: tuple[GraphViolation, ...] = ()
    models: tuple[StatisticalModelFact, ...] = ()
    processes: tuple[ProcessFact, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass
class _Accumulator:
    contradictions: list[Contradiction] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    violations: list[GraphViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_graph(block_id: str, extraction: ExtractionResult) -> BuildResult:
    """Costruisce il grafo del blocco a partire dai candidate facts."""
    acc = _Accumulator(warnings=list(extraction.warnings))

    factors = _build_factors(block_id, extraction.factors, acc)
    endpoints = _build_endpoints(block_id, extraction.endpoints, acc)
    contrasts = _build_contrasts(block_id, factors, acc)
    models = _build_models(block_id, extraction.models)
    processes = _build_processes(block_id, extraction.processes)
    n_statements = _build_n_statements(
        block_id,
        extraction.n_facts,
        factors,
        contrasts,
        endpoints,
        acc,
    )
    contrasts = _bind_contrast_endpoints(contrasts, n_statements)
    _register_n_statement_conflicts(block_id, n_statements, acc)

    required_types = _required_types(extraction)
    # I livelli v3 materializzati sui fatti scientifici possono essere piu
    # ricchi del contratto legacy dei candidate facts. In particolare,
    # application e declared_clustering devono avere un nodo bersaglio senza
    # essere reinterpretati come allocation.
    required_types.update(
        level
        for factor in factors
        for level in (factor.allocation_level, factor.application_level)
        if level is not None
    )
    required_types.update(level for model in models for level in model.declared_clustering)
    has_exclusions = any(process.kind == "exclusion" for process in processes)
    aggregate_nodes = _build_nodes(
        block_id, extraction.entities, required_types, acc, has_exclusions=has_exclusions
    )
    instance_nodes, instance_index = _build_instance_nodes(
        block_id,
        extraction.entity_instances,
        extraction.instance_assignments,
        acc,
    )
    relations = _build_relations(block_id, extraction.relations, aggregate_nodes, acc)
    relations.extend(_default_technical_containment(aggregate_nodes, relations))
    relations.extend(_build_instance_relations(extraction.instance_relations, instance_index, acc))
    design_nodes, design_relations = _build_design_graph(
        block_id,
        factors=factors,
        contrasts=contrasts,
        endpoints=endpoints,
        inference_targets=(),
        estimands=(),
        models=models,
        unit_nodes=aggregate_nodes,
    )
    relations.extend(design_relations)
    hierarchy = Hierarchy(
        nodes=(*aggregate_nodes.values(), *instance_nodes, *design_nodes),
        relations=tuple(relations),
    )

    return BuildResult(
        hierarchy=hierarchy,
        factors=factors,
        contrasts=contrasts,
        endpoints=endpoints,
        inference_targets=(),
        estimands=(),
        n_statements=n_statements,
        contradictions=tuple(acc.contradictions),
        questions=tuple(acc.questions),
        violations=tuple(acc.violations),
        models=models,
        processes=processes,
        warnings=tuple(dict.fromkeys(acc.warnings)),
    )


# --------------------------------------------------------------------- nodi


def _required_types(extraction: ExtractionResult) -> set[NodeType]:
    """Tipi che devono esistere come nodo anche senza conteggio."""
    types: set[NodeType] = set()
    for aggregate_relation in extraction.relations:
        types.add(aggregate_relation.source_type)
        types.add(aggregate_relation.target_type)
    for instance_relation in extraction.instance_relations:
        types.add(instance_relation.source_type)
        types.add(instance_relation.target_type)
    types.update(fact.node_type for fact in extraction.entity_instances)
    types.update(fact.node_type for fact in extraction.instance_assignments)
    for factor in extraction.factors:
        for level in (factor.allocation_level, factor.application_level):
            if level is not None:
                types.add(level)
    for endpoint in extraction.endpoints:
        if endpoint.measured_on is not None:
            types.add(endpoint.measured_on)
    for n_fact in extraction.n_facts:
        if n_fact.node_type is not None:
            types.add(n_fact.node_type)
    for process in extraction.processes:
        if process.node_type is not None:
            types.add(process.node_type)
    return types


def _build_models(
    block_id: str,
    facts: list[ExtractedStatisticalModelFact],
) -> tuple[StatisticalModelFact, ...]:
    """Materializza candidate facts in record stabili e correggibili."""

    models: dict[str, StatisticalModelFact] = {}
    for fact in facts:
        evidence_ids = (fact.evidence.id,) if fact.evidence is not None else ()
        model_id = stable_id(
            "mdl",
            block_id,
            fact.kind,
            tuple(str(level) for level in fact.accounts_for),
            fact.raw_text,
            evidence_ids,
        )
        models.setdefault(
            model_id,
            StatisticalModelFact(
                id=model_id,
                kind=fact.kind,
                accounts_for=fact.accounts_for,
                declared_clustering=fact.accounts_for,
                raw_text=fact.raw_text,
                evidence_ids=evidence_ids,
                provenance=Provenance(origin=fact.origin, evidence_ids=evidence_ids),
            ),
        )
    return tuple(models.values())


def _build_processes(
    block_id: str,
    facts: list[ExtractedProcessFact],
) -> tuple[ProcessFact, ...]:
    """Materializza processi senza perdere qualifier o provenance di fonte."""

    processes: dict[str, ProcessFact] = {}
    for fact in facts:
        evidence_ids = (fact.evidence.id,) if fact.evidence is not None else ()
        process_id = stable_id(
            "prc",
            block_id,
            fact.kind,
            fact.detail,
            str(fact.node_type),
            fact.value,
            fact.endpoint_hint,
            fact.group_hint,
            evidence_ids,
        )
        processes.setdefault(
            process_id,
            ProcessFact(
                id=process_id,
                kind=fact.kind,
                detail=fact.detail,
                node_type=fact.node_type,
                value=fact.value,
                endpoint_hint=fact.endpoint_hint,
                group_hint=fact.group_hint,
                evidence_ids=evidence_ids,
                provenance=Provenance(origin=fact.origin, evidence_ids=evidence_ids),
            ),
        )
    return tuple(processes.values())


def _build_nodes(
    block_id: str,
    entities: list[EntityFact],
    required: set[NodeType],
    acc: _Accumulator,
    *,
    has_exclusions: bool = False,
) -> dict[NodeType, GraphNode]:
    grouped: dict[NodeType, list[EntityFact]] = {}
    for fact in entities:
        grouped.setdefault(fact.node_type, []).append(fact)
    for node_type in required:
        grouped.setdefault(node_type, [])

    nodes: dict[NodeType, GraphNode] = {}
    for node_type, facts in grouped.items():
        unscoped_facts = [
            f
            for f in facts
            if not f.per_parent
            and not any(
                f.attributes.get(key)
                for key in ("scope_group", "scope_endpoint", "scope_timepoint")
            )
            and f.attributes.get("scope_qualifier") != "per_group"
        ]
        generic_per_group = sorted(
            {
                f.count
                for f in facts
                if f.count is not None
                and not f.per_parent
                and f.attributes.get("scope_qualifier") == "per_group"
                and not f.attributes.get("scope_group")
            }
        )
        totals = sorted({f.count for f in unscoped_facts if f.count is not None})
        # Compatibilita della vista aggregata: quando l'unica informazione e
        # "n per gruppo", il valore resta interrogabile ma viene marcato come
        # scoped; non viene mescolato a un totale globale eventualmente presente.
        if not totals and len(generic_per_group) == 1:
            totals = list(generic_per_group)
        per_parent = sorted({f.count for f in facts if f.count is not None and f.per_parent})
        evidence_ids = tuple(dict.fromkeys(f.evidence.id for f in facts if f.evidence is not None))
        origins = {f.origin for f in facts}
        origin = (
            ProvenanceKind.TABULAR
            if ProvenanceKind.TABULAR in origins
            else (next(iter(origins)) if origins else ProvenanceKind.DERIVED)
        )

        attributes: dict[str, str | int | float | bool | None] = {"aggregate": True}
        count: int | None = None
        if len(totals) == 1:
            count = totals[0]
        elif len(totals) == 2 and has_exclusions:
            # Due conteggi diversi con esclusioni riportate sono la differenza
            # attesa tra allocato e analizzato, non una contraddizione (ARRIVE 2.0).
            count = min(totals)
            attributes["n_allocated"] = max(totals)
            attributes["n_analyzed"] = min(totals)
            acc.questions.append(
                Question(
                    id=stable_id("qst", block_id, "allocated", str(node_type), *totals),
                    text=(
                        f"Per {node_type}: {max(totals)} unita allocate e {min(totals)} "
                        "analizzate. Confermare quali esclusioni si applicano a ciascun "
                        "gruppo ed endpoint."
                    ),
                    reason="differenza tra n allocato e n analizzato con esclusioni riportate",
                    missing_field=f"exclusions[{node_type}]",
                )
            )
        elif len(totals) > 1:
            contradiction = Contradiction(
                id=stable_id("con", block_id, str(node_type), *totals),
                description=(
                    f"conteggio contraddittorio per {node_type}: valori {totals} riportati da "
                    "fonti diverse"
                ),
                evidence_ids=evidence_ids,
            )
            acc.contradictions.append(contradiction)
            acc.questions.append(
                Question(
                    id=stable_id("qst", contradiction.id),
                    text=(
                        f"Quante unita di tipo {node_type} sono state effettivamente usate? "
                        f"Le fonti riportano {totals}."
                    ),
                    reason="conteggi in conflitto tra fonti diverse",
                    missing_field=f"count[{node_type}]",
                )
            )
            attributes["conflicting_counts"] = ", ".join(str(t) for t in totals)
            attributes["conflict_id"] = contradiction.id

        if len(per_parent) == 1:
            attributes["count_per_parent"] = per_parent[0]
        elif len(per_parent) > 1:
            attributes["conflicting_per_parent"] = ", ".join(str(p) for p in per_parent)

        if any(bool(f.attributes.get("declared_independent")) for f in facts):
            attributes["declared_independent"] = True
        if any(f.attributes.get("scope_qualifier") == "per_group" for f in facts):
            attributes["count_scope"] = "per_group"
        if len(generic_per_group) == 1:
            attributes["per_group_count"] = generic_per_group[0]
        scoped_fact_count = sum(
            1
            for f in facts
            if any(
                f.attributes.get(key)
                for key in ("scope_group", "scope_endpoint", "scope_timepoint")
            )
        )
        if scoped_fact_count:
            attributes["scoped_count_facts"] = scoped_fact_count
        columns = sorted(
            {str(f.attributes.get("column")) for f in facts if f.attributes.get("column")}
        )
        if columns:
            attributes["source_columns"] = ", ".join(columns)

        nodes[node_type] = GraphNode(
            id=make_node_id(block_id, node_type, str(node_type)),
            type=node_type,
            label=str(node_type),
            count=count,
            attributes=attributes,
            evidence_ids=evidence_ids,
            provenance=Provenance(
                origin=origin if facts else ProvenanceKind.DERIVED,
                evidence_ids=evidence_ids,
                derivation=None if facts else "livello richiesto da una relazione o da un fattore",
            ),
            confidence=max((f.confidence for f in facts), default=0.5),
        )
    return nodes


def _assignment_attribute(factor_name: str) -> str:
    return "assignment:" + "_".join(factor_name.strip().casefold().split())


def _build_instance_nodes(
    block_id: str,
    facts: list[EntityInstanceFact],
    assignments: list[InstanceAssignmentFact],
    acc: _Accumulator,
) -> tuple[list[GraphNode], dict[tuple[NodeType, str], GraphNode]]:
    """Costruisce nodi individuali senza sostituire i nodi aggregati."""

    grouped: dict[tuple[NodeType, str], list[EntityInstanceFact]] = {}
    for fact in facts:
        grouped.setdefault((fact.node_type, fact.instance_key), []).append(fact)

    assignments_by_instance: dict[tuple[NodeType, str], list[InstanceAssignmentFact]] = {}
    for assignment in assignments:
        key = (assignment.node_type, assignment.instance_key)
        assignments_by_instance.setdefault(key, []).append(assignment)
        if key not in grouped:
            acc.violations.append(
                GraphViolation(
                    code="dangling_instance_assignment",
                    message=(
                        f"assegnazione '{assignment.factor_name}={assignment.factor_level}' "
                        "senza istanza tabulare corrispondente"
                    ),
                )
            )

    nodes: list[GraphNode] = []
    index: dict[tuple[NodeType, str], GraphNode] = {}
    for key, instance_facts in grouped.items():
        node_type, instance_key = key
        evidence_ids = tuple(
            dict.fromkeys(
                evidence.id
                for evidence in (
                    *(fact.evidence for fact in instance_facts),
                    *(assignment.evidence for assignment in assignments_by_instance.get(key, [])),
                )
                if evidence is not None
            )
        )
        attributes: dict[str, str | int | float | bool | None] = {"instance": True}
        for fact in instance_facts:
            for attr_key, value in fact.attributes.items():
                attributes.setdefault(attr_key, value)

        grouped_assignments: dict[str, set[str]] = {}
        for assignment in assignments_by_instance.get(key, []):
            grouped_assignments.setdefault(assignment.factor_name, set()).add(
                assignment.factor_level
            )
        for factor_name, levels in grouped_assignments.items():
            if len(levels) == 1:
                attributes[_assignment_attribute(factor_name)] = next(iter(levels))
                continue
            acc.violations.append(
                GraphViolation(
                    code="conflicting_instance_assignment",
                    message=(
                        f"istanza di {node_type} associata a livelli incompatibili di "
                        f"'{factor_name}': {sorted(levels)}"
                    ),
                )
            )

        best = max(instance_facts, key=lambda fact: fact.confidence)
        node = GraphNode(
            id=stable_id("ndi", block_id, str(node_type), instance_key),
            type=node_type,
            label=best.label,
            count=1,
            attributes=attributes,
            evidence_ids=evidence_ids,
            provenance=Provenance(
                origin=best.origin,
                evidence_ids=evidence_ids,
                derivation="istanza distinta osservata nel sample sheet",
            ),
            confidence=min(
                [
                    *(fact.confidence for fact in instance_facts),
                    *(assignment.confidence for assignment in assignments_by_instance.get(key, [])),
                ]
            ),
        )
        nodes.append(node)
        index[key] = node
    return nodes, index


def _build_instance_relations(
    facts: list[InstanceRelationFact],
    nodes: dict[tuple[NodeType, str], GraphNode],
    acc: _Accumulator,
) -> list[GraphRelation]:
    """Materializza gli archi riga-per-riga con endpoint verificati."""

    relations: dict[str, GraphRelation] = {}
    for fact in facts:
        source = nodes.get((fact.source_type, fact.source_key))
        target = nodes.get((fact.target_type, fact.target_key))
        if source is None or target is None:
            acc.violations.append(
                GraphViolation(
                    code="dangling_instance_relation",
                    message=(
                        f"relazione tabulare {fact.source_type} -> {fact.target_type} "
                        "senza entrambe le istanze"
                    ),
                )
            )
            continue
        evidence_ids = (fact.evidence.id,) if fact.evidence is not None else ()
        relation_id = make_relation_id(fact.type, source.id, target.id)
        relation = GraphRelation(
            id=relation_id,
            type=fact.type,
            source=source.id,
            target=target.id,
            attributes={"instance_relation": True},
            evidence_ids=evidence_ids,
            provenance=Provenance(
                origin=fact.origin,
                evidence_ids=evidence_ids,
                derivation=fact.derivation,
            ),
            confidence=fact.confidence,
        )
        relations.setdefault(relation_id, relation)
    return list(relations.values())


# ----------------------------------------------------------------- relazioni


def _build_relations(
    block_id: str,
    relation_facts: list[RelationFact],
    nodes: dict[NodeType, GraphNode],
    acc: _Accumulator,
) -> list[GraphRelation]:
    grouped: dict[tuple[RelationType, NodeType, NodeType], list[RelationFact]] = {}
    for fact in relation_facts:
        if fact.source_type not in nodes or fact.target_type not in nodes:
            continue
        grouped.setdefault((fact.type, fact.source_type, fact.target_type), []).append(fact)

    relations: list[GraphRelation] = []
    for (rel_type, source_type, target_type), facts in grouped.items():
        source_rank, target_rank = rank_of(source_type), rank_of(target_type)
        if (
            rel_type is RelationType.NESTED_IN
            and source_rank is not None
            and target_rank is not None
            and source_rank <= target_rank
        ):
            acc.violations.append(
                GraphViolation(
                    code="hierarchy_inversion",
                    message=(
                        f"relazione {source_type} nested_in {target_type} incompatibile con "
                        "l'ordine di contenimento noto"
                    ),
                    blocking=False,
                )
            )
            continue

        counts = sorted({f.per_parent_count for f in facts if f.per_parent_count is not None})
        attributes: dict[str, str | int | float | bool | None] = {}
        if len(counts) == 1:
            attributes["per_parent_count"] = counts[0]
        elif len(counts) > 1:
            contradiction = Contradiction(
                id=stable_id("con", block_id, str(rel_type), str(source_type), *counts),
                description=(
                    f"cardinalita contraddittoria per {source_type} in {target_type}: {counts}"
                ),
                evidence_ids=tuple(f.evidence.id for f in facts if f.evidence is not None),
            )
            acc.contradictions.append(contradiction)
            attributes["conflicting_per_parent"] = ", ".join(str(c) for c in counts)

        derivations = sorted({f.derivation for f in facts if f.derivation})
        if derivations:
            attributes["derivation"] = "; ".join(derivations)

        best = max(facts, key=lambda f: f.confidence)
        evidence_ids = tuple(dict.fromkeys(f.evidence.id for f in facts if f.evidence is not None))
        relations.append(
            GraphRelation(
                id=make_relation_id(rel_type, nodes[source_type].id, nodes[target_type].id),
                type=rel_type,
                source=nodes[source_type].id,
                target=nodes[target_type].id,
                attributes=attributes,
                evidence_ids=evidence_ids,
                provenance=Provenance(
                    origin=best.origin,
                    evidence_ids=evidence_ids,
                    derivation=best.derivation,
                ),
                confidence=best.confidence,
            )
        )
    return relations


def _default_technical_containment(
    nodes: dict[NodeType, GraphNode], relations: list[GraphRelation]
) -> list[GraphRelation]:
    """Chiude la catena di contenimento tra livelli puramente tecnici.

    Che una cellula stia dentro un campo e che un campo stia dentro un pozzetto
    e ontologia di dominio, non ricostruzione del disegno. Il default e ammesso
    solo tra livelli tecnici e mai per l'indipendenza delle sorgenti biologiche,
    che e esattamente cio che il PRD vieta di assumere (PRD 1, 8.7).
    """
    candidates = sorted(
        (
            node_type
            for node_type in nodes
            if node_type in TECHNICAL_TYPES
            and node_type not in CLUSTER_TYPES
            and rank_of(node_type) is not None
        ),
        key=lambda t: rank_of(t) or 0,
    )
    if len(candidates) < 2:
        return []

    adjacency: dict[NodeType, set[NodeType]] = {}
    id_to_type = {node.id: node.type for node in nodes.values()}
    for relation in relations:
        if relation.type in {RelationType.NESTED_IN, RelationType.DERIVED_FROM}:
            source = id_to_type.get(relation.source)
            target = id_to_type.get(relation.target)
            if source is not None and target is not None:
                adjacency.setdefault(source, set()).add(target)

    def reaches(start: NodeType, goal: NodeType) -> bool:
        seen: set[NodeType] = set()
        stack = [start]
        while stack:
            current = stack.pop()
            if current == goal:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency.get(current, ()))
        return False

    added: list[GraphRelation] = []
    for coarser, finer in pairwise(candidates):
        if reaches(finer, coarser):
            continue
        relation = GraphRelation(
            id=make_relation_id(RelationType.NESTED_IN, nodes[finer].id, nodes[coarser].id),
            type=RelationType.NESTED_IN,
            source=nodes[finer].id,
            target=nodes[coarser].id,
            attributes={"default_containment": True},
            provenance=Provenance(
                origin=ProvenanceKind.DERIVED,
                derivation=(
                    "contenimento tecnico predefinito: non implica indipendenza delle sorgenti"
                ),
            ),
            confidence=0.6,
        )
        added.append(relation)
        adjacency.setdefault(finer, set()).add(coarser)
    return added


# ------------------------------------------------------------------- fattori


def _build_factors(
    block_id: str, factor_facts: list[FactorFact], acc: _Accumulator
) -> tuple[Factor, ...]:
    grouped: dict[str, list[FactorFact]] = {}
    for fact in factor_facts:
        grouped.setdefault(fact.name, []).append(fact)

    factors: list[Factor] = []
    for name, facts in grouped.items():
        levels = tuple(dict.fromkeys(level for fact in facts for level in fact.levels))
        evidence_ids = tuple(
            dict.fromkeys(
                e.id
                for fact in facts
                for e in (
                    fact.evidence,
                    fact.allocation_evidence,
                    fact.application_evidence,
                )
                if e is not None
            )
        )
        allocation_evidence_ids = tuple(
            dict.fromkeys(
                fact.allocation_evidence.id
                for fact in facts
                if fact.allocation_evidence is not None
            )
        )
        application_evidence_ids = tuple(
            dict.fromkeys(
                fact.application_evidence.id
                for fact in facts
                if fact.application_evidence is not None
            )
        )

        def resolve_level(
            dimension: str,
            *,
            current_facts: tuple[FactorFact, ...] = tuple(facts),
            factor_name: str = name,
            allocation_evidence: tuple[str, ...] = allocation_evidence_ids,
            application_evidence: tuple[str, ...] = application_evidence_ids,
        ) -> tuple[NodeType | None, float, str | None]:
            field = "allocation_level" if dimension == "allocation" else "application_level"
            confidence_field = (
                "allocation_confidence" if dimension == "allocation" else "application_confidence"
            )
            candidates = sorted(
                {
                    candidate
                    for fact in current_facts
                    if (candidate := getattr(fact, field)) is not None
                },
                key=lambda node_type: rank_of(node_type) or 0,
            )
            if len(candidates) == 1:
                candidate = candidates[0]
                confidence = max(
                    getattr(fact, confidence_field)
                    for fact in current_facts
                    if getattr(fact, field) is candidate
                )
                return candidate, confidence, None

            if len(candidates) > 1:
                names = ", ".join(str(candidate) for candidate in candidates)
                contradiction = Contradiction(
                    id=stable_id(
                        "con",
                        block_id,
                        dimension,
                        factor_name,
                        *[str(candidate) for candidate in candidates],
                    ),
                    description=(
                        f"livello di {dimension} contraddittorio per il fattore "
                        f"'{factor_name}': {names}"
                    ),
                    evidence_ids=(
                        allocation_evidence if dimension == "allocation" else application_evidence
                    ),
                )
                acc.contradictions.append(contradiction)
                acc.questions.append(
                    Question(
                        id=stable_id("qst", contradiction.id),
                        text=(
                            f"Qual e il livello di {dimension} del fattore '{factor_name}'? "
                            f"Le fonti indicano {names}."
                        ),
                        reason=f"livelli di {dimension} in conflitto tra le fonti",
                        missing_field=f"factor[{factor_name}].{field}",
                        priority=100 if dimension == "allocation" else 75,
                        decisive=dimension == "allocation",
                        impact=(
                            "Determina l'unita sperimentale e il relativo n."
                            if dimension == "allocation"
                            else "Distingue dove l'intervento e applicato da dove e allocato."
                        ),
                    )
                )
                return None, 0.0, names

            acc.questions.append(
                Question(
                    id=stable_id("qst", block_id, dimension, factor_name),
                    text=(
                        "Quale unita ha ricevuto indipendentemente il livello del fattore "
                        f"'{factor_name}'?"
                        if dimension == "allocation"
                        else "A quale unita e stato materialmente applicato il fattore "
                        f"'{factor_name}'?"
                    ),
                    reason=f"livello di {dimension} non identificabile dal materiale",
                    missing_field=f"factor[{factor_name}].{field}",
                    priority=100 if dimension == "allocation" else 65,
                    decisive=dimension == "allocation",
                    impact=(
                        "Senza allocation non sono determinabili unita sperimentale e n indipendente."
                        if dimension == "allocation"
                        else "Evita di fondere applicazione fisica e allocazione indipendente."
                    ),
                )
            )
            return None, 0.0, None

        allocation, allocation_confidence, allocation_note = resolve_level("allocation")
        application, application_confidence, application_note = resolve_level("application")

        origin = (
            ProvenanceKind.TABULAR
            if any(f.origin is ProvenanceKind.TABULAR for f in facts)
            else ProvenanceKind.EXPLICIT
        )
        factors.append(
            Factor(
                id=stable_id("fac", block_id, name),
                name=name,
                levels=levels,
                kind=facts[0].kind,
                allocation_level=allocation,
                application_level=application,
                allocation_confidence=allocation_confidence,
                application_confidence=application_confidence,
                allocation_evidence_ids=allocation_evidence_ids,
                application_evidence_ids=application_evidence_ids,
                randomized=True if any(f.randomized for f in facts) else None,
                evidence_ids=evidence_ids,
                provenance=Provenance(
                    origin=origin,
                    evidence_ids=evidence_ids,
                    derivation=(
                        "; ".join(
                            note
                            for note in (
                                f"allocation alternative: {allocation_note}"
                                if allocation_note
                                else None,
                                f"application alternative: {application_note}"
                                if application_note
                                else None,
                            )
                            if note is not None
                        )
                        if allocation_note or application_note
                        else None
                    ),
                ),
            )
        )
    return tuple(factors)


def _build_contrasts(
    block_id: str, factors: tuple[Factor, ...], acc: _Accumulator
) -> tuple[Contrast, ...]:
    contrasts: list[Contrast] = []
    for factor in factors:
        levels = [level for level in factor.levels if level]
        if len(levels) < 2:
            continue
        pairs = list(combinations(sorted(levels), 2))
        if len(pairs) > MAX_CONTRASTS_PER_FACTOR:
            acc.warnings.append(
                f"fattore '{factor.name}': {len(pairs)} confronti possibili, "
                f"analizzati i primi {MAX_CONTRASTS_PER_FACTOR}"
            )
            pairs = pairs[:MAX_CONTRASTS_PER_FACTOR]
        for group_a, group_b in pairs:
            label = f"{group_a}_vs_{group_b}"
            contrasts.append(
                Contrast(
                    id=stable_id("cnt", block_id, factor.id, label),
                    label=label,
                    factor_ids=(factor.id,),
                    compared_levels=(group_a, group_b),
                    evidence_ids=factor.evidence_ids,
                    provenance=Provenance(
                        origin=ProvenanceKind.DERIVED,
                        evidence_ids=factor.evidence_ids,
                        derivation="confronto derivato dai livelli del fattore",
                    ),
                )
            )
    return tuple(contrasts)


def _build_design_graph(
    block_id: str,
    *,
    factors: tuple[Factor, ...],
    contrasts: tuple[Contrast, ...],
    endpoints: tuple[Endpoint, ...],
    models: tuple[StatisticalModelFact, ...],
    unit_nodes: dict[NodeType, GraphNode],
    inference_targets: tuple[InferenceTarget, ...] = (),
    estimands: tuple[Estimand, ...] = (),
) -> tuple[list[GraphNode], list[GraphRelation]]:
    """Materializza il vocabolario di disegno senza inferire fatti assenti.

    Gli archi ``allocated_to`` e ``applied_to`` sono volutamente distinti.
    ``declares_clustering`` descrive soltanto cio che il modello dichiara di
    modellare e non viene mai usato per completare l'allocation del fattore.
    """

    block_node = GraphNode(
        id=stable_id("ndg", block_id, "design"),
        type=NodeType.EXPERIMENT_BLOCK,
        label=block_id,
        attributes={"domain_id": block_id, "design_object": True},
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            derivation="radice tipizzata del design graph",
        ),
        confidence=1.0,
    )
    nodes: list[GraphNode] = [block_node]
    relations: list[GraphRelation] = []
    factor_nodes: dict[str, GraphNode] = {}
    contrast_nodes: dict[str, GraphNode] = {}
    endpoint_nodes: dict[str, GraphNode] = {}

    def add_relation(
        relation_type: RelationType,
        source: GraphNode,
        target: GraphNode,
        *,
        evidence_ids: tuple[str, ...] = (),
        provenance: Provenance,
        confidence: float = 1.0,
        attributes: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        relations.append(
            GraphRelation(
                id=make_relation_id(relation_type, source.id, target.id),
                type=relation_type,
                source=source.id,
                target=target.id,
                attributes=attributes or {},
                evidence_ids=evidence_ids,
                provenance=provenance,
                confidence=confidence,
            )
        )

    for factor in factors:
        confidence = max(
            factor.allocation_confidence,
            factor.application_confidence,
            0.5,
        )
        node = GraphNode(
            id=factor.id,
            type=NodeType.FACTOR,
            label=factor.name,
            attributes={"domain_id": factor.id, "kind": factor.kind},
            evidence_ids=factor.evidence_ids,
            provenance=factor.provenance,
            confidence=confidence,
        )
        nodes.append(node)
        factor_nodes[factor.id] = node
        add_relation(
            RelationType.HAS_FACTOR,
            block_node,
            node,
            evidence_ids=factor.evidence_ids,
            provenance=factor.provenance,
            confidence=confidence,
        )

        for level in factor.levels:
            level_node = GraphNode(
                id=stable_id("lvl", block_id, factor.id, level),
                type=NodeType.FACTOR_LEVEL,
                label=level,
                attributes={"factor_id": factor.id, "design_object": True},
                evidence_ids=factor.evidence_ids,
                provenance=factor.provenance,
                confidence=confidence,
            )
            nodes.append(level_node)
            add_relation(
                RelationType.HAS_LEVEL,
                node,
                level_node,
                evidence_ids=factor.evidence_ids,
                provenance=factor.provenance,
                confidence=confidence,
            )

        if factor.allocation_level is not None:
            allocation_node = unit_nodes[factor.allocation_level]
            allocation_evidence = factor.allocation_evidence_ids
            add_relation(
                RelationType.ALLOCATED_TO,
                node,
                allocation_node,
                evidence_ids=allocation_evidence,
                provenance=Provenance(
                    origin=factor.provenance.origin,
                    evidence_ids=allocation_evidence,
                    derivation="allocation_level dichiarato sul fattore",
                ),
                confidence=factor.allocation_confidence,
            )
            if factor.randomized:
                add_relation(
                    RelationType.RANDOMIZED_AT,
                    node,
                    allocation_node,
                    evidence_ids=allocation_evidence,
                    provenance=Provenance(
                        origin=factor.provenance.origin,
                        evidence_ids=allocation_evidence,
                        derivation="randomizzazione dichiarata sul fattore",
                    ),
                    confidence=factor.allocation_confidence,
                )

        if factor.application_level is not None:
            application_node = unit_nodes[factor.application_level]
            add_relation(
                RelationType.APPLIED_TO,
                node,
                application_node,
                evidence_ids=factor.application_evidence_ids,
                provenance=Provenance(
                    origin=factor.provenance.origin,
                    evidence_ids=factor.application_evidence_ids,
                    derivation="application_level dichiarato sul fattore",
                ),
                confidence=factor.application_confidence,
            )

    for endpoint in endpoints:
        node = GraphNode(
            id=endpoint.id,
            type=NodeType.ENDPOINT,
            label=endpoint.name,
            attributes={"domain_id": endpoint.id, "design_object": True},
            evidence_ids=endpoint.evidence_ids,
            provenance=endpoint.provenance,
            confidence=1.0,
        )
        nodes.append(node)
        endpoint_nodes[endpoint.id] = node
        add_relation(
            RelationType.HAS_ENDPOINT,
            block_node,
            node,
            evidence_ids=endpoint.evidence_ids,
            provenance=endpoint.provenance,
        )
        if endpoint.measured_on is not None:
            add_relation(
                RelationType.MEASURED_ON,
                node,
                unit_nodes[endpoint.measured_on],
                evidence_ids=endpoint.evidence_ids,
                provenance=endpoint.provenance,
            )

    for contrast in contrasts:
        node = GraphNode(
            id=contrast.id,
            type=NodeType.CONTRAST,
            label=contrast.label,
            attributes={"domain_id": contrast.id, "design_object": True},
            evidence_ids=contrast.evidence_ids,
            provenance=contrast.provenance,
            confidence=1.0,
        )
        nodes.append(node)
        contrast_nodes[contrast.id] = node
        for factor_id in contrast.factor_ids:
            factor_node = factor_nodes.get(factor_id)
            if factor_node is not None:
                add_relation(
                    RelationType.DEFINES_CONTRAST,
                    factor_node,
                    node,
                    evidence_ids=contrast.evidence_ids,
                    provenance=contrast.provenance,
                )
        for endpoint_id in contrast.endpoint_ids:
            endpoint_node = endpoint_nodes.get(endpoint_id)
            if endpoint_node is not None:
                add_relation(
                    RelationType.HAS_ENDPOINT,
                    node,
                    endpoint_node,
                    evidence_ids=contrast.evidence_ids,
                    provenance=contrast.provenance,
                )

    inferential_nodes, inferential_relations = _build_inferential_graph_objects(
        block_id,
        block_node=block_node,
        inference_targets=inference_targets,
        estimands=estimands,
    )
    nodes.extend(inferential_nodes)
    relations.extend(inferential_relations)

    for model in models:
        model_node = GraphNode(
            id=model.id,
            type=NodeType.STATISTICAL_MODEL,
            label=model.kind,
            attributes={"domain_id": model.id, "design_object": True},
            evidence_ids=model.evidence_ids,
            provenance=model.provenance,
            confidence=1.0,
        )
        nodes.append(model_node)
        for cluster_level in model.declared_clustering:
            add_relation(
                RelationType.DECLARES_CLUSTERING,
                model_node,
                unit_nodes[cluster_level],
                evidence_ids=model.evidence_ids,
                provenance=model.provenance,
            )

    return nodes, relations


def materialize_inferential_graph(
    hierarchy: Hierarchy,
    *,
    block_id: str,
    inference_targets: tuple[InferenceTarget, ...],
    estimands: tuple[Estimand, ...],
) -> Hierarchy:
    """Sincronizza target ed estimand correggibili nel grafo formale.

    Il parser deterministico non inventa questi oggetti. Quando vengono aggiunti,
    sostituiti o rimossi dall'utente, i corrispondenti nodi vengono rigenerati in
    modo idempotente lasciando intatto il resto del grafo scientifico.
    """

    inferential_types = {NodeType.INFERENCE_TARGET, NodeType.ESTIMAND}
    removed_ids = {node.id for node in hierarchy.nodes if node.type in inferential_types}
    retained_nodes = tuple(node for node in hierarchy.nodes if node.id not in removed_ids)
    retained_relations = tuple(
        relation
        for relation in hierarchy.relations
        if relation.source not in removed_ids and relation.target not in removed_ids
    )
    block_node = next(
        (
            node
            for node in retained_nodes
            if node.type is NodeType.EXPERIMENT_BLOCK
            and node.attributes.get("domain_id") == block_id
        ),
        None,
    )
    if block_node is None:
        block_node = GraphNode(
            id=stable_id("ndg", block_id, "design"),
            type=NodeType.EXPERIMENT_BLOCK,
            label=block_id,
            attributes={"domain_id": block_id, "design_object": True},
            provenance=Provenance(
                origin=ProvenanceKind.DERIVED,
                derivation="radice tipizzata del design graph",
            ),
            confidence=1.0,
        )
        retained_nodes = (*retained_nodes, block_node)

    nodes, relations = _build_inferential_graph_objects(
        block_id,
        block_node=block_node,
        inference_targets=inference_targets,
        estimands=estimands,
    )
    return Hierarchy(
        nodes=(*retained_nodes, *nodes),
        relations=(*retained_relations, *relations),
    )


def _build_inferential_graph_objects(
    block_id: str,
    *,
    block_node: GraphNode,
    inference_targets: tuple[InferenceTarget, ...],
    estimands: tuple[Estimand, ...],
) -> tuple[list[GraphNode], list[GraphRelation]]:
    """Materializza gli oggetti inferenziali senza completarli per supposizione."""

    nodes: list[GraphNode] = []
    relations: list[GraphRelation] = []

    def attach(node: GraphNode) -> None:
        nodes.append(node)
        relations.append(
            GraphRelation(
                id=make_relation_id(RelationType.CONTAINS, block_node.id, node.id),
                type=RelationType.CONTAINS,
                source=block_node.id,
                target=node.id,
                evidence_ids=node.evidence_ids,
                provenance=node.provenance,
                confidence=node.confidence,
            )
        )

    for target in inference_targets:
        confidence = {
            InferenceTargetStatus.USER_CONFIRMED: 1.0,
            InferenceTargetStatus.EXTRACTED: 0.75,
            InferenceTargetStatus.CONFLICTED: 0.5,
            InferenceTargetStatus.MISSING: 0.0,
        }[target.status]
        attach(
            GraphNode(
                id=target.id,
                type=NodeType.INFERENCE_TARGET,
                label=target.question_text or target.claim_text or target.id,
                attributes={
                    "domain_id": target.id,
                    "design_object": True,
                    "status": target.status.value,
                    "population_of_inference": target.population_of_inference,
                    "target_biological_unit": (
                        target.target_biological_unit.value
                        if target.target_biological_unit is not None
                        else None
                    ),
                    "factor_ids": ",".join(target.factor_ids),
                    "contrast_ids": ",".join(target.contrast_ids),
                    "endpoint_ids": ",".join(target.endpoint_ids),
                },
                evidence_ids=target.evidence_ids,
                provenance=target.provenance,
                confidence=confidence,
            )
        )

    for estimand in estimands:
        provenance = estimand.provenance or Provenance(
            origin=ProvenanceKind.DERIVED,
            evidence_ids=estimand.evidence_ids,
            derivation="estimand materializzato dal contratto confermato",
        )
        attach(
            GraphNode(
                id=estimand.id,
                type=NodeType.ESTIMAND,
                label=estimand.effect_measure,
                attributes={
                    "domain_id": estimand.id,
                    "design_object": True,
                    "endpoint_id": estimand.endpoint_id,
                    "effect_measure": estimand.effect_measure,
                    "target_population_or_unit": estimand.target_population_or_unit,
                    "generalization_level": estimand.generalization_level,
                    "factor_ids": ",".join(estimand.factor_ids),
                    "timepoint": estimand.timepoint,
                    "condition": estimand.condition,
                },
                evidence_ids=estimand.evidence_ids,
                provenance=provenance,
                confidence=1.0 if estimand.provenance is not None else 0.75,
            )
        )

    return nodes, relations


def _build_endpoints(
    block_id: str, endpoint_facts: list[EndpointFact], acc: _Accumulator
) -> tuple[Endpoint, ...]:
    grouped: dict[str, list[EndpointFact]] = {}
    for fact in endpoint_facts:
        grouped.setdefault(fact.name.strip().lower(), []).append(fact)

    endpoints: list[Endpoint] = []
    for key, facts in grouped.items():
        measured_candidates = {fact.measured_on for fact in facts if fact.measured_on is not None}
        evidence_ids = tuple(dict.fromkeys(f.evidence.id for f in facts if f.evidence is not None))
        measured = next(iter(measured_candidates)) if len(measured_candidates) == 1 else None
        if len(measured_candidates) > 1:
            contradiction = Contradiction(
                id=stable_id(
                    "con",
                    block_id,
                    "endpoint-measured-on",
                    key,
                    *sorted(str(item) for item in measured_candidates),
                ),
                description=(
                    f"livello di misura contraddittorio per l'endpoint '{facts[0].name}': "
                    f"{sorted(str(item) for item in measured_candidates)}"
                ),
                evidence_ids=evidence_ids,
            )
            acc.contradictions.append(contradiction)
            acc.questions.append(
                Question(
                    id=stable_id("qst", contradiction.id),
                    text=(
                        f"Su quale livello e misurato l'endpoint '{facts[0].name}'? "
                        "Le fonti indicano livelli diversi."
                    ),
                    reason="livello di misura dell'endpoint in conflitto",
                    missing_field=f"endpoint[{key}].measured_on",
                )
            )
        endpoints.append(
            Endpoint(
                id=stable_id("end", block_id, key),
                name=facts[0].name,
                measured_on=measured,
                aggregation=next((f.aggregation for f in facts if f.aggregation), None),
                timepoints=tuple(
                    dict.fromkeys(timepoint for fact in facts for timepoint in fact.timepoints)
                ),
                evidence_ids=evidence_ids,
                provenance=Provenance(origin=ProvenanceKind.EXPLICIT, evidence_ids=evidence_ids),
            )
        )
    return tuple(endpoints)


def _normalize_scope_label(value: str) -> str:
    return " ".join(re.findall(r"[\w+./-]+", value.casefold()))


def _match_endpoint(hint: str | None, endpoints: tuple[Endpoint, ...]) -> Endpoint | None:
    if not hint:
        return None
    normalized = _normalize_scope_label(hint)
    matches = [
        endpoint
        for endpoint in endpoints
        if _normalize_scope_label(endpoint.name) == normalized
        or _normalize_scope_label(endpoint.name).startswith(f"{normalized} per ")
    ]
    if len(matches) == 1:
        return matches[0]
    # Una sola variabile nel blocco rende un riferimento locale non ambiguo
    # (per esempio il titolo di una figure legend).
    return endpoints[0] if len(endpoints) == 1 else None


def _factor_for_group(group: str | None, factors: tuple[Factor, ...]) -> Factor | None:
    if not group:
        return None
    if group == "per_group":
        return factors[0] if len(factors) == 1 else None
    normalized = _normalize_scope_label(group)
    matches = [
        factor
        for factor in factors
        if any(_normalize_scope_label(level) == normalized for level in factor.levels)
    ]
    return matches[0] if len(matches) == 1 else None


def _contrast_for_scope(
    group: str | None,
    factor: Factor | None,
    contrasts: tuple[Contrast, ...],
    *,
    endpoint_explicit: bool,
) -> Contrast | None:
    candidates = [
        contrast for contrast in contrasts if factor is None or contrast.factor_id == factor.id
    ]
    if group and group != "per_group":
        normalized = _normalize_scope_label(group)
        candidates = [
            contrast
            for contrast in candidates
            if normalized
            in {
                _normalize_scope_label(contrast.group_a or ""),
                _normalize_scope_label(contrast.group_b or ""),
            }
        ]
    if len(candidates) == 1 and (group is not None or endpoint_explicit):
        return candidates[0]
    return None


def _build_n_statements(
    block_id: str,
    n_facts: list[NFact],
    factors: tuple[Factor, ...],
    contrasts: tuple[Contrast, ...],
    endpoints: tuple[Endpoint, ...],
    acc: _Accumulator,
) -> tuple[NStatement, ...]:
    statements: list[NStatement] = []
    for fact in n_facts:
        endpoint = _match_endpoint(fact.endpoint_hint, endpoints)
        group = fact.group_hint or (
            "per_group" if any(q == "per_group" for q in fact.qualifiers) else None
        )
        factor = _factor_for_group(group, factors)
        if factor is None and endpoint is not None and len(factors) == 1:
            factor = factors[0]
        contrast = _contrast_for_scope(
            group,
            factor,
            contrasts,
            endpoint_explicit=endpoint is not None,
        )
        if contrast is not None and factor is None:
            factor = next((item for item in factors if item.id == contrast.factor_id), None)
        scope = NScope(
            factor_id=factor.id if factor else None,
            contrast_id=contrast.id if contrast else None,
            endpoint_id=endpoint.id if endpoint else None,
            group=group,
            timepoint=fact.timepoint_hint,
            is_global=not any((factor, contrast, endpoint, group, fact.timepoint_hint)),
        )
        evidence_ids = (fact.evidence.id,) if fact.evidence else ()
        statement = NStatement(
            id=stable_id(
                "nst",
                block_id,
                fact.raw_text,
                fact.value,
                fact.entity_text,
                fact.kind,
                scope.key(),
                evidence_ids,
            ),
            value=fact.value,
            entity_type=fact.entity_text or "non specificata",
            node_type=fact.node_type,
            scope=scope,
            kind=fact.kind,
            qualifiers=fact.qualifiers,
            raw_text=fact.raw_text,
            evidence_ids=evidence_ids,
            provenance=Provenance(origin=fact.origin, evidence_ids=evidence_ids),
            confidence=fact.confidence,
        )
        statements.append(statement)
        if fact.endpoint_hint and endpoint is None:
            acc.questions.append(
                Question(
                    id=stable_id("qst", block_id, "n-endpoint", fact.endpoint_hint),
                    text=(
                        f"A quale endpoint si riferisce '{fact.raw_text}'? Il riferimento "
                        f"'{fact.endpoint_hint}' non e univoco nel blocco."
                    ),
                    reason="scope endpoint della menzione di n non risolto",
                    missing_field=f"n_statement[{statement.id}].scope.endpoint_id",
                )
            )
        if fact.group_hint and factor is None:
            acc.questions.append(
                Question(
                    id=stable_id("qst", block_id, "n-group", fact.group_hint),
                    text=(
                        f"A quale fattore appartiene il gruppo '{fact.group_hint}' citato "
                        f"in '{fact.raw_text}'?"
                    ),
                    reason="scope di gruppo non associabile a un solo fattore",
                    missing_field=f"n_statement[{statement.id}].scope.factor_id",
                )
            )
        if fact.ambiguous_entity:
            acc.questions.append(
                Question(
                    id=stable_id("qst", block_id, "nentity", fact.raw_text),
                    text=(
                        f'A quale entita si riferisce "{fact.raw_text}"? '
                        "Il termine usato non identifica un livello sperimentale."
                    ),
                    reason="entita di n non risolvibile a un livello del grafo",
                    missing_field="n_statement.entity_type",
                )
            )
    return tuple(statements)


def _bind_contrast_endpoints(
    contrasts: tuple[Contrast, ...], statements: tuple[NStatement, ...]
) -> tuple[Contrast, ...]:
    """Collega endpoint e contrasto solo attraverso scope di n gia risolti."""

    bound: list[Contrast] = []
    for contrast in contrasts:
        endpoint_ids = tuple(
            dict.fromkeys(
                statement.scope.endpoint_id
                for statement in statements
                if statement.scope.contrast_id == contrast.id
                and statement.scope.endpoint_id is not None
            )
        )
        bound.append(
            contrast.model_copy(
                update={
                    "endpoint_ids": endpoint_ids,
                    "endpoint_id": endpoint_ids[0] if endpoint_ids else None,
                }
            )
        )
    return tuple(bound)


def _register_n_statement_conflicts(
    block_id: str, statements: tuple[NStatement, ...], acc: _Accumulator
) -> None:
    """Valori diversi confliggono solo nello stesso scope e nello stesso stato di n."""

    grouped: dict[tuple[object, ...], list[NStatement]] = {}
    for statement in statements:
        if statement.value is None:
            continue
        scope_key: tuple[object, ...] = (
            statement.node_type,
            statement.kind,
            *statement.scope.key(),
        )
        grouped.setdefault(scope_key, []).append(statement)
    for conflict_key, scoped in grouped.items():
        values = sorted({statement.value for statement in scoped if statement.value is not None})
        if len(values) < 2:
            continue
        contradiction = Contradiction(
            id=stable_id("con", block_id, "n-scope", conflict_key, *values),
            description=(
                f"valori di n contraddittori nello stesso scope "
                f"({scoped[0].scope.describe()}): {values}"
            ),
            statement_ids=tuple(statement.id for statement in scoped),
            evidence_ids=tuple(
                dict.fromkeys(
                    evidence_id for statement in scoped for evidence_id in statement.evidence_ids
                )
            ),
        )
        acc.contradictions.append(contradiction)
        acc.questions.append(
            Question(
                id=stable_id("qst", contradiction.id),
                text=(
                    f"Qual e il valore corretto di n per {scoped[0].scope.describe()}? "
                    f"Le fonti riportano {values}."
                ),
                reason="valori di n incompatibili nello stesso scope",
                missing_field="n_statement.value",
                scope=scoped[0].scope,
                priority=95,
                decisive=True,
                impact="Il valore di n per questo scope resta indeterminato finche il conflitto non e risolto.",
            )
        )
