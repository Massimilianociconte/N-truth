from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

import ntruth.training.mlx_inference as inference
import ntruth.training.mlx_runtime as runtime
from ntruth.governance import lineage
from ntruth.schemas.core import content_checksum
from ntruth.training.mlx_dataset import create_runtime_smoke_dataset
from ntruth.training.mlx_inference import _verify_evaluation_snapshot, tokenize_report
from ntruth.training.records import AnnotationStatus, DatasetManifest, ManifestRecord


def _protected_module() -> Any:
    from ntruth.training import protected_evaluation

    return protected_evaluation


def _write_protected_snapshot(
    tmp_path: Path,
    *,
    split: str = "TEST",
    rows: tuple[dict[str, Any], ...] | None = None,
    external_dependency: dict[str, Any] | None = None,
) -> tuple[Path, Path, Any]:
    protected = _protected_module()
    data_dir = tmp_path / f"protected-{split.lower()}"
    data_dir.mkdir()
    filename = "test.jsonl" if split == "TEST" else "external-challenge.jsonl"
    payload_rows = rows if rows is not None else ({"record_id": "protected-1"},)
    payload_path = data_dir / filename
    payload_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in payload_rows),
        encoding="utf-8",
    )
    source_records = tuple(
        ManifestRecord(
            record_id=str(row["record_id"]),
            record_checksum="1" * 64,
            input_checksum="2" * 64,
            candidate_target_checksum="3" * 64,
            exact_fingerprint="4" * 64,
            near_fingerprint="5" * 64,
            split=split,
            leakage_group_id=f"group-{row['record_id']}",
            source_id="source-1",
            source_asset_id=str(row["record_id"]),
            source_sha256="6" * 64,
            governance_hash="7" * 64,
            annotation_status=AnnotationStatus.CANDIDATE,
            training_eligible=False,
            evaluation_eligible=split == "TEST",
            release_eligible=split == "TEST",
            model_selection_eligible=False,
            reviewer_count=0,
            family_evidence=(
                {}
                if split == "TEST"
                else {
                    "study_family_id": "study-1",
                    "document_lineage_id": "document-1",
                }
            ),
            external_challenge_dependency=(None if split == "TEST" else external_dependency),
        )
        for row in payload_rows
    )
    source_manifest = DatasetManifest(
        record_schema_version="8.0.0",
        normalization_version="1.0.0",
        config_checksum="8" * 64,
        decisions_checksum="9" * 64,
        report_checksum="a" * 64,
        records=source_records,
    )
    source_path = tmp_path / f"source-{split.lower()}-dataset-manifest.json"
    source_path.write_text(
        json.dumps(source_manifest.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    manifest = protected.ProtectedEvaluationSnapshotManifest(
        split=split,
        purpose="CUSTODIAL_EVALUATION",
        payload_file=filename,
        payload_sha256=runtime.sha256_file(payload_path),
        payload_size_bytes=payload_path.stat().st_size,
        record_count=len(payload_rows),
        record_ids_checksum=content_checksum(sorted(str(row["record_id"]) for row in payload_rows)),
        lineage={
            "source_manifest_id": source_manifest.dataset_id,
            "source_manifest_sha256": runtime.sha256_file(source_path),
            "planned_design_artifact_id": "planned-1",
            "planned_design_artifact_sha256": "b" * 64,
            "executed_design_artifact_id": "executed-1",
            "executed_design_artifact_sha256": "c" * 64,
            "custody_reference_id": "custody-1",
            "custody_reference_sha256": "d" * 64,
        },
        external_challenge_dependency=external_dependency,
    )
    (data_dir / "protected-evaluation-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    return payload_path, source_path, manifest


def test_07_real_custodial_test_snapshot_validator_is_distinct_from_training(
    tmp_path: Path,
) -> None:
    payload_path, source_path, manifest = _write_protected_snapshot(tmp_path)
    protected = _protected_module()

    verified = protected.validate_protected_evaluation_snapshot(
        payload_path.parent,
        declared_split="TEST",
        source_manifest_path=source_path,
    )
    assert verified.snapshot_id == manifest.snapshot_id
    assert verified.record_count == 1
    with pytest.raises(runtime.MLXPipelineError, match=r"training|snapshot"):
        runtime.validate_snapshot_integrity(payload_path.parent)

    run_lineage = {
        "run_dataset_snapshot_id": "training-snapshot-1",
        "run_dataset_snapshot_sha256": "e" * 64,
        "run_dataset_manifest_sha256": "f" * 64,
        "planned_design_artifact_id": "planned-1",
        "planned_design_artifact_sha256": "b" * 64,
        "executed_design_artifact_id": "executed-1",
        "executed_design_artifact_sha256": "c" * 64,
        "protected_source_manifest_path": str(source_path),
        "protected_source_manifest_id": manifest.lineage.source_manifest_id,
        "protected_source_manifest_sha256": manifest.lineage.source_manifest_sha256,
        "smoke_test": False,
    }
    resolved, runtime_verified = _verify_evaluation_snapshot(
        payload_path,
        "test",
        run_lineage,
    )
    assert resolved == payload_path.resolve()
    assert runtime_verified["snapshot_id"] == manifest.snapshot_id


@pytest.mark.parametrize("entry_kind", ("test", "external", "symlink", "fifo"))
def test_08_training_snapshot_rejects_every_unmanifested_or_nonregular_entry(
    tmp_path: Path, entry_kind: str
) -> None:
    data_dir = tmp_path / entry_kind
    create_runtime_smoke_dataset(data_dir)
    if entry_kind == "test":
        (data_dir / "test.jsonl").write_text("{}\n", encoding="utf-8")
    elif entry_kind == "external":
        (data_dir / "external-challenge.jsonl").write_text("{}\n", encoding="utf-8")
    elif entry_kind == "symlink":
        (data_dir / "protected-link.jsonl").symlink_to(data_dir / "train.jsonl")
    else:
        os.mkfifo(data_dir / "protected.pipe")

    with pytest.raises(runtime.MLXPipelineError, match=r"allowlist|unmanifested|regular|symlink"):
        runtime.validate_snapshot_integrity(data_dir, smoke_test=True)


def test_08_verified_training_staging_detects_post_validation_replacement(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "source"
    create_runtime_smoke_dataset(data_dir)
    verified = runtime.validate_snapshot_integrity(data_dir, smoke_test=True)
    (data_dir / "train.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(runtime.MLXPipelineError, match=r"changed|stale|checksum"):
        runtime.stage_verified_training_view(
            data_dir,
            tmp_path / "run-owned",
            verified_snapshot=verified,
            smoke_test=True,
        )


def test_09_tokenization_validates_snapshot_before_model_or_payload_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "tokenize"
    create_runtime_smoke_dataset(data_dir)
    (data_dir / "test.jsonl").write_text("PROTECTED-SENTINEL\n", encoding="utf-8")
    model_calls: list[bool] = []

    def forbidden_model_path(*_args: Any, **_kwargs: Any) -> Path:
        model_calls.append(True)
        raise AssertionError("model boundary reached before snapshot validation")

    monkeypatch.setattr(inference, "_model_path", forbidden_model_path)
    with pytest.raises(runtime.MLXPipelineError, match=r"allowlist|unmanifested"):
        tokenize_report(
            tmp_path / "profile.json",
            tmp_path,
            data_dir,
            tmp_path / "report.json",
            smoke_test=True,
        )
    assert model_calls == []


def test_10_external_challenge_stays_review_required_without_task7_attestation(
    tmp_path: Path,
) -> None:
    dependency = {
        "review_status": "SCIENTIFIC_REVIEW_REQUIRED",
        "task7_contamination_attestation_reference": {
            "artifact_id": "attestation-1",
            "sha256": "a" * 64,
        },
        "custody_reference": {"artifact_id": "custody-1", "sha256": "b" * 64},
        "family_evidence_references": [{"artifact_id": "family-1", "sha256": "c" * 64}],
    }
    payload_path, source_path, _manifest = _write_protected_snapshot(
        tmp_path,
        split="EXTERNAL_CHALLENGE",
        external_dependency=dependency,
    )
    protected = _protected_module()

    with pytest.raises(
        protected.ExternalChallengeReviewRequired, match="SCIENTIFIC_REVIEW_REQUIRED"
    ):
        protected.validate_protected_evaluation_snapshot(
            payload_path.parent,
            declared_split="EXTERNAL_CHALLENGE",
            source_manifest_path=source_path,
        )


def test_11_historical_v7_lineage_uses_typed_one_way_migration() -> None:
    asset_payload = {
        "asset_id": "asset-1",
        "sha256": "a" * 64,
        "governance_hash": "b" * 64,
        "bundle_id": "bundle-1",
        "bundle_checksum": "c" * 64,
        "split": "train",
        "leakage_group_ids": ["group-1"],
    }
    manifest_payload = {
        "schema_version": "7.0.0",
        "parser_contract_version": "2.0.0",
        "guideline_version": "7.0.0",
        "ontology_version": "7.0.0",
        "assets": [asset_payload],
        "leakage_groups": [
            {"group_id": "group-1", "kind": "article_family", "asset_ids": ["asset-1"]}
        ],
    }
    legacy = lineage.CorpusSnapshotManifestV7.model_validate(manifest_payload)
    migrated = lineage.migrate_corpus_snapshot_manifest_v7_to_v8(legacy)
    assert migrated.source_checksum == legacy.snapshot_checksum()
    assert migrated.target.assets[0].split is lineage.CorpusSplit.TRAIN
    assert migrated.diagnostics[0].code == "LEGACY_V7_EXPLICIT_MIGRATION"
    with pytest.raises(ValueError):
        lineage.CorpusSnapshotManifest.model_validate(manifest_payload)

    run_payload = {
        "run_id": "run-1",
        "purpose": "training_declaration",
        "parser_contract_version": "2.0.0",
        "model_name": "model",
        "model_version": "1",
        "model_config_checksum": "d" * 64,
        "corpus_snapshot_id": legacy.snapshot_id,
        "corpus_snapshot_checksum": legacy.snapshot_checksum(),
        "input_splits": ["train", "external"],
        "schema_version": "7.0.0",
        "guideline_version": "7.0.0",
        "ontology_version": "7.0.0",
        "code_lock_checksum": "e" * 64,
        "seed": 7,
    }
    legacy_run = lineage.ModelRunLineageV7.model_validate(run_payload)
    migrated_run = lineage.migrate_model_run_lineage_v7_to_v8(legacy_run)
    assert isinstance(migrated_run, lineage.LineageMigrationReviewRequired)
    assert migrated_run.status == "SCIENTIFIC_REVIEW_REQUIRED"
    assert migrated_run.blocked_splits == ("EXTERNAL",)


def test_12_denied_gate_causes_zero_training_payload_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    snapshot = create_runtime_smoke_dataset(data_dir)
    artifact = runtime.build_training_reality_gate_v8_artifact(
        snapshot_id=str(snapshot["snapshot_id"]),
        snapshot_sha256=str(snapshot["snapshot_sha256"]),
        privacy_attestation_sha256="a" * 64,
        no_corpus_attestation_sha256="b" * 64,
        authorized=True,
        issued_by="self-issued-test",
    )
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(artifact.model_dump(mode="json")), encoding="utf-8")
    design_lineage = runtime.TrainingDesignLineagePins(
        planned_design_artifact_id="planned-1",
        planned_design_artifact_sha256="c" * 64,
        executed_design_artifact_id="executed-1",
        executed_design_artifact_sha256="d" * 64,
    )
    design_lineage_path = tmp_path / "task6-training-design-lineage.json"
    design_lineage_path.write_text(
        json.dumps(design_lineage.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    _, protected_source_manifest_path, _ = _write_protected_snapshot(tmp_path)
    payload_opens: list[Path] = []
    original_iter = runtime.iter_jsonl

    def guarded_iter(path: Path) -> Any:
        payload_opens.append(path)
        return original_iter(path)

    monkeypatch.setattr(runtime, "iter_jsonl", guarded_iter)
    with pytest.raises(runtime.MLXPipelineError, match=r"Task 7|authoritative|review"):
        runtime.run_training(
            tmp_path / "missing-profile.json",
            tmp_path,
            data_dir,
            tmp_path / "run",
            seed=7,
            smoke_test=True,
            reality_gate=runtime.FileRealityGateV8Protocol(gate_path),
            design_lineage_pins=design_lineage,
            design_lineage_artifact_path=design_lineage_path,
            protected_source_manifest_path=protected_source_manifest_path,
        )
    assert payload_opens == []


@pytest.mark.parametrize(
    "field",
    (
        "artifact_id",
        "artifact_sha256",
        "privacy_attestation_sha256",
        "no_corpus_attestation_sha256",
    ),
)
def test_13_resume_reconciles_complete_gate_pin_tuple(field: str) -> None:
    artifact = runtime.build_training_reality_gate_v8_artifact(
        snapshot_id="snapshot-1",
        snapshot_sha256="a" * 64,
        privacy_attestation_sha256="b" * 64,
        no_corpus_attestation_sha256="c" * 64,
        authorized=True,
        issued_by="untrusted-test",
    )
    pins = runtime.RealityGatePinTuple.from_artifact(artifact)
    state = pins.model_dump(mode="json")
    state[field] = "f" * 64 if field != "artifact_id" else "different-artifact"

    with pytest.raises(runtime.MLXPipelineError, match=field):
        runtime.reconcile_reality_gate_pins(state, pins)
