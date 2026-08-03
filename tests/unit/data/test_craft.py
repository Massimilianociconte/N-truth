"""Tests for CRAFT PMCID discovery and official 67/30 partition validation."""

from __future__ import annotations

from pathlib import Path
from ntruth.data.config import get_manifests_dir
from ntruth.data.datasets.craft import extract_craft_article_id, load_craft_official_split
from ntruth.data.splits import load_craft_2019_shared_task_split


def test_extract_craft_article_id():
    assert extract_craft_article_id(Path("corpus/PMC1134658.txt")) == "PMC1134658"
    assert extract_craft_article_id(Path("concept_annotations/PMC1247630.xml")) == "PMC1247630"


def test_load_craft_2019_shared_task_split():
    manifest_path = get_manifests_dir() / "craft_shared_task_2019_split.json"
    authority, split_map = load_craft_2019_shared_task_split(manifest_path)
    assert authority == "craft_shared_task_2019"
    assert len(split_map) == 97

    train_count = sum(1 for s in split_map.values() if s == "train")
    val_count = sum(1 for s in split_map.values() if s == "validation")
    test_count = sum(1 for s in split_map.values() if s == "test")

    assert train_count + val_count == 67
    assert test_count == 30


def test_load_craft_official_split_from_upstream_identifier_files(tmp_path: Path):
    ids = tmp_path / "articles" / "ids"
    ids.mkdir(parents=True)
    (ids / "craft-idmappings.txt").write_text(
        "#Format: [FILE NAME] <tab> [PMCID] <tab> [PMID]\n"
        "one.nxml\tPMC1\t1\n"
        "two.nxml\tPMC2\t2\n"
        "three.nxml\tPMC3\t3\n"
    )
    (ids / "craft-ids-train.txt").write_text("1\n")
    (ids / "craft-ids-dev.txt").write_text("2\n")
    (ids / "craft-ids-test.txt").write_text("3\n")

    authority, split_map, evidence = load_craft_official_split(tmp_path)

    assert authority == "craft_shared_task_2019"
    assert split_map == {"PMC1": "train", "PMC2": "validation", "PMC3": "test"}
    assert evidence["source_counts"] == {"train": 1, "validation": 1, "test": 1}
