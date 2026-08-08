from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import ntruth.governance as governance
import ntruth.training.mlx_inference as inference
import ntruth.training.mlx_runtime as runtime
from ntruth.governance.lineage import CorpusSplit
from ntruth.mvt_a.stage_schema import (
    FORBIDDEN_FINAL_FIELDS,
    ParserCandidateBundle,
    StageCompletionStatus,
    StageCoverage,
    StageErrorCode,
)
from ntruth.mvt_a.verifier import hard_verify_candidates, hard_verify_candidates_v7
from ntruth.parser_ai.adapter import run_parser_adapter
from ntruth.parser_ai.contract import (
    GoldParserTarget,
    ParserAIDocumentInput,
    ParserAIInput,
    ParserCandidateOutput,
)
from ntruth.schemas.core import content_checksum
from ntruth.training.mlx_dataset import create_runtime_smoke_dataset
from ntruth.training.preparation import prepare_dataset
from ntruth.training.records import (
    AnnotationStatus,
    DatasetManifest,
    ManifestRecord,
    PreparedDataset,
    SupervisedRecord,
    SupervisionProvenance,
)


def _candidate_payload(
    *,
    status: str = "COMPLETE",
    covered: tuple[str, ...] = ("file-a", "file-b"),
    missing: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "contract_version": "8.0.0",
        "experiment_blocks": [
            {
                "block_id": "block-a",
                "title": "Block A",
                "evidence_ids": ["ev-a"],
                "confidence": 0.9,
            }
        ],
        "evidence_spans": [
            {
                "evidence_id": "ev-a",
                "file_id": "file-a",
                "evidence_type": "AUTHOR_ASSERTION",
                "text": "a",
                "confidence": 0.9,
                "start": 0,
                "end": 1,
            }
        ],
        "candidate_nodes": [
            {
                "node_id": "node-a",
                "block_id": "block-a",
                "node_type": {"value": "CellCulture"},
                "label": "culture",
                "evidence_ids": ["ev-a"],
                "confidence": 0.9,
            }
        ],
        "coverage": {
            "status": status,
            "covered_artifact_ids": list(covered),
            "missing_artifact_ids": list(missing),
            "rationale": "Explicit request coverage fixture.",
        },
        "model_metadata": {
            "adapter_name": "fixture",
            "model_name": "fixture-model",
            "model_version": "1",
            "prompt_template_version": "candidate-v8",
        },
    }


def _request() -> ParserAIInput:
    return ParserAIInput(
        documents=(
            ParserAIDocumentInput(file_id="file-a", filename="a.txt", sha256="a" * 64, text="a"),
            ParserAIDocumentInput(file_id="file-b", filename="b.txt", sha256="b" * 64, text="b"),
        )
    )


@dataclass
class _Adapter:
    response: Any
    name: str = "fixture-adapter"
    version: str = "1"

    def parse(self, _request: ParserAIInput) -> Any:
        return self.response


def test_stage_coverage_is_non_vacuous_and_exactly_reconciled_to_request() -> None:
    with pytest.raises(ValueError, match=r"COMPLETE|covered"):
        StageCoverage(status="COMPLETE", rationale="Nothing was listed.")
    with pytest.raises(ValueError, match=r"PARTIAL|missing"):
        StageCoverage(status="PARTIAL", covered_artifact_ids=("file-a",), rationale="Partial.")

    omitted = ParserCandidateOutput.model_validate(
        _candidate_payload(covered=("file-a",), missing=())
    )
    stage = run_parser_adapter(_Adapter(omitted), _request())
    assert stage.status is StageCompletionStatus.FAILED
    assert stage.errors[0].code is StageErrorCode.CHUNK_COVERAGE_INCOMPLETE
    assert set(stage.coverage.missing_artifact_ids) == {"file-a", "file-b"}
    assert stage.preserved_artifact_ids == ("file-a",)


def test_unqualified_hard_verifier_is_v8_only_and_v7_is_explicitly_exported() -> None:
    legacy = ParserCandidateBundle(notes=("legacy abstention",))
    with pytest.raises(TypeError, match=r"v8|ParserCandidateOutput"):
        hard_verify_candidates(legacy)  # type: ignore[arg-type]
    assert hard_verify_candidates_v7(legacy).passed is True
    assert governance is not None  # keep the public-surface import exercised
    package = __import__("ntruth.mvt_a", fromlist=["hard_verify_candidates_v7"])
    assert package.hard_verify_candidates_v7 is hard_verify_candidates_v7


