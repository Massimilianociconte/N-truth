"""Tokenizzazione, generazione, scoring ed export locale degli adapter MLX."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ntruth.training.blockers import SCIENTIFIC_EXECUTION_CLOSED_DETAIL
from ntruth.training.mlx_runtime import (
    RUN_SCHEMA_VERSION,
    MLXPipelineError,
    _consume_isolated_training_payloads,
    load_profile_artifact,
    sha256_file,
    validate_mlx_dataset,
    verify_model,
)

EVALUATION_LINEAGE_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EVALUATION_SPLIT_FILES = {
    "validation": "valid.jsonl",
    "test": "test.jsonl",
    "external": "external.jsonl",
}
_SNAPSHOT_COUNT_NAMES = {
    "validation": "valid",
    "test": "test",
    "external": "external",
}
_EXPORTABLE_RUN_STATUSES = {"completed_maximum_phases", "early_stopped"}
_EVALUABLE_RUN_STATUSES = {*_EXPORTABLE_RUN_STATUSES, "stopped_memory_ceiling"}


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MLXPipelineError(f"{label} non leggibile: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MLXPipelineError(f"{label} deve essere un oggetto JSON: {path}")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MLXPipelineError(f"{label} assente o non valido")
    return value


def _require_equal(actual: object, expected: object, *, label: str) -> None:
    if actual != expected:
        raise MLXPipelineError(f"lineage non coerente: {label}")


def _verify_best_run(
    profile_path: Path,
    repo_root: Path,
    run_dir: Path,
    *,
    adapter_path: Path | None = None,
) -> dict[str, Any]:
    """Verifica profilo, modello, run-state e adapter ``best`` come un'unita."""

    profile_path = profile_path.resolve()
    repo_root = repo_root.resolve()
    run_dir = run_dir.resolve()
    expected_adapter_dir = run_dir / "best"
    supplied_adapter = (adapter_path or expected_adapter_dir).resolve()
    if supplied_adapter != expected_adapter_dir or supplied_adapter.name != "best":
        raise MLXPipelineError("inferenza consentita soltanto con l'adapter best del run")

    state_path = run_dir / "run-state.json"
    state = _read_json_object(state_path, label="run-state")
    if state.get("schema_version") != RUN_SCHEMA_VERSION:
        raise MLXPipelineError(
            f"run-state {RUN_SCHEMA_VERSION} obbligatorio per inferenza ed export"
        )
    status = state.get("status")
    if status not in _EVALUABLE_RUN_STATUSES:
        raise MLXPipelineError(f"run non valutabile nello stato {status!r}")

    profile_sha256 = sha256_file(profile_path)
    _require_equal(state.get("profile_sha256"), profile_sha256, label="profilo del run")
    model_check = verify_model(profile_path, repo_root)
    model_provenance_sha256 = _require_sha256(
        model_check.get("provenance_sha256"),
        label="provenance modello verificato",
    )
    _require_equal(
        state.get("model_provenance_sha256"),
        model_provenance_sha256,
        label="provenance modello del run",
    )

    best_phase = state.get("best_phase")
    last_completed_phase = state.get("last_completed_phase")
    if (
        isinstance(best_phase, bool)
        or not isinstance(best_phase, int)
        or best_phase < 1
        or isinstance(last_completed_phase, bool)
        or not isinstance(last_completed_phase, int)
        or last_completed_phase < best_phase
    ):
        raise MLXPipelineError("best_phase non valido nel run-state")

    adapter_file = expected_adapter_dir / "adapters.safetensors"
    if adapter_file.is_symlink() or not adapter_file.is_file():
        raise MLXPipelineError("adapter best assente o symlink non ammesso")
    adapter_sha256 = sha256_file(adapter_file)
    expected_adapter_sha256 = _require_sha256(
        state.get("best_adapter_sha256"),
        label="best_adapter_sha256 nel run-state",
    )
    _require_equal(adapter_sha256, expected_adapter_sha256, label="checksum adapter best")

    adapter_config = expected_adapter_dir / "adapter_config.json"
    adapter_config_sha256: str | None = None
    expected_config_sha256 = state.get("best_adapter_config_sha256")
    if adapter_config.exists():
        if adapter_config.is_symlink() or not adapter_config.is_file():
            raise MLXPipelineError("adapter_config best non regolare")
        adapter_config_sha256 = sha256_file(adapter_config)
        _require_equal(
            _require_sha256(
                expected_config_sha256,
                label="best_adapter_config_sha256 nel run-state",
            ),
            adapter_config_sha256,
            label="checksum adapter_config best",
        )
    elif expected_config_sha256 is not None:
        raise MLXPipelineError("adapter_config best mancante rispetto al run-state")

    dataset_snapshot_sha256 = _require_sha256(
        state.get("dataset_snapshot_sha256"),
        label="dataset_snapshot_sha256 nel run-state",
    )
    dataset_manifest_sha256 = _require_sha256(
        state.get("dataset_manifest_sha256"),
        label="dataset_manifest_sha256 nel run-state",
    )
    dataset_snapshot_id = state.get("dataset_snapshot_id")
    if not isinstance(dataset_snapshot_id, str) or not dataset_snapshot_id:
        raise MLXPipelineError("dataset_snapshot_id assente nel run-state")
    smoke_test = state.get("smoke_test")
    if not isinstance(smoke_test, bool):
        raise MLXPipelineError("smoke_test non booleano nel run-state")

    return {
        "schema_version": EVALUATION_LINEAGE_SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "profile_path": str(profile_path),
        "profile_sha256": profile_sha256,
        "model_provenance_sha256": model_provenance_sha256,
        "run_dir": str(run_dir),
        "run_state_path": str(state_path),
        "run_state_sha256": sha256_file(state_path),
        "run_status": status,
        "run_dataset_snapshot_id": dataset_snapshot_id,
        "run_dataset_snapshot_sha256": dataset_snapshot_sha256,
        "run_dataset_manifest_sha256": dataset_manifest_sha256,
        "smoke_test": smoke_test,
        "best_phase": best_phase,
        "adapter_path": str(expected_adapter_dir),
        "adapter_sha256": adapter_sha256,
        "adapter_config_sha256": adapter_config_sha256,
    }


