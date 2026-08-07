from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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
from ntruth.training.mlx_dataset import PARSER_CANDIDATE_GRAPH_TASK, export_mlx_dataset
from ntruth.training.mlx_inference import _verify_evaluation_snapshot
from ntruth.training.mlx_runtime import MLXPipelineError, validate_snapshot_integrity
from ntruth.training.records import normalize_record
from ntruth.training.splits import leakage_tokens


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _target(record_id: str) -> dict[str, object]:
    graph = CandidateGraphSet(
        result_id=f"adjudicated-result-{record_id}",
        status=StageStatus.COMPLETE,
        provenance=StageProvenance(
            stage_run_id=f"adjudication-stage-{record_id}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            authority=StageAuthority.ADJUDICATION,
            producer="v6-governance-adjudication",
            producer_version="6.0",
        ),
        graph_set_id=f"adjudicated-graph-{record_id}",
    )
    return GoldParserTarget(
        target_id=f"target-{record_id}",
        source_record_id=record_id,
        guideline_version="6.0",
        adjudication_id=f"adjudication-{record_id}",
        adjudication_rationale="Blind technical submissions reconciled.",
        adjudicator_roles=("wet-lab", "biostatistician"),
        source_submission_ids=(f"{record_id}-a", f"{record_id}-b"),
        comparisons=(
            SubmissionComparison(
                submission_id=f"{record_id}-a",
                reviewer_role="wet-lab",
                summary="Empty technical graph accepted.",
            ),
            SubmissionComparison(
                submission_id=f"{record_id}-b",
                reviewer_role="biostatistician",
                summary="Empty technical graph accepted.",
            ),
        ),
        adjudicated_graph=graph,
    ).model_dump(mode="json")


def _record(
    record_id: str,
    *,
    split: CorpusSplit = CorpusSplit.TRAIN,
    training_eligible: bool = True,
    evaluation_eligible: bool = False,
    release_eligible: bool = False,
    synthetic: bool = False,
    provenance_fields: dict[str, str] | None = None,
) -> SupervisedRecord:
    parser_input = ParserAIInput(
        metadata={"record": record_id},
        domain_hint="v6_training_governance",
        language="en",
    )
    return SupervisedRecord(
        record_id=record_id,
        task=PARSER_CANDIDATE_GRAPH_TASK,
        language="en",
        domain="v6_training_governance",
        input_text=parser_input.model_dump_json(),
        target=_target(record_id),
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=_sha(f"source:{record_id}"),
            governance_hash=_sha(f"governance:{record_id}"),
            license_or_authorization_id=f"license-{record_id}",
            guideline_version="6.0",
            reviewer_count=2,
            reviewer_roles=("wet-lab", "biostatistician"),
            adjudication_id=f"adjudication-{record_id}",
            synthetic=synthetic,
            **(provenance_fields or {}),
        ),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=training_eligible,
        evaluation_eligible=evaluation_eligible,
        release_eligible=release_eligible,
        requested_split=split,
    )


