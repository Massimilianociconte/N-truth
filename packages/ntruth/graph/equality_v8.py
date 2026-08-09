"""Exact identifier-invariant PRD v8 graph equality; partial scoring is blocked."""

from __future__ import annotations

import re
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

_GRAPH_IDENTIFIER_TOKENS = frozenset(
    {
        "aggregate",
        "application",
        "assignment",
        "block",
        "challenge",
        "claim",
        "condition",
        "confirmation",
        "contrast",
        "count",
        "endpoint",
        "event",
        "evidence",
        "exclusion",
        "exposure",
        "factor",
        "level",
        "measurement",
        "node",
        "observation",
        "pool",
        "preparation",
        "query",
        "sensitivity",
        "source",
        "split",
        "unit",
    }
)


class _UnaddressableGraphValue(ValueError):
    """Scientific edge content cannot be compared identifier-invariantly."""


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
                _scientific_edge_value(
                    relation.query_scope,
                    node_identities,
                    value_is_node_reference=True,
                ),
                _scientific_edge_value(
                    relation.factor_scope,
                    node_identities,
                    value_is_node_reference=True,
                ),
                _scientific_edge_value(relation.decisive_attributes, node_identities),
            ),
        )
    return graph


def _looks_like_graph_identifier(value: str) -> bool:
    if any(character.isspace() for character in value):
        return False
    parts = tuple(filter(None, re.split(r"[-_:/.]+", value.casefold())))
    return len(parts) > 1 and bool(_GRAPH_IDENTIFIER_TOKENS.intersection(parts))


def _field_requires_node_reference(field_name: str) -> bool:
    normalized = field_name.casefold()
    return normalized == "id" or normalized.endswith("_id") or normalized.endswith("_ids")


def _readdress_scientific_mapping_key(
    key: str,
    node_identities: Mapping[str, tuple[str, str, str]],
) -> object:
    identity = node_identities.get(key)
    if identity is not None:
        return {"type": "node_identity", "value": identity}
    if not _field_requires_node_reference(key) and _looks_like_graph_identifier(key):
        raise _UnaddressableGraphValue("unresolved graph identifier mapping key")
    return {"type": "str", "value": key}


def _readdress_scientific_payload(
    raw: object,
    node_identities: Mapping[str, tuple[str, str, str]],
    *,
    require_node_reference: bool = False,
    detect_ambiguous_identifier: bool = True,
) -> object:
    if raw is None:
        return {"type": "none"}
    if type(raw) is bool:
        return {"type": "bool", "value": raw}
    if type(raw) is int:
        return {"type": "int", "value": raw}
    if type(raw) is float:
        return {"type": "float", "value": raw}
    if type(raw) is str:
        identity = node_identities.get(raw)
        if identity is not None:
            return {"type": "node_identity", "value": identity}
        if require_node_reference or (
            detect_ambiguous_identifier and _looks_like_graph_identifier(raw)
        ):
            raise _UnaddressableGraphValue("unresolved graph identifier")
        return {"type": "str", "value": raw}
    if isinstance(raw, Mapping):
        if type(raw) is not dict:
            raise _UnaddressableGraphValue("non-builtin scientific mapping")
        keys = tuple(dict.keys(raw))
        if any(type(key) is not str for key in keys):
            raise _UnaddressableGraphValue("non-string scientific mapping key")
        items = [
            [
                _readdress_scientific_mapping_key(key, node_identities),
                _readdress_scientific_payload(
                    dict.__getitem__(raw, key),
                    node_identities,
                    require_node_reference=_field_requires_node_reference(key),
                    detect_ambiguous_identifier=detect_ambiguous_identifier,
                ),
            ]
            for key in keys
        ]
        items.sort(key=canonical_checksum)
        return {
            "type": "dict",
            "items": items,
        }
    if isinstance(raw, list):
        if type(raw) is not list:
            raise _UnaddressableGraphValue("non-builtin scientific list")
        return {
            "type": "list",
            "items": [
                _readdress_scientific_payload(
                    item,
                    node_identities,
                    require_node_reference=require_node_reference,
                    detect_ambiguous_identifier=detect_ambiguous_identifier,
                )
                for item in raw
            ],
        }
    if isinstance(raw, tuple):
        if type(raw) is not tuple:
            raise _UnaddressableGraphValue("non-builtin scientific tuple")
        return {
            "type": "tuple",
            "items": [
                _readdress_scientific_payload(
                    item,
                    node_identities,
                    require_node_reference=require_node_reference,
                    detect_ambiguous_identifier=detect_ambiguous_identifier,
                )
                for item in raw
            ],
        }
    raise _UnaddressableGraphValue("unsupported scientific runtime type")


def _scientific_edge_value(
    value: KnowledgeValue[Any],
    node_identities: Mapping[str, tuple[str, str, str]],
    *,
    value_is_node_reference: bool = False,
) -> str:
    """Bind epistemic value and scope while excluding evidence/provenance metadata."""

    payload = {
        "knowledge_state": value.knowledge_state.value,
        "value": _readdress_scientific_payload(
            value.value,
            node_identities,
            require_node_reference=value_is_node_reference and value.value is not None,
        ),
        "conflicting_values": _readdress_scientific_payload(
            value.conflicting_values,
            node_identities,
            require_node_reference=value_is_node_reference,
        ),
        "claim_scope_id": _readdress_scientific_payload(
            value.claim_scope_id,
            node_identities,
            detect_ambiguous_identifier=False,
        ),
        "query_scope_id": _readdress_scientific_payload(
            value.query_scope_id,
            node_identities,
            require_node_reference=value.query_scope_id is not None,
        ),
    }
    return canonical_checksum(payload)


def exact_graph_equal(left: ExactGraphView, right: ExactGraphView) -> bool:
    """Compare directed typed structure and semantic keys while ignoring local IDs."""

    try:
        matcher = MultiDiGraphMatcher(
            _networkx_graph(left),
            _networkx_graph(right),
            node_match=categorical_node_match("identity", None),
            edge_match=_parallel_relation_contracts_match,
        )
    except _UnaddressableGraphValue:
        return False
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
