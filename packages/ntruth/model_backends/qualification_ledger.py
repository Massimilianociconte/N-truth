"""Ledger append-only delle transizioni di qualificazione Train A.

**Policy di persistenza (ledger-first):**
- SQLite e la **sola fonte autorevole** delle transizioni.
- Il mirror JSON e sempre **rigenerabile** dal ledger.
- Un crash dopo COMMIT SQLite e prima del mirror JSON **non** annulla la
  transizione: al load successivo il JSON viene ricostruito.
- Il sistema e **tamper-evident**, non tamper-proof: un attaccante con accesso
  completo al filesystem puo sostituire ledger+evidenze; per release importanti
  ancorare esternamente l'ultimo ``transition_hash``.

Garanzie:
- trigger: vietano UPDATE/DELETE;
- sequence: ``new == max+1`` in ``BEGIN IMMEDIATE``;
- hash chaining: ``previous_transition_hash`` → ``transition_hash``;
- evidence content-addressed (SHA-256);
- bootstrap GENESIS + meta anti-reseed silenzioso.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class QualificationLedgerError(RuntimeError):
    """Errore di integrita o di scrittura del ledger."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_meta (
    registry_id TEXT PRIMARY KEY,
    genesis_at TEXT NOT NULL,
    genesis_actor TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_json_sha256 TEXT,
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
    previous_transition_hash TEXT,
    transition_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (registry_id, sequence),
    FOREIGN KEY (registry_id) REFERENCES ledger_meta(registry_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_qualification_transitions_hash
    ON qualification_transitions(registry_id, transition_hash);

CREATE TRIGGER IF NOT EXISTS qualification_transitions_forbid_update
BEFORE UPDATE ON qualification_transitions
BEGIN
    SELECT RAISE(ABORT, 'qualification_transitions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS qualification_transitions_forbid_delete
BEFORE DELETE ON qualification_transitions
BEGIN
    SELECT RAISE(ABORT, 'qualification_transitions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS ledger_meta_forbid_delete
BEFORE DELETE ON ledger_meta
BEGIN
    SELECT RAISE(ABORT, 'ledger_meta is append-only (no delete)');
END;
"""

# Seed/bootstrap dimension: prima riga della catena.
GENESIS_DIMENSION = "GENESIS"
LEDGER_SCHEMA_VERSION = "1.0.0"

# Lock di processo per append concorrenti sullo stesso path (oltre a BEGIN IMMEDIATE).
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
            "previous_transition_hash": self.previous_transition_hash,
            "transition_hash": self.transition_hash,
        }


def default_ledger_path(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[3]
    return root / "models" / "registry" / "qualification_ledger.sqlite3"


def default_evidence_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[3]
    return root / "models" / "registry" / "qualification_evidence"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def compute_transition_hash(
    *,
    sequence: int,
    registry_id: str,
    timestamp: str,
    actor: str,
    dimension: str,
    from_status: str,
    to_status: str,
    rationale: str,
    evidence_sha256: str | None,
    previous_transition_hash: str | None,
) -> str:
    payload = {
        "sequence": sequence,
        "registry_id": registry_id,
        "timestamp": timestamp,
        "actor": actor,
        "dimension": dimension,
        "from_status": from_status,
        "to_status": to_status,
        "rationale": rationale,
        "evidence_sha256": evidence_sha256,
        "previous_transition_hash": previous_transition_hash,
    }
    return _sha256_text(_canonical_json(payload))


def store_evidence_payload(
    evidence: str | Mapping[str, Any] | Path | None,
    *,
    evidence_root: Path,
) -> tuple[str | None, str | None]:
    """Restituisce (sha256, relative_path) content-addressed; None se assente."""

    if evidence is None:
        return None, None
    if isinstance(evidence, Path):
        data = evidence.read_bytes()
        digest = _sha256_bytes(data)
        relative = Path("sha256") / digest[:2] / digest
        target = evidence_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(target)
        if _sha256_bytes(target.read_bytes()) != digest:
            raise QualificationLedgerError(f"evidence file corrotto: {target}")
        return digest, relative.as_posix()

    text = _canonical_json(dict(evidence)) if isinstance(evidence, Mapping) else str(evidence)
    data = text.encode("utf-8")
    digest = _sha256_bytes(data)
    relative = Path("sha256") / digest[:2] / digest
    target = evidence_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
    if _sha256_bytes(target.read_bytes()) != digest:
        raise QualificationLedgerError(f"evidence blob corrotto: {target}")
    return digest, relative.as_posix()


def verify_evidence_blob(
    *,
    evidence_root: Path,
    evidence_sha256: str,
    evidence_relative_path: str | None,
) -> None:
    if not evidence_relative_path:
        raise QualificationLedgerError("evidence_relative_path assente con digest presente")
    path = evidence_root / evidence_relative_path
    if not path.is_file():
        raise QualificationLedgerError(f"evidence blob assente: {path}")
    actual = _sha256_bytes(path.read_bytes())
    if actual != evidence_sha256:
        raise QualificationLedgerError(
            f"evidence content mismatch: atteso {evidence_sha256}, trovato {actual}"
        )


class QualificationLedger:
    """Connessione SQLite append-only per un registry_id (tamper-evident locale)."""

    def __init__(
        self,
        path: Path,
        *,
        registry_id: str = "default",
        evidence_root: Path | None = None,
    ) -> None:
        self.path = path.expanduser().resolve()
        self.registry_id = registry_id.strip() or "default"
        self.evidence_root = (evidence_root or default_evidence_root()).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = FULL")
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

    def meta(self) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM ledger_meta WHERE registry_id = ?",
            (self.registry_id,),
        ).fetchone()
        if row is None:
            return None
        # sqlite3.Row non supporta l'appartenenza per chiave ne la conversione
        # diretta a dict: si itera su (indice, nome colonna).
        return {key: row[index] for index, key in enumerate(row.keys())}

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

    def latest(self) -> TransitionRecord | None:
        row = self.connection.execute(
            """
            SELECT * FROM qualification_transitions
            WHERE registry_id = ?
            ORDER BY sequence DESC LIMIT 1
            """,
            (self.registry_id,),
        ).fetchone()
        return _row_to_record(row) if row else None

    def list_transitions(self) -> tuple[TransitionRecord, ...]:
        rows = self.connection.execute(
            """
            SELECT * FROM qualification_transitions
            WHERE registry_id = ?
            ORDER BY sequence ASC
            """,
            (self.registry_id,),
        ).fetchall()
        return tuple(_row_to_record(row) for row in rows)

    def export_transition_log(self) -> list[dict[str, Any]]:
        """Mirror rigenerabile per il JSON registry."""

        return [item.as_dict() for item in self.list_transitions()]

    def verify_chain(self, *, verify_evidence: bool = True) -> None:
        """Verifica sequence 1..N senza buchi, hash chaining e evidence CA."""

        previous_hash: str | None = None
        expected_sequence = 1
        records = self.list_transitions()
        if self.is_initialized() and not records:
            raise QualificationLedgerError(
                "ledger_meta.initialized=1 ma transition table vuota: "
                "possibile cancellazione; non reseed automatico (richiede allow_reseed)"
            )
        for record in records:
            if record.sequence != expected_sequence:
                raise QualificationLedgerError(
                    f"sequence non monotona/senza buchi: attesa {expected_sequence}, "
                    f"trovata {record.sequence}"
                )
            if record.previous_transition_hash != previous_hash:
                raise QualificationLedgerError(
                    f"hash chain rotta a sequence={record.sequence}: "
                    f"previous atteso {previous_hash!r}, trovato {record.previous_transition_hash!r}"
                )
            recomputed = compute_transition_hash(
                sequence=record.sequence,
                registry_id=record.registry_id,
                timestamp=record.timestamp,
                actor=record.actor,
                dimension=record.dimension,
                from_status=record.from_status,
                to_status=record.to_status,
                rationale=record.rationale,
                evidence_sha256=record.evidence_sha256,
                previous_transition_hash=record.previous_transition_hash,
            )
            if recomputed != record.transition_hash:
                raise QualificationLedgerError(
                    f"transition_hash non valido a sequence={record.sequence}"
                )
            if verify_evidence and record.evidence_sha256:
                verify_evidence_blob(
                    evidence_root=self.evidence_root,
                    evidence_sha256=record.evidence_sha256,
                    evidence_relative_path=record.evidence_relative_path,
                )
            previous_hash = record.transition_hash
            expected_sequence += 1

        if records:
            meta = self.meta()
            if meta and meta.get("last_transition_hash") not in {None, previous_hash}:
                raise QualificationLedgerError(
                    "ledger_meta.last_transition_hash non allineato alla catena"
                )

    def append(
        self,
        *,
        dimension: str,
        from_status: str,
        to_status: str,
        actor: str,
        rationale: str,
        evidence: str | Mapping[str, Any] | Path | None = None,
        timestamp: str | None = None,
    ) -> TransitionRecord:
        """Inserisce una sola transizione con ``sequence == max+1`` in BEGIN IMMEDIATE."""

        actor_clean = actor.strip()
        rationale_clean = rationale.strip()
        if not actor_clean or not rationale_clean:
            raise QualificationLedgerError("actor e rationale obbligatori")
        if not dimension.strip() or not from_status.strip() or not to_status.strip():
            raise QualificationLedgerError("dimension/from_status/to_status obbligatori")

        ts = timestamp or datetime.now(UTC).isoformat().replace("+00:00", "Z")
        evidence_sha, evidence_path = store_evidence_payload(
            evidence,
            evidence_root=self.evidence_root,
        )

        lock = _path_lock(self.path)
        with lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                if not self.is_initialized() and dimension != GENESIS_DIMENSION:
                    # Bootstrap controllato: GENESIS deve essere la prima riga.
                    self.connection.execute("ROLLBACK")
                    raise QualificationLedgerError(
                        "ledger non inizializzato: richiedere bootstrap GENESIS "
                        "(seed_ledger / ensure_genesis) prima di altre transizioni"
                    )

                current_max = self.max_sequence()
                sequence = current_max + 1
                if sequence < 1:
                    raise QualificationLedgerError("sequence calcolata non valida")
                # Monotonicita esplicita: deve essere esattamente max+1.
                if sequence != current_max + 1:
                    raise QualificationLedgerError(
                        f"sequence non monotona: new={sequence} max={current_max}"
                    )

                latest = self.latest()
                previous_hash = None if latest is None else latest.transition_hash
                if latest is not None and latest.sequence != current_max:
                    raise QualificationLedgerError("incoerenza max_sequence vs latest.sequence")

                transition_hash = compute_transition_hash(
                    sequence=sequence,
                    registry_id=self.registry_id,
                    timestamp=ts,
                    actor=actor_clean,
                    dimension=dimension.strip(),
                    from_status=from_status.strip(),
                    to_status=to_status.strip(),
                    rationale=rationale_clean,
                    evidence_sha256=evidence_sha,
                    previous_transition_hash=previous_hash,
                )
                self.connection.execute(
                    """
                    INSERT INTO qualification_transitions(
                        sequence,
                        registry_id,
                        timestamp,
                        actor,
                        dimension,
                        from_status,
                        to_status,
                        rationale,
                        evidence_sha256,
                        evidence_relative_path,
                        previous_transition_hash,
                        transition_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence,
                        self.registry_id,
                        ts,
                        actor_clean,
                        dimension.strip(),
                        from_status.strip(),
                        to_status.strip(),
                        rationale_clean,
                        evidence_sha,
                        evidence_path,
                        previous_hash,
                        transition_hash,
                    ),
                )
                if dimension == GENESIS_DIMENSION:
                    # Mark initialized (UPDATE meta ammesso solo su last_transition_hash /
                    # fields non-delete; usiamo INSERT OR REPLACE solo a genesis).
                    pass
                self.connection.execute(
                    """
                    UPDATE ledger_meta
                    SET last_transition_hash = ?
                    WHERE registry_id = ?
                    """,
                    (transition_hash, self.registry_id),
                )
                # Se meta manca (solo test grezzi), non fallire su update 0 rows
                # se non e GENESIS: ensure_genesis deve essere stato chiamato.
                if dimension != GENESIS_DIMENSION and not self.is_initialized():
                    self.connection.execute("ROLLBACK")
                    raise QualificationLedgerError("ledger_meta assente durante append")
                self.connection.execute("COMMIT")
            except sqlite3.Error as exc:
                with contextlib.suppress(sqlite3.Error):
                    self.connection.execute("ROLLBACK")
                raise QualificationLedgerError(f"append fallito: {exc}") from exc

        record = self.latest()
        if record is None:  # pragma: no cover
            raise QualificationLedgerError("append non leggibile dopo insert")
        if record.sequence != self.max_sequence():
            raise QualificationLedgerError("sequence post-append non monotona")
        return record

    def ensure_genesis(
        self,
        *,
        actor: str,
        source_json_sha256: str | None,
        schema_version: str,
        allow_reseed: bool = False,
        rationale: str = "GENESIS: bootstrap del ledger di qualificazione",
    ) -> TransitionRecord | None:
        """Crea GENESIS se ledger non inizializzato. Blocca reseed silenzioso."""

        if self.is_initialized():
            if self.count() == 0 and not allow_reseed:
                raise QualificationLedgerError(
                    "ledger_meta.initialized=1 ma catena vuota: "
                    "possibile wipe; passare allow_reseed=True solo con conferma esplicita"
                )
            return None
        if self.count() > 0 and not allow_reseed:
            raise QualificationLedgerError(
                "transizioni presenti senza ledger_meta: stato incoerente"
            )

        actor_clean = actor.strip() or "ntruth-bootstrap"
        ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        lock = _path_lock(self.path)
        with lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                if self.is_initialized() and not allow_reseed:
                    self.connection.execute("ROLLBACK")
                    return None
                self.connection.execute(
                    """
                    INSERT INTO ledger_meta(
                        registry_id,
                        genesis_at,
                        genesis_actor,
                        schema_version,
                        source_json_sha256,
                        initialized,
                        last_transition_hash
                    ) VALUES (?, ?, ?, ?, ?, 1, NULL)
                    ON CONFLICT(registry_id) DO UPDATE SET
                        genesis_at = excluded.genesis_at,
                        genesis_actor = excluded.genesis_actor,
                        schema_version = excluded.schema_version,
                        source_json_sha256 = excluded.source_json_sha256,
                        initialized = 1
                    """,
                    (
                        self.registry_id,
                        ts,
                        actor_clean,
                        schema_version,
                        source_json_sha256,
                    ),
                )
                self.connection.execute("COMMIT")
            except sqlite3.Error as exc:
                with contextlib.suppress(sqlite3.Error):
                    self.connection.execute("ROLLBACK")
                raise QualificationLedgerError(f"ensure_genesis fallito: {exc}") from exc

        return self.append(
            dimension=GENESIS_DIMENSION,
            from_status="NONE",
            to_status="LEDGER_INITIALIZED",
            actor=actor_clean,
            rationale=rationale,
            evidence={
                "event": "GENESIS",
                "schema_version": schema_version,
                "source_json_sha256": source_json_sha256,
                "ledger_schema_version": LEDGER_SCHEMA_VERSION,
            },
            timestamp=ts,
        )


def _row_to_record(row: sqlite3.Row) -> TransitionRecord:
    return TransitionRecord(
        sequence=int(row["sequence"]),
        registry_id=str(row["registry_id"]),
        timestamp=str(row["timestamp"]),
        actor=str(row["actor"]),
        dimension=str(row["dimension"]),
        from_status=str(row["from_status"]),
        to_status=str(row["to_status"]),
        rationale=str(row["rationale"]),
        evidence_sha256=(
            str(row["evidence_sha256"]) if row["evidence_sha256"] is not None else None
        ),
        evidence_relative_path=(
            str(row["evidence_relative_path"])
            if row["evidence_relative_path"] is not None
            else None
        ),
        previous_transition_hash=(
            str(row["previous_transition_hash"])
            if row["previous_transition_hash"] is not None
            else None
        ),
        transition_hash=str(row["transition_hash"]),
    )


def seed_ledger_from_json_log(
    ledger: QualificationLedger,
    transition_log: list[dict[str, Any]],
    *,
    source_json_sha256: str | None = None,
    schema_version: str = "1.3.0",
    actor: str = "ntruth-bootstrap",
    allow_reseed: bool = False,
) -> int:
    """Bootstrap controllato: GENESIS + import JSON solo se ledger non inizializzato.

    Non riscrive un ledger gia inizializzato. ``allow_reseed`` solo con conferma esplicita.
    """

    if ledger.is_initialized() and ledger.count() > 0 and not allow_reseed:
        return 0
    if ledger.is_initialized() and ledger.count() == 0 and not allow_reseed:
        raise QualificationLedgerError(
            "ledger inizializzato ma vuoto: rifiuto reseed automatico "
            "(cancellazione sospetta del DB)"
        )

    ledger.ensure_genesis(
        actor=actor,
        source_json_sha256=source_json_sha256,
        schema_version=schema_version,
        allow_reseed=allow_reseed,
    )
    inserted = 0
    for entry in transition_log:
        # Salta eventuali GENESIS ridondanti dal mirror.
        if str(entry.get("dimension")) == GENESIS_DIMENSION:
            continue
        ledger.append(
            dimension=str(entry["dimension"]),
            from_status=str(entry["from_status"]),
            to_status=str(entry["to_status"]),
            actor=str(entry["actor"]),
            rationale=str(entry["rationale"]),
            evidence=entry.get("evidence_artifact") or entry.get("evidence_sha256"),
            timestamp=str(entry.get("timestamp") or datetime.now(UTC).isoformat()),
        )
        inserted += 1
    ledger.verify_chain()
    return inserted


def rebuild_json_transition_mirror(ledger: QualificationLedger) -> list[dict[str, Any]]:
    """Rigenera il mirror JSON dal ledger (policy: ledger-first)."""

    ledger.verify_chain(verify_evidence=True)
    return ledger.export_transition_log()


__all__ = [
    "GENESIS_DIMENSION",
    "LEDGER_SCHEMA_VERSION",
    "QualificationLedger",
    "QualificationLedgerError",
    "TransitionRecord",
    "compute_transition_hash",
    "default_evidence_root",
    "default_ledger_path",
    "rebuild_json_transition_mirror",
    "seed_ledger_from_json_log",
    "store_evidence_payload",
    "verify_evidence_blob",
]
