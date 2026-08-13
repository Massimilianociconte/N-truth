"""Machine-readable readiness / split-authority fields for public auxiliary datasets."""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from ntruth.data.alignment import align_sourcedata_configs
from ntruth.data.config import MEASEVAL_VERSION
from ntruth.data.datasets.craft import load_craft_official_split
from ntruth.data.datasets.measeval import install_measeval


def _write_measeval_tsv(path: Path, document_id: str) -> None:
    path.write_text(
        "docId\tannotSet\tannotType\tstartOffset\tendOffset\tannotId\ttext\tother\n"
        f"{document_id}\t1\tQuantity\t19\t24\tT1\t13 kg\t"
        '{"unit": "kg"}\n'
        f"{document_id}\t1\tMeasuredEntity\t4\t10\tT2\tsample\t"
        '{"HasQuantity": "T1"}\n',
        encoding="utf-8",
    )


def _build_measeval_fixture(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = root / "downloads" / f"measeval-{MEASEVAL_VERSION}.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"fixture archive identity")
    monkeypatch.setattr(
        "ntruth.data.datasets.measeval.ensure_pinned_archive",
        lambda *_args, **_kwargs: "pinned",
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.measeval.ensure_pinned_archive_verified_copy",
        lambda *_args, **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.measeval.resume_marker_matches",
        lambda *_args, **_kwargs: True,
    )

    raw_root = root / "raw" / "measeval" / MEASEVAL_VERSION
    raw_root.mkdir(parents=True)
    (raw_root / ".ntruth_complete.json").write_text("{}", encoding="utf-8")
    data_root = raw_root / "data"
    for partition, text_dir_name in (("train", "text"), ("eval", "text"), ("trial", "txt")):
        (data_root / partition / text_dir_name).mkdir(parents=True)
        (data_root / partition / "tsv").mkdir(parents=True)

    annotated_text = "The sample weighed 13 kg."
    train_id = "S0016236113008041-100"
    eval_id = "S0016236113008041-200"
    missing_train_id = "S9999999999999999-100"
    missing_eval_id = "S8888888888888888-100"
    trial_id = "S7777777777777777-100"

    for partition, text_dir_name, document_id in (
        ("train", "text", train_id),
        ("train", "text", missing_train_id),
        ("eval", "text", eval_id),
        ("eval", "text", missing_eval_id),
        ("trial", "txt", trial_id),
    ):
        (data_root / partition / text_dir_name / f"{document_id}.txt").write_text(
            annotated_text, encoding="utf-8"
        )

    _write_measeval_tsv(data_root / "train" / "tsv" / f"{train_id}.tsv", train_id)
    _write_measeval_tsv(data_root / "eval" / "tsv" / f"{eval_id}.tsv", eval_id)
    _write_measeval_tsv(data_root / "trial" / "tsv" / f"{trial_id}.tsv", trial_id)


def _read_processed_records(root: Path) -> list[dict[str, object]]:
    processed = root / "processed" / "measeval" / MEASEVAL_VERSION
    records: list[dict[str, object]] = []
    for path in sorted(processed.glob("*/records.jsonl")):
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return records


def test_alignment_report_marks_counts_as_derived_multitask_not_upstream_split():
    ner = [{"words": ["a", "b"], "labels": ["O", "B-X"]}]
    roles = [{"words": ["a", "b"], "labels": ["O", "B-Y"]}]
    aligned, report = align_sourcedata_configs(ner, roles)
    assert len(aligned) == 1
    assert report["matched_count"] == 1
    assert report["counts_are_derived_multitask"] is True
    join_key = report["join_key"]
    assert isinstance(join_key, dict)
    assert join_key["source_configuration"] == "token_classification/v_2.0.3"
    assert join_key["source_record_index"] == "0-based_physical_line_index_within_split_file"
    assert "words_sha256" in join_key
    assert join_key["revision_bound"] is True
    assert join_key["stable_across_revisions"] is False
    assert join_key["panel_id_field_present"] is False
    assert report["label_length_checked"] is True


def test_craft_official_split_maps_dev_to_validation_not_as_official_three_way(tmp_path: Path):
    ids = tmp_path / "articles" / "ids"
    ids.mkdir(parents=True)
    # 67+30 would be full corpus; miniature mapping still proves train/dev/test roles
    mapping_lines = ["#Format: [FILE NAME]\t[PMCID]\t[PMID]\n"]
    train_pmids, dev_pmids, test_pmids = [], [], []
    for i in range(1, 61):
        mapping_lines.append(f"t{i}.nxml\tPMC{i}\t{i}\n")
        train_pmids.append(str(i))
    for i in range(61, 68):
        mapping_lines.append(f"d{i}.nxml\tPMC{i}\t{i}\n")
        dev_pmids.append(str(i))
    for i in range(100, 130):
        mapping_lines.append(f"e{i}.nxml\tPMC{i}\t{i}\n")
        test_pmids.append(str(i))
    (ids / "craft-idmappings.txt").write_text("".join(mapping_lines))
    (ids / "craft-ids-train.txt").write_text("\n".join(train_pmids) + "\n")
    (ids / "craft-ids-dev.txt").write_text("\n".join(dev_pmids) + "\n")
    (ids / "craft-ids-test.txt").write_text("\n".join(test_pmids) + "\n")

    authority, split_map, evidence = load_craft_official_split(tmp_path)
    assert authority == "craft_shared_task_2019"
    assert evidence["source_counts"] == {"train": 60, "validation": 7, "test": 30}
    assert sum(1 for s in split_map.values() if s == "train") == 60
    assert sum(1 for s in split_map.values() if s == "validation") == 7
    assert sum(1 for s in split_map.values() if s == "test") == 30
    # zero PMCID overlap across roles
    by = {"train": set(), "validation": set(), "test": set()}
    for pmcid, split in split_map.items():
        by[split].add(pmcid)
    assert not (by["train"] & by["validation"])
    assert not (by["train"] & by["test"])
    assert not (by["validation"] & by["test"])


def test_measeval_install_marks_every_missing_tsv_record_review_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _build_measeval_fixture(tmp_path, monkeypatch)

    install_measeval(tmp_path)

    records = _read_processed_records(tmp_path)
    missing = [
        record for record in records if record["annotation_status"] == "missing_annotation_file"
    ]
    assert {record["source"]["segment_id"] for record in missing} == {  # type: ignore[index]
        "S9999999999999999-100",
        "S8888888888888888-100",
    }
    for record in missing:
        assert record["native_annotation_tier"] == "MISSING_ANNOTATION"
        assert record["eligibility"] == {
            "training_eligible": False,
            "evaluation_eligible": False,
            "requires_review": True,
        }


def test_measeval_processed_records_are_never_model_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _build_measeval_fixture(tmp_path, monkeypatch)

    report = install_measeval(tmp_path)

    for record in _read_processed_records(tmp_path):
        eligibility = record["eligibility"]
        assert eligibility["training_eligible"] is False  # type: ignore[index]
        assert eligibility["evaluation_eligible"] is False  # type: ignore[index]
    assert report["model_use_status"] == "BLOCKED"
    assert report["model_use_blockers"] == [
        "canonical_task_corpus_adapter_not_validated",
        "license_training_use_not_adjudicated",
    ]


def test_measeval_install_reconciles_upstream_overlap_without_group_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _build_measeval_fixture(tmp_path, monkeypatch)
    stale_training_ready = tmp_path / "training_ready" / "measeval" / MEASEVAL_VERSION
    stale_training_ready.mkdir(parents=True)
    (stale_training_ready / "stale.jsonl").write_text("stale", encoding="utf-8")
    legacy_trial = (
        tmp_path / "processed" / "measeval" / MEASEVAL_VERSION / "trial" / "records.jsonl"
    )
    legacy_trial.parent.mkdir(parents=True)
    legacy_trial.write_text("legacy trial representation\n", encoding="utf-8")

    report = install_measeval(tmp_path)

    assert report["training_ready_status"] == "BLOCKED_BY_MODEL_USE_GATES"
    assert report["training_ready_present"] is False
    assert report["article_overlap"] == {
        "has_overlap": True,
        "pairs": {
            "train_validation": {"count": 0, "article_ids": []},
            "train_test": {
                "count": 1,
                "article_ids": ["S0016236113008041"],
            },
            "validation_test": {"count": 0, "article_ids": []},
            "train_trial": {"count": 0, "article_ids": []},
            "validation_trial": {"count": 0, "article_ids": []},
            "test_trial": {"count": 0, "article_ids": []},
        },
    }
    assert report["split_authority"] == "ntruth_measeval_article_family_v1"
    assert report["split_counts"] == {"train": 1, "validation": 0, "test": 4}
    assert report["split_reconciliation"]["model_development_group_leakage_count"] == 0
    reconciliation_manifest = report["split_reconciliation_manifest"]
    reconciliation_path = Path(reconciliation_manifest["path"])
    assert reconciliation_path.is_file()
    assert (
        hashlib.sha256(reconciliation_path.read_bytes()).hexdigest()
        == reconciliation_manifest["sha256"]
    )
    assert report["split_reconciliation"]["source_partition_counts"] == {
        "train": 2,
        "eval": 2,
        "trial": 1,
    }
    assert report["split_reconciliation"]["source_partition_to_ntruth_split_counts"] == {
        "train": {"train": 1, "validation": 0, "test": 1},
        "eval": {"train": 0, "validation": 0, "test": 2},
        "trial": {"train": 0, "validation": 0, "test": 1},
    }

    records = _read_processed_records(tmp_path)
    splits_by_group: dict[str, set[str]] = {}
    for record in records:
        split = record["split"]
        splits_by_group.setdefault(split["group_id"], set()).add(split["name"])  # type: ignore[index]
    assert all(len(splits) == 1 for splits in splits_by_group.values())

    shared_family_records = [
        record
        for record in records
        if record["source"]["document_id"] == "S0016236113008041"  # type: ignore[index]
    ]
    assert len(shared_family_records) == 2
    assert {record["split"]["name"] for record in shared_family_records} == {"test"}  # type: ignore[index]

    trial_records = [
        record for record in records if record["annotation_status"] == "format_smoke_test"
    ]
    assert len(trial_records) == 1
    assert trial_records[0]["split"]["name"] == "test"  # type: ignore[index]
    assert trial_records[0]["eligibility"] == {
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": False,
    }
    assert report["native_annotation_tier_counts"] == {
        "HUMAN_CURATED_GOLD": 2,
        "HUMAN_CURATED_PARTIAL": 1,
        "MISSING_ANNOTATION": 2,
    }
    assert not stale_training_ready.exists()
    quarantined = (
        tmp_path / "quarantine" / "training_ready" / "measeval" / MEASEVAL_VERSION / "stale.jsonl"
    )
    assert quarantined.read_text(encoding="utf-8") == "stale"
    assert report["stale_training_ready_quarantined_to"] == str(quarantined.parent)
    quarantined_trial = (
        tmp_path
        / "quarantine"
        / "processed"
        / "measeval"
        / MEASEVAL_VERSION
        / "legacy-upstream-trial-split"
        / "records.jsonl"
    )
    assert quarantined_trial.read_text(encoding="utf-8") == "legacy trial representation\n"
    assert report["legacy_processed_trial_quarantined_to"] == str(quarantined_trial.parent)

    repeated_report = install_measeval(tmp_path)

    assert repeated_report == report
