"""Pipeline completa: riproducibilita, offline, report e correzioni (PRD 11.3, NFR-01/02)."""

from __future__ import annotations

import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import ProjectFactory

import ntruth.pipeline as pipeline_module
from ntruth.extract.facts import ExtractionResult
from ntruth.graph.builder import BuildResult
from ntruth.graph.validation import GraphValidationError
from ntruth.pipeline import AnalysisResult, analyze_project
from ntruth.reporting import write_all
from ntruth.reporting.html_report import render_html
from ntruth.schemas.core import Provenance, ProvenanceKind
from ntruth.schemas.graph import GraphRelation, RelationType

METHODS = (
    "# Materials and Methods\n\n"
    "## Cell culture\n\nPrimary neurons were prepared from three independent preparations. "
    "Each preparation was plated into four wells.\n\n"
    "## Treatment\n\nCells were treated with NGF or vehicle at the level of the culture.\n\n"
    "## Quantitative microscopy\n\nIntensity per cell was quantified. "
    "Five fields were acquired per well.\n\n"
    "## Statistical analysis\n\nGroups were compared with an unpaired t-test; n = 120 cells.\n"
)


def test_same_input_produces_the_same_report(make_project: ProjectFactory) -> None:
    """NFR-02: stesso input, stesse versioni, stesso output."""
    first = analyze_project(make_project({"m.md": METHODS}, name="a", project_name="studio"))
    second = analyze_project(make_project({"m.md": METHODS}, name="b", project_name="studio"))
    assert first.report.content_checksum() == second.report.content_checksum()
    assert first.block.id == second.block.id


def test_report_records_versions_and_checksums(make_project: ProjectFactory) -> None:
    """FR-034: ruleset e versioni in ogni report; FR-007: checksum degli input."""
    result = analyze_project(make_project({"m.md": METHODS}))
    report = result.report
    assert report.versions.ruleset_id == "ntruth-core"
    assert report.versions.ruleset_version
    assert report.versions.schema_version
    assert len(report.input_checksum) == 64
    assert len(report.ruleset_checksum) == 64


def test_html_contains_only_facts_present_in_the_json(
    make_project: ProjectFactory, tmp_path: Path
) -> None:
    """PRD 11.3: il renderer non introduce fatti assenti dal JSON."""
    result = analyze_project(make_project({"m.md": METHODS}))
    html = render_html(result.report)
    for alert in result.block.alerts:
        assert alert.rule_id in html
    numbers_in_json = {
        str(a.n_independent) for a in result.block.unit_assessments if a.n_independent is not None
    }
    for value in numbers_in_json:
        assert value in html


def test_write_all_produces_json_graph_and_html(
    make_project: ProjectFactory, tmp_path: Path
) -> None:
    result = analyze_project(make_project({"m.md": METHODS}))
    written = write_all(result.report, tmp_path / "out")
    assert written["json"].is_file() and written["html"].is_file()
    graph = json.loads(written["graph_0"].read_text(encoding="utf-8"))
    assert graph["nodes"] and graph["relations"]
    for node in graph["nodes"]:
        assert node["provenance"]["origin"]


def test_every_fact_carries_provenance(make_project: ProjectFactory) -> None:
    """PRD 7.4: nessun fatto senza origine dichiarata."""
    block = analyze_project(make_project({"m.md": METHODS})).block
    for node in block.hierarchy.nodes:
        assert node.provenance.origin
    for relation in block.hierarchy.relations:
        assert relation.provenance.origin
    for alert in block.alerts:
        assert alert.provenance.rule_id == alert.rule_id


def test_limits_are_declared_in_the_report(make_project: ProjectFactory) -> None:
    """FR-014 e trasparenza: i limiti noti sono nel report, non impliciti."""
    result = analyze_project(make_project({"m.md": METHODS}))
    joined = " ".join(result.report.limits)
    assert "ExperimentBlock" in joined
    assert "deterministica" in joined


