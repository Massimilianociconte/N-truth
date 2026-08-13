"""CLI orchestrator for N-Truth dataset acquisition, verification, alignment, repair, and lock resolution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ntruth.data.config import (
    DEFAULT_DATASET_ROOT,
    configure_external_cache_environment,
)
from ntruth.data.datasets.craft import install_craft
from ntruth.data.datasets.measeval import install_measeval
from ntruth.data.datasets.preclinie import install_preclinie
from ntruth.data.datasets.sourcedata import install_sourcedata
from ntruth.data.fs import (
    EMPTY_FILE_SHA256,
    atomic_write_json,
    calculate_manifest_merkle_root,
    canonical_file_manifest,
    is_ignorable_metadata,
    sha256_file,
)
from ntruth.data.manifests import (
    build_merkle_manifest,
    generate_datasets_manifest,
    generate_files_manifest,
    generate_splits_manifest,
)
from ntruth.data.quality import audit_common_envelope_jsonl
from ntruth.task_corpora.adapters.sourcedata_entity_roles import (
    build_sourcedata_entity_roles,
)

INTEGRITY_MANIFEST_RELATIVE_PATH = Path("manifests/checksums/merkle_manifest.json")
REQUIRED_INTEGRITY_ROOTS = (
    Path("downloads"),
    Path("raw"),
    Path("processed"),
    Path("manifests/datasets.json"),
    Path("manifests/files.jsonl"),
    Path("manifests/splits.json"),
    Path("manifests/licenses"),
    Path("manifests/reports/quality"),
    Path("manifests/sources"),
)
OPTIONAL_INTEGRITY_ROOTS = (Path("task_corpora"), Path("training_ready"))
REPAIR_LEDGER_RELATIVE_PATH = Path("quarantine/repair-ledger")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _relativize_report_paths(value: Any, root: Path) -> Any:
    """Remove host-specific root prefixes from canonical manifest reports."""

    if isinstance(value, dict):
        return {key: _relativize_report_paths(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_relativize_report_paths(item, root) for item in value]
    if isinstance(value, tuple):
        return tuple(_relativize_report_paths(item, root) for item in value)
    if isinstance(value, str):
        candidate = Path(value)
        if candidate.is_absolute():
            try:
                return candidate.resolve(strict=False).relative_to(root.resolve()).as_posix()
            except ValueError:
                return value
    return value


def _canonical_integrity_roots(root: Path) -> list[Path]:
    required = [root / path for path in REQUIRED_INTEGRITY_ROOTS]
    missing = [path for path in required if not path.exists()]
    if missing:
        rendered = ", ".join(str(path.relative_to(root)) for path in missing)
        raise FileNotFoundError(f"missing required canonical roots: {rendered}")

    optional = [root / path for path in OPTIONAL_INTEGRITY_ROOTS]
    return [*required, *(path for path in optional if path.exists())]


def _build_integrity_manifest(root: Path) -> dict[str, Any]:
    manifest = build_merkle_manifest(_canonical_integrity_roots(root))
    manifest["required_roots"] = sorted(path.as_posix() for path in REQUIRED_INTEGRITY_ROOTS)
    manifest["optional_roots"] = {
        path.as_posix(): (root / path).exists() for path in OPTIONAL_INTEGRITY_ROOTS
    }
    return manifest


def _tree_sha256(path: Path) -> str:
    return calculate_manifest_merkle_root(canonical_file_manifest([path]))


def _atomic_repair_move(source: Path, destination: Path) -> None:
    """Rename within the dataset root without a copy/delete fallback."""
    os.replace(source, destination)


def _create_repair_application_ledger(path: Path, report: dict[str, Any]) -> None:
    """Create the content-addressed replay barrier without overwriting an old record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"Repair plan already has an application record: {path}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_repair_application_records(
    application_path: Path,
    ledger_path: Path,
    report: dict[str, Any],
) -> None:
    atomic_write_json(ledger_path, report)
    if application_path != ledger_path:
        atomic_write_json(application_path, report)


