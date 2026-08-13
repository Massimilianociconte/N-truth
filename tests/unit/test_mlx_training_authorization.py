from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ntruth.reality_gate import (
    GatePredicateName,
    GatePurpose,
    GateValue,
    PredicateEvidence,
    RealityGatePredicate,
    evaluate_reality_gate,
    machine_readable_result,
)
from ntruth.training.cli import DEFAULT_PROFILE, app
from ntruth.training.mlx_runtime import (
    RUN_SCHEMA_VERSION,
    MLXPipelineError,
    build_training_authorization_envelope,
    doctor,
    run_training,
)


def _predicate(name: GatePredicateName, *, evidence_basis: str) -> RealityGatePredicate:
    return RealityGatePredicate(
        name=name,
        value=GateValue.TRUE,
        evidence=PredicateEvidence(basis=evidence_basis),
    )


def _binding(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "training_view_id": "mlx-training-view-" + "1" * 20,
        "training_view_sha256": "1" * 64,
        "protected_split_seal_sha256": "2" * 64,
        "profile_sha256": "3" * 64,
        "model_repository": "mlx-community/granite-test",
        "model_revision": "revision-test",
        "source_snapshot_sha256": "4" * 64,
        "seed": 13,
    }
    value.update(updates)
    return value


def _open_training_authorization(
    path: Path,
    *,
    evidence_basis: str = "unit-test",
    binding: dict[str, object] | None = None,
) -> Path:
    predicates = tuple(
        _predicate(name, evidence_basis=evidence_basis)
        for name in (
            GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES,
            GatePredicateName.NO_BLOCKING_SCHEMA_GAPS,
            GatePredicateName.REAL_ANCHOR_AVAILABLE,
            GatePredicateName.LICENCE_SCOPE_VERIFIED,
            GatePredicateName.PROTECTED_SPLIT_FROZEN,
            GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED,
            GatePredicateName.DECISIVE_FIELDS_REVIEWED,
            GatePredicateName.REAL_BASELINE_EXECUTED,
            GatePredicateName.SYNTHETIC_FACTORY_HUMAN_CALIBRATED,
        )
    )
    result = evaluate_reality_gate(predicates, purpose=GatePurpose.SUBSTANTIVE_TRAINING)
    assert result.substantive_training_allowed is True
    path.write_text(
        json.dumps(
            build_training_authorization_envelope(result, binding=binding or _binding()),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _blocked_training_authorization(path: Path) -> Path:
    result = evaluate_reality_gate((), purpose=GatePurpose.SUBSTANTIVE_TRAINING)
    path.write_text(
        json.dumps(
            build_training_authorization_envelope(result, binding=_binding()),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _doctor_must_not_run(*args: object, **kwargs: object) -> dict[str, object]:
    raise AssertionError("doctor must not run before authorization passes")


@pytest.mark.parametrize("authorization_kind", ["missing", "blocked", "tampered"])
def test_substantive_training_rejects_invalid_authorization_before_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authorization_kind: str,
) -> None:
    monkeypatch.setattr("ntruth.training.mlx_runtime.doctor", _doctor_must_not_run)
    authorization: Path | None
    if authorization_kind == "missing":
        authorization = None
    elif authorization_kind == "blocked":
        authorization = _blocked_training_authorization(tmp_path / "blocked.json")
    else:
        authorization = _open_training_authorization(tmp_path / "tampered.json")
        payload = json.loads(authorization.read_text(encoding="utf-8"))
        payload["binding"]["seed"] = 99
        authorization.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="autorizzazione"):
        run_training(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            tmp_path / "data",
            tmp_path / "run",
            seed=13,
            training_authorization=authorization,
        )


def test_open_v7_authorization_is_still_blocked_by_training_readiness_before_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _open_training_authorization(tmp_path / "open.json")
    monkeypatch.setattr("ntruth.training.mlx_runtime.doctor", _doctor_must_not_run)

    with pytest.raises(MLXPipelineError, match=r"PRD_V9|training readiness"):
        run_training(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            tmp_path / "data",
            tmp_path / "run",
            seed=13,
            training_authorization=authorization,
        )


def test_bare_reality_gate_is_rejected_before_doctor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = evaluate_reality_gate((), purpose=GatePurpose.SUBSTANTIVE_TRAINING)
    authorization = tmp_path / "bare-gate.json"
    authorization.write_text(json.dumps(machine_readable_result(result)), encoding="utf-8")
    monkeypatch.setattr("ntruth.training.mlx_runtime.doctor", _doctor_must_not_run)

    with pytest.raises(MLXPipelineError, match=r"bare gate rifiutato"):
        run_training(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            tmp_path / "data",
            tmp_path / "run",
            seed=13,
            training_authorization=authorization,
        )


@pytest.mark.parametrize(
    ("changed_key", "changed_value"),
    [
        ("training_view_id", "mlx-training-view-wrong"),
        ("training_view_sha256", "9" * 64),
        ("protected_split_seal_sha256", "6" * 64),
        ("profile_sha256", "8" * 64),
        ("model_repository", "mlx-community/wrong-model"),
        ("model_revision", "wrong-revision"),
        ("source_snapshot_sha256", "7" * 64),
        ("seed", 99),
    ],
)
def test_training_authorization_binding_mismatch_fails_before_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_key: str,
    changed_value: object,
) -> None:
    dataset = {
        "training_view_id": "mlx-training-view-" + "1" * 20,
        "training_view_sha256": "1" * 64,
        "protected_split_seal_sha256": "2" * 64,
    }
    profile = {
        "model": {
            "repository": "mlx-community/granite-test",
            "revision": "revision-test",
        },
        "training": {"seeds": [13]},
    }
    binding = _binding()
    binding[changed_key] = changed_value
    authorization = _open_training_authorization(
        tmp_path / "binding.json",
        binding=binding,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime._assert_current_training_readiness",
        lambda _result: None,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.validate_mlx_dataset",
        lambda *_args, **_kwargs: dataset,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.load_profile_artifact",
        lambda _path: (profile, "3" * 64),
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime._source_snapshot",
        lambda _path: {"sha256": "4" * 64},
    )
    monkeypatch.setattr("ntruth.training.mlx_runtime.doctor", _doctor_must_not_run)

    with pytest.raises(MLXPipelineError, match=rf"binding.*{changed_key}"):
        run_training(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            tmp_path / "training-view",
            tmp_path / "run",
            seed=13,
            training_authorization=authorization,
        )


def test_smoke_training_can_omit_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stop_at_doctor(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("doctor reached")

    monkeypatch.setattr("ntruth.training.mlx_runtime.doctor", stop_at_doctor)
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.validate_mlx_dataset",
        lambda *_args, **_kwargs: {},
    )

    with pytest.raises(MLXPipelineError, match=r"isolamento post-validazione non FD-safe"):
        run_training(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            tmp_path / "smoke-data",
            tmp_path / "smoke-run",
            seed=13,
            smoke_test=True,
        )


def test_resume_rejects_changed_authorization_before_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _open_training_authorization(tmp_path / "original.json", evidence_basis="original")
    replacement = _open_training_authorization(
        tmp_path / "replacement.json", evidence_basis="replacement"
    )
    original_payload = json.loads(original.read_text(encoding="utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run-state.json").write_text(
        json.dumps(
            {
                "schema_version": RUN_SCHEMA_VERSION,
                "training_authorization": {
                    "artifact_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                    "envelope_checksum": original_payload["checksum"],
                    "gate_checksum": original_payload["gate"]["checksum"],
                    "gate_version": original_payload["gate"]["gate_version"],
                    "purpose": original_payload["gate"]["purpose"],
                    "binding": original_payload["binding"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("ntruth.training.mlx_runtime.doctor", _doctor_must_not_run)
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime._assert_current_training_readiness",
        lambda _result: None,
    )

    with pytest.raises(MLXPipelineError, match=r"autorizzazione.*cambiata"):
        run_training(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            tmp_path / "data",
            run_dir,
            seed=13,
            resume=True,
            training_authorization=replacement,
        )


def test_resume_is_disabled_before_dataset_or_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run-state.json").write_text(
        json.dumps({"schema_version": RUN_SCHEMA_VERSION}),
        encoding="utf-8",
    )
    monkeypatch.setattr("ntruth.training.mlx_runtime.doctor", _doctor_must_not_run)
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.validate_mlx_dataset",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("dataset must not open during blocked resume")
        ),
    )

    with pytest.raises(MLXPipelineError, match=r"resume non supportato"):
        run_training(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            tmp_path / "data",
            run_dir,
            seed=13,
            smoke_test=True,
            resume=True,
        )


def test_train_cli_propagates_training_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = tmp_path / "authorization.json"

    def fake_run_training(
        profile: Path,
        repo: Path,
        data: Path,
        out: Path,
        *,
        seed: int,
        smoke_test: bool,
        resume: bool,
        training_authorization: Path | None,
    ) -> dict[str, object]:
        return {"training_authorization": str(training_authorization)}

    monkeypatch.setattr("ntruth.training.cli.run_training", fake_run_training)
    result = CliRunner().invoke(
        app,
        [
            "train",
            str(tmp_path / "data"),
            "--out",
            str(tmp_path / "run"),
            "--training-authorization",
            str(authorization),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["training_authorization"] == str(authorization.resolve())


def test_readiness_cli_reports_not_ready_and_exits_two() -> None:
    result = CliRunner().invoke(app, ["readiness"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["overall"] == "NOT_READY"
    assert payload["substantive_training_allowed"] is False


@pytest.mark.parametrize(
    "command",
    ["tokenize", "train", "predict", "calibrate", "export-adapter"],
)
def test_blocked_mlx_commands_are_marked_unavailable_in_help(command: str) -> None:
    result = CliRunner().invoke(app, [command, "--help"])

    assert result.exit_code == 0
    assert "UNAVAILABLE" in result.stdout


def test_doctor_never_claims_training_ready_without_fd_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_path = tmp_path / "models" / "local" / "granite-4.1-3b-4bit"
    model_path.mkdir(parents=True)
    (model_path / "model.safetensors").write_bytes(b"present-for-doctor-only")
    monkeypatch.setattr("ntruth.training.mlx_runtime._memory_bytes", lambda: 32 * 1024**3)
    monkeypatch.setattr("ntruth.training.mlx_runtime._installed_version", lambda _name: "0.31.3")
    monkeypatch.setattr("ntruth.training.mlx_runtime.sys.platform", "darwin")
    monkeypatch.setattr("ntruth.training.mlx_runtime.platform.machine", lambda: "arm64")
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.shutil.disk_usage",
        lambda _path: type("Disk", (), {"free": 100 * 1024**3})(),
    )

    result = doctor(DEFAULT_PROFILE, tmp_path)

    assert result["operational_prerequisites_passed"] is True
    assert result["model"]["present"] is True
    assert result["ready_to_train"] is False
    assert result["execution_blockers"]
