from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ntruth.governance.lineage import CorpusSplit, CorpusSplitV7
from ntruth.parser_ai.contract import ParserAIInput, ParserCandidateOutput
from ntruth.training import (
    AnnotationStatus,
    DatasetValidationError,
    SupervisedRecord,
    SupervisionProvenance,
    prepare_dataset,
)
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.mlx_inference import _verify_evaluation_snapshot
from ntruth.training.mlx_runtime import MLXPipelineError
from ntruth.training.records import normalize_record
from ntruth.training.splits import leakage_tokens, migrate_corpus_split_v7


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _gold_target(record_id: str) -> dict[str, object]:
    candidate = ParserCandidateOutput.model_validate(
        {
            "coverage": {
                "status": "PARTIAL",
                "missing_artifact_ids": ["not-reported"],
                "rationale": f"Adjudicated candidate fixture for {record_id}.",
            },
            "model_metadata": {
                "adapter_name": "v6-governance-adjudication",
                "model_name": "fixture",
                "model_version": "1",
                "prompt_template_version": "candidate-v8",
            },
        }
    )
    return {
        "schema_version": "8.0.0",
        "candidate_target": candidate.model_dump(mode="json"),
        "adjudication_id": f"adjudication-{record_id}",
        "reviewer_ids": ["wet-lab", "biostatistician"],
        "adjudication_rationale": "Blind technical submissions reconciled.",
        "submission_references": (
            {
                "submission_id": f"{record_id}-a",
                "submission_sha256": "a" * 64,
                "reviewer_id": "wet-lab",
                "reviewer_role": "wet-lab",
            },
            {
                "submission_id": f"{record_id}-b",
                "submission_sha256": "b" * 64,
                "reviewer_id": "biostatistician",
                "reviewer_role": "biostatistician",
            },
        ),
        "comparison_status": "AGREED",
        "material_differences": [],
    }


def _external_dependency(record_id: str) -> dict[str, object]:
    return {
        "review_status": "SCIENTIFIC_REVIEW_REQUIRED",
        "task7_contamination_attestation_reference": {
            "artifact_id": f"attestation-{record_id}",
            "sha256": "c" * 64,
        },
        "custody_reference": {"artifact_id": f"custody-{record_id}", "sha256": "d" * 64},
        "family_evidence_references": [{"artifact_id": f"family-{record_id}", "sha256": "e" * 64}],
    }


def _record(
    record_id: str,
    *,
    split: CorpusSplit = CorpusSplit.TRAIN,
    training_eligible: bool = True,
    evaluation_eligible: bool = False,
    release_eligible: bool = False,
    model_selection_eligible: bool = False,
    synthetic: bool = False,
    provenance_fields: dict[str, str] | None = None,
    metadata: dict[str, str] | None = None,
) -> SupervisedRecord:
    parser_input = ParserAIInput(
        metadata={"record": record_id, **(metadata or {})},
        domain_hint="v6_training_governance",
        language="en",
    )
    external = split is CorpusSplit.EXTERNAL_CHALLENGE
    return SupervisedRecord(
        record_id=record_id,
        task="parser_candidate_v8",
        language="en",
        domain="v6_training_governance",
        input_text=parser_input.model_dump_json(),
        target=_gold_target(record_id),
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=_sha(f"source:{record_id}"),
            governance_hash=_sha(f"governance:{record_id}"),
            license_or_authorization_id=f"license-{record_id}",
            guideline_version="6.0",
            reviewer_count=2,
            reviewer_ids=("wet-lab", "biostatistician"),
            reviewer_roles=("wet-lab", "biostatistician"),
            adjudication_id=f"adjudication-{record_id}",
            synthetic=synthetic,
            study_family_id=f"study-{record_id}" if external else None,
            document_lineage_id=f"document-{record_id}" if external else None,
            external_challenge_dependency=(_external_dependency(record_id) if external else None),
            **(provenance_fields or {}),
        ),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=training_eligible,
        evaluation_eligible=evaluation_eligible,
        release_eligible=release_eligible,
        model_selection_eligible=model_selection_eligible,
        split=split,
    )


