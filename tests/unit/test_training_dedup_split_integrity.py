from __future__ import annotations

import hashlib

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.training import (
    AnnotationStatus,
    DatasetValidationError,
    PreparationConfig,
    SupervisedRecord,
    SupervisionProvenance,
    prepare_dataset,
)
from ntruth.training.records import jaccard_similarity, normalize_record


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record(
    record_id: str,
    text: str,
    *,
    target: dict[str, str] | None = None,
    source_key: str | None = None,
    requested_split: CorpusSplit | None = None,
    laboratory_id: str | None = None,
) -> SupervisedRecord:
    source = source_key or record_id
    return SupervisedRecord(
        record_id=record_id,
        task="parser_ai_v2",
        language="en",
        domain="dedup-split-regression",
        input_text=text,
        target=target or {"label": record_id},
        provenance=SupervisionProvenance(
            source_id=f"source-{source}",
            source_asset_id=f"asset-{source}",
            source_sha256=_digest(f"source:{source}"),
            governance_hash=_digest(f"governance:{source}"),
            laboratory_id=laboratory_id,
            license_or_authorization_id=f"authorization-{source}",
            guideline_version="test-v1",
            reviewer_count=2,
            reviewer_roles=("wet-lab", "biostatistics"),
        ),
        annotation_status=AnnotationStatus.DOUBLE_REVIEWED,
        training_eligible=True,
        requested_split=requested_split,
    )


def test_exact_duplicates_with_incompatible_requested_splits_fail_before_selection() -> None:
    text = "The same experimental unit description appears in both records."
    target = {"independent_unit": "culture_well"}
    records = (
        _record(
            "a-train",
            text,
            target=target,
            requested_split=CorpusSplit.TRAIN,
        ),
        _record(
            "z-test",
            text,
            target=target,
            requested_split=CorpusSplit.TEST,
        ),
    )

    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset(records)

    assert {issue.code for issue in captured.value.issues} == {
        "conflicting_duplicate_requested_splits"
    }
    assert captured.value.issues[0].record_ids == ("a-train", "z-test")


def test_near_duplicates_with_incompatible_requested_splits_fail_before_selection() -> None:
    target = {"independent_unit": "animal"}
    records = (
        _record(
            "a-validation",
            "one two three four five six seven eight nine ten",
            target=target,
            requested_split=CorpusSplit.VALIDATION,
        ),
        _record(
            "z-external",
            "one two three four five six seven eight nine eleven",
            target=target,
            requested_split=CorpusSplit.EXTERNAL,
        ),
    )
    config = PreparationConfig(shingle_size=2, near_duplicate_threshold=0.8)

    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset(records, config=config)

    assert {issue.code for issue in captured.value.issues} == {
        "conflicting_duplicate_requested_splits"
    }
    assert captured.value.issues[0].record_ids == ("a-validation", "z-external")


def test_near_duplicate_inputs_with_different_targets_reject_cross_split_constraints() -> None:
    left = _record(
        "a-train-animal",
        "one two three four five six seven eight nine ten",
        target={"independent_unit": "animal"},
        requested_split=CorpusSplit.TRAIN,
    )
    right = _record(
        "z-test-cage",
        "one two three four five six seven eight nine eleven",
        target={"independent_unit": "cage"},
        requested_split=CorpusSplit.TEST,
    )
    config = PreparationConfig(shingle_size=1, near_duplicate_threshold=0.8)
    normalized_left = normalize_record(left, shingle_size=config.shingle_size)
    normalized_right = normalize_record(right, shingle_size=config.shingle_size)

    assert jaccard_similarity(normalized_left.shingles, normalized_right.shingles) == pytest.approx(
        9 / 11
    )
    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset((left, right), config=config)

    assert {issue.code for issue in captured.value.issues} == {
        "conflicting_duplicate_requested_splits"
    }
    assert captured.value.issues[0].record_ids == ("a-train-animal", "z-test-cage")


