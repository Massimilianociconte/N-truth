from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput, ParserAIOutput
from ntruth.training import (
    AnnotationStatus,
    DatasetManifest,
    PreparationConfig,
    SupervisedRecord,
    SupervisionProvenance,
    prepare_dataset,
)
from ntruth.training.mlx_dataset import create_runtime_smoke_dataset, export_mlx_dataset
from ntruth.training.mlx_runtime import (
    MLXPipelineError,
    validate_mlx_dataset,
    validate_snapshot_integrity,
)


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
                "adapter_name": "snapshot-integrity-gold",
                "model_name": "annotation",
                "model_version": "1",
                "model_checksum": None,
                "prompt_template_version": "snapshot-integrity-test",
                "contract_version": "2.0.0",
                "local_execution": True,
            },
        }
    ).model_dump(mode="json")


def _record(
    record_id: str,
    split: CorpusSplit,
    *,
    training_eligible: bool = True,
) -> SupervisedRecord:
    parser_input = ParserAIInput(
        metadata={"record": record_id},
        domain_hint="snapshot_integrity_test",
        language="en",
    )
    return SupervisedRecord(
        record_id=record_id,
        task="parser_ai_v2",
        language="en",
        domain="snapshot_integrity_test",
        input_text=parser_input.model_dump_json(),
        target=_target(),
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=_sha(f"source:{record_id}"),
            governance_hash=_sha(f"governance:{record_id}"),
            license_or_authorization_id=(f"license-{record_id}" if training_eligible else None),
            guideline_version="snapshot-integrity-test",
            reviewer_count=2 if training_eligible else 0,
            reviewer_roles=("wet-lab", "biostatistician") if training_eligible else (),
        ),
        annotation_status=(
            AnnotationStatus.DOUBLE_REVIEWED if training_eligible else AnnotationStatus.CANDIDATE
        ),
        training_eligible=training_eligible,
        requested_split=split,
    )


def _export_real_snapshot(
    output: Path,
    *,
    training_eligible: bool = True,
    include_all_splits: bool = True,
) -> None:
    records = [_record("train", CorpusSplit.TRAIN, training_eligible=training_eligible)]
    if include_all_splits:
        records.extend(
            (
                _record(
                    "valid",
                    CorpusSplit.VALIDATION,
                    training_eligible=training_eligible,
                ),
                _record("test", CorpusSplit.TEST, training_eligible=training_eligible),
            )
        )
    dataset = prepare_dataset(
        records,
        config=PreparationConfig(require_training_eligible=training_eligible),
    )
    export_mlx_dataset(dataset, output)


