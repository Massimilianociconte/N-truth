"""Handler for CRAFT v5.0.2 with pinned 67/30 Shared Task partition."""

from __future__ import annotations

import os
import re
import shutil
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
    """Extract a PMCID embedded in a path component (rare in v5.0.2 layout)."""
    match = re.search(r"(?i)(PMC\d+)", str(path))
    return match.group(1).upper() if match else None


def _normalize_pmcid(value: str) -> str:
    value = value.strip().upper()
    if not value:
        raise CRAFTError("Empty PMCID")
    if value.startswith("PMC"):
        return value
    if value.isdigit():
        return f"PMC{value}"
    raise CRAFTError(f"Unrecognized PMCID token: {value}")


def load_craft_id_mappings(raw_root: Path) -> dict[str, Any]:
    """Parse articles/ids/craft-idmappings.txt → PMCID/PMID/filename indices."""
    mapping_path = raw_root / "articles" / "ids" / "craft-idmappings.txt"
    if not mapping_path.exists():
        # tolerate nested single-root remnants
        candidates = [
            p
            for p in raw_root.rglob("craft-idmappings.txt")
            if p.is_file() and not is_ignorable_metadata(p)
        ]
        if not candidates:
            raise CRAFTError("craft-idmappings.txt not found under CRAFT raw root")
        mapping_path = sorted(candidates)[0]

    pmcid_by_pmid: dict[str, str] = {}
    pmcid_by_filename: dict[str, str] = {}
    pmid_by_pmcid: dict[str, str] = {}

    for line in mapping_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 3:
            continue
        filename, pmcid_raw, pmid = parts[0].strip(), parts[1].strip(), parts[2].strip()
        pmcid = _normalize_pmcid(pmcid_raw)
        pmcid_by_pmid[pmid] = pmcid
        pmcid_by_filename[filename] = pmcid
        pmcid_by_filename[Path(filename).stem] = pmcid
        pmid_by_pmcid[pmcid] = pmid

    if not pmcid_by_pmid:
        raise CRAFTError("No PMCID mappings parsed from craft-idmappings.txt")

    return {
        "mapping_path": str(mapping_path),
        "pmcid_by_pmid": pmcid_by_pmid,
        "pmcid_by_filename": pmcid_by_filename,
        "pmid_by_pmcid": pmid_by_pmcid,
        "pmcids": sorted(pmid_by_pmcid.keys()),
    }


