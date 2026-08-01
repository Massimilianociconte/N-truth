"""Ogni bug scientifico diventa una fixture congelata (PRD 22.3).

Questi test descrivono errori realmente osservati durante lo sviluppo. Non
vanno rilassati: se uno di essi fallisce, il sistema ha ripreso a leggere male
il disegno sperimentale.
"""

from __future__ import annotations

import pytest
from conftest import ProjectFactory

from ntruth.extract import extract
from ntruth.parsers.registry import build_document_ir
from ntruth.pipeline import analyze_project
from ntruth.schemas.core import Confidence, ProvenanceKind
from ntruth.schemas.experiment import Inferability
from ntruth.schemas.graph import NodeType, RelationType

pytestmark = pytest.mark.regression


def test_per_group_count_is_not_a_containment_cardinality(make_project: ProjectFactory) -> None:
    """Bug: '120 cellule per gruppo' veniva letto come '120 cellule per contenitore',
    lasciando il numero di osservazioni indeterminato."""
    project = make_project(
        {"m.md": "# Methods\n\n## Statistical analysis\n\nn = 120 cells per group.\n"}
    )
    result = extract(build_document_ir(project))
    cells = [e for e in result.entities if e.node_type is NodeType.CELL]
    assert cells and all(not e.per_parent for e in cells)


def test_material_plated_into_containers_is_not_inverted(make_project: ProjectFactory) -> None:
    """Bug: 'la preparazione e stata seminata in quattro pozzetti' produceva
    CellCulture annidata nel Well invece del contrario."""
    project = make_project(
        {"m.md": "# Methods\n\n## Cell culture\n\nEach preparation was plated into four wells.\n"}
    )
    result = extract(build_document_ir(project))
    nesting = {
        (r.source_type, r.target_type) for r in result.relations if r.type is RelationType.NESTED_IN
    }
    assert (NodeType.WELL, NodeType.CELL_CULTURE) in nesting
    assert (NodeType.CELL_CULTURE, NodeType.WELL) not in nesting


def test_domain_subsections_are_not_dropped(make_project: ProjectFactory) -> None:
    """Bug: '## Donors and cells' veniva classificata `other` e scartata, quindi il
    numero di donatori non entrava nel grafo e n indipendente restava ignoto."""
    project = make_project(
        {
            "m.md": (
                "# Materials and Methods\n\n## Donors and cells\n\n"
                "Cells were obtained from five independent donors.\n\n"
                "## Treatment\n\nCells were treated with drug or vehicle at the level of "
                "the donor.\n"
            )
        }
    )
    result = extract(build_document_ir(project))
    donors = [e for e in result.entities if e.node_type is NodeType.HUMAN_DONOR]
    assert any(e.count == 5 for e in donors)


def test_allocated_and_analysed_are_not_a_contradiction(make_project: ProjectFactory) -> None:
    """Bug: dieci animali allocati e otto analizzati venivano trattati come fonti
    in conflitto, bloccando ogni inferenza invece di rappresentare le esclusioni."""
    project = make_project(
        {
            "m.md": (
                "# Materials and Methods\n\n## Animals\n\nThe study used ten animals. "
                "Animals were treated with drug or vehicle.\n\n"
                "## Exclusions\n\nTwo animals were excluded from the analysis.\n\n"
                "## Statistical analysis\n\nn = 8 animals.\n"
            )
        }
    )
    result = analyze_project(project)
    block = result.block
    assert not [c for c in block.contradictions if c.status == "unresolved"]
    node = next(n for n in block.hierarchy.nodes if n.type is NodeType.ANIMAL)
    assert node.attributes.get("n_allocated") == 10
    assert node.attributes.get("n_analyzed") == 8


