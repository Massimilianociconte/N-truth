"""Canonical ASCII-LF framed JSONL reader for dataset acquisition and exports."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class DatasetIntegrityError(RuntimeError):
    """A dataset file violates the canonical framing or record contract."""


def iter_jsonl_physical_records(
    path: Path,
) -> Iterator[tuple[int, str, dict[str, Any]]]:
    """Yield line number, original record body, and parsed object."""
    with path.open("rb") as stream:
        for physical_line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise DatasetIntegrityError(
                    f"{path}:{physical_line_number}: invalid JSONL record"
                ) from exc
            if not isinstance(record, dict):
                raise DatasetIntegrityError(
                    f"{path}:{physical_line_number}: JSONL record must be an object"
                )
            try:
                record_body = raw_line.rstrip(b"\r\n").decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DatasetIntegrityError(
                    f"{path}:{physical_line_number}: invalid UTF-8 JSONL record"
                ) from exc
            yield physical_line_number, record_body, record


def iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield object records with their one-based physical line numbers."""
    for physical_line_number, _, record in iter_jsonl_physical_records(path):
        yield physical_line_number, record


def count_jsonl_records(path: Path) -> dict[str, int]:
    """Validate all records and return physical, parsed, and blank line counts."""
    physical_line_count = 0
    parsed_record_count = 0
    blank_line_count = 0
    with path.open("rb") as stream:
        for physical_line_count, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                blank_line_count += 1
                continue
            try:
                record = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise DatasetIntegrityError(
                    f"{path}:{physical_line_count}: invalid JSONL record"
                ) from exc
            if not isinstance(record, dict):
                raise DatasetIntegrityError(
                    f"{path}:{physical_line_count}: JSONL record must be an object"
                )
            parsed_record_count += 1
    return {
        "physical_line_count": physical_line_count,
        "parsed_record_count": parsed_record_count,
        "blank_line_count": blank_line_count,
    }