@pytest.mark.parametrize(
    ("collection", "item"),
    (
        (
            "factors",
            {
                "factor_id": "node-a",
                "block_id": "block-a",
                "name": "factor",
                "levels": ["control", "treated"],
                "allocation_level": None,
                "application_level": None,
                "evidence_ids": ["ev-a"],
                "confidence": 0.8,
            },
        ),
        (
            "endpoints",
            {
                "endpoint_id": "node-a",
                "block_id": "block-a",
                "name": "endpoint",
                "evidence_ids": ["ev-a"],
                "confidence": 0.8,
            },
        ),
        (
            "candidate_counts",
            {
                "count_id": "node-a",
                "block_id": "block-a",
                "kind": "reported_count_candidate",
                "candidate_value": 4,
                "raw_text": "four cultures",
                "evidence_ids": ["ev-a"],
                "confidence": 0.8,
            },
        ),
        (
            "candidate_events",
            {
                "event_id": "node-a",
                "block_id": "block-a",
                "event_type": "candidate exposure",
                "participant_candidate_ids": ["node-a"],
                "evidence_ids": ["ev-a"],
                "confidence": 0.8,
            },
        ),
        (
            "candidate_graphs",
            {
                "graph_id": "node-a",
                "block_id": "block-a",
                "candidate_node_ids": ["node-a"],
                "evidence_ids": ["ev-a"],
                "confidence": 0.8,
            },
        ),
    ),
)
def test_candidate_ids_are_globally_unique_across_active_types(
    collection: str, item: dict[str, Any]
) -> None:
    payload = _candidate_payload()
    payload[collection] = [item]
    with pytest.raises(ValueError, match=r"candidate.*duplic|global|unique"):
        ParserCandidateOutput.model_validate(payload)


def _gold_target() -> GoldParserTarget:
    candidate = ParserCandidateOutput.model_validate(_candidate_payload())
    return GoldParserTarget(
        candidate_target=candidate,
        adjudication_id="adj-1",
        reviewer_ids=("reviewer-a", "reviewer-b"),
        adjudication_rationale="Two independent submissions were reconciled.",
        submission_references=(
            {
                "submission_id": "submission-a",
                "submission_sha256": "a" * 64,
                "reviewer_id": "reviewer-a",
                "reviewer_role": "wet-lab",
            },
            {
                "submission_id": "submission-b",
                "submission_sha256": "b" * 64,
                "reviewer_id": "reviewer-b",
                "reviewer_role": "statistical-methods",
            },
        ),
        comparison_status="AGREED",
        material_differences=(),
    )


def _supervised_record() -> SupervisedRecord:
    target = _gold_target()
    return SupervisedRecord(
        record_id="record-1",
        task="parser_candidate_v8",
        language="en",
        input_text=ParserAIInput(metadata={"record": "record-1"}).model_dump_json(),
        target=target,
        provenance=SupervisionProvenance(
            source_id="source-1",
            source_asset_id="asset-1",
            source_sha256="c" * 64,
            governance_hash="d" * 64,
            study_family_id="study-1",
            document_lineage_id="document-1",
            license_or_authorization_id="license-1",
            guideline_version="8.0.0",
            reviewer_count=2,
            reviewer_ids=target.reviewer_ids,
            reviewer_roles=("wet-lab", "statistical-methods"),
            adjudication_id=target.adjudication_id,
        ),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=True,
        split=CorpusSplit.TRAIN,
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("candidate_target_checksum", "f" * 64),
        ("submission_ids", ("other-a", "other-b")),
        ("submission_checksums", ("e" * 64, "f" * 64)),
        ("comparison_status", "CONFLICT_ADJUDICATED"),
        ("material_differences_checksum", "e" * 64),
    ),
)
def test_prepared_dataset_cross_checks_every_gold_manifest_pin(
    field: str, replacement: Any
) -> None:
    dataset = prepare_dataset((_supervised_record(),))
    raw_manifest = dataset.manifest.model_dump(mode="json")
    raw_manifest["dataset_id"] = ""
    raw_manifest["records_checksum"] = ""
    raw_manifest["records"][0][field] = replacement
    mutated = DatasetManifest.model_validate(raw_manifest)
    raw_report = dataset.report.model_dump(mode="json")
    raw_report["dataset_records_checksum"] = mutated.records_checksum
    report = type(dataset.report).model_validate(raw_report)

    with pytest.raises(ValueError, match=r"manifest incoerente|gold|target"):
        PreparedDataset(records=dataset.records, manifest=mutated, report=report)


