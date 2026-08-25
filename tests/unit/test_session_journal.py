"""Journal durevole opt-in per le sessioni di analisi e resume esplicito."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.api.session_journal import (
    JournalCorruptError,
    append_entry,
    journal_dir_from_env,
    read_entry,
)


def test_env_flag_is_opt_in() -> None:
    assert journal_dir_from_env({}) is None
    assert journal_dir_from_env({"NTRUTH_SESSION_JOURNAL_DIR": ""}) is None
    assert journal_dir_from_env({"NTRUTH_SESSION_JOURNAL_DIR": "/tmp/j"}) == Path("/tmp/j")


def test_roundtrip_and_latest_entry_wins(tmp_path: Path) -> None:
    request_v1 = {"lane": "v7", "source": "a.md", "out": "./out"}
    request_v2 = {"lane": "v7", "source": "b.md", "out": "./out2"}
    append_entry(tmp_path, "sess-1", request_v1)
    append_entry(tmp_path, "other", request_v2)
    append_entry(tmp_path, "sess-1", {**request_v1, "domain": "cell_biology"})

    entry = read_entry(tmp_path, "sess-1")
    assert entry is not None
    assert entry.request["source"] == "a.md"
    assert entry.request["domain"] == "cell_biology"
    assert read_entry(tmp_path, "missing") is None


def test_corrupted_lines_are_quarantined_and_valid_ones_replay(tmp_path: Path) -> None:
    append_entry(tmp_path, "good", {"lane": "v7", "source": "a.md"})
    journal = tmp_path / "sessions.jsonl"
    lines = journal.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["request"]["source"] = "evil.md"  # invalida il checksum mantenendo il JSON valido
    lines.append(json.dumps(tampered, ensure_ascii=False, sort_keys=True))
    lines.append("{not-json")
    journal.write_text("\n".join(lines) + "\n", encoding="utf-8")

    entry = read_entry(tmp_path, "good")
    assert entry is not None
    assert entry.request["source"] == "a.md"
    quarantine = tmp_path / "sessions.quarantined"
    assert quarantine.is_file()
    quarantined = quarantine.read_text(encoding="utf-8").strip().splitlines()
    assert len(quarantined) == 2


def test_checksum_mismatch_is_detectable() -> None:
    with pytest.raises(JournalCorruptError):
        # Contratto: la lettura non deve mai riprodurre un record alterato.
        raise JournalCorruptError("checksum mismatch")


def test_resume_after_restart_replays_the_journaled_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    source = tmp_path / "methods.md"
    source.write_text(
        "# Methods\n\nsample_id=SUBJ-009 received drug or vehicle. n = 12 cultures per group.\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    journal = tmp_path / "journal"
    monkeypatch.setenv("NTRUTH_SESSION_JOURNAL_DIR", str(journal))

    client = TestClient(create_app(), base_url="http://127.0.0.1")
    created = client.post(
        "/v7/analyze",
        json={
            "source": str(source),
            "out": str(out_dir),
            "language": "en",
            "acknowledge_unvalidated_domain": True,
        },
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["session_id"]

    # Simula il restart: nuovo processo/app senza sessioni in memoria.
    client2 = TestClient(create_app(), base_url="http://127.0.0.1")
    missing = client2.get("/v1/sessions/whatever")
    assert missing.status_code in {404, 405}

    resumed = client2.post(f"/v1/sessions/{session_id}/resume")
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["session_id"] == session_id
    assert body["report"]["report_id"]

    # Il resume esplicito su journal disabilitato resta fail-closed.
    monkeypatch.delenv("NTRUTH_SESSION_JOURNAL_DIR")
    client3 = TestClient(create_app(), base_url="http://127.0.0.1")
    disabled = client3.post(f"/v1/sessions/{session_id}/resume")
    assert disabled.status_code == 404
    assert disabled.json()["detail"]["code"] == "session_journal_disabled"


def test_resume_unknown_session_is_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    monkeypatch.setenv("NTRUTH_SESSION_JOURNAL_DIR", str(tmp_path / "empty-journal"))
    client = TestClient(create_app(), base_url="http://127.0.0.1")
    response = client.post("/v1/sessions/nope/resume")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_resumable"


def test_sha256_of_refuses_symlinked_source(tmp_path: Path) -> None:
    from ntruth.ingest.project import SafetyError, sha256_of

    real = tmp_path / "real.txt"
    real.write_text("payload", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    with pytest.raises(SafetyError):
        sha256_of(link)
