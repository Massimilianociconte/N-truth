"""Tests for SourceData lockfile, counts, and revision-bound identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.data.datasets.sourcedata import (
    SOURCE_DATA_EXPECTED_SPLIT_COUNTS,
    SourceDataError,
    _preserve_sourcedata_semantics,
    build_sourcedata_record_id,
    install_sourcedata,
    load_sourcedata_lockfile,
    validate_sourcedata_split_counts,
)
from ntruth.data.fs import sha256_file


def test_load_sourcedata_lockfile():
    lock = load_sourcedata_lockfile()
    assert lock["repository"] == "EMBO/SourceData"
    assert lock["semantic_version"] == "2.0.3"
    assert lock["revision"] == "04333ae21badc91671a537e875bbca61b62f87e3"
    assert lock["historical_unresolvable_revision"] == ("b457c14041b61c56f671c6f966b4324f682855b7")
    assert lock["relock_evidence"] == (
        "all_six_locked_sha256_and_sizes_match_current_official_revision"
    )
    assert len(lock["files"]) == 6
    assert all(len(f["sha256"]) == 64 for f in lock["files"])


def test_verified_sourcedata_counts_match_locked_upstream_bytes():
    assert SOURCE_DATA_EXPECTED_SPLIT_COUNTS == {
        "train": 60266,
        "validation": 8201,
        "test": 6696,
    }
    assert sum(SOURCE_DATA_EXPECTED_SPLIT_COUNTS.values()) == 75163


def test_sourcedata_count_validation_fails_closed_on_record_loss():
    with pytest.raises(SourceDataError, match="train: expected 60266, found 60265"):
        validate_sourcedata_split_counts({"train": 60265, "validation": 8201, "test": 6696})


def test_sourcedata_record_identity_is_revision_and_content_bound():
    first = build_sourcedata_record_id(
        revision="abc123",
        split="train",
        physical_line_number=7,
        words=["Cells", "treated"],
    )
    repeated = build_sourcedata_record_id(
        revision="abc123",
        split="train",
        physical_line_number=7,
        words=["Cells", "treated"],
    )
    changed = build_sourcedata_record_id(
        revision="abc123",
        split="train",
        physical_line_number=7,
        words=["Cells", "untreated"],
    )

    assert first == repeated
    assert first != changed
    assert first.startswith("sourcedata:abc123:train:7:")


def test_sourcedata_preserves_original_text_and_configuration_metadata_losslessly():
    ner_record = {
        "words": ["B", "-", "D", "Left", "ventricular"],
        "text": "B-D Left ventricular",
        "is_category": [0, 0, 0, 1],
    }
    roles_record = {
        "words": ["B", "-", "D", "Left", "ventricular"],
        "text": "B-D Left ventricular",
        "is_category": [0, 0, 0, 0, 0],
    }

    original_text, source_metadata = _preserve_sourcedata_semantics(
        ner_record=ner_record,
        roles_record=roles_record,
    )

    assert original_text == "B-D Left ventricular"
    assert source_metadata == {
        "configurations": {
            "ner": {"is_category": [0, 0, 0, 1]},
            "roles_multi": {"is_category": [0, 0, 0, 0, 0]},
        },
        "transformation": {
            "is_category": "preserved_opaque_not_mapped_to_tag_mask",
            "original_text": "shared_exact_upstream_text",
        },
    }


@pytest.mark.parametrize(
    ("ner_record", "roles_record", "error"),
    [
        (
            {"text": "one", "is_category": [0]},
            {"text": "two", "is_category": [0]},
            "original text mismatch",
        ),
        (
            {"text": "one"},
            {"text": "one", "is_category": [0]},
            "missing is_category",
        ),
    ],
)
def test_sourcedata_semantic_preservation_fails_closed(
    ner_record: dict[str, object],
    roles_record: dict[str, object],
    error: str,
):
    with pytest.raises(SourceDataError, match=error):
        _preserve_sourcedata_semantics(
            ner_record=ner_record,
            roles_record=roles_record,
        )


def test_install_sourcedata_writes_blocked_processed_snapshot_not_training_export(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    files = [
        {
            "path": f"token_classification/v_2.0.3/{task}/{split}.jsonl",
            "sha256": "a" * 64,
        }
        for task in ("ner", "roles_multi")
        for split in ("train", "validation", "test")
    ]
    monkeypatch.setattr(
        "ntruth.data.datasets.sourcedata.load_sourcedata_lockfile",
        lambda: {
            "repository": "EMBO/SourceData",
            "semantic_version": "2.0.3",
            "revision": "revision-1",
            "files": files,
        },
    )

    def fake_download(
        repo_id: str,
        revision: str,
        file_path_relative: str,
        destination: Path,
        expected_sha256: str,
        refresh: bool = False,
    ) -> str:
        del repo_id, revision, expected_sha256, refresh
        task = file_path_relative.split("/")[-2]
        labels = ["B-ENTITY", "O"] if task == "ner" else ["B-CONTROLLED_VAR", "O"]
        is_category = [1] if task == "ner" else [0, 1]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "words": ["Cells", "grew"],
                    "labels": labels,
                    "is_category": is_category,
                    "text": "Cells, grew.",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return sha256_file(destination)

    monkeypatch.setattr(
        "ntruth.data.datasets.sourcedata.download_sourcedata_file",
        fake_download,
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.sourcedata.validate_sourcedata_split_counts",
        lambda counts: None,
    )

    report = install_sourcedata(tmp_path)

    processed_root = tmp_path / "processed" / "sourcedata" / "v2.0.3" / "multitask"
    train_record = json.loads(
        (processed_root / "train" / "records.jsonl").read_text(encoding="utf-8")
    )
    test_record = json.loads(
        (processed_root / "test" / "records.jsonl").read_text(encoding="utf-8")
    )
    source_inputs = processed_root / "train" / "source_inputs.json"

    assert not (tmp_path / "training_ready").exists()
    assert train_record["eligibility"] == {
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": False,
    }
    assert train_record["provenance"]["sha256"] == sha256_file(source_inputs)
    assert train_record["payload"]["original_text"] == "Cells, grew."
    assert train_record["payload"]["normalized_text"] == "Cells grew"
    assert train_record["payload"]["tag_mask"] is None
    assert train_record["payload"]["source_metadata"] == {
        "configurations": {
            "ner": {"is_category": [1]},
            "roles_multi": {"is_category": [0, 1]},
        },
        "transformation": {
            "is_category": "preserved_opaque_not_mapped_to_tag_mask",
            "original_text": "shared_exact_upstream_text",
        },
    }
    assert train_record["split"]["group_id"] == test_record["split"]["group_id"]
    assert train_record["record_id"] != test_record["record_id"]
    assert report["model_use_status"] == "BLOCKED"
    assert report["training_ready_status"] == "NOT_MATERIALIZED"
    assert report["paper_level_leakage_claim_allowed"] is False
    assert report["semantic_preservation"] == {
        "original_text": "payload.original_text",
        "is_category": "payload.source_metadata.configurations",
        "is_category_mapped_to_tag_mask": False,
    }
