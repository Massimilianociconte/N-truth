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
import tempfile
import time
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import Field, model_validator

from ntruth.governance.lineage import CorpusSplit
from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.training.mlx_fd_entrypoint import FD_ENV, FD_SENTINEL
from ntruth.training.records import (
    DatasetManifest,
    PreparationReport,
    PreparedRecord,
)

PROFILE_SCHEMA_VERSION = "1.0.0"
PROVENANCE_SCHEMA_VERSION = "1.0.0"
RUN_SCHEMA_VERSION = "8.0.0"
SNAPSHOT_SCHEMA_VERSION = "8.0.0"
_TEST_LOSS = re.compile(r"Test loss\s+([0-9]+(?:\.[0-9]+)?)")
_PEAK_MEMORY = re.compile(r"Peak mem(?:ory)?\s+([0-9]+(?:\.[0-9]+)?)\s*GB", re.I)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REAL_SNAPSHOT_FILES = frozenset(
    {
        "train.jsonl",
        "valid.jsonl",
        "dataset-manifest.source.json",
        "preparation-report.json",
    }
)
_SMOKE_SNAPSHOT_FILES = frozenset({"train.jsonl", "valid.jsonl"})
_SPLIT_FILES = {
    "train": "train.jsonl",
    "valid": "valid.jsonl",
}
_SOURCE_SPLIT_NAMES = {
    "TRAIN": "train",
    "VALIDATION": "valid",
}


class MLXPipelineError(RuntimeError):
    """Errore operativo previsto della corsia ML locale."""


class TrainingLineageReviewRequired(MLXPipelineError):
    """Task 6 design/source lineage is absent or not independently verifiable."""


class TrainingDesignLineagePins(FrozenModel):
    """Opaque Task 6 output pins; this boundary assigns no design meaning."""

    schema_version: Literal["8.0.0"] = "8.0.0"
    artifact_type: Literal["TASK6_TRAINING_DESIGN_LINEAGE_PINS"] = (
        "TASK6_TRAINING_DESIGN_LINEAGE_PINS"
    )
    artifact_id: str = ""
    artifact_sha256: str = ""
    planned_design_artifact_id: str
    planned_design_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executed_design_artifact_id: str
    executed_design_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _content_addressed(self) -> TrainingDesignLineagePins:
        if not self.planned_design_artifact_id.strip() or not (
            self.executed_design_artifact_id.strip()
        ):
            raise ValueError("planned/executed design artifact IDs must not be blank")
        identity = self.model_dump(mode="json", exclude={"artifact_id", "artifact_sha256"})
        checksum = content_checksum(identity)
        artifact_id = f"training-design-lineage-{checksum[:20]}"
        if self.artifact_sha256 and self.artifact_sha256 != checksum:
            raise ValueError("training design lineage checksum mismatch")
        if self.artifact_id and self.artifact_id != artifact_id:
            raise ValueError("training design lineage artifact id mismatch")
        object.__setattr__(self, "artifact_sha256", checksum)
        object.__setattr__(self, "artifact_id", artifact_id)
        return self


class TrainingRunLineagePins(FrozenModel):
    training_design_lineage_artifact_id: str
    training_design_lineage_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_design_lineage_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_design_lineage_artifact_path: str
    planned_design_artifact_id: str
    planned_design_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executed_design_artifact_id: str
    executed_design_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protected_source_manifest_id: str
    protected_source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protected_source_manifest_path: str
    protected_source_records_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _references_are_explicit(self) -> TrainingRunLineagePins:
        identifiers = (
            self.training_design_lineage_artifact_id,
            self.training_design_lineage_artifact_path,
            self.planned_design_artifact_id,
            self.executed_design_artifact_id,
            self.protected_source_manifest_id,
            self.protected_source_manifest_path,
        )
        if any(not value.strip() for value in identifiers):
            raise ValueError("training run lineage references must not be blank")
        return self

    def state_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


TRAINING_RUN_LINEAGE_STATE_FIELDS = tuple(TrainingRunLineagePins.model_fields)


def load_training_design_lineage_pins(path: Path) -> TrainingDesignLineagePins:
    path = path.resolve()
    if path.is_symlink() or not path.is_file():
        raise TrainingLineageReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: Task 6 design-lineage artifact is absent or symlinked"
        )
    try:
        return TrainingDesignLineagePins.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TrainingLineageReviewRequired(
            f"SCIENTIFIC_REVIEW_REQUIRED: Task 6 design-lineage artifact invalid: {exc}"
        ) from exc


