"""Validazione strutturale del grafo e degli ``ExperimentBlock``.

Il validator controlla soltanto invarianti di struttura e provenance. Non decide
quale unita sperimentale sia scientificamente corretta e non aggiunge relazioni:
quelle decisioni restano nel ruleset approvato e nel processo di adjudication.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

import networkx as nx

from ntruth.schemas.core import Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    Contrast,
    Endpoint,
    ExperimentBlock,
    Factor,
    GraphStatus,
    Hierarchy,
    InferenceTarget,
    NScope,
    inference_target_scope_mismatches,
)
from ntruth.schemas.graph import (
    GraphRelation,
    GraphViolation,
    NodeType,
    RelationType,
    rank_of,
)


class GraphValidationError(ValueError):
    """Il grafo contiene almeno una violazione bloccante."""

    def __init__(self, violations: Iterable[GraphViolation]) -> None:
        self.violations = tuple(violations)
        details = "; ".join(f"{item.code}: {item.message}" for item in self.violations)
        super().__init__(details or "grafo non valido")


def blocking_violations(
    violations: Iterable[GraphViolation],
) -> tuple[GraphViolation, ...]:
    """Restituisce soltanto le violazioni che devono bloccare l'inferenza."""

    return tuple(item for item in violations if item.blocking)


def validate_hierarchy(
    hierarchy: Hierarchy,
    *,
    evidence_ids: Iterable[str] | None = None,
) -> tuple[GraphViolation, ...]:
    """Valida identita, riferimenti, provenance e aciclicita del grafo.

    ``evidence_ids`` e facoltativo per mantenere il validator riusabile sul solo
    ``graph.json``. Quando viene fornito, ogni riferimento a evidenza viene
    controllato rispetto al registro del blocco.
    """

    violations: list[GraphViolation] = []
    known_evidence = set(evidence_ids) if evidence_ids is not None else None

    duplicate_node_ids = _duplicates(node.id for node in hierarchy.nodes)
    for node_id in duplicate_node_ids:
        violations.append(
            GraphViolation(
                code="duplicate_node_id",
                message=f"node id duplicato: {node_id}",
                node_ids=(node_id,),
            )
        )

    duplicate_relation_ids = _duplicates(relation.id for relation in hierarchy.relations)
    for relation_id in duplicate_relation_ids:
        violations.append(
            GraphViolation(
                code="duplicate_relation_id",
                message=f"relation id duplicato: {relation_id}",
                relation_ids=(relation_id,),
            )
        )

    nodes_by_id = {node.id: node for node in hierarchy.nodes}
    for node in hierarchy.nodes:
        _append_graph_provenance_violations(
            violations,
            owner_kind="node",
            owner_id=node.id,
            evidence_ids=node.evidence_ids,
            provenance=node.provenance,
            node_ids=(node.id,),
        )
        if node.provenance.origin is ProvenanceKind.MODEL:
            if not node.evidence_ids:
                violations.append(
                    GraphViolation(
                        code="model_node_without_evidence",
                        message=f"il candidate node AI {node.id} non ha evidence_ids",
                        node_ids=(node.id,),
                    )
                )
            if "confidence" not in node.model_fields_set:
                violations.append(
                    GraphViolation(
                        code="model_node_without_confidence",
                        message=f"il candidate node AI {node.id} non ha confidence esplicita",
                        node_ids=(node.id,),
                    )
                )
    for relation in hierarchy.relations:
        missing: list[str] = []
        if relation.source not in nodes_by_id:
            missing.append(relation.source)
        if relation.target not in nodes_by_id:
            missing.append(relation.target)
        if missing:
            violations.append(
                GraphViolation(
                    code="dangling_relation_endpoint",
                    message=(
                        f"la relazione {relation.id} riferisce nodi inesistenti: "
                        f"{', '.join(missing)}"
                    ),
                    node_ids=tuple(missing),
                    relation_ids=(relation.id,),
                )
            )
            continue

        _append_graph_provenance_violations(
            violations,
            owner_kind="relation",
            owner_id=relation.id,
            evidence_ids=relation.evidence_ids,
            provenance=relation.provenance,
            relation_ids=(relation.id,),
        )

        if relation.provenance.origin is ProvenanceKind.MODEL:
            if not relation.evidence_ids:
                violations.append(
                    GraphViolation(
                        code="model_relation_without_evidence",
                        message=f"il candidate edge AI {relation.id} non ha evidence_ids",
                        relation_ids=(relation.id,),
                    )
                )
            if "confidence" not in relation.model_fields_set:
                violations.append(
                    GraphViolation(
                        code="model_relation_without_confidence",
                        message=f"il candidate edge AI {relation.id} non ha confidence esplicita",
                        relation_ids=(relation.id,),
                    )
                )

        if relation.type is RelationType.NESTED_IN:
            child = nodes_by_id[relation.source]
            parent = nodes_by_id[relation.target]
            child_rank = rank_of(child.type)
            parent_rank = rank_of(parent.type)
            if child_rank is not None and parent_rank is not None and child_rank <= parent_rank:
                violations.append(
                    GraphViolation(
                        code="hierarchy_inversion",
                        message=(
                            f"{child.type} nested_in {parent.type} inverte o appiattisce "
                            "l'ordine di contenimento"
                        ),
                        node_ids=(child.id, parent.id),
                        relation_ids=(relation.id,),
                    )
                )

    if known_evidence is not None:
        for node in hierarchy.nodes:
            _append_missing_evidence(
                violations,
                owner_kind="node",
                owner_id=node.id,
                referenced=(*node.evidence_ids, *node.provenance.evidence_ids),
                known=known_evidence,
                node_ids=(node.id,),
            )
        for relation in hierarchy.relations:
            _append_missing_evidence(
                violations,
                owner_kind="relation",
                owner_id=relation.id,
                referenced=(*relation.evidence_ids, *relation.provenance.evidence_ids),
                known=known_evidence,
                relation_ids=(relation.id,),
            )

    cycle = _first_containment_cycle(hierarchy.relations, set(nodes_by_id))
    if cycle:
        cycle_nodes = tuple(dict.fromkeys((*cycle, cycle[0])))
        violations.append(
            GraphViolation(
                code="containment_cycle",
                message=f"ciclo nella gerarchia di contenimento: {' -> '.join(cycle_nodes)}",
                node_ids=cycle_nodes,
            )
        )

    return tuple(violations)


