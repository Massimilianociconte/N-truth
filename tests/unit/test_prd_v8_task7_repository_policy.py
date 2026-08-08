"""Bounded tracked-tree NO_CORPUS, privacy, secret and size policy."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ntruth.governance.repository_policy import (
    RepositoryPolicyFindingKindV8,
    scan_tracked_repository_v8,
)


def _write(root: Path, relative: str, content: str | bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return relative


def test_clean_source_and_manifest_metadata_are_allowed(tmp_path: Path) -> None:
    paths = (
        _write(tmp_path, "packages/ntruth/module.py", "VALUE = 'safe'\n"),
        _write(tmp_path, "data/manifests/README.md", "Metadata only; NO_CORPUS.\n"),
    )
    report = scan_tracked_repository_v8(tmp_path, paths)
    assert report.clean is True
    assert report.findings.knowledge_state.value == "ABSENT_EXPLICIT"
    assert report.scanned_file_count == 2


def test_corpus_payload_model_weight_and_private_key_are_blocked(tmp_path: Path) -> None:
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----\nnot-a-real-key\n"
    paths = (
        _write(tmp_path, "data/raw/records.jsonl", '{"record_id":"private"}\n'),
        _write(tmp_path, "models/checkpoints/weights.safetensors", b"not-a-model"),
        _write(tmp_path, "config/signing.pem", private_key_marker),
    )
    report = scan_tracked_repository_v8(tmp_path, paths)
    kinds = {finding.kind for finding in report.findings.value or ()}
    assert RepositoryPolicyFindingKindV8.NO_CORPUS in kinds
    assert RepositoryPolicyFindingKindV8.MODEL_OR_WEIGHT in kinds
    assert RepositoryPolicyFindingKindV8.SECRET in kinds
    assert report.clean is False


def test_payload_like_pii_large_file_symlink_and_path_escape_are_blocked(tmp_path: Path) -> None:
    pii = _write(tmp_path, "data/annotations/participants.csv", "email\npatient@example.org\n")
    large = _write(tmp_path, "docs/blob.bin", b"x" * 65)
    target = tmp_path / "safe.txt"
    target.write_text("safe", encoding="utf-8")
    link = tmp_path / "linked.txt"
    link.symlink_to(target)
    report = scan_tracked_repository_v8(
        tmp_path,
        (pii, large, "linked.txt", "../outside.txt"),
        max_file_bytes=64,
    )
    kinds = {finding.kind for finding in report.findings.value or ()}
    assert RepositoryPolicyFindingKindV8.PRIVACY_RISK in kinds
    assert RepositoryPolicyFindingKindV8.LARGE_FILE in kinds
    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in kinds


def test_report_is_content_addressed_and_never_claims_external_dataset_coverage(
    tmp_path: Path,
) -> None:
    safe = _write(tmp_path, "README.md", "safe\n")
    report = scan_tracked_repository_v8(tmp_path, (safe,))
    assert report.report_id.startswith("REPOSITORY-POLICY-")
    assert report.scope == "GIT_TRACKED_TREE_ONLY"
    assert report.external_datasets_inspected is False
    assert report.detection_semantics == "NO_FINDING_DETECTED_NOT_AN_ATTESTATION"


def test_scanner_rejects_ancestor_symlink_compressed_db_weights_and_encrypted_key(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside, "outside.txt", "external bytes\n")
    (root / "link").symlink_to(outside, target_is_directory=True)
    corpus_paths = (
        _write(root, "assets/challenge.json", "{}\n"),
        _write(root, "assets/challenge.csv", "record_id\nrecord-1\n"),
        _write(root, "assets/challenge.tsv", "record_id\trecord-1\n"),
        _write(root, "assets/challenge.ndjson", "{}\n"),
        _write(root, "assets/challenge.jsonl.gz", b"not-real-gzip"),
        _write(root, "assets/challenge.zip", b"PK-not-real-archive"),
        _write(root, "assets/challenge.db", b"SQLite format 3\x00"),
    )
    model_paths = tuple(
        _write(root, f"models/weights{suffix}", b"weight")
        for suffix in (".h5", ".hdf5", ".pkl", ".joblib", ".npy", ".npz")
    )
    encrypted_key = _write(
        root,
        "docs/secret.txt",
        "-----BEGIN ENCRYPTED " + "PRIVATE KEY-----\nnot-a-real-key\n",
    )
    paths = ("link/outside.txt", *corpus_paths, *model_paths, encrypted_key)

    report = scan_tracked_repository_v8(root, paths)
    findings = report.findings.value or ()
    by_path = {path: {item.kind for item in findings if item.path == path} for path in paths}
    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in by_path["link/outside.txt"]
    for path in corpus_paths:
        assert RepositoryPolicyFindingKindV8.NO_CORPUS in by_path[path]
    for path in model_paths:
        assert RepositoryPolicyFindingKindV8.MODEL_OR_WEIGHT in by_path[path]
    assert RepositoryPolicyFindingKindV8.SECRET in by_path[encrypted_key]
    assert report.clean is False


def test_ci_policy_command_exits_nonzero_for_compressed_corpus(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    _write(root, "assets/challenge.jsonl.gz", b"not-real-gzip")
    subprocess.run(["git", "-C", str(root), "add", "assets/challenge.jsonl.gz"], check=True)
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
