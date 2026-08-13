from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput, ParserAIOutput
from ntruth.training import (
    AnnotationStatus,
    SupervisedRecord,
    SupervisionProvenance,
    prepare_dataset,
)
from ntruth.training.blind_evaluation import (
    PROTECTED_EVALUATION_BLOCKER,
    freeze_training_view,
    validate_training_view,
)
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.mlx_inference import (
    _verify_evaluation_snapshot,
    predict_and_score,
    tokenize_report,
)
from ntruth.training.mlx_runtime import CommandResult, MLXPipelineError, run_training


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _target() -> dict[str, object]:
    return ParserAIOutput.model_validate(
        {
            "contract_version": "2.0.0",
            "experiment_blocks": [],
            "evidence_spans": [],
            "candidate_nodes": [],
            "candidate_edges": [],
            "factors": [],
            "endpoints": [],
            "contrasts": [],
            "candidate_estimands": [],
            "determinability": {
                "status": "INDETERMINATE",
                "rationale": "No decisive evidence.",
                "confidence": 0.5,
                "evidence_ids": [],
            },
            "alternatives": [],
            "clarification_questions": [],
            "model_metadata": {
                "adapter_name": "blind-view-test",
                "model_name": "annotation",
                "model_version": "1",
                "model_checksum": None,
                "prompt_template_version": "blind-view-test",
                "contract_version": "2.0.0",
                "local_execution": True,
            },
        }
    ).model_dump(mode="json")


def _record(record_id: str, split: CorpusSplit) -> SupervisedRecord:
    parser_input = ParserAIInput(
        metadata={"record": record_id},
        domain_hint="blind_view_test",
        language="en",
    )
    return SupervisedRecord(
        record_id=record_id,
        task="parser_ai_v2",
        language="en",
        domain="blind_view_test",
        input_text=parser_input.model_dump_json(),
        target=_target(),
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=_sha(f"source:{record_id}"),
            governance_hash=_sha(f"governance:{record_id}"),
            license_or_authorization_id=f"license-{record_id}",
            guideline_version="blind-view-test",
            reviewer_count=2,
            reviewer_roles=("wet-lab", "biostatistician"),
        ),
        annotation_status=AnnotationStatus.DOUBLE_REVIEWED,
        training_eligible=True,
        requested_split=split,
    )


def _custody_snapshot(path: Path) -> Path:
    dataset = prepare_dataset(
        (
            _record("train-secret", CorpusSplit.TRAIN),
            _record("valid-secret", CorpusSplit.VALIDATION),
            _record("test-protected-secret", CorpusSplit.TEST),
            _record("external-protected-secret", CorpusSplit.EXTERNAL),
        )
    )
    export_mlx_dataset(dataset, path)
    return path


def test_freeze_creates_physically_isolated_training_view(tmp_path: Path) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"

    result = freeze_training_view(custody, view)
    validated = validate_training_view(view)

    assert {path.name for path in view.iterdir()} == {
        "train.jsonl",
        "valid.jsonl",
        "training-records.jsonl",
        "training-view-manifest.json",
        "protected-split-seal.json",
    }
    serialized = b"".join(path.read_bytes() for path in sorted(view.iterdir()))
    assert b"test-protected-secret" not in serialized
    assert b"external-protected-secret" not in serialized
    assert b"test.jsonl" not in serialized
    assert b"external.jsonl" not in serialized
    assert result["training_view_id"] == validated["training_view_id"]
    assert validated["counts"] == {"train": 1, "valid": 1}