def _append_graph_provenance_violations(
    violations: list[GraphViolation],
    *,
    owner_kind: str,
    owner_id: str,
    evidence_ids: tuple[str, ...],
    provenance: Provenance,
    node_ids: tuple[str, ...] = (),
    relation_ids: tuple[str, ...] = (),
) -> None:
    """Applica la matrice di lineage v6 a ogni nodo e arco."""

    origin = provenance.origin
    provenance_evidence = tuple(provenance.evidence_ids)
    if not set(evidence_ids).issubset(provenance_evidence):
        violations.append(
            GraphViolation(
                code="graph_evidence_provenance_mismatch",
                message=f"{owner_kind} {owner_id}: evidence_ids assenti dalla provenance",
                node_ids=node_ids,
                relation_ids=relation_ids,
            )
        )
    if origin in {ProvenanceKind.EXPLICIT, ProvenanceKind.TABULAR} and not evidence_ids:
        violations.append(
            GraphViolation(
                code="source_graph_element_without_evidence",
                message=f"{owner_kind} {owner_id}: origine {origin.value} senza evidenza locale",
                node_ids=node_ids,
                relation_ids=relation_ids,
            )
        )
    elif origin is ProvenanceKind.DERIVED and not (
        provenance.derivation and provenance.derivation.strip()
    ):
        violations.append(
            GraphViolation(
                code="derived_graph_element_without_derivation",
                message=f"{owner_kind} {owner_id}: origine derived senza derivazione",
                node_ids=node_ids,
                relation_ids=relation_ids,
            )
        )
    elif origin is ProvenanceKind.RULE:
        versioned_rule = bool(provenance.rule_id and provenance.ruleset_version)
        has_inputs = bool(evidence_ids or (provenance.derivation and provenance.derivation.strip()))
        if not versioned_rule or not has_inputs:
            violations.append(
                GraphViolation(
                    code="rule_graph_element_without_trace",
                    message=(
                        f"{owner_kind} {owner_id}: origine rule senza rule/version "
                        "e input o derivazione"
                    ),
                    node_ids=node_ids,
                    relation_ids=relation_ids,
                )
            )
    elif origin in {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION}:
        timestamp = provenance.timestamp
        timestamp_aware = (
            timestamp is not None
            and timestamp.tzinfo is not None
            and timestamp.utcoffset() is not None
        )
        actor_present = bool(provenance.actor_role and provenance.actor_role.strip())
        correction_audit = bool(
            provenance.correction_id and provenance.correction_id.strip() and timestamp_aware
        )
        initial_confirmation = bool(evidence_ids and actor_present)
        traceable = actor_present and (
            correction_audit
            if (
                origin is ProvenanceKind.ADJUDICATION
                or provenance.correction_id
                or provenance.correction_role
            )
            else initial_confirmation
        )
        if not traceable:
            violations.append(
                GraphViolation(
                    code="human_graph_element_without_audit",
                    message=(
                        f"{owner_kind} {owner_id}: provenance umana senza evidenza di "
                        "conferma iniziale oppure audit completo della correzione"
                    ),
                    node_ids=node_ids,
                    relation_ids=relation_ids,
                )
            )


