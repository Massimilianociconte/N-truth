"""Indice interrogabile del grafo: chiusura di annidamento, conteggi e livelli.

E l'unica superficie che il rules engine puo interrogare (PRD 11.3): le regole
non vedono ne il testo ne i candidate facts del modello.
"""

from __future__ import annotations

from functools import cached_property

import networkx as nx

from ntruth.schemas.experiment import Hierarchy
from ntruth.schemas.graph import (
    CLUSTER_TYPES,
    TECHNICAL_TYPES,
    GraphNode,
    GraphRelation,
    NodeType,
    RelationType,
    rank_of,
)

#: Relazioni orientate dalla parte piu fine/derivata alla sorgente o contenitore.
_FORWARD_CONTAINMENT_RELATIONS: frozenset[RelationType] = frozenset(
    {
        RelationType.NESTED_IN,
        RelationType.DERIVED_FROM,
        RelationType.SPLIT_FROM,
        RelationType.MEMBER_OF_POOL,
        RelationType.POOLED_INTO,
    }
)

#: Alias legacy o relazioni canoniche con verso dichiarativo opposto.
_REVERSED_CONTAINMENT_RELATIONS: frozenset[RelationType] = frozenset(
    {
        RelationType.CONTAINS,
        RelationType.SPLIT_INTO,
        RelationType.POOLED_FROM,
    }
)

CONTAINMENT_RELATIONS: frozenset[RelationType] = frozenset(
    {*_FORWARD_CONTAINMENT_RELATIONS, *_REVERSED_CONTAINMENT_RELATIONS}
)


def _containment_endpoints(relation: GraphRelation) -> tuple[str, str] | None:
    """Normalizza soltanto la vista di reachability, senza riscrivere l'arco."""

    if relation.type in _FORWARD_CONTAINMENT_RELATIONS:
        return relation.source, relation.target
    if relation.type in _REVERSED_CONTAINMENT_RELATIONS:
        return relation.target, relation.source
    return None


