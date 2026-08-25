from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import test_prd_v8_task9_validation_eligibility_fix3 as fix3

import ntruth.training.preparation as preparation_module
from ntruth.training.preparation import DatasetValidationError, prepare_dataset
from ntruth.training.records import IssueSeverity, SupervisedRecord


def _assert_typed_materialization_failure(records: object) -> None:
    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset(records)  # type: ignore[arg-type]

    assert len(captured.value.issues) == 1
    issue = captured.value.issues[0]
    assert issue.code == "invalid_supervised_record"
    assert issue.severity is IssueSeverity.ERROR
    assert issue.detail == "SupervisedRecord non valido al confine di preparazione"
    assert issue.record_ids == ()


@pytest.mark.parametrize(
    "records",
    (
        None,
        7,
    ),
)
def test_non_iterable_ingress_is_a_typed_preparation_failure(records: object) -> None:
    _assert_typed_materialization_failure(records)


def test_iterable_ordinary_failure_is_typed_before_semantic_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_continuation: list[str] = []
    original_normalize: Callable[..., Any] = preparation_module.normalize_record

    def track_normalize(*args: Any, **kwargs: Any) -> Any:
        semantic_continuation.append("normalize")
        return original_normalize(*args, **kwargs)

    def broken_records() -> Iterator[SupervisedRecord]:
        raise RuntimeError("ordinary iterable failure")
        yield fix3._valid_record()

    monkeypatch.setattr(preparation_module, "normalize_record", track_normalize)

    _assert_typed_materialization_failure(broken_records())
    assert semantic_continuation == []


def test_partially_yielded_iterable_is_not_partially_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_continuation: list[str] = []
    original_normalize: Callable[..., Any] = preparation_module.normalize_record

    def track_normalize(*args: Any, **kwargs: Any) -> Any:
        semantic_continuation.append("normalize")
        return original_normalize(*args, **kwargs)

    def broken_after_one() -> Iterator[SupervisedRecord]:
        yield fix3._valid_record()
        raise RuntimeError("ordinary failure after one yielded record")

    monkeypatch.setattr(preparation_module, "normalize_record", track_normalize)

    _assert_typed_materialization_failure(broken_after_one())
    assert semantic_continuation == []


class _SentinelBaseException(BaseException):
    pass


def test_iterable_base_exception_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_continuation: list[str] = []
    original_normalize: Callable[..., Any] = preparation_module.normalize_record

    def track_normalize(*args: Any, **kwargs: Any) -> Any:
        semantic_continuation.append("normalize")
        return original_normalize(*args, **kwargs)

    def interrupted_records() -> Iterator[SupervisedRecord]:
        raise _SentinelBaseException
        yield fix3._valid_record()

    monkeypatch.setattr(preparation_module, "normalize_record", track_normalize)

    with pytest.raises(_SentinelBaseException):
        prepare_dataset(interrupted_records())
    assert semantic_continuation == []
