"""Model registry and runtime qualification state machine (cluster 2).

Authority hierarchy (see models/registry/AUTHORITY.md):

* **published_qualification_snapshot** (JSONL + public_evidence + tip manifest):
  repository-verifiable source of truth for clones / Git claims.
* **operational_qualification_ledger** (optional local SQLite): append-only host
  ledger while drafting new transitions; gitignored; not published authority.
* **registry_mirror** (``default.json``): derived current state view
  ("default registry record", not "default model").

Factory backend default remains ``legacy_qwen`` (see factory.py). This module
does not promote Granite to operational default.
"""

from __future__ import annotations

import hashlib
import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Any

from ntruth.model_backends.base import ModelProvider
from ntruth.model_backends.constants import (
    GRANITE_CANONICAL_MODEL_ID,
    GRANITE_MLX_REPO,
    GRANITE_MLX_REVISION,
    GRANITE_MLX_WEIGHT_SHA256,
)

REGISTRY_SCHEMA_VERSION = "1.3.0"

# Architectural provisional primary (not factory default).
PROVISIONAL_PRIMARY_MODEL_ID = GRANITE_CANONICAL_MODEL_ID
DEFAULT_MLX_REPO = GRANITE_MLX_REPO

ARTIFACT_FINGERPRINT_KEYS: tuple[str, ...] = (
    "model_id",
    "model_revision",
    "weights_sha256",
    "adapter_sha256",
    "tokenizer_revision",
    "chat_template_hash",
    "quantization",
    "backend",
    "backend_version",
    "schema_version",
    "task_profile",
    "domain_profile",
)


class ModelRegistryError(RuntimeError):
    pass


class MigrationStatus(StrEnum):
    ARCHITECTURE_MIGRATED = "ARCHITECTURE_MIGRATED"
    SUPERSEDED = "SUPERSEDED"


class RuntimeQualificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    STALE = "STALE"


class ScientificValidationStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PILOT_VALIDATED = "PILOT_VALIDATED"
    EXTERNAL_VALIDATED = "EXTERNAL_VALIDATED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def registry_path(repo_root: Path | None = None) -> Path:
    return (repo_root or _repo_root()) / "models" / "registry" / "default.json"


def public_chain_path(repo_root: Path | None = None) -> Path:
    return (repo_root or _repo_root()) / "models" / "registry" / "qualification_chain.jsonl"


def public_chain_manifest_path(repo_root: Path | None = None) -> Path:
    return (
        (repo_root or _repo_root())
        / "models"
        / "registry"
        / "qualification_chain.manifest.json"
    )


def public_evidence_root(repo_root: Path | None = None) -> Path:
    return (repo_root or _repo_root()) / "models" / "registry" / "public_evidence"


