"""Validazione strutturale del grafo e degli ``ExperimentBlock``.

Il validator controlla soltanto invarianti di struttura e provenance. Non decide
quale unita sperimentale sia scientificamente corretta e non aggiunge relazioni:
quelle decisioni restano nel ruleset approvato e nel processo di adjudication.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

import networkx as nx

from ntruth.schemas.core import ProvenanceKind
from ntruth.schemas.experiment import (
    Contrast,
    Endpoint,
    ExperimentBlock,
    Factor,
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
        *(("contradiction", item.id, item.evidence_ids, ()) for item in block.contradictions),
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
