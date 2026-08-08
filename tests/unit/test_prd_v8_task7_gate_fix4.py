"""Residual fail-closed regressions for the PRD v8 tracked-tree policy gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ntruth.governance import repository_policy
from ntruth.governance.repository_policy import (
    RepositoryPolicyFindingKindV8,
    scan_tracked_repository_v8,
    tracked_paths_from_git_v8,
)


def _write(root: Path, relative: str, payload: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return relative


def _kinds_for(report: object, relative: str) -> set[RepositoryPolicyFindingKindV8]:
    findings = report.findings.value or ()  # type: ignore[attr-defined]
    return {finding.kind for finding in findings if finding.path == relative}


@pytest.mark.parametrize(
    "relative",
    (
        "assets/corpus/cases.txt",
        "artifacts/challenge/cases.xml",
        "assets/study-participants/cases.text",
        "artifacts/subject-records/cases.tei",
    ),
)
def test_corpus_markers_in_any_payload_path_component_are_blocking(
    relative: str,
    tmp_path: Path,
) -> None:
    """Moving a decoded corpus below a marker-bearing directory must not bypass the gate."""

    tracked = _write(tmp_path, relative, b"synthetic case one\n")

    report = scan_tracked_repository_v8(tmp_path, (tracked,))

    assert RepositoryPolicyFindingKindV8.NO_CORPUS in _kinds_for(report, relative)


@pytest.mark.parametrize(
    ("relative", "payload"),
    (
        ("assets/corpus.md", b"case one\ncase two\n"),
        ("assets/challenge.yaml", b"cases: [one, two]\n"),
        ("assets/dataset.yml", b"records: [one, two]\n"),
    ),
)
def test_named_utf8_markdown_and_yaml_payloads_are_content_classified(
    relative: str,
    payload: bytes,
    tmp_path: Path,
) -> None:
    """Changing a corpus serialization to decoded Markdown/YAML must remain blocking."""

    tracked = _write(tmp_path, relative, payload)

    report = scan_tracked_repository_v8(tmp_path, (tracked,))

    assert RepositoryPolicyFindingKindV8.NO_CORPUS in _kinds_for(report, relative)


def test_explicit_source_and_manifest_metadata_directories_remain_non_payload_controls(
    tmp_path: Path,
) -> None:
    """Governed tooling and manifest paths must not be confused with corpus payload storage."""

    tracked = (
        _write(tmp_path, "packages/ntruth/task_corpora/cli.py", b"VALUE = 'metadata'\n"),
        _write(tmp_path, "scripts/task_corpora/check_records.py", b"VALUE = 'tooling'\n"),
        _write(tmp_path, "tests/unit/task_corpora/test_records.py", b"VALUE = 'test'\n"),
        _write(tmp_path, "data/manifests/dataset.json", b'{"snapshot_id":"synthetic"}\n'),
        _write(tmp_path, "docs/dataset.md", b"Dataset governance documentation.\n"),
    )

    report = scan_tracked_repository_v8(tmp_path, tracked)

    assert report.clean is True
    assert report.scanned_file_count == len(tracked)


@pytest.mark.parametrize(
    ("relative", "payload"),
    (
        ("docs/hidden-corpus.schema.json", b'{"records":[{"id":1}]}\n'),
        (
            "docs/task_corpora/task_record.schema.json",
            b'{"type":"object","properties":{},"records":[{"id":1}]}\n',
        ),
    ),
)
def test_documentation_schema_names_cannot_exempt_record_payloads(
    relative: str,
    payload: bytes,
    tmp_path: Path,
) -> None:
    """An unknown or mixed schema-named JSON payload must not inherit a docs exception."""

    tracked = _write(tmp_path, relative, payload)

    report = scan_tracked_repository_v8(tmp_path, (tracked,))

    assert RepositoryPolicyFindingKindV8.NO_CORPUS in _kinds_for(report, relative)


def test_early_empty_read_is_incomplete_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An immediate EOF before the descriptor size is consumed must be blocking evidence."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"secret-bearing bytes\n")
    monkeypatch.setattr(os, "read", lambda _fd, _size: b"")

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.scanned_file_count == 0
    assert report.tracked_path_count == 1
    assert report.inspection_complete is False


def test_partial_read_then_eof_is_incomplete_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A stable descriptor with truncated detector input must not count as inspected."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"secret-bearing bytes\n")
    real_read = os.read
    read_count = 0

    def partial_then_eof(fd: int, size: int) -> bytes:
        nonlocal read_count
        read_count += 1
        if read_count == 1:
            return real_read(fd, min(size, 4))
        return b""

    monkeypatch.setattr(os, "read", partial_then_eof)

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.scanned_file_count == 0
    assert report.tracked_path_count == 1
    assert report.inspection_complete is False


def test_preexisting_external_hard_link_is_not_reported_as_an_internal_scan(
    tmp_path: Path,
) -> None:
    """A multiply linked leaf must fail before bytes can contradict the provenance scope."""

    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    external = tmp_path / "synthetic-external.safe"
    external.write_bytes(b"synthetic external bytes\n")
    relative = "assets/ordinary.safe"
    inside = repository_root / relative
    inside.parent.mkdir(parents=True)
    os.link(external, inside)

    report = scan_tracked_repository_v8(repository_root, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.external_datasets_inspected is False
    assert report.scanned_file_count == 0
    assert report.inspection_complete is False


def test_git_path_enumeration_requires_a_complete_nul_terminated_stream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Truncating git output before its terminator must not yield a partial tracked set."""

    monkeypatch.setattr(
        repository_policy.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=b"README.md"),
    )

    with pytest.raises(RuntimeError, match="incomplete tracked-path enumeration"):
        tracked_paths_from_git_v8(tmp_path)


def test_complete_scan_reports_expected_and_inspected_path_cardinality(tmp_path: Path) -> None:
    """Removing one inspection must make the report's completeness evidence false."""

    tracked = (
        _write(tmp_path, "README.md", b"safe\n"),
        _write(tmp_path, "packages/ntruth/safe.py", b"VALUE = 'safe'\n"),
    )

    report = scan_tracked_repository_v8(tmp_path, tracked)

    assert report.tracked_path_count == 2
    assert report.scanned_file_count == 2
    assert report.inspection_complete is True


def test_real_ci_command_blocks_component_text_and_schema_bypasses(tmp_path: Path) -> None:
    """The CI entrypoint must propagate every residual decoded-text NO_CORPUS class."""

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    tracked = (
        _write(root, "assets/corpus/cases.txt", b"case one\n"),
        _write(root, "artifacts/challenge/cases.xml", b"<case/>\n"),
        _write(root, "assets/corpus.md", b"case one\n"),
        _write(root, "assets/challenge.yaml", b"cases: [one]\n"),
        _write(root, "assets/dataset.yml", b"records: [one]\n"),
        _write(root, "docs/hidden-corpus.schema.json", b'{"records":[{"id":1}]}\n'),
    )
    subprocess.run(["git", "-C", str(root), "add", *tracked], check=True)
    project_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts/check_repository_policy.py"),
            "--repo",
            str(root),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    output = json.loads(result.stdout)
    findings = output["findings"]["value"]
    assert {
        finding["path"]
        for finding in findings
        if finding["kind"] == RepositoryPolicyFindingKindV8.NO_CORPUS
    } == set(tracked)