def load_craft_official_split(raw_root: Path) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Load official train/dev/test PMID lists and map them to PMCIDs.

    Authority: CRAFT Shared Task 2019 identifier files shipped in the corpus
    (articles/ids/craft-ids-{train,dev,test}.txt). Dev maps to validation.
    """
    mappings = load_craft_id_mappings(raw_root)
    pmcid_by_pmid: dict[str, str] = mappings["pmcid_by_pmid"]
    ids_dir = Path(mappings["mapping_path"]).parent

    def _read_pmids(name: str) -> list[str]:
        path = ids_dir / f"craft-ids-{name}.txt"
        if not path.exists():
            raise CRAFTError(f"Official CRAFT id file missing: {path}")
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    train_pmids = _read_pmids("train")
    dev_pmids = _read_pmids("dev")
    test_pmids = _read_pmids("test")

    def _map(pmids: list[str], label: str) -> list[str]:
        out: list[str] = []
        for pmid in pmids:
            pmcid = pmcid_by_pmid.get(pmid)
            if pmcid is None:
                raise CRAFTError(f"Official {label} PMID {pmid} missing from craft-idmappings.txt")
            out.append(pmcid)
        return out

    train_pmcids = _map(train_pmids, "train")
    dev_pmcids = _map(dev_pmids, "dev")
    test_pmcids = _map(test_pmids, "test")

    train_dev = set(train_pmcids) | set(dev_pmcids)
    test_set = set(test_pmcids)
    if not train_dev.isdisjoint(test_set):
        raise CRAFTError("Official CRAFT train/dev and test PMCID sets overlap")
    if set(train_pmcids) & set(dev_pmcids):
        raise CRAFTError("Official CRAFT train and dev PMCID sets overlap")

    split_map: dict[str, str] = {}
    for pmcid in train_pmcids:
        split_map[pmcid] = "train"
    for pmcid in dev_pmcids:
        split_map[pmcid] = "validation"
    for pmcid in test_pmcids:
        split_map[pmcid] = "test"

    evidence = {
        "source": "articles/ids/craft-ids-{train,dev,test}.txt + craft-idmappings.txt",
        "source_counts": {
            "train": len(train_pmcids),
            "validation": len(dev_pmcids),
            "test": len(test_pmcids),
        },
        "mapping_path": mappings["mapping_path"],
    }
    return "craft_shared_task_2019", split_map, evidence


def _discover_files_by_pmcid(raw_root: Path, mappings: dict[str, Any]) -> dict[str, list[Path]]:
    """Index raw files under each PMCID using idmappings + path heuristics."""
    files_by_pmcid: dict[str, list[Path]] = {pmcid: [] for pmcid in mappings["pmcids"]}
    pmcid_by_pmid: dict[str, str] = mappings["pmcid_by_pmid"]
    pmcid_by_filename: dict[str, str] = mappings["pmcid_by_filename"]
    pmid_by_pmcid: dict[str, str] = mappings["pmid_by_pmcid"]

    for path in raw_root.rglob("*"):
        if not path.is_file() or is_ignorable_metadata(path):
            continue

        pmcid = extract_craft_article_id(path)
        if pmcid is None:
            name = path.name
            stem = path.stem
            pmcid = pmcid_by_filename.get(name) or pmcid_by_filename.get(stem)
        if pmcid is None:
            # articles/txt/{pmid}.txt layout
            if path.suffix == ".txt" and path.stem.isdigit():
                pmcid = pmcid_by_pmid.get(path.stem)
        if pmcid is None:
            # nxml often ends with -{pmcid_numeric}.nxml without PMC prefix
            match = re.search(r"-(\d+)\.(?:nxml|txt|xml)$", path.name)
            if match:
                token = match.group(1)
                pmcid = pmcid_by_pmid.get(token) or (
                    f"PMC{token}" if f"PMC{token}" in files_by_pmcid else None
                )

        if pmcid and pmcid in files_by_pmcid:
            files_by_pmcid[pmcid].append(path)

    # Ensure primary text path is preferred when present
    for pmcid, pmid in pmid_by_pmcid.items():
        preferred = raw_root / "articles" / "txt" / f"{pmid}.txt"
        if preferred.exists() and preferred not in files_by_pmcid[pmcid]:
            files_by_pmcid[pmcid].append(preferred)

    return files_by_pmcid


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
            with urllib.request.urlopen(req, timeout=120) as resp:
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
        atomic_extract_archive(
            archive,
            raw_root,
            {
                "dataset": "craft",
                "source_ref": source_ref,
                "source_url": "https://github.com/lhunter-lab/CRAFT",
                "archive_sha256": archive_sha,
            },
        )

    # License capture
    license_src = raw_root / "LICENSE.txt"
    if license_src.exists():
        licenses_dir = root / "manifests" / "licenses"
        licenses_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_src, licenses_dir / "craft_LICENSE.txt")
        readme_src = raw_root / "README.md"
        if readme_src.exists():
            shutil.copy2(readme_src, licenses_dir / "craft_README.md")

    mappings = load_craft_id_mappings(raw_root)
    found_pmcids = set(mappings["pmcids"])
    files_by_pmcid = _discover_files_by_pmcid(raw_root, mappings)

    if not found_pmcids:
        raise CRAFTError("No PMC identifiers discovered in CRAFT archive")

    split_evidence: dict[str, Any] = {}
    try:
        split_authority, split_map, split_evidence = load_craft_official_split(raw_root)
        counts = split_evidence.get("source_counts", {})
        if (
            counts.get("train", 0) + counts.get("validation", 0) != 67
            or counts.get("test", 0) != 30
        ):
            raise CRAFTError(
                "Official CRAFT split sizes invalid: "
                f"train_dev={counts.get('train', 0) + counts.get('validation', 0)} "
                f"test={counts.get('test', 0)}"
            )
    except Exception as official_exc:
        manifest_path = get_manifests_dir() / "craft_shared_task_2019_split.json"
        try:
            split_authority, split_map = load_craft_2019_shared_task_split(manifest_path)
            # Ensure manifest IDs actually belong to this corpus
            if not set(split_map).issubset(found_pmcids):
                raise CRAFTError(
                    "Package CRAFT split manifest does not match corpus PMCIDs "
                    f"(intersection={len(set(split_map) & found_pmcids)}/{len(found_pmcids)})"
                )
            split_evidence = {
                "source": str(manifest_path),
                "fallback_reason": str(official_exc),
            }
        except Exception as package_exc:
            split_authority = "custom_pmcid_level_fallback"
            split_map = stable_split(sorted(found_pmcids), seed="20260803", ratios=(80, 10, 10))
            split_evidence = {
                "source": "stable_split_fallback",
                "official_error": str(official_exc),
                "package_error": str(package_exc),
            }

    # Restrict to discovered corpus articles
    split_map = {pmcid: split for pmcid, split in split_map.items() if pmcid in found_pmcids}
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
            text_files = [p for p in pmc_files if p.suffix == ".txt" and not p.name.endswith(".copyright")]
            # Prefer articles/txt/{pmid}.txt
            pmid = mappings["pmid_by_pmcid"].get(pmcid)
            preferred = None
            if pmid:
                candidate = raw_root / "articles" / "txt" / f"{pmid}.txt"
                if candidate.exists():
                    preferred = candidate
            text_path = preferred or (text_files[0] if text_files else None)
            text_content = (
                text_path.read_text(encoding="utf-8", errors="replace")
                if text_path is not None
                else f"Article {pmcid}"
            )

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

    source_status = "VERIFIED" if split_authority == "craft_shared_task_2019" else "UNVERIFIED"
    if sum(split_counts.values()) != 97:
        source_status = "UNVERIFIED"

    return {
        "dataset": "CRAFT",
        "version": source_ref,
        "source_ref": source_ref,
        "source_status": source_status,
        "raw_path": str(raw_root),
        "processed_path": str(processed_root),
        "split_authority": split_authority,
        "split_counts": split_counts,
        "split_evidence": split_evidence,
        "license": "CC-BY-3.0",
        "native_annotation_tier": NativeAnnotationTier.HUMAN_CURATED_GOLD,
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": [{"path": str(archive.relative_to(root)), "sha256": archive_sha}],
    }
