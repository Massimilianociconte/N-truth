"""Ledger SQLite append-only: monotonia, GENESIS, chain, evidence, concurrency."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from ntruth.model_backends.qualification_ledger import (
    GENESIS_DIMENSION,
    QualificationLedger,
    QualificationLedgerError,
    compute_transition_hash,
    rebuild_json_transition_mirror,
    seed_ledger_from_json_log,
)


def _ledger(tmp_path: Path) -> QualificationLedger:
    return QualificationLedger(
        tmp_path / "ledger.sqlite3",
        evidence_root=tmp_path / "evidence",
    )


def test_append_only_triggers_block_update_and_delete(tmp_path: Path) -> None:
    with _ledger(tmp_path) as ledger:
        ledger.ensure_genesis(
            actor="tester",
            source_json_sha256="a" * 64,
            schema_version="1.3.0",
        )
        first = ledger.append(
            dimension="runtime_qualification_status",
            from_status="UNVERIFIED",
            to_status="PARTIALLY_VERIFIED",
            actor="tester",
            rationale="smoke qualification",
            evidence={"check": "e2e_ok"},
        )
        assert first.sequence == 2  # after GENESIS
        assert first.evidence_sha256 is not None

        second = ledger.append(
            dimension="runtime_qualification_status",
            from_status="PARTIALLY_VERIFIED",
            to_status="VERIFIED",
            actor="tester",
            rationale="full runtime suite",
            evidence="protocol://m5-benchmark",
        )
        assert second.sequence == 3
        assert second.previous_transition_hash == first.transition_hash
        ledger.verify_chain(verify_evidence=True)

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            ledger.connection.execute("UPDATE qualification_transitions SET rationale = 'tamper'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            ledger.connection.execute("DELETE FROM qualification_transitions")


def test_sequence_is_exactly_max_plus_one(tmp_path: Path) -> None:
    with _ledger(tmp_path) as ledger:
        ledger.ensure_genesis(
            actor="tester",
            source_json_sha256="b" * 64,
            schema_version="1.3.0",
        )
        assert ledger.max_sequence() == 1
        r = ledger.append(
            dimension="migration_status",
            from_status="ARCHITECTURE_MIGRATED",
            to_status="ARCHITECTURE_MIGRATED",
            actor="t",
            rationale="noop note",
        )
        assert r.sequence == ledger.max_sequence() == 2


def test_hash_chain_detects_tampered_row(tmp_path: Path) -> None:
    with _ledger(tmp_path) as ledger:
        ledger.ensure_genesis(
            actor="a",
            source_json_sha256="c" * 64,
            schema_version="1.3.0",
        )
        ledger.connection.executescript(
            """
            DROP TRIGGER qualification_transitions_forbid_update;
            UPDATE qualification_transitions SET rationale = 'evil';
            """
        )
        with pytest.raises(QualificationLedgerError, match="transition_hash non valido"):
            ledger.verify_chain(verify_evidence=False)


def test_skipped_sequence_fails_verify(tmp_path: Path) -> None:
    with _ledger(tmp_path) as ledger:
        ledger.ensure_genesis(
            actor="a",
            source_json_sha256="d" * 64,
            schema_version="1.3.0",
        )
        ledger.connection.executescript("DROP TRIGGER qualification_transitions_forbid_update;")
        # Forza sequence saltata 1 -> 7
        ledger.connection.execute(
            "UPDATE qualification_transitions SET sequence = 7 WHERE sequence = 1"
        )
        with pytest.raises(QualificationLedgerError, match="sequence non monotona"):
            ledger.verify_chain(verify_evidence=False)


def test_wrong_previous_hash_fails_verify(tmp_path: Path) -> None:
    with _ledger(tmp_path) as ledger:
        ledger.ensure_genesis(
            actor="a",
            source_json_sha256="e" * 64,
            schema_version="1.3.0",
        )
        ledger.append(
            dimension="x",
            from_status="A",
            to_status="B",
            actor="a",
            rationale="step",
        )
        ledger.connection.executescript("DROP TRIGGER qualification_transitions_forbid_update;")
        ledger.connection.execute(
            "UPDATE qualification_transitions SET previous_transition_hash = 'deadbeef' "
            "WHERE sequence = 2"
        )
        with pytest.raises(QualificationLedgerError, match="hash chain rotta"):
            ledger.verify_chain(verify_evidence=False)


def test_missing_or_altered_evidence_fails(tmp_path: Path) -> None:
    with _ledger(tmp_path) as ledger:
        ledger.ensure_genesis(
            actor="a",
            source_json_sha256="f" * 64,
            schema_version="1.3.0",
        )
        rec = ledger.append(
            dimension="x",
            from_status="A",
            to_status="B",
            actor="a",
            rationale="with evidence",
            evidence={"k": "v"},
        )
        assert rec.evidence_relative_path
        blob = ledger.evidence_root / rec.evidence_relative_path
        blob.write_bytes(b"tampered")
        with pytest.raises(QualificationLedgerError, match="evidence content mismatch"):
            ledger.verify_chain(verify_evidence=True)

        blob.unlink()
        with pytest.raises(QualificationLedgerError, match="evidence blob assente"):
            ledger.verify_chain(verify_evidence=True)


def test_seed_creates_genesis_and_forbids_silent_reseed(tmp_path: Path) -> None:
    log = [
        {
            "sequence": 1,
            "timestamp": "2026-08-02T00:00:00Z",
            "actor": "ntruth-maintainers",
            "dimension": "migration_status",
            "from_status": "NONE",
            "to_status": "ARCHITECTURE_MIGRATED",
            "rationale": "architectural migration",
            "evidence_artifact": "docs/adr/0010.md",
        }
    ]
    with _ledger(tmp_path) as ledger:
        n = seed_ledger_from_json_log(
            ledger,
            log,
            source_json_sha256="1" * 64,
            schema_version="1.3.0",
        )
        assert n == 1
        assert ledger.is_initialized()
        assert ledger.list_transitions()[0].dimension == GENESIS_DIMENSION
        assert seed_ledger_from_json_log(ledger, log) == 0  # no reseed
        meta = ledger.meta()
        assert meta is not None
        assert meta["source_json_sha256"] == "1" * 64
        assert meta["schema_version"] == "1.3.0"


def test_initialized_empty_chain_rejects_automatic_reseed(tmp_path: Path) -> None:
    with _ledger(tmp_path) as ledger:
        ledger.ensure_genesis(
            actor="a",
            source_json_sha256="2" * 64,
            schema_version="1.3.0",
        )
        # Wipe transitions while keeping meta (simula cancellazione parziale)
        ledger.connection.executescript(
            """
            DROP TRIGGER qualification_transitions_forbid_delete;
            DELETE FROM qualification_transitions;
            """
        )
        with pytest.raises(QualificationLedgerError, match=r"reseed|vuota|inizializzato"):
            seed_ledger_from_json_log(
                ledger,
                [],
                allow_reseed=False,
            )
        with pytest.raises(QualificationLedgerError, match=r"initialized=1|catena vuota|vuota"):
            ledger.verify_chain()


def test_concurrent_appends_keep_monotonic_sequence(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    evidence = tmp_path / "evidence"
    with QualificationLedger(path, evidence_root=evidence) as ledger:
        ledger.ensure_genesis(
            actor="boot",
            source_json_sha256="3" * 64,
            schema_version="1.3.0",
        )

    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            with QualificationLedger(path, evidence_root=evidence) as led:
                led.append(
                    dimension="runtime_qualification_status",
                    from_status="UNVERIFIED",
                    to_status="UNVERIFIED",
                    actor=f"w{i}",
                    rationale=f"concurrent {i}",
                )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    with QualificationLedger(path, evidence_root=evidence) as ledger:
        ledger.verify_chain(verify_evidence=True)
        sequences = [item.sequence for item in ledger.list_transitions()]
        assert sequences == list(range(1, len(sequences) + 1))
        assert len(sequences) == 9  # GENESIS + 8


def test_rebuild_mirror_from_ledger(tmp_path: Path) -> None:
    with _ledger(tmp_path) as ledger:
        ledger.ensure_genesis(
            actor="a",
            source_json_sha256="4" * 64,
            schema_version="1.3.0",
        )
        ledger.append(
            dimension="scientific_validation_status",
            from_status="NOT_STARTED",
            to_status="NOT_STARTED",
            actor="a",
            rationale="note",
        )
        mirror = rebuild_json_transition_mirror(ledger)
        assert len(mirror) == 2
        assert mirror[0]["dimension"] == GENESIS_DIMENSION


def test_compute_transition_hash_is_stable() -> None:
    h1 = compute_transition_hash(
        sequence=1,
        registry_id="default",
        timestamp="t",
        actor="a",
        dimension="d",
        from_status="A",
        to_status="B",
        rationale="r",
        evidence_sha256=None,
        previous_transition_hash=None,
    )
    h2 = compute_transition_hash(
        sequence=1,
        registry_id="default",
        timestamp="t",
        actor="a",
        dimension="d",
        from_status="A",
        to_status="B",
        rationale="r",
        evidence_sha256=None,
        previous_transition_hash=None,
    )
    assert h1 == h2 and len(h1) == 64
