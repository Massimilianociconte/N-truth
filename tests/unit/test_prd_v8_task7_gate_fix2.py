"""Regression tests for the final PRD v8 Gate/runtime policy boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ntruth.governance.repository_policy import (
    RepositoryPolicyFindingKindV8,
    scan_tracked_repository_v8,
)
from ntruth.reality_gate.v8 import (
    RealityGateTrainingPinTupleV8,
    reconcile_training_authorization_pins_v8,
)
from ntruth.training import mlx_runtime as runtime


def _canonical_pins() -> RealityGateTrainingPinTupleV8:
    identifiers = {
        field_name: f"gate-{field_name}"
        for field_name in RealityGateTrainingPinTupleV8.model_fields
        if field_name.endswith("_id") and field_name != "schema_version"
    }
    checksums = {
        field_name: format(index, "064x")
        for index, field_name in enumerate(
            (
                field_name
                for field_name in RealityGateTrainingPinTupleV8.model_fields
                if field_name.endswith("_sha256")
            ),
            start=1,
        )
    }
    return RealityGateTrainingPinTupleV8(**identifiers, **checksums)


def test_resume_reconciliation_ignores_run_schema_but_requires_exact_prefixed_pins() -> None:
    """A generic run schema must not collide with Gate pins; bare pin aliases still fail."""

    pins = _canonical_pins()
    state: dict[str, object] = {
        "schema_version": runtime.RUN_SCHEMA_VERSION,
        **pins.state_payload(),
    }
    reconcile_training_authorization_pins_v8(state, pins)

    missing_name = "reality_gate_policy_id"
    missing = dict(state)
    missing.pop(missing_name)
    missing["policy_id"] = pins.policy_id
    with pytest.raises(ValueError, match=r"non-canonical|missing"):
        reconcile_training_authorization_pins_v8(missing, pins)


def test_resume_pin_drift_fails_before_payload_model_doctor_staging_or_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A stale canonical pin must stop resume before any sensitive runtime consumer."""

    pins = _canonical_pins()
    envelope = {
        "snapshot_id": pins.snapshot_id,
        "snapshot_sha256": pins.snapshot_sha256,
        "manifest_sha256": "a" * 64,
    }
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state: dict[str, Any] = {
        "schema_version": runtime.RUN_SCHEMA_VERSION,
        "profile_sha256": "b" * 64,
        "dataset_snapshot_sha256": pins.snapshot_sha256,
        "dataset_snapshot_id": pins.snapshot_id,
        "dataset_manifest_sha256": envelope["manifest_sha256"],
        **pins.state_payload(),
    }
    state["reality_gate_decision_sha256"] = "f" * 64
    (run_dir / "run-state.json").write_text(json.dumps(state), encoding="utf-8")

    sensitive_calls = {
        "dataset_envelope": 0,
        "lineage": 0,
        "dataset": 0,
        "profile": 0,
        "doctor": 0,
        "model": 0,
        "environment": 0,
        "profile_hash": 0,
        "stage_training": 0,
        "verify_stage": 0,
        "stage_validation": 0,
        "subprocess": 0,
    }

    def touched(name: str, result: Any) -> Any:
        sensitive_calls[name] += 1
        return result

    profile = {
        "training": {
            "seeds": [13],
            "maximum_phases": 1,
            "iterations_per_phase": 1,
            "early_stopping_patience": 1,
            "early_stopping_min_delta": 0.0,
        }
    }
    monkeypatch.setattr(
        runtime,
        "resolve_training_lineage_inputs",
        lambda **_kwargs: touched("lineage", SimpleNamespace(state_payload=lambda: {})),
    )
    monkeypatch.setattr(
        runtime,
        "read_training_snapshot_envelope",
        lambda *_a, **_k: touched("dataset_envelope", envelope),
    )
    monkeypatch.setattr(runtime, "verify_training_reality_gate_v8", lambda *_a, **_k: pins)
    monkeypatch.setattr(
        runtime,
        "validate_mlx_dataset",
        lambda *_a, **_k: touched(
            "dataset",
            {
                "manifest_sha256": envelope["manifest_sha256"],
                "snapshot_sha256": pins.snapshot_sha256,
                "snapshot_id": pins.snapshot_id,
            },
        ),
    )
    monkeypatch.setattr(runtime, "load_profile", lambda *_a: touched("profile", profile))
    monkeypatch.setattr(
        runtime,
        "doctor",
        lambda *_a: touched("doctor", {"ready_to_train": True, "checks": {}}),
    )
    monkeypatch.setattr(
        runtime,
        "verify_model",
        lambda *_a: touched("model", {"provenance_sha256": "c" * 64}),
    )
    monkeypatch.setattr(
        runtime,
        "runtime_environment",
        lambda *_a: touched(
            "environment",
            {"uv_lock_sha256": "d" * 64, "source_snapshot_sha256": "e" * 64},
        ),
    )
    monkeypatch.setattr(runtime, "_model_path", lambda *_a: touched("model", tmp_path))
    monkeypatch.setattr(
        runtime,
        "sha256_file",
        lambda *_a, **_k: touched("profile_hash", "b" * 64),
    )
    monkeypatch.setattr(
        runtime,
        "stage_verified_training_view",
        lambda *_a, **_k: touched("stage_training", {"path": str(tmp_path), "file_hashes": {}}),
    )
    monkeypatch.setattr(
        runtime,
        "verify_staged_training_view",
        lambda *_a, **_k: touched("verify_stage", {}),
    )
    monkeypatch.setattr(
        runtime,
        "stage_validation_consumer_view",
        lambda *_a, **_k: touched("stage_validation", {"path": str(tmp_path)}),
    )
    monkeypatch.setattr(
        runtime,
        "_stream_command",
        lambda *_a, **_k: touched("subprocess", None),
    )

    with pytest.raises(runtime.MLXPipelineError, match=r"Reality Gate.*pin.*changed"):
        runtime.run_training(
            tmp_path / "profile.json",
            tmp_path,
            tmp_path / "data",
            run_dir,
            seed=13,
            reality_gate=object(),  # type: ignore[arg-type]
            design_lineage_pins=None,
            design_lineage_artifact_path=None,
            protected_source_manifest_path=None,
            resume=True,
        )

    assert sensitive_calls == {name: 0 for name in sensitive_calls}


