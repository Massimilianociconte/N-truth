"""Relation direction: contained_in must not invert subject/object silently."""

from __future__ import annotations

from ntruth.schemas.relations import V7Relation, canonical_relation, canonicalize_relation_edge


def test_contained_in_is_not_contains() -> None:
    edge = canonicalize_relation_edge("well", "contained_in", "plate")
    assert edge.relation is V7Relation.CONTAINED_IN
    assert edge.source == "well"
    assert edge.target == "plate"
    assert edge.inverted is False


def test_contains_stays_contains() -> None:
    edge = canonicalize_relation_edge("plate", "contains", "well")
    assert edge.relation.value == "contains"
    assert edge.source == "plate"
    assert edge.target == "well"


def test_string_alias_does_not_map_contained_in_to_contains() -> None:
    rel = canonical_relation("contained_in")
    assert rel is V7Relation.CONTAINED_IN
    assert rel.value != "contains"
