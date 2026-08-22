"""Persistenza locale PRD v6: SQLite, blob immutabili e revisioni append-only."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from ntruth.ingest import project as project_module
from ntruth.ingest.project import BLOBS_DIR, DATABASE_NAME, Project
from ntruth.ingest.safety import SafetyError
from ntruth.storage import (
    MIGRATIONS,
    BlobIntegrityError,
    BlobStore,
    BlobStoreError,
    StorageDatabase,
    StorageIntegrityError,
)
from ntruth.storage.migrations import apply_migrations


def test_migrations_are_idempotent_and_survive_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "state.sqlite3"
    expected_tables = {
        "audit_events",
        "blobs",
        "plan_execution_records",
        "project_blobs",
        "projects",
        "revisions",
        "runs",
        "schema_migrations",
        "sessions",
    }

    with StorageDatabase(database_path) as database:
        assert database.schema_version == MIGRATIONS[-1].version
        assert database.applied_migrations == tuple(item.version for item in MIGRATIONS)
        assert database.foreign_keys_enabled
        with database.transaction():
            assert apply_migrations(database.connection) == MIGRATIONS[-1].version
        rows = database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        assert expected_tables <= {str(row[0]) for row in rows}
        assert database.connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[
            0
        ] == len(MIGRATIONS)

        with pytest.raises(sqlite3.IntegrityError):
            database.connection.execute(
                """
                INSERT INTO revisions(
                    revision_id, project_id, sequence, content_checksum, payload_json
                ) VALUES ('rev-orphan', 'missing-project', 0, ?, '{}')
                """,
                ("0" * 64,),
            )

    with StorageDatabase(database_path) as reopened:
        assert reopened.applied_migrations == tuple(item.version for item in MIGRATIONS)
        assert reopened.foreign_keys_enabled


def test_blob_store_deduplicates_and_refuses_tampered_content(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    payload = b"same immutable scientific source\n"
    digest = hashlib.sha256(payload).hexdigest()

    first = store.put_bytes(payload)
    second = store.put_bytes(payload, expected_sha256=digest)

    assert not first.deduplicated
    assert second.deduplicated
    assert first.record == second.record
    assert first.record.relative_path == f"sha256/{digest[:2]}/{digest}"
    assert store.path(digest).read_bytes() == payload

    store.path(digest).write_bytes(b"tampered")
    with pytest.raises(BlobIntegrityError, match="blob alterato"):
        store.verify(digest)
    with pytest.raises(BlobIntegrityError, match="blob alterato"):
        store.put_bytes(payload)
    assert store.path(digest).read_bytes() == b"tampered"


def test_revisions_and_audit_events_are_append_only(tmp_path: Path) -> None:
    database_path = tmp_path / "state.sqlite3"
    project_id = "prj-test"
    with StorageDatabase(database_path) as database:
        database.upsert_project(
            project_id=project_id,
            name="studio",
            manifest_path="manifest.json",
            manifest_checksum="a" * 64,
        )
        first = database.append_revision(project_id=project_id, payload={"value": 1})
        duplicate = database.append_revision(project_id=project_id, payload={"value": 1})
        second = database.append_revision(project_id=project_id, payload={"value": 2})

        assert duplicate.revision_id == first.revision_id
        assert second.sequence == 1
        assert second.parent_revision_id == first.revision_id
        assert [event.action for event in database.audit_events(project_id)] == [
            "revision.appended",
            "revision.appended",
        ]

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.connection.execute(
                "UPDATE revisions SET actor_role = 'changed' WHERE revision_id = ?",
                (first.revision_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.connection.execute(
                "DELETE FROM revisions WHERE revision_id = ?", (first.revision_id,)
            )
        event_id = database.audit_events(project_id)[0].event_id
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.connection.execute("DELETE FROM audit_events WHERE event_id = ?", (event_id,))

    with StorageDatabase(database_path) as reopened:
        revisions = reopened.revisions(project_id)
        assert [revision.sequence for revision in revisions] == [0, 1]
        assert revisions[0].payload == {"value": 1}
        assert revisions[1].parent_revision_id == revisions[0].revision_id


def test_plan_execution_candidate_is_idempotent_append_only_and_promotable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "state.sqlite3"
    project_id = "prj-plan-exec"
    candidate_payload = {
        "record_id": "plan-execution-1",
        "contract_version": "1.0.0",
        "planned_design": {"title": "planned"},
        "executed_design": {"title": "executed"},
    }
    gold_payload = {
        "gold_id": "prospective-gold-1",
        "status": "adjudicated_gold",
        "plan_execution": candidate_payload,
        "source_annotation_ids": ["a", "b"],
        "reviewer_roles": ["wet_lab", "stats"],
        "adjudicator_role": "adjudicator",
        "adjudicated_at": "2026-08-01T00:00:00+00:00",
    }

    with StorageDatabase(database_path) as database:
        database.upsert_project(
            project_id=project_id,
            name="studio",
            manifest_path="manifest.json",
            manifest_checksum="b" * 64,
        )
        first = database.put_plan_execution_candidate(
            project_id, candidate_payload, actor_role="researcher"
        )
        duplicate = database.put_plan_execution_candidate(
            project_id, candidate_payload, actor_role="other"
        )
        second = database.put_plan_execution_candidate(
            project_id,
            {**candidate_payload, "record_id": "plan-execution-2"},
            actor_role="researcher",
        )

        assert duplicate.record_id == first.record_id
        assert duplicate.content_checksum == first.content_checksum
        assert second.record_id != first.record_id
        assert first.status == "candidate"
        assert first.parent_candidate_id is None
        assert first.payload == candidate_payload
        assert database.get_plan_execution(first.record_id) == first
        assert [item.record_id for item in database.list_plan_executions(project_id)] == [
            first.record_id,
            second.record_id,
        ]
        assert [
            item.record_id for item in database.list_plan_executions(project_id, status="candidate")
        ] == [first.record_id, second.record_id]

        gold = database.promote_plan_execution_gold(
            first.record_id, gold_payload, actor_role="adjudicator"
        )
        assert gold.status == "adjudicated_gold"
        assert gold.parent_candidate_id == first.record_id
        assert gold.payload == gold_payload
        # Il candidato resta immutato e distinto dal gold.
        reloaded_candidate = database.get_plan_execution(first.record_id)
        assert reloaded_candidate is not None
        assert reloaded_candidate.status == "candidate"
        assert reloaded_candidate.content_checksum == first.content_checksum
        assert reloaded_candidate.payload == candidate_payload

        with pytest.raises(StorageIntegrityError, match="gold gia presente"):
            database.promote_plan_execution_gold(first.record_id, gold_payload)

        with pytest.raises(StorageIntegrityError, match="non e un candidato"):
            database.promote_plan_execution_gold(gold.record_id, gold_payload)

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.connection.execute(
                "UPDATE plan_execution_records SET actor_role = 'changed' WHERE record_id = ?",
                (first.record_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.connection.execute(
                "DELETE FROM plan_execution_records WHERE record_id = ?",
                (first.record_id,),
            )

        actions = [event.action for event in database.audit_events(project_id)]
        assert actions == [
            "plan_execution.candidate_appended",
            "plan_execution.candidate_appended",
            "plan_execution.gold_promoted",
        ]

    with StorageDatabase(database_path) as reopened:
        listed = reopened.list_plan_executions(project_id, status="adjudicated_gold")
        assert len(listed) == 1
        assert listed[0].parent_candidate_id == first.record_id
        assert listed[0].payload["gold_id"] == "prospective-gold-1"


def test_plan_execution_requires_registered_project(tmp_path: Path) -> None:
    database_path = tmp_path / "state.sqlite3"
    with (
        StorageDatabase(database_path) as database,
        pytest.raises(StorageIntegrityError, match="progetto non registrato"),
    ):
        database.put_plan_execution_candidate(
            "missing-project",
            {"record_id": "orphan"},
        )


def test_project_keeps_legacy_sources_and_adds_content_addressed_storage(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    source.write_text("Three independent cultures were analysed.\n", encoding="utf-8")
    project = Project.create(tmp_path / "project", name="local-storage")

    result = project.add(source)

    assert not result.has_rejections
    project_file = result.accepted[0]
    legacy_path = project.path_of(project_file)
    blob_path = project.blob_store.path(project_file.sha256)
    assert legacy_path.is_file()
    assert legacy_path.relative_to(project.root).parts[0] == "sources"
    assert blob_path.is_file()
    assert blob_path.relative_to(project.root).parts[0] == BLOBS_DIR
    assert legacy_path.read_bytes() == blob_path.read_bytes() == source.read_bytes()

    persisted = json.loads((project.root / "manifest.json").read_text(encoding="utf-8"))
    assert persisted["files"][0]["relative_path"] == project_file.relative_path
    assert (project.root / DATABASE_NAME).is_file()
    with StorageDatabase(project.database_path) as database:
        row = database.connection.execute(
            """
            SELECT blob_sha256, legacy_relative_path
            FROM project_blobs WHERE project_id = ? AND file_id = ?
            """,
            (project.manifest.project_id, project_file.file_id),
        ).fetchone()
        assert tuple(row) == (project_file.sha256, project_file.relative_path)

    reopened = Project.open(project.root)
    assert reopened.path_of(project_file).is_file()
    assert reopened.blob_store.verify(project_file.sha256).sha256 == project_file.sha256
    assert not reopened.verify_integrity()


def test_project_open_rejects_manifest_tampering_before_revision_or_backfill(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    source.write_text("Three cultures received treatment.\n", encoding="utf-8")
    project = Project.create(tmp_path / "project", name="tamper-gate")
    project_file = project.add(source).accepted[0]
    blob_path = project.blob_store.path(project_file.sha256)
    blob_path.unlink()

    with StorageDatabase(project.database_path) as database:
        revisions_before = len(database.revisions(project.manifest.project_id))
    manifest_path = project.root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["ruleset_version"] = "tampered"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SafetyError, match="checksum manifest non corrispondente"):
        Project.open(project.root)

    assert not blob_path.exists()
    with StorageDatabase(project.database_path) as database:
        assert len(database.revisions(project.manifest.project_id)) == revisions_before


def test_project_verify_integrity_detects_manifest_tampered_after_open(tmp_path: Path) -> None:
    project = Project.create(tmp_path / "project", name="verify-tamper")
    manifest_path = project.root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["ruleset_version"] = "tampered"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    problems = project.verify_integrity()

    assert any("checksum manifest non corrispondente" in problem for problem in problems)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("name", "altered-name"),
        ("domain", "altered-domain"),
        ("language", "it"),
        ("notes", "altered notes"),
    ),
)
def test_manifest_checksum_covers_all_project_metadata(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    project = Project.create(tmp_path / f"project-{field}", name=f"metadata-{field}")
    manifest_path = project.root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload[field] = value
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SafetyError, match="checksum manifest non corrispondente"):
        Project.open(project.root, migrate_legacy_manifest=True)


def test_known_pre_v6_checksum_requires_explicit_migration(tmp_path: Path) -> None:
    project = Project.create(tmp_path / "project", name="legacy-checksum")
    manifest_path = project.root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("release_profile")
    payload["integrity"]["manifest_checksum"] = project.manifest.legacy_checksum_v5()
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    for suffix in ("", "-journal", "-shm", "-wal"):
        Path(f"{project.database_path}{suffix}").unlink(missing_ok=True)

    with pytest.raises(SafetyError, match="manifest legacy"):
        Project.open(project.root)

    migrated = Project.open(project.root, migrate_legacy_manifest=True)
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["integrity"]["manifest_checksum"] == migrated.manifest.checksum()
    assert persisted["integrity"]["manifest_checksum"] != migrated.manifest.legacy_checksum_v5()


def test_legacy_manifest_requires_explicit_verified_migration(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("Three cultures received treatment.\n", encoding="utf-8")
    project = Project.create(tmp_path / "project", name="legacy-migration")
    project_file = project.add(source).accepted[0]
    manifest_path = project.root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("integrity")
    payload.pop("release_profile")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    for suffix in ("", "-journal", "-shm", "-wal"):
        Path(f"{project.database_path}{suffix}").unlink(missing_ok=True)
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    with pytest.raises(SafetyError, match="manifest legacy"):
        Project.open(project.root)
    with pytest.raises(SafetyError, match="SHA-256 esplicito"):
        Project.open(project.root, migrate_legacy_manifest=True)

    reopened = Project.open(
        project.root,
        migrate_legacy_manifest=True,
        legacy_manifest_sha256=manifest_digest,
    )
    migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert migrated["integrity"]["manifest_checksum"] == reopened.manifest.checksum()
    assert not reopened.verify_integrity()
    assert reopened.blob_store.verify(project_file.sha256).sha256 == project_file.sha256


def test_legacy_manifest_migration_refuses_tampered_source(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("Three cultures received treatment.\n", encoding="utf-8")
    project = Project.create(tmp_path / "project", name="unsafe-legacy")
    project_file = project.add(source).accepted[0]
    manifest_path = project.root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("integrity")
    payload.pop("release_profile")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    for suffix in ("", "-journal", "-shm", "-wal"):
        Path(f"{project.database_path}{suffix}").unlink(missing_ok=True)
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    project.path_of(project_file).write_text("tampered\n", encoding="utf-8")

    with pytest.raises(SafetyError, match="manifest legacy non migrabile"):
        Project.open(
            project.root,
            migrate_legacy_manifest=True,
            legacy_manifest_sha256=manifest_digest,
        )

    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "integrity" not in persisted


@pytest.mark.parametrize("remove_release_profile", (False, True))
def test_v6_manifest_cannot_be_downgraded_and_resigned_as_legacy(
    tmp_path: Path,
    remove_release_profile: bool,
) -> None:
    project = Project.create(tmp_path / f"project-{remove_release_profile}", name="v6-downgrade")
    manifest_path = project.root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["name"] = "tampered-name"
    payload.pop("integrity")
    if remove_release_profile:
        payload.pop("release_profile")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    with pytest.raises(SafetyError, match="manifest v6 degradato"):
        Project.open(
            project.root,
            migrate_legacy_manifest=True,
            legacy_manifest_sha256=digest,
        )


def test_project_rejects_blob_and_database_symlink_storage(tmp_path: Path) -> None:
    outside_blobs = tmp_path / "outside-blobs"
    outside_blobs.mkdir()
    blob_workspace = tmp_path / "blob-workspace"
    blob_workspace.mkdir()
    (blob_workspace / BLOBS_DIR).symlink_to(outside_blobs, target_is_directory=True)

    with pytest.raises(SafetyError, match="symlink"):
        Project.create(blob_workspace)
    assert not tuple(outside_blobs.iterdir())

    outside_database = tmp_path / "outside.sqlite3"
    with sqlite3.connect(outside_database) as connection:
        connection.execute("CREATE TABLE sentinel(value TEXT)")
    database_workspace = tmp_path / "database-workspace"
    database_workspace.mkdir()
    (database_workspace / DATABASE_NAME).symlink_to(outside_database)

    with pytest.raises(SafetyError, match="symlink"):
        Project.create(database_workspace)
    with sqlite3.connect(outside_database) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert tables == {"sentinel"}


def test_blob_store_rejects_nested_symlink_components(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / ".tmp").symlink_to(outside, target_is_directory=True)

    with pytest.raises(BlobStoreError, match="symlink"):
        BlobStore(root).put_bytes(b"must stay local")
    assert not tuple(outside.iterdir())


def test_manifest_save_is_atomic_when_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Project.create(tmp_path / "project", name="atomic-manifest")
    manifest_path = project.root / "manifest.json"
    before = manifest_path.read_bytes()
    project.manifest = project.manifest.model_copy(update={"notes": "new revision"})

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr(project_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="publication failure"):
        project.save()

    assert manifest_path.read_bytes() == before
    assert Project.open(project.root).manifest.notes == ""


def test_same_basename_sha_prefix_collision_never_overwrites_a_source(tmp_path: Path) -> None:
    payloads = (
        b"sample_id,value\nBASE,0\n",
        b"sample_id,value\nS3543,3543\n",
        b"sample_id,value\nS78620,78620\n",
    )
    assert (
        hashlib.sha256(payloads[1]).hexdigest()[:8] == hashlib.sha256(payloads[2]).hexdigest()[:8]
    )
    project = Project.create(tmp_path / "project", name="collision-safe")

    accepted = []
    for index, payload in enumerate(payloads):
        source_dir = tmp_path / f"source-{index}"
        source_dir.mkdir()
        source = source_dir / "data.csv"
        source.write_bytes(payload)
        accepted.append(project.add(source).accepted[0])

    assert len({item.relative_path for item in accepted}) == 3
    assert [project.path_of(item).read_bytes() for item in accepted] == list(payloads)
    assert not project.verify_integrity()


def test_verify_integrity_detects_direct_file_tampering(tmp_path: Path) -> None:
    database_path = tmp_path / "state.sqlite3"
    project_id = "prj-tamper"
    with StorageDatabase(database_path) as database:
        database.upsert_project(
            project_id=project_id,
            name="studio",
            manifest_path="manifest.json",
            manifest_checksum="b" * 64,
        )
        database.append_revision(project_id=project_id, payload={"value": 1})
    with StorageDatabase(database_path) as database:
        assert database.verify_integrity() == {"revisions": 1, "plan_execution_records": 0}

    # Attore locale con accesso al file: droppa i trigger e riscrive il payload.
    forged = tmp_path / "forged.sqlite3"
    shutil.copyfile(database_path, forged)
    connection = sqlite3.connect(forged)
    try:
        connection.execute("DROP TRIGGER IF EXISTS revisions_forbid_update")
        connection.execute("UPDATE revisions SET payload_json = '{\"value\": 999}'")
        connection.commit()
    finally:
        connection.close()

    with StorageDatabase(forged) as database, pytest.raises(StorageIntegrityError):
        database.verify_integrity()
