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
from pydantic import BaseModel, Field, model_validator

from ntruth.derivation_theory.loader import canonical_checksum
from ntruth.runtime_tree import _preflight_exact_tree, canonicalize_exact_model
from ntruth.schemas.graph_v8 import V8ExperimentGraph, V8GraphNode, V8GraphRelation
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

_NODE_REFERENCE_FIELD_NAMES = frozenset(
    {
        "anchor",
        "anchors",
        "id",
        "ids",
        "member",
        "members",
        "node",
        "nodes",
        "reference",
        "references",
    }
)
_NODE_REFERENCE_FIELD_SUFFIXES = tuple(f"_{name}" for name in _NODE_REFERENCE_FIELD_NAMES)
_NODE_REFERENCE_MAPPING_FIELD_NAMES = frozenset({"member", "members"})
_NODE_REFERENCE_MAPPING_FIELD_SUFFIXES = tuple(
    f"_{name}" for name in _NODE_REFERENCE_MAPPING_FIELD_NAMES
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


def _require_same_exact_value(raw: object, checked: object) -> None:
    if type(raw) is not type(checked) or raw != checked:
        raise _UnaddressableGraphValue("non-canonical graph runtime value")


def _validated_graph_view(value: ExactGraphView, *, path: str) -> ExactGraphView:
    if type(value) is not ExactGraphView:
        raise _UnaddressableGraphValue("non-canonical exact graph view")
    _preflight_exact_tree(value, path=path)
    payload = BaseModel.model_dump(
        value,
        mode="json",
        exclude_unset=True,
        round_trip=True,
        warnings="none",
    )
    checked = ExactGraphView.model_validate(payload)
    if type(value.node_semantics) is not tuple:
        raise _UnaddressableGraphValue("non-canonical semantic identity container")
    for index, (raw_identity, checked_identity) in enumerate(
        zip(value.node_semantics, checked.node_semantics, strict=True)
    ):
        canonical_identity = canonicalize_exact_model(
            raw_identity,
            GraphNodeSemanticIdentity,
            path=f"{path}.node_semantics[{index}]",
        )
        if canonical_identity != checked_identity:
            raise _UnaddressableGraphValue("semantic identity reconstruction mismatch")

    if type(value.graph) is not V8ExperimentGraph:
        raise _UnaddressableGraphValue("non-canonical graph model")
    if type(value.graph.nodes) is not tuple or type(value.graph.relations) is not tuple:
        raise _UnaddressableGraphValue("non-canonical graph container")
    for index, (raw_node, checked_node) in enumerate(
        zip(value.graph.nodes, checked.graph.nodes, strict=True)
    ):
        canonical_node = canonicalize_exact_model(
            raw_node,
            V8GraphNode,
            path=f"{path}.graph.nodes[{index}]",
        )
        if canonical_node != checked_node:
            raise _UnaddressableGraphValue("graph node reconstruction mismatch")
    structural_fields = (
        "relation_id",
        "relation_type",
        "source_node_id",
        "target_node_id",
    )
    scope_fields = ("query_scope", "factor_scope")
    knowledge_metadata_fields = (
        "schema_version",
        "knowledge_state",
        "evidence_ids",
        "source_scope_ids",
        "rationale",
        "claim_scope_id",
        "query_scope_id",
    )
    for index, (raw_relation, checked_relation) in enumerate(
        zip(value.graph.relations, checked.graph.relations, strict=True)
    ):
        if type(raw_relation) is not V8GraphRelation:
            raise _UnaddressableGraphValue("non-canonical graph relation")
        for field_name in structural_fields:
            _require_same_exact_value(
                getattr(raw_relation, field_name),
                getattr(checked_relation, field_name),
            )
        for field_name in scope_fields:
            raw_scope = getattr(raw_relation, field_name)
            checked_scope = getattr(checked_relation, field_name)
            canonical_scope = canonicalize_exact_model(
                raw_scope,
                type(checked_scope),
                path=f"{path}.graph.relations[{index}].{field_name}",
            )
            if canonical_scope != checked_scope:
                raise _UnaddressableGraphValue("graph scope reconstruction mismatch")
        raw_attributes = raw_relation.decisive_attributes
        checked_attributes = checked_relation.decisive_attributes
        if type(raw_attributes) is not type(checked_attributes):
            raise _UnaddressableGraphValue("non-canonical decisive attributes")
        for field_name in knowledge_metadata_fields:
            _require_same_exact_value(
                getattr(raw_attributes, field_name),
                getattr(checked_attributes, field_name),
            )
    return value


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
    if len(set(node_identities.values())) != len(node_identities):
        raise _UnaddressableGraphValue("ambiguous graph semantic identity")
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


def _field_requires_node_reference(field_name: str) -> bool:
    normalized = field_name.casefold()
    return normalized in _NODE_REFERENCE_FIELD_NAMES or normalized.endswith(
        _NODE_REFERENCE_FIELD_SUFFIXES
    )


def _field_maps_node_references(field_name: str) -> bool:
    normalized = field_name.casefold()
    return normalized in _NODE_REFERENCE_MAPPING_FIELD_NAMES or normalized.endswith(
        _NODE_REFERENCE_MAPPING_FIELD_SUFFIXES
    )


def _readdress_scientific_mapping_key(
    key: str,
    node_identities: Mapping[str, tuple[str, str, str]],
    *,
    require_node_reference: bool,
) -> object:
    if require_node_reference:
        identity = node_identities.get(key)
        if identity is None:
            raise _UnaddressableGraphValue("unresolved graph node-reference mapping key")
        return {"type": "node_identity", "value": identity}
    return {"type": "str", "value": key}


def _readdress_scientific_payload(
    raw: object,
    node_identities: Mapping[str, tuple[str, str, str]],
    *,
    require_node_reference: bool = False,
    mapping_keys_are_node_references: bool = False,
    active: set[int] | None = None,
) -> object:
    if active is None:
        active = set()
    if raw is None:
        if require_node_reference:
            raise _UnaddressableGraphValue("null graph node reference")
        return {"type": "none"}
    if type(raw) is bool:
        if require_node_reference:
            raise _UnaddressableGraphValue("non-string graph node reference")
        return {"type": "bool", "value": raw}
    if type(raw) is int:
        if require_node_reference:
            raise _UnaddressableGraphValue("non-string graph node reference")
        return {"type": "int", "value": raw}
    if type(raw) is float:
        if require_node_reference:
            raise _UnaddressableGraphValue("non-string graph node reference")
        return {"type": "float", "value": raw}
    if type(raw) is str:
        if require_node_reference:
            node_identity = node_identities.get(raw)
            if node_identity is None:
                raise _UnaddressableGraphValue("unresolved graph node reference")
            return {"type": "node_identity", "value": node_identity}
        return {"type": "str", "value": raw}
    if isinstance(raw, Mapping):
        if type(raw) is not dict:
            raise _UnaddressableGraphValue("non-builtin scientific mapping")
        container_identity = id(raw)
        if container_identity in active:
            raise _UnaddressableGraphValue("recursive scientific mapping")
        active.add(container_identity)
        try:
            keys = tuple(dict.keys(raw))
            if any(type(key) is not str for key in keys):
                raise _UnaddressableGraphValue("non-string scientific mapping key")
            items = [
                [
                    _readdress_scientific_mapping_key(
                        key,
                        node_identities,
                        require_node_reference=mapping_keys_are_node_references,
                    ),
                    _readdress_scientific_payload(
                        dict.__getitem__(raw, key),
                        node_identities,
                        require_node_reference=_field_requires_node_reference(key),
                        mapping_keys_are_node_references=_field_maps_node_references(key),
                        active=active,
                    ),
                ]
                for key in keys
            ]
            items.sort(key=canonical_checksum)
            return {
                "type": "dict",
                "items": items,
            }
        finally:
            active.remove(container_identity)
    if isinstance(raw, list):
        if type(raw) is not list:
            raise _UnaddressableGraphValue("non-builtin scientific list")
        container_identity = id(raw)
        if container_identity in active:
            raise _UnaddressableGraphValue("recursive scientific list")
        active.add(container_identity)
        try:
            return {
                "type": "list",
                "items": [
                    _readdress_scientific_payload(
                        item,
                        node_identities,
                        require_node_reference=require_node_reference,
                        mapping_keys_are_node_references=mapping_keys_are_node_references,
                        active=active,
                    )
                    for item in raw
                ],
            }
        finally:
            active.remove(container_identity)
    if isinstance(raw, tuple):
        if type(raw) is not tuple:
            raise _UnaddressableGraphValue("non-builtin scientific tuple")
        container_identity = id(raw)
        if container_identity in active:
            raise _UnaddressableGraphValue("recursive scientific tuple")
        active.add(container_identity)
        try:
            return {
                "type": "tuple",
                "items": [
                    _readdress_scientific_payload(
                        item,
                        node_identities,
                        require_node_reference=require_node_reference,
                        mapping_keys_are_node_references=mapping_keys_are_node_references,
                        active=active,
                    )
                    for item in raw
                ],
            }
        finally:
            active.remove(container_identity)
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
        canonical_left = _validated_graph_view(left, path="$.left_graph_view")
        canonical_right = _validated_graph_view(right, path="$.right_graph_view")
        matcher = MultiDiGraphMatcher(
            _networkx_graph(canonical_left),
            _networkx_graph(canonical_right),
            node_match=categorical_node_match("identity", None),
            edge_match=_parallel_relation_contracts_match,
        )
        return matcher.is_isomorphic()
    except Exception:
        return False


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
