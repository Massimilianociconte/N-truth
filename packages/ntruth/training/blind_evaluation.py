"""Physical custody boundary between training and protected evaluation splits."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from collections import Counter
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from ntruth.governance.lineage import CorpusSplit
from ntruth.schemas.core import content_checksum
from ntruth.training.records import PreparedRecord, dumps_prepared_jsonl

TRAINING_VIEW_SCHEMA_VERSION = "1.0.0"
PROTECTED_SEAL_SCHEMA_VERSION = "1.0.0"
PROTECTED_EVALUATION_BLOCKER = (
    "evaluation protetta bloccata: serve un permit monouso autorizzato e un ledger "
    "append-only verificabile"
)
_PAYLOAD_FILES = frozenset({"train.jsonl", "valid.jsonl", "training-records.jsonl"})
_VIEW_FILES = frozenset(
    {
        *_PAYLOAD_FILES,
        "training-view-manifest.json",
        "protected-split-seal.json",
    }
)
_PROTECTED_CUSTODY_FILES = {"test": "test.jsonl", "external": "external.jsonl"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_VIEW_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "artifact_type",
        "created_at",
        "dataset_id",
        "custody_snapshot_id",
        "custody_snapshot_sha256",
        "custody_manifest_sha256",
        "source_records_checksum",
        "parser_contract_version",
        "prompt_template_version",
        "training_approved",
        "leakage_check_passed",
        "counts",
        "files",
        "protected_split_seal",
        "training_view_sha256",
        "training_view_id",
    }
)
_SEAL_KEYS = frozenset(
    {
        "schema_version",
        "artifact_type",
        "created_at",
        "custody_snapshot",
        "training_split_commitments",
        "protected_split_commitments",
        "parser_contract_version",
        "prompt_template_version",
        "seal_sha256",
        "seal_id",
    }
)


def _runtime() -> Any:
    from ntruth.training import mlx_runtime

    return mlx_runtime


def _fail(message: str) -> NoReturn:
    raise _runtime().MLXPipelineError(message)


def _identity(
    value: Mapping[str, Any],
    *,
    excluded: frozenset[str],
    prefix: str,
) -> tuple[str, str]:
    payload = {str(key): item for key, item in value.items() if key not in excluded}
    digest = _runtime().sha256_json(payload)
    return digest, prefix + digest[:20]


def _ordered_ids_commitment(record_ids: tuple[str, ...]) -> str:
    return content_checksum(list(record_ids))


def _file_entry(path: Path, *, count: int, record_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "sha256": _runtime().sha256_file(path),
        "size_bytes": path.stat().st_size,
        "count": count,
        "ordered_record_ids_sha256": _ordered_ids_commitment(record_ids),
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _assert_custody_file_unchanged(
    custody_root: Path,
    custody: Mapping[str, Any],
    filename: str,
) -> None:
    expected_hashes = custody.get("file_hashes")
    expected_sizes = custody.get("file_sizes")
    if not isinstance(expected_hashes, dict) or not isinstance(expected_sizes, dict):
        _fail("validazione custody priva di checksum e dimensioni")
    expected_hash = expected_hashes.get(filename)
    expected_size = expected_sizes.get(filename)
    path = custody_root / filename
    if (
        not isinstance(expected_hash, str)
        or _SHA256.fullmatch(expected_hash) is None
        or isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
    ):
        _fail(f"validazione custody priva di commitment per {filename}")
    try:
        changed = (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != expected_size
            or _runtime().sha256_file(path) != expected_hash
        )
    except OSError:
        changed = True
    if changed:
        _fail(f"custody input cambiato dopo la validazione: {filename}")


def _copy_verified_custody_file(
    custody_root: Path,
    custody: Mapping[str, Any],
    filename: str,
    destination: Path,
) -> None:
    _assert_custody_file_unchanged(custody_root, custody, filename)
    shutil.copyfile(custody_root / filename, destination)
    _assert_custody_file_unchanged(custody_root, custody, filename)
    expected_hash = custody["file_hashes"][filename]
    expected_size = custody["file_sizes"][filename]
    if (
        destination.stat().st_size != expected_size
        or _runtime().sha256_file(destination) != expected_hash
    ):
        _fail(f"copia custody non coerente con la validazione: {filename}")


def _assert_custody_snapshot_unchanged(
    custody_root: Path,
    custody: Mapping[str, Any],
) -> None:
    expected_hashes = custody.get("file_hashes")
    if not isinstance(expected_hashes, dict):
        _fail("validazione custody priva dei file manifestati")
    for filename in sorted(expected_hashes):
        _assert_custody_file_unchanged(custody_root, custody, filename)
    manifest_path = custody_root / "snapshot-manifest.json"
    expected_manifest_hash = custody.get("manifest_sha256")
    try:
        manifest_changed = (
            manifest_path.is_symlink()
            or not manifest_path.is_file()
            or not isinstance(expected_manifest_hash, str)
            or _runtime().sha256_file(manifest_path) != expected_manifest_hash
        )
    except OSError:
        manifest_changed = True
    if manifest_changed:
        _fail("custody input cambiato dopo la validazione: snapshot-manifest.json")


def _load_prepared(path: Path) -> tuple[PreparedRecord, ...]:
    records: list[PreparedRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        _fail(f"training records non leggibili: {path}: {exc}")
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(PreparedRecord.model_validate_json(line))
        except ValueError as exc:
            _fail(f"training record non valido {path}:{line_number}: {exc}")
    return tuple(records)


def _manifest_record_commitment(source_manifest: Mapping[str, Any], split: str) -> str:
    records = source_manifest.get("records")
    if not isinstance(records, list):
        _fail("manifest sorgente privo dei record necessari al seal")
    source_split = "validation" if split == "valid" else split
    selected = [
        record
        for record in records
        if isinstance(record, dict) and record.get("split") == source_split
    ]
    selected.sort(key=lambda value: str(value.get("record_id", "")))
    return content_checksum(selected)


def freeze_training_view(custody_snapshot: Path, output_dir: Path) -> dict[str, Any]:
    """Freeze a full validated custody snapshot into a blind-safe training view.

    This operation is the only path here allowed to inspect protected custody
    payloads. The resulting directory has no protected record, identifier, target,
    source manifest or preparation report.
    """

    runtime = _runtime()
    custody = runtime.validate_snapshot_integrity(custody_snapshot.resolve())
    manifest = custody["manifest"]
    if manifest.get("training_approved") is not True:
        _fail("custody snapshot non approvato per il training")
    if manifest.get("leakage_check_passed") is not True:
        _fail("custody snapshot privo di leakage_check_passed=true")
    target = output_dir.resolve()
    custody_root = custody_snapshot.resolve()
    if target.is_relative_to(custody_root) or custody_root.is_relative_to(target):
        _fail("training view e custody snapshot devono avere root fisicamente separati")
    if target.exists():
        _fail(f"training view gia esistente: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.tmp-{uuid.uuid4().hex}"
    temporary.mkdir()
    try:
        for filename in ("train.jsonl", "valid.jsonl"):
            _copy_verified_custody_file(
                custody_root,
                custody,
                filename,
                temporary / filename,
            )

        _assert_custody_file_unchanged(custody_root, custody, "prepared-records.jsonl")
        prepared = _load_prepared(custody_root / "prepared-records.jsonl")
        _assert_custody_file_unchanged(custody_root, custody, "prepared-records.jsonl")
        training_records = tuple(
            sorted(
                (
                    record
                    for record in prepared
                    if record.split in {CorpusSplit.TRAIN, CorpusSplit.VALIDATION}
                ),
                key=lambda record: record.record.record_id,
            )
        )
        if len(training_records) != custody["counts"]["train"] + custody["counts"]["valid"]:
            _fail("prepared records train/validation non coerenti con la custody snapshot")
        (temporary / "training-records.jsonl").write_text(
            dumps_prepared_jsonl(training_records), encoding="utf-8"
        )

        training_entries: dict[str, dict[str, Any]] = {}
        for split, filename in (("train", "train.jsonl"), ("valid", "valid.jsonl")):
            ids = tuple(custody["split_record_ids"][split])
            training_entries[split] = _file_entry(
                temporary / filename,
                count=int(custody["counts"][split]),
                record_ids=ids,
            )

        source_manifest = custody.get("source_manifest")
        if not isinstance(source_manifest, dict):
            _fail("custody snapshot reale priva di source manifest")
        protected_entries: dict[str, dict[str, Any]] = {}
        for split, filename in _PROTECTED_CUSTODY_FILES.items():
            _assert_custody_file_unchanged(custody_root, custody, filename)
            ids = tuple(custody["split_record_ids"][split])
            entry = _file_entry(
                custody_root / filename,
                count=int(custody["counts"][split]),
                record_ids=ids,
            )
            if (
                entry["sha256"] != custody["file_hashes"][filename]
                or entry["size_bytes"] != custody["file_sizes"][filename]
            ):
                _fail(f"custody input cambiato durante la lettura: {filename}")
            _assert_custody_file_unchanged(custody_root, custody, filename)
            entry["source_manifest_entries_sha256"] = _manifest_record_commitment(
                source_manifest, split
            )
            protected_entries[split] = entry

        seal: dict[str, Any] = {
            "schema_version": PROTECTED_SEAL_SCHEMA_VERSION,
            "artifact_type": "ntruth-protected-split-seal",
            "created_at": runtime.utc_now(),
            "custody_snapshot": {
                "snapshot_id": custody["snapshot_id"],
                "snapshot_sha256": custody["snapshot_sha256"],
                "manifest_sha256": custody["manifest_sha256"],
                "dataset_id": manifest["dataset_id"],
                "source_records_checksum": manifest["source_records_checksum"],
            },
            "training_split_commitments": training_entries,
            "protected_split_commitments": protected_entries,
            "parser_contract_version": manifest.get("parser_contract_version"),
            "prompt_template_version": manifest.get("prompt_template_version"),
        }
        seal["seal_sha256"], seal["seal_id"] = _identity(
            seal,
            excluded=frozenset({"created_at", "seal_sha256", "seal_id"}),
            prefix="protected-seal-",
        )
        seal_path = temporary / "protected-split-seal.json"
        _write_json(seal_path, seal)

        training_ids = tuple(record.record.record_id for record in training_records)
        files = {
            "train.jsonl": {
                "sha256": training_entries["train"]["sha256"],
                "size_bytes": training_entries["train"]["size_bytes"],
            },
            "valid.jsonl": {
                "sha256": training_entries["valid"]["sha256"],
                "size_bytes": training_entries["valid"]["size_bytes"],
            },
            "training-records.jsonl": {
                "sha256": runtime.sha256_file(temporary / "training-records.jsonl"),
                "size_bytes": (temporary / "training-records.jsonl").stat().st_size,
                "count": len(training_records),
                "ordered_record_ids_sha256": _ordered_ids_commitment(training_ids),
            },
        }
        view: dict[str, Any] = {
            "schema_version": TRAINING_VIEW_SCHEMA_VERSION,
            "artifact_type": "ntruth-blind-training-view",
            "created_at": runtime.utc_now(),
            "dataset_id": manifest["dataset_id"],
            "custody_snapshot_id": custody["snapshot_id"],
            "custody_snapshot_sha256": custody["snapshot_sha256"],
            "custody_manifest_sha256": custody["manifest_sha256"],
            "source_records_checksum": manifest["source_records_checksum"],
            "parser_contract_version": manifest.get("parser_contract_version"),
            "prompt_template_version": manifest.get("prompt_template_version"),
            "training_approved": True,
            "leakage_check_passed": True,
            "counts": {
                "train": int(custody["counts"]["train"]),
                "valid": int(custody["counts"]["valid"]),
            },
            "files": files,
            "protected_split_seal": {
                "seal_id": seal["seal_id"],
                "seal_sha256": seal["seal_sha256"],
                "artifact_sha256": runtime.sha256_file(seal_path),
            },
        }
        view["training_view_sha256"], view["training_view_id"] = _identity(
            view,
            excluded=frozenset({"created_at", "training_view_sha256", "training_view_id"}),
            prefix="mlx-training-view-",
        )
        _write_json(temporary / "training-view-manifest.json", view)
        _assert_custody_snapshot_unchanged(custody_root, custody)
        temporary.replace(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return validate_training_view(target)


def _validate_commitment_entry(value: object, *, label: str, count: int) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "sha256",
        "size_bytes",
        "count",
        "ordered_record_ids_sha256",
    }:
        _fail(f"commitment non valido per {label}")
    if value.get("count") != count:
        _fail(f"conteggio commitment non coerente per {label}")
    for key in ("sha256", "ordered_record_ids_sha256"):
        item = value.get(key)
        if not isinstance(item, str) or _SHA256.fullmatch(item) is None:
            _fail(f"{key} non valido per {label}")
    size = value.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        _fail(f"size_bytes non valido per {label}")
    return value


def _validate_seal(path: Path, view: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _runtime()
    seal = runtime._load_json_object(path, label="protected split seal")
    if set(seal) != _SEAL_KEYS:
        _fail("campi protected split seal inattesi o mancanti")
    if seal.get("schema_version") != PROTECTED_SEAL_SCHEMA_VERSION:
        _fail("schema protected split seal non supportato")
    if seal.get("artifact_type") != "ntruth-protected-split-seal":
        _fail("artifact_type protected split seal non valido")
    expected_hash, expected_id = _identity(
        seal,
        excluded=frozenset({"created_at", "seal_sha256", "seal_id"}),
        prefix="protected-seal-",
    )
    if seal.get("seal_sha256") != expected_hash or seal.get("seal_id") != expected_id:
        _fail("identita protected split seal non coerente")
    reference = view.get("protected_split_seal")
    if not isinstance(reference, dict) or set(reference) != {
        "seal_id",
        "seal_sha256",
        "artifact_sha256",
    }:
        _fail("riferimento protected split seal non valido")
    if reference.get("seal_id") != expected_id or reference.get("seal_sha256") != expected_hash:
        _fail("protected split seal non coincide con la training view")
    if reference.get("artifact_sha256") != runtime.sha256_file(path):
        _fail("checksum artefatto protected split seal non coerente")
    protected = seal.get("protected_split_commitments")
    if not isinstance(protected, dict) or set(protected) != {"test", "external"}:
        _fail("commitment split protetti incompleti")
    for split, entry in protected.items():
        if not isinstance(entry, dict) or set(entry) != {
            "sha256",
            "size_bytes",
            "count",
            "ordered_record_ids_sha256",
            "source_manifest_entries_sha256",
        }:
            _fail(f"commitment protetto non valido per {split}")
        for key in ("sha256", "ordered_record_ids_sha256", "source_manifest_entries_sha256"):
            item = entry.get(key)
            if not isinstance(item, str) or _SHA256.fullmatch(item) is None:
                _fail(f"{key} non valido nel commitment protetto {split}")
        count = entry.get("count")
        size = entry.get("size_bytes")
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            _fail(f"metadati numerici non validi nel commitment protetto {split}")
    custody = seal.get("custody_snapshot")
    if not isinstance(custody, dict) or set(custody) != {
        "snapshot_id",
        "snapshot_sha256",
        "manifest_sha256",
        "dataset_id",
        "source_records_checksum",
    }:
        _fail("custody snapshot commitment non valido nel seal")
    cross_checks = {
        "snapshot_id": view.get("custody_snapshot_id"),
        "snapshot_sha256": view.get("custody_snapshot_sha256"),
        "manifest_sha256": view.get("custody_manifest_sha256"),
        "dataset_id": view.get("dataset_id"),
        "source_records_checksum": view.get("source_records_checksum"),
    }
    if any(custody.get(key) != expected for key, expected in cross_checks.items()):
        _fail("custody commitment del seal non coincide con la training view")
    for key in ("parser_contract_version", "prompt_template_version"):
        if seal.get(key) != view.get(key):
            _fail(f"{key} del seal non coincide con la training view")
    return seal


def validate_training_view(data_dir: Path) -> dict[str, Any]:
    """Validate only the isolated allowlist; never resolve or open custody data."""

    runtime = _runtime()
    root = data_dir.resolve()
    if data_dir.is_symlink() or not root.is_dir():
        _fail("training view assente o symlink non ammesso")
    actual = {path.name for path in root.iterdir()}
    unexpected = sorted(actual - _VIEW_FILES)
    missing = sorted(_VIEW_FILES - actual)
    if unexpected:
        _fail(f"file inattesi nella training view: {unexpected}")
    if missing:
        _fail(f"file obbligatori assenti dalla training view: {missing}")
    for filename in _VIEW_FILES:
        path = root / filename
        if path.is_symlink() or not path.is_file():
            _fail(f"file training view non regolare: {filename}")
        if PurePosixPath(filename).parts != (filename,):
            _fail(f"nome file training view non sicuro: {filename}")

    manifest_path = root / "training-view-manifest.json"
    manifest = runtime._load_json_object(manifest_path, label="training view manifest")
    if set(manifest) != _VIEW_MANIFEST_KEYS:
        _fail("campi training view manifest inattesi o mancanti")
    if manifest.get("schema_version") != TRAINING_VIEW_SCHEMA_VERSION:
        _fail("schema training view non supportato")
    if manifest.get("artifact_type") != "ntruth-blind-training-view":
        _fail("artifact_type training view non valido")
    for key in (
        "dataset_id",
        "custody_snapshot_id",
        "parser_contract_version",
        "prompt_template_version",
        "training_view_id",
    ):
        value = manifest.get(key)
        if not isinstance(value, str) or _SAFE_IDENTIFIER.fullmatch(value) is None:
            _fail(f"identificatore training view non valido: {key}")
    for key in (
        "custody_snapshot_sha256",
        "custody_manifest_sha256",
        "source_records_checksum",
        "training_view_sha256",
    ):
        value = manifest.get(key)
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            _fail(f"checksum training view non valido: {key}")
    expected_hash, expected_id = _identity(
        manifest,
        excluded=frozenset({"created_at", "training_view_sha256", "training_view_id"}),
        prefix="mlx-training-view-",
    )
    if (
        manifest.get("training_view_sha256") != expected_hash
        or manifest.get("training_view_id") != expected_id
    ):
        _fail("identita training view non coerente")
    if manifest.get("training_approved") is not True:
        _fail("training view non approvata")
    if manifest.get("leakage_check_passed") is not True:
        _fail("training view priva di leakage_check_passed=true")

    counts = manifest.get("counts")
    if not isinstance(counts, dict) or set(counts) != {"train", "valid"}:
        _fail("counts training view deve contenere esattamente train e valid")
    for split in ("train", "valid"):
        count = counts.get(split)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            _fail(f"split training view vuoto o non valido: {split}")

    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != _PAYLOAD_FILES:
        _fail("files training view deve contenere solo payload train/validation")
    profiles: dict[str, dict[str, Any]] = {}
    seen_ids: dict[str, str] = {}
    for split, filename in (("train", "train.jsonl"), ("valid", "valid.jsonl")):
        entry = files.get(filename)
        if not isinstance(entry, dict) or set(entry) != {"sha256", "size_bytes"}:
            _fail(f"entry manifest non valida per {filename}")
        path = root / filename
        if entry.get("sha256") != runtime.sha256_file(path):
            _fail(f"checksum training view non coerente per {filename}")
        if entry.get("size_bytes") != path.stat().st_size:
            _fail(f"dimensione training view non coerente per {filename}")
        profile = runtime._jsonl_profile(path)
        if profile["count"] != counts[split]:
            _fail(f"conteggio training view non coerente per {split}")
        for record_id in profile["record_ids"]:
            previous = seen_ids.setdefault(record_id, split)
            if previous != split:
                _fail(f"record_id {record_id!r} attraversa train e validation")
        profiles[split] = profile

    records_path = root / "training-records.jsonl"
    records_entry = files.get("training-records.jsonl")
    training_records = _load_prepared(records_path)
    expected_count = counts["train"] + counts["valid"]
    records_entry = _validate_commitment_entry(
        records_entry,
        label="training-records.jsonl",
        count=expected_count,
    )
    if records_entry["sha256"] != runtime.sha256_file(records_path):
        _fail("checksum training-records.jsonl non coerente")
    if records_entry["size_bytes"] != records_path.stat().st_size:
        _fail("dimensione training-records.jsonl non coerente")
    record_ids = tuple(record.record.record_id for record in training_records)
    if len(record_ids) != len(set(record_ids)):
        duplicates = sorted(
            record_id for record_id, count in Counter(record_ids).items() if count > 1
        )
        _fail(f"record_id duplicati nei training records: {duplicates}")
    if records_entry["ordered_record_ids_sha256"] != _ordered_ids_commitment(record_ids):
        _fail("ordered_record_ids_sha256 non coerente per training-records.jsonl")
    if any(
        record.split not in {CorpusSplit.TRAIN, CorpusSplit.VALIDATION}
        for record in training_records
    ):
        _fail("training-records.jsonl contiene uno split protetto")
    if any(not record.record.training_eligible for record in training_records):
        _fail("training-records.jsonl contiene record non eleggibili")

    from ntruth.training.mlx_dataset import _chat_record

    expected_chat: dict[str, list[dict[str, Any]]] = {"train": [], "valid": []}
    group_splits: dict[str, str] = {}
    for prepared in training_records:
        split = "train" if prepared.split is CorpusSplit.TRAIN else "valid"
        expected_chat[split].append(_chat_record(prepared))
        previous = group_splits.setdefault(prepared.leakage_group_id, split)
        if previous != split:
            _fail("leakage group attraversa train e validation")
    for split in ("train", "valid"):
        expected_rows = sorted(expected_chat[split], key=lambda row: str(row["record_id"]))
        actual_rows = sorted(profiles[split]["records"], key=lambda row: str(row["record_id"]))
        if expected_rows != actual_rows:
            _fail(f"contenuto chat {split} non coincide coi training records")

    seal = _validate_seal(root / "protected-split-seal.json", manifest)
    training_commitments = seal.get("training_split_commitments")
    if not isinstance(training_commitments, dict) or set(training_commitments) != {
        "train",
        "valid",
    }:
        _fail("commitment train/validation incompleti nel seal")
    for split, filename in (("train", "train.jsonl"), ("valid", "valid.jsonl")):
        entry = training_commitments[split]
        _validate_commitment_entry(entry, label=split, count=counts[split])
        if entry["sha256"] != files[filename]["sha256"]:
            _fail(f"seal non coerente col payload {split}")
        if entry["size_bytes"] != files[filename]["size_bytes"]:
            _fail(f"dimensione seal non coerente col payload {split}")
        if entry["ordered_record_ids_sha256"] != _ordered_ids_commitment(
            tuple(profiles[split]["record_ids"])
        ):
            _fail(f"seal non coerente con gli ID ordinati {split}")

    return {
        "path": str(root),
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "manifest_sha256": runtime.sha256_file(manifest_path),
        "training_view_id": expected_id,
        "training_view_sha256": expected_hash,
        "snapshot_id": expected_id,
        "snapshot_sha256": expected_hash,
        "counts": {"train": counts["train"], "valid": counts["valid"]},
        "file_hashes": {filename: files[filename]["sha256"] for filename in _PAYLOAD_FILES},
        "file_sizes": {filename: files[filename]["size_bytes"] for filename in _PAYLOAD_FILES},
        "protected_split_seal_id": seal["seal_id"],
        "protected_split_seal_sha256": seal["seal_sha256"],
        "protected_split_seal_artifact_sha256": manifest["protected_split_seal"]["artifact_sha256"],
        "custody_snapshot_id": manifest["custody_snapshot_id"],
        "custody_snapshot_sha256": manifest["custody_snapshot_sha256"],
        "custody_manifest_sha256": manifest["custody_manifest_sha256"],
        "training_approved": True,
        "leakage_check_passed": True,
        "runtime_smoke_only": False,
    }
