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
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ntruth.schemas.core import content_checksum
from ntruth.training.records import (
    DatasetManifest,
    PreparationReport,
    PreparedDataset,
    PreparedRecord,
)

PROFILE_SCHEMA_VERSION = "1.0.0"
PROVENANCE_SCHEMA_VERSION = "1.0.0"
RUN_SCHEMA_VERSION = "2.0.0"
SNAPSHOT_SCHEMA_VERSION = "2.0.0"
_TEST_LOSS = re.compile(r"Test loss\s+([0-9]+(?:\.[0-9]+)?)")
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
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
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
    return profile


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
    result["ready_to_train"] = (
        result["ready_to_download"] and runtime_version == expected_runtime and model_exists
    )
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
        lines = path.read_text(encoding="utf-8").splitlines()
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
) -> None:
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
        _validate_runtime_smoke_manifest(manifest, split_record_ids)
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

    integrity = validate_snapshot_integrity(data_dir, smoke_test=smoke_test)
    manifest = integrity["manifest"]
    approved = manifest["training_approved"] is True
    leakage_free = manifest["leakage_check_passed"] is True
    if not smoke_test and (not approved or not leakage_free):
        raise MLXPipelineError(
            "training bloccato: servono training_approved=true e leakage_check_passed=true"
        )
    return {
        "path": integrity["path"],
        "counts": {split: integrity["counts"][split] for split in ("train", "valid", "test")},
        "manifest": integrity["manifest_path"],
        "manifest_data": manifest,
        "manifest_sha256": integrity["manifest_sha256"],
        "snapshot_id": integrity["snapshot_id"],
        "snapshot_sha256": integrity["snapshot_sha256"],
        "file_hashes": integrity["file_hashes"],
        "source_manifest_sha256": integrity["source_manifest_sha256"],
        "training_approved": approved,
        "leakage_check_passed": leakage_free,
        "smoke_test": smoke_test,
    }