def _validate_repair_target(entry: dict[str, Any], target: Path, relative_path: Path) -> None:
    if not target.exists():
        raise FileNotFoundError(target)
    if target.is_symlink():
        raise ValueError(f"Repair target may not be a symlink: {relative_path}")
    observed_type = entry.get("observed_type")
    actual_type = "directory" if target.is_dir() else "file"
    if observed_type != actual_type:
        raise ValueError(f"Repair target changed since plan creation: {relative_path}")
    observed_sha = entry.get("observed_sha256")
    if actual_type == "file" and (
        not isinstance(observed_sha, str) or sha256_file(target) != observed_sha
    ):
        raise ValueError(f"Repair target changed since plan creation: {relative_path}")
    observed_tree_sha = entry.get("observed_tree_sha256")
    if actual_type == "directory" and (
        not isinstance(observed_tree_sha, str) or _tree_sha256(target) != observed_tree_sha
    ):
        raise ValueError(f"Repair target changed since plan creation: {relative_path}")


def _assert_repair_path_has_no_symlink_components(root: Path, relative_path: Path) -> None:
    current = root
    traversed = Path()
    for component in relative_path.parts:
        traversed /= component
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as exc:
            raise ValueError(f"Repair target changed since plan creation: {relative_path}") from exc
        if stat.S_ISLNK(mode):
            raise ValueError(
                f"Repair target path contains symlink component: {traversed.as_posix()}"
            )


def _attach_processed_quality_reports(root: Path, reports: list[dict[str, Any]]) -> None:
    quality_dir = root / "manifests" / "reports" / "quality"
    for report in reports:
        dataset_name = str(report["dataset"]).casefold()
        processed_root = Path(str(report.get("processed_path", root / "processed" / dataset_name)))
        if not processed_root.is_absolute():
            processed_root = root / processed_root
        inputs = sorted(processed_root.rglob("records.jsonl")) if processed_root.is_dir() else []
        quality = audit_common_envelope_jsonl(inputs)
        destination = quality_dir / f"{dataset_name}.json"
        quality_payload = _relativize_report_paths(quality.model_dump(mode="json"), root)
        if any(Path(str(item["path"])).is_absolute() for item in quality_payload["inputs"]):
            raise ValueError(f"quality input escapes dataset root: {dataset_name}")
        atomic_write_json(destination, quality_payload)
        report["quality"] = {
            "status": quality.status.value,
            "report_path": str(destination.relative_to(root)),
            "records": quality.records.model_dump(mode="json"),
            "blockers": [
                {"code": blocker.code, "count": blocker.count} for blocker in quality.blockers
            ],
        }


def cmd_status(root: Path) -> None:
    print("=== N-Truth Dataset Acquisition Status ===")
    print(f"Root path: {root}")
    if not root.exists():
        print("Status: ERROR — Root directory does not exist or volume unmounted")
        return

    stat = os.statvfs(root)
    free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
    print(f"Available disk space on root volume: {free_gb:.2f} GB")

    for ds_name in ("sourcedata", "preclinie", "measeval", "craft"):
        raw_dir = root / "raw" / ds_name
        proc_dir = root / "processed" / ds_name
        raw_status = "PRESENT" if raw_dir.exists() and any(raw_dir.rglob("*")) else "MISSING"
        proc_status = "PRESENT" if proc_dir.exists() and any(proc_dir.rglob("*")) else "MISSING"
        print(f"  - Dataset {ds_name:12s}: raw={raw_status:7s} | processed={proc_status:7s}")