def assert_valid_hierarchy(
    hierarchy: Hierarchy,
    *,
    evidence_ids: Iterable[str] | None = None,
) -> None:
    """Solleva ``GraphValidationError`` se il grafo non e inferibile in sicurezza."""

    blocking = blocking_violations(validate_hierarchy(hierarchy, evidence_ids=evidence_ids))
    if blocking:
        raise GraphValidationError(blocking)


def validate_experiment_block(block: ExperimentBlock) -> tuple[GraphViolation, ...]:
    """Valida i riferimenti strutturali che attraversano un ``ExperimentBlock``."""

    violations: list[GraphViolation] = []
    evidence_ids = {item.id for item in block.evidence}
    violations.extend(validate_hierarchy(block.hierarchy, evidence_ids=evidence_ids))

    _append_duplicate_violations(
        violations, "duplicate_evidence_id", "evidence", (item.id for item in block.evidence)
    )
    _append_duplicate_violations(
        violations,
        "duplicate_inference_target_id",
        "inference target",
        (item.id for item in block.inference_targets),
    )
    _append_duplicate_violations(
        violations, "duplicate_factor_id", "factor", (item.id for item in block.factors)
    )
    _append_duplicate_violations(
        violations, "duplicate_contrast_id", "contrast", (item.id for item in block.contrasts)
    )
    _append_duplicate_violations(
        violations, "duplicate_endpoint_id", "endpoint", (item.id for item in block.endpoints)
    )
    _append_duplicate_violations(
        violations, "duplicate_estimand_id", "estimand", (item.id for item in block.estimands)
    )
    _append_duplicate_violations(
        violations, "duplicate_model_id", "model", (item.id for item in block.models)
    )
    _append_duplicate_violations(
        violations, "duplicate_process_id", "process", (item.id for item in block.processes)
    )
    _append_duplicate_violations(
        violations,
        "duplicate_n_statement_id",
        "n statement",
        (item.id for item in block.n_statements),
    )
    _append_duplicate_violations(
        violations,
        "duplicate_count_record_id",
        "count record",
        (item.count_id for item in block.count_records),
    )
    _append_duplicate_violations(
        violations,
        "duplicate_exclusion_record_id",
        "exclusion record",
        (item.id for item in block.exclusion_records),
    )
    _append_duplicate_violations(
        violations,
        "duplicate_assessment_id",
        "unit assessment",
        (item.id for item in block.unit_assessments),
    )
    _append_duplicate_violations(
        violations, "duplicate_alert_id", "alert", (item.id for item in block.alerts)
    )
    _append_duplicate_violations(
        violations, "duplicate_question_id", "question", (item.id for item in block.questions)
    )
    _append_duplicate_violations(
        violations,
        "duplicate_contradiction_id",
        "contradiction",
        (item.id for item in block.contradictions),
    )
    _append_duplicate_violations(
        violations,
        "duplicate_correction_id",
        "correction",
        (item.id for item in block.corrections),
    )

    factors = {item.id: item for item in block.factors}
    inference_targets = {item.id: item for item in block.inference_targets}
    contrasts = {item.id: item for item in block.contrasts}
    endpoints = {item.id: item for item in block.endpoints}
    statements = {item.id: item for item in block.n_statements}
    questions = {item.id: item for item in block.questions}
    graph_nodes = {item.id: item for item in block.hierarchy.nodes}

    violations.extend(
        _validate_plausible_graph_set(
            block,
            evidence_ids=evidence_ids,
            factors=factors,
            contrasts=contrasts,
            endpoints=endpoints,
            inference_targets=inference_targets,
            questions=questions,
        )
    )

    for target in block.inference_targets:
        node = graph_nodes.get(target.id)
        if node is None or node.type is not NodeType.INFERENCE_TARGET:
            violations.append(
                GraphViolation(
                    code="missing_inference_target_node",
                    message=(
                        f"inference target {target.id} non materializzato come nodo "
                        "InferenceTarget del grafo"
                    ),
                    node_ids=(target.id,),
                    blocking=False,
                )
            )
    for estimand in block.estimands:
        node = graph_nodes.get(estimand.id)
        if node is None or node.type is not NodeType.ESTIMAND:
            violations.append(
                GraphViolation(
                    code="missing_estimand_node",
                    message=f"estimand {estimand.id} non materializzato come nodo Estimand del grafo",
                    node_ids=(estimand.id,),
                    blocking=False,
                )
            )

    for contrast in block.contrasts:
        for factor_id in contrast.factor_ids:
            if factor_id not in factors:
                violations.append(
                    _reference_violation(
                        "dangling_contrast_factor",
                        f"contrast {contrast.id}",
                        "factor",
                        factor_id,
                    )
                )
        for endpoint_id in contrast.endpoint_ids:
            if endpoint_id not in endpoints:
                violations.append(
                    _reference_violation(
                        "dangling_contrast_endpoint",
                        f"contrast {contrast.id}",
                        "endpoint",
                        endpoint_id,
                    )
                )

    for estimand in block.estimands:
        if estimand.endpoint_id not in endpoints:
            violations.append(
                _reference_violation(
                    "dangling_estimand_endpoint",
                    f"estimand {estimand.id}",
                    "endpoint",
                    estimand.endpoint_id,
                )
            )
        for factor_id in estimand.factor_ids:
            if factor_id not in factors:
                violations.append(
                    _reference_violation(
                        "dangling_estimand_factor",
                        f"estimand {estimand.id}",
                        "factor",
                        factor_id,
                    )
                )

    scoped_items = [
        *((f"n statement {item.id}", item.scope) for item in block.n_statements),
        *((f"unit assessment {item.id}", item.scope) for item in block.unit_assessments),
        *((f"alert {item.id}", item.scope) for item in block.alerts if item.scope is not None),
        *(
            (f"question {item.id}", item.scope)
            for item in block.questions
            if item.scope is not None
        ),
    ]
    for owner, scope in scoped_items:
        violations.extend(
            _validate_scope(
                owner,
                scope,
                factors=factors,
                contrasts=contrasts,
                endpoints=endpoints,
                inference_targets=inference_targets,
            )
        )

    for count in block.count_records:
        owner = f"count record {count.count_id}"
        if count.scope.factor_id is not None and count.scope.factor_id not in factors:
            violations.append(
                _reference_violation(
                    "dangling_count_factor", owner, "factor", count.scope.factor_id
                )
            )
        if count.scope.contrast_id is not None and count.scope.contrast_id not in contrasts:
            violations.append(
                _reference_violation(
                    "dangling_count_contrast", owner, "contrast", count.scope.contrast_id
                )
            )
        if count.scope.endpoint_id is not None and count.scope.endpoint_id not in endpoints:
            violations.append(
                _reference_violation(
                    "dangling_count_endpoint", owner, "endpoint", count.scope.endpoint_id
                )
            )

    for exclusion in block.exclusion_records:
        owner = f"exclusion record {exclusion.id}"
        if exclusion.factor_id is not None and exclusion.factor_id not in factors:
            violations.append(
                _reference_violation(
                    "dangling_exclusion_factor", owner, "factor", exclusion.factor_id
                )
            )
        if exclusion.contrast_id is not None and exclusion.contrast_id not in contrasts:
            violations.append(
                _reference_violation(
                    "dangling_exclusion_contrast", owner, "contrast", exclusion.contrast_id
                )
            )
        if exclusion.endpoint_id is not None and exclusion.endpoint_id not in endpoints:
            violations.append(
                _reference_violation(
                    "dangling_exclusion_endpoint", owner, "endpoint", exclusion.endpoint_id
                )
            )
        if exclusion.unit_id is not None:
            unit = graph_nodes.get(exclusion.unit_id)
            if unit is None:
                violations.append(
                    _reference_violation(
                        "dangling_exclusion_unit", owner, "graph unit", exclusion.unit_id
                    )
                )
            elif unit.type is not exclusion.unit_type:
                violations.append(
                    GraphViolation(
                        code="exclusion_unit_type_mismatch",
                        message=(
                            f"{owner} dichiara unit_type={exclusion.unit_type.value}, "
                            f"ma il nodo {unit.id} ha type={unit.type.value}"
                        ),
                        node_ids=(unit.id,),
                    )
                )

    for alert in block.alerts:
        for question_id in alert.question_ids:
            if question_id not in questions:
                violations.append(
                    _reference_violation(
                        "dangling_alert_question",
                        f"alert {alert.id}",
                        "question",
                        question_id,
                    )
                )

    for contradiction in block.contradictions:
        for statement_id in contradiction.statement_ids:
            if statement_id not in statements:
                violations.append(
                    _reference_violation(
                        "dangling_contradiction_statement",
                        f"contradiction {contradiction.id}",
                        "n statement",
                        statement_id,
                    )
                )

    _validate_block_evidence(block, evidence_ids, violations)
    _validate_correction_order(block, violations)

    source_file_ids = set(block.source_file_ids)
    if source_file_ids:
        for evidence in block.evidence:
            if evidence.file_id not in source_file_ids:
                violations.append(
                    _reference_violation(
                        "dangling_evidence_file",
                        f"evidence {evidence.id}",
                        "source file",
                        evidence.file_id,
                    )
                )

    return tuple(violations)


