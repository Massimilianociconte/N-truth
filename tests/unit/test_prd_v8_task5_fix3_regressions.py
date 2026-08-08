from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any

import pytest

import ntruth.training.cli as training_cli
import ntruth.training.mlx_inference as inference
import ntruth.training.mlx_runtime as runtime
from ntruth.governance.lineage import CorpusSplit
from ntruth.schemas.core import content_checksum
from ntruth.training.mlx_dataset import create_runtime_smoke_dataset
from ntruth.training.records import AnnotationStatus, DatasetManifest, ManifestRecord


def _source_manifest(*, record_ids: tuple[str, ...] = ("protected-1",)) -> DatasetManifest:
    return DatasetManifest(
        record_schema_version="8.0.0",
        normalization_version="1.0.0",
        config_checksum="1" * 64,
        decisions_checksum="2" * 64,
        report_checksum="3" * 64,
        records=tuple(
            ManifestRecord(
                record_id=record_id,
                record_checksum="4" * 64,
                input_checksum="5" * 64,
                candidate_target_checksum="6" * 64,
                exact_fingerprint="7" * 64,
                near_fingerprint="8" * 64,
                split=CorpusSplit.TEST,
                leakage_group_id=f"group-{record_id}",
                source_id="source-1",
                source_asset_id=record_id,
                source_sha256="9" * 64,
                governance_hash="a" * 64,
                annotation_status=AnnotationStatus.CANDIDATE,
                training_eligible=False,
                evaluation_eligible=True,
                release_eligible=True,
                model_selection_eligible=False,
                reviewer_count=0,
            )
            for record_id in record_ids
        ),
    )


def _write_source_manifest(
    path: Path, *, record_ids: tuple[str, ...] = ("protected-1",)
) -> DatasetManifest:
    manifest = _source_manifest(record_ids=record_ids)
    path.write_text(json.dumps(manifest.model_dump(mode="json"), sort_keys=True), encoding="utf-8")
    return manifest


def _write_design_pins(path: Path) -> Any:
    pins_type = getattr(runtime, "TrainingDesignLineagePins", None)
    assert pins_type is not None, "Task 5 requires the opaque Task 6 design-pin type"
    pins = pins_type(
        planned_design_artifact_id="planned-1",
        planned_design_artifact_sha256="b" * 64,
        executed_design_artifact_id="executed-1",
        executed_design_artifact_sha256="c" * 64,
    )
    path.write_text(json.dumps(pins.model_dump(mode="json"), sort_keys=True), encoding="utf-8")
    return pins


def test_training_and_cli_require_typed_design_and_protected_source_inputs() -> None:
    runtime_parameters = inspect.signature(runtime.run_training).parameters
    cli_parameters = inspect.signature(training_cli.train).parameters
    for name in (
        "design_lineage_pins",
        "design_lineage_artifact_path",
        "protected_source_manifest_path",
    ):
        assert name in runtime_parameters
        assert runtime_parameters[name].default is inspect.Parameter.empty
    assert cli_parameters["design_lineage_v8"].default.default is ...
    assert cli_parameters["protected_source_manifest"].default.default is ...


def test_missing_design_lineage_fails_typed_before_any_snapshot_or_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = getattr(runtime, "TrainingLineageReviewRequired", None)
    assert blocker is not None
    reached: list[str] = []
    monkeypatch.setattr(
        runtime,
        "read_training_snapshot_envelope",
        lambda *_a, **_k: reached.append("snapshot"),
    )
    with pytest.raises(blocker, match="SCIENTIFIC_REVIEW_REQUIRED"):
        runtime.run_training(
            tmp_path / "profile.json",
            tmp_path,
            tmp_path / "data",
            tmp_path / "run",
            seed=13,
            reality_gate=object(),  # type: ignore[arg-type]
            design_lineage_pins=None,  # type: ignore[arg-type]
            design_lineage_artifact_path=None,  # type: ignore[arg-type]
            protected_source_manifest_path=None,  # type: ignore[arg-type]
        )
    assert reached == []