def cmd_clean_temp(root: Path) -> None:
    print(f"Cleaning temporary files under {root}...")
    removed_count = 0
    bytes_freed = 0

    for path in root.rglob("*"):
        if is_ignorable_metadata(path):
            continue
        if path.is_file() and path.name.endswith(".part"):
            bytes_freed += path.stat().st_size
            path.unlink()
            removed_count += 1
        elif path.is_dir() and ".extract." in path.name:
            # Safe temporary extract folder cleanup
            import shutil

            shutil.rmtree(path, ignore_errors=True)
            removed_count += 1

    print(
        f"Cleanup complete. Removed {removed_count} temporary items ({bytes_freed / (1024**2):.2f} MB freed)."
    )


def _load_verified_integrity_snapshot(root: Path) -> tuple[dict[str, Any], str]:
    """Read the pin once and verify that exact parsed object against canonical data."""
    merkle_manifest_path = root / INTEGRITY_MANIFEST_RELATIVE_PATH
    if not merkle_manifest_path.is_file():
        raise FileNotFoundError(f"missing pinned integrity snapshot: {merkle_manifest_path}")

    try:
        pinned_bytes = merkle_manifest_path.read_bytes()
        expected = json.loads(pinned_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"pinned integrity snapshot is unreadable: {merkle_manifest_path}"
        ) from exc
    if not isinstance(expected, dict):
        raise ValueError("pinned integrity snapshot must be a JSON object")
    current = _build_integrity_manifest(root)
    if expected != current:
        raise ValueError(
            "canonical integrity snapshot mismatch: "
            f"expected={expected.get('merkle_root')} current={current['merkle_root']}"
        )
    merkle_root = str(current["merkle_root"])
    return expected, merkle_root


def cmd_verify(root: Path) -> str:
    """Verify canonical files against the existing pinned integrity snapshot."""
    print(f"Verifying canonical dataset directories under {root}...")
    _, merkle_root = _load_verified_integrity_snapshot(root)
    print(f"Verified Canonical Merkle Root: {merkle_root}")
    return merkle_root


def cmd_snapshot_integrity(root: Path) -> str:
    """Explicitly pin the current canonical file inventory and Merkle root."""
    print(f"Snapshotting canonical dataset directories under {root}...")
    stale_export = root / "training_ready" / "sourcedata_multitask"
    if stale_export.exists():
        raise ValueError(
            "semantically stale SourceData training export must be quarantined before snapshot"
        )
    merkle_manifest_path = root / INTEGRITY_MANIFEST_RELATIVE_PATH
    manifest = _build_integrity_manifest(root)
    atomic_write_json(merkle_manifest_path, manifest)
    merkle_root = str(manifest["merkle_root"])
    print(f"Pinned Canonical Merkle Root: {merkle_root}")
    return merkle_root