def test_near_duplicate_inputs_with_different_targets_are_kept_in_one_leakage_group() -> None:
    left = _record(
        "a-animal",
        "one two three four five six seven eight nine ten",
        target={"independent_unit": "animal"},
        requested_split=CorpusSplit.TEST,
    )
    right = _record(
        "z-cage",
        "one two three four five six seven eight nine eleven",
        target={"independent_unit": "cage"},
    )
    config = PreparationConfig(shingle_size=1, near_duplicate_threshold=0.8)

    dataset = prepare_dataset((left, right), config=config)

    assert {record.record.record_id for record in dataset.records} == {"a-animal", "z-cage"}
    assert {record.split for record in dataset.records} == {CorpusSplit.TEST}
    assert len({record.leakage_group_id for record in dataset.records}) == 1
    assert dataset.report.near_duplicate_count == 0


def test_different_target_inputs_below_near_threshold_remain_independent() -> None:
    left = _record(
        "a-train",
        "one two three four five six seven eight nine ten",
        target={"independent_unit": "animal"},
        requested_split=CorpusSplit.TRAIN,
    )
    right = _record(
        "z-test",
        "alpha beta gamma delta epsilon zeta eta theta iota kappa",
        target={"independent_unit": "cage"},
        requested_split=CorpusSplit.TEST,
    )
    config = PreparationConfig(shingle_size=1, near_duplicate_threshold=0.8)

    dataset = prepare_dataset((left, right), config=config)
    prepared = {record.record.record_id: record for record in dataset.records}

    assert prepared["a-train"].split is CorpusSplit.TRAIN
    assert prepared["z-test"].split is CorpusSplit.TEST
    assert prepared["a-train"].leakage_group_id != prepared["z-test"].leakage_group_id


def test_exact_duplicate_propagates_test_constraint_and_removed_source_identity() -> None:
    duplicate_text = "Twelve observations came from four independently allocated cages."
    duplicate_target = {"independent_unit": "cage"}
    records = (
        _record(
            "a-canonical",
            duplicate_text,
            target=duplicate_target,
            source_key="canonical-source",
        ),
        _record(
            "z-duplicate-test",
            duplicate_text,
            target=duplicate_target,
            source_key="restricted-source",
            requested_split=CorpusSplit.TEST,
        ),
        _record(
            "m-related-to-removed-source",
            "A second endpoint was measured on those same four cages.",
            target={"endpoint": "secondary"},
            source_key="restricted-source",
        ),
    )

    dataset = prepare_dataset(records)
    prepared = {item.record.record_id: item for item in dataset.records}

    assert set(prepared) == {"a-canonical", "m-related-to-removed-source"}
    assert {item.split for item in prepared.values()} == {CorpusSplit.TEST}
    assert len({item.leakage_group_id for item in prepared.values()}) == 1
    assert dataset.report.exact_duplicate_count == 1
    assert dataset.report.duplicate_decisions[0].duplicate_record_id == "z-duplicate-test"


def test_near_duplicate_propagates_external_constraint_through_laboratory_identity() -> None:
    target = {"independent_unit": "dish"}
    records = (
        _record(
            "a-canonical",
            "one two three four five six seven eight nine ten",
            target=target,
            source_key="canonical-source",
        ),
        _record(
            "z-duplicate-external",
            "one two three four five six seven eight nine eleven",
            target=target,
            source_key="external-source",
            requested_split=CorpusSplit.EXTERNAL,
            laboratory_id="laboratory-unseen-01",
        ),
        _record(
            "m-same-laboratory",
            "An unrelated assay was performed by the same external laboratory.",
            target={"endpoint": "orthogonal-assay"},
            source_key="other-external-source",
            laboratory_id="laboratory-unseen-01",
        ),
    )
    config = PreparationConfig(shingle_size=2, near_duplicate_threshold=0.8)

    dataset = prepare_dataset(records, config=config)
    prepared = {item.record.record_id: item for item in dataset.records}

    assert set(prepared) == {"a-canonical", "m-same-laboratory"}
    assert {item.split for item in prepared.values()} == {CorpusSplit.EXTERNAL}
    assert len({item.leakage_group_id for item in prepared.values()}) == 1
    assert dataset.report.near_duplicate_count == 1
    assert dataset.report.duplicate_decisions[0].duplicate_record_id == "z-duplicate-external"