def assert_valid_experiment_block(block: ExperimentBlock) -> None:
    """Solleva se il blocco contiene riferimenti o topologia non validi."""

    blocking = blocking_violations(validate_experiment_block(block))
    if blocking:
        raise GraphValidationError(blocking)


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    counts = Counter(values)
    return tuple(sorted(value for value, count in counts.items() if count > 1))


def _append_duplicate_violations(
    violations: list[GraphViolation],
    code: str,
    label: str,
    values: Iterable[str],
) -> None:
    for value in _duplicates(values):
        violations.append(GraphViolation(code=code, message=f"{label} id duplicato: {value}"))


def _append_missing_evidence(
    violations: list[GraphViolation],
    *,
    owner_kind: str,
    owner_id: str,
    referenced: Iterable[str],
    known: set[str],
    node_ids: tuple[str, ...] = (),
    relation_ids: tuple[str, ...] = (),
) -> None:
    missing = sorted(set(referenced) - known)
    if not missing:
        return
    violations.append(
        GraphViolation(
            code="dangling_evidence",
            message=(
                f"{owner_kind} {owner_id} riferisce evidenze inesistenti: {', '.join(missing)}"
            ),
            node_ids=node_ids,
            relation_ids=relation_ids,
        )
    )


def _first_containment_cycle(
    relations: Iterable[GraphRelation], known_nodes: set[str]
) -> tuple[str, ...]:
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(known_nodes)
    for relation in relations:
        if relation.source not in known_nodes or relation.target not in known_nodes:
            continue
        edge = _canonical_containment_edge(relation)
        if edge is not None:
            graph.add_edge(*edge)
    try:
        cycle_edges = nx.find_cycle(graph, orientation="original")
    except nx.NetworkXNoCycle:
        return ()
    return tuple(edge[0] for edge in cycle_edges)


