from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO

import pytest

import ntruth.training.mlx_fd_entrypoint as fd_entrypoint


class _SentinelBaseException(BaseException):
    pass


@contextmanager
def _anonymous_jsonl(payload: bytes) -> Iterator[tuple[BinaryIO, dict[str, str]]]:
    with tempfile.TemporaryFile(mode="w+b") as handle:
        handle.write(payload)
        handle.flush()
        environment = {fd_entrypoint.FD_ENV: json.dumps({"test": handle.fileno()})}
        yield handle, environment


def test_ordinary_close_failure_does_not_replace_active_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_loads = json.loads
    real_dup = os.dup
    real_close = os.close
    interrupted = _SentinelBaseException("decode interrupted")
    duplicated: list[int] = []
    close_calls: list[int] = []

    def track_dup(descriptor: int) -> int:
        duplicate = real_dup(descriptor)
        duplicated.append(duplicate)
        return duplicate

    def interrupt_row_decode(value: str | bytes) -> object:
        if type(value) is str:
            return real_loads(value)
        raise interrupted

    def close_then_fail(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        raise RuntimeError("ordinary close failure")

    with _anonymous_jsonl(b"{}\n") as (original, environment):
        original_descriptor = original.fileno()
        monkeypatch.setattr(fd_entrypoint.os, "dup", track_dup)
        monkeypatch.setattr(fd_entrypoint.json, "loads", interrupt_row_decode)
        monkeypatch.setattr(fd_entrypoint.os, "close", close_then_fail)

        with pytest.raises(_SentinelBaseException) as captured:
            fd_entrypoint.read_inherited_jsonl(
                expected_splits=("test",),
                environment=environment,
            )

        assert captured.value is interrupted
        assert close_calls == duplicated
        assert len(duplicated) == 1
        with pytest.raises(OSError):
            os.fstat(duplicated[0])
        assert os.fstat(original_descriptor).st_nlink == 0


def test_ordinary_close_failure_does_not_replace_active_typed_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_close = os.close
    close_calls: list[int] = []

    def close_then_fail(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        raise RuntimeError("ordinary close failure")

    with _anonymous_jsonl(b"not-json\n") as (original, environment):
        original_descriptor = original.fileno()
        monkeypatch.setattr(fd_entrypoint.os, "close", close_then_fail)

        with pytest.raises(
            fd_entrypoint.InheritedFDContractError,
            match=r"inherited JSONL invalid at test:1$",
        ):
            fd_entrypoint.read_inherited_jsonl(
                expected_splits=("test",),
                environment=environment,
            )

        assert len(close_calls) == 1
        with pytest.raises(OSError):
            os.fstat(close_calls[0])
        assert os.fstat(original_descriptor).st_nlink == 0


def test_ordinary_close_failure_without_active_exception_is_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_close = os.close
    close_calls: list[int] = []

    def close_then_fail(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        raise OSError("ordinary close failure")

    with _anonymous_jsonl(b"{}\n") as (original, environment):
        original_descriptor = original.fileno()
        monkeypatch.setattr(fd_entrypoint.os, "close", close_then_fail)

        with pytest.raises(
            fd_entrypoint.InheritedFDContractError,
            match=r"inherited FD cleanup failed for split test$",
        ) as captured:
            fd_entrypoint.read_inherited_jsonl(
                expected_splits=("test",),
                environment=environment,
            )

        assert isinstance(captured.value.__cause__, OSError)
        assert len(close_calls) == 1
        with pytest.raises(OSError):
            os.fstat(close_calls[0])
        assert os.fstat(original_descriptor).st_nlink == 0


def test_close_base_exception_propagates_after_single_close_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_close = os.close
    interrupted = _SentinelBaseException("close interrupted")
    close_calls: list[int] = []

    def close_then_interrupt(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        raise interrupted

    with _anonymous_jsonl(b"{}\n") as (original, environment):
        original_descriptor = original.fileno()
        monkeypatch.setattr(fd_entrypoint.os, "close", close_then_interrupt)

        with pytest.raises(_SentinelBaseException) as captured:
            fd_entrypoint.read_inherited_jsonl(
                expected_splits=("test",),
                environment=environment,
            )

        assert captured.value is interrupted
        assert len(close_calls) == 1
        with pytest.raises(OSError):
            os.fstat(close_calls[0])
        assert os.fstat(original_descriptor).st_nlink == 0
