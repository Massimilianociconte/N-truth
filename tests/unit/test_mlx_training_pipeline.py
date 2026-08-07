from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput
from ntruth.parser_ai.stages import (
    CandidateGraphSet,
    StageAuthority,
    StageName,
    StageProvenance,
    StageStatus,
)
from ntruth.training import (
    AnnotationStatus,
    GoldParserTarget,
    SubmissionComparison,
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
from ntruth.training.metrics_v6 import (
    aggregate_scores,
    parse_prediction_text,
    score_invalid_output,
    score_output,
)
from ntruth.training.mlx_dataset import (
    PARSER_CANDIDATE_GRAPH_TASK,
    create_runtime_smoke_dataset,
    export_mlx_dataset,
)
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


def _output(
    *, variant: str = "gold", authority: StageAuthority = StageAuthority.MODEL
) -> CandidateGraphSet:
    return CandidateGraphSet(
        result_id=f"result-{variant}",
        status=StageStatus.COMPLETE,
        provenance=StageProvenance(
            stage_run_id=f"stage-{variant}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            authority=authority,
            producer="test-candidate-parser",
            producer_version=variant,
        ),
        graph_set_id=f"graph-{variant}",
    )


def _gold_target(record_id: str) -> dict[str, object]:
    return GoldParserTarget(
        target_id=f"target-{record_id}",
        source_record_id=record_id,
        guideline_version="6.0",
        adjudication_id=f"adjudication-{record_id}",
        adjudication_rationale="Two blind submissions reconciled for a technical test.",
        adjudicator_roles=("wet-lab", "biostatistician"),
        source_submission_ids=(f"{record_id}-blind-a", f"{record_id}-blind-b"),
        comparisons=(
            SubmissionComparison(
                submission_id=f"{record_id}-blind-a",
                reviewer_role="wet-lab",
                summary="No differences in the empty technical graph.",
            ),
            SubmissionComparison(
                submission_id=f"{record_id}-blind-b",
                reviewer_role="biostatistician",
                summary="No differences in the empty technical graph.",
            ),
        ),
        adjudicated_graph=_output(
            variant=f"adjudicated-{record_id}",
            authority=StageAuthority.ADJUDICATION,
        ),
    ).model_dump(mode="json")


def _record(record_id: str, split: CorpusSplit) -> SupervisedRecord:
    parser_input = ParserAIInput(
        metadata={"record": record_id},
        domain_hint="runtime_test",
        language="en",
    )
    training_eligible = split is CorpusSplit.TRAIN
    evaluation_eligible = split in {CorpusSplit.VALIDATION, CorpusSplit.TEST}
    return SupervisedRecord(
        record_id=record_id,
        task=PARSER_CANDIDATE_GRAPH_TASK,
        language="en",
        domain="runtime_test",
        input_text=parser_input.model_dump_json(),
        target=_gold_target(record_id),
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=_sha(f"source-{record_id}"),
            governance_hash=_sha(f"governance-{record_id}"),
            license_or_authorization_id=f"license-{record_id}",
            guideline_version="6.0",
            reviewer_count=2,
            reviewer_roles=("wet-lab", "biostatistician"),
            adjudication_id=f"adjudication-{record_id}",
        ),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=training_eligible,
        evaluation_eligible=evaluation_eligible,
        requested_split=split,
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
    assert profile["data"]["task"] == PARSER_CANDIDATE_GRAPH_TASK
    assert profile["data"]["parser_input_contract_version"] == "2.0.0"
    assert profile["data"]["candidate_graph_contract_version"] == "1.0.0"
    assert profile["data"]["gold_target_contract_version"] == "1.0.0"
    assert "contract_version" not in profile["data"]
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


def test_structured_score_does_not_require_identical_envelope_ids() -> None:
    predicted = _output(variant="prediction")
    gold = _output(variant="gold")

    score = score_output(predicted, gold)

    assert score["schema_valid"] is True
    assert score["micro"]["f1"] == 1.0
    assert score["exact_contract_match"] is False
    assert "determinability" not in score
    assert "determinability_accuracy" not in score


def test_invalid_empty_prediction_is_not_reported_as_perfect() -> None:
    score = score_invalid_output(_output(), "not JSON")
    aggregate = aggregate_scores((score,))

    assert score["micro"]["f1"] == 0.0
    assert aggregate["invalid_output_count"] == 1
    assert aggregate["schema_valid_rate"] == 0.0
    assert all("determinability" not in key for key in aggregate)
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
    assert validated["counts"] == {"train": 1, "valid": 1, "test": 1}
    train = json.loads((output / "train.jsonl").read_text().splitlines()[0])
    assert train["messages"][-1]["role"] == "assistant"
    assistant = CandidateGraphSet.model_validate_json(train["messages"][-1]["content"])
    payload = assistant.model_dump(mode="json")
    assert assistant.provenance.authority is StageAuthority.MODEL
    assert "determinability" not in payload
    assert "verdict" not in payload


def test_legacy_parser_output_task_cannot_enter_v6_training(tmp_path: Path) -> None:
    legacy = _record("legacy", CorpusSplit.TRAIN).model_copy(update={"task": "parser_ai_v2"})
    dataset = prepare_dataset((legacy,))

    with pytest.raises(MLXPipelineError, match="task atteso parser_candidate_graph_v6"):
        export_mlx_dataset(dataset, tmp_path / "legacy")


def test_parser_gold_identity_must_match_the_supervised_record(tmp_path: Path) -> None:
    record = _record("identity", CorpusSplit.TRAIN)
    target = dict(record.target)
    target["source_record_id"] = "different-record"
    inconsistent = record.model_copy(update={"target": target})
    dataset = prepare_dataset((inconsistent,))

    with pytest.raises(MLXPipelineError, match="record sorgente diverso"):
        export_mlx_dataset(dataset, tmp_path / "inconsistent")


def test_double_reviewed_flag_cannot_substitute_parser_gold_adjudication(
    tmp_path: Path,
) -> None:
    record = _record("not-adjudicated", CorpusSplit.TRAIN).model_copy(
        update={"annotation_status": AnnotationStatus.DOUBLE_REVIEWED}
    )
    dataset = prepare_dataset((record,))

    with pytest.raises(MLXPipelineError, match="annotation_status=adjudicated"):
        export_mlx_dataset(dataset, tmp_path / "not-adjudicated")


def test_runtime_smoke_dataset_is_allowed_only_with_explicit_smoke_gate(tmp_path: Path) -> None:
    output = tmp_path / "smoke"
    create_runtime_smoke_dataset(output)

    with pytest.raises(MLXPipelineError, match="training bloccato"):
        validate_mlx_dataset(output)
    result = validate_mlx_dataset(output, smoke_test=True)
    assert result["counts"] == {"train": 4, "valid": 2, "test": 2}
    assert result["smoke_test"] is True