def _canonical_containment_edge(relation: GraphRelation) -> tuple[str, str] | None:
    """Normalizza ogni relazione gerarchica come ``figlio -> genitore``."""

    if relation.type in {
        RelationType.NESTED_IN,
        RelationType.DERIVED_FROM,
        RelationType.SPLIT_FROM,
        RelationType.POOLED_INTO,
        RelationType.MEMBER_OF_POOL,
    }:
        return relation.source, relation.target
    if relation.type in {RelationType.CONTAINS, RelationType.SPLIT_INTO}:
        return relation.target, relation.source
    return None


def _validate_scope(
    owner: str,
    scope: NScope,
    *,
    factors: Mapping[str, Factor],
    contrasts: Mapping[str, Contrast],
    endpoints: Mapping[str, Endpoint],
    inference_targets: Mapping[str, InferenceTarget],
) -> tuple[GraphViolation, ...]:
    violations: list[GraphViolation] = []
    if scope.factor_id is not None and scope.factor_id not in factors:
        violations.append(
            _reference_violation("dangling_scope_factor", owner, "factor", scope.factor_id)
        )
    if scope.contrast_id is not None and scope.contrast_id not in contrasts:
        violations.append(
            _reference_violation("dangling_scope_contrast", owner, "contrast", scope.contrast_id)
        )
    if scope.endpoint_id is not None and scope.endpoint_id not in endpoints:
        violations.append(
            _reference_violation("dangling_scope_endpoint", owner, "endpoint", scope.endpoint_id)
        )
    if scope.inference_target_id is not None and scope.inference_target_id not in inference_targets:
        violations.append(
            _reference_violation(
                "dangling_scope_inference_target",
                owner,
                "inference target",
                scope.inference_target_id,
            )
        )
    contrast_id = scope.contrast_id
    if contrast_id is not None and contrast_id in contrasts and scope.factor_id is not None:
        contrast = contrasts[contrast_id]
        contrast_factors = contrast.factor_ids
        if scope.factor_id not in contrast_factors:
            violations.append(
                GraphViolation(
                    code="scope_factor_contrast_mismatch",
                    message=(
                        f"{owner} usa factor {scope.factor_id}, ma contrast "
                        f"{contrast_id} appartiene a {', '.join(contrast_factors)}"
                    ),
                )
            )
    target_id = scope.inference_target_id
    if target_id is not None and target_id in inference_targets:
        for dimension in inference_target_scope_mismatches(
            scope,
            inference_targets[target_id],
            factors=factors,
            contrasts=contrasts,
            endpoints=endpoints,
        ):
            violations.append(
                GraphViolation(
                    code=f"scope_target_{dimension}_mismatch",
                    message=f"{owner} usa {dimension} incompatibile con inference target {target_id}",
                )
            )
    return tuple(violations)


