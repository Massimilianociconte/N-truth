from __future__ import annotations

from pathlib import Path

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput, ParserCandidateOutput
from ntruth.training.manifest import build_manifest_records
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.mlx_runtime import validate_snapshot_integrity
from ntruth.training.preparation import prepare_dataset
from ntruth.training.records import (
    AnnotationStatus,
    DatasetManifest,
    ManifestRecord,
    PreparationConfig,
    PreparedRecord,
    SupervisedRecord,
    SupervisionProvenance,
)
from ntruth.training.splits import migrate_corpus_split_v7


def _gold_target() -> dict[str, object]:
    candidate = ParserCandidateOutput.model_validate(
        {
            "coverage": {
                "status": "PARTIAL",
                "missing_artifact_ids": ["not-reported"],
                "rationale": "Candidate-only fixture.",
            },
            "model_metadata": {
                "adapter_name": "fixture",
                "model_name": "fixture",
                "model_version": "1",
                "prompt_template_version": "candidate-v8",
            },
        }
    )
    return {
        "schema_version": "8.0.0",
        "candidate_target": candidate.model_dump(mode="json"),
        "adjudication_id": "adj-1",
        "reviewer_ids": ["reviewer-a", "reviewer-b"],
        "adjudication_rationale": "Submissions reconciled.",
        "submission_references": [
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
                "reviewer_role": "biostatistician",
            },
        ],
        "comparison_status": "AGREED",
        "material_differences": [],
    }


def _record(
    record_id: str,
    split: CorpusSplit,
    *,
    training: bool = False,
    evaluation: bool = False,
    model_selection: bool = False,
    input_text: str | None = None,
) -> SupervisedRecord:
    return SupervisedRecord(
        record_id=record_id,
        task="parser_candidate_v8",
        language="en",
        input_text=input_text or ParserAIInput(metadata={"record": record_id}).model_dump_json(),
        target=_gold_target(),
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=(record_id[0] if record_id[0] in "abcdef" else "a") * 64,
            governance_hash="f" * 64,
            license_or_authorization_id="license-1",
            guideline_version="8.0.0",
            reviewer_count=2,
            reviewer_ids=("reviewer-a", "reviewer-b"),
            reviewer_roles=("wet-lab", "biostatistician"),
            adjudication_id="adj-1",
            study_family_id=f"study-{record_id}",
            document_lineage_id=f"document-{record_id}",
            external_challenge_dependency=(
                {
                    "review_status": "SCIENTIFIC_REVIEW_REQUIRED",
                    "task7_contamination_attestation_reference": {
                        "artifact_id": f"attestation-{record_id}",
                        "sha256": "c" * 64,
                    },
                    "custody_reference": {
                        "artifact_id": f"custody-{record_id}",
                        "sha256": "d" * 64,
                    },
                    "family_evidence_references": [
                        {
                            "artifact_id": f"family-{record_id}",
                            "sha256": "e" * 64,
                        }
                    ],
                }
                if split is CorpusSplit.EXTERNAL_CHALLENGE
                else None
            ),
        ),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=training,
        evaluation_eligible=evaluation and split is not CorpusSplit.EXTERNAL_CHALLENGE,
        model_selection_eligible=model_selection,
        split=split,
    )


def test_canonical_split_vocabulary_and_explicit_v7_external_adapter() -> None:
    assert {split.value for split in CorpusSplit} == {
        "UNASSIGNED",
        "TRAIN",
        "VALIDATION",
        "TEST",
        "EXTERNAL_CHALLENGE",
    }
    with pytest.raises(ValueError):
        CorpusSplit("external")
    assert migrate_corpus_split_v7("external") is CorpusSplit.EXTERNAL_CHALLENGE


@pytest.mark.parametrize("split", (CorpusSplit.TEST, CorpusSplit.EXTERNAL_CHALLENGE))
def test_protected_supervised_split_rejects_training_eligibility(split: CorpusSplit) -> None:
    with pytest.raises(ValueError, match="training_eligible"):
        _record("a-protected", split, training=True)


@pytest.mark.parametrize("split", (CorpusSplit.TEST, CorpusSplit.EXTERNAL_CHALLENGE))
def test_protected_split_rejects_model_selection_at_record_boundary(
    split: CorpusSplit,
) -> None:
    with pytest.raises(ValueError, match="model_selection_eligible"):
        _record(
            "a-challenge",
            split,
            evaluation=True,
            model_selection=True,
        )


