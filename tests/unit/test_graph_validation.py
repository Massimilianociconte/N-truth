"""Invarianti strutturali prima di applicare regole o correzioni al grafo."""

from __future__ import annotations

import pytest

from ntruth.graph.validation import (
    GraphValidationError,
    assert_valid_experiment_block,
    assert_valid_hierarchy,
    validate_experiment_block,
    validate_hierarchy,
)
from ntruth.schemas.core import Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    Contrast,
    ExperimentBlock,
    Factor,
    Hierarchy,
    NScope,
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import GraphNode, GraphRelation, NodeType, RelationType


def _provenance() -> Provenance:
    return Provenance(origin=ProvenanceKind.EXPLICIT)


def _node(node_id: str, node_type: NodeType) -> GraphNode:
    return GraphNode(id=node_id, type=node_type, label=node_id, provenance=_provenance())


def _relation(
    relation_id: str,
    relation_type: RelationType,
    source: str,
    target: str,
) -> GraphRelation:
    return GraphRelation(
        id=relation_id,
        type=relation_type,
        source=source,
        target=target,
        provenance=_provenance(),
    )


def _versions() -> Versions:
    return Versions(
        schema_version="0.1.0",
        parser_version="0.1.0",
        graph_version="0.1.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.1.0",
    )


def test_valid_hierarchy_has_no_violations() -> None:
    hierarchy = Hierarchy(
        nodes=(
            _node("animal-1", NodeType.ANIMAL),
            _node("cell-1", NodeType.CELL),
        ),
        relations=(
            _relation(
                "nested-1",
                RelationType.NESTED_IN,
                "cell-1",
                "animal-1",
            ),
        ),
    )
    assert validate_hierarchy(hierarchy) == ()
    assert_valid_hierarchy(hierarchy)


def test_duplicate_nodes_and_dangling_edges_are_blocking() -> None:
    hierarchy = Hierarchy(
        nodes=(
            _node("duplicate", NodeType.ANIMAL),
            _node("duplicate", NodeType.CELL),
        ),
        relations=(
            _relation(
                "dangling",
                RelationType.NESTED_IN,
                "missing-child",
                "missing-parent",
            ),
        ),
    )
    violations = validate_hierarchy(hierarchy)
    assert {item.code for item in violations} >= {
        "duplicate_node_id",
        "dangling_relation_endpoint",
    }
    assert all(item.blocking for item in violations)
    with pytest.raises(GraphValidationError):
        assert_valid_hierarchy(hierarchy)


def test_containment_cycles_are_rejected() -> None:
    hierarchy = Hierarchy(
        nodes=(
            _node("source-a", NodeType.ANIMAL),
            _node("source-b", NodeType.CELL_CULTURE),
        ),
        relations=(
            _relation("r-a", RelationType.DERIVED_FROM, "source-a", "source-b"),
            _relation("r-b", RelationType.DERIVED_FROM, "source-b", "source-a"),
        ),
    )
    assert "containment_cycle" in {item.code for item in validate_hierarchy(hierarchy)}


def test_inverted_nesting_is_rejected_without_adding_scientific_edges() -> None:
    hierarchy = Hierarchy(
        nodes=(
            _node("animal-1", NodeType.ANIMAL),
            _node("cell-1", NodeType.CELL),
        ),
        relations=(
            _relation(
                "inverted",
                RelationType.NESTED_IN,
                "animal-1",
                "cell-1",
            ),
        ),
    )
    assert "hierarchy_inversion" in {item.code for item in validate_hierarchy(hierarchy)}


def test_experiment_block_cross_references_are_validated() -> None:
    factor = Factor(
        id="factor-1",
        name="treatment",
        provenance=_provenance(),
    )
    contrast = Contrast(
        id="contrast-1",
        label="a_vs_b",
        factor_id="missing-factor",
        endpoint_ids=("missing-endpoint",),
        provenance=_provenance(),
    )
    assessment = UnitAssessment(
        id="assessment-1",
        scope=NScope(factor_id="factor-1", contrast_id="missing-contrast"),
        provenance=Provenance(origin=ProvenanceKind.DERIVED),
    )
    block = ExperimentBlock(
        id="block-1",
        document_id="document-1",
        factors=(factor,),
        contrasts=(contrast,),
        unit_assessments=(assessment,),
        versions=_versions(),
    )
    codes = {item.code for item in validate_experiment_block(block)}
    assert {
        "dangling_contrast_factor",
        "dangling_contrast_endpoint",
        "dangling_scope_contrast",
    } <= codes
    with pytest.raises(GraphValidationError):
        assert_valid_experiment_block(block)


def test_missing_evidence_references_are_rejected() -> None:
    node = GraphNode(
        id="animal-1",
        type=NodeType.ANIMAL,
        label="animal",
        evidence_ids=("ev-missing",),
        provenance=Provenance(
            origin=ProvenanceKind.EXPLICIT,
            evidence_ids=("ev-missing",),
        ),
    )
    block = ExperimentBlock(
        id="block-1",
        document_id="document-1",
        hierarchy=Hierarchy(nodes=(node,)),
        versions=_versions(),
    )
    assert "dangling_evidence" in {item.code for item in validate_experiment_block(block)}
