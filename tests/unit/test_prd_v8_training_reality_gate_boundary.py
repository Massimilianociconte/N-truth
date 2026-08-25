from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import ntruth.training.mlx_runtime as runtime
from ntruth.training.records import AnnotationStatus, DatasetManifest, ManifestRecord


@dataclass
class _FakeGate:
    artifact: object

    def authorize_training(self, _request: object) -> object:
        return self.artifact


def _artifact(*, snapshot_id: str = "snapshot-current") -> object:
    return runtime.build_training_reality_gate_v8_artifact(
        snapshot_id=snapshot_id,
        snapshot_sha256="a" * 64,
        privacy_attestation_sha256="b" * 64,
        no_corpus_attestation_sha256="c" * 64,
        authorized=True,
        issued_by="fake-test-gate",
    )


def _write_training_lineage_inputs(
    tmp_path: Path,
) -> tuple[runtime.TrainingDesignLineagePins, Path, Path]:
    pins = runtime.TrainingDesignLineagePins(
        planned_design_artifact_id="planned-1",
        planned_design_artifact_sha256="d" * 64,
        executed_design_artifact_id="executed-1",
        executed_design_artifact_sha256="e" * 64,
    )
    pins_path = tmp_path / "task6-training-design-lineage.json"
    pins_path.write_text(json.dumps(pins.model_dump(mode="json"), sort_keys=True), encoding="utf-8")
    source = DatasetManifest(
        record_schema_version="8.0.0",
        normalization_version="1.0.0",
        config_checksum="1" * 64,
        decisions_checksum="2" * 64,
        report_checksum="3" * 64,
        records=(
            ManifestRecord(
                record_id="protected-1",
                record_checksum="4" * 64,
                input_checksum="5" * 64,
                candidate_target_checksum="6" * 64,
                exact_fingerprint="7" * 64,
                near_fingerprint="8" * 64,
                split="TEST",
                leakage_group_id="protected-group-1",
                source_id="protected-source-1",
                source_asset_id="protected-asset-1",
                source_sha256="9" * 64,
                governance_hash="a" * 64,
                annotation_status=AnnotationStatus.CANDIDATE,
                training_eligible=False,
                evaluation_eligible=True,
                release_eligible=True,
                model_selection_eligible=False,
                reviewer_count=0,
            ),
        ),
    )
    source_path = tmp_path / "protected-source-dataset-manifest.json"
    source_path.write_text(
        json.dumps(source.model_dump(mode="json"), sort_keys=True), encoding="utf-8"
    )
    return pins, pins_path, source_path


def test_gate_artifact_is_content_addressed_and_tamper_rejected() -> None:
    artifact = _artifact()
    payload = artifact.model_dump(mode="json")
    payload["privacy_attestation_sha256"] = "d" * 64

    with pytest.raises(ValueError, match="artifact checksum"):
        runtime.TrainingRealityGateV8Artifact.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("gate_version", "7.0.0", "v8"),
        ("purpose", "EVALUATE", "TRAIN"),
        ("snapshot_id", "snapshot-stale", "stale"),
        ("artifact_sha256", "f" * 64, "checksum"),
    ),
)
def test_wrong_stale_or_hash_mismatched_gate_fails_closed(
    field: str, value: str, message: str
) -> None:
    payload = (
        _artifact(snapshot_id=value).model_dump(mode="json")
        if field == "snapshot_id"
        else _artifact().model_dump(mode="json")
    )
    if field != "snapshot_id":
        payload[field] = value
    gate = _FakeGate(payload)
    request = runtime.TrainingRealityGateV8Request(
        snapshot_id="snapshot-current",
        snapshot_sha256="a" * 64,
    )

    with pytest.raises(runtime.MLXPipelineError, match=message):
        runtime.verify_training_reality_gate_v8(gate, request)


def test_run_training_rejects_stale_gate_before_any_command_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    design_pins, design_path, protected_source_path = _write_training_lineage_inputs(tmp_path)
    command_calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        runtime,
        "read_training_snapshot_envelope",
        lambda *_args, **_kwargs: {
            "snapshot_id": "snapshot-current",
            "snapshot_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(
        runtime,
        "_stream_command",
        lambda *args, **kwargs: command_calls.append((args, kwargs)),
    )

    with pytest.raises(runtime.MLXPipelineError, match="stale"):
        runtime.run_training(
            tmp_path / "missing-profile.json",
            tmp_path,
            tmp_path / "data",
            tmp_path / "run",
            seed=13,
            reality_gate=_FakeGate(_artifact(snapshot_id="snapshot-stale")),
            design_lineage_pins=design_pins,
            design_lineage_artifact_path=design_path,
            protected_source_manifest_path=protected_source_path,
        )

    assert command_calls == []
