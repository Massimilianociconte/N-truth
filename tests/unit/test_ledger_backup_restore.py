"""Ledger backup/restore: file-level copy preserves chain; corrupt copy fails.

Engineering-only regression test. It proves nothing about scientific
validity. Uses only the public QualificationLedger API plus sqlite3's
online backup API; never touches production data paths.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from ntruth.model_backends.qualification_ledger import (
    QualificationLedger,
    QualificationLedgerError,
)


def _seeded(path: Path, evidence: Path) -> None:
    with QualificationLedger(path, evidence_root=evidence) as ledger:
        ledger.ensure_genesis(
            actor="backup-tester",
            source_json_sha256="b" * 64,
            schema_version="1.3.0",
        )
        ledger.append(
            dimension="runtime_qualification_status",
            from_status="UNVERIFIED",
            to_status="PARTIALLY_VERIFIED",
            actor="backup-tester",
            rationale="pre-backup qualification",
            evidence={"check": "backup_ok"},
        )


def _sqlite_backup(src: Path, dst: Path) -> None:
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def test_backup_restore_preserves_chain(tmp_path: Path) -> None:
    src, evidence = tmp_path / "ledger.sqlite3", tmp_path / "evidence"
    _seeded(src, evidence)

    dst, dst_evidence = tmp_path / "restored.sqlite3", tmp_path / "evidence-restored"
    _sqlite_backup(src, dst)
    shutil.copytree(evidence, dst_evidence)

    with QualificationLedger(dst, evidence_root=dst_evidence) as ledger:
        ledger.verify_chain(verify_evidence=True)
        assert [t.sequence for t in ledger.list_transitions()] == [1, 2]


def test_restored_ledger_without_evidence_fails_evidence_verify(tmp_path: Path) -> None:
    src = tmp_path / "ledger.sqlite3"
    _seeded(src, tmp_path / "evidence")

    dst = tmp_path / "restored-no-evidence.sqlite3"
    _sqlite_backup(src, dst)

    # Chain structure is intact, but evidence verification must fail
    # because the evidence directory was not restored alongside the DB.
    with (
        QualificationLedger(dst, evidence_root=tmp_path / "evidence-missing") as ledger,
        pytest.raises(QualificationLedgerError),
    ):
        ledger.verify_chain(verify_evidence=True)
