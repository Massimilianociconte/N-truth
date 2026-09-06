"""Durable journal for analysis sessions (resume-after-restart).

Design boundaries:
- **Default-on, explicitly off**: the API applies a local default directory
  (``local-data/runtime/session-journal`` under the working directory, or
  ``$NTRUTH_DATA_HOME`` when set) so a v7 session survives a server restart;
  operators disable it with ``NTRUTH_SESSION_JOURNAL_DIR=off`` and relocate it
  with ``NTRUTH_SESSION_JOURNAL_DIR=<path>``.
- **Replay, not resurrection**: nothing is silently re-executed at boot. A
  journaled session returns only through the explicit
  ``POST /v1/sessions/{id}/resume`` endpoint, which re-runs the deterministic
  analyze path with the exact recorded request.
- **Fail-closed integrity**: every record carries the SHA-256 of its payload;
  a mismatched line is quarantined (renamed) and reported, never replayed.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

JOURNAL_FILENAME = "sessions.jsonl"
QUARANTINE_SUFFIX = ".quarantined"
DEFAULT_JOURNAL_SUBPATH = ("local-data", "runtime", "session-journal")


class JournalCorruptError(ValueError):
    """A journaled record failed its integrity checksum."""


@dataclass(frozen=True)
class JournalEntry:
    session_id: str
    request: dict[str, object]
    payload_sha256: str


def journal_dir_from_env(env: dict[str, str] | None = None) -> Path | None:
    """Resolve the operator-configured journal directory, or None to disable.

    ``off`` (case-insensitive) disables the journal explicitly; an empty value
    keeps the historical opt-in behaviour of leaving the decision to the caller.
    """

    source = os.environ if env is None else env
    raw = (source.get("NTRUTH_SESSION_JOURNAL_DIR") or "").strip()
    if not raw:
        return None
    if raw.lower() == "off":
        return None
    return Path(raw).expanduser()


def default_session_journal_dir(env: dict[str, str] | None = None) -> Path:
    """Local-first default journal directory used when the operator sets none."""

    source = os.environ if env is None else env
    root = (source.get("NTRUTH_DATA_HOME") or "").strip()
    base = Path(root).expanduser() if root else Path.cwd()
    return base.joinpath(*DEFAULT_JOURNAL_SUBPATH)


def _payload_bytes(session_id: str, request: dict[str, object]) -> bytes:
    payload = {"session_id": session_id, "request": request}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    line = json.dumps({**payload, "payload_sha256": digest}, ensure_ascii=False, sort_keys=True)
    return f"{line}\n".encode()


def append_entry(directory: Path, session_id: str, request: dict[str, object]) -> None:
    """Append one checksummed record; creates the directory with 0o700."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / JOURNAL_FILENAME).open("ab") as handle:
        handle.write(_payload_bytes(session_id, request))


def read_entry(directory: Path, session_id: str) -> JournalEntry | None:
    """Return the latest valid entry for the id; quarantine corrupted lines."""
    journal = directory / JOURNAL_FILENAME
    if not journal.is_file():
        return None
    found: JournalEntry | None = None
    corrupt: list[str] = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            claimed = str(record.get("payload_sha256"))
            payload = {"session_id": record["session_id"], "request": record["request"]}
            canonical = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if actual != claimed:
                raise JournalCorruptError("checksum mismatch")
            if str(record["session_id"]) == session_id:
                found = JournalEntry(
                    session_id=session_id,
                    request=dict(record["request"]),
                    payload_sha256=claimed,
                )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            corrupt.append(line)
    if corrupt:
        target = journal.with_suffix(f"{QUARANTINE_SUFFIX}")
        with target.open("a", encoding="utf-8") as quarantine:
            for line in corrupt:
                quarantine.write(line + "\n")
    return found


__all__ = [
    "JournalCorruptError",
    "JournalEntry",
    "append_entry",
    "journal_dir_from_env",
    "read_entry",
]
