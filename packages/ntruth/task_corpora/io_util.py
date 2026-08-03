"""Idempotent JSONL / JSON writers reusing data.fs atomic helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ntruth.data.fs import atomic_write_json, atomic_write_text, sha256_file

# JSONL records are delimited only by ASCII LF (0x0A). Scientific text may
# contain U+2028 LINE SEPARATOR / U+2029 PARAGRAPH SEPARATOR; str.splitlines()
# treats those as breaks and would corrupt mid-record hashing and parse.


def iter_jsonl_physical_lines(path: Path) -> Iterator[str]:
    """Yield non-empty physical lines from a JSONL file (LF-delimited only)."""
    text = path.read_text(encoding="utf-8")
    for line in text.split("\n"):
        if line.strip():
            yield line


def read_jsonl_physical_lines(path: Path) -> list[str]:
    return list(iter_jsonl_physical_lines(path))


def records_content_sha256(lines: Iterable[str]) -> str:
    """Deterministic content hash: sorted LF-joined record bodies + trailing LF."""
    body = list(lines)
    return hashlib.sha256(
        ("\n".join(sorted(body)) + ("\n" if body else "")).encode("utf-8")
    ).hexdigest()


def write_jsonl_records(path: Path, lines: Iterable[str]) -> str:
    """Write newline-delimited JSON; return sha256 of file bytes.

    Each element must be a single physical line (no raw ASCII LF/CR inside).
    Unicode line/paragraph separators inside JSON string values are allowed.
    """
    parts: list[str] = []
    for line in lines:
        core = line[:-1] if line.endswith("\n") else line
        if "\n" in core or "\r" in core:
            raise ValueError(f"JSONL record must not contain raw CR/LF: {path}")
        parts.append(core + "\n")
    atomic_write_text(path, "".join(parts))
    return sha256_file(path)


def write_json(path: Path, value: Any) -> str:
    atomic_write_json(path, value)
    return sha256_file(path)


def record_checksum(record_dict: dict[str, Any]) -> str:
    """Stable content checksum excluding the checksum field itself."""
    body = {k: v for k, v in record_dict.items() if k != "checksum"}
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()