def _write(root: Path, relative: str, payload: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return relative


@pytest.mark.parametrize(
    "relative",
    (
        "artifacts/payload.tgz",
        "artifacts/payload.rar",
        "artifacts/payload.zst",
        "artifacts/payload.duckdb",
        "artifacts/payload.mdb",
    ),
)
def test_repository_policy_blocks_additional_archive_and_database_suffixes(
    relative: str,
    tmp_path: Path,
) -> None:
    tracked = _write(tmp_path, relative, b"synthetic-placeholder")
    report = scan_tracked_repository_v8(tmp_path, (tracked,))
    assert {
        finding.kind for finding in report.findings.value or () if finding.path == relative
    } >= {RepositoryPolicyFindingKindV8.NO_CORPUS}


@pytest.mark.parametrize(
    ("relative", "magic"),
    (
        ("docs/gzip.txt", b"\x1f\x8b\x08\x00"),
        ("docs/bzip.txt", b"BZh9"),
        ("docs/zstd.txt", b"\x28\xb5\x2f\xfd"),
        ("docs/zip.txt", b"PK\x03\x04"),
        ("docs/rar.txt", b"Rar!\x1a\x07\x00"),
        ("docs/xz.txt", b"\xfd7zXZ\x00"),
        ("docs/7zip.txt", b"7z\xbc\xaf'\x1c"),
    ),
)
def test_repository_policy_blocks_compressed_magic_under_benign_suffix(
    relative: str,
    magic: bytes,
    tmp_path: Path,
) -> None:
    tracked = _write(tmp_path, relative, magic + b"synthetic-placeholder")
    report = scan_tracked_repository_v8(tmp_path, (tracked,))
    assert {
        finding.kind for finding in report.findings.value or () if finding.path == relative
    } >= {RepositoryPolicyFindingKindV8.NO_CORPUS}


def test_ci_policy_command_fails_for_new_suffixes_and_renamed_compressed_magic(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    tracked = (
        _write(root, "artifacts/challenge.tgz", b"placeholder"),
        _write(root, "artifacts/cache.duckdb", b"placeholder"),
        _write(root, "docs/innocent.txt", b"BZh9placeholder"),
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
    finding_paths = {finding["path"] for finding in json.loads(result.stdout)["findings"]["value"]}
    assert finding_paths >= set(tracked)
