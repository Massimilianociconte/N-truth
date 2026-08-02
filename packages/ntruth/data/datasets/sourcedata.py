"""Handler for SourceData-NLP v2.0.3 using lockfile validation and config alignment."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from ntruth.data.alignment import align_sourcedata_configs
from ntruth.data.config import DATASET_TASK_POLICIES, FORBIDDEN_NTRUTH_TARGETS, SOURCE_DATA_VERSION, get_manifests_dir
from ntruth.data.fs import atomic_write_json, atomic_write_text, sha256_file
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


class SourceDataError(RuntimeError):
    """SourceData processing failure."""


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
            raise SourceDataError(f"SHA-256 hash must be 64 characters for {path_str}, found: {sha}")

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
        raise SourceDataError(f"SHA-256 mismatch for {url}: expected {expected_sha256}, got {actual_sha}")

    os.replace(partial, destination)
    return actual_sha


def install_sourcedata(root: Path, refresh: bool = False) -> dict[str, Any]:
    lock = load_sourcedata_lockfile()
    repo_id = lock["repository"]
    revision = lock["revision"]
    raw_root = root / "raw" / "sourcedata" / f"v{SOURCE_DATA_VERSION}"
    processed_root = root / "processed" / "sourcedata" / f"v{SOURCE_DATA_VERSION}"
    training_ready_root = root / "training_ready" / "sourcedata_multitask"

    records_by_task_split: dict[str, dict[str, list[dict[str, Any]]]] = {
        "ner": {"train": [], "validation": [], "test": []},
        "roles_multi": {"train": [], "validation": [], "test": []},
    }

    files_manifest: list[dict[str, Any]] = []

    for file_info in lock["files"]:
        rel_path = file_info["path"]
        expected_sha = file_info["sha256"]
        parts = rel_path.split("/")
        task = parts[-2]
        split = parts[-1].replace(".jsonl", "")

        local_raw = raw_root / task / f"{split}.jsonl"
        actual_sha = download_sourcedata_file(repo_id, revision, rel_path, local_raw, expected_sha, refresh=refresh)
        files_manifest.append({"path": str(local_raw.relative_to(root)), "sha256": actual_sha, "split": split, "task": task})

        # Load raw JSONL records
        with local_raw.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                rec = json.loads(line)
                rec["split"] = split
                records_by_task_split[task][split].append(rec)

    # Process individual tasks & align for multitask
    split_counts: dict[str, int] = {}
    for split in ("train", "validation", "test"):
        ner_recs = records_by_task_split["ner"][split]
        roles_recs = records_by_task_split["roles_multi"][split]

        aligned_recs, report = align_sourcedata_configs(ner_recs, roles_recs)
        split_counts[f"multitask:{split}"] = len(aligned_recs)

        # Write multitask processed output
        out_dir = training_ready_root / split
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = out_dir / "records.jsonl"

        lines = []
        for idx, rec in enumerate(aligned_recs):
            words = rec.get("words", rec.get("tokens", []))
            normalized_text = " ".join(words)
            offsets = []
            curr = 0
            for w in words:
                offsets.append((curr, curr + len(w)))
                curr += len(w) + 1

            envelope = CommonEnvelope(
                record_id=f"sourcedata:{rec.get('panel_id', idx)}:{split}:{idx}",
                source=SourceReference(
                    dataset="SourceData",
                    version=SOURCE_DATA_VERSION,
                    commit=revision,
                    document_id=str(rec.get("document_id", "")),
                    segment_id=str(rec.get("panel_id", "")),
                ),
                split=SplitAssignment(name=split, authority="upstream_official", group_id=str(rec.get("document_id", ""))),
                eligibility=Eligibility(
                    training_eligible=(split == "train"),
                    evaluation_eligible=(split in {"validation", "test"}),
                    requires_review=False,
                ),
                provenance=Provenance(
                    source_url=f"https://huggingface.co/datasets/{repo_id}",
                    sha256=files_manifest[0]["sha256"],
                    transform_version="1.0.0",
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
                    entity_tags=rec.get("entity_tags", []),
                    role_tags=rec.get("role_tags", []),
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
        "processed_path": str(processed_root),
        "split_authority": "upstream_official",
        "split_counts": split_counts,
        "native_annotation_tier": NativeAnnotationTier.HUMAN_CURATED_GOLD,
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": files_manifest,
    }
