"""Final content, binary-signature, and mount-boundary repository-policy regressions."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ntruth.governance import repository_policy
from ntruth.governance.repository_policy import (
    RepositoryPolicyFindingKindV8,
    scan_tracked_repository_v8,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REVIEWED_SCHEMA_PATHS = (
    "docs/task_corpora/build_manifest.schema.json",
    "docs/task_corpora/license_use_decision.schema.json",
    "docs/task_corpora/task_record.schema.json",
)


def _write(root: Path, relative: str, payload: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return relative


def _kinds_for(report: object, relative: str) -> set[RepositoryPolicyFindingKindV8]:
    findings = report.findings.value or ()  # type: ignore[attr-defined]
    return {finding.kind for finding in findings if finding.path == relative}


@pytest.mark.parametrize("relative", _REVIEWED_SCHEMA_PATHS)
def test_reviewed_schema_assets_require_the_exact_content_address(
    relative: str,
    tmp_path: Path,
) -> None:
    """Changing even ignorable whitespace in a reviewed schema must revoke its exception."""

    original = (_PROJECT_ROOT / relative).read_bytes()
    tracked = _write(tmp_path, relative, original)
    approved = scan_tracked_repository_v8(tmp_path, (tracked,))
    assert approved.clean is True

    (tmp_path / relative).write_bytes(original + b" ")
    mutated = scan_tracked_repository_v8(tmp_path, (tracked,))

    assert RepositoryPolicyFindingKindV8.NO_CORPUS in _kinds_for(mutated, relative)


@pytest.mark.parametrize("relative", _REVIEWED_SCHEMA_PATHS)
def test_schema_annotation_cannot_hide_record_bearing_content(
    relative: str,
    tmp_path: Path,
) -> None:
    """A record object below a schema annotation keyword must not pass as a schema."""

    payload = (
        b'{"$schema":"https://json-schema.org/draft/2020-12/schema",'
        b'"description":{"records":[{"id":"synthetic"}]}}\n'
    )
    tracked = _write(tmp_path, relative, payload)

    report = scan_tracked_repository_v8(tmp_path, (tracked,))

    assert RepositoryPolicyFindingKindV8.NO_CORPUS in _kinds_for(report, relative)


@pytest.mark.parametrize(
    "relative",
    (
        "packages/ntruth/task_corpora/corpus.yaml",
        "scripts/task_corpora/dataset.yaml",
        "tests/integration/task_corpora/records.yaml",
        "tests/unit/task_corpora/participants.yaml",
        "data/manifests/dataset.yaml",
        "docs/dataset.md",
    ),
)
def test_metadata_and_documentation_locations_do_not_exempt_record_payloads(
    relative: str,
    tmp_path: Path,
) -> None:
    """Moving a record-bearing document under a governed-looking prefix must stay blocking."""

    tracked = _write(tmp_path, relative, b"records:\n  - id: synthetic\n")

    report = scan_tracked_repository_v8(tmp_path, (tracked,))

    assert RepositoryPolicyFindingKindV8.NO_CORPUS in _kinds_for(report, relative)


def test_source_code_and_content_addressed_documentation_remain_allowed_controls(
    tmp_path: Path,
) -> None:
    """The narrowed policy must preserve source code and an exact reviewed document asset."""

    reviewed = "docs/dataset-assessment.md"
    tracked = (
        _write(tmp_path, "packages/ntruth/task_corpora/tool.py", b"RECORD = 'metadata'\n"),
        _write(tmp_path, reviewed, (_PROJECT_ROOT / reviewed).read_bytes()),
    )

    report = scan_tracked_repository_v8(tmp_path, tracked)

    assert report.clean is True
    assert report.scanned_file_count == len(tracked)


@pytest.mark.parametrize(
    "relative",
    (
        "assets/corpus.dat",
        "assets/corpus",
        "assets/dataset/cache.safe",
        "artifacts/challenge/payload",
        "packages/ntruth/task_corpora/corpus.py",
    ),
)
def test_marker_bearing_non_utf8_payloads_are_blocked_independently_of_suffix(
    relative: str,
    tmp_path: Path,
) -> None:
    """Invalid UTF-8 and an unknown suffix must not neutralize explicit corpus path semantics."""

    tracked = _write(tmp_path, relative, b"\xff\xfe\x00synthetic")

    report = scan_tracked_repository_v8(tmp_path, (tracked,))

    assert RepositoryPolicyFindingKindV8.NO_CORPUS in _kinds_for(report, relative)


@pytest.mark.parametrize(
    ("relative", "payload", "expected"),
    (
        (
            "assets/ordinary-parquet.safe",
            b"PAR1\x15\x00synthetic-column-chunkPAR1",
            RepositoryPolicyFindingKindV8.NO_CORPUS,
        ),
        (
            "assets/ordinary-arrow.safe",
            b"ARROW1\x00\x00synthetic-record-batchARROW1",
            RepositoryPolicyFindingKindV8.NO_CORPUS,
        ),
        (
            "assets/ordinary-feather.safe",
            b"ARROW1\x00\x00synthetic-featherARROW1",
            RepositoryPolicyFindingKindV8.NO_CORPUS,
        ),
        (
            "assets/ordinary-model.safe",
            b"GGUF\x03\x00\x00\x00synthetic-model-metadata",
            RepositoryPolicyFindingKindV8.MODEL_OR_WEIGHT,
        ),
        (
            "assets/ordinary-database.safe",
            b"\x00\x00\x00\x00\x00\x00\x00\x00DUCKsynthetic-database",
            RepositoryPolicyFindingKindV8.NO_CORPUS,
        ),
    ),
)
def test_renamed_corpus_and_model_signatures_are_classified_from_bytes(
    relative: str,
    payload: bytes,
    expected: RepositoryPolicyFindingKindV8,
    tmp_path: Path,
) -> None:
    """Renaming a governed binary format must not bypass byte-level classification."""

    tracked = _write(tmp_path, relative, payload)

    report = scan_tracked_repository_v8(tmp_path, (tracked,))

    assert expected in _kinds_for(report, relative)


def test_git_lfs_pointer_is_a_blocking_uninspected_external_object_reference(
    tmp_path: Path,
) -> None:
    """A tracked LFS indirection must not be reported as inspected repository payload bytes."""

    relative = _write(
        tmp_path,
        "assets/ordinary.safe",
        (
            b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
            b"size 12345\n"
        ),
    )

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.external_datasets_inspected is False


def test_missing_platform_mount_inventory_fails_closed_before_file_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A platform that cannot establish mount boundaries must not inspect a tracked leaf."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"synthetic internal bytes\n")
    monkeypatch.setattr(
        repository_policy,
        "_mount_points_for_repository",
        lambda _root: None,
        raising=False,
    )

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.scanned_file_count == 0
    assert report.external_datasets_inspected is False


def test_descendant_mount_boundary_fails_closed_before_file_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A tracked path below an inventoried mount point must not have its leaf bytes opened."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"synthetic mounted bytes\n")
    monkeypatch.setattr(
        repository_policy,
        "_mount_points_for_repository",
        lambda root: frozenset({root / "assets"}),
        raising=False,
    )

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.scanned_file_count == 0
    assert report.external_datasets_inspected is False


def test_real_ci_command_blocks_all_fix5_counterfactuals(tmp_path: Path) -> None:
    """The real CI entrypoint must propagate content, binary, and LFS bypass findings."""

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    tracked = (
        _write(
            root,
            "docs/task_corpora/task_record.schema.json",
            (
                b'{"$schema":"https://json-schema.org/draft/2020-12/schema",'
                b'"description":{"records":[{"id":"synthetic"}]}}\n'
            ),
        ),
        _write(root, "packages/ntruth/task_corpora/corpus.yaml", b"records: [synthetic]\n"),
        _write(root, "assets/corpus.dat", b"\xff\xfe\x00synthetic"),
        _write(root, "assets/parquet.safe", b"PAR1syntheticPAR1"),
        _write(root, "assets/arrow.safe", b"ARROW1syntheticARROW1"),
        _write(root, "assets/model.safe", b"GGUF\x03\x00\x00\x00synthetic"),
        _write(root, "assets/database.safe", b"\x00\x00\x00\x00\x00\x00\x00\x00DUCKsynthetic"),
        _write(
            root,
            "assets/lfs.safe",
            (
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
                b"size 12345\n"
            ),
        ),
    )
    subprocess.run(["git", "-C", str(root), "add", *tracked], check=True)

    result = subprocess.run(
        [
            sys.executable,
            str(_PROJECT_ROOT / "scripts/check_repository_policy.py"),
            "--repo",
            str(root),
        ],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    findings = json.loads(result.stdout)["findings"]["value"]
    assert {finding["path"] for finding in findings} == set(tracked)
