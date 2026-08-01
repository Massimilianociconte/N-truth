"""Proprieta strutturali del grafo deterministico (PRD v3, sezione 25.2).

Questi test generano topologie sintetiche per verificare il software. Non sono
annotazioni scientifiche, non stimano metriche del modello e non sostituiscono
un gold corpus adjudicato da esperti.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ntruth.graph.validation import (
    GraphValidationError,
    assert_valid_hierarchy,
    blocking_violations,
    validate_hierarchy,
)
from ntruth.schemas.core import Provenance, ProvenanceKind
from ntruth.schemas.experiment import Hierarchy
from ntruth.schemas.graph import (
    CONTAINMENT_RANK,
    GraphNode,
    GraphRelation,
    NodeType,
    RelationType,
    rank_of,
)

PROVENANCE = Provenance(origin=ProvenanceKind.EXPLICIT)
RANKED_NODE_TYPES = tuple(CONTAINMENT_RANK)
ALL_NODE_TYPES = tuple(NodeType)
ALL_RELATION_TYPES = tuple(RelationType)


def _node(node_id: str, node_type: NodeType) -> GraphNode:
    return GraphNode(
        id=node_id,
        type=node_type,
        label=f"{node_type.value} {node_id}",
        provenance=PROVENANCE,
    )


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
        provenance=PROVENANCE,
    )


@st.composite
def valid_ranked_hierarchies(draw: st.DrawFn) -> Hierarchy:
    """DAG con archi ``nested_in`` sempre dal livello fine a quello sorgente."""

    selected_types = draw(
        st.lists(
            st.sampled_from(RANKED_NODE_TYPES),
            min_size=1,
            max_size=12,
            unique=True,
        )
    )
    selected_types.sort(key=lambda node_type: (rank_of(node_type) or -1, node_type.value))
    nodes = tuple(
        _node(f"node-{index}", node_type) for index, node_type in enumerate(selected_types)
    )

    possible_edges = [
        (child_index, parent_index)
        for child_index, child_type in enumerate(selected_types)
        for parent_index, parent_type in enumerate(selected_types)
        if (rank_of(child_type) or -1) > (rank_of(parent_type) or -1)
    ]
    if possible_edges:
        edge_indices = draw(
            st.sets(
                st.integers(min_value=0, max_value=len(possible_edges) - 1),
                max_size=min(24, len(possible_edges)),
            )
        )
    else:
        edge_indices = set()

    relations = tuple(
        _relation(
            f"relation-{relation_index}",
            RelationType.NESTED_IN,
            f"node-{possible_edges[edge_index][0]}",
            f"node-{possible_edges[edge_index][1]}",
        )
        for relation_index, edge_index in enumerate(sorted(edge_indices))
    )
    return Hierarchy(nodes=nodes, relations=relations)


@st.composite
def arbitrary_typed_hierarchies(draw: st.DrawFn) -> Hierarchy:
    """Grafi tipizzati costruibili dallo schema, inclusi input strutturalmente ostili."""

    node_count = draw(st.integers(min_value=0, max_value=12))
    node_types = draw(
        st.lists(st.sampled_from(ALL_NODE_TYPES), min_size=node_count, max_size=node_count)
    )
    nodes = tuple(_node(f"node-{index}", node_type) for index, node_type in enumerate(node_types))

    endpoints = (*(node.id for node in nodes), "missing-a", "missing-b")
    relation_count = draw(st.integers(min_value=0, max_value=24))
    relation_specs = draw(
        st.lists(
            st.tuples(
                st.sampled_from(ALL_RELATION_TYPES),
                st.sampled_from(endpoints),
                st.sampled_from(endpoints),
            ),
            min_size=relation_count,
            max_size=relation_count,
        )
    )
    relations = tuple(
        _relation(f"relation-{index}", relation_type, source, target)
        for index, (relation_type, source, target) in enumerate(relation_specs)
    )
    return Hierarchy(nodes=nodes, relations=relations)


@settings(max_examples=120, deadline=None)
@given(valid_ranked_hierarchies())
def test_valid_ranked_dags_are_accepted(hierarchy: Hierarchy) -> None:
    """Un grafo valido e aciclico non deve produrre falsi blocchi."""

    assert validate_hierarchy(hierarchy) == ()
    assert_valid_hierarchy(hierarchy)


@settings(max_examples=120, deadline=None)
@given(
    node_types=st.lists(
        st.sampled_from(ALL_NODE_TYPES),
        min_size=0,
        max_size=12,
    ),
    relation_type=st.sampled_from(ALL_RELATION_TYPES),
    missing_source=st.booleans(),
)
def test_every_dangling_endpoint_is_blocking(
    node_types: list[NodeType],
    relation_type: RelationType,
    missing_source: bool,
) -> None:
    """Qualunque tipo di arco deve essere bloccato se un endpoint non esiste."""

    nodes = tuple(_node(f"node-{index}", node_type) for index, node_type in enumerate(node_types))
    known_endpoint = nodes[0].id if nodes else "also-missing"
    source = "missing-endpoint" if missing_source else known_endpoint
    target = known_endpoint if missing_source else "missing-endpoint"
    hierarchy = Hierarchy(
        nodes=nodes,
        relations=(_relation("dangling", relation_type, source, target),),
    )

    violations = validate_hierarchy(hierarchy)
    dangling = tuple(item for item in violations if item.code == "dangling_relation_endpoint")
    assert dangling
    assert all(item.blocking for item in dangling)
    with pytest.raises(GraphValidationError) as caught:
        assert_valid_hierarchy(hierarchy)
    assert "dangling_relation_endpoint" in {item.code for item in caught.value.violations}


@settings(max_examples=60, deadline=None)
@given(cycle_size=st.integers(min_value=2, max_value=12))
def test_every_containment_cycle_is_blocking(cycle_size: int) -> None:
    """Cicli di qualunque lunghezza sono sempre invalidi per l'inferenza."""

    nodes = tuple(_node(f"node-{index}", NodeType.ANIMAL) for index in range(cycle_size))
    relations = tuple(
        _relation(
            f"cycle-{index}",
            RelationType.DERIVED_FROM,
            f"node-{index}",
            f"node-{(index + 1) % cycle_size}",
        )
        for index in range(cycle_size)
    )
    hierarchy = Hierarchy(nodes=nodes, relations=relations)

    violations = validate_hierarchy(hierarchy)
    cycles = tuple(item for item in violations if item.code == "containment_cycle")
    assert len(cycles) == 1
    assert cycles[0].blocking is True
    with pytest.raises(GraphValidationError):
        assert_valid_hierarchy(hierarchy)


@settings(max_examples=180, deadline=None)
@given(arbitrary_typed_hierarchies())
def test_validation_is_total_and_deterministic(hierarchy: Hierarchy) -> None:
    """Ogni grafo ammesso dallo schema termina e produce lo stesso esito a ogni run."""

    first = validate_hierarchy(hierarchy)
    second = validate_hierarchy(hierarchy)
    assert first == second

    blocking = blocking_violations(first)
    if blocking:
        with pytest.raises(GraphValidationError) as caught:
            assert_valid_hierarchy(hierarchy)
        assert caught.value.violations == blocking
    else:
        assert_valid_hierarchy(hierarchy)
