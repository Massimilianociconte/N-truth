"""Cluster 2 conditions: authority hierarchy + verification ≠ re-qualification."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ntruth.model_backends.registry import (
    ModelRegistryError,
    _validate_qualification_block,
    load_public_chain,
    load_registry,
    public_chain_manifest_path,
    public_chain_path,
    public_evidence_root,
    verify_public_chain,
)


REPO = Path(__file__).resolve().parents[2]


def test_authority_docs_present() -> None:
    assert (REPO / "models/registry/AUTHORITY.md").is_file()
    text = (REPO / "models/registry/AUTHORITY.md").read_text(encoding="utf-8")
    assert "published_qualification_snapshot" in text
    assert "operational_qualification_ledger" in text
    assert "registry_mirror" in text
    assert "default registry record" in text.lower() or "not \"default model\"" in text


def test_default_json_is_registry_record_not_default_model() -> None:
    reg = load_registry()
    assert reg["factory_default_provider"] == "legacy_qwen"
    assert reg["provisional_primary_model_id"].startswith("ibm-granite/")
    assert reg["authority"]["registry_mirror"] == "default.json"
    assert "default model" not in reg["authority"]["note"].lower() or "not" in reg["authority"]["note"].lower()


def test_tip_manifest_matches_chain() -> None:
    chain = load_public_chain()
    manifest = json.loads(public_chain_manifest_path().read_text(encoding="utf-8"))
    assert manifest["tip_transition_hash"] == chain[-1]["transition_hash"]
    assert int(manifest["event_count"]) == len(chain)
    report = verify_public_chain()
    assert report["tip_transition_hash"] == manifest["tip_transition_hash"]


def test_all_public_evidence_digests_verified() -> None:
    report = verify_public_chain(verify_evidence=True)
    assert report["ok"] is True
    chain = load_public_chain()
    root = public_evidence_root()
    for entry in chain:
        digest = entry.get("evidence_sha256")
        if not digest:
            continue
        path = root / str(entry["evidence_relative_path"])
        assert path.is_file()
        actual = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
        assert actual == digest


def test_modified_evidence_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ntruth.model_backends.registry as regmod

    # Copy real evidence tree then corrupt one blob
    import shutil

    src = public_evidence_root()
    dst = tmp_path / "public_evidence"
    shutil.copytree(src, dst)
    blob = next(dst.rglob("*"))
    while blob.is_dir():
        blob = next(p for p in dst.rglob("*") if p.is_file())
    blob.write_bytes(b"tampered-evidence-content")
    monkeypatch.setattr(regmod, "public_evidence_root", lambda repo_root=None: dst)
    with pytest.raises(ModelRegistryError, match="mismatch|missing"):
        verify_public_chain(verify_evidence=True)


def test_missing_evidence_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ntruth.model_backends.registry as regmod

    empty = tmp_path / "empty_evidence"
    empty.mkdir()
    monkeypatch.setattr(regmod, "public_evidence_root", lambda repo_root=None: empty)
    with pytest.raises(ModelRegistryError, match="missing|mismatch|evidence"):
        verify_public_chain(verify_evidence=True)


def test_invalid_state_transition_rejected() -> None:
    reg = load_registry()
    bad = json.loads(json.dumps(reg["qualification"]))
    bad["scientific_validation_status"] = "EXTERNAL_VALIDATED"
    # runtime remains PARTIALLY_VERIFIED → invalid
    with pytest.raises(ModelRegistryError, match="EXTERNAL_VALIDATED|VERIFIED"):
        _validate_qualification_block(bad)


def test_no_absolute_local_paths_in_public_evidence() -> None:
    root = public_evidence_root()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "/Users/" not in text
        assert "massimiliano" not in text.lower()
        assert str(REPO) not in text


def test_verify_published_cli_semantics() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts/models/qualify_granite_runtime.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        env={**dict(**__import__("os").environ), "PYTHONPATH": str(REPO / "packages")},
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    report = json.loads(proc.stdout)
    assert report["operation"] == "VERIFY_PUBLISHED_QUALIFICATION"
    assert report["runtime_reexecuted"] is False
    assert report["new_qualification_issued"] is False
    assert report["chain_valid"] is True
    assert report["evidence_integrity_valid"] is True
    assert report["ok"] is True


def test_sequence_and_previous_hash_on_chain() -> None:
    chain = load_public_chain()
    prev = None
    for i, entry in enumerate(chain, start=1):
        assert int(entry["sequence"]) == i
        assert entry.get("previous_transition_hash") == prev
        prev = entry["transition_hash"]
