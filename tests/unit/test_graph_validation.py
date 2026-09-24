"""Invarianti strutturali prima di applicare regole o correzioni al grafo."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ntruth.graph.validation import (
    GraphValidationError,
    assert_valid_experiment_block,
    assert_valid_hierarchy,
    validate_experiment_block,
    validate_hierarchy,
)
from ntruth.schemas.core import EvidenceSpan, Provenance, ProvenanceKind
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
    return Provenance(
        origin=ProvenanceKind.DERIVED,
        derivation="synthetic structural-validation fixture",
    )


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


def test_graph_provenance_matrix_fails_closed_for_untraceable_origins() -> None:
    explicit = GraphNode(
        id="explicit-without-source",
        type=NodeType.ANIMAL,
        label="animal",
        provenance=Provenance(origin=ProvenanceKind.EXPLICIT),
    )
    derived = GraphNode(
        id="derived-without-derivation",
        type=NodeType.CELL,
        label="cell",
        provenance=Provenance(origin=ProvenanceKind.DERIVED),
    )
    incomplete_correction = GraphNode(
        id="human-without-timestamp",
        type=NodeType.WELL,
        label="well",
        provenance=Provenance(
            origin=ProvenanceKind.USER,
            actor_role="wet_lab_reviewer",
            correction_id="correction-1",
        ),
    )
    block = ExperimentBlock(
        id="block-provenance-invalid",
        document_id="document-provenance-invalid",
        hierarchy=Hierarchy(nodes=(explicit, derived, incomplete_correction)),
        versions=_versions(),
    )

    codes = {item.code for item in validate_experiment_block(block)}

    assert {
        "source_graph_element_without_evidence",
        "derived_graph_element_without_derivation",
        "human_graph_element_without_audit",
    } <= codes


def test_initial_human_graph_confirmation_with_local_evidence_is_traceable() -> None:
    evidence = EvidenceSpan(id="ev-human", file_id="file-1", text="Reviewer source")
    node = GraphNode(
        id="human-confirmed",
        type=NodeType.ANIMAL,
        label="animal",
        evidence_ids=(evidence.id,),
        provenance=Provenance(
            origin=ProvenanceKind.USER,
            evidence_ids=(evidence.id,),
            actor_role="wet_lab_reviewer",
        ),
    )
    corrected = node.model_copy(
        update={
            "id": "human-corrected",
            "provenance": node.provenance.model_copy(
                update={
                    "correction_id": "correction-2",
                    "correction_role": "wet_lab_reviewer",
                    "timestamp": datetime(2026, 8, 1, tzinfo=UTC),
                }
            ),
        }
    )
    block = ExperimentBlock(
        id="block-provenance-valid",
        document_id="document-provenance-valid",
        evidence=(evidence,),
        hierarchy=Hierarchy(nodes=(node, corrected)),
        versions=_versions(),
    )

    provenance_codes = {
        item.code
        for item in validate_experiment_block(block)
        if "provenance" in item.code or "audit" in item.code or "trace" in item.code
    }
    assert provenance_codes == set()
