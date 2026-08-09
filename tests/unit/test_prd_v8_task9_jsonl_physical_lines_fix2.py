from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO

import pytest

from ntruth.training.mlx_fd_entrypoint import (
    FD_ENV,
    InheritedFDContractError,
    read_inherited_jsonl,
)
from ntruth.training.records import DatasetFormatError, loads_supervised_jsonl


@contextmanager
def _anonymous_jsonl(payload: bytes) -> Iterator[tuple[BinaryIO, dict[str, str]]]:
    with tempfile.TemporaryFile(mode="w+b") as handle:
        handle.write(payload)
        handle.flush()
        environment = {FD_ENV: json.dumps({"test": handle.fileno()})}
        yield handle, environment


def test_supervised_string_encoding_error_is_dataset_format_error() -> None:
    with pytest.raises(DatasetFormatError) as captured:
        loads_supervised_jsonl("scientific\u2028content\n\ud800")

    assert captured.value.line_number == 2
    assert isinstance(captured.value.__cause__, UnicodeEncodeError)


def test_inherited_fd_uses_only_lf_framing_and_preserves_exact_bytes() -> None:
    scientific_text = "alpha\u2028beta\u2029gamma"
    payload = (
        b'{\r"record_id":"row-1","note":"'
        + scientific_text.encode("utf-8")
        + b'"}\r\n'
        + b'{"record_id":"row-2","note":"final-lf"}\n'
        + b"\n"
    )
    expected_digest = hashlib.sha256(payload).hexdigest()

    with _anonymous_jsonl(payload) as (handle, environment):
        rows = read_inherited_jsonl(
            expected_splits=("test",),
            environment=environment,
        )
        handle.seek(0)
        consumed_bytes = handle.read()

    assert rows == {
        "test": [
            {"record_id": "row-1", "note": scientific_text},
            {"record_id": "row-2", "note": "final-lf"},
        ]
    }
    assert consumed_bytes == payload
    assert hashlib.sha256(consumed_bytes).hexdigest() == expected_digest


def test_inherited_fd_diagnostics_count_only_physical_lf_lines() -> None:
    payload = b'\r{"record_id":"row-1"}\nnot-json\n'

    with (
        _anonymous_jsonl(payload) as (_handle, environment),
        pytest.raises(
            InheritedFDContractError,
            match=r"inherited JSONL invalid at test:2$",
        ),
    ):
        read_inherited_jsonl(
            expected_splits=("test",),
            environment=environment,
        )


def test_inherited_fd_invalid_utf8_is_typed_with_physical_line_number() -> None:
    payload = b'{"record_id":"row-1"}\n{"record_id":"\xff"}\n'

    with (
        _anonymous_jsonl(payload) as (_handle, environment),
        pytest.raises(
            InheritedFDContractError,
            match=r"inherited JSONL invalid at test:2$",
        ),
    ):
        read_inherited_jsonl(
            expected_splits=("test",),
            environment=environment,
        )
