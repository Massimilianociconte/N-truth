"""Optional local SQLite ledger + export helpers (cluster 2).

Published Git proof is ``qualification_chain.jsonl``. SQLite is optional on a
developer host for append workflows and is gitignored when present.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ntruth.model_backends.registry import compute_transition_hash


class QualificationLedgerError(RuntimeError):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_meta (
    registry_id TEXT PRIMARY KEY,
    genesis_at TEXT NOT NULL,
    genesis_actor TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    initialized INTEGER NOT NULL CHECK(initialized IN (0, 1)),
    last_transition_hash TEXT
);

CREATE TABLE IF NOT EXISTS qualification_transitions (
    sequence INTEGER NOT NULL,
    registry_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    dimension TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_sha256 TEXT,
    evidence_relative_path TEXT,
    artifact_fingerprint_sha256 TEXT,
    previous_transition_hash TEXT,
    transition_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (registry_id, sequence)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_qt_hash
    ON qualification_transitions(registry_id, transition_hash);

CREATE TRIGGER IF NOT EXISTS qt_forbid_update
BEFORE UPDATE ON qualification_transitions
BEGIN
    SELECT RAISE(ABORT, 'qualification_transitions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS qt_forbid_delete
BEFORE DELETE ON qualification_transitions
BEGIN
    SELECT RAISE(ABORT, 'qualification_transitions are append-only');
END;
"""

LEDGER_SCHEMA_VERSION = "1.0.0"
_APPEND_LOCKS: dict[str, threading.Lock] = {}
_APPEND_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _APPEND_LOCKS_GUARD:
        lock = _APPEND_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _APPEND_LOCKS[key] = lock
        return lock


def default_ledger_path(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[3]
    return root / "models" / "registry" / "qualification_ledger.sqlite3"


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    sequence: int
    registry_id: str
    timestamp: str
    actor: str
    dimension: str
    from_status: str
    to_status: str
    rationale: str
    evidence_sha256: str | None
    evidence_relative_path: str | None
    previous_transition_hash: str | None
    transition_hash: str
    artifact_fingerprint_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "registry_id": self.registry_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "dimension": self.dimension,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "rationale": self.rationale,
            "evidence_sha256": self.evidence_sha256,
            "evidence_relative_path": self.evidence_relative_path,
            "artifact_fingerprint_sha256": self.artifact_fingerprint_sha256,
            "previous_transition_hash": self.previous_transition_hash,
            "transition_hash": self.transition_hash,
        }


class QualificationLedger:
    def __init__(self, path: Path, *, registry_id: str = "default") -> None:
        self.path = path.expanduser().resolve()
        self.registry_id = registry_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(_SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> QualificationLedger:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def is_initialized(self) -> bool:
        row = self.connection.execute(
            "SELECT initialized FROM ledger_meta WHERE registry_id = ?",
            (self.registry_id,),
        ).fetchone()
        return bool(row and int(row["initialized"]) == 1)

    def count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS n FROM qualification_transitions WHERE registry_id = ?",
            (self.registry_id,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def max_sequence(self) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS m FROM qualification_transitions "
            "WHERE registry_id = ?",
            (self.registry_id,),
        ).fetchone()
        return int(row["m"]) if row else 0

    def list_transitions(self) -> list[TransitionRecord]:
        rows = self.connection.execute(
            "SELECT * FROM qualification_transitions WHERE registry_id = ? "
            "ORDER BY sequence ASC",
            (self.registry_id,),
        ).fetchall()
        return [
            TransitionRecord(
                sequence=int(r["sequence"]),
                registry_id=str(r["registry_id"]),
                timestamp=str(r["timestamp"]),
                actor=str(r["actor"]),
                dimension=str(r["dimension"]),
                from_status=str(r["from_status"]),
                to_status=str(r["to_status"]),
                rationale=str(r["rationale"]),
                evidence_sha256=r["evidence_sha256"],
                evidence_relative_path=r["evidence_relative_path"],
                previous_transition_hash=r["previous_transition_hash"],
                transition_hash=str(r["transition_hash"]),
                artifact_fingerprint_sha256=r["artifact_fingerprint_sha256"],
            )
            for r in rows
        ]

    def ensure_meta(self, *, actor: str = "ntruth") -> None:
        if self.is_initialized():
            return
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self.connection.execute(
            "INSERT INTO ledger_meta(registry_id, genesis_at, genesis_actor, "
            "schema_version, initialized, last_transition_hash) "
            "VALUES (?, ?, ?, ?, 1, NULL)",
            (self.registry_id, now, actor, LEDGER_SCHEMA_VERSION),
        )

    def append(
        self,
        *,
        dimension: str,
        from_status: str,
        to_status: str,
        rationale: str,
        actor: str,
        evidence_sha256: str | None = None,
        evidence_relative_path: str | None = None,
        artifact_fingerprint_sha256: str | None = None,
        timestamp: str | None = None,
    ) -> TransitionRecord:
        with _path_lock(self.path):
            self.ensure_meta(actor=actor)
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                seq = self.max_sequence() + 1
                prev = None
                if seq > 1:
                    latest = self.list_transitions()[-1]
                    prev = latest.transition_hash
                ts = timestamp or datetime.now(UTC).isoformat().replace("+00:00", "Z")
                th = compute_transition_hash(
                    sequence=seq,
                    registry_id=self.registry_id,
                    timestamp=ts,
                    actor=actor,
                    dimension=dimension,
                    from_status=from_status,
                    to_status=to_status,
                    rationale=rationale,
                    evidence_sha256=evidence_sha256,
                    previous_transition_hash=prev,
                    artifact_fingerprint_sha256=artifact_fingerprint_sha256,
                )
                self.connection.execute(
                    """
                    INSERT INTO qualification_transitions(
                      sequence, registry_id, timestamp, actor, dimension,
                      from_status, to_status, rationale, evidence_sha256,
                      evidence_relative_path, artifact_fingerprint_sha256,
                      previous_transition_hash, transition_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        seq,
                        self.registry_id,
                        ts,
                        actor,
                        dimension,
                        from_status,
                        to_status,
                        rationale,
                        evidence_sha256,
                        evidence_relative_path,
                        artifact_fingerprint_sha256,
                        prev,
                        th,
                    ),
                )
                self.connection.execute(
                    "UPDATE ledger_meta SET last_transition_hash = ? WHERE registry_id = ?",
                    (th, self.registry_id),
                )
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise
            return TransitionRecord(
                sequence=seq,
                registry_id=self.registry_id,
                timestamp=ts,
                actor=actor,
                dimension=dimension,
                from_status=from_status,
                to_status=to_status,
                rationale=rationale,
                evidence_sha256=evidence_sha256,
                evidence_relative_path=evidence_relative_path,
                previous_transition_hash=prev,
                transition_hash=th,
                artifact_fingerprint_sha256=artifact_fingerprint_sha256,
            )

    def export_jsonl(self, path: Path) -> None:
        rows = [t.as_dict() for t in self.list_transitions()]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


__all__ = [
    "QualificationLedger",
    "QualificationLedgerError",
    "TransitionRecord",
    "default_ledger_path",
]