def cmd_repair_existing(
    root: Path, write_plan: Path | None = None, apply_plan: Path | None = None
) -> None:
    print("=== Legacy Installer Repair Analysis ===")
    resolved_root = root.resolve()
    plan_entries: list[dict[str, Any]] = []
    quarantine_dir = resolved_root / "quarantine"

    for path in (root / "raw").rglob("*"):
        relative_path = str(path.relative_to(root))
        if is_ignorable_metadata(path):
            plan_entries.append(
                {
                    "path": relative_path,
                    "classification": "IGNORABLE_METADATA",
                    "observed_type": "directory" if path.is_dir() else "file",
                }
            )
            continue
        if path.is_dir() and ".extract." in path.name:
            plan_entries.append(
                {
                    "path": relative_path,
                    "classification": "INCOMPLETE",
                    "action": "quarantine",
                    "observed_type": "directory",
                    "observed_tree_sha256": _tree_sha256(path),
                }
            )

    stale_sourcedata_export = root / "training_ready" / "sourcedata_multitask"
    if stale_sourcedata_export.exists():
        plan_entries.append(
            {
                "path": str(stale_sourcedata_export.relative_to(root)),
                "classification": "SEMANTICALLY_STALE",
                "action": "quarantine",
                "observed_type": ("directory" if stale_sourcedata_export.is_dir() else "file"),
                (
                    "observed_tree_sha256"
                    if stale_sourcedata_export.is_dir()
                    else "observed_sha256"
                ): (
                    _tree_sha256(stale_sourcedata_export)
                    if stale_sourcedata_export.is_dir()
                    else sha256_file(stale_sourcedata_export)
                ),
            }
        )

    for path in (root / "downloads").rglob("*"):
        relative_path = str(path.relative_to(root))
        if is_ignorable_metadata(path):
            plan_entries.append(
                {
                    "path": relative_path,
                    "classification": "IGNORABLE_METADATA",
                    "observed_type": "directory" if path.is_dir() else "file",
                }
            )
            continue
        if path.is_file():
            sha = sha256_file(path)
            if sha == EMPTY_FILE_SHA256:
                plan_entries.append(
                    {
                        "path": relative_path,
                        "classification": "CORRUPT",
                        "action": "quarantine",
                        "observed_type": "file",
                        "observed_sha256": sha,
                    }
                )
            elif path.name.lower().endswith(".part"):
                plan_entries.append(
                    {
                        "path": relative_path,
                        "classification": "INCOMPLETE",
                        "action": "quarantine",
                        "observed_type": "file",
                        "observed_sha256": sha,
                    }
                )
            else:
                plan_entries.append(
                    {
                        "path": relative_path,
                        "classification": "PRESENT_UNVERIFIED",
                        "observed_type": "file",
                        "observed_sha256": sha,
                    }
                )

    report = {
        "analyzed_at": _utc_now(),
        "root": str(resolved_root),
        "total_items": len(plan_entries),
        "planned_action_count": sum("action" in entry for entry in plan_entries),
        "plan": plan_entries,
    }

    if write_plan:
        atomic_write_json(write_plan, report)
        print(f"Repair plan written to {write_plan}")

    if apply_plan and apply_plan.exists():
        plan_bytes = apply_plan.read_bytes()
        plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
        plan_data = json.loads(plan_bytes.decode("utf-8"))
        application_path = apply_plan.with_name(f"{apply_plan.stem}.application.json")
        ledger_path = (
            resolved_root / REPAIR_LEDGER_RELATIVE_PATH / (f"{plan_sha256}.application.json")
        )
        existing_application = next(
            (
                path
                for path in (application_path, ledger_path)
                if path.exists() or path.is_symlink()
            ),
            None,
        )
        if existing_application is not None:
            raise ValueError(
                f"Repair plan already has an application record: {existing_application}"
            )
        if Path(str(plan_data.get("root", ""))).resolve() != resolved_root:
            raise ValueError("Repair plan root does not match requested root")
        raw_plan = plan_data.get("plan", [])
        if not isinstance(raw_plan, list):
            raise ValueError("Repair plan actions must be a list")
        if any(not isinstance(entry, dict) for entry in raw_plan):
            raise ValueError("Repair plan entries must be objects")
        validated_plan = cast(list[dict[str, Any]], raw_plan)

        resolved_quarantine = quarantine_dir.resolve(strict=False)
        try:
            resolved_quarantine.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError("Quarantine directory escapes requested root") from exc
        resolved_ledger_path = ledger_path.resolve(strict=False)
        try:
            resolved_ledger_path.relative_to(resolved_quarantine)
        except ValueError as exc:
            raise ValueError("Repair application ledger escapes quarantine root") from exc

        actions: list[tuple[Path, Path, Path, dict[str, Any]]] = []
        seen_targets: set[Path] = set()
        seen_destinations: set[Path] = set()
        for plan_entry in validated_plan:
            action = plan_entry.get("action")
            if action is not None and action != "quarantine":
                raise ValueError(f"Unsupported repair action: {action}")
            if action == "quarantine":
                action_path = Path(str(plan_entry.get("path", "")))
                if (
                    action_path.is_absolute()
                    or action_path == Path(".")
                    or ".." in action_path.parts
                ):
                    raise ValueError(f"Repair plan path must be relative: {action_path}")
                if action_path.parts[0] not in {"downloads", "raw", "training_ready"}:
                    raise ValueError(f"Repair plan path is outside repair scope: {action_path}")
                _assert_repair_path_has_no_symlink_components(resolved_root, action_path)
                target = resolved_root / action_path
                resolved_target = target.resolve(strict=False)
                try:
                    resolved_target.relative_to(resolved_root)
                except ValueError as exc:
                    raise ValueError(f"Repair plan path escapes root: {action_path}") from exc
                if resolved_target in seen_targets:
                    raise ValueError(f"Duplicate repair target: {action_path}")
                seen_targets.add(resolved_target)
                if not target.exists():
                    raise ValueError(f"Repair target changed since plan creation: {action_path}")
                _validate_repair_target(plan_entry, target, action_path)

                destination = quarantine_dir / action_path
                resolved_destination = destination.resolve(strict=False)
                try:
                    resolved_destination.relative_to(resolved_quarantine)
                except ValueError as exc:
                    raise ValueError(
                        f"Quarantine destination escapes quarantine root: {action_path}"
                    ) from exc
                if resolved_destination in seen_destinations:
                    raise ValueError(f"Duplicate quarantine destination: {destination}")
                seen_destinations.add(resolved_destination)
                if destination.exists() or destination.is_symlink():
                    raise ValueError(f"Quarantine destination already exists: {destination}")
                existing_parent = destination.parent
                while not existing_parent.exists() and existing_parent != quarantine_dir.parent:
                    existing_parent = existing_parent.parent
                if not existing_parent.is_dir():
                    raise ValueError(
                        f"Quarantine destination parent is not a directory: {destination}"
                    )
                if target.stat().st_dev != existing_parent.stat().st_dev:
                    raise ValueError(
                        f"Repair target and quarantine destination are on different filesystems: "
                        f"{action_path}"
                    )
                actions.append((action_path, target, destination, plan_entry))

        for index, (_, target, _, _) in enumerate(actions):
            for _, other_target, _, _ in actions[index + 1 :]:
                if target in other_target.parents or other_target in target.parents:
                    raise ValueError("Repair plan may not contain nested quarantine targets")

        planned_actions = sum(
            plan_entry.get("action") == "quarantine" for plan_entry in validated_plan
        )
        application_path = apply_plan.with_name(f"{apply_plan.stem}.application.json")
        if application_path.exists() or application_path.is_symlink():
            raise ValueError(f"Repair plan already has an application record: {application_path}")
        action_results: list[dict[str, str]] = [
            {"path": str(path), "status": "PENDING"} for path, _, _, _ in actions
        ]
        application_report = {
            "application_schema": "ntruth.repair-application.v1",
            "status": "APPLYING",
            "root": str(resolved_root),
            "plan_path": str(apply_plan.resolve()),
            "plan_sha256": plan_sha256,
            "planned_action_count": planned_actions,
            "applied_action_count": 0,
            "skipped_action_count": 0,
            "actions": action_results,
        }
        _create_repair_application_ledger(ledger_path, application_report)
        if application_path != ledger_path:
            atomic_write_json(application_path, application_report)

        moved_actions: list[tuple[Path, Path, Path]] = []
        try:
            for action_path, target, destination, plan_entry in actions:
                try:
                    _assert_repair_path_has_no_symlink_components(resolved_root, action_path)
                    _validate_repair_target(plan_entry, target, action_path)
                except FileNotFoundError as exc:
                    raise ValueError(
                        f"Repair target changed since plan creation: {action_path}"
                    ) from exc
                destination.parent.mkdir(parents=True, exist_ok=True)
                result = next(item for item in action_results if item["path"] == str(action_path))
                result["status"] = "MOVING"
                _write_repair_application_records(application_path, ledger_path, application_report)
                _assert_repair_path_has_no_symlink_components(resolved_root, action_path)
                _atomic_repair_move(target, destination)
                moved_actions.append((action_path, target, destination))
                result["status"] = "QUARANTINED"
                application_report["applied_action_count"] = len(moved_actions)
                _write_repair_application_records(application_path, ledger_path, application_report)
        except BaseException as apply_error:
            rollback_errors: list[str] = []
            for moved_path, target, destination in reversed(moved_actions):
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_repair_move(destination, target)
                    for result in action_results:
                        if result["path"] == str(moved_path):
                            result["status"] = "ROLLED_BACK"
                            break
                except BaseException as rollback_error:
                    rollback_errors.append(f"{moved_path}: {rollback_error}")

            application_report["status"] = "ROLLBACK_FAILED" if rollback_errors else "ROLLED_BACK"
            application_report["applied_action_count"] = sum(
                result["status"] == "QUARANTINED" for result in action_results
            )
            application_report["error"] = f"{type(apply_error).__name__}: {apply_error}"
            if rollback_errors:
                application_report["rollback_errors"] = rollback_errors
            _write_repair_application_records(application_path, ledger_path, application_report)
            if rollback_errors:
                raise RuntimeError(
                    "Repair apply failed and rollback was incomplete; inspect application report"
                ) from apply_error
            raise

        application_report["status"] = "APPLIED"
        application_report["applied_action_count"] = len(moved_actions)
        _write_repair_application_records(application_path, ledger_path, application_report)
        print(f"Applied repair plan: moved {len(moved_actions)} items to {quarantine_dir}")


