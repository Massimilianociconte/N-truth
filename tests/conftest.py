"""Utilita condivise dai test.

Ogni fixture scientifica e una cartella con input sintetici e un `expected.json`
normativo derivato dal PRD. E un contratto di regressione del software, non un
gold corpus annotato o adjudicato da esperti.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from ntruth.ingest.project import Project
from ntruth.pipeline import AnalysisResult, analyze_project
from ntruth.rules.loader import load_ruleset
from ntruth.schemas.rules import Ruleset

FIXTURES_DIR = Path(__file__).parent / "scientific_fixtures"


@dataclass
class Case:
    """Una fixture scientifica caricata."""

    name: str
    path: Path
    expected: dict[str, Any]

    @property
    def case_id(self) -> str:
        return str(self.expected.get("id", self.name))


AnalyzeFixture = Callable[..., AnalysisResult]
ProjectFactory = Callable[..., Project]


def load_cases() -> list[Case]:
    cases: list[Case] = []
    for directory in sorted(FIXTURES_DIR.iterdir()):
        expected_path = directory / "expected.json"
        if not directory.is_dir() or not expected_path.is_file():
            continue
        cases.append(
            Case(
                name=directory.name,
                path=directory,
                expected=json.loads(expected_path.read_text(encoding="utf-8")),
            )
        )
    return cases


def analyze_directory(source: Path, workspace: Path, *, lang: str = "it") -> AnalysisResult:
    """Esegue la pipeline completa su una cartella di input."""
    project = Project.create(workspace, name=source.name, language="en")
    project.add(source)
    return analyze_project(project, ruleset=load_ruleset(), lang=lang)


@pytest.fixture
def analyze(tmp_path: Path) -> AnalyzeFixture:
    """Analizza una cartella in un workspace temporaneo."""

    def _run(source: Path, *, lang: str = "it") -> AnalysisResult:
        workspace = tmp_path / f"prj-{source.name}"
        return analyze_directory(source, workspace, lang=lang)

    return _run


@pytest.fixture
def make_project(tmp_path: Path) -> ProjectFactory:
    """Crea un progetto con file scritti al volo."""

    def _make(
        files: dict[str, str], name: str = "test", project_name: str | None = None
    ) -> Project:
        """`name` isola le cartelle, `project_name` e il nome logico del progetto.

        Tenerli distinti permette di creare due workspace diversi con lo stesso
        input logico, che e cio che serve per verificare la riproducibilita.
        """
        source = tmp_path / f"src-{name}"
        source.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (source / filename).write_text(content, encoding="utf-8")
        project = Project.create(tmp_path / f"prj-{name}", name=project_name or name, language="en")
        project.add(source)
        return project

    return _make


@pytest.fixture
def ruleset() -> Ruleset:
    return load_ruleset()
