"""Regression tests for fail-closed PRD v8 tracked-tree inspection."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ntruth.governance.repository_policy import (
    RepositoryPolicyFindingKindV8,
    scan_tracked_repository_v8,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
        "assets/corpus.txt",
        "artifacts/challenge.xml",
        "artifacts/dataset.conll",
        "artifacts/participant.iob",
        "artifacts/record.tei",
        "artifacts/subject.text",
    ),
)
def test_named_raw_text_corpora_are_blocked_below_the_size_limit(
    relative: str,
    tmp_path: Path,
) -> None:
    """A payload-capable text suffix must not bypass NO_CORPUS name markers."""

    tracked = _write(tmp_path, relative, b"synthetic experiment record\n")
    report = scan_tracked_repository_v8(tmp_path, (tracked,), max_file_bytes=128)

    assert RepositoryPolicyFindingKindV8.NO_CORPUS in _kinds_for(report, relative)
    assert report.clean is False


def test_exact_reviewed_documentation_assets_remain_non_payload_controls(tmp_path: Path) -> None:
    """Content-addressed reviewed documents remain allowed without a class-wide exception."""

    tracked = (
        _write(
            tmp_path,
            "docs/dataset-assessment.md",
            (_PROJECT_ROOT / "docs/dataset-assessment.md").read_bytes(),
        ),
        _write(
            tmp_path,
            "docs/task_corpora/provisional-reality-gate-ref.md",
            (_PROJECT_ROOT / "docs/task_corpora/provisional-reality-gate-ref.md").read_bytes(),
        ),
        _write(
            tmp_path,
            "docs/task_corpora/task_record.schema.json",
            (_PROJECT_ROOT / "docs/task_corpora/task_record.schema.json").read_bytes(),
        ),
    )
    report = scan_tracked_repository_v8(tmp_path, tracked)

    assert report.clean is True


def test_ci_policy_command_fails_for_small_named_txt_and_xml_corpora(tmp_path: Path) -> None:
    """The real CI command must propagate named text/XML corpus findings."""

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    tracked = (
        _write(root, "assets/corpus.txt", b"case one\ncase two\n"),
        _write(root, "artifacts/challenge.xml", b"<cases><case id='1'/></cases>\n"),
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
    by_path = {finding["path"]: finding["kind"] for finding in output["findings"]["value"]}
    assert by_path == {relative: "NO_CORPUS" for relative in sorted(tracked)}


def test_open_failure_is_an_explicit_blocking_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An inability to open a tracked file must never degrade to a clean report."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"safe text\n")
    real_open = os.open

    def failing_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if Path(os.fsdecode(path)).name == "ordinary.safe":
            raise OSError("injected tracked-file open failure")
        if dir_fd is None:
            return real_open(path, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", failing_open)
    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.clean is False


def test_fstat_failure_is_an_explicit_blocking_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An inability to inspect descriptor metadata must fail the scan closed."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"safe text\n")

    def failing_fstat(_fd: int) -> os.stat_result:
        raise OSError("injected tracked-file stat failure")

    monkeypatch.setattr(os, "fstat", failing_fstat)
    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.clean is False


def test_read_failure_is_an_explicit_blocking_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An inability to read tracked bytes must fail the scan closed."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"safe text\n")

    def failing_read(_fd: int, _size: int) -> bytes:
        raise OSError("injected tracked-file read failure")

    monkeypatch.setattr(os, "read", failing_read)
    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.clean is False


def test_path_replacement_during_read_is_an_explicit_blocking_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A tracked name swapped during inspection must not inherit a clean scan."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"original safe text\n")
    tracked_path = tmp_path / relative
    tracked_inode = tracked_path.stat().st_ino
    replacement = tmp_path / "assets/replacement.safe"
    replacement.write_bytes(b"replacement bytes\n")
    real_read = os.read
    swapped = False

    def replacing_read(fd: int, size: int) -> bytes:
        nonlocal swapped
        if not swapped and os.fstat(fd).st_ino == tracked_inode:
            os.replace(replacement, tracked_path)
            swapped = True
        return real_read(fd, size)

    monkeypatch.setattr(os, "read", replacing_read)
    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert swapped is True
    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.clean is False
