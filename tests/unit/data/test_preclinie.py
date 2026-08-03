"""Tests for PreClinIE group ID extraction and publication-level split logic."""

from __future__ import annotations

from ntruth.data.splits import preclinie_group_id, stable_split


def test_preclinie_group_normalization():
    assert preclinie_group_id("my_pdf1001_title") == "my_pdf1001"
    assert preclinie_group_id("my_pdf1001_abstract") == "my_pdf1001"
    assert preclinie_group_id("my_pdf1001_methods") == "my_pdf1001"


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
