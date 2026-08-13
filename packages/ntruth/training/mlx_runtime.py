"""Runtime locale e riproducibile per MLX-LM su Apple Silicon.

Le importazioni MLX/Hugging Face sono lazy: il core deterministico resta privo di
dipendenze ML e continua a funzionare su Linux.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ntruth.reality_gate import (
    DataReadiness,
    GatePurpose,
    RealityGateResult,
    machine_readable_result,
)
from ntruth.schemas.core import content_checksum
from ntruth.training.blockers import (
    FD_ISOLATION_BLOCKER_CODE,
    FD_ISOLATION_BLOCKER_DETAIL,
    SCIENTIFIC_EXECUTION_CLOSED_CODE,
    SCIENTIFIC_EXECUTION_CLOSED_DETAIL,
)
from ntruth.training.records import (
    DatasetManifest,
    PreparationReport,
    PreparedDataset,
    PreparedRecord,
)

PROFILE_SCHEMA_VERSION = "1.0.0"
PROVENANCE_SCHEMA_VERSION = "1.0.0"
RUN_SCHEMA_VERSION = "5.0.0"
SNAPSHOT_SCHEMA_VERSION = "2.0.0"
TRAINING_AUTHORIZATION_SCHEMA_VERSION = "1.0.0"
FD_ISOLATION_BLOCKER = FD_ISOLATION_BLOCKER_DETAIL
_PEAK_MEMORY = re.compile(r"Peak mem(?:ory)?\s+([0-9]+(?:\.[0-9]+)?)\s*GB", re.I)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REAL_SNAPSHOT_FILES = frozenset(
    {
        "train.jsonl",
        "valid.jsonl",
        "test.jsonl",
        "external.jsonl",
        "dataset-manifest.source.json",
        "prepared-records.jsonl",
        "preparation-report.json",
    }
)
_SMOKE_SNAPSHOT_FILES = frozenset({"train.jsonl", "valid.jsonl", "test.jsonl"})
_SPLIT_FILES = {
    "train": "train.jsonl",
    "valid": "valid.jsonl",
    "test": "test.jsonl",
    "external": "external.jsonl",
}
_SOURCE_SPLIT_NAMES = {
    "train": "train",
    "validation": "valid",
    "test": "test",
    "external": "external",
}
_TRAINING_AUTHORIZATION_BINDING_KEYS = frozenset(
    {
        "training_view_id",
        "training_view_sha256",
        "protected_split_seal_sha256",
        "profile_sha256",
        "model_repository",
        "model_revision",
        "source_snapshot_sha256",
        "seed",
    }
)


class MLXPipelineError(RuntimeError):
    """Errore operativo previsto della corsia ML locale."""


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    output: str
    elapsed_seconds: float
    peak_memory_gb: float | None


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_regular_file_bytes(path: Path, *, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MLXPipelineError(f"{label} non e un file regolare: {path}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError as exc:
        raise MLXPipelineError(
            f"{label} non leggibile o symlink non ammesso: {path}: {exc}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _assert_current_training_readiness(result: RealityGateResult) -> None:
    """Prevent an open legacy gate from bypassing the normative PRD v9 projection."""

    from ntruth.training.readiness import (
        OverallReadiness,
        project_small_model_training_readiness,
    )

    projection = project_small_model_training_readiness(result)
    if projection.overall is not OverallReadiness.READY:
        raise MLXPipelineError(
            "training readiness normativa PRD_V9 non READY: "
            f"overall={projection.overall.value}, "
            f"v9_schema_conformance={projection.v9_schema_conformance}, "
            f"model_selection_status={projection.model_selection_status.value}"
        )


def build_training_authorization_envelope(
    result: RealityGateResult,
    *,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a canonical Reality Gate result to exactly one preregistered run."""

    normalized_binding = _validate_training_authorization_binding_payload(dict(binding))
    envelope: dict[str, Any] = {
        "schema_version": TRAINING_AUTHORIZATION_SCHEMA_VERSION,
        "artifact_type": "ntruth-training-authorization-envelope",
        "gate": machine_readable_result(result),
        "binding": normalized_binding,
    }
    envelope["checksum"] = content_checksum(envelope)
    return envelope


def _validate_training_authorization_binding_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _TRAINING_AUTHORIZATION_BINDING_KEYS:
        raise MLXPipelineError("binding autorizzazione training incompleto o inatteso")
    normalized = dict(value)
    for key in (
        "training_view_sha256",
        "protected_split_seal_sha256",
        "profile_sha256",
        "source_snapshot_sha256",
    ):
        item = normalized.get(key)
        if not isinstance(item, str) or _SHA256.fullmatch(item) is None:
            raise MLXPipelineError(f"binding autorizzazione training non valido: {key}")
    for key in ("training_view_id", "model_repository", "model_revision"):
        item = normalized.get(key)
        if not isinstance(item, str) or not item.strip():
            raise MLXPipelineError(f"binding autorizzazione training non valido: {key}")
    seed = normalized.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise MLXPipelineError("binding autorizzazione training non valido: seed")
    return normalized


