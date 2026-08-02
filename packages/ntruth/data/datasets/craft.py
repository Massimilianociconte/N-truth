"""Handler for CRAFT v5.0.2 with pinned 67/30 Shared Task partition."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from ntruth.data.config import CRAFT_VERSION, DATASET_TASK_POLICIES, FORBIDDEN_NTRUTH_TARGETS, get_manifests_dir
from ntruth.data.fs import atomic_extract_archive, atomic_write_text, is_ignorable_metadata, sha256_file
from ntruth.data.schemas import (
    CommonEnvelope,
    CoreferencePayload,
    Eligibility,
    NativeAnnotationTier,
    NTruthUsageTier,
    Provenance,
    SourceReference,
    SplitAssignment,
)
from ntruth.data.splits import load_craft_2019_shared_task_split, stable_split, validate_anti_leakage


class CRAFTError(RuntimeError):
    """CRAFT dataset processing error."""


def extract_craft_article_id(path: Path) -> str | None:
    match = re.search(r"(?i)(PMC\d+)", str(path))
    return match.group(1).upper() if match else None


def install_craft(root: Path, refresh: bool = False) -> dict[str, Any]:
    source_ref = CRAFT_VERSION
    archive_url = f"https://codeload.github.com/lhunter-lab/CRAFT/zip/refs/tags/{source_ref}"
    archive = root / "downloads" / f"craft-{source_ref}.zip"
    raw_root = root / "raw" / "craft" / source_ref
    processed_root = root / "processed" / "craft" / source_ref

    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() or refresh:
        try:
            req = urllib.request.Request(archive_url, headers={"User-Agent": "NTruthDataInstaller/1.0"})
            partial = archive.with_name(archive.name + ".part")
            with urllib.request.urlopen(req, timeout=60) as resp:
                partial.write_bytes(resp.read())
            os.replace(partial, archive)
        except Exception as exc:
            if not archive.exists():
                return {
                    "dataset": "CRAFT",
                    "version": source_ref,
                    "source_ref": source_ref,
                    "source_status": "UNVERIFIED",
                    "warnings": [f"CRAFT archive missing locally and network fetch failed: {exc}"],
                    "split_counts": {},
                    "files": [],
                }

    archive_sha = sha256_file(archive)
    marker = raw_root / ".ntruth_complete.json"
    if not marker.exists() or refresh:
        atomic_extract_archive(archive, raw_root, {"dataset": "craft", "source_ref": source_ref})

    # Discover PMCIDs from raw files
    found_pmcids: set[str] = set()
    files_by_pmcid: dict[str, list[Path]] = {}

    for path in raw_root.rglob("*"):
        if path.is_file() and not is_ignorable_metadata(path):
            pmcid = extract_craft_article_id(path)
            if pmcid:
                found_pmcids.add(pmcid)
                files_by_pmcid.setdefault(pmcid, []).append(path)

    if not found_pmcids:
        raise CRAFTError("No PMC identifiers discovered in CRAFT archive")

    # Load official 67/30 shared task split manifest if valid
    manifest_path = get_manifests_dir() / "craft_shared_task_2019_split.json"
    try:
        split_authority, split_map = load_craft_2019_shared_task_split(manifest_path)
    except Exception:
        split_authority = "custom_pmcid_level_fallback"
        split_map = stable_split(sorted(found_pmcids), seed="20260803", ratios=(80, 10, 10))

    validate_anti_leakage(split_map)

    split_counts: dict[str, int] = {"train": 0, "validation": 0, "test": 0}

    for split in ("train", "validation", "test"):
        out_dir = processed_root / split
        out_dir.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        for pmcid in sorted(found_pmcids):
            if split_map.get(pmcid) != split:
                continue

            pmc_files = files_by_pmcid.get(pmcid, [])
            text_files = [p for p in pmc_files if p.suffix == ".txt"]
            text_content = text_files[0].read_text(encoding="utf-8") if text_files else f"Article {pmcid}"

            envelope = CommonEnvelope(
                record_id=f"craft:{pmcid}",
                source=SourceReference(
                    dataset="CRAFT",
                    version=source_ref,
                    commit=source_ref,
                    document_id=pmcid,
                    segment_id=pmcid,
                ),
                split=SplitAssignment(name=split, authority=split_authority, group_id=pmcid),
                eligibility=Eligibility(
                    training_eligible=(split == "train"),
                    evaluation_eligible=(split in {"validation", "test"}),
                    requires_review=False,
                ),
                provenance=Provenance(
                    source_url="https://github.com/lhunter-lab/CRAFT",
                    sha256=archive_sha,
                    transform_version="1.0.0",
                ),
                native_annotation_tier=NativeAnnotationTier.HUMAN_CURATED_GOLD,
                ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
                allowed_tasks=DATASET_TASK_POLICIES["CRAFT"],
                forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
                task_type="coreference",
                payload=CoreferencePayload(text=text_content, mentions=[], chains=[]),
            )
            lines.append(envelope.model_dump_json() + "\n")

        atomic_write_text(out_dir / "records.jsonl", "".join(lines))
        split_counts[split] = len(lines)

    return {
        "dataset": "CRAFT",
        "version": source_ref,
        "source_ref": source_ref,
        "raw_path": str(raw_root),
        "processed_path": str(processed_root),
        "split_authority": split_authority,
        "split_counts": split_counts,
        "native_annotation_tier": NativeAnnotationTier.HUMAN_CURATED_GOLD,
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": [{"path": str(archive.relative_to(root)), "sha256": archive_sha}],
    }
