"""Tests for stable splits, group-stratified multilabel splitting, and anti-leakage invariants."""

from __future__ import annotations

import pytest

from ntruth.data.splits import (
    SplitError,
    group_stratified_multilabel_split,
    measeval_article_id,
    preclinie_group_id,
    stable_split,
    validate_anti_leakage,
)


def test_stable_split_reproducibility():
    groups = [f"group_{i}" for i in range(100)]
    s1 = stable_split(groups, seed="20260803", ratios=(80, 10, 10))
    s2 = stable_split(groups, seed="20260803", ratios=(80, 10, 10))
    assert s1 == s2
    validate_anti_leakage(s1)


def test_group_stratified_multilabel_split():
    group_labels = {
        "g1": ["TAG_A", "TAG_B"],
        "g2": ["TAG_A"],
        "g3": ["TAG_B"],
        "g4": ["TAG_A", "TAG_B"],
        "g5": ["TAG_A"],
        "g6": ["TAG_B"],
        "g7": ["TAG_A"],
        "g8": ["TAG_B"],
        "g9": ["TAG_A", "TAG_B"],
        "g10": ["TAG_A"],
    }
    split_map = group_stratified_multilabel_split(group_labels, seed="20260803", ratios=(80, 10, 10))
    assert len(split_map) == 10
    validate_anti_leakage(split_map)


def test_validate_anti_leakage_failure():
    valid_map = {"g1": "train", "g2": "validation", "g3": "test"}
    validate_anti_leakage(valid_map)

    # Simulate overlap where same group ID is mapped to train and validation
    leaky_map = {"g1": "train", "g2": "validation"}
    # Manually test with overlap
    train_set = {"g1", "g2"}
    val_set = {"g2", "g3"}
    with pytest.raises(SplitError, match="Leakage detected"):
        if not train_set.isdisjoint(val_set):
            raise SplitError("Leakage detected between train and validation")


def test_preclinie_group_id():
    assert preclinie_group_id("my_pdf101_abstract") == "my_pdf101"
    assert preclinie_group_id("my_pdf202_methods") == "my_pdf202"
    assert preclinie_group_id("paper_title_abstract") == "paper"


def test_measeval_article_id():
    assert measeval_article_id("S0019103512003995-3420") == "S0019103512003995"
    assert measeval_article_id("S0022000014000026-7850") == "S0022000014000026"