def test_typed_lineage_is_persistable_and_resume_reconciles_every_pin(tmp_path: Path) -> None:
    design_path = tmp_path / "task6-design-lineage.json"
    source_path = tmp_path / "source-dataset-manifest.json"
    design = _write_design_pins(design_path)
    source = _write_source_manifest(source_path)
    resolver = getattr(runtime, "resolve_training_lineage_inputs", None)
    reconciler = getattr(runtime, "reconcile_training_lineage_pins", None)
    assert callable(resolver) and callable(reconciler)
    resolved = resolver(
        design_lineage_pins=design,
        design_lineage_artifact_path=design_path,
        protected_source_manifest_path=source_path,
    )
    state = resolved.state_payload()
    assert state["planned_design_artifact_id"] == "planned-1"
    assert state["executed_design_artifact_id"] == "executed-1"
    assert state["protected_source_manifest_id"] == source.dataset_id
    assert state["protected_source_manifest_sha256"] == runtime.sha256_file(source_path)
    reconciler(state, resolved)
    for field in (
        "planned_design_artifact_sha256",
        "executed_design_artifact_sha256",
        "protected_source_manifest_id",
        "protected_source_manifest_sha256",
        "protected_source_manifest_path",
    ):
        mutated = dict(state)
        mutated[field] = "f" * 64
        with pytest.raises(runtime.MLXPipelineError, match=field):
            reconciler(mutated, resolved)


