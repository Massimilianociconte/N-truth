"""Regressioni per il contratto pubblico della CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ntruth.cli.main import app


@pytest.mark.parametrize("language", ["it", "en"])
def test_analyze_accepts_only_documented_languages(tmp_path: Path, language: str) -> None:
    source = tmp_path / "methods.md"
    source.write_text(
        "# Methods\n\nThree independent donors were assigned to treatment.", encoding="utf-8"
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(source),
            "--out",
            str(tmp_path / "out"),
            "--lang",
            language,
            "--acknowledge-unvalidated-domain",
            "--quiet",
        ],
    )

    assert result.exit_code == 0, result.output


def test_analyze_rejects_unsupported_language_before_running(tmp_path: Path) -> None:
    source = tmp_path / "methods.md"
    source.write_text(
        "# Methods\n\nThree independent donors were assigned to treatment.", encoding="utf-8"
    )
    output = tmp_path / "out"

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(source),
            "--out",
            str(output),
            "--lang",
            "fr",
            "--acknowledge-unvalidated-domain",
        ],
    )

    assert result.exit_code == 2
    assert not output.exists()


@pytest.mark.parametrize("existing_directory", [False, True])
def test_verify_reports_an_unopenable_workspace_without_traceback(
    tmp_path: Path, existing_directory: bool
) -> None:
    workspace = tmp_path / "missing-workspace"
    if existing_directory:
        workspace.mkdir()

    result = CliRunner().invoke(app, ["verify", str(workspace)])

    assert result.exit_code == 2
    assert "Workspace non verificabile:" in result.output
    assert "manifest assente" in result.output
    assert "Traceback" not in result.output
