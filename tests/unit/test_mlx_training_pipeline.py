from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import (
    GoldParserTarget,
    ParserAIInput,
    ParserCandidateOutput,
)
from ntruth.training import (
    AnnotationStatus,
    SupervisedRecord,
    SupervisionProvenance,
    prepare_dataset,
)
from ntruth.training.calibration import (
    ConfidenceObservation,
    calibration_report,
    negative_log_likelihood,
)
from ntruth.training.cli import DEFAULT_PROFILE
from ntruth.training.metrics import (
    aggregate_scores,
    parse_prediction_text,
    score_invalid_output,
    score_output,
)
from ntruth.training.mlx_dataset import create_runtime_smoke_dataset, export_mlx_dataset
from ntruth.training.mlx_inference import calibrate_predictions
from ntruth.training.mlx_runtime import (
    MLXPipelineError,
    load_profile,
    runtime_environment,
    storage_budget,
    validate_mlx_dataset,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _output(*, confidence: float = 0.5) -> ParserCandidateOutput:
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
                    "boundary_predicates": [
                        {
                            "criterion": "DISTINCT_EXPERIMENT_SOURCE_DOCUMENT",
                            "internal_query_representability": "NOT_REPRESENTABLE",
                        }
                    ],
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
                "rationale": "Candidate-only test fixture.",
            },
            "model_metadata": {
                "adapter_name": "gold",
                "model_name": "annotation",
                "model_version": "1",
                "model_checksum": None,
                "prompt_template_version": "test",
                "contract_version": "8.0.0",
                "local_execution": True,
            },
        }
    )


def _record(record_id: str, split: CorpusSplit) -> SupervisedRecord:
    parser_input = ParserAIInput(
        metadata={"record": record_id},
        domain_hint="runtime_test",
        language="en",
    )
    return SupervisedRecord(
        record_id=record_id,
        task="parser_candidate_v8",
        language="en",
        domain="runtime_test",
        input_text=parser_input.model_dump_json(),
        target=GoldParserTarget(
            candidate_target=_output(),
            adjudication_id=f"adjudication-{record_id}",
            reviewer_ids=("wet-lab", "biostatistician"),
            adjudication_rationale="Candidate facts were reconciled.",
            submission_references=(
                {
                    "submission_id": f"submission-wet-{record_id}",
                    "submission_sha256": "a" * 64,
                    "reviewer_id": "wet-lab",
                    "reviewer_role": "wet-lab",
                },
                {
                    "submission_id": f"submission-stat-{record_id}",
                    "submission_sha256": "b" * 64,
                    "reviewer_id": "biostatistician",
                    "reviewer_role": "biostatistician",
                },
            ),
            comparison_status="AGREED",
            material_differences=(),
        ),
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=_sha(f"source-{record_id}"),
            governance_hash=_sha(f"governance-{record_id}"),
            license_or_authorization_id=f"license-{record_id}",
            guideline_version="test",
            reviewer_count=2,
            reviewer_ids=("wet-lab", "biostatistician"),
            reviewer_roles=("wet-lab", "biostatistician"),
            adjudication_id=f"adjudication-{record_id}",
        ),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=split in {CorpusSplit.TRAIN, CorpusSplit.VALIDATION},
        evaluation_eligible=split is CorpusSplit.TEST,
        model_selection_eligible=split is CorpusSplit.VALIDATION,
        split=split,
    )


def test_profile_has_consistent_storage_budget(tmp_path: Path) -> None:
    path = Path("models/configs/granite-4.1-3b-mlx-qlora.json")
    profile = load_profile(path)
    budget = storage_budget(profile)

    assert profile["model"]["provider"] == "granite"
    assert profile["model"]["canonical_repository"] == "ibm-granite/granite-4.1-3b"
    assert profile["model"]["repository"] == "mlx-community/granite-4.1-3b-4bit"
    assert profile["model"]["revision"] == "b1b476b5a17c46b7d6cd663b4a8ed44b66720aef"
    assert profile["model"]["expected_weight_bytes"] == 2_127_162_429
    assert (
        profile["model"]["expected_weight_sha256"]
        == "cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d"
    )
    assert profile["model"]["selection_role"] == "provisional_primary_train_a"
    assert profile["model"]["scientifically_selected"] is False
    assert "qwen" not in profile["model"]["repository"].casefold()
    assert profile["data"]["format"] == "chat_jsonl"
    assert budget["total_gib"] <= budget["workspace_cap_gib"]
    assert DEFAULT_PROFILE.is_file()
    assert DEFAULT_PROFILE.name == "granite-4.1-3b-mlx-qlora.json"

    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["data"]["contract_version"] = "2.0.0"
    legacy_path = tmp_path / "legacy-profile.json"
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    with pytest.raises(MLXPipelineError, match="contract_version e ambiguo"):
        load_profile(legacy_path)


