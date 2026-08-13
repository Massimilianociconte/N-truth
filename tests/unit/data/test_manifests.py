"""Tests for datasets, files, splits, and prevalence manifests generation."""

from __future__ import annotations

import json
from pathlib import Path

from ntruth.data.manifests import (
    generate_merkle_manifest,
    generate_split_prevalence_report,
    generate_splits_manifest,
)


def test_generate_splits_manifest(tmp_path: Path):
    split_mappings = {
        "SourceData": {"train": 100, "validation": 10, "test": 10},
        "PreClinIE": {"train": 80, "validation": 10, "test": 10},
    }
    generate_splits_manifest(split_mappings, tmp_path)
    res = json.loads((tmp_path / "splits.json").read_text())
    assert res["seed"] == "20260803"
    assert "SourceData" in res["mappings"]


def test_generate_split_prevalence_report(tmp_path: Path):
    records_by_split = {
        "train": [
            {"payload": {"entity_tags": ["O", "B-SMALL_MOLECULE"]}},
            {"payload": {"role_tags": ["O", "B-CONTROLLED_VAR"]}},
        ],
        "validation": [
            {"payload": {"entity_tags": ["O", "B-SMALL_MOLECULE"]}},
        ],
        "test": [],
    }
    report_file = tmp_path / "split_prevalence_report.json"
    generate_split_prevalence_report(records_by_split, report_file)
    data = json.loads(report_file.read_text())
    labels = {item["label"]: item for item in data["labels"]}
    assert "B-SMALL_MOLECULE" in labels
    assert labels["B-SMALL_MOLECULE"]["train_count"] == 1
    assert labels["B-SMALL_MOLECULE"]["validation_count"] == 1


def test_generate_merkle_manifest_persists_canonical_file_entries(tmp_path: Path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    raw.mkdir()
    processed.mkdir()
    (raw / "sample.txt").write_bytes(b"raw")
    (processed / "sample.txt").write_bytes(b"processed")
    destination = tmp_path / "manifests" / "checksums" / "merkle_manifest.json"

    merkle_root = generate_merkle_manifest([raw, processed], destination)

    data = json.loads(destination.read_text(encoding="utf-8"))
    assert data["schema_version"] == "ntruth.canonical-files.v1"
    assert data["file_count"] == 2
    assert data["files"] == [
        {
            "path": "processed/sample.txt",
            "sha256": "58190ffabf981aa3956f64e7fb6c336b181e7145950a37f4ce6d761a81f5d083",
            "size_bytes": 9,
        },
        {
            "path": "raw/sample.txt",
            "sha256": "d7439bee24773bcbfa2d0a97947ee36227b10d1022b1a55847e928965bb6bfde",
            "size_bytes": 3,
        },
    ]
    assert data["merkle_root"] == merkle_root
