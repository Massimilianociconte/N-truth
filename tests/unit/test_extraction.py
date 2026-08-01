"""Estrazione baseline: numeri, entita, relazioni e livello di assegnazione."""

from __future__ import annotations

import pytest
from conftest import ProjectFactory

from ntruth.extract.lexicon import is_ambiguous, lookup_entity
from ntruth.extract.numbers import find_count_phrases, find_n_mentions, parse_number
from ntruth.extract.text_extract import resolve_head_noun, resolve_phrase
from ntruth.schemas.graph import NodeType


@pytest.mark.parametrize(
    ("token", "value"),
    [("12", 12), ("1,200", 1200), ("three", 3), ("tre", 3), ("dodici", 12), ("abc", None)],
)
def test_number_parsing(token: str, value: int | None) -> None:
    assert parse_number(token) == value


def test_n_mention_with_entity_and_scope() -> None:
    mentions = find_n_mentions("Groups were compared; n = 120 cells per group.")
    assert len(mentions) == 1
    assert mentions[0].value == 120
    assert "per_group" in mentions[0].qualifiers


def test_count_phrase_qualifier_stays_inside_the_sentence() -> None:
    """Un 'per X' della frase successiva non e una cardinalita del conteggio."""
    mentions = find_count_phrases("The study used six animals. Fifty cells per animal.")
    six = next(m for m in mentions if m.value == 6)
    assert not any(q.startswith("per_") for q in six.qualifiers)


@pytest.mark.parametrize(
    ("term", "node_type"),
    [
        ("donors", NodeType.HUMAN_DONOR),
        ("colture", NodeType.CELL_CULTURE),
        ("preparation", NodeType.CELL_CULTURE),
        ("pozzetti", NodeType.WELL),
        ("mice", NodeType.ANIMAL),
        ("nuclei", NodeType.CELL),
        ("images", NodeType.FIELD),
        ("cell lines", NodeType.CELL_LINE),
    ],
)
def test_lexicon_lookup(term: str, node_type: NodeType) -> None:
    assert lookup_entity(term) is node_type


@pytest.mark.parametrize("term", ["replicates", "independent experiments", "samples", "repliche"])
def test_ambiguous_terms_are_not_resolved(term: str) -> None:
    """GEN-003: 'replica' e 'esperimento indipendente' non identificano un livello."""
    assert is_ambiguous(term)
    assert lookup_entity(term) is None


def test_modifiers_do_not_hide_the_noun() -> None:
    assert resolve_phrase("three independent preparations") is NodeType.CELL_CULTURE
    assert resolve_phrase("primary cortical neurons") is NodeType.CELL


def test_head_noun_wins_over_the_tail() -> None:
    node_type, term = resolve_head_noun("cells per group")
    assert node_type is NodeType.CELL
    assert term == "cells"


def test_assignment_level_from_explicit_statement(make_project: ProjectFactory) -> None:
    from ntruth.extract import extract
    from ntruth.parsers.registry import build_document_ir

    project = make_project(
        {
            "m.md": (
                "# Methods\n\n## Treatment\n\n"
                "Cells were treated with NGF or vehicle at the level of the culture.\n"
            )
        }
    )
    result = extract(build_document_ir(project))
    factor = next(f for f in result.factors if f.name == "treatment")
    assert factor.allocation_level is NodeType.CELL_CULTURE
    assert factor.assignment_level is NodeType.CELL_CULTURE
    assert factor.assignment_confidence >= 0.9
    assert factor.application_level is NodeType.CELL
    assert set(factor.levels) == {"NGF", "vehicle"}


def test_application_statement_does_not_silently_determine_allocation(
    make_project: ProjectFactory,
) -> None:
    from ntruth.extract import extract
    from ntruth.parsers.registry import build_document_ir

    project = make_project(
        {"m.md": ("# Methods\n\n## Treatment\n\nAnimals were treated with drug or vehicle.\n")}
    )
    result = extract(build_document_ir(project))
    factor = next(f for f in result.factors if f.name == "treatment")
    assert factor.application_level is NodeType.ANIMAL
    assert factor.allocation_level is None
    assert factor.assignment_level is None


def test_sample_sheet_infers_nesting_and_assignment(make_project: ProjectFactory) -> None:
    """Da una tabella l'annidamento e esatto, non probabilistico (ipotesi H5)."""
    from ntruth.extract import extract
    from ntruth.parsers.registry import build_document_ir
    from ntruth.schemas.graph import RelationType

    project = make_project(
        {
            "s.csv": (
                "donor,culture,well,treatment\n"
                "D1,C1,W1,drug\nD1,C1,W2,drug\nD1,C2,W3,vehicle\nD2,C3,W4,vehicle\n"
            )
        }
    )
    result = extract(build_document_ir(project))
    pairs = {
        (r.source_type, r.target_type) for r in result.relations if r.type is RelationType.NESTED_IN
    }
    assert (NodeType.WELL, NodeType.CELL_CULTURE) in pairs
    assert (NodeType.CELL_CULTURE, NodeType.HUMAN_DONOR) in pairs
    factor = next(f for f in result.factors if f.name == "treatment")
    assert factor.assignment_level is NodeType.CELL_CULTURE


def test_exclusion_counts_do_not_become_entity_totals(make_project: ProjectFactory) -> None:
    from ntruth.extract import extract
    from ntruth.parsers.registry import build_document_ir

    project = make_project(
        {
            "m.md": (
                "# Methods\n\n## Animals\n\nThe study used ten animals.\n\n"
                "## Exclusions\n\nTwo animals were excluded from the analysis.\n"
            )
        }
    )
    result = extract(build_document_ir(project))
    animal_counts = {e.count for e in result.entities if e.node_type is NodeType.ANIMAL}
    assert animal_counts == {10}
    assert any(p.kind == "exclusion" and p.value == 2 for p in result.processes)