def _verify_evaluation_snapshot(
    evaluation_jsonl: Path,
    declared_split: str,
    run_lineage: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    from ntruth.training.blind_evaluation import PROTECTED_EVALUATION_BLOCKER

    if declared_split in {"test", "external"}:
        raise MLXPipelineError(PROTECTED_EVALUATION_BLOCKER)
    filename = _EVALUATION_SPLIT_FILES.get(declared_split)
    if filename is None:
        raise MLXPipelineError(f"split di evaluation non supportato: {declared_split}")
    evaluation_jsonl = evaluation_jsonl.absolute()
    if evaluation_jsonl.is_symlink() or evaluation_jsonl.name != filename:
        raise MLXPipelineError(
            f"mismatch split/file: {declared_split} richiede esattamente {filename}"
        )
    data_dir = evaluation_jsonl.parent.resolve()
    expected_path = data_dir / filename
    if evaluation_jsonl.resolve() != expected_path or not expected_path.is_file():
        raise MLXPipelineError(
            f"mismatch split/file: {declared_split} richiede il file manifestato {filename}"
        )

    smoke_test = run_lineage.get("smoke_test") is True
    snapshot = validate_mlx_dataset(data_dir, smoke_test=smoke_test)
    count_name = _SNAPSHOT_COUNT_NAMES[declared_split]
    if int(snapshot["counts"].get(count_name, 0)) < 1:
        raise MLXPipelineError(f"split di evaluation vuoto: {declared_split}")

    if declared_split == "validation":
        _require_equal(
            snapshot["snapshot_id"],
            run_lineage.get("run_dataset_snapshot_id"),
            label=f"snapshot {declared_split} rispetto al run",
        )
        _require_equal(
            snapshot["snapshot_sha256"],
            run_lineage.get("run_dataset_snapshot_sha256"),
            label=f"checksum snapshot {declared_split} rispetto al run",
        )
        _require_equal(
            snapshot["manifest_sha256"],
            run_lineage.get("run_dataset_manifest_sha256"),
            label=f"manifest snapshot {declared_split} rispetto al run",
        )
    return expected_path, snapshot


def _evaluation_lineage(
    run_lineage: Mapping[str, Any],
    evaluation_path: Path,
    snapshot: Mapping[str, Any],
    declared_split: str,
) -> dict[str, Any]:
    filename = _EVALUATION_SPLIT_FILES[declared_split]
    return {
        **dict(run_lineage),
        "declared_split": declared_split,
        "evaluation_dataset_path": str(evaluation_path.parent),
        "evaluation_file": filename,
        "evaluation_sha256": snapshot["file_hashes"][filename],
        "evaluation_snapshot_id": snapshot["snapshot_id"],
        "evaluation_snapshot_sha256": snapshot["snapshot_sha256"],
        "evaluation_manifest_sha256": snapshot["manifest_sha256"],
        "evaluation_runtime_smoke_only": snapshot["runtime_smoke_only"],
    }


def tokenize_report(
    profile_path: Path,
    repo_root: Path,
    data_dir: Path,
    output_path: Path,
    *,
    smoke_test: bool = False,
) -> dict[str, Any]:
    """Misura le lunghezze reali senza produrre copie tokenizzate permanenti."""

    data_root = data_dir.resolve()
    if output_path.resolve().is_relative_to(data_root):
        raise MLXPipelineError("report token non puo essere scritto nella training view")
    dataset = validate_mlx_dataset(data_root, smoke_test=smoke_test)
    profile: dict[str, Any] = {}
    if profile_path.is_file() and not profile_path.is_symlink():
        profile, _checksum = load_profile_artifact(profile_path)
    _consume_isolated_training_payloads(
        data_root,
        dataset,
        profile=profile,
        authorization=None,
        smoke_test=smoke_test,
    )
    del repo_root
    raise MLXPipelineError(SCIENTIFIC_EXECUTION_CLOSED_DETAIL)


def predict_and_score(
    profile_path: Path,
    repo_root: Path,
    evaluation_jsonl: Path,
    adapter_path: Path,
    output_dir: Path,
    *,
    declared_split: str,
    retry_invalid_once: bool = True,
) -> dict[str, Any]:
    """Genera JSON locale, valida lo schema e calcola metriche candidate-fact."""

    from ntruth.training.blind_evaluation import PROTECTED_EVALUATION_BLOCKER

    if declared_split in {"test", "external"}:
        raise MLXPipelineError(PROTECTED_EVALUATION_BLOCKER)
    if declared_split != "validation" or evaluation_jsonl.name != "valid.jsonl":
        raise MLXPipelineError("mismatch split/file: validation richiede esattamente valid.jsonl")
    data_root = evaluation_jsonl.parent.resolve()
    if output_dir.resolve().is_relative_to(data_root):
        raise MLXPipelineError("directory predictions non puo essere dentro la training view")
    smoke_manifest = data_root / "snapshot-manifest.json"
    smoke_test = False
    if smoke_manifest.is_file() and not smoke_manifest.is_symlink():
        raw_manifest = _read_json_object(smoke_manifest, label="manifest snapshot smoke")
        smoke_test = raw_manifest.get("runtime_smoke_only") is True
    dataset = validate_mlx_dataset(data_root, smoke_test=smoke_test)
    profile: dict[str, Any] = {}
    if profile_path.is_file() and not profile_path.is_symlink():
        profile, _checksum = load_profile_artifact(profile_path)
    _consume_isolated_training_payloads(
        data_root,
        dataset,
        profile=profile,
        authorization=None,
        smoke_test=smoke_test,
    )
    del repo_root, adapter_path, retry_invalid_once
    raise MLXPipelineError(SCIENTIFIC_EXECUTION_CLOSED_DETAIL)


def _verify_metrics_artifacts(
    metrics_path: Path,
    *,
    expected_split: str | None = None,
    require_real: bool = False,
) -> dict[str, Any]:
    del metrics_path, expected_split, require_real
    raise MLXPipelineError(SCIENTIFIC_EXECUTION_CLOSED_DETAIL)


def calibrate_predictions(
    observations_jsonl: Path,
    output_path: Path,
    *,
    fit_split: str = "validation",
    maximum_risk: float = 0.10,
    minimum_coverage_count: int = 10,
) -> dict[str, Any]:
    del observations_jsonl, output_path, fit_split, maximum_risk, minimum_coverage_count
    raise MLXPipelineError(SCIENTIFIC_EXECUTION_CLOSED_DETAIL)


def _verify_calibration_artifact(calibration_path: Path) -> dict[str, Any]:
    del calibration_path
    raise MLXPipelineError(SCIENTIFIC_EXECUTION_CLOSED_DETAIL)


def export_adapter_bundle(
    profile_path: Path,
    repo_root: Path,
    run_dir: Path,
    output_dir: Path,
    *,
    dataset_manifest: Path,
    metrics_path: Path,
    calibration_path: Path,
) -> dict[str, Any]:
    """Fail closed until protected metrics carry a one-shot attestation."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise MLXPipelineError("directory export non vuota")
    del profile_path, repo_root, run_dir, dataset_manifest, metrics_path, calibration_path
    from ntruth.training.blind_evaluation import PROTECTED_EVALUATION_BLOCKER

    raise MLXPipelineError(
        f"export finale bloccato: {PROTECTED_EVALUATION_BLOCKER}; "
        "serve inoltre un'attestazione finale verificabile"
    )