def _jsonl_ids(path: Path) -> tuple[str, ...]:
    return tuple(
        json.loads(line)["record_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def test_external_legacy_value_is_read_but_canonicalized() -> None:
    assert CorpusSplit("external") is CorpusSplit.EXTERNAL_CHALLENGE
    assert CorpusSplit.EXTERNAL is CorpusSplit.EXTERNAL_CHALLENGE
    assert CorpusSplit.EXTERNAL_CHALLENGE.value == "external_challenge"
    assert "external" not in {split.value for split in CorpusSplit}

    record = _record(
        "legacy-external",
        split=CorpusSplit.EXTERNAL_CHALLENGE,
        training_eligible=False,
        evaluation_eligible=True,
    )
    payload = record.model_dump(mode="json")
    payload["requested_split"] = "external"
    loaded = SupervisedRecord.model_validate(payload)
    assert loaded.requested_split is CorpusSplit.EXTERNAL_CHALLENGE
    assert loaded.model_dump(mode="json")["requested_split"] == "external_challenge"


@pytest.mark.parametrize(
    "split",
    (CorpusSplit.TEST, CorpusSplit.EXTERNAL_CHALLENGE),
)
def test_closed_evaluation_splits_reject_training_eligibility(split: CorpusSplit) -> None:
    with pytest.raises(ValidationError, match="training_eligible=false"):
        _record(record_id=f"blocked-{split.value}", split=split)


def test_evaluation_and_release_flags_survive_the_manifest() -> None:
    evaluation = _record(
        "test-evaluation",
        split=CorpusSplit.TEST,
        training_eligible=False,
        evaluation_eligible=True,
        release_eligible=True,
    )

    dataset = prepare_dataset((evaluation,))
    manifest_record = dataset.manifest.records[0]

    assert manifest_record.split is CorpusSplit.TEST
    assert manifest_record.training_eligible is False
    assert manifest_record.evaluation_eligible is True
    assert manifest_record.release_eligible is True


def test_synthetic_records_are_confined_to_train() -> None:
    with pytest.raises(ValidationError, match="soltanto a train"):
        _record(
            "synthetic-test",
            split=CorpusSplit.TEST,
            training_eligible=False,
            evaluation_eligible=True,
            synthetic=True,
        )

    synthetic = _record(
        "synthetic-unassigned",
        split=CorpusSplit.UNASSIGNED,
        synthetic=True,
    )
    prepared = prepare_dataset((synthetic,)).records[0]
    assert prepared.split is CorpusSplit.TRAIN


@pytest.mark.parametrize(
    ("field", "prefix"),
    (
        ("supplement_id", "supplement"),
        ("preprint_id", "preprint"),
        ("dataset_id", "dataset"),
        ("facility_id", "facility"),
        ("synthetic_family_id", "synthetic_family"),
        ("counterfactual_family_id", "counterfactual_family"),
    ),
)
def test_v6_provenance_identifiers_generate_leakage_tokens(field: str, prefix: str) -> None:
    record = _record(
        f"token-{prefix}",
        provenance_fields={field: " Shared Family "},
    )
    normalized = normalize_record(record, shingle_size=5)

    assert f"{prefix}:shared family" in leakage_tokens(normalized)


def test_export_uses_only_train_for_gradients_and_keeps_evaluation_manifest(tmp_path: Path) -> None:
    records = (
        _record("train", split=CorpusSplit.TRAIN),
        _record(
            "validation",
            split=CorpusSplit.VALIDATION,
            training_eligible=False,
            evaluation_eligible=True,
        ),
        _record(
            "test",
            split=CorpusSplit.TEST,
            training_eligible=False,
            evaluation_eligible=True,
        ),
        _record(
            "external",
            split=CorpusSplit.EXTERNAL_CHALLENGE,
            training_eligible=False,
            evaluation_eligible=True,
        ),
    )
    dataset = prepare_dataset(records)
    output = tmp_path / "mlx"

    snapshot = export_mlx_dataset(dataset, output)

    assert _jsonl_ids(output / "train.jsonl") == ("train",)
    assert _jsonl_ids(output / "valid.jsonl") == ("validation",)
    assert _jsonl_ids(output / "test.jsonl") == ("test",)
    assert _jsonl_ids(output / "external.jsonl") == ("external",)
    assert {entry.record_id for entry in dataset.manifest.records} == {
        "train",
        "validation",
        "test",
        "external",
    }
    assert snapshot["training_approved"] is True


def test_external_snapshot_must_be_disjoint_from_the_run_snapshot(tmp_path: Path) -> None:
    training_record = _record("train", split=CorpusSplit.TRAIN)
    long_tokens = [f"token-{index:03d}" for index in range(200)]
    training_record = training_record.model_copy(
        update={
            "input_text": ParserAIInput(
                metadata={"record": "train", "body": " ".join(long_tokens)},
                domain_hint="v6_training_governance",
                language="en",
            ).model_dump_json()
        }
    )
    training_dataset = prepare_dataset(
        (
            training_record,
            _record(
                "validation",
                split=CorpusSplit.VALIDATION,
                training_eligible=False,
                evaluation_eligible=True,
            ),
            _record(
                "test",
                split=CorpusSplit.TEST,
                training_eligible=False,
                evaluation_eligible=True,
            ),
        )
    )
    training_dir = tmp_path / "training-snapshot"
    export_mlx_dataset(training_dataset, training_dir)
    training_snapshot = validate_snapshot_integrity(training_dir)
    run_lineage = {
        "smoke_test": False,
        "run_dataset_snapshot_path": str(training_dir.resolve()),
        "run_dataset_snapshot_id": training_snapshot["snapshot_id"],
        "run_dataset_snapshot_sha256": training_snapshot["snapshot_sha256"],
        "run_dataset_manifest_sha256": training_snapshot["manifest_sha256"],
    }

    external = _record(
        "external-contaminated",
        split=CorpusSplit.EXTERNAL_CHALLENGE,
        training_eligible=False,
        evaluation_eligible=True,
    )
    external = external.model_copy(
        update={
            "provenance": external.provenance.model_copy(
                update={
                    "source_id": training_record.provenance.source_id,
                    "source_asset_id": training_record.provenance.source_asset_id,
                    "source_sha256": training_record.provenance.source_sha256,
                }
            )
        }
    )
    contaminated_dir = tmp_path / "contaminated-external"
    export_mlx_dataset(prepare_dataset((external,)), contaminated_dir)

    with pytest.raises(MLXPipelineError, match="contaminazione train/external"):
        _verify_evaluation_snapshot(
            contaminated_dir / "external.jsonl",
            "external",
            run_lineage,
        )

    near_tokens = list(long_tokens)
    near_tokens[100] = "single-changed-token"
    near_external = _record(
        "external-near",
        split=CorpusSplit.EXTERNAL_CHALLENGE,
        training_eligible=False,
        evaluation_eligible=True,
    ).model_copy(
        update={
            "input_text": ParserAIInput(
                metadata={"record": "external-near", "body": " ".join(near_tokens)},
                domain_hint="v6_training_governance",
                language="en",
            ).model_dump_json()
        }
    )
    near_dir = tmp_path / "near-external"
    export_mlx_dataset(prepare_dataset((near_external,)), near_dir)
    with pytest.raises(MLXPipelineError, match="near-duplicate"):
        _verify_evaluation_snapshot(
            near_dir / "external.jsonl",
            "external",
            run_lineage,
        )

    clean_dir = tmp_path / "clean-external"
    export_mlx_dataset(
        prepare_dataset(
            (
                _record(
                    "external-clean",
                    split=CorpusSplit.EXTERNAL_CHALLENGE,
                    training_eligible=False,
                    evaluation_eligible=True,
                ),
            )
        ),
        clean_dir,
    )
    _, clean_snapshot = _verify_evaluation_snapshot(
        clean_dir / "external.jsonl",
        "external",
        run_lineage,
    )
    assert clean_snapshot["external_disjointness"]["status"] == "passed"
    assert clean_snapshot["external_disjointness"]["external_records_checked"] == 1


def test_external_evaluation_fails_closed_without_training_snapshot_path(
    tmp_path: Path,
) -> None:
    external_dir = tmp_path / "external"
    export_mlx_dataset(
        prepare_dataset(
            (
                _record(
                    "external-only",
                    split=CorpusSplit.EXTERNAL_CHALLENGE,
                    training_eligible=False,
                    evaluation_eligible=True,
                ),
            )
        ),
        external_dir,
    )
    with pytest.raises(MLXPipelineError, match="dataset_snapshot_path"):
        _verify_evaluation_snapshot(
            external_dir / "external.jsonl",
            "external",
            {"smoke_test": False},
        )


def test_manifest_retains_v6_leakage_provenance_fields() -> None:
    identifiers = {
        "supplement_id": "supplement-1",
        "preprint_id": "preprint-1",
        "dataset_id": "dataset-1",
        "facility_id": "facility-1",
        "synthetic_family_id": "synthetic-family-1",
        "counterfactual_family_id": "counterfactual-family-1",
    }
    dataset = prepare_dataset((_record("provenance", provenance_fields=identifiers),))
    entry = dataset.manifest.records[0]

    for field, expected in identifiers.items():
        assert getattr(entry, field) == expected