def resolve_training_lineage_inputs(
    *,
    design_lineage_pins: TrainingDesignLineagePins | None,
    design_lineage_artifact_path: Path | None,
    protected_source_manifest_path: Path | None,
) -> TrainingRunLineagePins:
    if (
        design_lineage_pins is None
        or design_lineage_artifact_path is None
        or protected_source_manifest_path is None
    ):
        raise TrainingLineageReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: Task 6 design pins and protected source "
            "DatasetManifest are mandatory"
        )
    design_path = design_lineage_artifact_path.resolve()
    loaded_design = load_training_design_lineage_pins(design_path)
    if loaded_design != design_lineage_pins:
        raise TrainingLineageReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: in-memory design pins do not match Task 6 artifact"
        )
    source_path = protected_source_manifest_path.resolve()
    if source_path.is_symlink() or not source_path.is_file():
        raise TrainingLineageReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: protected source DatasetManifest is absent or symlinked"
        )
    try:
        source = DatasetManifest.model_validate_json(source_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TrainingLineageReviewRequired(
            f"SCIENTIFIC_REVIEW_REQUIRED: protected source DatasetManifest invalid: {exc}"
        ) from exc
    return TrainingRunLineagePins(
        training_design_lineage_artifact_id=loaded_design.artifact_id,
        training_design_lineage_artifact_sha256=loaded_design.artifact_sha256,
        training_design_lineage_file_sha256=sha256_file(design_path),
        training_design_lineage_artifact_path=str(design_path),
        planned_design_artifact_id=loaded_design.planned_design_artifact_id,
        planned_design_artifact_sha256=loaded_design.planned_design_artifact_sha256,
        executed_design_artifact_id=loaded_design.executed_design_artifact_id,
        executed_design_artifact_sha256=loaded_design.executed_design_artifact_sha256,
        protected_source_manifest_id=source.dataset_id,
        protected_source_manifest_sha256=sha256_file(source_path),
        protected_source_manifest_path=str(source_path),
        protected_source_records_checksum=source.records_checksum,
    )


def reconcile_training_lineage_pins(
    recorded: Mapping[str, Any], expected: TrainingRunLineagePins
) -> None:
    for field_name, expected_value in expected.state_payload().items():
        if recorded.get(field_name) != expected_value:
            raise MLXPipelineError(f"training lineage {field_name} changed: cannot resume the run")


class TrainingRealityGateV8Request(FrozenModel):
    gate_version: Literal["8.0.0"] = "8.0.0"
    purpose: Literal["TRAIN"] = "TRAIN"
    snapshot_id: str
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TrainingRealityGateV8Artifact(FrozenModel):
    """Untrusted Task-5 proposal; never an authorization capability.

    Task 7 owns the authoritative decision contract.  Keeping this DTO allows
    old callers and tests to serialize their proposal without letting Task 5
    mint a grant that production would accept.
    """

    gate_version: Literal["8.0.0"] = "8.0.0"
    purpose: Literal["TRAIN"] = "TRAIN"
    snapshot_id: str
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_attestation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    no_corpus_attestation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized: bool
    issued_by: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_id: str
    trust_state: Literal["UNTRUSTED_TASK5_PROPOSAL"] = "UNTRUSTED_TASK5_PROPOSAL"

    def identity_payload(self) -> dict[str, object]:
        return self.model_dump(
            mode="json",
            exclude={"artifact_sha256", "artifact_id"},
        )

    @model_validator(mode="after")
    def _content_addressed(self) -> TrainingRealityGateV8Artifact:
        if not self.snapshot_id.strip() or not self.issued_by.strip():
            raise ValueError("Reality Gate v8 snapshot_id/issued_by must not be blank")
        expected = content_checksum(self.identity_payload())
        if self.artifact_sha256 != expected:
            raise ValueError("Reality Gate v8 artifact checksum mismatch")
        if self.artifact_id != f"reality-gate-v8-{expected[:20]}":
            raise ValueError("Reality Gate v8 artifact_id mismatch")
        return self


@runtime_checkable
class RealityGateV8Protocol(Protocol):
    def authorize_training(
        self, request: TrainingRealityGateV8Request
    ) -> TrainingRealityGateV8Artifact | Mapping[str, Any]: ...


@dataclass(frozen=True)
class FileRealityGateV8Protocol:
    artifact_path: Path

    def authorize_training(self, _request: TrainingRealityGateV8Request) -> Mapping[str, Any]:
        try:
            payload = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Reality Gate v8 artifact is not readable: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Reality Gate v8 artifact must be a JSON object")
        return payload


def build_training_reality_gate_v8_artifact(
    *,
    snapshot_id: str,
    snapshot_sha256: str,
    privacy_attestation_sha256: str,
    no_corpus_attestation_sha256: str,
    authorized: bool,
    issued_by: str,
) -> TrainingRealityGateV8Artifact:
    """Encode an explicitly untrusted Task-5 proposal.

    The returned object is useful for compatibility and negative tests.  The
    production verifier deliberately rejects it until Task 7 supplies the
    independently reviewed authoritative decision interface.
    """

    payload: dict[str, object] = {
        "gate_version": "8.0.0",
        "purpose": "TRAIN",
        "snapshot_id": snapshot_id,
        "snapshot_sha256": snapshot_sha256,
        "privacy_attestation_sha256": privacy_attestation_sha256,
        "no_corpus_attestation_sha256": no_corpus_attestation_sha256,
        "authorized": authorized,
        "issued_by": issued_by,
        "trust_state": "UNTRUSTED_TASK5_PROPOSAL",
    }
    checksum = content_checksum(payload)
    return TrainingRealityGateV8Artifact.model_validate(
        {
            **payload,
            "artifact_sha256": checksum,
            "artifact_id": f"reality-gate-v8-{checksum[:20]}",
        }
    )


def verify_training_reality_gate_v8(
    gate: RealityGateV8Protocol,
    request: TrainingRealityGateV8Request,
) -> TrainingRealityGateV8Artifact:
    """Fail closed on absent, unparseable, stale, blocked or mismatched decisions."""

    if not isinstance(gate, RealityGateV8Protocol):
        raise MLXPipelineError("Reality Gate v8 protocol missing or invalid")
    try:
        artifact = TrainingRealityGateV8Artifact.model_validate(gate.authorize_training(request))
    except (TypeError, ValueError) as exc:
        raise MLXPipelineError(f"Reality Gate v8 artifact invalid: {exc}") from exc
    if artifact.purpose != "TRAIN":
        raise MLXPipelineError("Reality Gate v8 purpose must be TRAIN")
    if artifact.snapshot_id != request.snapshot_id:
        raise MLXPipelineError("Reality Gate v8 artifact is stale for this snapshot")
    if artifact.snapshot_sha256 != request.snapshot_sha256:
        raise MLXPipelineError("Reality Gate v8 snapshot hash mismatch")
    if not artifact.authorized:
        raise MLXPipelineError("Reality Gate v8 blocked purpose TRAIN")
    raise MLXPipelineError(
        "Reality Gate v8 Task 7 authoritative decision unavailable; SCIENTIFIC_REVIEW_REQUIRED"
    )


class RealityGatePinTuple(FrozenModel):
    """Complete audit tuple that a future authoritative gate must reconcile."""

    artifact_id: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_attestation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    no_corpus_attestation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_artifact(cls, artifact: TrainingRealityGateV8Artifact) -> RealityGatePinTuple:
        return cls(
            artifact_id=artifact.artifact_id,
            artifact_sha256=artifact.artifact_sha256,
            privacy_attestation_sha256=artifact.privacy_attestation_sha256,
            no_corpus_attestation_sha256=artifact.no_corpus_attestation_sha256,
        )


def reconcile_reality_gate_pins(
    recorded: Mapping[str, Any],
    expected: RealityGatePinTuple,
) -> None:
    """Reject a resume state when any independently recorded gate pin drifts."""

    canonical_state_names = {
        "artifact_id": "reality_gate_artifact_id",
        "artifact_sha256": "reality_gate_artifact_sha256",
        "privacy_attestation_sha256": "reality_gate_privacy_attestation_sha256",
        "no_corpus_attestation_sha256": "reality_gate_no_corpus_attestation_sha256",
    }
    present_aliases = sorted(set(canonical_state_names) & set(recorded))
    if present_aliases:
        raise MLXPipelineError(
            f"non-canonical Reality Gate v8 aliases/duplicate pins present: {present_aliases}"
        )
    missing = sorted(set(canonical_state_names.values()) - set(recorded))
    if missing:
        raise MLXPipelineError(f"canonical Reality Gate v8 pins missing: {missing}")
    for field_name, state_name in canonical_state_names.items():
        actual = recorded[state_name]
        if actual != getattr(expected, field_name):
            raise MLXPipelineError(f"Reality Gate v8 {field_name} changed: cannot resume the run")


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
    pass_fds: tuple[int, ...] = (),
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
            pass_fds=pass_fds,
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
    from ntruth.parser_ai.contract import ParserAIInput, ParserCandidateOutput

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
            if (
                not isinstance(messages, list)
                or not messages
                or any(not isinstance(message, dict) for message in messages)
            ):
                raise MLXPipelineError(f"record senza messages in {path}:{line_number}")
            record_id = value.get("record_id") if isinstance(value, dict) else None
            if not isinstance(record_id, str) or not record_id.strip():
                raise MLXPipelineError(f"record_id assente in {path}:{line_number}")
            user_messages = [message for message in messages if message.get("role") == "user"]
            final = messages[-1]
            if (
                not user_messages
                or not isinstance(user_messages[-1].get("content"), str)
                or not isinstance(final, dict)
                or final.get("role") != "assistant"
                or not isinstance(final.get("content"), str)
            ):
                raise MLXPipelineError(f"record candidate incompleto in {path}:{line_number}")
            try:
                ParserAIInput.model_validate_json(user_messages[-1]["content"])
                ParserCandidateOutput.model_validate_json(final["content"])
            except ValueError as exc:
                raise MLXPipelineError(
                    f"record candidate v8 non valido in {path}:{line_number}: {exc}"
                ) from exc
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
    manifest_names = set(entries)
    missing = sorted(required_files - manifest_names)
    unexpected = sorted(manifest_names - required_files)
    if missing or unexpected:
        raise MLXPipelineError(
            f"snapshot schema file set mismatch: missing={missing}, unexpected={unexpected}"
        )
    if "snapshot-manifest.json" in entries:
        raise MLXPipelineError("snapshot-manifest.json non puo auto-includersi in files")

    allowed_physical = set(required_files) | {"snapshot-manifest.json"}
    try:
        physical_entries = tuple(data_dir.iterdir())
    except OSError as exc:
        raise MLXPipelineError(f"directory snapshot non leggibile: {exc}") from exc
    physical_names = {entry.name for entry in physical_entries}
    extras = sorted(physical_names - allowed_physical)
    missing_physical = sorted(allowed_physical - physical_names)
    if extras or missing_physical:
        raise MLXPipelineError(
            "snapshot physical allowlist mismatch: "
            f"unmanifested={extras}, missing={missing_physical}"
        )
    for physical in physical_entries:
        if physical.is_symlink() or not physical.is_file():
            raise MLXPipelineError(
                f"snapshot entry must be a regular non-symlink file: {physical.name}"
            )

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


def read_training_snapshot_envelope(
    data_dir: Path,
    *,
    smoke_test: bool = False,
) -> dict[str, Any]:
    """Read only the content-addressed manifest needed before a gate decision.

    This function intentionally never opens train/valid or source payloads.
    """

    root = data_dir.resolve()
    manifest_path = root / "snapshot-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise MLXPipelineError("snapshot-manifest.json absent or symlink not allowed")
    manifest = _load_json_object(manifest_path, label="snapshot manifest envelope")
    if manifest.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise MLXPipelineError("training snapshot envelope schema mismatch")
    runtime_smoke_only = manifest.get("runtime_smoke_only") is True
    if runtime_smoke_only != smoke_test:
        raise MLXPipelineError("training snapshot envelope smoke purpose mismatch")
    expected_hash, expected_id = _snapshot_identity(manifest)
    if manifest.get("snapshot_sha256") != expected_hash:
        raise MLXPipelineError("training snapshot envelope hash mismatch")
    if manifest.get("snapshot_id") != expected_id:
        raise MLXPipelineError("training snapshot envelope id mismatch")
    return {
        "path": str(root),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "snapshot_id": expected_id,
        "snapshot_sha256": expected_hash,
        "runtime_smoke_only": runtime_smoke_only,
    }


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
    expected_split_names = tuple(_SPLIT_FILES)
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
        if require_nonempty_training_splits and split in {"train", "valid"} and actual_count < 1:
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
        split_name = _SOURCE_SPLIT_NAMES.get(record.split.value)
        if split_name is not None and record.training_eligible:
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
    source_by_id = {record.record_id: record for record in source.records}
    for split in _SPLIT_FILES:
        actual_ids = tuple(sorted(split_record_ids[split]))
        if actual_ids != source_ids[split]:
            raise MLXPipelineError(
                f"record_id dello split {split} non coincidono col manifest sorgente"
            )
        if counts[split] != len(source_ids[split]):
            raise MLXPipelineError(f"conteggio {split} non coincide col manifest sorgente")
        for row in split_records[split]:
            record_id = str(row["record_id"])
            source_record = source_by_id[record_id]
            messages = row["messages"]
            user_messages = [message for message in messages if message.get("role") == "user"]
            try:
                from ntruth.parser_ai.contract import ParserAIInput, ParserCandidateOutput

                parser_input = ParserAIInput.model_validate_json(user_messages[-1]["content"])
                candidate_target = ParserCandidateOutput.model_validate_json(
                    messages[-1]["content"]
                )
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                raise MLXPipelineError(f"contenuto chat non valido per {record_id}: {exc}") from exc
            if content_checksum(parser_input.model_dump(mode="json")) != (
                source_record.input_checksum
            ):
                raise MLXPipelineError(
                    f"contenuto chat input non coincide col manifest sorgente: {record_id}"
                )
            if content_checksum(candidate_target.model_dump(mode="json")) != (
                source_record.candidate_target_checksum
            ):
                raise MLXPipelineError(
                    f"contenuto chat target non coincide col manifest sorgente: {record_id}"
                )

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
        split.value: sum(record.split is split for record in source.records)
        for split in CorpusSplit
    }
    if report.split_counts != expected_report_counts:
        raise MLXPipelineError("split_counts del report non coincidono coi file snapshot")

    membership_counts = manifest.get("membership_counts")
    if membership_counts != expected_report_counts:
        raise MLXPipelineError("membership_counts snapshot non coincide col manifest sorgente")
    training_members = tuple(
        record
        for record in source.records
        if record.split in {CorpusSplit.TRAIN, CorpusSplit.VALIDATION} and record.training_eligible
    )
    derived_approved = (
        bool(source_ids["train"])
        and bool(source_ids["valid"])
        and all(record.training_eligible for record in training_members)
    )
    if manifest.get("training_approved") is not derived_approved:
        raise MLXPipelineError(
            "training_approved non coincide con le evidenze del manifest sorgente"
        )
    derived_synthetic = bool(training_members) and all(
        record.synthetic for record in training_members
    )
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
        "valid": tuple(f"runtime-smoke-{index:02d}" for index in range(4, 8)),
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
        "counts": {split: integrity["counts"][split] for split in ("train", "valid")},
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