@pytest.mark.parametrize("split", (CorpusSplit.TEST, CorpusSplit.EXTERNAL_CHALLENGE))
def test_prepared_and_manifest_boundaries_recheck_protected_training(split: CorpusSplit) -> None:
    corrupted = _record("a-base", CorpusSplit.TRAIN, training=True).model_copy(
        update={"split": split}
    )
    with pytest.raises(ValueError, match="training"):
        PreparedRecord(
            record=corrupted,
            normalized_input="fixture",
            canonical_target=corrupted.target.model_dump_json(),
            exact_fingerprint="a" * 64,
            near_fingerprint="b" * 64,
            leakage_group_id="leakage-1",
            split=split,
        )

    with pytest.raises(ValueError, match="training"):
        ManifestRecord(
            record_id="manifest-protected",
            record_checksum="a" * 64,
            input_checksum="f" * 64,
            candidate_target_checksum="f" * 64,
            exact_fingerprint="b" * 64,
            near_fingerprint="c" * 64,
            split=split,
            leakage_group_id="leakage-1",
            source_id="source",
            source_asset_id="asset",
            source_sha256="d" * 64,
            governance_hash="e" * 64,
            annotation_status=AnnotationStatus.ADJUDICATED,
            training_eligible=True,
            license_or_authorization_id="license",
            reviewer_count=2,
            adjudication_id="adj",
        )


@pytest.mark.parametrize("split", (CorpusSplit.TEST, CorpusSplit.EXTERNAL_CHALLENGE))
def test_prepared_and_manifest_boundaries_recheck_protected_model_selection(
    split: CorpusSplit,
) -> None:
    corrupted_record = _record(
        "a-base",
        CorpusSplit.TRAIN,
        model_selection=True,
    ).model_copy(update={"split": split})
    with pytest.raises(ValueError, match=r"model[_-]selection"):
        PreparedRecord(
            record=corrupted_record,
            normalized_input="fixture",
            canonical_target=corrupted_record.target.model_dump_json(),
            exact_fingerprint="a" * 64,
            near_fingerprint="b" * 64,
            leakage_group_id="leakage-1",
            split=split,
        )

    valid_manifest_record = ManifestRecord(
        record_id="manifest-protected",
        record_checksum="a" * 64,
        input_checksum="f" * 64,
        candidate_target_checksum="f" * 64,
        exact_fingerprint="b" * 64,
        near_fingerprint="c" * 64,
        split=CorpusSplit.TRAIN,
        leakage_group_id="leakage-1",
        source_id="source",
        source_asset_id="asset",
        source_sha256="d" * 64,
        governance_hash="e" * 64,
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=False,
        model_selection_eligible=True,
        license_or_authorization_id="license",
        reviewer_count=2,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        reviewer_roles=("wet-lab", "biostatistician"),
        adjudication_id="adj",
        target_adjudication_id="adj",
        submission_ids=("submission-a", "submission-b"),
        submission_checksums=("a" * 64, "b" * 64),
        comparison_status="AGREED",
        material_differences_checksum="c" * 64,
    )
    corrupted_manifest_record = valid_manifest_record.model_copy(update={"split": split})
    with pytest.raises(ValueError, match=r"model[_-]selection"):
        DatasetManifest(
            record_schema_version="8.0.0",
            normalization_version="8.0.0",
            config_checksum="a" * 64,
            decisions_checksum="b" * 64,
            report_checksum="c" * 64,
            records=(corrupted_manifest_record,),
        )


def test_training_export_preserves_membership_but_never_reads_protected_content(
    tmp_path: Path,
) -> None:
    protected = "PROTECTED-SENTINEL-MUST-NOT-BE-READ"
    records = (
        _record("a-train", CorpusSplit.TRAIN, training=True),
        _record(
            "b-valid",
            CorpusSplit.VALIDATION,
            training=True,
            model_selection=True,
        ),
        _record(
            "c-test",
            CorpusSplit.TEST,
            evaluation=True,
            input_text=ParserAIInput(
                metadata={"protected_sentinel": protected + "-test"}
            ).model_dump_json(),
        ),
        _record(
            "d-challenge",
            CorpusSplit.EXTERNAL_CHALLENGE,
            evaluation=True,
            input_text=ParserAIInput(
                metadata={"protected_sentinel": protected + "-challenge"}
            ).model_dump_json(),
        ),
    )
    dataset = prepare_dataset(
        records,
        config=PreparationConfig(),
    )

    assert len(build_manifest_records(dataset.records)) == 4
    output = tmp_path / "training-view"
    snapshot = export_mlx_dataset(dataset, output)

    assert set(snapshot["counts"]) == {"train", "valid"}
    assert snapshot["membership_counts"]["TEST"] == 1
    assert snapshot["membership_counts"]["EXTERNAL_CHALLENGE"] == 1
    assert not (output / "test.jsonl").exists()
    assert not (output / "external.jsonl").exists()
    assert not (output / "prepared-records.jsonl").exists()
    integrity = validate_snapshot_integrity(output)
    assert integrity["counts"] == {"train": 1, "valid": 1}
    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in output.iterdir() if path.is_file()
    )
    assert protected not in serialized


def test_supervised_target_recursively_rejects_final_verdict_alias() -> None:
    payload = _gold_target()
    payload["candidate_target"]["alternatives"] = [{"metadata": {"RuleResult": "forbidden"}}]
    with pytest.raises(ValueError, match="final field"):
        SupervisedRecord(
            record_id="a-final",
            task="parser_candidate_v8",
            language="en",
            input_text=ParserAIInput().model_dump_json(),
            target=payload,
            provenance=_record("a-source", CorpusSplit.UNASSIGNED).provenance,
        )