def _source_manifest(
    *,
    record_ids: tuple[str, ...] = ("protected-1",),
    evaluation_eligible: bool = True,
    release_eligible: bool = True,
) -> DatasetManifest:
    entries = tuple(
        ManifestRecord(
            record_id=record_id,
            record_checksum=hashlib.sha256(f"record:{record_id}".encode()).hexdigest(),
            input_checksum=hashlib.sha256(f"input:{record_id}".encode()).hexdigest(),
            candidate_target_checksum=hashlib.sha256(f"target:{record_id}".encode()).hexdigest(),
            exact_fingerprint=hashlib.sha256(f"exact:{record_id}".encode()).hexdigest(),
            near_fingerprint=hashlib.sha256(f"near:{record_id}".encode()).hexdigest(),
            split=CorpusSplit.TEST,
            leakage_group_id=f"group:{record_id}",
            source_id="source-1",
            source_asset_id=record_id,
            source_sha256="a" * 64,
            governance_hash="b" * 64,
            annotation_status=AnnotationStatus.CANDIDATE,
            training_eligible=False,
            evaluation_eligible=evaluation_eligible,
            release_eligible=release_eligible,
            model_selection_eligible=False,
            reviewer_count=0,
        )
        for record_id in record_ids
    )
    return DatasetManifest(
        record_schema_version="8.0.0",
        normalization_version="1.0.0",
        config_checksum="c" * 64,
        decisions_checksum="d" * 64,
        report_checksum="e" * 64,
        records=entries,
    )


def _write_protected_snapshot(
    root: Path,
    *,
    payload_ids: tuple[str, ...] = ("protected-1",),
    source_ids: tuple[str, ...] = ("protected-1",),
    evaluation_eligible: bool = True,
    release_eligible: bool = True,
) -> tuple[Path, Path, Any]:
    from ntruth.training.protected_evaluation import ProtectedEvaluationSnapshotManifest

    root.mkdir()
    payload = root / "test.jsonl"
    payload.write_text(
        "".join(json.dumps({"record_id": record_id}) + "\n" for record_id in payload_ids),
        encoding="utf-8",
    )
    source = _source_manifest(
        record_ids=source_ids,
        evaluation_eligible=evaluation_eligible,
        release_eligible=release_eligible,
    )
    source_path = root.parent / f"{root.name}-source-dataset-manifest.json"
    source_path.write_text(
        json.dumps(source.model_dump(mode="json"), sort_keys=True), encoding="utf-8"
    )
    manifest = ProtectedEvaluationSnapshotManifest(
        split="TEST",
        purpose="CUSTODIAL_EVALUATION",
        payload_file="test.jsonl",
        payload_sha256=runtime.sha256_file(payload),
        payload_size_bytes=payload.stat().st_size,
        record_count=len(payload_ids),
        record_ids_checksum=content_checksum(sorted(payload_ids)),
        lineage={
            "source_manifest_id": source.dataset_id,
            "source_manifest_sha256": runtime.sha256_file(source_path),
            "planned_design_artifact_id": "planned-1",
            "planned_design_artifact_sha256": "1" * 64,
            "executed_design_artifact_id": "executed-1",
            "executed_design_artifact_sha256": "2" * 64,
            "custody_reference_id": "custody-1",
            "custody_reference_sha256": "3" * 64,
        },
    )
    (root / "protected-evaluation-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True), encoding="utf-8"
    )
    return payload, source_path, manifest


def test_protected_test_resolves_source_manifest_and_exact_membership(tmp_path: Path) -> None:
    from ntruth.training.protected_evaluation import validate_protected_evaluation_snapshot

    payload, source_path, manifest = _write_protected_snapshot(tmp_path / "valid")
    verified = validate_protected_evaluation_snapshot(
        payload.parent, declared_split="TEST", source_manifest_path=source_path
    )
    assert verified.snapshot_id == manifest.snapshot_id

    mismatched, mismatched_source, _ = _write_protected_snapshot(
        tmp_path / "mismatched", payload_ids=("protected-1",), source_ids=("protected-2",)
    )
    with pytest.raises(runtime.MLXPipelineError, match=r"membership|record.*IDs"):
        validate_protected_evaluation_snapshot(
            mismatched.parent,
            declared_split="TEST",
            source_manifest_path=mismatched_source,
        )


def test_protected_test_requires_planned_and_executed_run_pins(tmp_path: Path) -> None:
    payload, source_path, _ = _write_protected_snapshot(tmp_path / "protected")
    with pytest.raises(runtime.MLXPipelineError, match=r"planned_design|executed_design"):
        inference._verify_evaluation_snapshot(
            payload,
            "test",
            {
                "run_dataset_snapshot_id": "training-1",
                "run_dataset_snapshot_sha256": "a" * 64,
                "run_dataset_manifest_sha256": "b" * 64,
                "protected_source_manifest_path": str(source_path),
                "smoke_test": False,
            },
        )