def stage_verified_training_view(
    data_dir: Path,
    target_dir: Path,
    *,
    verified_snapshot: Mapping[str, Any],
    smoke_test: bool = False,
) -> dict[str, Any]:
    """Copy only pinned train/valid bytes into a run-owned immutable view."""

    try:
        current = validate_snapshot_integrity(data_dir, smoke_test=smoke_test)
    except MLXPipelineError as exc:
        raise MLXPipelineError(f"training snapshot changed after validation: {exc}") from exc
    for key in ("snapshot_id", "snapshot_sha256", "manifest_sha256"):
        if current.get(key) != verified_snapshot.get(key):
            raise MLXPipelineError(f"training snapshot changed after validation ({key})")
    expected_hashes = current["file_hashes"]
    if target_dir.exists() and any(target_dir.iterdir()):
        entries = tuple(target_dir.iterdir())
        if {entry.name for entry in entries} != {"train.jsonl", "valid.jsonl"}:
            raise MLXPipelineError("run-owned training view allowlist mismatch")
        for entry in entries:
            if entry.is_symlink() or not entry.is_file():
                raise MLXPipelineError("run-owned training view contains non-regular content")
            if sha256_file(entry) != expected_hashes[entry.name]:
                raise MLXPipelineError(f"staged training checksum changed: {entry.name}")
        target_dir.chmod(0o555)
        return {
            "path": str(target_dir.resolve()),
            "snapshot_id": current["snapshot_id"],
            "snapshot_sha256": current["snapshot_sha256"],
            "manifest_sha256": current["manifest_sha256"],
            "file_hashes": {
                entry.name: sha256_file(entry)
                for entry in sorted(entries, key=lambda item: item.name)
            },
        }
    target_dir.mkdir(parents=True, exist_ok=True)
    staged_hashes: dict[str, str] = {}
    for filename in ("train.jsonl", "valid.jsonl"):
        source = data_dir.resolve() / filename
        target = target_dir / filename
        if source.is_symlink() or not source.is_file():
            raise MLXPipelineError(f"training source replacement detected: {filename}")
        before = sha256_file(source)
        if before != expected_hashes[filename]:
            raise MLXPipelineError(f"training source checksum changed: {filename}")
        shutil.copyfile(source, target)
        after = sha256_file(source)
        staged = sha256_file(target)
        if after != before or staged != before:
            raise MLXPipelineError(f"training source changed while staging: {filename}")
        target.chmod(0o444)
        staged_hashes[filename] = staged
    if {path.name for path in target_dir.iterdir()} != {"train.jsonl", "valid.jsonl"}:
        raise MLXPipelineError("run-owned training view allowlist mismatch")
    target_dir.chmod(0o555)
    return {
        "path": str(target_dir.resolve()),
        "snapshot_id": current["snapshot_id"],
        "snapshot_sha256": current["snapshot_sha256"],
        "manifest_sha256": current["manifest_sha256"],
        "file_hashes": staged_hashes,
    }


