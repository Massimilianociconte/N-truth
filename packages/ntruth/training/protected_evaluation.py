"""Protected test/external custody: one-shot permit, append-only ledger, attestation."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ntruth.schemas.core import content_checksum
from ntruth.training.blind_evaluation import PROTECTED_EVALUATION_BLOCKER
from ntruth.training.fd_isolation import (
    close_isolated,
    consume_isolated_bytes,
    isolate_verified_file,
)

PERMIT_SCHEMA_VERSION = "1.0.0"
LEDGER_SCHEMA_VERSION = "1.0.0"
ATTESTATION_SCHEMA_VERSION = "1.0.0"
DEVELOPMENT_MARK = "development_opened.json"
PROTECTED_SCOPES = frozenset({"test", "external"})


class ProtectedEvaluationError(RuntimeError):
    """Fail-closed protected evaluation error."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ProtectedEvaluationError("timestamp senza fuso")
    return parsed


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtectedEvaluationError(f"{label} non leggibile: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProtectedEvaluationError(f"{label} deve essere un oggetto JSON")
    return payload


def physical_vault_root(base: Path) -> Path:
    return base / "protected-vault"


def seal_protected_splits(
    custody_snapshot: Path,
    vault_dir: Path,
    *,
    commitments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Copy only test/external into a vault physically outside the training view."""

    from ntruth.training.mlx_runtime import validate_snapshot_integrity

    custody = validate_snapshot_integrity(custody_snapshot.resolve())
    target = vault_dir.resolve()
    custody_root = custody_snapshot.resolve()
    if target.is_relative_to(custody_root) or custody_root.is_relative_to(target):
        raise ProtectedEvaluationError(
            "vault protetto e custody devono avere root fisicamente separati"
        )
    if target.exists():
        raise ProtectedEvaluationError(f"vault protetto gia esistente: {target}")
    target.mkdir(parents=True)
    files: dict[str, dict[str, Any]] = {}
    for split, filename in (("test", "test.jsonl"), ("external", "external.jsonl")):
        source = custody_root / filename
        if source.is_symlink() or not source.is_file():
            raise ProtectedEvaluationError(f"payload protetto assente o symlink: {filename}")
        payload = source.read_bytes()
        digest = _sha256_bytes(payload)
        expected = commitments.get(split) or custody["file_hashes"][filename]
        expected_hash = expected if isinstance(expected, str) else expected.get("sha256")
        if digest != expected_hash:
            raise ProtectedEvaluationError(f"checksum vault non coerente per {split}")
        destination = target / filename
        destination.write_bytes(payload)
        os.chmod(destination, stat.S_IRUSR)
        files[split] = {
            "filename": filename,
            "sha256": digest,
            "size_bytes": len(payload),
        }
    manifest = {
        "schema_version": "1.0.0",
        "artifact_type": "ntruth-protected-evaluation-vault",
        "custody_snapshot_id": custody["snapshot_id"],
        "custody_snapshot_sha256": custody["snapshot_sha256"],
        "files": files,
        "development_opened": False,
    }
    manifest["vault_sha256"] = content_checksum(
        {key: value for key, value in manifest.items() if key != "vault_sha256"}
    )
    _write_json(target / "vault-manifest.json", manifest)
    return manifest


def mark_development_opened(path: Path, *, reason: str) -> None:
    mark = {
        "schema_version": "1.0.0",
        "artifact_type": "ntruth-development-opened-mark",
        "path": str(path),
        "reason": reason,
        "opened_at": _utc_now().isoformat().replace("+00:00", "Z"),
    }
    _write_json(path if path.name == DEVELOPMENT_MARK else path / DEVELOPMENT_MARK, mark)


def _is_development_opened(vault_dir: Path, payload_sha256: str) -> bool:
    mark_path = vault_dir / DEVELOPMENT_MARK
    if mark_path.is_file():
        return True
    for candidate in vault_dir.glob("*.jsonl"):
        if candidate.name in {"test.jsonl", "external.jsonl"}:
            continue
        if candidate.is_file() and _sha256_bytes(candidate.read_bytes()) == payload_sha256:
            return True
    return False


def issue_permit(
    *,
    scope: str,
    vault_dir: Path,
    ttl: timedelta,
    issuer_role: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if scope not in PROTECTED_SCOPES:
        raise ProtectedEvaluationError(f"scope permit non valido: {scope}")
    if not issuer_role.strip():
        raise ProtectedEvaluationError("issuer_role richiesto")
    if ttl <= timedelta(0):
        raise ProtectedEvaluationError("scadenza permit non positiva")
    current = now or _utc_now()
    vault = _read_json(vault_dir / "vault-manifest.json", label="vault manifest")
    files = vault.get("files")
    if not isinstance(files, dict) or scope not in files:
        raise ProtectedEvaluationError(f"vault privo dello split {scope}")
    entry = files[scope]
    permit = {
        "schema_version": PERMIT_SCHEMA_VERSION,
        "artifact_type": "ntruth-protected-evaluation-permit",
        "permit_id": f"permit-{secrets.token_hex(8)}",
        "scope": scope,
        "nonce": secrets.token_hex(16),
        "issued_at": current.isoformat().replace("+00:00", "Z"),
        "expires_at": (current + ttl).isoformat().replace("+00:00", "Z"),
        "issuer_role": issuer_role,
        "vault_sha256": vault.get("vault_sha256"),
        "payload_sha256": entry["sha256"],
        "filename": entry["filename"],
    }
    permit["permit_sha256"] = content_checksum(
        {key: value for key, value in permit.items() if key != "permit_sha256"}
    )
    return permit


def _empty_ledger() -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "artifact_type": "ntruth-protected-evaluation-ledger",
        "entries": [],
    }


def load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_ledger()
    ledger = _read_json(path, label="evaluation ledger")
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise ProtectedEvaluationError("schema ledger non supportato")
    if ledger.get("artifact_type") != "ntruth-protected-evaluation-ledger":
        raise ProtectedEvaluationError("artifact_type ledger non valido")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise ProtectedEvaluationError("ledger entries non valide")
    return ledger


def append_ledger(path: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    """Append-only: existing bytes are never rewritten in place."""

    ledger = load_ledger(path)
    previous = tuple(ledger["entries"])
    if any(
        isinstance(item, dict) and item.get("permit_id") == entry.get("permit_id")
        for item in previous
    ):
        raise ProtectedEvaluationError("permit gia consumato: monouso")
    ledger = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "artifact_type": "ntruth-protected-evaluation-ledger",
        "entries": [*previous, dict(entry)],
    }
    if path.exists():
        existing = path.read_bytes()
        parsed = json.loads(existing.decode("utf-8"))
        if parsed.get("entries") != list(previous):
            raise ProtectedEvaluationError("ledger non append-only: contenuto mutato")
    _write_json(path, ledger)
    return ledger


def consume_permit(
    permit: Mapping[str, Any],
    *,
    vault_dir: Path,
    ledger_path: Path,
    now: datetime | None = None,
    development_test: bool = False,
) -> dict[str, Any]:
    if set(permit) < {
        "schema_version",
        "scope",
        "nonce",
        "expires_at",
        "permit_id",
        "payload_sha256",
        "filename",
    }:
        raise ProtectedEvaluationError("permit incompleto: servono scope, nonce e scadenza")
    if permit.get("schema_version") != PERMIT_SCHEMA_VERSION:
        raise ProtectedEvaluationError("schema permit non supportato")
    scope = permit.get("scope")
    if scope not in PROTECTED_SCOPES:
        raise ProtectedEvaluationError(f"scope permit non valido: {scope}")
    nonce = permit.get("nonce")
    if not isinstance(nonce, str) or len(nonce) < 16:
        raise ProtectedEvaluationError("nonce permit assente")
    current = now or _utc_now()
    if current >= _parse_time(str(permit["expires_at"])):
        raise ProtectedEvaluationError("permit scaduto")
    if development_test:
        raise ProtectedEvaluationError(
            "un test gia aperto in development non e il test protetto"
        )
    if _is_development_opened(vault_dir, str(permit["payload_sha256"])):
        raise ProtectedEvaluationError(
            "un test gia aperto in development non e il test protetto"
        )

    payload_path = vault_dir / str(permit["filename"])
    isolated = isolate_verified_file(
        payload_path,
        label=f"protected-{scope}",
        expected_sha256=str(permit["payload_sha256"]),
    )
    try:
        consumed = consume_isolated_bytes(isolated)
    finally:
        close_isolated(isolated)
    if _sha256_bytes(consumed) != permit["payload_sha256"]:
        raise ProtectedEvaluationError("payload protetto non coincide col permit")

    entry = {
        "permit_id": permit["permit_id"],
        "permit_sha256": permit.get("permit_sha256"),
        "nonce": nonce,
        "scope": scope,
        "payload_sha256": permit["payload_sha256"],
        "consumed_at": current.isoformat().replace("+00:00", "Z"),
    }
    ledger = append_ledger(ledger_path, entry)
    attestation = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "artifact_type": "ntruth-protected-evaluation-attestation",
        "permit_id": permit["permit_id"],
        "scope": scope,
        "nonce": nonce,
        "payload_sha256": permit["payload_sha256"],
        "ledger_entry_count": len(ledger["entries"]),
        "consumed_at": entry["consumed_at"],
        "blocker_if_unattested": PROTECTED_EVALUATION_BLOCKER,
    }
    attestation["attestation_sha256"] = content_checksum(
        {key: value for key, value in attestation.items() if key != "attestation_sha256"}
    )
    verify_attestation(attestation, ledger)
    return attestation


def verify_attestation(attestation: Mapping[str, Any], ledger: Mapping[str, Any]) -> None:
    expected = content_checksum(
        {key: value for key, value in attestation.items() if key != "attestation_sha256"}
    )
    if attestation.get("attestation_sha256") != expected:
        raise ProtectedEvaluationError("attestazione non verificabile")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise ProtectedEvaluationError("ledger assente dall'attestazione")
    matches = [
        item
        for item in entries
        if isinstance(item, dict) and item.get("permit_id") == attestation.get("permit_id")
    ]
    if len(matches) != 1:
        raise ProtectedEvaluationError("attestazione non corrisponde a un unico consumo")
    match = matches[0]
    if match.get("nonce") != attestation.get("nonce"):
        raise ProtectedEvaluationError("nonce attestazione non coincide col ledger")
    if match.get("payload_sha256") != attestation.get("payload_sha256"):
        raise ProtectedEvaluationError("payload attestazione non coincide col ledger")


def reject_open_development_as_protected(path: Path) -> None:
    raise ProtectedEvaluationError(
        f"un test gia aperto in development non e il test protetto: {path}"
    )