@pytest.mark.parametrize("mutated_filename", ["prepared-records.jsonl", "test.jsonl"])
def test_freeze_rejects_custody_mutation_between_validation_and_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutated_filename: str,
) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"
    from ntruth.training import mlx_runtime

    real_validate = mlx_runtime.validate_snapshot_integrity

    def validate_then_mutate(path: Path, **kwargs: object) -> dict[str, object]:
        result = real_validate(path, **kwargs)
        target = custody / mutated_filename
        target.write_bytes(target.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(mlx_runtime, "validate_snapshot_integrity", validate_then_mutate)

    with pytest.raises(
        MLXPipelineError,
        match=rf"custody input cambiato.*{mutated_filename}",
    ):
        freeze_training_view(custody, view)

    assert not view.exists()


def test_validation_never_hashes_or_opens_protected_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"
    freeze_training_view(custody, view)
    observed: list[str] = []

    from ntruth.training import mlx_runtime

    real_sha256_file = mlx_runtime.sha256_file

    def observed_hash(path: Path, **kwargs: object) -> str:
        observed.append(path.name)
        assert path.name not in {"test.jsonl", "external.jsonl", "prepared-records.jsonl"}
        return real_sha256_file(path, **kwargs)

    monkeypatch.setattr(mlx_runtime, "sha256_file", observed_hash)

    validate_training_view(view)

    assert set(observed) <= {
        "train.jsonl",
        "valid.jsonl",
        "training-records.jsonl",
        "training-view-manifest.json",
        "protected-split-seal.json",
    }


def test_tokenization_reads_only_train_and_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"
    freeze_training_view(custody, view)
    from ntruth.training import mlx_inference

    monkeypatch.setattr(
        mlx_inference,
        "_verify_best_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model must not open")),
    )

    with pytest.raises(
        MLXPipelineError,
        match=r"isolamento post-validazione non FD-safe|esecuzione scientifica chiusa",
    ):
        tokenize_report(
            tmp_path / "profile.json",
            Path("."),
            view,
            tmp_path / "token-report.json",
        )


def test_training_and_reports_cannot_mutate_training_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"
    freeze_training_view(custody, view)
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime._load_training_authorization",
        lambda _path: {"gate_checksum": "1" * 64},
    )

    with pytest.raises(MLXPipelineError, match=r"directory run.*training view"):
        run_training(
            Path("profile.json"),
            Path("."),
            view,
            view / "run",
            seed=13,
            training_authorization=tmp_path / "authorization.json",
        )

    with pytest.raises(MLXPipelineError, match=r"report token.*training view"):
        tokenize_report(
            Path("profile.json"),
            Path("."),
            view,
            view / "token-report.json",
        )


def test_training_view_rejects_mixed_or_symlinked_protected_payload(tmp_path: Path) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"
    freeze_training_view(custody, view)
    (view / "test.jsonl").symlink_to(custody / "test.jsonl")

    with pytest.raises(MLXPipelineError, match=r"file inattesi.*test.jsonl"):
        validate_training_view(view)