def test_protected_release_uses_protected_not_training_snapshot_pins() -> None:
    validator = getattr(inference, "validate_protected_release_lineage", None)
    assert callable(validator), "protected release validator must be an explicit boundary"
    source = _source_manifest()
    manifest = {
        "split": "TEST",
        "snapshot_id": "protected-1",
        "snapshot_sha256": "a" * 64,
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
        "protected_evaluation": manifest,
        "source_dataset_manifest": source.model_dump(mode="json"),
    }
    run = {
        "run_dataset_snapshot_id": "training-distinct",
        "run_dataset_snapshot_sha256": "e" * 64,
        "planned_design_artifact_id": "planned-1",
        "planned_design_artifact_sha256": "c" * 64,
        "executed_design_artifact_id": "executed-1",
        "executed_design_artifact_sha256": "d" * 64,
    }
    pins = validator(
        metrics_snapshot=snapshot,
        calibration_snapshot={"snapshot_sha256": "e" * 64},
        run_lineage=run,
    )
    assert pins["protected_snapshot_sha256"] == "a" * 64
    assert pins["training_snapshot_sha256"] == "e" * 64


def _manifest_extra_snapshot(data_dir: Path) -> Path:
    create_runtime_smoke_dataset(data_dir)
    protected = data_dir / "test.jsonl"
    protected.write_text("PROTECTED-SENTINEL\n", encoding="utf-8")
    manifest_path = data_dir / "snapshot-manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["files"]["test.jsonl"] = {
        "sha256": runtime.sha256_file(protected),
        "size_bytes": protected.stat().st_size,
    }
    raw["snapshot_id"] = ""
    raw["snapshot_sha256"] = ""
    digest, snapshot_id = runtime._snapshot_identity(raw)
    raw["snapshot_sha256"] = digest
    raw["snapshot_id"] = snapshot_id
    manifest_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    return protected


def test_training_schema_owns_exact_files_and_never_opens_manifested_protected_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    protected = _manifest_extra_snapshot(data_dir)
    original = runtime.sha256_file
    opened: list[Path] = []

    def tracked(path: Path, **kwargs: Any) -> str:
        opened.append(path.resolve())
        return original(path, **kwargs)

    monkeypatch.setattr(runtime, "sha256_file", tracked)
    with pytest.raises(runtime.MLXPipelineError, match=r"schema|allowlist|unexpected"):
        runtime.validate_snapshot_integrity(data_dir, smoke_test=True)
    assert protected.resolve() not in opened


def _replace_staged_file(path: Path) -> None:
    path.parent.chmod(0o755)
    path.chmod(0o644)
    replacement = path.with_suffix(".replacement")
    replacement.write_text("{}\n", encoding="utf-8")
    os.replace(replacement, path)


def test_post_staging_replacement_is_rejected_at_training_consumer_boundary(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "source"
    create_runtime_smoke_dataset(data_dir)
    verified = runtime.validate_snapshot_integrity(data_dir, smoke_test=True)
    staged = runtime.stage_verified_training_view(
        data_dir,
        tmp_path / "staged",
        verified_snapshot=verified,
        smoke_test=True,
    )
    _replace_staged_file(Path(str(staged["path"])) / "train.jsonl")
    verifier = getattr(runtime, "verify_staged_training_view", None)
    assert callable(verifier), "training consumer needs an explicit staged-view verifier"
    with pytest.raises(runtime.MLXPipelineError, match=r"changed|checksum|replacement"):
        verifier(Path(str(staged["path"])), staged["file_hashes"])


def test_post_staging_replacement_is_rejected_before_tokenizer_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "source"
    create_runtime_smoke_dataset(data_dir)
    verified = runtime.validate_snapshot_integrity(data_dir, smoke_test=True)
    staged = runtime.stage_verified_training_view(
        data_dir,
        tmp_path / "staged",
        verified_snapshot=verified,
        smoke_test=True,
    )
    _replace_staged_file(Path(str(staged["path"])) / "train.jsonl")
    model_calls: list[bool] = []
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"model")
    monkeypatch.setattr(
        inference,
        "load_profile",
        lambda _path: {"data": {"max_sequence_length": 1024}},
    )

    def model_path(*_args: Any) -> Path:
        model_calls.append(True)
        return model_dir

    monkeypatch.setattr(inference, "_model_path", model_path)
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=lambda *_a, **_k: None)),
    )
    with pytest.raises(runtime.MLXPipelineError, match=r"changed|checksum|replacement"):
        inference._tokenize_verified_report(
            tmp_path / "profile.json",
            tmp_path,
            Path(str(staged["path"])),
            tmp_path / "report.json",
            verified,
        )
    assert model_calls == []