def _load_training_authorization(path: Path) -> dict[str, Any]:
    artifact_bytes = _read_regular_file_bytes(path, label="autorizzazione training")
    try:
        raw = json.loads(artifact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MLXPipelineError(f"autorizzazione training non leggibile: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise MLXPipelineError("autorizzazione training deve essere un oggetto JSON")
    if set(raw) != {"schema_version", "artifact_type", "gate", "binding", "checksum"}:
        raise MLXPipelineError(
            "autorizzazione training deve essere un envelope canonico v1; bare gate rifiutato"
        )
    if raw.get("schema_version") != TRAINING_AUTHORIZATION_SCHEMA_VERSION:
        raise MLXPipelineError("schema autorizzazione training non supportato")
    if raw.get("artifact_type") != "ntruth-training-authorization-envelope":
        raise MLXPipelineError("artifact_type autorizzazione training non valido")
    checksum = raw.get("checksum")
    envelope_payload = {key: value for key, value in raw.items() if key != "checksum"}
    if not isinstance(checksum, str) or checksum != content_checksum(envelope_payload):
        raise MLXPipelineError("checksum contenuto autorizzazione training non valido")
    gate_payload = raw.get("gate")
    if not isinstance(gate_payload, dict):
        raise MLXPipelineError("gate assente dall'envelope autorizzazione training")
    gate_checksum = gate_payload.get("checksum")
    canonical_gate_payload = {
        key: value for key, value in gate_payload.items() if key != "checksum"
    }
    if not isinstance(gate_checksum, str) or gate_checksum != content_checksum(
        canonical_gate_payload
    ):
        raise MLXPipelineError("checksum RealityGate nell'autorizzazione non valido")
    try:
        result = RealityGateResult.model_validate(canonical_gate_payload)
    except ValueError as exc:
        raise MLXPipelineError(f"autorizzazione training non valida: {exc}") from exc
    if gate_payload != machine_readable_result(result):
        raise MLXPipelineError(
            "contenuto autorizzazione training non canonico per RealityGateResult"
        )
    if result.purpose is not GatePurpose.SUBSTANTIVE_TRAINING:
        raise MLXPipelineError("autorizzazione training richiede purpose=SUBSTANTIVE_TRAINING")
    if result.substantive_training_allowed is not True:
        raise MLXPipelineError("autorizzazione training blocca il training sostanziale")
    if result.data_readiness.status != DataReadiness.READY.value:
        raise MLXPipelineError("autorizzazione training priva di data_readiness=READY")
    blockers = (
        *result.engineering_readiness.blockers,
        *result.data_readiness.blockers,
        *result.scientific_validation.blockers,
        *result.overall_blockers,
    )
    if blockers:
        raise MLXPipelineError("autorizzazione training contiene blocker")
    _assert_current_training_readiness(result)
    binding = _validate_training_authorization_binding_payload(raw.get("binding"))
    return {
        "artifact_path": str(path.resolve()),
        "artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "envelope_checksum": checksum,
        "gate_checksum": gate_checksum,
        "gate_version": result.gate_version,
        "purpose": result.purpose.value,
        "binding": binding,
    }


def _assert_training_authorization_binding(
    authorization: Mapping[str, Any],
    *,
    dataset: Mapping[str, Any],
    profile: Mapping[str, Any],
    profile_sha256: str,
    source_snapshot_sha256: str,
    seed: int,
) -> None:
    binding = authorization.get("binding")
    if not isinstance(binding, dict):
        raise MLXPipelineError("binding autorizzazione training assente")
    model = profile.get("model")
    if not isinstance(model, dict):
        raise MLXPipelineError("profilo privo di binding modello")
    expected = {
        "training_view_id": dataset.get("training_view_id"),
        "training_view_sha256": dataset.get("training_view_sha256"),
        "protected_split_seal_sha256": dataset.get("protected_split_seal_sha256"),
        "profile_sha256": profile_sha256,
        "model_repository": model.get("repository"),
        "model_revision": model.get("revision"),
        "source_snapshot_sha256": source_snapshot_sha256,
        "seed": seed,
    }
    mismatches = sorted(key for key, value in expected.items() if binding.get(key) != value)
    if mismatches:
        raise MLXPipelineError(
            "binding autorizzazione training non coincide col run: " + ", ".join(mismatches)
        )


def _load_resume_state(state_path: Path) -> dict[str, Any]:
    state_bytes = _read_regular_file_bytes(state_path, label="stato run")
    try:
        state = json.loads(state_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MLXPipelineError(f"stato run non riprendibile: {exc}") from exc
    if not isinstance(state, dict):
        raise MLXPipelineError("stato run non riprendibile: atteso oggetto JSON")
    if state.get("schema_version") != RUN_SCHEMA_VERSION:
        raise MLXPipelineError("schema run cambiato: impossibile riprendere il run")
    return state


def _assert_resume_authorization(
    state: Mapping[str, Any],
    authorization: Mapping[str, str] | None,
    *,
    smoke_test: bool,
) -> None:
    previous = state.get("training_authorization")
    if smoke_test:
        if previous is not None:
            raise MLXPipelineError(
                "lineage autorizzazione inattesa nel run smoke: impossibile riprendere il run"
            )
        return
    if not isinstance(previous, dict) or authorization is None:
        raise MLXPipelineError("lineage autorizzazione assente: impossibile riprendere il run")
    compared_fields = (
        "artifact_sha256",
        "envelope_checksum",
        "gate_checksum",
        "gate_version",
        "purpose",
        "binding",
    )
    if any(previous.get(key) != authorization.get(key) for key in compared_fields):
        raise MLXPipelineError("autorizzazione training cambiata: impossibile riprendere il run")


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _source_snapshot(repo_root: Path) -> dict[str, Any]:
    """Fingerprint the code and lock inputs that can change an ML run."""

    candidates = [repo_root / "pyproject.toml", repo_root / "uv.lock"]
    for package in ("training", "parser_ai"):
        candidates.extend(sorted((repo_root / "packages" / "ntruth" / package).rglob("*.py")))
    files = [path for path in candidates if path.is_file()]
    payload = [
        {
            "path": path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in files
    ]
    return {
        "sha256": sha256_json(payload),
        "files": payload,
    }


def _git_state(repo_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"commit": None, "tracked_changes_present": None}
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return result
    if revision.returncode == 0:
        result["commit"] = revision.stdout.strip() or None
    if status.returncode == 0:
        result["tracked_changes_present"] = bool(status.stdout.strip())
    return result


def runtime_environment(repo_root: Path) -> dict[str, Any]:
    """Return a non-secret, machine-readable experiment environment record."""

    source = _source_snapshot(repo_root)
    lock_path = repo_root / "uv.lock"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {
            name: _installed_version(name) for name in ("ntruth", "mlx-lm", "mlx", "transformers")
        },
        "uv_lock_sha256": sha256_file(lock_path) if lock_path.is_file() else None,
        "source_snapshot_sha256": source["sha256"],
        "source_files": source["files"],
        "git": _git_state(repo_root),
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_profile(path: Path) -> dict[str, Any]:
    profile, _checksum = load_profile_artifact(path)
    return profile


def load_profile_artifact(path: Path) -> tuple[dict[str, Any], str]:
    profile_bytes = _read_regular_file_bytes(path, label="profilo MLX")
    try:
        profile = json.loads(profile_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MLXPipelineError(f"profilo MLX non leggibile: {path}: {exc}") from exc
    if not isinstance(profile, dict) or profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise MLXPipelineError(
            f"schema profilo atteso {PROFILE_SCHEMA_VERSION}, ricevuto "
            f"{profile.get('schema_version') if isinstance(profile, dict) else type(profile).__name__}"
        )
    for section in ("runtime", "model", "hardware", "data", "training", "calibration"):
        if not isinstance(profile.get(section), dict):
            raise MLXPipelineError(f"sezione obbligatoria assente nel profilo: {section}")
    expected = int(profile["model"].get("expected_download_bytes", 0))
    if expected <= 0:
        raise MLXPipelineError("expected_download_bytes deve essere positivo")
    if profile["model"].get("quantization_bits") != 4:
        raise MLXPipelineError("il profilo iniziale supporta soltanto una base MLX 4-bit")
    if not re.fullmatch(r"[0-9a-f]{64}", str(profile["model"].get("expected_weight_sha256", ""))):
        raise MLXPipelineError("expected_weight_sha256 mancante o non valido")
    if int(profile["model"].get("expected_weight_bytes", 0)) <= 0:
        raise MLXPipelineError("expected_weight_bytes deve essere positivo")
    return profile, hashlib.sha256(profile_bytes).hexdigest()


def _memory_bytes() -> int | None:
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                check=True,
                capture_output=True,
                text=True,
            )
            return int(result.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None
    return int(pages * page_size)


def _installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _model_path(repo_root: Path, profile: Mapping[str, Any]) -> Path:
    candidate = (repo_root / str(profile["model"]["local_path"])).resolve()
    models_root = (repo_root / "models" / "local").resolve()
    if not candidate.is_relative_to(models_root):
        raise MLXPipelineError("il modello locale deve restare sotto models/local")
    return candidate


def storage_budget(profile: Mapping[str, Any]) -> dict[str, Any]:
    configured = profile.get("storage_budget", {})
    items = configured.get("items_gib", {}) if isinstance(configured, Mapping) else {}
    if not isinstance(items, Mapping):
        raise MLXPipelineError("storage_budget.items_gib deve essere un oggetto")
    normalized = {str(name): float(value) for name, value in items.items()}
    if any(value < 0 for value in normalized.values()):
        raise MLXPipelineError("le stime di spazio non possono essere negative")
    return {
        "items_gib": normalized,
        "total_gib": sum(normalized.values()),
        "free_floor_gib": float(profile["hardware"]["required_free_disk_gib"]),
        "workspace_cap_gib": float(profile["hardware"]["maximum_ntruth_workspace_gib"]),
    }


def doctor(profile_path: Path, repo_root: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    memory = _memory_bytes()
    disk = shutil.disk_usage(repo_root)
    model_path = _model_path(repo_root, profile)
    runtime_version = _installed_version("mlx-lm")
    expected_runtime = str(profile["runtime"]["version"])
    budget = storage_budget(profile)
    system_ok = sys.platform == "darwin" and platform.machine() == "arm64"
    memory_ok = memory is not None and memory >= int(
        float(profile["hardware"]["minimum_unified_memory_gib"]) * 1024**3
    )
    free_gib = disk.free / 1024**3
    download_headroom_gib = free_gib - profile["model"]["expected_download_bytes"] / 1024**3
    disk_ok = download_headroom_gib >= budget["free_floor_gib"]
    model_exists = (model_path / "model.safetensors").is_file()
    result = {
        "profile": str(profile_path),
        "profile_sha256": sha256_file(profile_path),
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "unified_memory_gib": memory / 1024**3 if memory is not None else None,
        "available_disk_gib": free_gib,
        "available_after_model_download_gib": download_headroom_gib,
        "storage_budget": budget,
        "mlx_lm": {"installed": runtime_version, "required": expected_runtime},
        "model": {
            "path": str(model_path),
            "present": model_exists,
            "logical_size_bytes": directory_size(model_path),
        },
        "checks": {
            "apple_silicon": system_ok,
            "memory": memory_ok,
            "disk_download_headroom": disk_ok,
            "runtime_version": runtime_version == expected_runtime,
            "model_present": model_exists,
        },
    }
    result["ready_to_download"] = system_ok and memory_ok and disk_ok
    result["operational_prerequisites_passed"] = (
        result["ready_to_download"] and runtime_version == expected_runtime and model_exists
    )
    from ntruth.training.fd_isolation import fd_isolation_contract_holds

    execution_blockers: list[str] = []
    if not fd_isolation_contract_holds():
        execution_blockers.extend((FD_ISOLATION_BLOCKER_CODE, FD_ISOLATION_BLOCKER))
    execution_blockers.extend(
        (
            "MODEL_SELECTION_BENCHMARK_PENDING",
            SCIENTIFIC_EXECUTION_CLOSED_CODE,
            SCIENTIFIC_EXECUTION_CLOSED_DETAIL,
        )
    )
    result["execution_blockers"] = execution_blockers
    result["ready_to_train"] = False
    return result


def download_model(profile_path: Path, repo_root: Path) -> dict[str, Any]:
    """Scarica lo snapshot fissato soltanto dopo i gate hardware/spazio."""

    profile = load_profile(profile_path)
    status = doctor(profile_path, repo_root)
    if not status["ready_to_download"]:
        raise MLXPipelineError(f"download bloccato dai gate: {status['checks']}")
    target = _model_path(repo_root, profile)
    if target.exists() and any(target.iterdir()):
        provenance = target / "model-provenance.json"
        if provenance.is_file():
            return verify_model(profile_path, repo_root)
        raise MLXPipelineError(
            f"directory modello non vuota e priva di provenance: {target}; revisione manuale richiesta"
        )
    target.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError as exc:
        raise MLXPipelineError("installare prima l'extra ML: uv sync --extra ml --locked") from exc

    model = profile["model"]
    cache_dir = repo_root / "local-data" / "cache" / "huggingface"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    snapshot_download(
        repo_id=str(model["repository"]),
        revision=str(model["revision"]),
        local_dir=target,
        cache_dir=cache_dir,
    )
    base_license = hf_hub_download(
        repo_id=str(model["base_repository"]),
        revision=str(model["base_revision_observed"]),
        filename="LICENSE",
        cache_dir=cache_dir,
    )
    shutil.copyfile(base_license, target / "BASE_MODEL_LICENSE")

    files = []
    for path in sorted(item for item in target.rglob("*") if item.is_file()):
        if ".cache" in path.parts or path.name == "model-provenance.json":
            continue
        files.append(
            {
                "path": path.relative_to(target).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "created_at": utc_now(),
        "repository": model["repository"],
        "revision": model["revision"],
        "base_repository": model["base_repository"],
        "base_revision_observed": model["base_revision_observed"],
        "license": model["license"],
        "license_url": model["license_url"],
        "profile_sha256": sha256_file(profile_path),
        "files": files,
        "total_verified_bytes": sum(
            value for item in files if isinstance((value := item.get("size_bytes")), int)
        ),
    }
    _write_json(target / "model-provenance.json", manifest)
    return verify_model(profile_path, repo_root)


def verify_model(profile_path: Path, repo_root: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    target = _model_path(repo_root, profile)
    provenance_path = target / "model-provenance.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MLXPipelineError(f"provenance modello non leggibile: {exc}") from exc
    if provenance.get("revision") != profile["model"]["revision"]:
        raise MLXPipelineError("la revisione locale del modello non coincide col profilo")
    problems: list[str] = []
    for entry in provenance.get("files", []):
        path = target / str(entry["path"])
        if not path.is_file():
            problems.append(f"file mancante: {entry['path']}")
            continue
        if path.stat().st_size != int(entry["size_bytes"]):
            problems.append(f"dimensione cambiata: {entry['path']}")
            continue
        if sha256_file(path) != entry["sha256"]:
            problems.append(f"checksum cambiato: {entry['path']}")
    weight_path = target / str(profile["model"]["expected_weight_file"])
    if not weight_path.is_file():
        problems.append(f"file pesi atteso mancante: {weight_path.name}")
    elif weight_path.stat().st_size != int(profile["model"]["expected_weight_bytes"]):
        problems.append(f"dimensione pesi inattesa: {weight_path.name}")
    elif sha256_file(weight_path) != profile["model"]["expected_weight_sha256"]:
        problems.append(f"checksum pesi inatteso: {weight_path.name}")
    result = {
        "path": str(target),
        "repository": provenance.get("repository"),
        "revision": provenance.get("revision"),
        "files": len(provenance.get("files", [])),
        "total_verified_bytes": provenance.get("total_verified_bytes"),
        "provenance_sha256": sha256_file(provenance_path),
        "problems": problems,
        "valid": not problems,
    }
    if problems:
        raise MLXPipelineError("verifica modello fallita: " + "; ".join(problems))
    return result


def _stream_command(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    environment: Mapping[str, str] | None = None,
) -> CommandResult:
    env = os.environ.copy()
    env.update(environment or {})
    started = time.monotonic()
    output_lines: list[str] = []
    peak_memory: float | None = None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{utc_now()}] command: {json.dumps(command)}\n")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(line)
            log.write(line)
            log.flush()
            match = _PEAK_MEMORY.search(line)
            if match:
                value = float(match.group(1))
                peak_memory = value if peak_memory is None else max(peak_memory, value)
        returncode = process.wait()
    result = CommandResult(
        command=tuple(command),
        returncode=returncode,
        output="".join(output_lines),
        elapsed_seconds=time.monotonic() - started,
        peak_memory_gb=peak_memory,
    )
    if returncode:
        tail = "".join(output_lines[-20:]).strip()
        raise MLXPipelineError(f"comando MLX fallito ({returncode}): {tail}")
    return result


def _jsonl_profile(path: Path) -> dict[str, Any]:
    record_ids: list[str] = []
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MLXPipelineError(f"JSONL non valido {path}:{line_number}: {exc}") from exc
            messages = value.get("messages") if isinstance(value, dict) else None
            if not isinstance(messages, list) or not messages:
                raise MLXPipelineError(f"record senza messages in {path}:{line_number}")
            record_id = value.get("record_id") if isinstance(value, dict) else None
            if not isinstance(record_id, str) or not record_id.strip():
                raise MLXPipelineError(f"record_id assente in {path}:{line_number}")
            record_ids.append(record_id)
            records.append(value)
    duplicates = sorted(record_id for record_id, count in Counter(record_ids).items() if count > 1)
    if duplicates:
        raise MLXPipelineError(f"record_id duplicati in {path}: {duplicates}")
    return {
        "count": len(record_ids),
        "record_ids": tuple(record_ids),
        "records": tuple(records),
    }


def _jsonl_count(path: Path) -> int:
    return int(_jsonl_profile(path)["count"])


def _snapshot_identity(manifest: Mapping[str, Any]) -> tuple[str, str]:
    identity_payload = {
        str(key): value
        for key, value in manifest.items()
        if key not in {"created_at", "snapshot_id", "snapshot_sha256"}
    }
    digest = sha256_json(identity_payload)
    prefix = "mlx-smoke-" if manifest.get("runtime_smoke_only") is True else "mlx-dataset-"
    return digest, prefix + digest[:20]


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MLXPipelineError(f"{label} non leggibile: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MLXPipelineError(f"{label} deve essere un oggetto JSON: {path}")
    return value


def _verify_snapshot_files(
    data_dir: Path,
    manifest: Mapping[str, Any],
    *,
    required_files: frozenset[str],
) -> tuple[dict[str, str], dict[str, int]]:
    entries = manifest.get("files")
    if not isinstance(entries, dict):
        raise MLXPipelineError("files deve essere un mapping nel manifest snapshot")
    missing = sorted(required_files - entries.keys())
    if missing:
        raise MLXPipelineError(f"file obbligatori assenti dal manifest snapshot: {missing}")
    if "snapshot-manifest.json" in entries:
        raise MLXPipelineError("snapshot-manifest.json non puo auto-includersi in files")

    root = data_dir.resolve()
    hashes: dict[str, str] = {}
    sizes: dict[str, int] = {}
    if any(not isinstance(filename, str) for filename in entries):
        raise MLXPipelineError("files contiene un nome non testuale")
    for filename, entry in sorted(entries.items()):
        if (
            PurePosixPath(filename).parts != (filename,)
            or filename in {"", ".", ".."}
            or "\\" in filename
        ):
            raise MLXPipelineError(f"path non sicuro nel manifest snapshot: {filename!r}")
        if not isinstance(entry, dict):
            raise MLXPipelineError(f"entry files non valida per {filename}")
        expected_hash = entry.get("sha256")
        expected_size = entry.get("size_bytes")
        if not isinstance(expected_hash, str) or _SHA256.fullmatch(expected_hash) is None:
            raise MLXPipelineError(f"sha256 non valido nel manifest per {filename}")
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise MLXPipelineError(f"size_bytes non valido nel manifest per {filename}")
        path = data_dir / filename
        if path.is_symlink():
            raise MLXPipelineError(f"file snapshot symlink non ammesso: {filename}")
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not path.is_file():
            raise MLXPipelineError(f"file snapshot mancante o esterno: {filename}")
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise MLXPipelineError(
                f"dimensione file snapshot non coerente per {filename}: "
                f"attesa {expected_size}, trovata {actual_size}"
            )
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise MLXPipelineError(f"checksum file snapshot non coerente per {filename}")
        hashes[filename] = actual_hash
        sizes[filename] = actual_size
    return hashes, sizes


def _verify_snapshot_counts(
    data_dir: Path,
    manifest: Mapping[str, Any],
    *,
    smoke_test: bool,
    require_nonempty_training_splits: bool,
) -> tuple[
    dict[str, int],
    dict[str, tuple[str, ...]],
    dict[str, tuple[dict[str, Any], ...]],
]:
    expected_split_names = ("train", "valid", "test") if smoke_test else tuple(_SPLIT_FILES)
    manifest_counts = manifest.get("counts")
    if not isinstance(manifest_counts, dict) or set(manifest_counts) != set(expected_split_names):
        raise MLXPipelineError(
            f"counts snapshot deve contenere esattamente {sorted(expected_split_names)}"
        )
    counts: dict[str, int] = {}
    record_ids: dict[str, tuple[str, ...]] = {}
    split_records: dict[str, tuple[dict[str, Any], ...]] = {}
    seen: dict[str, str] = {}
    for split in expected_split_names:
        path = data_dir / _SPLIT_FILES[split]
        profile = _jsonl_profile(path)
        actual_count = int(profile["count"])
        declared_count = manifest_counts.get(split)
        if isinstance(declared_count, bool) or not isinstance(declared_count, int):
            raise MLXPipelineError(f"conteggio snapshot non valido per {split}")
        if declared_count != actual_count:
            raise MLXPipelineError(
                f"conteggio snapshot non coerente per {split}: "
                f"atteso {declared_count}, trovato {actual_count}"
            )
        if (
            require_nonempty_training_splits
            and split in {"train", "valid", "test"}
            and actual_count < 1
        ):
            raise MLXPipelineError(f"split MLX vuoto: {path}")
        ids = tuple(str(value) for value in profile["record_ids"])
        for record_id in ids:
            previous = seen.setdefault(record_id, split)
            if previous != split:
                raise MLXPipelineError(
                    f"record_id {record_id!r} attraversa gli split {previous} e {split}"
                )
        counts[split] = actual_count
        record_ids[split] = ids
        split_records[split] = tuple(profile["records"])
    if smoke_test:
        counts["external"] = 0
        record_ids["external"] = ()
        split_records["external"] = ()
    return counts, record_ids, split_records


def _load_prepared_records(path: Path) -> tuple[PreparedRecord, ...]:
    records: list[PreparedRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        raise MLXPipelineError(f"prepared records non leggibili: {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(PreparedRecord.model_validate_json(line))
        except ValueError as exc:
            raise MLXPipelineError(
                f"prepared record non valido {path}:{line_number}: {exc}"
            ) from exc
    identifiers = [record.record.record_id for record in records]
    duplicates = sorted(record_id for record_id, count in Counter(identifiers).items() if count > 1)
    if duplicates:
        raise MLXPipelineError(f"record_id duplicati nei prepared records: {duplicates}")
    return tuple(records)


def _source_manifest_split_ids(source: DatasetManifest) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {name: [] for name in _SPLIT_FILES}
    for record in source.records:
        split_name = _SOURCE_SPLIT_NAMES[record.split.value]
        grouped[split_name].append(record.record_id)
    return {name: tuple(sorted(values)) for name, values in grouped.items()}


def _validate_real_snapshot_source(
    data_dir: Path,
    manifest: Mapping[str, Any],
    *,
    file_hashes: Mapping[str, str],
    counts: Mapping[str, int],
    split_record_ids: Mapping[str, tuple[str, ...]],
    split_records: Mapping[str, tuple[dict[str, Any], ...]],
) -> tuple[DatasetManifest, Path, str]:
    source_identity = manifest.get("source_manifest")
    if not isinstance(source_identity, dict):
        raise MLXPipelineError("identita source_manifest assente dal manifest snapshot")
    source_filename = source_identity.get("path")
    if source_filename != "dataset-manifest.source.json":
        raise MLXPipelineError("source_manifest.path inatteso")
    source_path = data_dir / source_filename
    source_raw = _load_json_object(source_path, label="manifest sorgente")
    if not source_raw.get("dataset_id") or not source_raw.get("records_checksum"):
        raise MLXPipelineError("manifest sorgente privo di identita content-addressed esplicita")
    try:
        source = DatasetManifest.model_validate(source_raw)
    except ValueError as exc:
        raise MLXPipelineError(f"manifest sorgente non valido: {exc}") from exc
    source_hash = file_hashes[source_filename]
    checks = {
        "sha256": source_hash,
        "dataset_id": source.dataset_id,
        "manifest_checksum": source.manifest_checksum(),
        "records_checksum": source.records_checksum,
        "prepared_records_sha256": file_hashes["prepared-records.jsonl"],
        "preparation_report_sha256": file_hashes["preparation-report.json"],
    }
    for key, actual in checks.items():
        if source_identity.get(key) != actual:
            raise MLXPipelineError(f"source_manifest.{key} non coincide col manifest sorgente")
    if manifest.get("dataset_id") != source.dataset_id:
        raise MLXPipelineError("dataset_id snapshot non coincide col manifest sorgente")
    if manifest.get("source_records_checksum") != source.records_checksum:
        raise MLXPipelineError("source_records_checksum non coincide col manifest sorgente")

    source_ids = _source_manifest_split_ids(source)
    for split in _SPLIT_FILES:
        actual_ids = tuple(sorted(split_record_ids[split]))
        if actual_ids != source_ids[split]:
            raise MLXPipelineError(
                f"record_id dello split {split} non coincidono col manifest sorgente"
            )
        if counts[split] != len(source_ids[split]):
            raise MLXPipelineError(f"conteggio {split} non coincide col manifest sorgente")

    report_path = data_dir / "preparation-report.json"
    report_raw = _load_json_object(report_path, label="report preparazione")
    try:
        report = PreparationReport.model_validate(report_raw)
    except ValueError as exc:
        raise MLXPipelineError(f"report preparazione non valido: {exc}") from exc
    if report.dataset_records_checksum != source.records_checksum:
        raise MLXPipelineError("checksum record non coincide tra report e manifest sorgente")
    if report.kept_count != len(source.records):
        raise MLXPipelineError("kept_count non coincide col manifest sorgente")
    expected_report_checksum = content_checksum(report.model_dump(mode="json"))
    if source.report_checksum != expected_report_checksum:
        raise MLXPipelineError("report_checksum non coincide col manifest sorgente")
    decision_payload = [
        decision.model_dump(mode="json")
        for decision in sorted(
            report.duplicate_decisions,
            key=lambda item: (
                item.kind.value,
                item.duplicate_record_id,
                item.canonical_record_id,
            ),
        )
    ]
    if source.decisions_checksum != content_checksum(decision_payload):
        raise MLXPipelineError("decisions_checksum non coincide col report preparazione")

    expected_report_counts = {
        "train": counts["train"],
        "validation": counts["valid"],
        "test": counts["test"],
        "external": counts["external"],
    }
    if report.split_counts != expected_report_counts:
        raise MLXPipelineError("split_counts del report non coincidono coi file snapshot")

    prepared_records = _load_prepared_records(data_dir / "prepared-records.jsonl")
    try:
        PreparedDataset(records=prepared_records, manifest=source, report=report)
    except ValueError as exc:
        raise MLXPipelineError(
            f"prepared records non coerenti col manifest sorgente: {exc}"
        ) from exc
    source_by_id = {record.record_id: record for record in source.records}
    for prepared in prepared_records:
        record_id = prepared.record.record_id
        if (
            content_checksum(prepared.model_dump(mode="json"))
            != source_by_id[record_id].record_checksum
        ):
            raise MLXPipelineError(
                f"record_checksum del prepared record {record_id} non coincide col manifest sorgente"
            )

    # Import locale per evitare il ciclo mlx_dataset -> mlx_runtime al module load.
    from ntruth.training.mlx_dataset import _chat_record

    expected_chat: dict[str, list[dict[str, Any]]] = {name: [] for name in _SPLIT_FILES}
    for prepared in prepared_records:
        split_name = _SOURCE_SPLIT_NAMES[prepared.split.value]
        expected_chat[split_name].append(_chat_record(prepared))
    for split in _SPLIT_FILES:
        expected_rows = sorted(expected_chat[split], key=lambda row: str(row["record_id"]))
        actual_rows = sorted(split_records[split], key=lambda row: str(row["record_id"]))
        if actual_rows != expected_rows:
            raise MLXPipelineError(
                f"contenuto chat dello split {split} non coincide coi prepared records"
            )

    derived_approved = bool(source.records) and all(
        record.training_eligible for record in source.records
    )
    if manifest.get("training_approved") is not derived_approved:
        raise MLXPipelineError(
            "training_approved non coincide con le evidenze del manifest sorgente"
        )
    derived_synthetic = bool(source.records) and all(record.synthetic for record in source.records)
    if manifest.get("synthetic_only") is not derived_synthetic:
        raise MLXPipelineError("synthetic_only non coincide col manifest sorgente")
    if manifest.get("leakage_check_passed") is not True:
        raise MLXPipelineError("leakage_check_passed non coincide col manifest sorgente validato")
    return source, source_path, source_hash


def _validate_runtime_smoke_manifest(
    manifest: Mapping[str, Any],
    split_record_ids: Mapping[str, tuple[str, ...]],
    split_records: Mapping[str, tuple[dict[str, Any], ...]],
    data_dir: Path,
) -> None:
    from ntruth.training.mlx_dataset import runtime_smoke_jsonl_bytes, runtime_smoke_split_rows

    exact_flags = {
        "dataset_id": "runtime-smoke-only",
        "training_approved": False,
        "leakage_check_passed": False,
        "synthetic_only": True,
        "runtime_smoke_only": True,
        "scientific_metrics_allowed": False,
    }
    for key, expected in exact_flags.items():
        if manifest.get(key) != expected or type(manifest.get(key)) is not type(expected):
            raise MLXPipelineError(f"flag smoke non valido: {key}")
    if manifest.get("source_manifest") is not None:
        raise MLXPipelineError("lo smoke runtime non puo dichiarare un manifest sorgente reale")
    expected_ids = {
        "train": tuple(f"runtime-smoke-{index:02d}" for index in range(4)),
        "valid": tuple(f"runtime-smoke-{index:02d}" for index in range(4, 6)),
        "test": tuple(f"runtime-smoke-{index:02d}" for index in range(6, 8)),
        "external": (),
    }
    if dict(split_record_ids) != expected_ids:
        raise MLXPipelineError("record_id smoke non coincidono con la fixture runtime isolata")
    expected_rows = runtime_smoke_split_rows()
    for split in ("train", "valid", "test"):
        if list(split_records[split]) != expected_rows[split]:
            raise MLXPipelineError(
                f"contenuto {split} non coincide con la fixture runtime canonica"
            )
        actual_bytes = _read_regular_file_bytes(
            data_dir / f"{split}.jsonl",
            label=f"fixture runtime {split}",
        )
        if actual_bytes != runtime_smoke_jsonl_bytes(split):
            raise MLXPipelineError(f"byte {split} non coincidono con la fixture runtime canonica")


def validate_snapshot_integrity(
    data_dir: Path,
    *,
    smoke_test: bool = False,
    require_nonempty_training_splits: bool = True,
) -> dict[str, Any]:
    """Verifica identita, file e manifest sorgente di uno snapshot MLX.

    La funzione non autorizza il training scientifico: prova che lo snapshot sia
    content-addressed e coerente. ``validate_mlx_dataset`` applica poi il gate di
    autorizzazione. Lo smoke usa un contratto sintetico separato e non puo essere
    accettato implicitamente dal percorso reale.
    """

    root = data_dir.resolve()
    manifest_path = root / "snapshot-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise MLXPipelineError("snapshot-manifest.json assente o symlink non ammesso")
    manifest = _load_json_object(manifest_path, label="manifest snapshot")
    if manifest.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise MLXPipelineError(
            f"schema snapshot atteso {SNAPSHOT_SCHEMA_VERSION}, "
            f"ricevuto {manifest.get('schema_version')}"
        )
    runtime_smoke_only = manifest.get("runtime_smoke_only") is True
    if runtime_smoke_only and not smoke_test:
        raise MLXPipelineError(
            "training bloccato: snapshot runtime smoke richiede il gate esplicito smoke_test"
        )
    if smoke_test and not runtime_smoke_only:
        raise MLXPipelineError("il gate smoke rifiuta snapshot non runtime_smoke_only")

    expected_hash, expected_id = _snapshot_identity(manifest)
    if manifest.get("snapshot_sha256") != expected_hash:
        raise MLXPipelineError("snapshot_sha256 non coerente col contenuto del manifest")
    if manifest.get("snapshot_id") != expected_id:
        raise MLXPipelineError("snapshot_id non coerente col contenuto del manifest")

    required_files = _SMOKE_SNAPSHOT_FILES if smoke_test else _REAL_SNAPSHOT_FILES
    file_hashes, file_sizes = _verify_snapshot_files(
        root,
        manifest,
        required_files=required_files,
    )
    counts, split_record_ids, split_records = _verify_snapshot_counts(
        root,
        manifest,
        smoke_test=smoke_test,
        require_nonempty_training_splits=require_nonempty_training_splits,
    )

    source: DatasetManifest | None = None
    source_path: Path | None = None
    source_hash: str | None = None
    if smoke_test:
        _validate_runtime_smoke_manifest(
            manifest,
            split_record_ids,
            split_records,
            root,
        )
    else:
        source, source_path, source_hash = _validate_real_snapshot_source(
            root,
            manifest,
            file_hashes=file_hashes,
            counts=counts,
            split_record_ids=split_record_ids,
            split_records=split_records,
        )

    return {
        "path": str(root),
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "snapshot_id": expected_id,
        "snapshot_sha256": expected_hash,
        "counts": counts,
        "split_record_ids": split_record_ids,
        "file_hashes": file_hashes,
        "file_sizes": file_sizes,
        "source_manifest": source.model_dump(mode="json") if source is not None else None,
        "source_manifest_path": str(source_path) if source_path is not None else None,
        "source_manifest_sha256": source_hash,
        "runtime_smoke_only": runtime_smoke_only,
    }


def validate_mlx_dataset(data_dir: Path, *, smoke_test: bool = False) -> dict[str, Any]:
    """Valida file MLX e gate di governance prima di qualsiasi training."""

    if not smoke_test:
        from ntruth.training.blind_evaluation import validate_training_view

        if (data_dir / "snapshot-manifest.json").exists():
            raise MLXPipelineError(
                "training bloccato: snapshot misto di custody; creare e usare una training view"
            )
        return validate_training_view(data_dir)
    integrity = validate_snapshot_integrity(data_dir, smoke_test=True)
    manifest = integrity["manifest"]
    approved = manifest["training_approved"] is True
    leakage_free = manifest["leakage_check_passed"] is True
    return {
        "path": integrity["path"],
        "counts": {split: integrity["counts"][split] for split in ("train", "valid", "test")},
        "manifest": integrity["manifest_path"],
        "manifest_data": manifest,
        "manifest_sha256": integrity["manifest_sha256"],
        "snapshot_id": integrity["snapshot_id"],
        "snapshot_sha256": integrity["snapshot_sha256"],
        "file_hashes": integrity["file_hashes"],
        "file_sizes": integrity["file_sizes"],
        "source_manifest_sha256": integrity["source_manifest_sha256"],
        "training_approved": approved,
        "leakage_check_passed": leakage_free,
        "smoke_test": smoke_test,
    }


def _consume_isolated_training_payloads(
    data_root: Path,
    dataset: Mapping[str, Any],
    *,
    profile: Mapping[str, Any],
    authorization: Mapping[str, Any] | None,
    smoke_test: bool,
) -> dict[str, Any]:
    """Validate bytes, materialize unlinked FDs, consume only those FDs."""

    from ntruth.training.fd_isolation import (
        FdIsolationError,
        bind_run_state,
        close_isolated,
        consume_isolated_bytes,
        fd_isolation_contract_holds,
        isolate_verified_file,
    )

    if not fd_isolation_contract_holds():
        raise MLXPipelineError(FD_ISOLATION_BLOCKER)

    hashes = dataset.get("file_hashes")
    if not isinstance(hashes, dict) or not hashes:
        if smoke_test:
            return {
                "consumed": {},
                "run_state": bind_run_state(
                    dataset_sha256=hashlib.sha256(b"smoke-dataset-absent").hexdigest(),
                    authorization_sha256=hashlib.sha256(
                        b"runtime-smoke-no-authorization"
                    ).hexdigest(),
                    model_sha256=hashlib.sha256(b"model-absent").hexdigest(),
                    tokenizer_sha256=hashlib.sha256(b"tokenizer-absent").hexdigest(),
                    checkpoint_sha256=hashlib.sha256(b"checkpoint-absent").hexdigest(),
                    consumed_labels=(),
                ),
            }
        raise MLXPipelineError("dataset validato privo di checksum per l'isolamento FD")
    isolated = []
    consumed_hashes: dict[str, str] = {}
    try:
        for filename, expected in hashes.items():
            if not isinstance(filename, str) or not isinstance(expected, str):
                raise MLXPipelineError(f"checksum dataset non valido: {filename}")
            handle = isolate_verified_file(
                data_root / filename,
                label=filename,
                expected_sha256=expected,
            )
            isolated.append(handle)
            payload = consume_isolated_bytes(handle)
            consumed_hashes[filename] = hashlib.sha256(payload).hexdigest()
            if consumed_hashes[filename] != expected:
                raise MLXPipelineError(f"consume FD non coincide con la validazione: {filename}")
    except FdIsolationError as exc:
        raise MLXPipelineError(str(exc)) from exc
    finally:
        for handle in isolated:
            close_isolated(handle)

    dataset_hash = dataset.get("snapshot_sha256") or dataset.get("training_view_sha256")
    if not isinstance(dataset_hash, str):
        raise MLXPipelineError("identita dataset assente dal consume FD")
    authorization_hash = (
        authorization.get("artifact_sha256")
        if isinstance(authorization, Mapping)
        else None
    )
    if not isinstance(authorization_hash, str):
        authorization_hash = hashlib.sha256(
            b"runtime-smoke-no-authorization" if smoke_test else b"authorization-absent"
        ).hexdigest()
    model = profile.get("model") if isinstance(profile.get("model"), dict) else {}
    model_hash = model.get("expected_weight_sha256")
    if not isinstance(model_hash, str) or len(model_hash) != 64:
        model_hash = hashlib.sha256(b"model-absent").hexdigest()
    tokenizer_hash = hashlib.sha256(
        f"{model.get('repository', '')}@{model.get('revision', '')}".encode()
    ).hexdigest()
    checkpoint_hash = hashlib.sha256(b"checkpoint-absent").hexdigest()
    state = bind_run_state(
        dataset_sha256=dataset_hash,
        authorization_sha256=authorization_hash,
        model_sha256=model_hash,
        tokenizer_sha256=tokenizer_hash,
        checkpoint_sha256=checkpoint_hash,
        consumed_labels=tuple(sorted(consumed_hashes)),
    )
    return {"consumed": consumed_hashes, "run_state": state}


def run_training(
    profile_path: Path,
    repo_root: Path,
    data_dir: Path,
    run_dir: Path,
    *,
    seed: int,
    smoke_test: bool = False,
    resume: bool = False,
    training_authorization: Path | None = None,
) -> dict[str, Any]:
    """Validate the intended run, then fail closed until MLX has an FD-only runner."""

    authorization: dict[str, Any] | None = None
    if not smoke_test:
        if training_authorization is None:
            raise MLXPipelineError(
                "autorizzazione training obbligatoria per il training sostanziale"
            )
        authorization = _load_training_authorization(training_authorization)

    data_root = data_dir.resolve()
    run_root = run_dir.resolve()
    if not smoke_test and (
        run_root.is_relative_to(data_root) or data_root.is_relative_to(run_root)
    ):
        raise MLXPipelineError(
            "directory run e training view devono essere root fisicamente separate"
        )

    state_path = run_dir / "run-state.json"
    resumed_state: dict[str, Any] | None = None
    if resume:
        resumed_state = _load_resume_state(state_path)
        _assert_resume_authorization(
            resumed_state,
            authorization,
            smoke_test=smoke_test,
        )
        from ntruth.training.fd_isolation import fd_isolation_contract_holds

        if not fd_isolation_contract_holds():
            raise MLXPipelineError(f"{FD_ISOLATION_BLOCKER}; resume non supportato")
        raise MLXPipelineError(f"{SCIENTIFIC_EXECUTION_CLOSED_DETAIL}; resume non supportato")

    dataset = validate_mlx_dataset(data_root, smoke_test=smoke_test)
    profile, profile_sha256 = load_profile_artifact(profile_path)
    training = profile["training"]
    allowed_seeds = tuple(int(item) for item in training["seeds"])
    if seed not in allowed_seeds and not smoke_test:
        raise MLXPipelineError(f"seed non preregistrato: {seed}; ammessi {allowed_seeds}")
    if not smoke_test:
        assert authorization is not None
        _assert_training_authorization_binding(
            authorization,
            dataset=dataset,
            profile=profile,
            profile_sha256=profile_sha256,
            source_snapshot_sha256=str(_source_snapshot(repo_root)["sha256"]),
            seed=seed,
        )
    _consume_isolated_training_payloads(
        data_root,
        dataset,
        profile=profile,
        authorization=authorization,
        smoke_test=smoke_test,
    )
    raise MLXPipelineError(SCIENTIFIC_EXECUTION_CLOSED_DETAIL)


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MLXPipelineError(f"JSONL non valido {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise MLXPipelineError(f"record non-oggetto in {path}:{line_number}")
            yield value