def _copy_validation_as_test(data_dir: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(data_dir / "valid.jsonl", target / "test.jsonl")


def _mlx_command(config_path: Path) -> list[str]:
    return [sys.executable, "-m", "mlx_lm", "lora", "--config", str(config_path)]


def run_training(
    profile_path: Path,
    repo_root: Path,
    data_dir: Path,
    run_dir: Path,
    *,
    seed: int,
    smoke_test: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Esegue QLoRA a fasi con validation, checkpoint e early stopping reale.

    MLX-LM 0.31.3 non espone early stopping nativo. Ogni fase riprende
    deterministicamente l'adapter precedente, viene valutata sul validation set e
    il controller interrompe dopo ``patience`` fasi senza miglioramento.
    """

    profile = load_profile(profile_path)
    machine = doctor(profile_path, repo_root)
    if not machine["ready_to_train"]:
        raise MLXPipelineError(f"training bloccato dal doctor: {machine['checks']}")
    model_check = verify_model(profile_path, repo_root)
    dataset = validate_mlx_dataset(data_dir, smoke_test=smoke_test)
    environment_record = runtime_environment(repo_root)
    model_path = _model_path(repo_root, profile)
    training = profile["training"]
    allowed_seeds = tuple(int(item) for item in training["seeds"])
    if seed not in allowed_seeds and not smoke_test:
        raise MLXPipelineError(f"seed non preregistrato: {seed}; ammessi {allowed_seeds}")

    state_path = run_dir / "run-state.json"
    if run_dir.exists() and any(run_dir.iterdir()) and not resume:
        raise MLXPipelineError("run directory non vuota; usare --resume o una nuova directory")
    run_dir.mkdir(parents=True, exist_ok=True)
    validation_dir = run_dir / "_validation-as-test"
    _copy_validation_as_test(data_dir, validation_dir)

    maximum_phases = 1 if smoke_test else int(training["maximum_phases"])
    iterations_per_phase = (
        min(2, int(training["iterations_per_phase"]))
        if smoke_test
        else int(training["iterations_per_phase"])
    )
    patience = int(training["early_stopping_patience"])
    min_delta = float(training["early_stopping_min_delta"])
    state: dict[str, Any]
    if resume:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MLXPipelineError(f"stato run non riprendibile: {exc}") from exc
        if state.get("schema_version") != RUN_SCHEMA_VERSION:
            raise MLXPipelineError("schema run cambiato: impossibile riprendere il run")
        if state.get("profile_sha256") != sha256_file(profile_path):
            raise MLXPipelineError("profilo cambiato: impossibile riprendere il run")
        if state.get("dataset_snapshot_sha256") != dataset["snapshot_sha256"]:
            raise MLXPipelineError("snapshot dati cambiato: impossibile riprendere il run")
        if state.get("dataset_snapshot_id") != dataset["snapshot_id"]:
            raise MLXPipelineError("identita snapshot cambiata: impossibile riprendere il run")
        if state.get("dataset_manifest_sha256") != dataset["manifest_sha256"]:
            raise MLXPipelineError("manifest snapshot cambiato: impossibile riprendere il run")
        previous_environment = state.get("environment")
        if not isinstance(previous_environment, dict):
            raise MLXPipelineError("record ambiente assente: impossibile riprendere il run")
        for key in ("uv_lock_sha256", "source_snapshot_sha256"):
            if previous_environment.get(key) != environment_record.get(key):
                raise MLXPipelineError(
                    f"ambiente di esecuzione cambiato ({key}): impossibile riprendere il run"
                )
    else:
        state = {
            "schema_version": RUN_SCHEMA_VERSION,
            "status": "running",
            "started_at": utc_now(),
            "profile_sha256": sha256_file(profile_path),
            "dataset_snapshot_sha256": dataset["snapshot_sha256"],
            "dataset_snapshot_id": dataset["snapshot_id"],
            "dataset_manifest_sha256": dataset["manifest_sha256"],
            "model_provenance_sha256": model_check["provenance_sha256"],
            "environment": environment_record,
            "seed": seed,
            "smoke_test": smoke_test,
            "last_completed_phase": 0,
            "best_phase": None,
            "best_validation_loss": None,
            "phases_without_improvement": 0,
            "phases": [],
        }
        _write_json(state_path, state)

    offline_environment = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TOKENIZERS_PARALLELISM": "true",
    }
    start_phase = int(state["last_completed_phase"]) + 1
    best_loss = state.get("best_validation_loss")
    stale = int(state.get("phases_without_improvement", 0))
    latest_adapter: Path | None = None
    if state["last_completed_phase"]:
        latest_adapter = (
            run_dir
            / "checkpoints"
            / f"phase-{int(state['last_completed_phase']):04d}"
            / "adapters.safetensors"
        )
        if not latest_adapter.is_file():
            raise MLXPipelineError("checkpoint di ripresa mancante")

    for phase in range(start_phase, maximum_phases + 1):
        checkpoint_dir = run_dir / "checkpoints" / f"phase-{phase:04d}"
        phase_config = {
            "model": str(model_path),
            "train": True,
            "test": False,
            "fine_tune_type": training["fine_tune_type"],
            "optimizer": training["optimizer"],
            "data": str(data_dir.resolve()),
            "seed": seed + phase - 1,
            "num_layers": int(training["num_layers"]),
            "batch_size": int(training["batch_size"]),
            "iters": iterations_per_phase,
            "val_batches": int(training["validation_batches"]),
            "learning_rate": float(training["learning_rate"]),
            "steps_per_report": 1 if smoke_test else min(10, iterations_per_phase),
            "steps_per_eval": iterations_per_phase,
            "grad_accumulation_steps": (
                1 if smoke_test else int(training["gradient_accumulation_steps"])
            ),
            "resume_adapter_file": str(latest_adapter) if latest_adapter else None,
            "adapter_path": str(checkpoint_dir),
            "save_every": iterations_per_phase,
            "max_seq_length": int(profile["data"]["max_sequence_length"]),
            "grad_checkpoint": bool(training["gradient_checkpointing"]),
            "mask_prompt": bool(training["mask_prompt"]),
            "report_to": None,
            "lora_parameters": training["lora_parameters"],
        }
        config_path = run_dir / "configs" / f"phase-{phase:04d}.json"
        _write_json(config_path, phase_config)
        train_result = _stream_command(
            _mlx_command(config_path),
            cwd=repo_root,
            log_path=run_dir / "train.log",
            environment=offline_environment,
        )
        latest_adapter = checkpoint_dir / "adapters.safetensors"
        if not latest_adapter.is_file():
            raise MLXPipelineError("MLX-LM non ha prodotto adapters.safetensors")

        eval_config = {
            "model": str(model_path),
            "train": False,
            "test": True,
            "data": str(validation_dir),
            "adapter_path": str(checkpoint_dir),
            "batch_size": 1,
            "test_batches": -1,
            "max_seq_length": int(profile["data"]["max_sequence_length"]),
        }
        eval_path = run_dir / "configs" / f"phase-{phase:04d}-eval.json"
        _write_json(eval_path, eval_config)
        eval_result = _stream_command(
            _mlx_command(eval_path),
            cwd=repo_root,
            log_path=run_dir / "validation.log",
            environment=offline_environment,
        )
        loss_match = _TEST_LOSS.search(eval_result.output)
        if not loss_match:
            raise MLXPipelineError("loss di validazione non trovata nell'output MLX-LM")
        validation_loss = float(loss_match.group(1))
        improved = best_loss is None or validation_loss < float(best_loss) - min_delta
        if improved:
            best_loss = validation_loss
            stale = 0
            best_dir = run_dir / "best"
            best_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(latest_adapter, best_dir / "adapters.safetensors")
            adapter_config = checkpoint_dir / "adapter_config.json"
            if adapter_config.is_file():
                shutil.copyfile(adapter_config, best_dir / "adapter_config.json")
            state["best_phase"] = phase
            state["best_validation_loss"] = validation_loss
        else:
            stale += 1

        phase_record = {
            "phase": phase,
            "iterations": iterations_per_phase,
            "validation_loss": validation_loss,
            "improved": improved,
            "train_elapsed_seconds": train_result.elapsed_seconds,
            "validation_elapsed_seconds": eval_result.elapsed_seconds,
            "peak_memory_gb": train_result.peak_memory_gb,
            "checkpoint": str(checkpoint_dir.relative_to(run_dir)),
        }
        state["phases"].append(phase_record)
        state["last_completed_phase"] = phase
        state["phases_without_improvement"] = stale
        _write_json(state_path, state)

        memory_ceiling = float(training.get("maximum_observed_peak_memory_gib", 18.0))
        if train_result.peak_memory_gb is not None and train_result.peak_memory_gb > memory_ceiling:
            state["status"] = "stopped_memory_ceiling"
            break
        if stale >= patience:
            state["status"] = "early_stopped"
            break
    else:
        state["status"] = "completed_maximum_phases"

    state["completed_at"] = utc_now()
    state["best_validation_loss"] = best_loss
    best_adapter_path = run_dir / "best" / "adapters.safetensors"
    if best_adapter_path.is_file():
        state["best_adapter_sha256"] = sha256_file(best_adapter_path)
    best_adapter_config = run_dir / "best" / "adapter_config.json"
    if best_adapter_config.is_file():
        state["best_adapter_config_sha256"] = sha256_file(best_adapter_config)
    _write_json(state_path, state)

    keep = max(1, int(training["keep_checkpoints"]))
    checkpoint_dirs = sorted((run_dir / "checkpoints").glob("phase-*"))
    for obsolete in checkpoint_dirs[:-keep]:
        shutil.rmtree(obsolete)
    return state


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
