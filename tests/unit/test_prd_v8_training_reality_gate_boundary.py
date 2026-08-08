from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import ntruth.training.mlx_runtime as runtime


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
        )

    assert command_calls == []