def _validate_plausible_graph_set(
    block: ExperimentBlock,
    *,
    evidence_ids: set[str],
    factors: Mapping[str, Factor],
    contrasts: Mapping[str, Contrast],
    endpoints: Mapping[str, Endpoint],
    inference_targets: Mapping[str, InferenceTarget],
    questions: Mapping[str, object],
) -> tuple[GraphViolation, ...]:
    """Valida fail-closed i rami che autorizzano ``MULTIPLE_PLAUSIBLE_GRAPHS``."""

    graph_set = block.plausible_graph_set
    if graph_set is None:
        return ()

    violations: list[GraphViolation] = []
    if block.graph_status is not GraphStatus.CONDITIONAL:
        violations.append(
            GraphViolation(
                code="alternative_graph_set_without_conditional_status",
                message="plausible_graph_set richiede graph_status=conditional",
            )
        )
    if len(graph_set.alternatives) < 2:
        violations.append(
            GraphViolation(
                code="alternative_graph_set_too_small",
                message="plausible_graph_set richiede almeno due grafi alternativi",
            )
        )
    _append_duplicate_violations(
        violations,
        "duplicate_alternative_graph_id",
        "alternative graph",
        (item.id for item in graph_set.alternatives),
    )
    signatures = [item.scientific_signature() for item in graph_set.alternatives]
    if len(signatures) != len(set(signatures)):
        violations.append(
            GraphViolation(
                code="duplicate_alternative_graph_content",
                message="plausible_graph_set contiene grafi scientificamente equivalenti",
            )
        )

    question = questions.get(graph_set.discriminating_question_id)
    if question is None:
        violations.append(
            _reference_violation(
                "dangling_alternative_graph_question",
                f"plausible graph set {graph_set.id}",
                "question",
                graph_set.discriminating_question_id,
            )
        )
    elif not bool(getattr(question, "decisive", False)):
        violations.append(
            GraphViolation(
                code="alternative_graph_question_not_decisive",
                message=(
                    f"question {graph_set.discriminating_question_id} deve avere decisive=true"
                ),
            )
        )

    _append_alternative_traceability_violations(
        violations,
        owner_kind="plausible graph set",
        owner_id=graph_set.id,
        direct_evidence=graph_set.evidence_ids,
        provenance=graph_set.provenance,
        known_evidence=evidence_ids,
    )
    for alternative in graph_set.alternatives:
        _append_alternative_traceability_violations(
            violations,
            owner_kind="alternative graph",
            owner_id=alternative.id,
            direct_evidence=alternative.evidence_ids,
            provenance=alternative.provenance,
            known_evidence=evidence_ids,
        )
        if not alternative.hierarchy.nodes:
            violations.append(
                GraphViolation(
                    code="empty_alternative_graph",
                    message=f"alternative graph {alternative.id} non contiene nodi",
                )
            )
        violations.extend(validate_hierarchy(alternative.hierarchy, evidence_ids=evidence_ids))
        _append_duplicate_violations(
            violations,
            "duplicate_alternative_consequence_id",
            f"alternative graph {alternative.id} consequence",
            (item.id for item in alternative.consequences),
        )
        if not alternative.consequences:
            violations.append(
                GraphViolation(
                    code="alternative_graph_without_consequences",
                    message=f"alternative graph {alternative.id} non esplicita conseguenze",
                )
            )
        alternative_node_types = {node.type for node in alternative.hierarchy.nodes}
        for consequence in alternative.consequences:
            _append_alternative_traceability_violations(
                violations,
                owner_kind="alternative graph consequence",
                owner_id=consequence.id,
                direct_evidence=consequence.evidence_ids,
                provenance=consequence.provenance,
                known_evidence=evidence_ids,
            )
            violations.extend(
                _validate_scope(
                    f"alternative graph consequence {consequence.id}",
                    consequence.scope,
                    factors=factors,
                    contrasts=contrasts,
                    endpoints=endpoints,
                    inference_targets=inference_targets,
                )
            )
            if (
                consequence.experimental_unit is not None
                and consequence.experimental_unit not in alternative_node_types
            ):
                violations.append(
                    GraphViolation(
                        code="alternative_consequence_unit_missing_from_graph",
                        message=(
                            f"consequence {consequence.id} usa experimental_unit "
                            f"{consequence.experimental_unit.value} assente dal grafo "
                            f"{alternative.id}"
                        ),
                    )
                )
            if (
                consequence.n_independent is not None or consequence.n_independent_by_group
            ) and consequence.experimental_unit is None:
                violations.append(
                    GraphViolation(
                        code="alternative_n_without_experimental_unit",
                        message=(
                            f"consequence {consequence.id} pubblica n senza experimental_unit"
                        ),
                    )
                )
    return tuple(violations)