def _legacy_snapshot_payload(split: str) -> dict[str, Any]:
    return {
        "schema_version": "7.0.0",
        "parser_contract_version": "2.0.0",
        "guideline_version": "7.0.0",
        "ontology_version": "7.0.0",
        "assets": [
            {
                "asset_id": "asset-1",
                "sha256": "a" * 64,
                "governance_hash": "b" * 64,
                "bundle_id": "bundle-1",
                "bundle_checksum": "c" * 64,
                "split": split,
                "leakage_group_ids": ["group-1"],
            }
        ],
        "leakage_groups": [
            {"group_id": "group-1", "kind": "article_family", "asset_ids": ["asset-1"]}
        ],
    }


def test_v7_external_migration_is_typed_review_required_and_public() -> None:
    legacy_type = governance.CorpusSnapshotManifestV7
    migrate = governance.migrate_corpus_snapshot_manifest_v7_to_v8
    review_type = governance.LineageMigrationReviewRequired
    legacy = legacy_type.model_validate(_legacy_snapshot_payload("external"))
    result = migrate(legacy)
    assert isinstance(result, review_type)
    assert result.status == "SCIENTIFIC_REVIEW_REQUIRED"
    assert "EXTERNAL" in result.blocked_splits
    assert not hasattr(result, "target")


def test_v7_internal_split_migration_remains_unambiguous_and_public() -> None:
    legacy = governance.CorpusSnapshotManifestV7.model_validate(_legacy_snapshot_payload("train"))
    result = governance.migrate_corpus_snapshot_manifest_v7_to_v8(legacy)
    assert result.target.assets[0].split is CorpusSplit.TRAIN


@pytest.mark.parametrize(
    "alias",
    (
        "artifact_id",
        "artifact_sha256",
        "privacy_attestation_sha256",
        "no_corpus_attestation_sha256",
    ),
)
def test_resume_rejects_bare_aliases_and_alias_canonical_collisions(alias: str) -> None:
    artifact = runtime.build_training_reality_gate_v8_artifact(
        snapshot_id="snapshot-1",
        snapshot_sha256="a" * 64,
        privacy_attestation_sha256="b" * 64,
        no_corpus_attestation_sha256="c" * 64,
        authorized=True,
        issued_by="untrusted-test",
    )
    pins = runtime.RealityGatePinTuple.from_artifact(artifact)
    state = {
        "reality_gate_artifact_id": pins.artifact_id,
        "reality_gate_artifact_sha256": pins.artifact_sha256,
        "reality_gate_privacy_attestation_sha256": pins.privacy_attestation_sha256,
        "reality_gate_no_corpus_attestation_sha256": pins.no_corpus_attestation_sha256,
        alias: "collision",
    }
    with pytest.raises(runtime.MLXPipelineError, match=r"alias|canonical|duplicate"):
        runtime.reconcile_reality_gate_pins(state, pins)


def test_resume_accepts_only_complete_canonical_pin_schema() -> None:
    artifact = runtime.build_training_reality_gate_v8_artifact(
        snapshot_id="snapshot-1",
        snapshot_sha256="a" * 64,
        privacy_attestation_sha256="b" * 64,
        no_corpus_attestation_sha256="c" * 64,
        authorized=True,
        issued_by="untrusted-test",
    )
    pins = runtime.RealityGatePinTuple.from_artifact(artifact)
    state = {
        "reality_gate_artifact_id": pins.artifact_id,
        "reality_gate_artifact_sha256": pins.artifact_sha256,
        "reality_gate_privacy_attestation_sha256": pins.privacy_attestation_sha256,
        "reality_gate_no_corpus_attestation_sha256": pins.no_corpus_attestation_sha256,
    }
    runtime.reconcile_reality_gate_pins(state, pins)


def _canonical_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                keys.add(key.casefold())
            keys.update(_canonical_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(_canonical_keys(item))
    return keys


def test_candidate_and_gold_dump_recursive_keys_exclude_every_final_field() -> None:
    dumps = (
        ParserCandidateOutput.model_validate(_candidate_payload()).model_dump(mode="json"),
        _gold_target().model_dump(mode="json"),
    )
    for dumped in dumps:
        assert _canonical_keys(dumped).isdisjoint(FORBIDDEN_FINAL_FIELDS)
