"""Regressioni per il contratto pubblico della CLI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ntruth.cli.main import app
from ntruth.ingest.project import Project
from ntruth.storage import StorageDatabase


@pytest.mark.parametrize("language", ["it", "en"])
def test_analyze_v7_accepts_only_documented_languages(tmp_path: Path, language: str) -> None:
    source = tmp_path / "methods.md"
    source.write_text(
        "# Methods\n\nThree independent donors were assigned to treatment.", encoding="utf-8"
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze-v7",
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
    assert "DEPRECATED_V7_ADAPTER" in result.output


def test_analyze_v7_rejects_unsupported_language_before_running(tmp_path: Path) -> None:
    source = tmp_path / "methods.md"
    source.write_text(
        "# Methods\n\nThree independent donors were assigned to treatment.", encoding="utf-8"
    )
    output = tmp_path / "out"

    result = CliRunner().invoke(
        app,
        [
            "analyze-v7",
            str(source),
            "--out",
            str(output),
            "--lang",
            "fr",
            "--acknowledge-unvalidated-domain",
        ],
    )

    assert result.exit_code == 2
    assert "--lang" in result.output
    assert "fr" in result.output
    assert not output.exists()


def test_analyze_help_exposes_conservative_default_and_experimental_opt_in() -> None:
    result = CliRunner().invoke(app, ["analyze-v7", "--help"])

    assert result.exit_code == 0, result.output
    assert "--release-profile" in result.output
    assert "d0_core" in result.output
    assert "extended_experimental" in result.output


def test_sample_sheet_cli_generates_and_validates_v6_template(tmp_path: Path) -> None:
    destination = tmp_path / "samples.csv"
    runner = CliRunner()

    created = runner.invoke(
        app,
        [
            "sample-sheet",
            "init",
            str(destination),
            "--factor",
            "treatment",
        ],
    )
    validated = runner.invoke(app, ["sample-sheet", "validate", str(destination)])

    assert created.exit_code == 0, created.output
    assert destination.is_file()
    assert "non provano allocation o indipendenza" in created.output
    assert validated.exit_code == 0, validated.output
    assert "schema 6.0" in validated.output


def test_sample_sheet_cli_fails_closed_on_invalid_csv(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.csv"
    invalid.write_text("sample_id,lifecycle_status\nS1,observed\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["sample-sheet", "validate", str(invalid)])

    assert result.exit_code == 1
    assert "missing_required_header" in result.output
    assert "Sample sheet non valido" in result.output


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


def test_verify_rejects_a_tampered_manifest_without_side_effects(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project = Project.create(workspace, name="cli-tamper")
    manifest_path = workspace / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["ruleset_version"] = "tampered"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with StorageDatabase(project.database_path) as database:
        revisions_before = len(database.revisions(project.manifest.project_id))

    result = CliRunner().invoke(app, ["verify", str(workspace)])

    assert result.exit_code == 2
    assert "checksum manifest non corrispondente" in result.output
    assert "Traceback" not in result.output
    with StorageDatabase(project.database_path) as database:
        assert len(database.revisions(project.manifest.project_id)) == revisions_before


def test_verify_can_explicitly_migrate_a_valid_legacy_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    Project.create(workspace, name="cli-legacy")
    manifest_path = workspace / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("integrity")
    payload.pop("release_profile")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    for suffix in ("", "-journal", "-shm", "-wal"):
        Path(f"{workspace / 'ntruth.sqlite3'}{suffix}").unlink(missing_ok=True)
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    missing_digest = CliRunner().invoke(
        app,
        ["verify", str(workspace), "--migrate-legacy-manifest"],
    )
    assert missing_digest.exit_code == 2
    assert "SHA-256 esplicito" in missing_digest.output

    result = CliRunner().invoke(
        app,
        [
            "verify",
            str(workspace),
            "--migrate-legacy-manifest",
            "--legacy-manifest-sha256",
            digest,
        ],
    )

    assert result.exit_code == 0, result.output
    migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(migrated["integrity"]["manifest_checksum"]) == 64