def test_default_profile_is_granite_not_qwen() -> None:
    from ntruth.model_backends.base import ModelProvider
    from ntruth.model_backends.registry import DEFAULT_MODEL_ID, resolve_provider

    assert resolve_provider() is ModelProvider.GRANITE
    assert DEFAULT_MODEL_ID == "ibm-granite/granite-4.1-3b"
    assert "qwen" not in DEFAULT_PROFILE.name.casefold()


def test_runtime_environment_records_lock_and_source_without_secrets() -> None:
    environment = runtime_environment(Path(".").resolve())

    assert len(environment["uv_lock_sha256"]) == 64
    assert len(environment["source_snapshot_sha256"]) == 64
    assert environment["machine"]
    paths = {item["path"] for item in environment["source_files"]}
    assert {"pyproject.toml", "uv.lock"} <= paths
    serialized = json.dumps(environment, sort_keys=True).casefold()
    assert "token" not in serialized
    assert "password" not in serialized


def test_calibration_improves_validation_nll_and_never_uses_test() -> None:
    observations = tuple(
        ConfidenceObservation(confidence=confidence, correct=correct)
        for confidence, correct in (
            (0.95, True),
            (0.90, False),
            (0.80, True),
            (0.70, False),
            (0.30, True),
            (0.20, False),
            (0.10, False),
            (0.05, True),
            (0.60, True),
            (0.40, False),
        )
    )
    report = calibration_report(observations, minimum_coverage_count=2)

    assert report["test_used_for_fit"] is False
    assert report["after"]["negative_log_likelihood"] <= negative_log_likelihood(observations, 1.0)
    assert report["temperature"] > 0


