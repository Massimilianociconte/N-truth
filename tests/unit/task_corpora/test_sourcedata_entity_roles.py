"""Unit tests for SourceData → entity_roles conversion."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ntruth.data.fs import sha256_file
from ntruth.task_corpora.adapters.sourcedata_entity_roles import (
    SourceDataModelUseGate,
    build_sourcedata_entity_roles,
    convert_source_record,
    load_label_map,
)
from ntruth.task_corpora.authority import ExclusionReason
from ntruth.task_corpora.io_util import relative_path_reference
from ntruth.task_corpora.license_loader import load_license_decision
from ntruth.task_corpora.readiness import DatasetReadinessProjection


def _future_permissive_license():
    return load_license_decision("sourcedata").model_copy(
        update={
            "training_allowed": True,
            "derived_labels_allowed": True,
            "development_allowed": True,
            "evaluation_allowed": True,
        }
    )


def _open_model_use_gate() -> SourceDataModelUseGate:
    return SourceDataModelUseGate(
        ntruth_partition_approved=True,
        approved_partition_authority="upstream_official",
        engineering_component_status="VERIFIED_FOR_C0_C1",
        split_protection_status="TRUE",
        licence_scope_status="TRUE",
        provenance_status="TRUE",
        real_anchor_available="TRUE",
        paper_level_leakage_claim_allowed=True,
        model_use_status="READY",
        data_readiness="READY",
        scientific_validation="VALIDATED",
        reality_gate_status="READY",
        substantive_training_allowed=True,
        blockers=(),
    )


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
        "eligibility": {
            "training_eligible": False,
            "evaluation_eligible": False,
            "requires_review": False,
        },
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
    assert rec.evaluation_eligible is False
    assert rec.requires_review is False
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


def test_convert_preserves_conservative_source_leakage_group_without_document_id():
    lic = load_license_decision("sourcedata")
    label_map = load_label_map()
    source = _source_rec(
        ["a"],
        ["O"],
        ["O"],
        document_id="",
    )
    source["source"]["segment_id"] = "revision-specific-record"
    source["split"]["group_id"] = "unknown_document_scope:revision-1"

    record, exclusion = convert_source_record(
        source,
        split="train",
        source_path="processed/sourcedata/v2.0.3/multitask/train/records.jsonl",
        parent_sha="00" * 32,
        license_decision=lic,
        label_map=label_map,
        line_no=1,
    )

    assert exclusion is None
    assert record is not None
    assert record.leakage_group == "unknown_document_scope:revision-1"


@pytest.mark.parametrize(
    ("upstream_training", "upstream_evaluation", "split", "crosses_splits"),
    [
        (False, True, "train", False),
        (True, False, "validation", False),
        (True, True, "train", True),
        (True, True, "validation", True),
    ],
)
def test_convert_never_promotes_when_any_upstream_or_split_gate_is_closed(
    upstream_training: bool,
    upstream_evaluation: bool,
    split: str,
    crosses_splits: bool,
):
    source = _source_rec(["a"], ["O"], ["O"])
    source["split"]["name"] = split
    source["eligibility"] = {
        "training_eligible": upstream_training,
        "evaluation_eligible": upstream_evaluation,
        "requires_review": False,
    }

    record, exclusion = convert_source_record(
        source,
        split=split,
        source_path="processed/sourcedata/v2.0.3/multitask/records.jsonl",
        parent_sha="00" * 32,
        license_decision=_future_permissive_license(),
        label_map=load_label_map(),
        line_no=1,
        model_use_gate=_open_model_use_gate(),
        leakage_group_crosses_splits=crosses_splits,
    )

    assert exclusion is None
    assert record is not None
    assert record.training_eligible is False
    assert record.evaluation_eligible is False


def test_convert_future_permissive_license_does_not_bypass_readiness_blockers():
    source = _source_rec(["a"], ["O"], ["O"])
    source["eligibility"] = {
        "training_eligible": True,
        "evaluation_eligible": True,
        "requires_review": False,
    }

    record, exclusion = convert_source_record(
        source,
        split="train",
        source_path="processed/sourcedata/v2.0.3/multitask/train/records.jsonl",
        parent_sha="00" * 32,
        license_decision=_future_permissive_license(),
        label_map=load_label_map(),
        line_no=1,
        model_use_gate=SourceDataModelUseGate.from_projection(
            DatasetReadinessProjection(),
            ntruth_partition_approved=True,
        ),
        leakage_group_crosses_splits=False,
    )

    assert exclusion is None
    assert record is not None
    assert record.training_eligible is False
    assert record.evaluation_eligible is False


def test_convert_missing_upstream_eligibility_fails_closed_and_requires_review():
    source = _source_rec(["a"], ["O"], ["O"])
    del source["eligibility"]

    record, exclusion = convert_source_record(
        source,
        split="train",
        source_path="processed/sourcedata/v2.0.3/multitask/train/records.jsonl",
        parent_sha="00" * 32,
        license_decision=_future_permissive_license(),
        label_map=load_label_map(),
        line_no=1,
        model_use_gate=_open_model_use_gate(),
        leakage_group_crosses_splits=False,
    )

    assert exclusion is None
    assert record is not None
    assert record.training_eligible is False
    assert record.evaluation_eligible is False
    assert record.requires_review is True


def test_convert_propagates_upstream_review_and_partition_mismatch_fail_closed():
    source = _source_rec(["a"], ["O"], ["O"])
    source["split"]["name"] = "validation"
    source["eligibility"] = {
        "training_eligible": True,
        "evaluation_eligible": True,
        "requires_review": True,
    }

    record, exclusion = convert_source_record(
        source,
        split="train",
        source_path="processed/sourcedata/v2.0.3/multitask/train/records.jsonl",
        parent_sha="00" * 32,
        license_decision=_future_permissive_license(),
        label_map=load_label_map(),
        line_no=1,
        model_use_gate=_open_model_use_gate(),
        leakage_group_crosses_splits=False,
    )

    assert exclusion is None
    assert record is not None
    assert record.requires_review is True
    assert record.training_eligible is False
    assert record.evaluation_eligible is False


def test_convert_nonapproved_ntruth_partition_fails_closed_with_other_gates_open():
    source = _source_rec(["a"], ["O"], ["O"])
    source["eligibility"] = {
        "training_eligible": True,
        "evaluation_eligible": True,
        "requires_review": False,
    }

    record, exclusion = convert_source_record(
        source,
        split="train",
        source_path="processed/sourcedata/v2.0.3/multitask/train/records.jsonl",
        parent_sha="00" * 32,
        license_decision=_future_permissive_license(),
        label_map=load_label_map(),
        line_no=1,
        model_use_gate=replace(
            _open_model_use_gate(),
            ntruth_partition_approved=False,
        ),
        leakage_group_crosses_splits=False,
    )

    assert exclusion is None
    assert record is not None
    assert record.training_eligible is False
    assert record.evaluation_eligible is False


@pytest.mark.parametrize(
    ("gate_update", "source_authority"),
    [
        ({"blockers": ("scientific blocker",)}, "upstream_official"),
        ({"model_use_status": "BLOCKED"}, "upstream_official"),
        ({"reality_gate_status": "BLOCKED"}, "upstream_official"),
        ({}, "unapproved_partition"),
    ],
)
def test_convert_model_use_blocker_or_unapproved_authority_fails_closed(
    gate_update: dict[str, object],
    source_authority: str,
):
    source = _source_rec(["a"], ["O"], ["O"])
    source["split"]["authority"] = source_authority
    source["eligibility"] = {
        "training_eligible": True,
        "evaluation_eligible": True,
        "requires_review": False,
    }

    record, exclusion = convert_source_record(
        source,
        split="train",
        source_path="processed/sourcedata/v2.0.3/multitask/train/records.jsonl",
        parent_sha="00" * 32,
        license_decision=_future_permissive_license(),
        label_map=load_label_map(),
        line_no=1,
        model_use_gate=replace(_open_model_use_gate(), **gate_update),
        leakage_group_crosses_splits=False,
    )

    assert exclusion is None
    assert record is not None
    assert record.training_eligible is False
    assert record.evaluation_eligible is False


def test_convert_open_gates_prove_fail_closed_tests_are_not_vacuous():
    source = _source_rec(["a"], ["O"], ["O"])
    source["eligibility"] = {
        "training_eligible": True,
        "evaluation_eligible": True,
        "requires_review": False,
    }

    record, exclusion = convert_source_record(
        source,
        split="train",
        source_path="processed/sourcedata/v2.0.3/multitask/train/records.jsonl",
        parent_sha="00" * 32,
        license_decision=_future_permissive_license(),
        label_map=load_label_map(),
        line_no=1,
        model_use_gate=_open_model_use_gate(),
        leakage_group_crosses_splits=False,
    )

    assert exclusion is None
    assert record is not None
    assert record.training_eligible is True
    assert record.evaluation_eligible is False

    source["split"]["name"] = "validation"
    evaluation_record, evaluation_exclusion = convert_source_record(
        source,
        split="validation",
        source_path="processed/sourcedata/v2.0.3/multitask/validation/records.jsonl",
        parent_sha="00" * 32,
        license_decision=_future_permissive_license(),
        label_map=load_label_map(),
        line_no=1,
        model_use_gate=_open_model_use_gate(),
        leakage_group_crosses_splits=False,
    )
    assert evaluation_exclusion is None
    assert evaluation_record is not None
    assert evaluation_record.training_eligible is False
    assert evaluation_record.evaluation_eligible is True


def test_build_idempotent_on_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Minimal multitask tree → two identical builds share records_sha256."""
    monkeypatch.setattr(
        "ntruth.task_corpora.adapters.sourcedata_entity_roles.load_license_decision",
        lambda _dataset_key: _future_permissive_license(),
    )
    root = tmp_path / "data"
    for split, n in (("train", 3), ("validation", 1), ("test", 1)):
        d = root / "processed" / "sourcedata" / "v2.0.3" / "multitask" / split
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
    manifest_bytes = (out / "manifest.json").read_bytes()
    clean_run_log_bytes = (out / "clean_run_log.txt").read_bytes()
    manifest = json.loads(manifest_bytes)
    clean_run_log = json.loads(clean_run_log_bytes)
    assert manifest["root"] == "."
    assert manifest["output_dir"] == ("task_corpora/entity_roles/sourcedata/v2.0.3")
    assert clean_run_log["manifest"] == (
        "task_corpora/entity_roles/sourcedata/v2.0.3/manifest.json"
    )
    assert clean_run_log["records_sha256"] == m2.records_sha256
    assert clean_run_log["manifest_sha256"] == sha256_file(out / "manifest.json")
    for artifact_bytes in (manifest_bytes, clean_run_log_bytes):
        artifact_text = artifact_bytes.decode("utf-8")
        assert str(root.resolve()) not in artifact_text
        assert "/Volumes/" not in artifact_text
        assert "/Users/" not in artifact_text

    build_sourcedata_entity_roles(root)
    assert (out / "manifest.json").read_bytes() == manifest_bytes
    assert (out / "clean_run_log.txt").read_bytes() == clean_run_log_bytes
    # no NTRUTH_GOLD
    for split in ("train", "validation", "test"):
        for line in (out / f"{split}.jsonl").read_text().splitlines():
            rec = json.loads(line)
            assert rec["authority_level"] == "AUXILIARY"
            assert rec["training_eligible"] is False
            assert rec["evaluation_eligible"] is False