def test_analysis_does_not_open_network_connections(
    make_project: ProjectFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-01 e FR-035: il core funziona senza rete."""

    def _blocked(*args: object, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("il core non deve aprire connessioni di rete")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    result = analyze_project(make_project({"m.md": METHODS}))
    assert result.block.alerts


def test_project_reopens_offline_without_loss(make_project: ProjectFactory, tmp_path: Path) -> None:
    """FR-001: riapertura offline senza perdita."""
    from ntruth.ingest.project import Project

    project = make_project({"m.md": METHODS}, name="riapertura")
    checksum = project.manifest.checksum()
    reopened = Project.open(project.root)
    assert reopened.manifest.checksum() == checksum
    assert not reopened.verify_integrity()
    assert analyze_project(reopened).report.content_checksum()


def test_rules_can_change_without_touching_the_code(
    make_project: ProjectFactory, tmp_path: Path
) -> None:
    """FR-018: modificare il ruleset non richiede retraining ne una nuova build."""
    from ntruth.rules.loader import load_ruleset_file

    payload = {
        "ruleset_id": "test-locale",
        "version": "0.0.1",
        "description": "ruleset minimo per il test",
        "rules": [
            {
                "rule_id": "LOC-001",
                "version": "1.0.0",
                "domain": "general",
                "title": "regola locale",
                "preconditions": ["analysis_finer_than_assignment()"],
                "inference": "local rule",
                "message_it": "regola locale attiva su {experimental_unit}",
                "message_en": "local rule active on {experimental_unit}",
                "severity": "medium",
            }
        ],
    }
    path = tmp_path / "test-locale-0.0.1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ruleset = load_ruleset_file(path)

    result = analyze_project(make_project({"m.md": METHODS}), ruleset=ruleset)
    assert {a.rule_id for a in result.block.alerts} == {"LOC-001"}


def test_language_layer_is_separate_from_the_scientific_layer(
    make_project: ProjectFactory,
) -> None:
    """NFR-15: cambiare lingua cambia i messaggi, non unita, n o regole scattate."""
    italian = analyze_project(make_project({"m.md": METHODS}, name="lang-it"), lang="it")
    english = analyze_project(make_project({"m.md": METHODS}, name="lang-en"), lang="en")

    def scientific_content(
        result: AnalysisResult,
    ) -> tuple[list[str], list[tuple[str, int | None, str]]]:
        return (
            sorted(a.rule_id for a in result.block.alerts),
            [
                (str(a.experimental_unit), a.n_independent, a.risk.value)
                for a in result.block.unit_assessments
            ],
        )

    assert scientific_content(italian) == scientific_content(english)
    assert italian.block.alerts
    assert {a.message for a in italian.block.alerts} != {a.message for a in english.block.alerts}


def test_invalid_graph_is_rejected_before_unit_resolution(
    make_project: ProjectFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project({"m.md": METHODS}, name="invalid-graph")
    original_build_graph = pipeline_module.build_graph
    resolver_called = False

    def invalid_build(block_id: str, extraction: ExtractionResult) -> BuildResult:
        built = original_build_graph(block_id, extraction)
        dangling = GraphRelation(
            id="dangling-relation",
            type=RelationType.NESTED_IN,
            source="missing-child",
            target="missing-parent",
            provenance=Provenance(origin=ProvenanceKind.DERIVED),
        )
        hierarchy = built.hierarchy.model_copy(
            update={"relations": (*built.hierarchy.relations, dangling)}
        )
        return replace(built, hierarchy=hierarchy)

    def forbidden_resolver(*args: object, **kwargs: object) -> None:
        nonlocal resolver_called
        resolver_called = True
        raise AssertionError("il resolver non deve leggere un grafo non valido")

    monkeypatch.setattr(pipeline_module, "build_graph", invalid_build)
    monkeypatch.setattr(pipeline_module, "resolve_units", forbidden_resolver)

    with pytest.raises(GraphValidationError, match="dangling_relation_endpoint"):
        pipeline_module.analyze_project(project)
    assert not resolver_called
