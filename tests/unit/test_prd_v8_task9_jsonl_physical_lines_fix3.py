from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO

import pytest

import ntruth.training.mlx_fd_entrypoint as fd_entrypoint
from ntruth.training.records import (
    DatasetFormatError,
    SupervisedRecord,
    loads_supervised_jsonl,
)


class _HostileText(str):
    def encode(self, *_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError("hostile text encoding")


class _HostileBytes(bytes):
    def split(self, *_args: object, **_kwargs: object) -> list[bytes]:
        raise RuntimeError("hostile byte splitting")


class _SentinelBaseException(BaseException):
    pass


@contextmanager
def _anonymous_jsonl(payload: bytes) -> Iterator[tuple[BinaryIO, dict[str, str]]]:
    with tempfile.TemporaryFile(mode="w+b") as handle:
        handle.write(payload)
        handle.flush()
        environment = {fd_entrypoint.FD_ENV: json.dumps({"test": handle.fileno()})}
        yield handle, environment


@pytest.mark.parametrize("payload_kind", ("text", "bytes"))
def test_supervised_loader_rejects_non_exact_text_or_bytes_with_stable_error(
    payload_kind: str,
) -> None:
    payload: str | bytes = (
        _HostileText("{}\n") if payload_kind == "text" else _HostileBytes(b"{}\n")
    )
    with pytest.raises(DatasetFormatError) as captured:
        loads_supervised_jsonl(payload)

    assert captured.value.line_number == 1
    assert captured.value.detail == "payload JSONL deve usare str o bytes builtin"


def test_supervised_loader_normalizes_ordinary_validation_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_validation(_payload: bytes) -> SupervisedRecord:
        raise RuntimeError("hostile validator")

    monkeypatch.setattr(
        SupervisedRecord,
        "model_validate_json",
        staticmethod(fail_validation),
    )

    with pytest.raises(DatasetFormatError) as captured:
        loads_supervised_jsonl(b"{}\n")

    assert captured.value.line_number == 1
    assert captured.value.detail == "record supervisionato JSONL non valido"
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_supervised_loader_does_not_catch_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_validation(_payload: bytes) -> SupervisedRecord:
        raise _SentinelBaseException

    monkeypatch.setattr(
        SupervisedRecord,
        "model_validate_json",
        staticmethod(fail_validation),
    )

    with pytest.raises(_SentinelBaseException):
        loads_supervised_jsonl(b"{}\n")


@pytest.mark.parametrize("failure", (RuntimeError("decode"), RecursionError("deep JSON")))
def test_inherited_fd_normalizes_every_ordinary_json_decode_exception(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    real_loads = json.loads

    def fail_row(value: str | bytes) -> object:
        if type(value) is str:
            return real_loads(value)
        raise failure

    monkeypatch.setattr(fd_entrypoint.json, "loads", fail_row)
    with (
        _anonymous_jsonl(b"{}\n") as (_handle, environment),
        pytest.raises(
            fd_entrypoint.InheritedFDContractError,
            match=r"inherited JSONL invalid at test:1$",
        ) as captured,
    ):
        fd_entrypoint.read_inherited_jsonl(
            expected_splits=("test",),
            environment=environment,
        )

    assert captured.value.__cause__ is failure


def test_inherited_fd_does_not_catch_base_exception_from_json_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_loads = json.loads

    def fail_row(value: str | bytes) -> object:
        if type(value) is str:
            return real_loads(value)
        raise _SentinelBaseException

    monkeypatch.setattr(fd_entrypoint.json, "loads", fail_row)
    with (
        _anonymous_jsonl(b"{}\n") as (_handle, environment),
        pytest.raises(_SentinelBaseException),
    ):
        fd_entrypoint.read_inherited_jsonl(
            expected_splits=("test",),
            environment=environment,
        )


@pytest.mark.parametrize("base_exception", (False, True))
def test_fdopen_failure_closes_only_duplicate_and_preserves_exception_policy(
    monkeypatch: pytest.MonkeyPatch,
    base_exception: bool,
) -> None:
    duplicated: list[int] = []
    close_calls: list[int] = []
    real_dup = os.dup
    real_close = os.close
    failure: BaseException = (
        _SentinelBaseException("fdopen base") if base_exception else RuntimeError("fdopen ordinary")
    )

    def track_dup(descriptor: int) -> int:
        duplicate = real_dup(descriptor)
        duplicated.append(duplicate)
        return duplicate

    def track_close(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)

    def fail_fdopen(*_args: object, **_kwargs: object) -> BinaryIO:
        raise failure

    with _anonymous_jsonl(b"{}\n") as (original, environment):
        original_descriptor = original.fileno()
        monkeypatch.setattr(fd_entrypoint.os, "dup", track_dup)
        monkeypatch.setattr(fd_entrypoint.os, "close", track_close)
        monkeypatch.setattr(fd_entrypoint.os, "fdopen", fail_fdopen)

        expected = (
            _SentinelBaseException if base_exception else fd_entrypoint.InheritedFDContractError
        )
        with pytest.raises(expected):
            fd_entrypoint.read_inherited_jsonl(
                expected_splits=("test",),
                environment=environment,
            )

        assert len(duplicated) == 1
        assert close_calls == duplicated
        with pytest.raises(OSError):
            os.fstat(duplicated[0])
        assert os.fstat(original_descriptor).st_nlink == 0


def test_successful_fd_read_closes_duplicate_exactly_once_not_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicated: list[int] = []
    close_calls: list[int] = []
    real_dup = os.dup
    real_close = os.close

    def track_dup(descriptor: int) -> int:
        duplicate = real_dup(descriptor)
        duplicated.append(duplicate)
        return duplicate

    def track_close(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)

    with _anonymous_jsonl(b'{"record_id":"row"}\n') as (original, environment):
        original_descriptor = original.fileno()
        monkeypatch.setattr(fd_entrypoint.os, "dup", track_dup)
        monkeypatch.setattr(fd_entrypoint.os, "close", track_close)

        rows = fd_entrypoint.read_inherited_jsonl(
            expected_splits=("test",),
            environment=environment,
        )

        assert rows == {"test": [{"record_id": "row"}]}
        assert len(duplicated) == 1
        assert close_calls == duplicated
        with pytest.raises(OSError):
            os.fstat(duplicated[0])
        assert os.fstat(original_descriptor).st_nlink == 0