def test_substantive_training_rejects_mixed_snapshot_before_doctor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime._load_training_authorization",
        lambda _path: {"gate_checksum": "1" * 64},
    )

    def forbidden_doctor(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("doctor must not run for a mixed custody snapshot")

    monkeypatch.setattr("ntruth.training.mlx_runtime.doctor", forbidden_doctor)

    with pytest.raises(MLXPipelineError, match=r"training view|snapshot misto"):
        run_training(
            Path("models/configs/granite-4.1-3b-mlx-qlora.json"),
            Path(".").resolve(),
            custody,
            tmp_path / "run",
            seed=13,
            training_authorization=tmp_path / "authorization.json",
        )


def test_training_fails_closed_before_mlx_receives_any_dataset_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"
    freeze_training_view(custody, view)
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        Path("models/configs/granite-4.1-3b-mlx-qlora.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    captured_data_paths: list[str] = []

    profile = {
        "data": {"max_sequence_length": 512},
        "training": {
            "seeds": [13],
            "maximum_phases": 1,
            "iterations_per_phase": 1,
            "early_stopping_patience": 1,
            "early_stopping_min_delta": 0.0,
            "fine_tune_type": "lora",
            "optimizer": "adam",
            "num_layers": 1,
            "batch_size": 1,
            "validation_batches": 1,
            "learning_rate": 0.0001,
            "gradient_accumulation_steps": 1,
            "gradient_checkpointing": True,
            "mask_prompt": True,
            "lora_parameters": {"rank": 1},
            "maximum_observed_peak_memory_gib": 18.0,
            "keep_checkpoints": 1,
        },
    }
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime._load_training_authorization",
        lambda _path: {"gate_checksum": "1" * 64},
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.load_profile_artifact",
        lambda _path: (profile, "5" * 64),
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime._assert_training_authorization_binding",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.doctor", lambda *_args: {"ready_to_train": True}
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.verify_model",
        lambda *_args: {"provenance_sha256": "2" * 64},
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime.runtime_environment",
        lambda _repo: {"uv_lock_sha256": "3" * 64, "source_snapshot_sha256": "4" * 64},
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_runtime._model_path", lambda *_args: tmp_path / "model"
    )

    def fake_stream(
        command: list[str], *, cwd: Path, log_path: Path, environment: object
    ) -> CommandResult:
        del command, cwd, environment
        if log_path.name == "train.log":
            config_path = tmp_path / "run" / "configs" / "phase-0001.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            captured_data_paths.append(config["data"])
            adapter = Path(config["adapter_path"])
            adapter.mkdir(parents=True, exist_ok=True)
            (adapter / "adapters.safetensors").write_bytes(b"adapter")
            output = "Peak memory 1.0 GB"
        else:
            config_path = tmp_path / "run" / "configs" / "phase-0001-eval.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            captured_data_paths.append(config["data"])
            output = "Test loss 1.0"
        return CommandResult(tuple(), 0, output, 0.01, 1.0)

    monkeypatch.setattr("ntruth.training.mlx_runtime._stream_command", fake_stream)

    with pytest.raises(
        MLXPipelineError,
        match=r"isolamento post-validazione non FD-safe|esecuzione scientifica chiusa",
    ):
        run_training(
            profile_path,
            Path(".").resolve(),
            view,
            tmp_path / "run",
            seed=13,
            training_authorization=tmp_path / "authorization.json",
        )

    assert captured_data_paths == []


@pytest.mark.parametrize("declared_split", ["test", "external"])
def test_generic_prediction_fails_closed_for_protected_splits_before_run_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    declared_split: str,
) -> None:
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_best_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("run must not open")),
    )

    with pytest.raises(MLXPipelineError, match=PROTECTED_EVALUATION_BLOCKER):
        predict_and_score(
            Path("profile.json"),
            Path("."),
            tmp_path / f"{declared_split}.jsonl",
            tmp_path / "adapter",
            tmp_path / "out",
            declared_split=declared_split,
        )


def test_validation_snapshot_uses_training_view_without_custody_access(tmp_path: Path) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"
    frozen = freeze_training_view(custody, view)
    run_lineage = {
        "smoke_test": False,
        "run_dataset_snapshot_id": frozen["training_view_id"],
        "run_dataset_snapshot_sha256": frozen["training_view_sha256"],
        "run_dataset_manifest_sha256": frozen["manifest_sha256"],
    }

    path, snapshot = _verify_evaluation_snapshot(
        view / "valid.jsonl",
        "validation",
        run_lineage,
    )

    assert path == (view / "valid.jsonl").resolve()
    assert snapshot["counts"] == {"train": 1, "valid": 1}


def test_validation_rejects_mixed_custody_before_model_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_best_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model verification must not run for mixed custody")
        ),
    )

    with pytest.raises(MLXPipelineError, match="snapshot misto"):
        predict_and_score(
            Path("profile.json"),
            Path("."),
            custody / "valid.jsonl",
            tmp_path / "adapter",
            tmp_path / "out",
            declared_split="validation",
        )


def test_validation_mutation_after_snapshot_validation_fails_before_model_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody = _custody_snapshot(tmp_path / "custody")
    view = tmp_path / "training-view"
    freeze_training_view(custody, view)
    from ntruth.training import mlx_inference

    real_validate = mlx_inference.validate_mlx_dataset

    def validate_then_mutate(path: Path, **kwargs: object) -> dict[str, object]:
        result = real_validate(path, **kwargs)
        valid_path = view / "valid.jsonl"
        valid_path.write_bytes(valid_path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(mlx_inference, "validate_mlx_dataset", validate_then_mutate)
    monkeypatch.setattr(
        mlx_inference,
        "_verify_best_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model/run access must follow verified ownership")
        ),
    )

    with pytest.raises(
        MLXPipelineError,
        match=r"isolamento post-validazione non FD-safe|esecuzione scientifica chiusa|bytes cambiati dopo la validazione",
    ):
        predict_and_score(
            Path("profile.json"),
            Path("."),
            view / "valid.jsonl",
            tmp_path / "run" / "best",
            tmp_path / "out",
            declared_split="validation",
        )