def _append_alternative_traceability_violations(
    violations: list[GraphViolation],
    *,
    owner_kind: str,
    owner_id: str,
    direct_evidence: tuple[str, ...],
    provenance: object,
    known_evidence: set[str],
) -> None:
    provenance_evidence = tuple(getattr(provenance, "evidence_ids", ()))
    provenance_origin = getattr(provenance, "origin", None)
    if not direct_evidence:
        violations.append(
            GraphViolation(
                code="alternative_graph_object_without_evidence",
                message=f"{owner_kind} {owner_id} non ha evidence_ids",
            )
        )
    if not set(direct_evidence).issubset(provenance_evidence):
        violations.append(
            GraphViolation(
                code="alternative_evidence_missing_from_provenance",
                message=f"{owner_kind} {owner_id} ha evidence non inclusa nella provenance",
            )
        )
    if provenance_origin is ProvenanceKind.MODEL:
        violations.append(
            GraphViolation(
                code="model_authority_forbidden_for_core_alternative",
                message=f"{owner_kind} {owner_id} conserva autorita model nel contratto core",
            )
        )
    _append_missing_evidence(
        violations,
        owner_kind=owner_kind,
        owner_id=owner_id,
        referenced=(*direct_evidence, *provenance_evidence),
        known=known_evidence,
    )