def test_declared_independence_is_never_assumed_for_biological_sources(
    make_project: ProjectFactory,
) -> None:
    """Il contenimento predefinito vale solo tra livelli tecnici: nessun arco
    inventato tra pozzetto e coltura o tra coltura e donatore."""
    project = make_project(
        {
            "m.md": (
                "# Materials and Methods\n\n## Microscopy\n\n"
                "Cells were imaged in wells. Cultures were prepared weekly.\n"
            )
        }
    )
    result = analyze_project(project)
    default_edges = [
        r for r in result.block.hierarchy.relations if r.attributes.get("default_containment")
    ]
    by_id = {n.id: n for n in result.block.hierarchy.nodes}
    for relation in default_edges:
        source, target = by_id[relation.source].type, by_id[relation.target].type
        assert source is not NodeType.CELL_CULTURE
        assert target is not NodeType.CELL_CULTURE
        assert target is not NodeType.HUMAN_DONOR


def test_conflicting_sources_never_produce_an_independent_n(make_project: ProjectFactory) -> None:
    """UC10: con fonti in conflitto il sistema non sceglie da solo un valore."""
    project = make_project(
        {
            "m.md": (
                "# Materials and Methods\n\n## Donors\n\n"
                "Cells were obtained from four independent donors.\n\n"
                "## Treatment\n\nCells were treated with drug or vehicle at the level of "
                "the donor.\n"
            ),
            "s.csv": "sample_id,donor,treatment\nS1,D1,drug\nS2,D2,drug\nS3,D3,vehicle\n",
        }
    )
    result = analyze_project(project)
    assert [c for c in result.block.contradictions if c.status == "unresolved"]
    for assessment in result.block.unit_assessments:
        assert assessment.n_independent is None


def test_author_independent_experiments_assertion_does_not_prove_independence(
    make_project: ProjectFactory,
) -> None:
    """PRD 9.2: "independent experiments" resta una AUTHOR_ASSERTION.

    Anche quando il parser risolve il conteggio e il livello di allocation, la
    frase non puo promuovere da sola l'indipendenza a HIGH o produrre un n
    indipendente autorevole.
    """

    project = make_project(
        {
            "m.md": (
                "# Materials and Methods\n\n## Cell culture\n\n"
                "Primary neurons were prepared from three independent preparations. "
                "Data are from three independent experiments. "
                "Cells were treated with drug or vehicle at the level of the culture. "
                "Intensity per culture was measured.\n"
            )
        },
        name="author-independence-assertion",
    )

    result = analyze_project(project)
    culture = next(
        node for node in result.block.hierarchy.nodes if node.type is NodeType.CELL_CULTURE
    )
    assessment = result.block.unit_assessments[0]

    assert culture.attributes.get("declared_independent") is True
    assert culture.provenance.origin is ProvenanceKind.EXPLICIT
    assert assessment.data_sufficiency.source_independence is not Confidence.HIGH
    assert assessment.inferability is Inferability.REQUIRES_CONFIRMATION
    assert assessment.n_allocated == 3
    assert assessment.n_independent is None
    assert result.abstention.abstained is True
    assert any(
        question.missing_field == "source_independence" for question in result.block.questions
    )


def test_unscoped_n_is_not_cartesian_joined_to_multiple_endpoints(
    make_project: ProjectFactory,
) -> None:
    """GEN-006: un n globale non viene replicato su endpoint non collegati."""

    project = make_project(
        {
            "m.md": (
                "# Materials and Methods\n\n## Animals\n\n"
                "Ten animals were used. Animals were treated with drug or vehicle at the "
                "level of the animal.\n\n## Outcomes\n\n"
                "Cell viability per animal was measured. Marker intensity per animal was "
                "measured.\n\n## Statistics\n\nn = 10 animals.\n"
            )
        },
        name="ambiguous-endpoint-scope",
    )

    result = analyze_project(project)
    block = result.block

    assert len(block.endpoints) == 2
    assert len(block.contrasts) == 1
    assert len(block.unit_assessments) == 1
    assessment = block.unit_assessments[0]
    assert assessment.scope.endpoint_id is None
    assert assessment.n_declared is None
    assert "GEN-006" in {alert.rule_id for alert in block.alerts}
    assert any(question.missing_field == "contrast.endpoint_ids" for question in block.questions)