def _jsonl_ids(path: Path) -> tuple[str, ...]:
    return tuple(
        json.loads(line)["record_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def test_external_legacy_value_is_read_but_canonicalized() -> None:
    assert CorpusSplitV7("external") is CorpusSplitV7.EXTERNAL_CHALLENGE
    assert CorpusSplitV7.EXTERNAL is CorpusSplitV7.EXTERNAL_CHALLENGE
    assert CorpusSplitV7.EXTERNAL_CHALLENGE.value == "external_challenge"
    assert "external" not in {split.value for split in CorpusSplitV7}
    assert migrate_corpus_split_v7("external") is CorpusSplit.EXTERNAL_CHALLENGE
    with pytest.raises(ValueError):
        CorpusSplit("external")

    record = _record(
        "legacy-external",
        split=migrate_corpus_split_v7("external"),
        training_eligible=False,
    )
    payload = record.model_dump(mode="json")
    assert payload["split"] == "EXTERNAL_CHALLENGE"
    payload["requested_split"] = "external"
    with pytest.raises(ValidationError):
        SupervisedRecord.model_validate(payload)
    reloaded = SupervisedRecord.model_validate({**payload, "requested_split": "EXTERNAL_CHALLENGE"})
    assert reloaded.requested_split is CorpusSplit.EXTERNAL_CHALLENGE
    assert reloaded.model_dump(mode="json")["requested_split"] == "EXTERNAL_CHALLENGE"


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
            model_selection_eligible=True,
        ),
        _record(
            "test",
            split=CorpusSplit.TEST,
            training_eligible=False,
            evaluation_eligible=True,
        ),
        _record("external", split=CorpusSplit.EXTERNAL_CHALLENGE, training_eligible=False),
    )
    dataset = prepare_dataset(records)
    output = tmp_path / "mlx"

    snapshot = export_mlx_dataset(dataset, output)

    assert _jsonl_ids(output / "train.jsonl") == ("train",)
    assert _jsonl_ids(output / "valid.jsonl") == ("validation",)
    assert not (output / "test.jsonl").exists()
    assert not (output / "external.jsonl").exists()
    assert snapshot["counts"] == {"train": 1, "valid": 1}
    assert snapshot["membership_counts"] == {
        "UNASSIGNED": 0,
        "TRAIN": 1,
        "VALIDATION": 1,
        "TEST": 1,
        "EXTERNAL_CHALLENGE": 1,
    }
    assert {entry.record_id for entry in dataset.manifest.records} == {
        "train",
        "validation",
        "test",
        "external",
    }
    assert snapshot["training_approved"] is True


def test_external_membership_stays_disjoint_from_the_training_view() -> None:
    long_tokens = [f"token-{index:03d}" for index in range(200)]
    training_record = _record(
        "train",
        split=CorpusSplit.TRAIN,
        metadata={"body": " ".join(long_tokens)},
    )
    contaminated = _record(
        "external-contaminated",
        split=CorpusSplit.EXTERNAL_CHALLENGE,
        training_eligible=False,
    )
    contaminated = contaminated.model_copy(
        update={
            "provenance": contaminated.provenance.model_copy(
                update={
                    "source_id": training_record.provenance.source_id,
                    "source_asset_id": training_record.provenance.source_asset_id,
                    "source_sha256": training_record.provenance.source_sha256,
                }
            )
        }
    )
    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset((training_record, contaminated))
    assert "conflicting_requested_splits" in {issue.code for issue in captured.value.issues}

    near_tokens = list(long_tokens)
    near_tokens[100] = "single-changed-token"
    near_external = _record(
        "external-near",
        split=CorpusSplit.EXTERNAL_CHALLENGE,
        training_eligible=False,
        metadata={"body": " ".join(near_tokens)},
    )
    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset((training_record, near_external))
    assert "conflicting_duplicate_requested_splits" in {
        issue.code for issue in captured.value.issues
    }


def test_external_evaluation_fails_closed_without_custodial_pins(tmp_path: Path) -> None:
    data_dir = tmp_path / "external"
    data_dir.mkdir()
    payload = data_dir / "external-challenge.jsonl"
    payload.write_text("{}\n", encoding="utf-8")

    with pytest.raises(MLXPipelineError, match="SCIENTIFIC_REVIEW_REQUIRED"):
        _verify_evaluation_snapshot(payload, "external_challenge", {"smoke_test": False})

    design_pins = {
        "planned_design_artifact_id": "planned-1",
        "planned_design_artifact_sha256": "b" * 64,
        "executed_design_artifact_id": "executed-1",
        "executed_design_artifact_sha256": "c" * 64,
    }
    with pytest.raises(MLXPipelineError, match="DatasetManifest"):
        _verify_evaluation_snapshot(
            payload, "external_challenge", {"smoke_test": False, **design_pins}
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
