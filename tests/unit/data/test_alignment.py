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
