"""Unit tests for SourceData → entity_roles conversion."""

from __future__ import annotations

import json
from pathlib import Path

from ntruth.task_corpora.adapters.sourcedata_entity_roles import (
    build_sourcedata_entity_roles,
    convert_source_record,
    load_label_map,
)
from ntruth.task_corpora.authority import ExclusionReason
from ntruth.task_corpora.license_loader import load_license_decision


def _source_rec(
    tokens: list[str],
    entity: list[str],
    roles: list[str],
    *,
    record_id: str = "sd:1",
    document_id: str = "docA",
) -> dict:
    return {
        "record_id": record_id,
        "source": {
            "dataset": "SourceData",
            "version": "2.0.3",
            "commit": "b457c140",
            "document_id": document_id,
            "segment_id": "seg1",
        },
        "split": {"name": "train", "authority": "upstream_official", "group_id": document_id},
        "payload": {
            "kind": "token_classification",
            "tokens": tokens,
            "entity_tags": entity,
            "role_tags": roles,
            "normalized_text": " ".join(tokens),
            "token_offsets": None,
        },
    }


def test_convert_happy_path():
    lic = load_license_decision("sourcedata")
    label_map = load_label_map()
    rec, excl = convert_source_record(
        _source_rec(
            ["the", "gene", "x"],
            ["O", "B-GENEPROD", "O"],
            ["O", "B-MEASURED_VAR", "O"],
        ),
        split="train",
        source_path="training_ready/sourcedata_multitask/train/records.jsonl",
        parent_sha="00" * 32,
        license_decision=lic,
        label_map=label_map,
        line_no=1,
    )
    assert excl is None
    assert rec is not None
    assert rec.authority_level.value == "AUXILIARY"
    assert rec.training_eligible is False  # licence training_allowed false
    assert rec.payload.entity_labels == ["O", "B-GENEPROD", "O"]
    assert rec.payload.role_labels == ["O", "B-MEASURED_VAR", "O"]
    assert "experimental_unit_gold" in rec.forbidden_uses
    assert rec.leakage_group == "docA"
    assert rec.checksum and rec.checksum != "pending"


def test_convert_token_label_mismatch_excluded():
    lic = load_license_decision("sourcedata")
    label_map = load_label_map()
    rec, excl = convert_source_record(
        _source_rec(["a", "b"], ["O"], ["O", "O"]),
        split="train",
        source_path="x",
        parent_sha="00" * 32,
        license_decision=lic,
        label_map=label_map,
        line_no=1,
    )
    assert rec is None
    assert excl is not None
    assert excl.reason == ExclusionReason.TOKEN_LABEL_LENGTH_MISMATCH.value


def test_convert_unknown_label_excluded():
    lic = load_license_decision("sourcedata")
    label_map = load_label_map()
    rec, excl = convert_source_record(
        _source_rec(["a"], ["B-NOT_A_REAL_TYPE"], ["O"]),
        split="train",
        source_path="x",
        parent_sha="00" * 32,
        license_decision=lic,
        label_map=label_map,
        line_no=1,
    )
    assert rec is None
    assert excl is not None
    assert excl.reason == ExclusionReason.UNMAPPED_LABEL.value


def test_build_idempotent_on_fixture(tmp_path: Path):
    """Minimal multitask tree → two identical builds share records_sha256."""
    root = tmp_path / "data"
    for split, n in (("train", 3), ("validation", 1), ("test", 1)):
        d = root / "training_ready" / "sourcedata_multitask" / split
        d.mkdir(parents=True)
        lines = []
        for i in range(n):
            lines.append(
                json.dumps(
                    _source_rec(
                        ["tok", "A"],
                        ["O", "B-ORGANISM"],
                        ["O", "B-CONTROLLED_VAR"],
                        record_id=f"r-{split}-{i}",
                        document_id=f"doc-{split}-{i}",
                    )
                )
            )
        (d / "records.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    m1 = build_sourcedata_entity_roles(root)
    h1 = m1.records_sha256
    # second run
    m2 = build_sourcedata_entity_roles(root)
    assert m2.records_sha256 == h1
    assert m1.record_counts == m2.record_counts == {"train": 3, "validation": 1, "test": 1}

    out = root / "task_corpora" / "entity_roles" / "sourcedata" / "v2.0.3"
    assert (out / "manifest.json").exists()
    assert (out / "stats.json").exists()
    assert (out / "exclusions.jsonl").exists()
    # no NTRUTH_GOLD
    for split in ("train", "validation", "test"):
        for line in (out / f"{split}.jsonl").read_text().splitlines():
            rec = json.loads(line)
            assert rec["authority_level"] == "AUXILIARY"
            assert rec["training_eligible"] is False


def test_build_excludes_bad_records(tmp_path: Path):
    root = tmp_path / "data"
    d = root / "training_ready" / "sourcedata_multitask" / "train"
    d.mkdir(parents=True)
    good = _source_rec(["a"], ["B-TISSUE"], ["O"], document_id="g1")
    bad = _source_rec(["a", "b"], ["O"], ["O", "O"], document_id="b1")  # length mismatch
    (d / "records.jsonl").write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n")
    for split in ("validation", "test"):
        sd = root / "training_ready" / "sourcedata_multitask" / split
        sd.mkdir(parents=True)
        (sd / "records.jsonl").write_text(
            json.dumps(_source_rec(["z"], ["O"], ["O"], document_id=f"{split}-d")) + "\n"
        )
    m = build_sourcedata_entity_roles(root)
    assert m.record_counts["train"] == 1
    assert m.exclusion_counts.get(ExclusionReason.TOKEN_LABEL_LENGTH_MISMATCH.value) == 1
