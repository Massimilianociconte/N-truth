"""Handler for SourceData-NLP v2.0.3 using lockfile validation and config alignment."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Literal, cast

from ntruth.data.alignment import align_sourcedata_configs
from ntruth.data.config import (
    DATASET_TASK_POLICIES,
    FORBIDDEN_NTRUTH_TARGETS,
    SOURCE_DATA_VERSION,
    get_manifests_dir,
)
from ntruth.data.fs import atomic_write_json, atomic_write_text, sha256_file
from ntruth.data.jsonl import count_jsonl_records, iter_jsonl
from ntruth.data.schemas import (
    CommonEnvelope,
    Eligibility,
    NativeAnnotationTier,
    NTruthUsageTier,
    OffsetAuthority,
    Provenance,
    SourceReference,
    SplitAssignment,
    TokenClassificationPayload,
)

EMPTY_FILE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SOURCE_DATA_EXPECTED_SPLIT_COUNTS = {
    "train": 60_266,
    "validation": 8_201,
    "test": 6_696,
}


class SourceDataError(RuntimeError):
    """SourceData processing failure."""


def validate_sourcedata_split_counts(split_counts: dict[str, int]) -> None:
    for split, expected in SOURCE_DATA_EXPECTED_SPLIT_COUNTS.items():
        actual = split_counts.get(split)
        if actual != expected:
            raise SourceDataError(f"{split}: expected {expected}, found {actual}")


def _words_hash(words: list[str]) -> str:
    canonical_words = json.dumps(words, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(canonical_words).hexdigest()


def build_sourcedata_record_id(
    *,
    revision: str,
    split: str,
    physical_line_number: int,
    words: list[str],
) -> str:
    return f"sourcedata:{revision}:{split}:{physical_line_number}:{_words_hash(words)[:16]}"


def _preserve_sourcedata_semantics(
    *,
    ner_record: dict[str, Any],
    roles_record: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    ner_text = ner_record.get("text")
    roles_text = roles_record.get("text")
    if not isinstance(ner_text, str) or not isinstance(roles_text, str):
        raise SourceDataError("SourceData record is missing original text")
    if ner_text != roles_text:
        raise SourceDataError("SourceData original text mismatch between configurations")

    configuration_metadata: dict[str, dict[str, Any]] = {}
    for configuration, record in (("ner", ner_record), ("roles_multi", roles_record)):
        if "is_category" not in record:
            raise SourceDataError(
                f"SourceData {configuration} record is missing is_category metadata"
            )
        is_category = record["is_category"]
        if not isinstance(is_category, list):
            raise SourceDataError(f"SourceData {configuration} is_category metadata must be a list")
        configuration_metadata[configuration] = {"is_category": is_category}

    return ner_text, {
        "configurations": configuration_metadata,
        "transformation": {
            "is_category": "preserved_opaque_not_mapped_to_tag_mask",
            "original_text": "shared_exact_upstream_text",
        },
    }


def load_sourcedata_lockfile() -> dict[str, Any]:
    lockfile_path = get_manifests_dir() / "public_sources.lock.json"
    if not lockfile_path.exists():
        raise SourceDataError(f"Lockfile missing: {lockfile_path}")
    data = json.loads(lockfile_path.read_text(encoding="utf-8"))
    sourcedata_lock = data.get("sourcedata", {})

    # Validate lockfile integrity
    revision = sourcedata_lock.get("revision", "")
    if not revision or revision in {"...", "TBD", "TODO"}:
        raise SourceDataError(f"Invalid or unresolved SourceData revision in lockfile: {revision}")

    for file_info in sourcedata_lock.get("files", []):
        path_str = file_info.get("path", "")
        sha = file_info.get("sha256", "")
        if not path_str or not sha or sha in {"...", "TBD", "TODO"}:
            raise SourceDataError(f"Invalid placeholder hash for {path_str} in lockfile")
        if len(sha) != 64:
            raise SourceDataError(
                f"SHA-256 hash must be 64 characters for {path_str}, found: {sha}"
            )

    return sourcedata_lock


def download_sourcedata_file(
    repo_id: str,
    revision: str,
    file_path_relative: str,
    destination: Path,
    expected_sha256: str,
    refresh: bool = False,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not refresh:
        actual_sha = sha256_file(destination)
        if actual_sha == expected_sha256:
            return actual_sha
        if actual_sha == EMPTY_FILE_SHA256:
            raise SourceDataError(f"Local file {destination} is empty (SHA-256 e3b0c442...)")

    url = f"https://huggingface.co/datasets/{repo_id}/resolve/{revision}/{file_path_relative}?download=true"
    req = urllib.request.Request(url, headers={"User-Agent": "NTruthDataInstaller/1.0"})
    partial = destination.with_name(destination.name + ".part")

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            content = resp.read()
            if not content:
                raise SourceDataError(f"Downloaded empty file from {url}")
            partial.write_bytes(content)
    except Exception as exc:
        if partial.exists():
            partial.unlink()
        raise SourceDataError(f"Failed downloading {url}: {exc}") from exc

    actual_sha = sha256_file(partial)
    if actual_sha == EMPTY_FILE_SHA256:
        partial.unlink()
        raise SourceDataError(f"Downloaded file from {url} is empty")
    if actual_sha != expected_sha256 and expected_sha256 != "SKIP_CHECK":
        partial.unlink()
        raise SourceDataError(
            f"SHA-256 mismatch for {url}: expected {expected_sha256}, got {actual_sha}"
        )

    os.replace(partial, destination)
    return actual_sha


def install_sourcedata(root: Path, refresh: bool = False) -> dict[str, Any]:
    lock = load_sourcedata_lockfile()
    repo_id = lock["repository"]
    revision = lock["revision"]
    raw_root = root / "raw" / "sourcedata" / f"v{SOURCE_DATA_VERSION}"
    processed_root = root / "processed" / "sourcedata" / f"v{SOURCE_DATA_VERSION}"
    multitask_root = processed_root / "multitask"

    records_by_task_split: dict[str, dict[str, list[dict[str, Any]]]] = {
        "ner": {"train": [], "validation": [], "test": []},
        "roles_multi": {"train": [], "validation": [], "test": []},
    }

    files_manifest: list[dict[str, Any]] = []
    parsed_counts_by_task: dict[str, dict[str, int]] = {"ner": {}, "roles_multi": {}}

    for file_info in lock["files"]:
        rel_path = file_info["path"]
        expected_sha = file_info["sha256"]
        parts = rel_path.split("/")
        task = parts[-2]
        split = parts[-1].replace(".jsonl", "")

        local_raw = raw_root / task / f"{split}.jsonl"
        actual_sha = download_sourcedata_file(
            repo_id, revision, rel_path, local_raw, expected_sha, refresh=refresh
        )
        files_manifest.append(
            {
                "path": str(local_raw.relative_to(root)),
                "sha256": actual_sha,
                "split": split,
                "task": task,
            }
        )

        framing = count_jsonl_records(local_raw)
        if framing["blank_line_count"]:
            raise SourceDataError(f"{local_raw}: blank physical JSONL lines are not allowed")
        parsed_counts_by_task[task][split] = framing["parsed_record_count"]
        for physical_line_number, rec in iter_jsonl(local_raw):
            rec["split"] = split
            rec["_physical_line_number"] = physical_line_number
            records_by_task_split[task][split].append(rec)

    for task, counts in parsed_counts_by_task.items():
        try:
            validate_sourcedata_split_counts(counts)
        except SourceDataError as exc:
            raise SourceDataError(f"{task}: {exc}") from exc

    # Process individual tasks & align for multitask
    split_counts: dict[str, int] = {}
    for split in ("train", "validation", "test"):
        ner_recs = records_by_task_split["ner"][split]
        roles_recs = records_by_task_split["roles_multi"][split]
        roles_by_line_number = {
            int(record["_physical_line_number"]): record for record in roles_recs
        }

        aligned_recs, report = align_sourcedata_configs(ner_recs, roles_recs)
        split_counts[f"multitask:{split}"] = len(aligned_recs)

        # This is a validated auxiliary snapshot, not a training export. Paper-level
        # provenance and explicit development/training rights remain unresolved.
        out_dir = multitask_root / split
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = out_dir / "records.jsonl"
        split_inputs = sorted(
            (entry for entry in files_manifest if entry["split"] == split),
            key=lambda entry: entry["task"],
        )
        source_inputs_path = out_dir / "source_inputs.json"
        atomic_write_json(
            source_inputs_path,
            {
                "dataset": "SourceData",
                "revision": revision,
                "split": split,
                "inputs": split_inputs,
            },
        )
        source_inputs_sha = sha256_file(source_inputs_path)

        lines = []
        for rec in aligned_recs:
            words = rec.get("words", rec.get("tokens", []))
            physical_line_number = int(rec["_physical_line_number"])
            roles_record = roles_by_line_number.get(physical_line_number)
            if roles_record is None:
                raise SourceDataError(
                    "SourceData aligned record has no roles_multi source at physical line "
                    f"{physical_line_number}"
                )
            original_text, source_metadata = _preserve_sourcedata_semantics(
                ner_record=rec,
                roles_record=roles_record,
            )
            normalized_text = " ".join(words)
            offsets = []
            curr = 0
            for w in words:
                offsets.append((curr, curr + len(w)))
                curr += len(w) + 1

            envelope = CommonEnvelope(
                record_id=build_sourcedata_record_id(
                    revision=revision,
                    split=split,
                    physical_line_number=physical_line_number,
                    words=words,
                ),
                source=SourceReference(
                    dataset="SourceData",
                    version=SOURCE_DATA_VERSION,
                    commit=revision,
                    document_id="",
                    segment_id=(f"{split}:{physical_line_number}:{_words_hash(words)[:16]}"),
                ),
                split=SplitAssignment(
                    name=cast(Literal["train", "validation", "test", "trial"], split),
                    authority="upstream_official",
                    # No paper/panel identity exists in the locked JSONL. Grouping the
                    # whole revision together is conservative and prevents a false
                    # paper-level anti-leakage claim.
                    group_id=f"unknown_document_scope:{revision}",
                ),
                eligibility=Eligibility(
                    training_eligible=False,
                    evaluation_eligible=False,
                    requires_review=False,
                ),
                provenance=Provenance(
                    source_url=f"https://huggingface.co/datasets/{repo_id}",
                    sha256=source_inputs_sha,
                    transform_version="1.2.0",
                ),
                native_annotation_tier=NativeAnnotationTier.HUMAN_CURATED_GOLD,
                ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
                allowed_tasks=DATASET_TASK_POLICIES["SourceData"],
                forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
                task_type="token_classification",
                payload=TokenClassificationPayload(
                    tokens=words,
                    token_offsets=offsets,
                    offset_authority=OffsetAuthority.DERIVED_NORMALIZED_TEXT,
                    normalized_text=normalized_text,
                    original_text=original_text,
                    entity_tags=rec.get("entity_tags", []),
                    role_tags=rec.get("role_tags", []),
                    source_metadata=source_metadata,
                ),
            )
            lines.append(envelope.model_dump_json() + "\n")

        atomic_write_text(jsonl_path, "".join(lines))
        atomic_write_json(out_dir / "alignment_report.json", report)

    return {
        "dataset": "SourceData",
        "version": SOURCE_DATA_VERSION,
        "source_ref": revision,
        "raw_path": str(raw_root),
        "processed_path": str(multitask_root),
        "split_authority": "upstream_official",
        "split_counts": split_counts,
        "status": "ACQUIRED_AND_PROCESSED_NOT_TRAINING_READY",
        "model_use_status": "BLOCKED",
        "training_ready_status": "NOT_MATERIALIZED",
        "model_use_blockers": [
            "paper_level_provenance_unresolved",
            "ntruth_partition_not_approved",
            "development_and_training_rights_not_closed",
        ],
        "leakage_group_granularity": "REVISION_SCOPE_FAIL_CLOSED",
        "paper_level_leakage_claim_allowed": False,
        "semantic_preservation": {
            "original_text": "payload.original_text",
            "is_category": "payload.source_metadata.configurations",
            "is_category_mapped_to_tag_mask": False,
        },
        "native_annotation_tier": NativeAnnotationTier.HUMAN_CURATED_GOLD,
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": files_manifest,
    }