class GraphIndex:
    """Vista di sola lettura sul grafo di un ExperimentBlock."""

    def __init__(self, hierarchy: Hierarchy) -> None:
        self.hierarchy = hierarchy
        self._by_id: dict[str, GraphNode] = {node.id: node for node in hierarchy.nodes}
        self._nodes_by_type: dict[NodeType, list[GraphNode]] = {}
        for node in hierarchy.nodes:
            self._nodes_by_type.setdefault(node.type, []).append(node)
        self._by_type: dict[NodeType, GraphNode] = {}
        for node_type, nodes in self._nodes_by_type.items():
            aggregate = next(
                (node for node in nodes if bool(node.attributes.get("aggregate"))),
                None,
            )
            non_instance = next(
                (node for node in nodes if not bool(node.attributes.get("instance"))),
                None,
            )
            self._by_type[node_type] = aggregate or non_instance or nodes[0]
        self._graph: nx.DiGraph[NodeType] = nx.DiGraph()
        self._instance_graph: nx.DiGraph[str] = nx.DiGraph()
        for node in hierarchy.nodes:
            self._graph.add_node(node.type)
            if bool(node.attributes.get("instance")):
                self._instance_graph.add_node(node.id)
        for relation in hierarchy.relations:
            source = self.node_type_of(relation.source)
            target = self.node_type_of(relation.target)
            if source is None or target is None:
                continue
            containment = _containment_endpoints(relation)
            if containment is not None:
                child_id, parent_id = containment
                child_type = self.node_type_of(child_id)
                parent_type = self.node_type_of(parent_id)
                if child_type is None or parent_type is None:
                    continue
                self._graph.add_edge(child_type, parent_type, relation=relation.type)
                if child_id in self._instance_graph and parent_id in self._instance_graph:
                    self._instance_graph.add_edge(child_id, parent_id, relation=relation.type)

    # ------------------------------------------------------------------ lookup

    def node_type_of(self, node_id: str) -> NodeType | None:
        node = self._by_id.get(node_id)
        return node.type if node else None

    def node(self, node_type: NodeType) -> GraphNode | None:
        """Nodo aggregato compatibile con il rules engine esistente."""

        return self._by_type.get(node_type)

    def nodes(self, node_type: NodeType) -> tuple[GraphNode, ...]:
        """Tutti i nodi del tipo, inclusi quelli instance-level."""

        return tuple(self._nodes_by_type.get(node_type, ()))

    def instances(self, node_type: NodeType) -> tuple[GraphNode, ...]:
        return tuple(
            node
            for node in self._nodes_by_type.get(node_type, ())
            if bool(node.attributes.get("instance"))
        )

    def has(self, node_type: NodeType) -> bool:
        return node_type in self._by_type

    def count(self, node_type: NodeType) -> int | None:
        node = self._by_type.get(node_type)
        if node is not None and (
            node.attributes.get("conflict_id") or node.attributes.get("conflicting_counts")
        ):
            return None
        if node is not None and node.count is not None:
            return node.count
        instances = self.instances(node_type)
        return len(instances) if instances else None

    def attribute(self, node_type: NodeType, key: str) -> object:
        node = self._by_type.get(node_type)
        return node.attributes.get(key) if node else None

    @cached_property
    def levels(self) -> list[NodeType]:
        """Livelli gerarchici presenti, dal piu alto (sorgente) al piu basso."""
        present = [t for t in self._by_type if rank_of(t) is not None]
        return sorted(present, key=lambda t: rank_of(t) or 0)

    # ------------------------------------------------------------- annidamento

    def ancestors(self, node_type: NodeType) -> list[NodeType]:
        """Livelli che contengono il tipo dato, dal piu vicino al piu lontano."""
        if node_type not in self._graph:
            return []
        found = nx.descendants(self._graph, node_type)  # gli archi puntano verso l'alto
        return sorted(found, key=lambda t: -(rank_of(t) or 0))

    def descendants(self, node_type: NodeType) -> list[NodeType]:
        if node_type not in self._graph:
            return []
        found = nx.ancestors(self._graph, node_type)
        return sorted(found, key=lambda t: rank_of(t) or 0)

    def is_nested_in(self, child: NodeType, parent: NodeType) -> bool:
        if child not in self._graph or parent not in self._graph:
            return False
        return nx.has_path(self._graph, child, parent) and child != parent

    def direct_parents(self, node_type: NodeType) -> list[NodeType]:
        if node_type not in self._graph:
            return []
        return list(self._graph.successors(node_type))

    def relation(
        self, rel_type: RelationType, source: NodeType, target: NodeType
    ) -> GraphRelation | None:
        fallback: GraphRelation | None = None
        for relation in self.hierarchy.relations:
            if (
                relation.type is rel_type
                and self.node_type_of(relation.source) is source
                and self.node_type_of(relation.target) is target
            ):
                if not bool(relation.attributes.get("instance_relation")):
                    return relation
                fallback = fallback or relation
        return fallback

    def relations_of_type(self, rel_type: RelationType) -> list[GraphRelation]:
        return [r for r in self.hierarchy.relations if r.type is rel_type]

    def relations_from(
        self, node_id: str, rel_type: RelationType | None = None
    ) -> list[GraphRelation]:
        """Archi dichiarati uscenti da uno specifico nodo, senza collassare i tipi."""

        return [
            relation
            for relation in self.hierarchy.relations
            if relation.source == node_id and (rel_type is None or relation.type is rel_type)
        ]

    def relations_to(
        self, node_id: str, rel_type: RelationType | None = None
    ) -> list[GraphRelation]:
        """Archi dichiarati entranti in uno specifico nodo, senza invertirne il verso."""

        return [
            relation
            for relation in self.hierarchy.relations
            if relation.target == node_id and (rel_type is None or relation.type is rel_type)
        ]

    def per_parent(self, child: NodeType, parent: NodeType) -> int | None:
        for relation in self.hierarchy.relations:
            containment = _containment_endpoints(relation)
            if containment is None:
                continue
            child_id, parent_id = containment
            if self.node_type_of(child_id) is child and self.node_type_of(parent_id) is parent:
                value = relation.attributes.get("per_parent_count")
                if isinstance(value, int):
                    return value
        return None

    # ------------------------------------------------------------------ derivati

    def derived_count(self, node_type: NodeType) -> int | None:
        """Conteggio totale, ricavato se necessario risalendo la gerarchia."""
        direct = self.count(node_type)
        if direct is not None:
            return direct
        for parent in self.direct_parents(node_type):
            per = self.per_parent(node_type, parent)
            parent_count = self.derived_count(parent)
            if per is not None and parent_count is not None:
                return per * parent_count
        return None

    def scoped_instance_count(
        self, node_type: NodeType, *, factor_name: str, group: str
    ) -> int | None:
        """Conta istanze collegate a un'assegnazione esplicita di gruppo.

        L'assegnazione puo trovarsi sul nodo stesso o su un suo antenato reale
        nel grafo instance-level. In assenza di una catena esplicita restituisce
        ``None`` invece di usare il totale aggregato.
        """

        key = "assignment:" + "_".join(factor_name.strip().casefold().split())
        normalized_group = group.strip().casefold()
        all_instances = [
            node
            for nodes in self._nodes_by_type.values()
            for node in nodes
            if bool(node.attributes.get("instance"))
        ]
        if not any(key in node.attributes for node in all_instances):
            return None

        targets = self.instances(node_type)
        if not targets:
            return None
        matched = 0
        for node in targets:
            closure = {node.id}
            if node.id in self._instance_graph:
                closure.update(nx.descendants(self._instance_graph, node.id))
            if any(
                str(self._by_id[item].attributes.get(key, "")).strip().casefold()
                == normalized_group
                for item in closure
            ):
                matched += 1
        return matched

    def derived_count_for_scope(
        self,
        node_type: NodeType,
        *,
        factor_name: str,
        group: str | None,
    ) -> int | None:
        """Conteggio per gruppo; mai fallback silenzioso al totale globale."""

        if not group or group == "per_group":
            node = self.node(node_type)
            if node is not None and node.attributes.get("count_scope") == "per_group":
                value = node.attributes.get("per_group_count", node.count)
                return int(value) if isinstance(value, int) else None
            return self.derived_count(node_type)

        return self._derived_scoped(
            node_type,
            factor_name=factor_name,
            group=group,
            seen=set(),
        )

    def _derived_scoped(
        self,
        node_type: NodeType,
        *,
        factor_name: str,
        group: str,
        seen: set[NodeType],
    ) -> int | None:
        if node_type in seen:
            return None
        seen = {*seen, node_type}
        direct = self.scoped_instance_count(node_type, factor_name=factor_name, group=group)
        if direct is not None:
            return direct
        node = self.node(node_type)
        if node is not None and node.attributes.get("count_scope") == "per_group":
            value = node.attributes.get("per_group_count", node.count)
            if isinstance(value, int):
                return value
        for parent in self.direct_parents(node_type):
            per = self.per_parent(node_type, parent)
            parent_count = self._derived_scoped(
                parent,
                factor_name=factor_name,
                group=group,
                seen=seen,
            )
            if per is not None and parent_count is not None:
                return per * parent_count
        return None

    def clusters_above(self, node_type: NodeType) -> list[NodeType]:
        """Livelli superiori che raggruppano il tipo dato (blocchi o cluster)."""
        return [
            t for t in self.ancestors(node_type) if t in CLUSTER_TYPES or rank_of(t) is not None
        ]

    def is_technical(self, node_type: NodeType) -> bool:
        return node_type in TECHNICAL_TYPES

    def finest_level(self) -> NodeType | None:
        return self.levels[-1] if self.levels else None

    def coarsest_level(self) -> NodeType | None:
        return self.levels[0] if self.levels else None