def cmd_lock_resolve(root: Path, dataset: str, output_path: Path) -> None:
    print(f"Resolving candidate lockfile for dataset={dataset}...")
    del root
    if dataset != "sourcedata":
        raise ValueError(f"Lock resolution currently supported for sourcedata, got {dataset}")
    from ntruth.data.datasets.sourcedata import load_sourcedata_lockfile

    candidate = {"sourcedata": load_sourcedata_lockfile()}
    atomic_write_json(output_path, candidate)
    print(f"Lock candidate generated: {output_path}")


def cmd_lock_verify(candidate_path: Path) -> None:
    print(f"Verifying lock candidate {candidate_path}...")
    data = json.loads(candidate_path.read_text(encoding="utf-8"))
    sourcedata = data.get("sourcedata", {})

    revision = sourcedata.get("revision", "")
    if not revision or revision in {"...", "TBD", "TODO"}:
        raise ValueError(f"Lock candidate has invalid revision: {revision}")

    files = sourcedata.get("files", [])
    if len(files) != 6:
        raise ValueError(f"Lock candidate must specify 6 files, found {len(files)}")

    for f in files:
        sha = f.get("sha256", "")
        if sha == EMPTY_FILE_SHA256:
            raise ValueError(f"Lock candidate contains empty file hash for {f['path']}")
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None:
            raise ValueError(
                f"Lock candidate requires a valid lowercase SHA-256 for {f.get('path', '')}"
            )

    print("Lock candidate successfully verified.")


