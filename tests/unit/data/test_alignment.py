"""Tests for SourceData NER ↔ ROLES_MULTI join key alignment."""

from __future__ import annotations

from ntruth.data.alignment import align_sourcedata_configs


def test_align_sourcedata_configs_matching():
    ner = [
        {"panel_id": "p1", "words": ["Cells", "glucose"], "labels": ["O", "B-SMALL_MOLECULE"], "split": "train"},
        {"panel_id": "p2", "words": ["Mice", "saline"], "labels": ["B-SPECIES", "B-CONTROL"], "split": "train"},
    ]
    roles = [
        {"panel_id": "p1", "words": ["Cells", "glucose"], "labels": ["O", "B-CONTROLLED_VAR"], "split": "train"},
        {"panel_id": "p2", "words": ["Mice", "saline"], "labels": ["O", "B-CONTROLLED_VAR"], "split": "train"},
    ]

    aligned, report = align_sourcedata_configs(ner, roles)
    assert len(aligned) == 2
    assert report["matched_count"] == 2
    assert report["ner_only_count"] == 0
    assert report["roles_only_count"] == 0
    assert aligned[0]["entity_tags"] == ["O", "B-SMALL_MOLECULE"]
    assert aligned[0]["role_tags"] == ["O", "B-CONTROLLED_VAR"]


def test_align_sourcedata_configs_unmatched():
    ner = [
        {"panel_id": "p1", "words": ["Cells"], "labels": ["O"], "split": "train"},
        {"panel_id": "p_only_ner", "words": ["Word"], "labels": ["O"], "split": "train"},
    ]
    roles = [
        {"panel_id": "p1", "words": ["Cells"], "labels": ["O"], "split": "train"},
    ]

    aligned, report = align_sourcedata_configs(ner, roles)
    assert len(aligned) == 1
    assert report["ner_only_count"] == 1


def test_align_sourcedata_configs_excludes_label_token_length_mismatch():
    """Fail-closed: labels length must equal words length on both NER and ROLES sides."""
    ner = [
        {
            "panel_id": "ok",
            "words": ["Cells", "glucose"],
            "labels": ["O", "B-X"],
            "split": "train",
        },
        {
            "panel_id": "bad_ner",
            "words": ["Mice", "saline"],
            "labels": ["B-SPECIES"],  # shorter than words
            "split": "train",
        },
    ]
    roles = [
        {
            "panel_id": "ok",
            "words": ["Cells", "glucose"],
            "labels": ["O", "B-Y"],
            "split": "train",
        },
        {
            "panel_id": "bad_ner",
            "words": ["Mice", "saline"],
            "labels": ["O", "B-CONTROL"],
            "split": "train",
        },
    ]

    aligned, report = align_sourcedata_configs(ner, roles)

    assert len(aligned) == 1
    assert aligned[0]["panel_id"] == "ok"
    assert report["matched_count"] == 1
    assert report["label_length_mismatches"] == 1
    assert report["label_length_checked"] is True
    assert report["excluded_count_by_reason"]["label_length_mismatches"] == 1


def test_align_sourcedata_configs_excludes_roles_label_length_mismatch():
    ner = [
        {"words": ["a", "b"], "labels": ["O", "B-X"], "split": "train"},
    ]
    roles = [
        {"words": ["a", "b"], "labels": ["O", "B-Y", "EXTRA"], "split": "train"},
    ]

    aligned, report = align_sourcedata_configs(ner, roles)

    assert aligned == []
    assert report["matched_count"] == 0
    assert report["label_length_mismatches"] == 1
    assert report["label_length_checked"] is True
