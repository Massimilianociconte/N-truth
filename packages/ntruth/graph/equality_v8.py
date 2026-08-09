"""Exact identifier-invariant PRD v8 graph equality; partial scoring is blocked."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

import networkx as nx
from networkx.algorithms.isomorphism import (
    MultiDiGraphMatcher,
    categorical_node_match,
)
from pydantic import Field, model_validator

from ntruth.derivation_theory.loader import canonical_checksum
from ntruth.schemas.graph_v8 import V8ExperimentGraph
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement


class GraphNodeSemanticIdentity(KernelModel):
    node_id: NonBlankStr
    role: NonBlankStr
    semantic_key: NonBlankStr


class ExactGraphView(KernelModel):
    graph: V8ExperimentGraph
    node_semantics: tuple[GraphNodeSemanticIdentity, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _complete_semantic_identity(self) -> ExactGraphView:
        node_ids = {node.node_id for node in self.graph.nodes}
        semantic_ids = [identity.node_id for identity in self.node_semantics]
        if len(set(semantic_ids)) != len(semantic_ids):
            raise ValueError("duplicate graph semantic identity")
        if set(semantic_ids) != node_ids:
            raise ValueError("exact graph equality requires one semantic identity per node")
        return self


def _networkx_graph(view: ExactGraphView) -> nx.MultiDiGraph[str]:
    semantics = {identity.node_id: identity for identity in view.node_semantics}
    node_identities = {
        node.node_id: (
            node.node_type.value,
            semantics[node.node_id].role,
            semantics[node.node_id].semantic_key,
        )
        for node in view.graph.nodes
    }
    graph: nx.MultiDiGraph[str] = nx.MultiDiGraph()
    for node in view.graph.nodes:
        identity = semantics[node.node_id]
        graph.add_node(
            node.node_id,
            identity=(node.node_type.value, identity.role, identity.semantic_key),
        )
    for relation in view.graph.relations:
        graph.add_edge(
            relation.source_node_id,
            relation.target_node_id,
            key=relation.relation_id,
            identity=(
                relation.relation_type.value,
                _scientific_edge_value(relation.query_scope, node_identities),
                _scientific_edge_value(relation.factor_scope, node_identities),
                _scientific_edge_value(relation.decisive_attributes, node_identities),
            ),
        )
    return graph


def _scientific_edge_value(
    value: KnowledgeValue[Any],
    node_identities: Mapping[str, tuple[str, str, str]],
) -> str:
    """Bind epistemic value and scope while excluding evidence/provenance metadata."""

    payload = value.model_dump(
        mode="json",
        include={
            "knowledge_state",
            "value",
            "conflicting_values",
            "claim_scope_id",
            "query_scope_id",
        },
    )
    for field_name in ("value", "claim_scope_id", "query_scope_id"):
        reference = payload.get(field_name)
        if isinstance(reference, str) and reference in node_identities:
            payload[field_name] = node_identities[reference]
    conflicts = payload.get("conflicting_values")
    if isinstance(conflicts, list):
        payload["conflicting_values"] = [
            node_identities.get(item, item) if isinstance(item, str) else item for item in conflicts
        ]
    return canonical_checksum(payload)


def exact_graph_equal(left: ExactGraphView, right: ExactGraphView) -> bool:
    """Compare directed typed structure and semantic keys while ignoring local IDs."""

    matcher = MultiDiGraphMatcher(
        _networkx_graph(left),
        _networkx_graph(right),
        node_match=categorical_node_match("identity", None),
        edge_match=_parallel_relation_contracts_match,
    )
    return matcher.is_isomorphic()


def _parallel_relation_contracts_match(
    left: Mapping[object, Mapping[str, object]],
    right: Mapping[object, Mapping[str, object]],
) -> bool:
    """Compare the full directed multiset, not only the set of edge labels."""

    return Counter(item.get("identity") for item in left.values()) == Counter(
        item.get("identity") for item in right.values()
    )


def partial_graph_score() -> ScientificReviewRequirement:
    """Return the normative blocker instead of inventing weights or tolerances."""

    return ScientificReviewRequirement(
        issue_id="SRR-V8-012",
        rationale=(
            "Partial graph-scoring weights, tolerances and semantic matching policy require "
            "scientific review."
        ),
    )


__all__ = [
    "ExactGraphView",
    "GraphNodeSemanticIdentity",
    "exact_graph_equal",
    "partial_graph_score",
]