def cmd_all(root: Path, resume: bool = False) -> None:
    print("=== Running Full N-Truth Dataset Acquisition Pipeline ===")
    configure_external_cache_environment(root)

    integrity_path = root / INTEGRITY_MANIFEST_RELATIVE_PATH
    merkle_before = None
    previous_snapshot: dict[str, Any] | None = None
    if resume:
        previous_snapshot, merkle_before = _load_verified_integrity_snapshot(root)
    elif integrity_path.is_file():
        try:
            loaded_snapshot = json.loads(integrity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded_snapshot = None
        if isinstance(loaded_snapshot, dict):
            previous_snapshot = loaded_snapshot
            merkle_before = previous_snapshot.get("merkle_root")

    reports = []
    reports.append(install_sourcedata(root, refresh=not resume))
    reports.append(install_preclinie(root, refresh=not resume))
    reports.append(install_measeval(root, refresh=not resume))
    reports.append(install_craft(root, refresh=not resume))
    _attach_processed_quality_reports(root, reports)

    build_sourcedata_entity_roles(root, resume=resume)

    # Generate Manifests
    manifests_dir = root / "manifests"
    canonical_reports = [_relativize_report_paths(report, root) for report in reports]
    generate_datasets_manifest(canonical_reports, manifests_dir)

    all_file_entries = []
    for rep in reports:
        all_file_entries.extend(rep.get("files", []))
    generate_files_manifest(all_file_entries, manifests_dir)

    split_mappings = {rep["dataset"]: rep.get("split_counts", {}) for rep in reports}
    generate_splits_manifest(split_mappings, manifests_dir)
    (manifests_dir / "licenses").mkdir(parents=True, exist_ok=True)
    (manifests_dir / "sources").mkdir(parents=True, exist_ok=True)

    candidate_snapshot = _build_integrity_manifest(root)
    if resume:
        if previous_snapshot is None:
            raise RuntimeError("resume requires a verified pinned integrity snapshot")
        if candidate_snapshot != previous_snapshot:
            raise ValueError(
                "resume build changed canonical data; refusing to overwrite pinned integrity "
                f"snapshot: before={merkle_before} "
                f"candidate={candidate_snapshot['merkle_root']}"
            )
        merkle_after = str(candidate_snapshot["merkle_root"])
        cmd_verify(root)
    else:
        merkle_after = cmd_snapshot_integrity(root)
        cmd_verify(root)
    print(f"Pipeline complete. Merkle Root: {merkle_after} (before={merkle_before})")


def main() -> int:
    parser = argparse.ArgumentParser(description="N-Truth Dataset Acquisition & Preparation CLI")
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_DATASET_ROOT, help="Dataset root directory"
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume existing downloads and extractions"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    for sc in ("status", "clean-temp", "verify", "snapshot-integrity", "all"):
        sub = subparsers.add_parser(sc)
        sub.add_argument("--root", type=Path, default=None)
        sub.add_argument("--resume", action="store_true")

    repair_parser = subparsers.add_parser("repair-existing")
    repair_parser.add_argument("--root", type=Path, default=None)
    repair_parser.add_argument("--from-legacy-installer", action="store_true")
    repair_parser.add_argument("--write-plan", type=Path)
    repair_parser.add_argument("--apply-plan", type=Path)

    lock_parser = subparsers.add_parser("lock")
    lock_parser.add_argument("--root", type=Path, default=None)
    lock_sub = lock_parser.add_subparsers(dest="lock_command", required=True)
    resolve_p = lock_sub.add_parser("resolve")
    resolve_p.add_argument("--root", type=Path, default=None)
    resolve_p.add_argument("--dataset", required=True)
    resolve_p.add_argument("--output", type=Path, required=True)
    verify_p = lock_sub.add_parser("verify")
    verify_p.add_argument("--root", type=Path, default=None)
    verify_p.add_argument("--candidate", type=Path, required=True)

    args = parser.parse_args()
    root = args.root or DEFAULT_DATASET_ROOT

    if args.command == "status":
        cmd_status(root)
    elif args.command == "clean-temp":
        cmd_clean_temp(root)
    elif args.command == "verify":
        cmd_verify(root)
    elif args.command == "snapshot-integrity":
        cmd_snapshot_integrity(root)
    elif args.command == "repair-existing":
        cmd_repair_existing(root, write_plan=args.write_plan, apply_plan=args.apply_plan)
    elif args.command == "lock":
        if args.lock_command == "resolve":
            cmd_lock_resolve(root, args.dataset, args.output)
        elif args.lock_command == "verify":
            cmd_lock_verify(args.candidate)
    elif args.command == "all":
        cmd_all(root, resume=args.resume)

    return 0


if __name__ == "__main__":
    sys.exit(main())
