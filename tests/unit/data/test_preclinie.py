"""Tests for PreClinIE group ID extraction and publication-level split logic."""

from __future__ import annotations

import csv
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from ntruth.data.config import PRECLINIE_VERSION
from ntruth.data.datasets.preclinie import PreClinIEError, _parse_list_field, install_preclinie
from ntruth.data.splits import preclinie_group_id, stable_split


def test_preclinie_group_normalization():
    assert preclinie_group_id("my_pdf1001_title") == "my_pdf1001"
    assert preclinie_group_id("my_pdf1001_abstract") == "my_pdf1001"
    assert preclinie_group_id("my_pdf1001_methods") == "my_pdf1001"


def test_preclinie_rejects_malformed_serialized_lists():
    with pytest.raises(PreClinIEError, match="tokens is not a valid serialized list"):
        _parse_list_field("['alpha,beta", field_name="tokens")


def test_preclinie_paper_grouping():
    doc_ids = [
        "my_pdf1_title",
        "my_pdf1_abstract",
        "my_pdf1_methods",
        "my_pdf2_title",
        "my_pdf2_abstract",
    ]
    groups = [preclinie_group_id(d) for d in doc_ids]

    split_map = stable_split(groups, seed="20260803", ratios=(80, 10, 10))
    # All segments of my_pdf1 must land in the exact same split
    assert (
        split_map[preclinie_group_id("my_pdf1_title")]
        == split_map[preclinie_group_id("my_pdf1_abstract")]
    )
    assert (
        split_map[preclinie_group_id("my_pdf1_abstract")]
        == split_map[preclinie_group_id("my_pdf1_methods")]
    )