def test_best_run_surfaces_persisted_design_and_protected_source_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    design_path = tmp_path / "task6-design-lineage.json"
    source_path = tmp_path / "source-dataset-manifest.json"
    design = _write_design_pins(design_path)
    _write_source_manifest(source_path)
    resolved = runtime.resolve_training_lineage_inputs(
        design_lineage_pins=design,
        design_lineage_artifact_path=design_path,
        protected_source_manifest_path=source_path,
    )
    profile = tmp_path / "profile.json"
    profile.write_text("{}\n", encoding="utf-8")
    run = tmp_path / "run"
    best = run / "best"
    best.mkdir(parents=True)
    adapter = best / "adapters.safetensors"
    adapter.write_bytes(b"adapter")
    state = {
        "schema_version": "8.0.0",
        "status": "completed_maximum_phases",
        "profile_sha256": runtime.sha256_file(profile),
        "model_provenance_sha256": "d" * 64,
        "best_phase": 1,
        "last_completed_phase": 1,
        "best_adapter_sha256": runtime.sha256_file(adapter),
        "best_adapter_config_sha256": None,
        "dataset_snapshot_id": "training-1",
        "dataset_snapshot_sha256": "e" * 64,
        "dataset_manifest_sha256": "f" * 64,
        "smoke_test": False,
        **resolved.state_payload(),
    }
    (run / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(
        inference,
        "verify_model",
        lambda *_a, **_k: {"provenance_sha256": "d" * 64},
    )
    lineage = inference._verify_best_run(profile, tmp_path, run)
    assert lineage["planned_design_artifact_id"] == "planned-1"
    assert lineage["executed_design_artifact_id"] == "executed-1"
    assert lineage["protected_source_manifest_id"] == resolved.protected_source_manifest_id
    assert lineage["protected_source_manifest_sha256"] == runtime.sha256_file(source_path)
    assert lineage["protected_source_manifest_path"] == str(source_path.resolve())


def test_predict_and_score_test_uses_real_sealed_run_and_protected_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ntruth.training.protected_evaluation import ProtectedEvaluationSnapshotManifest

    design_path = tmp_path / "task6-design-lineage.json"
    source_path = tmp_path / "source-dataset-manifest.json"
    design = _write_design_pins(design_path)
    source = _write_source_manifest(source_path)
    resolved = runtime.resolve_training_lineage_inputs(
        design_lineage_pins=design,
        design_lineage_artifact_path=design_path,
        protected_source_manifest_path=source_path,
    )

    protected_dir = tmp_path / "protected-test"
    protected_dir.mkdir()
    payload = protected_dir / "test.jsonl"
    payload.write_text('{"record_id":"protected-1"}\n', encoding="utf-8")
    protected_manifest = ProtectedEvaluationSnapshotManifest(
        split="TEST",
        purpose="CUSTODIAL_EVALUATION",
        payload_file="test.jsonl",
        payload_sha256=runtime.sha256_file(payload),
        payload_size_bytes=payload.stat().st_size,
        record_count=1,
        record_ids_checksum=("e19fb8e28174c0999f801fbe618e3db0820dab93acb1eb0877db6f40f8cdf50d"),
        lineage={
            "source_manifest_id": source.dataset_id,
            "source_manifest_sha256": runtime.sha256_file(source_path),
            "planned_design_artifact_id": design.planned_design_artifact_id,
            "planned_design_artifact_sha256": design.planned_design_artifact_sha256,
            "executed_design_artifact_id": design.executed_design_artifact_id,
            "executed_design_artifact_sha256": design.executed_design_artifact_sha256,
            "custody_reference_id": "custody-1",
            "custody_reference_sha256": "d" * 64,
        },
    )
    (protected_dir / "protected-evaluation-manifest.json").write_text(
        json.dumps(protected_manifest.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )

    run = tmp_path / "run"
    best = run / "best"
    best.mkdir(parents=True)
    adapter = best / "adapters.safetensors"
    adapter.write_bytes(b"adapter")
    state = {
        "schema_version": "8.0.0",
        "status": "completed_maximum_phases",
        "profile_sha256": runtime.sha256_file(training_cli.DEFAULT_PROFILE),
        "model_provenance_sha256": "e" * 64,
        "best_phase": 1,
        "last_completed_phase": 1,
        "best_adapter_sha256": runtime.sha256_file(adapter),
        "dataset_snapshot_id": "training-1",
        "dataset_snapshot_sha256": "f" * 64,
        "dataset_manifest_sha256": "0" * 64,
        "smoke_test": False,
        **resolved.state_payload(),
    }
    (run / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(
        inference,
        "verify_model",
        lambda *_a, **_k: {"provenance_sha256": "e" * 64},
    )

    verified: dict[str, Any] = {}
    real_verify = inference._verify_evaluation_snapshot

    class ProtectedBoundaryReached(RuntimeError):
        pass

    def stop_after_real_protected_verification(
        evaluation_jsonl: Path,
        declared_split: str,
        run_lineage: dict[str, Any],
    ) -> tuple[Path, dict[str, Any]]:
        resolved_path, snapshot = real_verify(evaluation_jsonl, declared_split, run_lineage)
        verified["path"] = resolved_path
        verified["snapshot"] = snapshot
        verified["run_lineage"] = run_lineage
        raise ProtectedBoundaryReached

    monkeypatch.setattr(
        inference,
        "_verify_evaluation_snapshot",
        stop_after_real_protected_verification,
    )
    with pytest.raises(ProtectedBoundaryReached):
        inference.predict_and_score(
            training_cli.DEFAULT_PROFILE,
            tmp_path,
            payload,
            best,
            tmp_path / "predictions",
            declared_split="test",
        )
    assert verified["path"] == payload.resolve()
    assert verified["snapshot"]["source_dataset_manifest"]["dataset_id"] == source.dataset_id
    assert verified["run_lineage"]["protected_source_manifest_sha256"] == runtime.sha256_file(
        source_path
    )
    assert not (tmp_path / "predictions").exists()


def test_release_recomputes_exact_test_membership_from_source_manifest() -> None:
    source = _source_manifest(record_ids=("source-only",))
    protected = {
        "split": "TEST",
        "snapshot_id": "protected-1",
        "snapshot_sha256": "a" * 64,
        "record_count": 1,
        "record_ids_checksum": content_checksum(["payload-only"]),
        "lineage": {
            "source_manifest_id": source.dataset_id,
            "source_manifest_sha256": "b" * 64,
            "planned_design_artifact_id": "planned-1",
            "planned_design_artifact_sha256": "c" * 64,
            "executed_design_artifact_id": "executed-1",
            "executed_design_artifact_sha256": "d" * 64,
        },
    }
    snapshot = {
        "snapshot_id": "protected-1",
        "snapshot_sha256": "a" * 64,
        "protected_evaluation": protected,
        "source_dataset_manifest": source.model_dump(mode="json"),
    }
    run = {
        "run_dataset_snapshot_sha256": "e" * 64,
        "planned_design_artifact_id": "planned-1",
        "planned_design_artifact_sha256": "c" * 64,
        "executed_design_artifact_id": "executed-1",
        "executed_design_artifact_sha256": "d" * 64,
    }
    with pytest.raises(runtime.MLXPipelineError, match=r"membership|record"):
        inference.validate_protected_release_lineage(
            metrics_snapshot=snapshot,
            calibration_snapshot={"snapshot_sha256": "e" * 64},
            run_lineage=run,
        )


def _staged_training_view(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    source = tmp_path / "source"
    create_runtime_smoke_dataset(source)
    verified = runtime.validate_snapshot_integrity(source, smoke_test=True)
    staged = runtime.stage_verified_training_view(
        source,
        tmp_path / "training-view",
        verified_snapshot=verified,
        smoke_test=True,
    )
    return Path(str(staged["path"])), staged


def test_validation_as_test_view_is_content_addressed_exact_and_read_only(tmp_path: Path) -> None:
    training_dir, training_view = _staged_training_view(tmp_path)
    stage = getattr(runtime, "stage_validation_consumer_view", None)
    assert callable(stage)
    view = stage(
        training_dir,
        tmp_path / "validation-view",
        training_view=training_view,
    )
    root = Path(str(view["path"]))
    assert {item.name for item in root.iterdir()} == {
        "test.jsonl",
        "consumer-view-manifest.json",
    }
    manifest = json.loads((root / "consumer-view-manifest.json").read_text(encoding="utf-8"))
    assert manifest["view_id"] == view["view_id"]
    assert manifest["view_sha256"] == view["view_sha256"]
    assert manifest["payload_sha256"] == view["file_hashes"]["test.jsonl"]
    assert root.stat().st_mode & 0o222 == 0
    assert all(item.stat().st_mode & 0o222 == 0 for item in root.iterdir())


@pytest.mark.parametrize("mutation", ("replace", "symlink", "extra", "protected"))
def test_validation_consumer_blocks_every_mutation_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    training_dir, training_view = _staged_training_view(tmp_path)
    validation = runtime.stage_validation_consumer_view(
        training_dir,
        tmp_path / "validation-view",
        training_view=training_view,
    )
    root = Path(str(validation["path"]))
    root.chmod(0o755)
    payload = root / "test.jsonl"
    payload.chmod(0o644)
    if mutation in {"replace", "protected"}:
        replacement = root / "replacement.jsonl"
        replacement.write_text(
            "PROTECTED-TEST-CONTENT\n" if mutation == "protected" else "{}\n",
            encoding="utf-8",
        )
        os.replace(replacement, payload)
    elif mutation == "symlink":
        payload.unlink()
        payload.symlink_to(training_dir / "valid.jsonl")
    else:
        (root / "external-challenge.jsonl").write_text("PROTECTED\n", encoding="utf-8")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(runtime, "_stream_command", lambda *_a, **kwargs: calls.append(kwargs))
    with pytest.raises(runtime.MLXPipelineError, match=r"changed|allowlist|symlink|checksum"):
        runtime.stream_mlx_with_sealed_view(
            {"model": "fixture", "test": True},
            view=validation,
            config_path=tmp_path / "eval-config.json",
            cwd=tmp_path,
            log_path=tmp_path / "eval.log",
        )
    assert calls == []


def test_train_and_validation_consumers_use_directory_fd_and_pass_fds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    training_dir, training_view = _staged_training_view(tmp_path)
    validation = runtime.stage_validation_consumer_view(
        training_dir,
        tmp_path / "validation-view",
        training_view=training_view,
    )
    calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def fake_stream(command: list[str], **kwargs: Any) -> runtime.CommandResult:
        config = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        calls.append((config, kwargs))
        return runtime.CommandResult(
            command=("fixture",),
            returncode=0,
            output="Test loss 1.0",
            elapsed_seconds=0.0,
            peak_memory_gb=None,
        )

    monkeypatch.setattr(runtime, "_stream_command", fake_stream)
    for name, view in (("train", training_view), ("eval", validation)):
        config_path = tmp_path / f"{name}.json"
        runtime.stream_mlx_with_sealed_view(
            {"model": "fixture", "train": name == "train", "test": name == "eval"},
            view=view,
            config_path=config_path,
            cwd=tmp_path,
            log_path=tmp_path / f"{name}.log",
        )
    assert len(calls) == 2
    for config, kwargs in calls:
        assert str(config["data"]).startswith("/dev/fd/")
        fd = int(str(config["data"]).rsplit("/", 1)[1])
        assert kwargs["pass_fds"] == (fd,)
