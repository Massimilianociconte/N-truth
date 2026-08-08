from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput, ParserCandidateOutput
from ntruth.training.calibration import ConfidenceObservation
from ntruth.training.cli import DEFAULT_PROFILE
from ntruth.training.metrics import aggregate_scores, confidence_observations, score_output
from ntruth.training.mlx_inference import (
    _verify_calibration_artifact,
    _verify_metrics_artifacts,
    calibrate_predictions,
    export_adapter_bundle,
    predict_and_score,
)
from ntruth.training.mlx_runtime import (
    MLXPipelineError,
    TrainingDesignLineagePins,
    resolve_training_lineage_inputs,
    sha256_file,
)
from ntruth.training.records import AnnotationStatus, DatasetManifest, ManifestRecord


def _protected_release_source_manifest() -> DatasetManifest:
    return DatasetManifest(
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
                split=CorpusSplit.TEST,
                leakage_group_id="protected-group-1",
                source_id="source-1",
                source_asset_id="asset-1",
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


def _parser_output(*, confidence: float = 0.7) -> ParserCandidateOutput:
    return ParserCandidateOutput.model_validate(
        {
            "contract_version": "8.0.0",
            "experiment_blocks": [
                {
                    "block_id": "block-1",
                    "title": "Candidate block",
                    "evidence_ids": ["evidence-1"],
                    "confidence": confidence,
                }
            ],
            "block_boundaries": [
                {
                    "block_id": "block-1",
                    "boundary_basis_candidates": ["explicit_document_structure"],
                    "rationale": "The source explicitly identifies the candidate block.",
                    "evidence_ids": ["evidence-1"],
                    "confidence": confidence,
                }
            ],
            "evidence_spans": [
                {
                    "evidence_id": "evidence-1",
                    "file_id": "fixture",
                    "evidence_type": "STRUCTURAL_FACT",
                    "text": "candidate",
                    "confidence": confidence,
                    "start": 0,
                    "end": 9,
                }
            ],
            "candidate_nodes": [],
            "candidate_edges": [],
            "factors": [],
            "endpoints": [],
            "contrasts": [],
            "candidate_estimands": [],
            "candidate_counts": [],
            "candidate_events": [],
            "candidate_graphs": [],
            "alternatives": [],
            "clarification_questions": [],
            "missing_predicates": [],
            "coverage": {
                "status": "PARTIAL",
                "covered_artifact_ids": ["fixture"],
                "missing_artifact_ids": ["not-reported"],
                "rationale": "Candidate-only lineage fixture.",
            },
            "model_metadata": {
                "adapter_name": "lineage-test",
                "model_name": "test",
                "model_version": "1",
                "model_checksum": None,
                "prompt_template_version": "lineage-test",
                "contract_version": "8.0.0",
                "local_execution": True,
            },
        }
    )


def _evaluation_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    evaluation_path = snapshot_dir / "test.jsonl"
    parser_input = ParserAIInput(
        documents=(
            {
                "file_id": "fixture",
                "filename": "fixture.txt",
                "sha256": "a" * 64,
                "text": "candidate",
            },
        ),
        metadata={"record": "test-1"},
        language="en",
    )
    gold = _parser_output()
    evaluation_row = {
        "record_id": "test-1",
        "messages": [
            {"role": "system", "content": "test"},
            {"role": "user", "content": parser_input.model_dump_json()},
            {"role": "assistant", "content": gold.model_dump_json()},
        ],
    }
    evaluation_path.write_text(json.dumps(evaluation_row) + "\n", encoding="utf-8")

    predicted = _parser_output()
    score = score_output(predicted, gold)
    prediction_row = {
        "record_id": "test-1",
        "schema_valid": True,
        "error": None,
        "attempts": 1,
        "raw_outputs": [predicted.model_dump_json()],
        "gold": gold.model_dump(mode="json"),
        "prediction": predicted.model_dump(mode="json"),
        "score": score,
    }
    output_dir = tmp_path / "evaluation"
    output_dir.mkdir()
    predictions_path = output_dir / "predictions.jsonl"
    predictions_path.write_text(json.dumps(prediction_row) + "\n", encoding="utf-8")
    expected_observations = confidence_observations(predicted, gold)
    observations_path = output_dir / "confidence-observations.jsonl"
    observations_path.write_text(
        "".join(
            json.dumps({"confidence": item.confidence, "correct": item.correct}) + "\n"
            for item in expected_observations
        ),
        encoding="utf-8",
    )

    run_lineage = {
        "schema_version": "8.0.0",
        "profile_path": str(DEFAULT_PROFILE.resolve()),
        "repo_root": str(Path(".").resolve()),
        "run_dir": str((tmp_path / "run").resolve()),
        "adapter_path": str((tmp_path / "run" / "best").resolve()),
    }
    snapshot = {
        "file_hashes": {"test.jsonl": sha256_file(evaluation_path)},
        "snapshot_id": "mlx-dataset-" + "d" * 20,
        "snapshot_sha256": "d" * 64,
        "manifest_sha256": "e" * 64,
        "runtime_smoke_only": False,
    }
    lineage = {
        **run_lineage,
        "declared_split": "test",
        "evaluation_dataset_path": str(snapshot_dir.resolve()),
        "evaluation_file": "test.jsonl",
        "evaluation_sha256": sha256_file(evaluation_path),
        "evaluation_snapshot_id": snapshot["snapshot_id"],
        "evaluation_snapshot_sha256": snapshot["snapshot_sha256"],
        "evaluation_manifest_sha256": snapshot["manifest_sha256"],
        "evaluation_runtime_smoke_only": False,
    }
    metrics = aggregate_scores((score,))
    metrics.update(
        {
            "schema_version": "1.0.0",
            "created_at": "2026-08-01T00:00:00Z",
            "evaluation_file": str(evaluation_path.resolve()),
            "evaluation_sha256": sha256_file(evaluation_path),
            "adapter_path": run_lineage["adapter_path"],
            "records": 1,
            "confidence_observations": len(expected_observations),
            "retry_invalid_once": True,
            "declared_split": "test",
            "lineage": lineage,
            "predictions_sha256": sha256_file(predictions_path),
            "confidence_observations_sha256": sha256_file(observations_path),
        }
    )
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_best_run",
        lambda *_args, **_kwargs: run_lineage,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_evaluation_snapshot",
        lambda *_args, **_kwargs: (evaluation_path.resolve(), snapshot),
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._evaluation_lineage",
        lambda *_args, **_kwargs: lineage,
    )
    return metrics_path, predictions_path, observations_path