def _resign_snapshot(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    identity_payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"created_at", "snapshot_id", "snapshot_sha256"}
    }
    canonical = json.dumps(
        identity_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    prefix = "mlx-smoke-" if manifest.get("runtime_smoke_only") is True else "mlx-dataset-"
    manifest["snapshot_sha256"] = digest
    manifest["snapshot_id"] = prefix + digest[:20]
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def test_real_snapshot_verifies_files_counts_and_source_identity(tmp_path: Path) -> None:
    output = tmp_path / "snapshot"
    _export_real_snapshot(output)

    result = validate_snapshot_integrity(output)
    training = validate_mlx_dataset(output)

    assert result["counts"] == {"train": 1, "valid": 1, "test": 1, "external": 0}
    assert result["snapshot_id"].startswith("mlx-dataset-")
    assert len(result["snapshot_sha256"]) == 64
    assert result["source_manifest"]["dataset_id"] == result["manifest"]["dataset_id"]
    assert result["source_manifest_sha256"] == result["file_hashes"]["dataset-manifest.source.json"]
    assert training["snapshot_sha256"] == result["snapshot_sha256"]


def test_changed_split_bytes_are_rejected_before_training(tmp_path: Path) -> None:
    output = tmp_path / "snapshot"
    _export_real_snapshot(output)
    train = output / "train.jsonl"
    train.write_text(train.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(MLXPipelineError, match=r"(dimensione|checksum).*train.jsonl"):
        validate_mlx_dataset(output)


def test_manifest_counts_are_checked_even_if_snapshot_identity_is_recomputed(
    tmp_path: Path,
) -> None:
    output = tmp_path / "snapshot"
    _export_real_snapshot(output)
    manifest_path = output / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["train"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _resign_snapshot(manifest_path)

    with pytest.raises(MLXPipelineError, match=r"conteggio.*train"):
        validate_snapshot_integrity(output)


def test_updated_file_hash_cannot_detach_records_from_source_manifest(tmp_path: Path) -> None:
    output = tmp_path / "snapshot"
    _export_real_snapshot(output)
    train_path = output / "train.jsonl"
    rows = [json.loads(line) for line in train_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["record_id"] = "different-record"
    train_path.write_text(json.dumps(rows[0], sort_keys=True) + "\n", encoding="utf-8")

    manifest_path = output / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["train.jsonl"] = {
        "sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "size_bytes": train_path.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _resign_snapshot(manifest_path)

    with pytest.raises(MLXPipelineError, match=r"record_id.*manifest sorgente"):
        validate_snapshot_integrity(output)


def test_updated_hash_cannot_certify_changed_messages_with_same_record_id(
    tmp_path: Path,
) -> None:
    output = tmp_path / "snapshot"
    _export_real_snapshot(output)
    train_path = output / "train.jsonl"
    row = json.loads(train_path.read_text(encoding="utf-8"))
    row["messages"][-1]["content"] = json.dumps(_target() | {"experiment_blocks": []}) + " "
    train_path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    manifest_path = output / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["train.jsonl"] = {
        "sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "size_bytes": train_path.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _resign_snapshot(manifest_path)

    with pytest.raises(MLXPipelineError, match=r"contenuto chat.*prepared records"):
        validate_snapshot_integrity(output)


def test_training_approval_cannot_be_self_certified_with_boolean_flags(tmp_path: Path) -> None:
    output = tmp_path / "diagnostic-snapshot"
    _export_real_snapshot(output, training_eligible=False)
    manifest_path = output / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["training_approved"] is False
    manifest["training_approved"] = True
    manifest["leakage_check_passed"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _resign_snapshot(manifest_path)

    with pytest.raises(MLXPipelineError, match=r"training_approved.*manifest sorgente"):
        validate_snapshot_integrity(output)


def test_snapshot_dataset_id_must_match_content_addressed_source_manifest(
    tmp_path: Path,
) -> None:
    output = tmp_path / "snapshot"
    _export_real_snapshot(output)
    manifest_path = output / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_id"] = "dataset-00000000000000000000"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _resign_snapshot(manifest_path)

    with pytest.raises(MLXPipelineError, match=r"dataset_id.*manifest sorgente"):
        validate_snapshot_integrity(output)


def test_decisions_checksum_is_reconciled_with_preparation_report(tmp_path: Path) -> None:
    output = tmp_path / "snapshot"
    _export_real_snapshot(output)
    source_path = output / "dataset-manifest.source.json"
    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    source_payload["dataset_id"] = ""
    source_payload["decisions_checksum"] = _sha("detached-decisions")
    changed_source = DatasetManifest.model_validate(source_payload)
    source_path.write_text(
        json.dumps(changed_source.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest_path = output / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest["files"]["dataset-manifest.source.json"] = {
        "sha256": source_hash,
        "size_bytes": source_path.stat().st_size,
    }
    manifest["dataset_id"] = changed_source.dataset_id
    manifest["source_manifest"].update(
        {
            "sha256": source_hash,
            "dataset_id": changed_source.dataset_id,
            "manifest_checksum": changed_source.manifest_checksum(),
            "records_checksum": changed_source.records_checksum,
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _resign_snapshot(manifest_path)

    with pytest.raises(MLXPipelineError, match="decisions_checksum"):
        validate_snapshot_integrity(output)


def test_integrity_can_inspect_empty_splits_but_training_remains_fail_closed(
    tmp_path: Path,
) -> None:
    output = tmp_path / "partial-snapshot"
    _export_real_snapshot(output, include_all_splits=False)

    result = validate_snapshot_integrity(
        output,
        require_nonempty_training_splits=False,
    )
    assert result["counts"] == {"train": 1, "valid": 0, "test": 0, "external": 0}
    with pytest.raises(MLXPipelineError, match="split MLX vuoto"):
        validate_mlx_dataset(output)


def test_runtime_smoke_has_separate_identity_and_requires_explicit_gate(tmp_path: Path) -> None:
    output = tmp_path / "smoke"
    create_runtime_smoke_dataset(output)

    with pytest.raises(MLXPipelineError, match=r"training bloccato.*runtime smoke"):
        validate_snapshot_integrity(output)
    result = validate_snapshot_integrity(output, smoke_test=True)
    training = validate_mlx_dataset(output, smoke_test=True)

    assert result["snapshot_id"].startswith("mlx-smoke-")
    assert result["source_manifest"] is None
    assert result["manifest"]["training_approved"] is False
    assert result["manifest"]["scientific_metrics_allowed"] is False
    assert training["smoke_test"] is True
