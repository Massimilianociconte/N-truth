from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.parser_ai.contract import ParserAIDocumentInput, ParserAIEvidenceSpan, ParserAIInput
from ntruth.parser_ai.stages import (
    CandidateExperimentBlock,
    CandidateFactor,
    CandidateGraphSet,
    ChunkCoverageRecord,
    StageAuthority,
    StageName,
    StageProvenance,
    StageStatus,
    validate_candidate_graph_pair,
)
from ntruth.schemas.core import EvidenceType
from ntruth.training.calibration import ConfidenceObservation
from ntruth.training.cli import DEFAULT_PROFILE
from ntruth.training.metrics_v6 import (
    aggregate_scores,
    confidence_observations,
    score_output,
)
from ntruth.training.mlx_inference import (
    _verify_calibration_artifact,
    _verify_metrics_artifacts,
    calibrate_predictions,
    export_adapter_bundle,
    predict_and_score,
)
from ntruth.training.mlx_runtime import MLXPipelineError, sha256_file


def _parser_output(*, confidence: float = 0.7) -> CandidateGraphSet:
    return CandidateGraphSet(
        result_id="lineage-result",
        status=StageStatus.COMPLETE,
        provenance=StageProvenance(
            stage_run_id="lineage-stage",
            stage=StageName.CANDIDATE_GRAPH_SET,
            authority=StageAuthority.MODEL,
            producer="lineage-test-parser",
            producer_version="6.0",
        ),
        graph_set_id="lineage-graph",
        evidence_spans=(
            ParserAIEvidenceSpan(
                evidence_id="evidence-1",
                file_id="document-1",
                evidence_type=EvidenceType.STRUCTURAL_FACT,
                text="Evidence.",
                confidence=confidence,
                start=0,
                end=9,
            ),
        ),
        chunk_coverage=(
            ChunkCoverageRecord(
                file_id="document-1",
                total_chunks=1,
                processed_chunks=(0,),
            ),
        ),
    )


def _evidence_link_output(*, swapped: bool) -> CandidateGraphSet:
    evidence = (
        ParserAIEvidenceSpan(
            evidence_id="evidence-a",
            file_id="document-1",
            evidence_type=EvidenceType.STRUCTURAL_FACT,
            text="Alpha",
            confidence=0.8,
            start=0,
            end=5,
        ),
        ParserAIEvidenceSpan(
            evidence_id="evidence-b",
            file_id="document-1",
            evidence_type=EvidenceType.STRUCTURAL_FACT,
            text="Beta",
            confidence=0.8,
            start=6,
            end=10,
        ),
    )
    links = ("evidence-b", "evidence-a") if swapped else ("evidence-a", "evidence-b")
    return CandidateGraphSet(
        result_id="link-result",
        status=StageStatus.COMPLETE,
        provenance=StageProvenance(
            stage_run_id="link-stage",
            stage=StageName.CANDIDATE_GRAPH_SET,
            authority=StageAuthority.MODEL,
            producer="link-test-parser",
            producer_version="6.0",
        ),
        graph_set_id="link-graph",
        experiment_blocks=(
            CandidateExperimentBlock(
                block_id="block-1",
                title="Experiment",
                evidence_ids=("evidence-a",),
                confidence=0.9,
            ),
        ),
        evidence_spans=evidence,
        factors=(
            CandidateFactor(
                factor_id="factor-a",
                block_id="block-1",
                name="treatment",
                levels=("drug", "vehicle"),
                allocation_level=None,
                application_level=None,
                evidence_ids=(links[0],),
                confidence=0.9,
            ),
            CandidateFactor(
                factor_id="factor-b",
                block_id="block-1",
                name="sex",
                levels=("female", "male"),
                allocation_level=None,
                application_level=None,
                evidence_ids=(links[1],),
                confidence=0.9,
            ),
        ),
    )


def test_metrics_and_calibration_detect_swapped_evidence_links() -> None:
    gold = _evidence_link_output(swapped=False)
    predicted = _evidence_link_output(swapped=True)

    score = score_output(predicted, gold)
    observations = confidence_observations(predicted, gold)

    assert score["categories"]["evidence_spans"]["f1"] == 1.0
    assert score["categories"]["factors"]["f1"] == 0.0
    assert score["micro"]["f1"] < 1.0
    assert sum(not observation.correct for observation in observations) == 2


def _evaluation_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    evaluation_path = snapshot_dir / "test.jsonl"
    parser_input = ParserAIInput(
        documents=(
            ParserAIDocumentInput(
                file_id="document-1",
                filename="methods.txt",
                sha256="a" * 64,
                text="Evidence.",
            ),
        ),
        metadata={"record": "test-1"},
        language="en",
    )
    gold = validate_candidate_graph_pair(parser_input, _parser_output())
    evaluation_row = {
        "record_id": "test-1",
        "messages": [
            {"role": "system", "content": "test"},
            {"role": "user", "content": parser_input.model_dump_json()},
            {"role": "assistant", "content": gold.model_dump_json()},
        ],
    }
    evaluation_path.write_text(json.dumps(evaluation_row) + "\n", encoding="utf-8")

    predicted = validate_candidate_graph_pair(parser_input, _parser_output())
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
        "schema_version": "1.0.0",
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
    state = {
        "schema_version": "2.0.0",
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


def test_export_rejects_test_metrics_from_another_snapshot(
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

    with pytest.raises(MLXPipelineError, match="snapshot test"):
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
        "schema_version": "1.0.0",
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
    assert context["metrics"]["confidence_observations"] == 1


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
    row["prediction"]["evidence_spans"][0]["confidence"] = 0.1
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
    row["gold"]["graph_set_id"] = "altered-gold-graph"
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
    row = json.loads(observations_path.read_text(encoding="utf-8"))
    row["confidence"] = 0.1
    observations_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["confidence_observations_sha256"] = sha256_file(observations_path)
    metrics["confidence_observations"] = 1
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
    }
    metrics_context = {
        "path": metrics_path.resolve(),
        "sha256": sha256_file(metrics_path),
        "metrics": {"declared_split": "test"},
        "run_lineage": run_lineage,
        "snapshot": training_snapshot,
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
