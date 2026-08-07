"""Database applicativo SQLite locale per progetti, revisioni e audit N-Truth."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ntruth.storage.blobs import BlobRecord
from ntruth.storage.migrations import apply_migrations


class StorageIntegrityError(RuntimeError):
    """Un record persistito contraddice una identita o un checksum immutabile."""


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    revision_id: str
    project_id: str
    sequence: int
    parent_revision_id: str | None
    content_checksum: str
    payload_json: str
    actor_role: str | None
    created_at: str

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self.payload_json)
        if not isinstance(value, dict):  # pragma: no cover - schema/API invariant
            raise StorageIntegrityError("payload di revisione non oggetto")
        return value


@dataclass(frozen=True, slots=True)
class AuditEventRecord:
    event_id: str
    project_id: str
    sequence: int
    revision_id: str | None
    run_id: str | None
    session_id: str | None
    action: str
    payload_json: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PlanExecutionStorageRecord:
    """Riga immutabile di piano/esecuzione prospettico (candidato o gold)."""

    record_id: str
    project_id: str
    status: str
    content_checksum: str
    payload_json: str
    actor_role: str | None
    parent_candidate_id: str | None
    created_at: str

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self.payload_json)
        if not isinstance(value, dict):  # pragma: no cover - schema/API invariant
            raise StorageIntegrityError("payload plan_execution non oggetto")
        return value


class StorageDatabase:
    """Connessione SQLite con migrazioni, FK e transazioni annidabili.

    La classe non apre socket e non dipende da servizi remoti. Ogni istanza
    applica le migrazioni in una singola transazione ``BEGIN IMMEDIATE``.
    """

    def __init__(self, path: Path) -> None:
        expanded = path.expanduser()
        if expanded.is_symlink():
            raise StorageIntegrityError(f"database SQLite symlink non ammesso: {expanded}")
        for suffix in ("-journal", "-shm", "-wal"):
            sidecar = Path(f"{expanded}{suffix}")
            if sidecar.is_symlink():
                raise StorageIntegrityError(f"sidecar SQLite symlink non ammesso: {sidecar}")
        self.path = expanded.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        self.connection.row_factory = sqlite3.Row
        self._savepoint_counter = 0
        self._closed = False
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA busy_timeout = 30000")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = FULL")
            with self.transaction():
                self.schema_version = apply_migrations(self.connection)
        except BaseException:
            self.connection.close()
            self._closed = True
            raise

    def __enter__(self) -> StorageDatabase:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self.connection.close()
            self._closed = True

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Esegue unita atomiche; le chiamate annidate usano SAVEPOINT."""

        if self.connection.in_transaction:
            self._savepoint_counter += 1
            savepoint = f"ntruth_{self._savepoint_counter}"
            self.connection.execute(f"SAVEPOINT {savepoint}")
            try:
                yield
            except BaseException:
                self.connection.execute(f"ROLLBACK TO {savepoint}")
                self.connection.execute(f"RELEASE {savepoint}")
                raise
            else:
                self.connection.execute(f"RELEASE {savepoint}")
            return

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    @property
    def foreign_keys_enabled(self) -> bool:
        row = self.connection.execute("PRAGMA foreign_keys").fetchone()
        return bool(row and row[0] == 1)

    @property
    def applied_migrations(self) -> tuple[int, ...]:
        rows = self.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        return tuple(int(row[0]) for row in rows)

    def upsert_project(
        self,
        *,
        project_id: str,
        name: str,
        manifest_path: str,
        manifest_checksum: str,
    ) -> None:
        _validate_sha256(manifest_checksum)
        with self.transaction():
            self.connection.execute(
                """
                INSERT INTO projects(project_id, name, manifest_path, manifest_checksum)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    name = excluded.name,
                    manifest_path = excluded.manifest_path,
                    manifest_checksum = excluded.manifest_checksum,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, name, manifest_path, manifest_checksum),
            )

    def register_blob(self, record: BlobRecord, *, media_type: str | None = None) -> None:
        _validate_sha256(record.sha256)
        expected_path = f"sha256/{record.sha256[:2]}/{record.sha256}"
        if record.relative_path != expected_path:
            raise StorageIntegrityError(
                f"percorso blob non canonico: {record.relative_path!r} != {expected_path!r}"
            )
        with self.transaction():
            self.connection.execute(
                """
                INSERT OR IGNORE INTO blobs(
                    sha256, size_bytes, relative_path, media_type, verified_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (record.sha256, record.size_bytes, record.relative_path, media_type),
            )
            row = self.connection.execute(
                """
                SELECT size_bytes, relative_path, media_type
                FROM blobs WHERE sha256 = ?
                """,
                (record.sha256,),
            ).fetchone()
            if row is None:  # pragma: no cover - guarded by INSERT
                raise StorageIntegrityError(f"blob non registrato: {record.sha256}")
            existing_media_type = str(row[2]) if row[2] is not None else None
            if (
                int(row[0]) != record.size_bytes
                or str(row[1]) != record.relative_path
                or (media_type is not None and existing_media_type not in {None, media_type})
            ):
                raise StorageIntegrityError(f"metadati incoerenti per blob {record.sha256}")

    def link_project_blob(
        self,
        *,
        project_id: str,
        file_id: str,
        blob_sha256: str,
        filename: str,
        media_type: str,
        legacy_relative_path: str,
    ) -> None:
        _validate_sha256(blob_sha256)
        with self.transaction():
            self.connection.execute(
                """
                INSERT OR IGNORE INTO project_blobs(
                    project_id,
                    file_id,
                    blob_sha256,
                    filename,
                    media_type,
                    legacy_relative_path
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    file_id,
                    blob_sha256,
                    filename,
                    media_type,
                    legacy_relative_path,
                ),
            )
            row = self.connection.execute(
                """
                SELECT blob_sha256, filename, media_type, legacy_relative_path
                FROM project_blobs WHERE project_id = ? AND file_id = ?
                """,
                (project_id, file_id),
            ).fetchone()
            expected = (blob_sha256, filename, media_type, legacy_relative_path)
            actual = tuple(str(value) for value in row) if row is not None else None
            if actual != expected:
                raise StorageIntegrityError(
                    f"mapping blob incoerente per {project_id}/{file_id}: {actual!r}"
                )

    def append_revision(
        self,
        *,
        project_id: str,
        payload: Mapping[str, object],
        actor_role: str | None = None,
    ) -> RevisionRecord:
        """Aggiunge una revisione lineare o restituisce quella identica esistente."""

        payload_json = _canonical_json(payload)
        checksum = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        with self.transaction():
            existing = self.connection.execute(
                """
                SELECT * FROM revisions
                WHERE project_id = ? AND content_checksum = ?
                """,
                (project_id, checksum),
            ).fetchone()
            if existing is not None:
                return _revision_from_row(existing)

            project_exists = self.connection.execute(
                "SELECT 1 FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if project_exists is None:
                raise StorageIntegrityError(f"progetto non registrato: {project_id}")

            latest = self.connection.execute(
                """
                SELECT revision_id, sequence FROM revisions
                WHERE project_id = ? ORDER BY sequence DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            sequence = int(latest[1]) + 1 if latest is not None else 0
            parent_revision_id = str(latest[0]) if latest is not None else None
            revision_id = _stable_id("rev", project_id, str(sequence), checksum)
            self.connection.execute(
                """
                INSERT INTO revisions(
                    revision_id,
                    project_id,
                    sequence,
                    parent_revision_id,
                    content_checksum,
                    payload_json,
                    actor_role
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    project_id,
                    sequence,
                    parent_revision_id,
                    checksum,
                    payload_json,
                    actor_role,
                ),
            )
            self._append_audit_event(
                project_id=project_id,
                action="revision.appended",
                payload={"content_checksum": checksum, "sequence": sequence},
                revision_id=revision_id,
            )
            row = self.connection.execute(
                "SELECT * FROM revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            if row is None:  # pragma: no cover - guarded by INSERT
                raise StorageIntegrityError(f"revisione non registrata: {revision_id}")
            return _revision_from_row(row)

    def revisions(self, project_id: str) -> tuple[RevisionRecord, ...]:
        rows = self.connection.execute(
            "SELECT * FROM revisions WHERE project_id = ? ORDER BY sequence", (project_id,)
        ).fetchall()
        return tuple(_revision_from_row(row) for row in rows)

    def append_audit_event(
        self,
        *,
        project_id: str,
        action: str,
        payload: Mapping[str, object] | None = None,
        revision_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> AuditEventRecord:
        with self.transaction():
            return self._append_audit_event(
                project_id=project_id,
                action=action,
                payload=payload or {},
                revision_id=revision_id,
                run_id=run_id,
                session_id=session_id,
            )

    def audit_events(self, project_id: str) -> tuple[AuditEventRecord, ...]:
        rows = self.connection.execute(
            "SELECT * FROM audit_events WHERE project_id = ? ORDER BY sequence", (project_id,)
        ).fetchall()
        return tuple(_audit_from_row(row) for row in rows)

    def put_plan_execution_candidate(
        self,
        project_id: str,
        payload: Mapping[str, object],
        actor_role: str | None = None,
    ) -> PlanExecutionStorageRecord:
        """Inserisce un candidato piano/esecuzione o restituisce l'identico esistente.

        La validazione di schema (ProspectivePlanExecutionRecord) resta al layer
        applicativo/API: lo storage serializza solo mapping JSON-canonici.
        """

        payload_json = _canonical_json(payload)
        checksum = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        status = "candidate"
        with self.transaction():
            existing = self.connection.execute(
                """
                SELECT * FROM plan_execution_records
                WHERE project_id = ? AND content_checksum = ? AND status = ?
                """,
                (project_id, checksum, status),
            ).fetchone()
            if existing is not None:
                return _plan_execution_from_row(existing)

            project_exists = self.connection.execute(
                "SELECT 1 FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if project_exists is None:
                raise StorageIntegrityError(f"progetto non registrato: {project_id}")

            record_id = _stable_id("pex", project_id, status, checksum)
            self.connection.execute(
                """
                INSERT INTO plan_execution_records(
                    record_id,
                    project_id,
                    status,
                    content_checksum,
                    payload_json,
                    actor_role,
                    parent_candidate_id
                ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    record_id,
                    project_id,
                    status,
                    checksum,
                    payload_json,
                    actor_role,
                ),
            )
            self._append_audit_event(
                project_id=project_id,
                action="plan_execution.candidate_appended",
                payload={
                    "record_id": record_id,
                    "content_checksum": checksum,
                    "status": status,
                },
            )
            row = self.connection.execute(
                "SELECT * FROM plan_execution_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:  # pragma: no cover - guarded by INSERT
                raise StorageIntegrityError(f"plan_execution non registrato: {record_id}")
            return _plan_execution_from_row(row)

    def get_plan_execution(self, record_id: str) -> PlanExecutionStorageRecord | None:
        """Restituisce un record piano/esecuzione per id, o None se assente."""

        row = self.connection.execute(
            "SELECT * FROM plan_execution_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return _plan_execution_from_row(row)

    def list_plan_executions(
        self,
        project_id: str,
        status: str | None = None,
    ) -> tuple[PlanExecutionStorageRecord, ...]:
        """Elenca i record piano/esecuzione di un progetto, opzionalmente filtrati."""

        if status is None:
            rows = self.connection.execute(
                """
                SELECT * FROM plan_execution_records
                WHERE project_id = ?
                ORDER BY created_at, record_id
                """,
                (project_id,),
            ).fetchall()
        else:
            if status not in {"candidate", "adjudicated_gold"}:
                raise StorageIntegrityError(f"status plan_execution non ammesso: {status!r}")
            rows = self.connection.execute(
                """
                SELECT * FROM plan_execution_records
                WHERE project_id = ? AND status = ?
                ORDER BY created_at, record_id
                """,
                (project_id, status),
            ).fetchall()
        return tuple(_plan_execution_from_row(row) for row in rows)

    def promote_plan_execution_gold(
        self,
        candidate_id: str,
        gold_payload: Mapping[str, object],
        actor_role: str | None = None,
    ) -> PlanExecutionStorageRecord:
        """Promuove un candidato a gold inserendo una nuova riga append-only.

        Il candidato non viene mai mutato. Un solo gold per candidato e ammesso.
        """

        payload_json = _canonical_json(gold_payload)
        checksum = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        status = "adjudicated_gold"
        with self.transaction():
            candidate_row = self.connection.execute(
                "SELECT * FROM plan_execution_records WHERE record_id = ?",
                (candidate_id,),
            ).fetchone()
            if candidate_row is None:
                raise StorageIntegrityError(f"candidato plan_execution assente: {candidate_id}")
            if str(candidate_row["status"]) != "candidate":
                raise StorageIntegrityError(
                    f"record {candidate_id} non e un candidato (status={candidate_row['status']!r})"
                )

            existing_gold = self.connection.execute(
                """
                SELECT record_id FROM plan_execution_records
                WHERE parent_candidate_id = ? AND status = ?
                """,
                (candidate_id, status),
            ).fetchone()
            if existing_gold is not None:
                raise StorageIntegrityError(
                    f"gold gia presente per candidato {candidate_id}: {existing_gold['record_id']}"
                )

            project_id = str(candidate_row["project_id"])
            record_id = _stable_id("pex", project_id, status, checksum, candidate_id)
            self.connection.execute(
                """
                INSERT INTO plan_execution_records(
                    record_id,
                    project_id,
                    status,
                    content_checksum,
                    payload_json,
                    actor_role,
                    parent_candidate_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    project_id,
                    status,
                    checksum,
                    payload_json,
                    actor_role,
                    candidate_id,
                ),
            )
            self._append_audit_event(
                project_id=project_id,
                action="plan_execution.gold_promoted",
                payload={
                    "record_id": record_id,
                    "parent_candidate_id": candidate_id,
                    "content_checksum": checksum,
                    "status": status,
                },
            )
            row = self.connection.execute(
                "SELECT * FROM plan_execution_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:  # pragma: no cover - guarded by INSERT
                raise StorageIntegrityError(f"plan_execution gold non registrato: {record_id}")
            return _plan_execution_from_row(row)

    def _append_audit_event(
        self,
        *,
        project_id: str,
        action: str,
        payload: Mapping[str, object],
        revision_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> AuditEventRecord:
        payload_json = _canonical_json(payload)
        row = self.connection.execute(
            "SELECT COALESCE(MAX(sequence), -1) + 1 FROM audit_events WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        sequence = int(row[0]) if row is not None else 0
        event_id = _stable_id(
            "aud",
            project_id,
            str(sequence),
            action,
            payload_json,
            revision_id or "",
            run_id or "",
            session_id or "",
        )
        self.connection.execute(
            """
            INSERT INTO audit_events(
                event_id,
                project_id,
                sequence,
                revision_id,
                run_id,
                session_id,
                action,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                project_id,
                sequence,
                revision_id,
                run_id,
                session_id,
                action,
                payload_json,
            ),
        )
        event = self.connection.execute(
            "SELECT * FROM audit_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if event is None:  # pragma: no cover - guarded by INSERT
            raise StorageIntegrityError(f"evento audit non registrato: {event_id}")
        return _audit_from_row(event)


def _canonical_json(payload: Mapping[str, object]) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise StorageIntegrityError(
            f"payload non serializzabile in JSON canonico: {error}"
        ) from error


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:24]}"


def _validate_sha256(checksum: str) -> None:
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise StorageIntegrityError("checksum atteso: SHA-256 lowercase di 64 caratteri")


def _revision_from_row(row: sqlite3.Row) -> RevisionRecord:
    return RevisionRecord(
        revision_id=str(row["revision_id"]),
        project_id=str(row["project_id"]),
        sequence=int(row["sequence"]),
        parent_revision_id=(
            str(row["parent_revision_id"]) if row["parent_revision_id"] is not None else None
        ),
        content_checksum=str(row["content_checksum"]),
        payload_json=str(row["payload_json"]),
        actor_role=str(row["actor_role"]) if row["actor_role"] is not None else None,
        created_at=str(row["created_at"]),
    )


def _audit_from_row(row: sqlite3.Row) -> AuditEventRecord:
    return AuditEventRecord(
        event_id=str(row["event_id"]),
        project_id=str(row["project_id"]),
        sequence=int(row["sequence"]),
        revision_id=str(row["revision_id"]) if row["revision_id"] is not None else None,
        run_id=str(row["run_id"]) if row["run_id"] is not None else None,
        session_id=str(row["session_id"]) if row["session_id"] is not None else None,
        action=str(row["action"]),
        payload_json=str(row["payload_json"]),
        created_at=str(row["created_at"]),
    )


def _plan_execution_from_row(row: sqlite3.Row) -> PlanExecutionStorageRecord:
    return PlanExecutionStorageRecord(
        record_id=str(row["record_id"]),
        project_id=str(row["project_id"]),
        status=str(row["status"]),
        content_checksum=str(row["content_checksum"]),
        payload_json=str(row["payload_json"]),
        actor_role=str(row["actor_role"]) if row["actor_role"] is not None else None,
        parent_candidate_id=(
            str(row["parent_candidate_id"]) if row["parent_candidate_id"] is not None else None
        ),
        created_at=str(row["created_at"]),
    )


__all__ = [
    "AuditEventRecord",
    "PlanExecutionStorageRecord",
    "RevisionRecord",
    "StorageDatabase",
    "StorageIntegrityError",
]