def artifact_fingerprint(values: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise ModelRegistryError("artifact_fingerprint requires an object")
    out: dict[str, Any] = {}
    for key in ARTIFACT_FINGERPRINT_KEYS:
        value = values.get(key)
        if value is None or value == "":
            out[key] = None
        elif isinstance(value, str):
            out[key] = value.strip() or None
        else:
            out[key] = value
    return out


def canonical_fingerprint_payload(values: dict[str, Any] | None) -> str:
    fingerprint = artifact_fingerprint(values)
    return json.dumps(
        fingerprint,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_fingerprint_hash(values: dict[str, Any] | None) -> str:
    return hashlib.sha256(canonical_fingerprint_payload(values).encode("utf-8")).hexdigest()


def fingerprints_equal(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return False
    return canonical_fingerprint_hash(left) == canonical_fingerprint_hash(right)


def _binding_is_complete(binding: object) -> bool:
    if not isinstance(binding, dict):
        return False
    fingerprint = artifact_fingerprint(binding)
    required = ("model_id", "model_revision", "weights_sha256", "quantization", "backend")
    return all(fingerprint.get(key) is not None for key in required)


def _positive_scientific(status: ScientificValidationStatus) -> bool:
    return status in {
        ScientificValidationStatus.PILOT_VALIDATED,
        ScientificValidationStatus.EXTERNAL_VALIDATED,
    }


def _positive_runtime(status: RuntimeQualificationStatus) -> bool:
    return status in {
        RuntimeQualificationStatus.PARTIALLY_VERIFIED,
        RuntimeQualificationStatus.VERIFIED,
    }


def _validate_transition_log(block: dict[str, Any]) -> None:
    log = block.get("transition_log")
    if log is None:
        raise ModelRegistryError("qualification.transition_log is required")
    if not isinstance(log, list):
        raise ModelRegistryError("qualification.transition_log must be an array")
    for index, entry in enumerate(log):
        if not isinstance(entry, dict):
            raise ModelRegistryError(f"transition_log[{index}] must be an object")
        for field in (
            "sequence",
            "timestamp",
            "actor",
            "dimension",
            "from_status",
            "to_status",
            "rationale",
            "transition_hash",
        ):
            if entry.get(field) in (None, ""):
                raise ModelRegistryError(
                    f"transition_log[{index}] missing required field {field}"
                )
        if index > 0:
            prev = log[index - 1]
            if int(entry["sequence"]) <= int(prev["sequence"]):
                raise ModelRegistryError("transition_log sequence must be strictly increasing")
            if entry.get("previous_transition_hash") != prev.get("transition_hash"):
                raise ModelRegistryError(
                    f"transition_log[{index}] previous_transition_hash does not match prior tip"
                )


def _validate_qualification_block(block: object) -> None:
    if not isinstance(block, dict):
        raise ModelRegistryError("registry.qualification is required")
    try:
        MigrationStatus(str(block.get("migration_status")))
        runtime = RuntimeQualificationStatus(str(block.get("runtime_qualification_status")))
        scientific = ScientificValidationStatus(str(block.get("scientific_validation_status")))
    except ValueError as exc:
        raise ModelRegistryError(f"invalid qualification status: {exc}") from exc

    _validate_transition_log(block)
    binding = block.get("qualified_artifact")

    if scientific is ScientificValidationStatus.EXTERNAL_VALIDATED and runtime is not (
        RuntimeQualificationStatus.VERIFIED
    ):
        raise ModelRegistryError(
            "INVALID: EXTERNAL_VALIDATED requires runtime_qualification_status=VERIFIED"
        )

    if runtime is RuntimeQualificationStatus.VERIFIED and not _binding_is_complete(binding):
        raise ModelRegistryError(
            "INVALID: VERIFIED requires complete qualified_artifact binding"
        )

    if _positive_scientific(scientific):
        if runtime in {
            RuntimeQualificationStatus.UNVERIFIED,
            RuntimeQualificationStatus.FAILED,
            RuntimeQualificationStatus.STALE,
        }:
            raise ModelRegistryError(
                "INVALID: positive scientific status requires runtime "
                "PARTIALLY_VERIFIED or VERIFIED"
            )
        if not _binding_is_complete(binding):
            raise ModelRegistryError(
                "INVALID: positive scientific status requires complete qualified_artifact"
            )

    if _positive_runtime(runtime) and not _binding_is_complete(binding):
        raise ModelRegistryError(
            "INVALID: PARTIALLY_VERIFIED/VERIFIED require qualified_artifact fingerprint"
        )

    if isinstance(binding, dict) and binding:
        fingerprint = artifact_fingerprint(binding)
        expected = binding.get("canonical_fingerprint_sha256")
        if expected is not None:
            actual = canonical_fingerprint_hash(fingerprint)
            if str(expected) != actual:
                raise ModelRegistryError(
                    "INVALID: qualified_artifact.canonical_fingerprint_sha256 mismatch"
                )


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
    artifact_fingerprint_sha256: str | None = None,
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
        "artifact_fingerprint_sha256": artifact_fingerprint_sha256,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_public_chain(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or public_chain_path()
    if not target.is_file():
        raise ModelRegistryError(f"public qualification chain missing: {target}")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ModelRegistryError(f"invalid JSONL at line {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ModelRegistryError(f"chain line {line_no} must be an object")
        rows.append(row)
    return rows


def verify_public_chain(
    *,
    repo_root: Path | None = None,
    verify_evidence: bool = True,
) -> dict[str, Any]:
    """Verify published JSONL chain integrity (hash links + optional evidence blobs)."""

    root = repo_root or _repo_root()
    chain = load_public_chain(public_chain_path(root))
    if not chain:
        raise ModelRegistryError("public chain is empty")

    previous_hash: str | None = None
    expected_sequence = 1
    evidence_root = public_evidence_root(root)

    for index, entry in enumerate(chain):
        sequence = int(entry["sequence"])
        if sequence != expected_sequence:
            raise ModelRegistryError(
                f"chain sequence gap: expected {expected_sequence}, got {sequence}"
            )
        if entry.get("previous_transition_hash") != previous_hash:
            raise ModelRegistryError(f"chain broken at sequence={sequence}")

        recomputed = compute_transition_hash(
            sequence=sequence,
            registry_id=str(entry.get("registry_id") or "default"),
            timestamp=str(entry["timestamp"]),
            actor=str(entry["actor"]),
            dimension=str(entry["dimension"]),
            from_status=str(entry["from_status"]),
            to_status=str(entry["to_status"]),
            rationale=str(entry["rationale"]),
            evidence_sha256=entry.get("evidence_sha256"),
            previous_transition_hash=entry.get("previous_transition_hash"),
            artifact_fingerprint_sha256=entry.get("artifact_fingerprint_sha256"),
        )
        if recomputed != entry.get("transition_hash"):
            raise ModelRegistryError(
                f"transition_hash mismatch at sequence={sequence}: "
                f"stored={entry.get('transition_hash')}, recomputed={recomputed}"
            )

        if verify_evidence and entry.get("evidence_sha256"):
            rel = entry.get("evidence_relative_path")
            if not rel:
                raise ModelRegistryError(
                    f"evidence_sha256 present without evidence_relative_path at seq={sequence}"
                )
            path = evidence_root / str(rel)
            if not path.is_file():
                raise ModelRegistryError(f"public evidence missing: {path}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != entry["evidence_sha256"]:
                raise ModelRegistryError(
                    f"evidence content mismatch at seq={sequence}: "
                    f"expected {entry['evidence_sha256']}, got {digest}"
                )

        previous_hash = str(entry["transition_hash"])
        expected_sequence += 1

    manifest_path = public_chain_manifest_path(root)
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tip = chain[-1]["transition_hash"]
        if manifest.get("tip_transition_hash") != tip:
            raise ModelRegistryError(
                "qualification_chain.manifest.json tip does not match chain tip"
            )
        if int(manifest.get("event_count") or -1) != len(chain):
            raise ModelRegistryError("manifest event_count does not match chain length")

    return {
        "ok": True,
        "event_count": len(chain),
        "tip_transition_hash": previous_hash,
        "last_to_status": chain[-1].get("to_status"),
        "last_dimension": chain[-1].get("dimension"),
    }


def load_registry(
    path: Path | None = None,
    *,
    verify_public_chain_integrity: bool = True,
) -> dict[str, Any]:
    """Load **derived** registry mirror and validate against published chain.

    ``default.json`` is not an independent authority: when
    ``verify_public_chain_integrity`` is true, the published JSONL snapshot must
    validate and the mirror's PARTIALLY_VERIFIED claim must be backed by a chain
    event.
    """

    target = path or registry_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelRegistryError(f"registry unreadable: {target}: {exc}") from exc

    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ModelRegistryError(
            f"registry schema expected {REGISTRY_SCHEMA_VERSION}, "
            f"got {payload.get('schema_version')!r}"
        )

    # Factory default must not silently flip to granite via registry alone.
    factory_default = str(payload.get("factory_default_provider") or "legacy_qwen")
    if factory_default not in {"legacy_qwen", "granite", "generic"}:
        raise ModelRegistryError(f"invalid factory_default_provider: {factory_default}")

    # Annotate authority roles for callers / audits.
    payload.setdefault(
        "authority",
        {
            "published_qualification_snapshot": "qualification_chain.jsonl",
            "registry_mirror": "default.json",
            "operational_ledger": "qualification_ledger.sqlite3 (local, optional)",
            "note": "default.json is the default registry record, not the default model",
        },
    )

    _validate_qualification_block(payload.get("qualification"))

    if verify_public_chain_integrity:
        repo_root = target.resolve().parents[2]
        chain_report = verify_public_chain(repo_root=repo_root)
        block = payload["qualification"]
        chain = load_public_chain(public_chain_path(repo_root))
        if block.get("runtime_qualification_status") == (
            RuntimeQualificationStatus.PARTIALLY_VERIFIED.value
        ):
            runtime_events = [
                e
                for e in chain
                if e.get("dimension") == "runtime_qualification_status"
                and e.get("to_status")
                == RuntimeQualificationStatus.PARTIALLY_VERIFIED.value
            ]
            if not runtime_events:
                raise ModelRegistryError(
                    "PARTIALLY_VERIFIED claimed without public chain event"
                )
            # Derived mirror tip hash should match published tip.
            tip = chain[-1]["transition_hash"]
            if chain_report.get("tip_transition_hash") != tip:
                raise ModelRegistryError("chain report tip mismatch")
        payload = {**payload, "_public_chain_report": chain_report}

    return payload

def qualification_status(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    data = registry if registry is not None else load_registry()
    block = data["qualification"]
    return {
        "migration_status": block["migration_status"],
        "runtime_qualification_status": block["runtime_qualification_status"],
        "scientific_validation_status": block["scientific_validation_status"],
        "factory_default_provider": data.get("factory_default_provider", "legacy_qwen"),
        "provisional_primary_model_id": data.get(
            "provisional_primary_model_id", PROVISIONAL_PRIMARY_MODEL_ID
        ),
        "summary": block.get("summary")
        or (
            "Architecture migrated; runtime qualification is artifact-bound; "
            "scientific validation not started; factory default remains legacy_qwen."
        ),
    }


def is_scientifically_releasable(registry: dict[str, Any] | None = None) -> bool:
    data = registry if registry is not None else load_registry()
    block = data["qualification"]
    runtime = RuntimeQualificationStatus(str(block["runtime_qualification_status"]))
    scientific = ScientificValidationStatus(str(block["scientific_validation_status"]))
    return (
        runtime is RuntimeQualificationStatus.VERIFIED
        and scientific is ScientificValidationStatus.EXTERNAL_VALIDATED
    )


def claim_gates(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fail-closed claim gates (research may continue under weaker statuses)."""

    data = registry if registry is not None else load_registry()
    block = data["qualification"]
    runtime = RuntimeQualificationStatus(str(block["runtime_qualification_status"]))
    scientific = ScientificValidationStatus(str(block["scientific_validation_status"]))

    exploratory = True  # always allowed
    internal_pilot = runtime in {
        RuntimeQualificationStatus.PARTIALLY_VERIFIED,
        RuntimeQualificationStatus.VERIFIED,
    }
    external_validation = runtime is RuntimeQualificationStatus.VERIFIED
    scientific_release = is_scientifically_releasable(data)

    def _gate(allowed: bool, reason: str, next_state: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"allowed": allowed, "reason": reason}
        if next_state:
            out["required_next_state"] = next_state
        return out

    return {
        "exploratory_benchmark": _gate(exploratory, "ALWAYS_ALLOWED"),
        "internal_pilot": _gate(
            internal_pilot,
            "OK" if internal_pilot else "RUNTIME_UNVERIFIED",
            None if internal_pilot else "PARTIALLY_VERIFIED",
        ),
        "external_validation": _gate(
            external_validation,
            "OK" if external_validation else "RUNTIME_NOT_VERIFIED",
            None if external_validation else "VERIFIED",
        ),
        "scientifically_releasable": _gate(
            scientific_release,
            "OK" if scientific_release else "SCIENCE_OR_RUNTIME_INCOMPLETE",
            None if scientific_release else "EXTERNAL_VALIDATED_AND_RUNTIME_VERIFIED",
        ),
        "runtime": runtime.value,
        "scientific": scientific.value,
    }


def evaluate_qualification_against_artifact(
    *,
    current_artifact: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = registry if registry is not None else load_registry()
    block = data["qualification"]
    runtime = RuntimeQualificationStatus(str(block["runtime_qualification_status"]))
    scientific = ScientificValidationStatus(str(block["scientific_validation_status"]))
    binding = block.get("qualified_artifact")
    current = artifact_fingerprint(current_artifact)
    match = fingerprints_equal(binding if isinstance(binding, dict) else None, current)

    evaluated_runtime = runtime
    evaluated_scientific = scientific
    stale_reasons: list[str] = []
    if _positive_runtime(runtime) and not match:
        evaluated_runtime = RuntimeQualificationStatus.STALE
        stale_reasons.append("artifact_fingerprint_mismatch")
    if _positive_scientific(scientific) and not match:
        evaluated_scientific = ScientificValidationStatus.INVALIDATED
        stale_reasons.append("scientific_binding_mismatch")

    return {
        "match": match,
        "evaluated_runtime_qualification_status": evaluated_runtime.value,
        "evaluated_scientific_validation_status": evaluated_scientific.value,
        "stale_reasons": stale_reasons,
        "current_fingerprint_sha256": canonical_fingerprint_hash(current),
        "qualified_fingerprint_sha256": (
            canonical_fingerprint_hash(binding) if isinstance(binding, dict) else None
        ),
        "note": "Qualification does not transfer across MLX/GGUF/BF16/adapter variants.",
    }


def assert_factory_default_not_silently_granite(registry: dict[str, Any] | None = None) -> None:
    data = registry if registry is not None else load_registry()
    if str(data.get("factory_default_provider")) == "granite":
        # Allowed only if explicitly set; cluster 2 published registry must keep legacy_qwen.
        pass


__all__ = [
    "ARTIFACT_FINGERPRINT_KEYS",
    "DEFAULT_MLX_REPO",
    "MigrationStatus",
    "ModelRegistryError",
    "PROVISIONAL_PRIMARY_MODEL_ID",
    "REGISTRY_SCHEMA_VERSION",
    "RuntimeQualificationStatus",
    "ScientificValidationStatus",
    "artifact_fingerprint",
    "canonical_fingerprint_hash",
    "canonical_fingerprint_payload",
    "claim_gates",
    "compute_transition_hash",
    "evaluate_qualification_against_artifact",
    "fingerprints_equal",
    "is_scientifically_releasable",
    "load_public_chain",
    "load_registry",
    "public_chain_manifest_path",
    "public_chain_path",
    "public_evidence_root",
    "qualification_status",
    "registry_path",
    "verify_public_chain",
]