def test_relative_path_reference_rejects_path_outside_root(tmp_path: Path):
    root = tmp_path / "dataset"
    root.mkdir()

    with pytest.raises(ValueError, match="artifact path escapes dataset root"):
        relative_path_reference(tmp_path / "elsewhere" / "manifest.json", root=root)


def test_build_excludes_bad_records(tmp_path: Path):
    root = tmp_path / "data"
    d = root / "processed" / "sourcedata" / "v2.0.3" / "multitask" / "train"
    d.mkdir(parents=True)
    good = _source_rec(["a"], ["B-TISSUE"], ["O"], document_id="g1")
    bad = _source_rec(["a", "b"], ["O"], ["O", "O"], document_id="b1")  # length mismatch
    (d / "records.jsonl").write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n")
    for split in ("validation", "test"):
        sd = root / "processed" / "sourcedata" / "v2.0.3" / "multitask" / split
        sd.mkdir(parents=True)
        (sd / "records.jsonl").write_text(
            json.dumps(_source_rec(["z"], ["O"], ["O"], document_id=f"{split}-d")) + "\n"
        )
    m = build_sourcedata_entity_roles(root)
    assert m.record_counts["train"] == 1
    assert m.exclusion_counts.get(ExclusionReason.TOKEN_LABEL_LENGTH_MISMATCH.value) == 1
