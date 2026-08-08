"""Exact identifier-invariant PRD v8 graph equality; partial scoring is blocked."""

from __future__ import annotations

import networkx as nx
from networkx.algorithms.isomorphism import (
    MultiDiGraphMatcher,
    categorical_multiedge_match,
    categorical_node_match,
)
from pydantic import Field, model_validator

from ntruth.schemas.graph_v8 import V8ExperimentGraph
from ntruth.schemas.kernel import KernelModel, NonBlankStr
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
            relation_type=relation.relation_type.value,
        )
    return graph


def exact_graph_equal(left: ExactGraphView, right: ExactGraphView) -> bool:
    """Compare directed typed structure and semantic keys while ignoring local IDs."""

    matcher = MultiDiGraphMatcher(
        _networkx_graph(left),
        _networkx_graph(right),
        node_match=categorical_node_match("identity", None),
        edge_match=categorical_multiedge_match("relation_type", None),
    )
    return matcher.is_isomorphic()


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
