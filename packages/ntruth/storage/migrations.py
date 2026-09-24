"""Migrazioni SQLite idempotenti e verificabili per la persistenza locale v6."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass


class StorageMigrationError(RuntimeError):
    """Lo schema registrato non coincide con la migrazione incorporata."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        payload = "\0".join(statement.strip() for statement in self.statements)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="initial_local_storage",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                manifest_checksum TEXT NOT NULL CHECK(length(manifest_checksum) = 64),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS blobs (
                sha256 TEXT PRIMARY KEY CHECK(length(sha256) = 64),
                size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
                relative_path TEXT NOT NULL UNIQUE,
                media_type TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                verified_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS revisions (
                revision_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK(sequence >= 0),
                parent_revision_id TEXT,
                content_checksum TEXT NOT NULL CHECK(length(content_checksum) = 64),
                payload_json TEXT NOT NULL,
                actor_role TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE RESTRICT,
                FOREIGN KEY(parent_revision_id) REFERENCES revisions(revision_id) ON DELETE RESTRICT,
                UNIQUE(project_id, sequence),
                UNIQUE(project_id, content_checksum)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                actor_role TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE RESTRICT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                session_id TEXT,
                input_revision_id TEXT,
                status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'complete', 'partial', 'failed')),
                metadata_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE RESTRICT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
                FOREIGN KEY(input_revision_id) REFERENCES revisions(revision_id) ON DELETE RESTRICT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK(sequence >= 0),
                revision_id TEXT,
                run_id TEXT,
                session_id TEXT,
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE RESTRICT,
                FOREIGN KEY(revision_id) REFERENCES revisions(revision_id) ON DELETE RESTRICT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE RESTRICT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
                UNIQUE(project_id, sequence)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS project_blobs (
                project_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                blob_sha256 TEXT NOT NULL,
                filename TEXT NOT NULL,
                media_type TEXT NOT NULL,
                legacy_relative_path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(project_id, file_id),
                FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE RESTRICT,
                FOREIGN KEY(blob_sha256) REFERENCES blobs(sha256) ON DELETE RESTRICT
            )
            """,
        ),
    ),
    Migration(
        version=2,
        name="append_only_history",
        statements=(
            """
            CREATE TRIGGER IF NOT EXISTS revisions_forbid_update
            BEFORE UPDATE ON revisions
            BEGIN
                SELECT RAISE(ABORT, 'revisions are append-only');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS revisions_forbid_delete
            BEFORE DELETE ON revisions
            BEGIN
                SELECT RAISE(ABORT, 'revisions are append-only');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS audit_events_forbid_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events are append-only');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS audit_events_forbid_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events are append-only');
            END
            """,
        ),
    ),
    Migration(
        version=3,
        name="storage_indexes",
        statements=(
            "CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, started_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at)",
            "CREATE INDEX IF NOT EXISTS idx_revisions_project ON revisions(project_id, sequence)",
            "CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_events(project_id, sequence)",
            "CREATE INDEX IF NOT EXISTS idx_project_blobs_sha ON project_blobs(blob_sha256)",
        ),
    ),
    Migration(
        version=4,
        name="plan_execution_records",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS plan_execution_records (
                record_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE RESTRICT,
                status TEXT NOT NULL CHECK(status IN ('candidate', 'adjudicated_gold')),
                content_checksum TEXT NOT NULL CHECK(length(content_checksum) = 64),
                payload_json TEXT NOT NULL,
                actor_role TEXT,
                parent_candidate_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, content_checksum, status),
                FOREIGN KEY(parent_candidate_id)
                    REFERENCES plan_execution_records(record_id) ON DELETE RESTRICT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_plan_execution_project ON plan_execution_records(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_plan_execution_status ON plan_execution_records(status)",
            """
            CREATE TRIGGER IF NOT EXISTS plan_execution_records_forbid_update
            BEFORE UPDATE ON plan_execution_records
            BEGIN
                SELECT RAISE(ABORT, 'plan_execution_records are append-only');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS plan_execution_records_forbid_delete
            BEFORE DELETE ON plan_execution_records
            BEGIN
                SELECT RAISE(ABORT, 'plan_execution_records are append-only');
            END
            """,
        ),
    ),
)


def apply_migrations(connection: sqlite3.Connection) -> int:
    """Applica ogni migrazione una sola volta nella transazione chiamante."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            checksum TEXT NOT NULL CHECK(length(checksum) = 64),
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {
        int(row[0]): (str(row[1]), str(row[2]))
        for row in connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        )
    }
    for migration in MIGRATIONS:
        registered = applied.get(migration.version)
        expected = (migration.name, migration.checksum)
        if registered is not None:
            if registered != expected:
                raise StorageMigrationError(
                    f"migrazione {migration.version} registrata come {registered}, attesa {expected}"
                )
            continue
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, name, checksum) VALUES (?, ?, ?)",
            (migration.version, migration.name, migration.checksum),
        )
    return MIGRATIONS[-1].version if MIGRATIONS else 0


__all__ = ["MIGRATIONS", "Migration", "StorageMigrationError", "apply_migrations"]