def _fake_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    run = tmp_path / "run"
    best = run / "best"
    best.mkdir(parents=True)
    adapter = best / "adapters.safetensors"
    adapter.write_bytes(b"adapter")
    model_hash = "a" * 64
    design_lineage = TrainingDesignLineagePins(
        planned_design_artifact_id="planned-1",
        planned_design_artifact_sha256="d" * 64,
        executed_design_artifact_id="executed-1",
        executed_design_artifact_sha256="e" * 64,
    )
    design_lineage_path = tmp_path / "task6-training-design-lineage.json"
    design_lineage_path.write_text(
        json.dumps(design_lineage.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    protected_source = _protected_release_source_manifest()
    protected_source_path = tmp_path / "protected-source-dataset-manifest.json"
    protected_source_path.write_text(
        json.dumps(protected_source.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    training_lineage = resolve_training_lineage_inputs(
        design_lineage_pins=design_lineage,
        design_lineage_artifact_path=design_lineage_path,
        protected_source_manifest_path=protected_source_path,
    )
    state = {
        "schema_version": "8.0.0",
        "status": "completed_maximum_phases",
        "profile_sha256": sha256_file(DEFAULT_PROFILE),
        "model_provenance_sha256": model_hash,
        "dataset_snapshot_id": "mlx-dataset-" + "b" * 20,
        "dataset_snapshot_sha256": "b" * 64,
        "dataset_manifest_sha256": "c" * 64,
        "smoke_test": False,
        "best_phase": 1,
        "last_completed_phase": 1,
        "best_adapter_sha256": sha256_file(adapter),
        **training_lineage.state_payload(),
    }
    (run / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(
        "ntruth.training.mlx_inference.verify_model",
        lambda *_args: {"provenance_sha256": model_hash},
    )
    return run, best


def test_predict_cannot_relabel_test_as_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run, best = _fake_run(tmp_path, monkeypatch)
    test_file = tmp_path / "snapshot" / "test.jsonl"
    test_file.parent.mkdir()
    test_file.write_text("{}\n", encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="mismatch split/file"):
        predict_and_score(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            test_file,
            best,
            tmp_path / "predictions",
            declared_split="validation",
        )
    assert not (tmp_path / "predictions").exists()


def test_export_rejects_test_metrics_without_protected_snapshot_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_lineage = {
        "run_status": "completed_maximum_phases",
        "smoke_test": False,
        "profile_sha256": "1" * 64,
        "model_provenance_sha256": "2" * 64,
        "run_state_sha256": "3" * 64,
        "run_dataset_snapshot_id": "mlx-dataset-" + "4" * 20,
        "run_dataset_snapshot_sha256": "4" * 64,
        "run_dataset_manifest_sha256": "5" * 64,
        "adapter_sha256": "6" * 64,
    }
    training_snapshot = {
        "manifest_path": str((tmp_path / "snapshot-manifest.json").resolve()),
        "snapshot_id": run_lineage["run_dataset_snapshot_id"],
        "snapshot_sha256": run_lineage["run_dataset_snapshot_sha256"],
        "manifest_sha256": run_lineage["run_dataset_manifest_sha256"],
    }
    foreign_snapshot = {**training_snapshot, "snapshot_sha256": "9" * 64}
    metrics_context = {
        "metrics": {"declared_split": "test"},
        "run_lineage": run_lineage,
        "snapshot": foreign_snapshot,
    }
    calibration_source = {
        "run_lineage": run_lineage,
        "snapshot": training_snapshot,
    }
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_best_run", lambda *_args, **_kwargs: run_lineage
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference.validate_snapshot_integrity",
        lambda *_args, **_kwargs: training_snapshot,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_metrics_artifacts",
        lambda *_args, **_kwargs: metrics_context,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_calibration_artifact",
        lambda *_args, **_kwargs: {"source_metrics": calibration_source},
    )

    with pytest.raises(MLXPipelineError, match="custodial/source manifest"):
        export_adapter_bundle(
            DEFAULT_PROFILE,
            Path(".").resolve(),
            tmp_path / "run",
            tmp_path / "export",
            dataset_manifest=tmp_path / "snapshot-manifest.json",
            metrics_path=tmp_path / "test-eval" / "metrics.json",
            calibration_path=tmp_path / "calibration.json",
        )
    assert not (tmp_path / "export").exists()


def test_metrics_top_level_cannot_detach_from_hashed_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluation_dir = tmp_path / "snapshot"
    evaluation_dir.mkdir()
    evaluation_path = evaluation_dir / "test.jsonl"
    evaluation_path.write_text("{}\n", encoding="utf-8")
    run_lineage = {
        "schema_version": "8.0.0",
        "profile_path": str(DEFAULT_PROFILE.resolve()),
        "repo_root": str(Path(".").resolve()),
        "run_dir": str((tmp_path / "run").resolve()),
        "adapter_path": str((tmp_path / "run" / "best").resolve()),
    }
    expected_lineage = {
        **run_lineage,
        "declared_split": "test",
        "evaluation_dataset_path": str(evaluation_dir.resolve()),
        "evaluation_file": "test.jsonl",
        "evaluation_sha256": sha256_file(evaluation_path),
    }
    metrics_dir = tmp_path / "evaluation"
    metrics_dir.mkdir()
    metrics = {
        "schema_version": "1.0.0",
        "declared_split": "test",
        "evaluation_file": str(evaluation_path.resolve()),
        "evaluation_sha256": sha256_file(evaluation_path),
        "adapter_path": str((tmp_path / "other-run" / "best").resolve()),
        "lineage": expected_lineage,
    }
    metrics_path = metrics_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_best_run",
        lambda *_args, **_kwargs: run_lineage,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_evaluation_snapshot",
        lambda *_args, **_kwargs: (evaluation_path.resolve(), {}),
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._evaluation_lineage",
        lambda *_args, **_kwargs: expected_lineage,
    )

    with pytest.raises(MLXPipelineError, match="adapter_path top-level"):
        _verify_metrics_artifacts(metrics_path)


def test_metrics_are_reconstructed_from_predictions_and_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_path, _predictions, _observations = _evaluation_artifacts(tmp_path, monkeypatch)

    context = _verify_metrics_artifacts(metrics_path)

    assert context["metrics"]["micro"]["f1"] == 1.0
    assert context["metrics"]["confidence_observations"] == 2


def test_tampered_micro_f1_is_rejected_even_without_an_external_metrics_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_path, _predictions, _observations = _evaluation_artifacts(tmp_path, monkeypatch)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["micro"]["f1"] = 0.0
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="metrica ricalcolata micro"):
        _verify_metrics_artifacts(metrics_path)


def test_tampered_prediction_is_rejected_after_predictions_hash_is_updated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_path, predictions_path, _observations = _evaluation_artifacts(tmp_path, monkeypatch)
    row = json.loads(predictions_path.read_text(encoding="utf-8"))
    row["prediction"]["experiment_blocks"][0]["confidence"] = 0.1
    predictions_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["predictions_sha256"] = sha256_file(predictions_path)
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="output grezzo"):
        _verify_metrics_artifacts(metrics_path)


def test_tampered_prediction_gold_is_rejected_against_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_path, predictions_path, _observations = _evaluation_artifacts(tmp_path, monkeypatch)
    row = json.loads(predictions_path.read_text(encoding="utf-8"))
    row["gold"]["coverage"]["rationale"] = "Altered gold."
    predictions_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["predictions_sha256"] = sha256_file(predictions_path)
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="gold prediction"):
        _verify_metrics_artifacts(metrics_path)