def test_preclinie_excludes_and_reports_token_label_length_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    archive = tmp_path / "downloads" / f"preclinie-{PRECLINIE_VERSION}.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"fixture archive identity")
    monkeypatch.setattr(
        "ntruth.data.datasets.preclinie.ensure_pinned_archive",
        lambda *_args, **_kwargs: "pinned",
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.preclinie.ensure_pinned_archive_verified_copy",
        lambda *_args, **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.preclinie.resume_marker_matches",
        lambda *_args, **_kwargs: True,
    )

    raw_root = tmp_path / "raw" / "preclinie" / PRECLINIE_VERSION
    raw_root.mkdir(parents=True)
    (raw_root / ".ntruth_complete.json").write_text("{}\n", encoding="utf-8")
    token_csv = raw_root / "all_annotations_minimal_fixed_multi_tokens_tags.csv"
    rows = [
        {"doc_id": "paper_pdf1_abstract", "tokens": "['valid', 'row']", "ner_tags": "['O', 'B-X']"},
        {"doc_id": "paper_pdf2_abstract", "tokens": "['too', 'many']", "ner_tags": "['O']"},
        {"doc_id": "paper_pdf3_abstract", "tokens": "['one']", "ner_tags": "['O', 'B-X']"},
        {"doc_id": "paper_pdf4_abstract", "tokens": "['broken'", "ner_tags": "['O']"},
    ]
    with token_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doc_id", "tokens", "ner_tags"])
        writer.writeheader()
        writer.writerows(rows)

    report = install_preclinie(tmp_path)

    assert sum(report["split_counts"].values()) == 1
    processed_files = sorted(
        (tmp_path / "processed" / "preclinie" / PRECLINIE_VERSION).glob("*/records.jsonl")
    )
    processed = [
        json.loads(line)
        for path in processed_files
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert processed[0]["payload"]["tokens"] == ["valid", "row"]
    assert processed[0]["payload"]["entity_tags"] == ["O", "B-X"]
    assert processed[0]["eligibility"] == {
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": False,
    }
    assert report["model_use_status"] == "BLOCKED"
    assert report["training_ready_status"] == "NOT_MATERIALIZED"
    assert report["label_alignment"] == {
        "status": "PARTIAL",
        "input_rows": 4,
        "accepted_rows": 1,
        "excluded_rows": 3,
        "quarantine_path": (
            f"quarantine/preclinie/{PRECLINIE_VERSION}/annotation_row_issues.jsonl"
        ),
        "mismatches": [
            {
                "csv_line_number": 3,
                "document_id": "paper_pdf2_abstract",
                "token_count": 2,
                "entity_tag_count": 1,
                "reason": "TOKEN_LABEL_LENGTH_MISMATCH",
            },
            {
                "csv_line_number": 4,
                "document_id": "paper_pdf3_abstract",
                "token_count": 1,
                "entity_tag_count": 2,
                "reason": "TOKEN_LABEL_LENGTH_MISMATCH",
            },
        ],
        "parse_errors": [
            {
                "csv_line_number": 5,
                "document_id": "paper_pdf4_abstract",
                "reason": "INVALID_SERIALIZED_LIST",
                "detail": "tokens is not a valid serialized list",
                "raw_tokens": "['broken'",
                "raw_entity_tags": "['O']",
            }
        ],
    }

    quarantine = tmp_path / report["label_alignment"]["quarantine_path"]
    quarantined = [json.loads(line) for line in quarantine.read_text().splitlines()]
    assert [record["document_id"] for record in quarantined] == [
        "paper_pdf2_abstract",
        "paper_pdf3_abstract",
        "paper_pdf4_abstract",
    ]
    assert quarantined[0]["tokens"] == ["too", "many"]
    assert quarantined[0]["entity_tags"] == ["O"]


def test_preclinie_ties_connected_exact_content_families_to_one_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    archive = tmp_path / "downloads" / f"preclinie-{PRECLINIE_VERSION}.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"fixture archive identity")
    monkeypatch.setattr(
        "ntruth.data.datasets.preclinie.ensure_pinned_archive",
        lambda *_args, **_kwargs: "pinned",
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.preclinie.ensure_pinned_archive_verified_copy",
        lambda *_args, **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        "ntruth.data.datasets.preclinie.resume_marker_matches",
        lambda *_args, **_kwargs: True,
    )

    raw_root = tmp_path / "raw" / "preclinie" / PRECLINIE_VERSION
    raw_root.mkdir(parents=True)
    (raw_root / ".ntruth_complete.json").write_text("{}\n", encoding="utf-8")
    token_csv = raw_root / "all_annotations_minimal_fixed_multi_tokens_tags.csv"
    rows = [
        {
            "doc_id": "My_pdf1_title",
            "tokens": "['Shared', 'alpha']",
            "ner_tags": "['O', 'O']",
        },
        {
            "doc_id": "My_pdf1_abstract",
            "tokens": "['paper', 'one']",
            "ner_tags": "['O', 'O']",
        },
        {
            "doc_id": "My_pdf2_title",
            "tokens": "['shared', 'alpha']",
            "ner_tags": "['O', 'O']",
        },
        {
            "doc_id": "My_pdf2_abstract",
            "tokens": "['Bridge', 'beta']",
            "ner_tags": "['O', 'O']",
        },
        {
            "doc_id": "My_pdf3_title",
            "tokens": "['bridge', 'beta']",
            "ner_tags": "['O', 'O']",
        },
        {
            "doc_id": "My_pdf3_abstract",
            "tokens": "['paper', 'three']",
            "ner_tags": "['O', 'O']",
        },
        {
            "doc_id": "My_pdf4_title",
            "tokens": "['unique', 'four']",
            "ner_tags": "['O', 'O']",
        },
        {
            "doc_id": "My_pdf5_title",
            "tokens": "['unique', 'five']",
            "ner_tags": "['O', 'O']",
        },
    ]
    with token_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doc_id", "tokens", "ner_tags"])
        writer.writeheader()
        writer.writerows(rows)

    report = install_preclinie(tmp_path)

    processed_files = sorted(
        (tmp_path / "processed" / "preclinie" / PRECLINIE_VERSION).glob("*/records.jsonl")
    )
    records = [
        json.loads(line)
        for path in processed_files
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    by_document = {record["source"]["document_id"]: record for record in records}

    assert len(records) == len(rows)
    connected_documents = (
        "My_pdf1_title",
        "My_pdf1_abstract",
        "My_pdf2_title",
        "My_pdf2_abstract",
        "My_pdf3_title",
        "My_pdf3_abstract",
    )
    assert len({by_document[doc]["split"]["name"] for doc in connected_documents}) == 1
    assert len({by_document[doc]["split"]["group_id"] for doc in connected_documents}) == 1
    assert all(
        not record["eligibility"]["training_eligible"]
        and not record["eligibility"]["evaluation_eligible"]
        for record in records
    )
    assert report["grouping_key"] == "publication_id+exact_normalized_content_family"
    assert report["split_algorithm"] == (
        "stable_split 80/10/10 over connected exact-content publication families"
    )
    assert report["leakage_control"] == {
        "status": "PASS",
        "policy": "EXACT_NORMALIZED_CONTENT_ONLY_NOT_SEMANTIC_EQUIVALENCE",
        "publication_group_count": 5,
        "connected_family_count": 3,
        "multi_publication_family_count": 1,
        "largest_family_publication_count": 3,
        "duplicate_normalized_content_count": 2,
        "duplicate_record_count": 2,
        "cross_split_exact_content_leakage_count": 0,
    }
