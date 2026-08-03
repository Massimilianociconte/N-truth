"""Registro canonico delle relazioni v7 (PRD v7 §8.5) con alias di migrazione.

``contained_in`` NON e alias di ``contains``: e una relazione canonica con
soggetto/oggetto opposti. Una sostituzione di stringa senza inversione
dell'arco e vietata.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.schemas.graph import RelationType

RELATION_REGISTRY_VERSION: Final[str] = "0.2.1"


class V7Relation(StrEnum):
    ACQUIRED_FROM = "acquired_from"
    OBSERVED_IN = "observed_in"
    AGGREGATED_TO = "aggregated_to"
    EXPOSED_WITH = "exposed_with"
    MAY_INTERFERE_WITH = "may_interfere_with"
    SUPPORTING_EVIDENCE = "supporting_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    CONTAINED_IN = "contained_in"


RELATION_ALIASES: dict[str, RelationType | V7Relation] = {
    "acquired_from": V7Relation.ACQUIRED_FROM,
    "observed_in": V7Relation.OBSERVED_IN,
    "aggregated_to": V7Relation.AGGREGATED_TO,
    "exposed_with": V7Relation.EXPOSED_WITH,
    "may_interfere_with": V7Relation.MAY_INTERFERE_WITH,
    "contained_in": V7Relation.CONTAINED_IN,
    "measured_on": RelationType.MEASURED_ON,
    "derived_from": RelationType.DERIVED_FROM,
    "nested_in": RelationType.NESTED_IN,
    "allocated_to": RelationType.ALLOCATED_TO,
    "applied_to": RelationType.APPLIED_TO,
    "repeated_measure_of": RelationType.REPEATED_MEASURE_OF,
    "supports": RelationType.SUPPORTS,
    "contradicts": RelationType.CONTRADICTS,
    "contains": RelationType.CONTAINS,
}

EXPOSURE_RELATIONS: frozenset[V7Relation] = frozenset(
    {V7Relation.EXPOSED_WITH, V7Relation.MAY_INTERFERE_WITH}
)
EVIDENCE_RELATIONS: frozenset[V7Relation] = frozenset(
    {V7Relation.SUPPORTING_EVIDENCE, V7Relation.CONFLICTING_EVIDENCE}
)
REGISTERED_RELATION_VALUES: frozenset[str] = frozenset(
    {r.value for r in RelationType} | {r.value for r in V7Relation}
)


class RelationRegistryEntry(FrozenModel):
    name: str
    canonical: str
    semantics: str
    introduced_in: str = RELATION_REGISTRY_VERSION
    alias_of: str | None = None


@dataclass(frozen=True)
class CanonicalEdge:
    source: str
    relation: RelationType | V7Relation
    target: str
    inverted: bool = False


def canonical_relation(raw: str) -> RelationType | V7Relation:
    key = raw.strip().lower()
    alias = RELATION_ALIASES.get(key)
    if alias is not None:
        return alias
    try:
        return RelationType(raw)
    except ValueError:
        pass
    try:
        return V7Relation(raw)
    except ValueError:
        raise ValueError(
            f"relazione non registrata nel registry {RELATION_REGISTRY_VERSION}: {raw!r}"
        ) from None


def canonicalize_relation_edge(source: str, relation: str, target: str) -> CanonicalEdge:
    """Normalizza un arco senza invertire silenziosamente soggetto/oggetto."""
    rel = canonical_relation(relation)
    return CanonicalEdge(source=source, relation=rel, target=target, inverted=False)


def registry_checksum() -> str:
    entries = {
        "version": RELATION_REGISTRY_VERSION,
        "v7_relations": sorted(r.value for r in V7Relation),
        "aliases": {k: str(v) for k, v in sorted(RELATION_ALIASES.items())},
    }
    return content_checksum(entries)
