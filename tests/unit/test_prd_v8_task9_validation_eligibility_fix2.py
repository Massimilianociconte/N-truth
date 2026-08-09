from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import test_mlx_snapshot_integrity as snapshot_fixtures
import test_prd_v8_training_records_splits as record_fixtures

import ntruth.training.mlx_runtime as runtime
from ntruth.governance.lineage import CorpusSplit
from ntruth.schemas.core import content_checksum
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.preparation import prepare_dataset
from ntruth.training.records import (
    DatasetManifest,
    ManifestRecord,
    PreparedDataset,
    PreparedRecord,
    SupervisedRecord,
)


def _valid_dataset() -> PreparedDataset:
    return prepare_dataset(
        (
            record_fixtures._record(
                "a-train",
                CorpusSplit.TRAIN,
                training=True,
                model_selection=False,
            ),
            record_fixtures._record(
                "b-validation",
                CorpusSplit.VALIDATION,
                training=True,
                model_selection=True,
            ),
        )
    )


def _validation_prepared(dataset: PreparedDataset) -> PreparedRecord:
    return next(record for record in dataset.records if record.split is CorpusSplit.VALIDATION)


def _validation_manifest(dataset: PreparedDataset) -> ManifestRecord:
    return next(
        record for record in dataset.manifest.records if record.split is CorpusSplit.VALIDATION
    )


def _coherently_false_dataset() -> PreparedDataset:
    dataset = _valid_dataset()
    prepared_records = tuple(
        prepared.model_copy(
            update={
                "record": prepared.record.model_copy(update={"model_selection_eligible": False})
            }
        )
        if prepared.split is CorpusSplit.VALIDATION
        else prepared
        for prepared in dataset.records
    )
    manifest_records = tuple(
        record.model_copy(update={"model_selection_eligible": False})
        if record.split is CorpusSplit.VALIDATION
        else record
        for record in dataset.manifest.records
    )
    manifest = DatasetManifest.model_construct(
        **{
            **dataset.manifest.model_dump(mode="python"),
            "dataset_id": "",
            "records_checksum": "",
            "records": manifest_records,
        }
    )
    records_checksum = content_checksum(
        sorted(
            (record.model_dump(mode="json") for record in manifest_records),
            key=lambda record: str(record["record_id"]),
        )
    )
    report = dataset.report.model_copy(update={"dataset_records_checksum": records_checksum})
    manifest = manifest.model_copy(
        update={
            "records_checksum": records_checksum,
            "report_checksum": content_checksum(report.model_dump(mode="json")),
        }
    )
    manifest_checksum = content_checksum(
        {
            "manifest_version": manifest.manifest_version,
            "parents": sorted(manifest.parent_dataset_ids),
            "record_schema_version": manifest.record_schema_version,
            "normalization_version": manifest.normalization_version,
            "config_checksum": manifest.config_checksum,
            "records_checksum": records_checksum,
            "decisions_checksum": manifest.decisions_checksum,
            "report_checksum": manifest.report_checksum,
            "records": sorted(
                (record.model_dump(mode="json") for record in manifest_records),
                key=lambda record: str(record["record_id"]),
            ),
        }
    )
    manifest = manifest.model_copy(update={"dataset_id": f"dataset-{manifest_checksum[:20]}"})
    return dataset.model_copy(
        update={"records": prepared_records, "manifest": manifest, "report": report}
    )


