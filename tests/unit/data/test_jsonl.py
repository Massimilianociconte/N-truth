"""Regression tests for canonical physical-line JSONL handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.data.jsonl import DatasetIntegrityError, count_jsonl_records, iter_jsonl


def test_iter_jsonl_preserves_unicode_line_separator_inside_record(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    path.write_bytes(
        json.dumps({"id": "first", "text": "before\u2028after"}, ensure_ascii=False).encode()
        + b"\n"
        + json.dumps({"id": "second"}).encode()
        + b"\n"
    )

    records = list(iter_jsonl(path))

    assert [line_number for line_number, _ in records] == [1, 2]
    assert records[0][1]["text"] == "before\u2028after"
    assert count_jsonl_records(path) == {
        "physical_line_count": 2,
        "parsed_record_count": 2,
        "blank_line_count": 0,
    }


def test_iter_jsonl_reports_invalid_physical_line(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    path.write_bytes(b'{"id": 1}\nnot-json\n')

    with pytest.raises(DatasetIntegrityError, match=r"records\.jsonl:2: invalid JSONL record"):
        list(iter_jsonl(path))


def test_iter_jsonl_rejects_non_object_records(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    path.write_bytes(b"[]\n")

    with pytest.raises(DatasetIntegrityError, match="JSONL record must be an object"):
        list(iter_jsonl(path))