def test_tampered_observation_is_rejected_after_hash_and_count_are_updated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_path, _predictions, observations_path = _evaluation_artifacts(tmp_path, monkeypatch)
    rows = [json.loads(line) for line in observations_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["confidence"] = 0.1
    observations_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["confidence_observations_sha256"] = sha256_file(observations_path)
    metrics["confidence_observations"] = len(rows)
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="confidence-observations ricalcolate"):
        _verify_metrics_artifacts(metrics_path)


def test_calibration_is_recomputed_before_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observations_path = tmp_path / "confidence-observations.jsonl"
    observations = tuple(
        ConfidenceObservation(confidence=confidence, correct=correct)
        for confidence, correct in ((0.9, True), (0.8, False), (0.2, False), (0.1, True))
    )
    observations_path.write_text(
        "".join(
            json.dumps({"confidence": row.confidence, "correct": row.correct}) + "\n"
            for row in observations
        ),
        encoding="utf-8",
    )
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text("{}\n", encoding="utf-8")
    context = {
        "path": metrics_path.resolve(),
        "sha256": sha256_file(metrics_path),
        "metrics": {"declared_split": "validation", "confidence_observations": 4},
        "lineage": {"schema_version": "1.0.0"},
        "observations_path": observations_path.resolve(),
    }
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_metrics_artifacts",
        lambda *_args, **_kwargs: context,
    )
    calibration_path = tmp_path / "calibration.json"
    valid_report = calibrate_predictions(
        observations_path,
        calibration_path,
        minimum_coverage_count=1,
    )
    assert valid_report["fit_split"] == "validation"
    assert valid_report["test_used_for_fit"] is False
    report = json.loads(calibration_path.read_text(encoding="utf-8"))
    report["temperature"] = float(report["temperature"]) + 1.0
    calibration_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="ricalcolo temperature"):
        _verify_calibration_artifact(calibration_path)


