"""Manifests generation for dataset inventory, files registry, splits, licenses, and Merkle roots."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from ntruth.data.fs import atomic_write_json, atomic_write_text, calculate_merkle_root, sha256_file


def generate_datasets_manifest(reports: Sequence[Mapping[str, Any]], destination: Path) -> None:
    data = {
        "generated_at_utc": "2026-08-03T00:00:00Z",
        "datasets": {rep["dataset"]: rep for rep in reports},
    }
    atomic_write_json(destination / "datasets.json", data)


def generate_files_manifest(file_entries: Sequence[Mapping[str, Any]], destination: Path) -> None:
    lines = [json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in file_entries]
    atomic_write_text(destination / "files.jsonl", "".join(lines))


def generate_splits_manifest(split_mappings: Mapping[str, Mapping[str, str]], destination: Path) -> None:
    data = {
        "seed": "20260803",
        "mappings": split_mappings,
    }
    atomic_write_json(destination / "splits.json", data)


def generate_split_prevalence_report(
    records_by_split: Mapping[str, Sequence[Mapping[str, Any]]],
    destination: Path,
) -> None:
    """Generates label total_count, train_count, val_count, test_count, and prevalence."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"train": 0, "validation": 0, "test": 0, "total": 0})

    for split_name, records in records_by_split.items():
        if split_name not in {"train", "validation", "test"}:
            continue
        for rec in records:
            payload = rec.get("payload", {})
            labels: set[str] = set()
            if "entity_tags" in payload and payload["entity_tags"]:
                labels.update(t for t in payload["entity_tags"] if t != "O")
            if "role_tags" in payload and payload["role_tags"]:
                labels.update(t for t in payload["role_tags"] if t != "O")
            if "labels" in payload and payload["labels"]:
                labels.update(payload["labels"])

            for lbl in labels:
                counts[lbl][split_name] += 1
                counts[lbl]["total"] += 1

    report_entries = []
    for lbl in sorted(counts.keys()):
        c = counts[lbl]
        tot = c["total"] or 1
        entry = {
            "label": lbl,
            "total_count": c["total"],
            "train_count": c["train"],
            "validation_count": c["validation"],
            "test_count": c["test"],
            "train_prevalence": round(c["train"] / tot, 4),
            "validation_prevalence": round(c["validation"] / tot, 4),
            "test_prevalence": round(c["test"] / tot, 4),
        }
        report_entries.append(entry)

    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(destination, {"labels": report_entries})


def generate_merkle_manifest(canonical_dirs: list[Path], destination: Path) -> str:
    merkle_root = calculate_merkle_root(canonical_dirs)
    manifest_data = {
        "merkle_root": merkle_root,
        "canonical_directories": [str(d) for d in canonical_dirs],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(destination, manifest_data)
    return merkle_root