def test_calibration_requires_hashed_validation_provenance(tmp_path: Path) -> None:
    observations = tmp_path / "confidence-observations.jsonl"
    rows = [
        {"confidence": 0.9 if index % 2 == 0 else 0.2, "correct": index % 2 == 0}
        for index in range(10)
    ]
    observations.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    observations_sha256 = hashlib.sha256(observations.read_bytes()).hexdigest()
    metrics = {
        "declared_split": "test",
        "confidence_observations": len(rows),
        "confidence_observations_sha256": observations_sha256,
    }
    (tmp_path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="schema metrics evaluation"):
        calibrate_predictions(observations, tmp_path / "calibration.json")

    metrics["declared_split"] = "validation"
    (tmp_path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    with pytest.raises(MLXPipelineError, match="schema metrics evaluation"):
        calibrate_predictions(observations, tmp_path / "calibration.json")


def test_prediction_parser_rejects_trailing_prose() -> None:
    payload = _output().model_dump_json()

    assert parse_prediction_text(payload) == _output()
    assert parse_prediction_text(f"```json\n{payload}\n```") == _output()
    with pytest.raises(ValueError, match="testo extra"):
        parse_prediction_text(payload + " explanation")


def test_structured_score_does_not_require_identical_metadata() -> None:
    predicted = _output(confidence=0.9)
    gold = _output(confidence=0.5)

    score = score_output(predicted, gold)

    assert score["schema_valid"] is True
    assert score["micro"]["f1"] == 1.0
    assert score["exact_contract_match"] is False


def test_invalid_empty_prediction_is_not_reported_as_perfect() -> None:
    score = score_invalid_output(_output(), "not JSON")
    aggregate = aggregate_scores((score,))

    assert score["micro"]["f1"] == 0.0
    assert aggregate["invalid_output_count"] == 1
    assert aggregate["schema_valid_rate"] == 0.0
    assert "determinability_macro_f1" not in aggregate
    assert aggregate["macro_category_f1"] == 0.0
    assert all(category["f1"] == 0.0 for category in aggregate["categories"].values())
    assert aggregate["micro"]["precision"] == 0.0
    assert aggregate["micro"]["recall"] == 0.0
    assert aggregate["micro"]["f1"] == 0.0


def test_governed_dataset_exports_mlx_chat_and_snapshot(tmp_path: Path) -> None:
    dataset = prepare_dataset(
        (
            _record("train", CorpusSplit.TRAIN),
            _record("valid", CorpusSplit.VALIDATION),
            _record("test", CorpusSplit.TEST),
        )
    )
    output = tmp_path / "mlx"

    snapshot = export_mlx_dataset(dataset, output)
    validated = validate_mlx_dataset(output)

    assert snapshot["training_approved"] is True
    assert snapshot["leakage_check_passed"] is True
    assert validated["counts"] == {"train": 1, "valid": 1}
    assert snapshot["membership_counts"]["TEST"] == 1
    assert not (output / "test.jsonl").exists()
    train = json.loads((output / "train.jsonl").read_text().splitlines()[0])
    assert train["messages"][-1]["role"] == "assistant"
    ParserCandidateOutput.model_validate_json(train["messages"][-1]["content"])


def test_runtime_smoke_dataset_is_allowed_only_with_explicit_smoke_gate(tmp_path: Path) -> None:
    output = tmp_path / "smoke"
    create_runtime_smoke_dataset(output)

    with pytest.raises(MLXPipelineError, match="training bloccato"):
        validate_mlx_dataset(output)
    result = validate_mlx_dataset(output, smoke_test=True)
    assert result["counts"] == {"train": 4, "valid": 4}
    assert result["smoke_test"] is True


def test_substantive_training_blocked_by_registry_hold(tmp_path: Path) -> None:
    from ntruth.training.mlx_runtime import MLXPipelineError, assert_substantive_training_allowed

    registry = tmp_path / "models" / "registry"
    registry.mkdir(parents=True)
    (registry / "training_program.json").write_text(
        json.dumps(
            {
                "training_execution_gate": "HOLD_PENDING_REAL_ANCHOR",
                "substantive_p0_training_allowed": False,
                "engineering_smoke_training_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(MLXPipelineError, match="HOLD_PENDING_REAL_ANCHOR"):
        assert_substantive_training_allowed(tmp_path, smoke_test=False)
    summary = assert_substantive_training_allowed(tmp_path, smoke_test=True)
    assert summary["engineering_smoke_training_allowed"] is True


def test_substantive_training_allowed_when_registry_opens(tmp_path: Path) -> None:
    from ntruth.training.mlx_runtime import assert_substantive_training_allowed

    registry = tmp_path / "models" / "registry"
    registry.mkdir(parents=True)
    (registry / "training_program.json").write_text(
        json.dumps(
            {
                "training_execution_gate": "OPEN_AFTER_GATES",
                "substantive_p0_training_allowed": True,
                "engineering_smoke_training_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    summary = assert_substantive_training_allowed(tmp_path, smoke_test=False)
    assert summary["substantive_p0_training_allowed"] is True


def test_missing_registry_fails_closed_for_both_modes(tmp_path: Path) -> None:
    from ntruth.training.mlx_runtime import MLXPipelineError, assert_substantive_training_allowed

    with pytest.raises(MLXPipelineError, match="fail-closed"):
        assert_substantive_training_allowed(tmp_path, smoke_test=False)
    with pytest.raises(MLXPipelineError, match="fail-closed"):
        assert_substantive_training_allowed(tmp_path, smoke_test=True)


def test_bundled_registry_blocks_substantive_training() -> None:
    from ntruth.training.mlx_runtime import MLXPipelineError, assert_substantive_training_allowed

    repo_root = Path(__file__).resolve().parents[2]
    with pytest.raises(MLXPipelineError, match="training_execution_gate"):
        assert_substantive_training_allowed(repo_root, smoke_test=False)
