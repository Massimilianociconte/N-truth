"""Tests for datasets, files, splits, and prevalence manifests generation."""

from __future__ import annotations

import json
from pathlib import Path

from ntruth.data.manifests import generate_split_prevalence_report, generate_splits_manifest


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