def verify_staged_training_view(
    target_dir: Path,
    expected_hashes: Mapping[str, Any],
) -> dict[str, str]:
    """Re-verify the schema-owned view immediately at a local consumer boundary."""

    required = {"train.jsonl", "valid.jsonl"}
    if set(expected_hashes) != required:
        raise MLXPipelineError("staged training expected-hash schema mismatch")
    root = target_dir.resolve()
    try:
        entries = tuple(root.iterdir())
    except OSError as exc:
        raise MLXPipelineError(f"staged training view unreadable: {exc}") from exc
    if {entry.name for entry in entries} != required:
        raise MLXPipelineError("staged training view allowlist changed")
    verified: dict[str, str] = {}
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise MLXPipelineError(f"staged training replacement detected: {entry.name}")
        expected = expected_hashes.get(entry.name)
        if not isinstance(expected, str) or _SHA256.fullmatch(expected) is None:
            raise MLXPipelineError(f"staged training expected checksum invalid: {entry.name}")
        actual = sha256_file(entry)
        if actual != expected:
            raise MLXPipelineError(f"staged training checksum changed: {entry.name}")
        verified[entry.name] = actual
    return verified


def iter_verified_jsonl(path: Path, *, expected_sha256: str) -> Iterator[dict[str, Any]]:
    """Open, hash and parse one pinned JSONL file through the same file descriptor."""

    if _SHA256.fullmatch(expected_sha256) is None:
        raise MLXPipelineError("verified JSONL expected checksum is invalid")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MLXPipelineError(f"verified JSONL open failed: {path.name}: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MLXPipelineError(f"verified JSONL is not regular: {path.name}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read()
    finally:
        os.close(descriptor)
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise MLXPipelineError(f"verified JSONL checksum changed: {path.name}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MLXPipelineError(f"verified JSONL is not UTF-8: {path.name}") from exc
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MLXPipelineError(
                f"verified JSONL invalid at {path.name}:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise MLXPipelineError(
                f"verified JSONL row is not an object: {path.name}:{line_number}"
            )
        yield value


class ValidationConsumerViewManifest(FrozenModel):
    schema_version: Literal["8.0.0"] = "8.0.0"
    purpose: Literal["MODEL_SELECTION_VALIDATION"] = "MODEL_SELECTION_VALIDATION"
    view_id: str = ""
    view_sha256: str = ""
    payload_file: Literal["test.jsonl"] = "test.jsonl"
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_size_bytes: int = Field(ge=0)
    source_training_snapshot_id: str
    source_training_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_valid_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _content_addressed(self) -> ValidationConsumerViewManifest:
        identity = self.model_dump(mode="json", exclude={"view_id", "view_sha256"})
        checksum = content_checksum(identity)
        view_id = f"validation-consumer-{checksum[:20]}"
        if self.view_sha256 and self.view_sha256 != checksum:
            raise ValueError("validation consumer view checksum mismatch")
        if self.view_id and self.view_id != view_id:
            raise ValueError("validation consumer view id mismatch")
        object.__setattr__(self, "view_sha256", checksum)
        object.__setattr__(self, "view_id", view_id)
        return self


def _validated_validation_consumer_view(target: Path) -> dict[str, Any]:
    root = target.resolve()
    expected_names = {"test.jsonl", "consumer-view-manifest.json"}
    try:
        entries = tuple(root.iterdir())
    except OSError as exc:
        raise MLXPipelineError(f"validation consumer view unreadable: {exc}") from exc
    if {entry.name for entry in entries} != expected_names:
        raise MLXPipelineError("validation consumer view allowlist changed")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise MLXPipelineError("validation consumer view contains symlink/non-regular content")
    manifest_path = root / "consumer-view-manifest.json"
    try:
        manifest = ValidationConsumerViewManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise MLXPipelineError(f"validation consumer manifest invalid: {exc}") from exc
    payload = root / manifest.payload_file
    if payload.stat().st_size != manifest.payload_size_bytes:
        raise MLXPipelineError("validation consumer payload size changed")
    if sha256_file(payload) != manifest.payload_sha256:
        raise MLXPipelineError("validation consumer payload checksum changed")
    return {
        "path": str(root),
        "view_id": manifest.view_id,
        "view_sha256": manifest.view_sha256,
        "file_hashes": {
            "test.jsonl": manifest.payload_sha256,
            "consumer-view-manifest.json": sha256_file(manifest_path),
        },
    }


def stage_validation_consumer_view(
    data_dir: Path,
    target: Path,
    *,
    training_view: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the exact content-addressed validation-as-test consumer view."""

    expected_training_hashes = training_view.get("file_hashes")
    if not isinstance(expected_training_hashes, Mapping):
        raise MLXPipelineError("training view hashes absent for validation staging")
    verify_staged_training_view(data_dir, expected_training_hashes)
    if target.exists() and any(target.iterdir()):
        existing = _validated_validation_consumer_view(target)
        manifest = ValidationConsumerViewManifest.model_validate_json(
            (target / "consumer-view-manifest.json").read_text(encoding="utf-8")
        )
        if (
            manifest.source_training_snapshot_id != training_view.get("snapshot_id")
            or manifest.source_training_snapshot_sha256 != training_view.get("snapshot_sha256")
            or manifest.source_valid_sha256 != expected_training_hashes.get("valid.jsonl")
        ):
            raise MLXPipelineError("validation consumer view source lineage changed")
        target.chmod(0o555)
        return existing
    target.mkdir(parents=True, exist_ok=True)
    source = data_dir.resolve() / "valid.jsonl"
    payload = target / "test.jsonl"
    if source.is_symlink() or not source.is_file():
        raise MLXPipelineError("validation source replacement detected")
    before = sha256_file(source)
    if before != expected_training_hashes.get("valid.jsonl"):
        raise MLXPipelineError("validation source checksum changed")
    shutil.copyfile(source, payload)
    if sha256_file(source) != before or sha256_file(payload) != before:
        raise MLXPipelineError("validation source changed while staging")
    manifest = ValidationConsumerViewManifest(
        payload_sha256=before,
        payload_size_bytes=payload.stat().st_size,
        source_training_snapshot_id=str(training_view.get("snapshot_id")),
        source_training_snapshot_sha256=str(training_view.get("snapshot_sha256")),
        source_valid_sha256=before,
    )
    manifest_path = target / "consumer-view-manifest.json"
    _write_json(manifest_path, manifest.model_dump(mode="json"))
    payload.chmod(0o444)
    manifest_path.chmod(0o444)
    target.chmod(0o555)
    return _validated_validation_consumer_view(target)


def _required_anonymous_splits(config: Mapping[str, Any]) -> tuple[str, ...]:
    train = config.get("train") is True
    test = config.get("test") is True
    if train == test:
        raise MLXPipelineError("sealed MLX consumer requires exactly one train/test mode")
    return ("train", "valid") if train else ("test",)


@contextmanager
def _open_verified_anonymous_files(
    view: Mapping[str, Any],
    *,
    required_splits: tuple[str, ...],
) -> Iterator[dict[str, Any]]:
    root_value = view.get("path")
    expected_hashes = view.get("file_hashes")
    if not isinstance(root_value, str) or not isinstance(expected_hashes, Mapping):
        raise MLXPipelineError("sealed consumer view metadata is incomplete")
    required_filenames = tuple(f"{split}.jsonl" for split in required_splits)
    expected_names = (
        {"train.jsonl", "valid.jsonl"}
        if required_splits == ("train", "valid")
        else {"test.jsonl", "consumer-view-manifest.json"}
        if required_splits == ("test",)
        else set()
    )
    if not expected_names or set(expected_hashes) != expected_names:
        raise MLXPipelineError("sealed consumer expected-hash schema mismatch")
    for filename, expected_hash in expected_hashes.items():
        if not isinstance(filename, str) or not isinstance(expected_hash, str):
            raise MLXPipelineError("sealed consumer hash manifest invalid")
        if _SHA256.fullmatch(expected_hash) is None:
            raise MLXPipelineError(f"sealed consumer checksum invalid: {filename}")

    root = Path(root_value).absolute()
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        directory_fd = os.open(root, flags)
    except OSError as exc:
        raise MLXPipelineError(f"sealed consumer directory open failed: {exc}") from exc
    with ExitStack() as anonymous_stack:
        anonymous_by_split: dict[str, Any] = {}
        try:
            directory_metadata = os.fstat(directory_fd)
            if not stat.S_ISDIR(directory_metadata.st_mode):
                raise MLXPipelineError("sealed consumer root is not a directory")
            names = set(os.listdir(directory_fd))
            if names != expected_names:
                raise MLXPipelineError("sealed consumer view allowlist changed")
            for name in sorted(expected_names):
                expected_hash = str(expected_hashes[name])
                split = name.removesuffix(".jsonl") if name in required_filenames else None
                anonymous_file = None
                if split is not None:
                    anonymous_file = anonymous_stack.enter_context(
                        tempfile.TemporaryFile(mode="w+b")
                    )
                    anonymous_by_split[split] = anonymous_file

                digest = hashlib.sha256()
                byte_count = 0
                file_flags = os.O_RDONLY
                if hasattr(os, "O_NOFOLLOW"):
                    file_flags |= os.O_NOFOLLOW
                try:
                    file_fd = os.open(name, file_flags, dir_fd=directory_fd)
                except OSError as exc:
                    raise MLXPipelineError(
                        f"sealed consumer file symlink/replacement blocked: {name}: {exc}"
                    ) from exc
                try:
                    metadata = os.fstat(file_fd)
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o222:
                        raise MLXPipelineError(f"sealed consumer file mode changed: {name}")
                    while chunk := os.read(file_fd, 1024 * 1024):
                        digest.update(chunk)
                        byte_count += len(chunk)
                        if anonymous_file is not None:
                            anonymous_file.write(chunk)
                    if byte_count != metadata.st_size:
                        raise MLXPipelineError(f"sealed consumer file size changed: {name}")
                finally:
                    os.close(file_fd)
                if digest.hexdigest() != expected_hash:
                    raise MLXPipelineError(f"sealed consumer checksum changed: {name}")
                if anonymous_file is not None:
                    anonymous_file.flush()
                    anonymous_file.seek(0)
                    anonymous_metadata = os.fstat(anonymous_file.fileno())
                    if (
                        not stat.S_ISREG(anonymous_metadata.st_mode)
                        or anonymous_metadata.st_nlink != 0
                        or anonymous_metadata.st_size != byte_count
                    ):
                        raise MLXPipelineError(f"anonymous consumer file invariant failed: {name}")
        finally:
            os.close(directory_fd)

        if tuple(anonymous_by_split) != required_splits:
            raise MLXPipelineError("anonymous consumer split mapping is not exact")
        yield anonymous_by_split


def stream_mlx_with_sealed_view(
    config: Mapping[str, Any],
    *,
    view: Mapping[str, Any],
    config_path: Path,
    cwd: Path,
    log_path: Path,
    environment: Mapping[str, str] | None = None,
) -> CommandResult:
    """Copy verified bytes into anonymous files inherited by the MLX child."""

    required_splits = _required_anonymous_splits(config)
    if environment is not None and FD_ENV in environment:
        raise MLXPipelineError("caller cannot override the inherited-FD mapping")
    with _open_verified_anonymous_files(
        view,
        required_splits=required_splits,
    ) as anonymous_by_split:
        payload = dict(config)
        payload["data"] = FD_SENTINEL
        _write_json(config_path, payload)
        fd_mapping = {split: anonymous_by_split[split].fileno() for split in required_splits}
        child_environment = dict(environment or {})
        child_environment[FD_ENV] = json.dumps(fd_mapping, separators=(",", ":"))
        return _stream_command(
            _mlx_command(config_path),
            cwd=cwd,
            log_path=log_path,
            environment=child_environment,
            pass_fds=tuple(fd_mapping.values()),
        )


def _mlx_command(config_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "ntruth.training.mlx_fd_entrypoint",
        "--config",
        str(config_path),
    ]


def run_training(
    profile_path: Path,
    repo_root: Path,
    data_dir: Path,
    run_dir: Path,
    *,
    seed: int,
    reality_gate: RealityGateV8Protocol,
    design_lineage_pins: TrainingDesignLineagePins | None,
    design_lineage_artifact_path: Path | None,
    protected_source_manifest_path: Path | None,
    smoke_test: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Esegue QLoRA a fasi con validation, checkpoint e early stopping reale.

    MLX-LM 0.31.3 non espone early stopping nativo. Ogni fase riprende
    deterministicamente l'adapter precedente, viene valutata sul validation set e
    il controller interrompe dopo ``patience`` fasi senza miglioramento.
    """

    training_lineage = resolve_training_lineage_inputs(
        design_lineage_pins=design_lineage_pins,
        design_lineage_artifact_path=design_lineage_artifact_path,
        protected_source_manifest_path=protected_source_manifest_path,
    )
    envelope = read_training_snapshot_envelope(data_dir, smoke_test=smoke_test)
    gate_artifact = verify_training_reality_gate_v8(
        reality_gate,
        TrainingRealityGateV8Request(
            snapshot_id=str(envelope["snapshot_id"]),
            snapshot_sha256=str(envelope["snapshot_sha256"]),
        ),
    )
    dataset = validate_mlx_dataset(data_dir, smoke_test=smoke_test)
    if dataset["manifest_sha256"] != envelope["manifest_sha256"]:
        raise MLXPipelineError("training snapshot manifest changed after gate decision")
    profile = load_profile(profile_path)
    machine = doctor(profile_path, repo_root)
    if not machine["ready_to_train"]:
        raise MLXPipelineError(f"training bloccato dal doctor: {machine['checks']}")
    model_check = verify_model(profile_path, repo_root)
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
    training_view = stage_verified_training_view(
        data_dir,
        run_dir / "_verified-training-view",
        verified_snapshot=dataset,
        smoke_test=smoke_test,
    )
    training_view_dir = Path(str(training_view["path"]))
    verify_staged_training_view(training_view_dir, training_view["file_hashes"])
    validation_dir = run_dir / "_validation-as-test"
    validation_view = stage_validation_consumer_view(
        training_view_dir,
        validation_dir,
        training_view=training_view,
    )

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
        reconcile_reality_gate_pins(state, RealityGatePinTuple.from_artifact(gate_artifact))
        reconcile_training_lineage_pins(state, training_lineage)
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
            "reality_gate_artifact_id": gate_artifact.artifact_id,
            "reality_gate_artifact_sha256": gate_artifact.artifact_sha256,
            "reality_gate_privacy_attestation_sha256": (gate_artifact.privacy_attestation_sha256),
            "reality_gate_no_corpus_attestation_sha256": (
                gate_artifact.no_corpus_attestation_sha256
            ),
            **training_lineage.state_payload(),
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
            "data": str(training_view_dir),
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
        train_result = stream_mlx_with_sealed_view(
            phase_config,
            view=training_view,
            config_path=config_path,
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
        eval_result = stream_mlx_with_sealed_view(
            eval_config,
            view=validation_view,
            config_path=eval_path,
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
