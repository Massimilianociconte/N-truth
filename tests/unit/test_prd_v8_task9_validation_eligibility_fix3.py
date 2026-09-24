from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import test_prd_v8_training_records_splits as record_fixtures

import ntruth.training.preparation as preparation_module
from ntruth.governance.lineage import CorpusSplit
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.mlx_runtime import validate_mlx_dataset
from ntruth.training.preparation import DatasetValidationError, prepare_dataset
from ntruth.training.records import IssueSeverity, SupervisedRecord


def _valid_record(record_id: str = "a-train") -> SupervisedRecord:
    return record_fixtures._record(
        record_id,
        CorpusSplit.TRAIN,
        training=True,
        model_selection=False,
    )


def _physical_record_ids(path: Path) -> tuple[str, ...]:
    return tuple(
        str(json.loads(line)["record_id"]) for line in path.read_bytes().split(b"\n") if line
    )


@pytest.mark.parametrize("diagnostic_split", (CorpusSplit.TRAIN, CorpusSplit.VALIDATION))
def test_diagnostic_membership_is_preserved_but_not_emitted_or_counted_for_approval(
    tmp_path: Path,
    diagnostic_split: CorpusSplit,
) -> None:
    diagnostic_id = f"c-diagnostic-{diagnostic_split.value.lower()}"
    dataset = prepare_dataset(
        (
            _valid_record(),
            record_fixtures._record(
                "b-validation",
                CorpusSplit.VALIDATION,
                training=True,
                model_selection=True,
            ),
            record_fixtures._record(diagnostic_id, diagnostic_split),
        )
    )

    prepared = next(item for item in dataset.records if item.record.record_id == diagnostic_id)
    manifested = next(item for item in dataset.manifest.records if item.record_id == diagnostic_id)
    assert prepared.split is diagnostic_split
    assert manifested.split is diagnostic_split
    assert prepared.record.training_eligible is False
    assert manifested.training_eligible is False

    output = tmp_path / diagnostic_split.value.lower()
    snapshot = export_mlx_dataset(dataset, output)

    assert _physical_record_ids(output / "train.jsonl") == ("a-train",)
    assert _physical_record_ids(output / "valid.jsonl") == ("b-validation",)
    assert snapshot["counts"] == {"train": 1, "valid": 1}
    assert snapshot["membership_counts"][diagnostic_split.value] == 2
    assert snapshot["training_approved"] is True
    assert validate_mlx_dataset(output)["training_approved"] is True


def _assert_typed_ingress_failure(record: SupervisedRecord) -> None:
    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset((record,))

    assert len(captured.value.issues) == 1
    issue = captured.value.issues[0]
    assert issue.code == "invalid_supervised_record"
    assert issue.severity is IssueSeverity.ERROR
    assert issue.detail == "SupervisedRecord non valido al confine di preparazione"
    assert issue.record_ids == ()


def test_prepare_revalidates_model_construct_with_nested_unvalidated_dicts() -> None:
    valid = _valid_record()
    forged = SupervisedRecord.model_construct(**valid.model_dump(mode="python"))

    _assert_typed_ingress_failure(forged)


def test_prepare_converts_cyclic_nested_state_to_typed_failure() -> None:
    cyclic_metadata: dict[str, Any] = {}
    cyclic_metadata["self"] = cyclic_metadata
    forged = _valid_record().model_copy(update={"metadata": cyclic_metadata})

    _assert_typed_ingress_failure(forged)


def test_prepare_converts_ordinary_dump_failure_before_semantic_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_continuation: list[str] = []
    original_normalize = preparation_module.normalize_record

    def track_normalize(*args: Any, **kwargs: Any) -> Any:
        semantic_continuation.append("normalize")
        return original_normalize(*args, **kwargs)

    def fail_dump(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("hostile ordinary failure")

    monkeypatch.setattr(preparation_module, "normalize_record", track_normalize)
    monkeypatch.setattr(SupervisedRecord, "model_dump", fail_dump)

    _assert_typed_ingress_failure(_valid_record())
    assert semantic_continuation == []


class _SentinelBaseException(BaseException):
    pass


def test_prepare_does_not_catch_base_exception_at_ingress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_continuation: list[str] = []
    original_normalize: Callable[..., Any] = preparation_module.normalize_record

    def track_normalize(*args: Any, **kwargs: Any) -> Any:
        semantic_continuation.append("normalize")
        return original_normalize(*args, **kwargs)

    def fail_dump(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise _SentinelBaseException

    monkeypatch.setattr(preparation_module, "normalize_record", track_normalize)
    monkeypatch.setattr(SupervisedRecord, "model_dump", fail_dump)

    with pytest.raises(_SentinelBaseException):
        prepare_dataset((_valid_record(),))

    assert semantic_continuation == []
