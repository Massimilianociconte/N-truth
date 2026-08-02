"""Tests for CRAFT PMCID discovery and official 67/30 partition validation."""

from __future__ import annotations

from pathlib import Path
from ntruth.data.config import get_manifests_dir
from ntruth.data.datasets.craft import extract_craft_article_id
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