def _reference_violation(code: str, owner: str, target_kind: str, target_id: str) -> GraphViolation:
    return GraphViolation(
        code=code,
        message=f"{owner} riferisce {target_kind} inesistente: {target_id}",
    )


def _validate_block_evidence(
    block: ExperimentBlock,
    known: set[str],
    violations: list[GraphViolation],
) -> None:
    objects = [
        *(
            ("inference target", item.id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.inference_targets
        ),
        *(
            (
                "factor",
                item.id,
                (
                    *item.evidence_ids,
                    *item.allocation_evidence_ids,
                    *item.application_evidence_ids,
                    *item.independence_evidence_ids,
                ),
                item.provenance.evidence_ids,
            )
            for item in block.factors
        ),
        *(
            ("contrast", item.id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.contrasts
        ),
        *(
            ("endpoint", item.id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.endpoints
        ),
        *(
            (
                "estimand",
                item.id,
                item.evidence_ids,
                item.provenance.evidence_ids if item.provenance is not None else (),
            )
            for item in block.estimands
        ),
        *(
            ("model", item.id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.models
        ),
        *(
            ("process", item.id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.processes
        ),
        *(
            ("n statement", item.id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.n_statements
        ),
        *(
            ("count record", item.count_id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.count_records
        ),
        *(
            ("exclusion record", item.id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.exclusion_records
        ),
        *(
            (
                "unit assessment",
                item.id,
                (
                    *item.evidence_ids,
                    *(
                        evidence_id
                        for scenario in item.conditional_scenarios
                        for evidence_id in scenario.evidence_ids
                    ),
                ),
                item.provenance.evidence_ids,
            )
            for item in block.unit_assessments
        ),
        *(
            ("alert", item.id, item.evidence_ids, item.provenance.evidence_ids)
            for item in block.alerts
        ),
        *(
            (
                "contradiction",
                item.id,
                item.evidence_ids,
                item.provenance.evidence_ids if item.provenance is not None else (),
            )
            for item in block.contradictions
        ),
        *(("correction", item.id, item.evidence_ids, ()) for item in block.corrections),
    ]
    for kind, owner_id, direct, provenance in objects:
        _append_missing_evidence(
            violations,
            owner_kind=kind,
            owner_id=owner_id,
            referenced=(*direct, *provenance),
            known=known,
        )


def _validate_correction_order(block: ExperimentBlock, violations: list[GraphViolation]) -> None:
    previous: int | None = None
    seen: set[int] = set()
    for correction in block.corrections:
        if correction.sequence in seen:
            violations.append(
                GraphViolation(
                    code="duplicate_correction_sequence",
                    message=f"correction sequence duplicata: {correction.sequence}",
                )
            )
        if previous is not None and correction.sequence <= previous:
            violations.append(
                GraphViolation(
                    code="correction_sequence_not_increasing",
                    message=(
                        f"correction {correction.id} ha sequence {correction.sequence} "
                        f"dopo {previous}"
                    ),
                )
            )
        seen.add(correction.sequence)
        previous = correction.sequence