def _forge_readdressed_snapshot_with_ineligible_validation(output: Path) -> str:
    snapshot_fixtures._export_real_snapshot(output)
    source_path = output / "dataset-manifest.source.json"
    report_path = output / "preparation-report.json"
    snapshot_path = output / "snapshot-manifest.json"

    source = json.loads(source_path.read_text(encoding="utf-8"))
    validation_id = ""
    for record in source["records"]:
        if record["split"] == "VALIDATION":
            validation_id = str(record["record_id"])
            record["model_selection_eligible"] = False
    assert validation_id
    ordered_records = sorted(source["records"], key=lambda record: str(record["record_id"]))
    records_checksum = content_checksum(ordered_records)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["dataset_records_checksum"] = records_checksum
    source["records_checksum"] = records_checksum
    source["report_checksum"] = content_checksum(report)
    manifest_checksum = content_checksum(
        {
            "manifest_version": source["manifest_version"],
            "parents": sorted(source["parent_dataset_ids"]),
            "record_schema_version": source["record_schema_version"],
            "normalization_version": source["normalization_version"],
            "config_checksum": source["config_checksum"],
            "records_checksum": records_checksum,
            "decisions_checksum": source["decisions_checksum"],
            "report_checksum": source["report_checksum"],
            "records": ordered_records,
        }
    )
    source["dataset_id"] = f"dataset-{manifest_checksum[:20]}"
    source_path.write_text(
        json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    snapshot["dataset_id"] = source["dataset_id"]
    snapshot["source_records_checksum"] = records_checksum
    snapshot["files"]["dataset-manifest.source.json"] = {
        "sha256": source_sha,
        "size_bytes": source_path.stat().st_size,
    }
    snapshot["files"]["preparation-report.json"] = {
        "sha256": report_sha,
        "size_bytes": report_path.stat().st_size,
    }
    snapshot["source_manifest"].update(
        {
            "sha256": source_sha,
            "dataset_id": source["dataset_id"],
            "manifest_checksum": manifest_checksum,
            "records_checksum": records_checksum,
            "preparation_report_sha256": report_sha,
        }
    )
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    snapshot_fixtures._resign_snapshot(snapshot_path)
    return validation_id


def test_validation_training_eligibility_requires_model_selection_at_record_boundary() -> None:
    valid = _validation_prepared(_valid_dataset()).record
    forged = valid.model_copy(update={"model_selection_eligible": False})

    with pytest.raises(ValueError, match=r"VALIDATION.*model[_-]selection"):
        SupervisedRecord.model_validate(forged.model_dump(mode="python"))


def test_train_training_eligibility_remains_independent_of_model_selection() -> None:
    train = next(record for record in _valid_dataset().records if record.split is CorpusSplit.TRAIN)

    reconstructed = SupervisedRecord.model_validate(train.record.model_dump(mode="python"))

    assert reconstructed.training_eligible is True
    assert reconstructed.model_selection_eligible is False


def test_validation_requires_model_selection_at_prepared_and_manifest_boundaries() -> None:
    dataset = _valid_dataset()
    prepared = _validation_prepared(dataset)
    forged_prepared = prepared.model_copy(
        update={"record": prepared.record.model_copy(update={"model_selection_eligible": False})}
    )
    manifest = _validation_manifest(dataset)
    forged_manifest = manifest.model_copy(update={"model_selection_eligible": False})

    with pytest.raises(ValueError, match=r"VALIDATION.*model[_-]selection"):
        PreparedRecord.model_validate(forged_prepared.model_dump(mode="python"))
    with pytest.raises(ValueError, match=r"VALIDATION.*model[_-]selection"):
        ManifestRecord.model_validate(forged_manifest.model_dump(mode="python"))


def test_dataset_manifest_rejects_coherently_false_validation_membership() -> None:
    dataset = _valid_dataset()
    records = tuple(
        record.model_copy(update={"model_selection_eligible": False})
        if record.split is CorpusSplit.VALIDATION
        else record
        for record in dataset.manifest.records
    )
    forged = dataset.manifest.model_copy(
        update={"dataset_id": "", "records_checksum": "", "records": records}
    )

    with pytest.raises(ValueError, match=r"VALIDATION.*model[_-]selection"):
        DatasetManifest.model_validate(forged.model_dump(mode="python"))


def test_prepared_dataset_reconstruction_and_export_reject_coherent_false_mutation(
    tmp_path: Path,
) -> None:
    forged = _coherently_false_dataset()

    with pytest.raises(ValueError, match=r"VALIDATION.*model[_-]selection"):
        PreparedDataset.model_validate(forged.model_dump(mode="python"))
    with pytest.raises(runtime.MLXPipelineError, match=r"VALIDATION.*model-selection"):
        export_mlx_dataset(forged, tmp_path / "forged")


def test_runtime_validation_ids_require_both_eligibility_flags() -> None:
    dataset = _valid_dataset()
    records = tuple(
        record.model_copy(update={"model_selection_eligible": False})
        if record.split is CorpusSplit.VALIDATION
        else record
        for record in dataset.manifest.records
    )
    forged = dataset.manifest.model_copy(update={"records": records})

    split_ids = runtime._source_manifest_split_ids(forged)

    assert split_ids["train"] == ("a-train",)
    assert split_ids["valid"] == ()


def test_readdressed_ineligible_validation_snapshot_stops_before_checkpoint_use(
    tmp_path: Path,
) -> None:
    output = tmp_path / "snapshot"
    validation_id = _forge_readdressed_snapshot_with_ineligible_validation(output)
    semantic_continuation: list[str] = []

    with pytest.raises(runtime.MLXPipelineError, match=r"VALIDATION.*model[_-]selection"):
        runtime.validate_mlx_dataset(output)
        semantic_continuation.extend(("validation-loss", "early-stopping", "best-checkpoint"))

    assert validation_id == "valid"
    assert semantic_continuation == []
