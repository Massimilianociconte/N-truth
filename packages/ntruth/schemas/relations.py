"""Registro canonico delle relazioni v7 (PRD v7 §8.5) con alias di migrazione.

Il registry e versionato separatamente dal codice (NFR-16). Le relazioni gia
presenti in ``RelationType`` restano la fonte operativa; qui si registrano le
relazioni aggiuntive v7 e le normalizzazioni dai termini legacy.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.schemas.graph import RelationType

RELATION_REGISTRY_VERSION: Final[str] = "0.2.0"


class V7Relation(StrEnum):
    """Relazioni aggiuntive o ri-registrate in v7 rispetto al registry 0.1.0."""

    ACQUIRED_FROM = "acquired_from"  # immagine/file <- field/well/instrument (E-09)
    OBSERVED_IN = "observed_in"  # osservazione <- contesto
    AGGREGATED_TO = "aggregated_to"  # osservazioni -> aggregato analitico
    EXPOSED_WITH = "exposed_with"  # esposizione condivisa
    MAY_INTERFERE_WITH = "may_interfere_with"  # interferenza possibile
    SUPPORTING_EVIDENCE = "supporting_evidence"  # evidenza a supporto
    CONFLICTING_EVIDENCE = "conflicting_evidence"  # evidenza in conflitto


#: Alias dai termini legacy verso il tipo canonico operativo.
#: Nessuna riscrittura silenziosa dei record storici: l'alias e dichiarato.
RELATION_ALIASES: dict[str, RelationType | V7Relation] = {
    "acquired_from": V7Relation.ACQUIRED_FROM,
    "observed_in": V7Relation.OBSERVED_IN,
    "aggregated_to": V7Relation.AGGREGATED_TO,
    "exposed_with": V7Relation.EXPOSED_WITH,
    "may_interfere_with": V7Relation.MAY_INTERFERE_WITH,
    "measured_on": RelationType.MEASURED_ON,
    "derived_from": RelationType.DERIVED_FROM,
    "nested_in": RelationType.NESTED_IN,
    "contained_in": RelationType.CONTAINS,
    "allocated_to": RelationType.ALLOCATED_TO,
    "applied_to": RelationType.APPLIED_TO,
    "repeated_measure_of": RelationType.REPEATED_MEASURE_OF,
    "supports": RelationType.SUPPORTS,
    "contradicts": RelationType.CONTRADICTS,
}

#: Relazioni che riguardano l'esposizione/interferenza: il silenzio non le
#: implica mai assenti (NFR-26).
EXPOSURE_RELATIONS: frozenset[V7Relation] = frozenset(
    {V7Relation.EXPOSED_WITH, V7Relation.MAY_INTERFERE_WITH}
)

#: Relazioni di evidenza: non sono fatti strutturali ma supporto/conflict.
EVIDENCE_RELATIONS: frozenset[V7Relation] = frozenset(
    {V7Relation.SUPPORTING_EVIDENCE, V7Relation.CONFLICTING_EVIDENCE}
)


class RelationRegistryEntry(FrozenModel):
    """Voce di registro: relazione, semantica e provenienza della decisione."""

    name: str
    canonical: str
    semantics: str
    introduced_in: str = RELATION_REGISTRY_VERSION
    alias_of: str | None = None


def canonical_relation(raw: str) -> RelationType | V7Relation:
    """Normalizza un termine legacy al tipo canonico (fail-closed)."""
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


def registry_checksum() -> str:
    """Checksum stabile del registro, per manifest e test di migrazione."""
    entries = {
        "version": RELATION_REGISTRY_VERSION,
        "v7_relations": sorted(r.value for r in V7Relation),
        "aliases": {k: str(v) for k, v in sorted(RELATION_ALIASES.items())},
    }
    return content_checksum(entries)