def test_export_happy_path_copies_verified_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    best = run / "best"
    best.mkdir(parents=True)
    adapter = best / "adapters.safetensors"
    adapter.write_bytes(b"verified-adapter")
    run_state = run / "run-state.json"
    run_state.write_text('{"schema_version":"2.0.0"}\n', encoding="utf-8")
    dataset_manifest = tmp_path / "snapshot-manifest.json"
    dataset_manifest.write_text('{"schema_version":"2.0.0"}\n', encoding="utf-8")
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text('{"schema_version":"1.0.0"}\n', encoding="utf-8")
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text('{"schema_version":"1.0.0"}\n', encoding="utf-8")

    training_snapshot = {
        "manifest_path": str(dataset_manifest.resolve()),
        "snapshot_id": "mlx-dataset-" + "a" * 20,
        "snapshot_sha256": "a" * 64,
        "manifest_sha256": sha256_file(dataset_manifest),
    }
    run_lineage = {
        "run_status": "completed_maximum_phases",
        "smoke_test": False,
        "profile_sha256": sha256_file(DEFAULT_PROFILE),
        "model_provenance_sha256": "b" * 64,
        "run_state_sha256": sha256_file(run_state),
        "run_dataset_snapshot_id": training_snapshot["snapshot_id"],
        "run_dataset_snapshot_sha256": training_snapshot["snapshot_sha256"],
        "run_dataset_manifest_sha256": training_snapshot["manifest_sha256"],
        "adapter_sha256": sha256_file(adapter),
        "planned_design_artifact_id": "planned-1",
        "planned_design_artifact_sha256": "d" * 64,
        "executed_design_artifact_id": "executed-1",
        "executed_design_artifact_sha256": "e" * 64,
    }
    source_manifest = _protected_release_source_manifest()
    protected_snapshot = {
        "snapshot_id": "protected-test-1",
        "snapshot_sha256": "f" * 64,
        "manifest_sha256": "0" * 64,
        "protected_evaluation": {
            "split": "TEST",
            "snapshot_id": "protected-test-1",
            "snapshot_sha256": "f" * 64,
            "record_count": 1,
            "record_ids_checksum": (
                "e19fb8e28174c0999f801fbe618e3db0820dab93acb1eb0877db6f40f8cdf50d"
            ),
            "lineage": {
                "source_manifest_id": source_manifest.dataset_id,
                "source_manifest_sha256": "b" * 64,
                "planned_design_artifact_id": "planned-1",
                "planned_design_artifact_sha256": "d" * 64,
                "executed_design_artifact_id": "executed-1",
                "executed_design_artifact_sha256": "e" * 64,
            },
        },
        "source_dataset_manifest": source_manifest.model_dump(mode="json"),
    }
    metrics_context = {
        "path": metrics_path.resolve(),
        "sha256": sha256_file(metrics_path),
        "metrics": {"declared_split": "test"},
        "run_lineage": run_lineage,
        "snapshot": protected_snapshot,
    }
    calibration_source = {
        "sha256": "c" * 64,
        "run_lineage": run_lineage,
        "snapshot": training_snapshot,
    }
    calibration_context = {
        "path": calibration_path.resolve(),
        "sha256": sha256_file(calibration_path),
        "source_metrics": calibration_source,
    }
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_best_run", lambda *_args, **_kwargs: run_lineage
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference.validate_snapshot_integrity",
        lambda *_args, **_kwargs: training_snapshot,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_metrics_artifacts",
        lambda *_args, **_kwargs: metrics_context,
    )
    monkeypatch.setattr(
        "ntruth.training.mlx_inference._verify_calibration_artifact",
        lambda *_args, **_kwargs: calibration_context,
    )

    output = tmp_path / "export"
    manifest = export_adapter_bundle(
        DEFAULT_PROFILE,
        Path(".").resolve(),
        run,
        output,
        dataset_manifest=dataset_manifest,
        metrics_path=metrics_path,
        calibration_path=calibration_path,
    )

    assert (output / "adapters.safetensors").read_bytes() == b"verified-adapter"
    assert (output / "metrics.json").is_file()
    assert (output / "calibration.json").is_file()
    assert manifest["lineage"]["metrics_split"] == "test"
    assert manifest["lineage"]["dataset_snapshot_sha256"] == "a" * 64
    assert manifest["contains_base_weights"] is False
