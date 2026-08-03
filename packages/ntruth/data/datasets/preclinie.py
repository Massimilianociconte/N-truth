"""Handler for PreClinIE dataset with paper-level group-stratified splitting."""

from __future__ import annotations

import ast
import csv
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from ntruth.data.config import DATASET_TASK_POLICIES, FORBIDDEN_NTRUTH_TARGETS, PRECLINIE_VERSION
from ntruth.data.fs import (
    atomic_extract_archive,
    atomic_write_text,
    is_ignorable_metadata,
    sha256_file,
)
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
from ntruth.data.splits import preclinie_group_id, stable_split, validate_anti_leakage


class PreClinIEError(RuntimeError):
    """PreClinIE dataset error."""


def install_preclinie(root: Path, refresh: bool = False) -> dict[str, Any]:
    source_ref = PRECLINIE_VERSION
    archive_url = (
        f"https://codeload.github.com/Ineichen-Group/Preclinical_IE_Dataset/zip/{source_ref}"
    )
    archive = root / "downloads" / f"preclinie-{source_ref}.zip"
    raw_root = root / "raw" / "preclinie" / source_ref
    processed_root = root / "processed" / "preclinie" / source_ref

    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() or refresh:
        req = urllib.request.Request(archive_url, headers={"User-Agent": "NTruthDataInstaller/1.0"})
        partial = archive.with_name(archive.name + ".part")
        with urllib.request.urlopen(req, timeout=60) as resp:
            partial.write_bytes(resp.read())
        os.replace(partial, archive)

    archive_sha = sha256_file(archive)
    marker = raw_root / ".ntruth_complete.json"
    if not marker.exists() or refresh:
        atomic_extract_archive(
            archive, raw_root, {"dataset": "preclinie", "source_ref": source_ref}
        )

    # Discover annotation CSVs
    token_csvs = [
        p
        for p in raw_root.rglob("all_annotations_minimal_fixed_multi_tokens_tags.csv")
        if not is_ignorable_metadata(p)
    ]
    if not token_csvs:
        raise PreClinIEError("PreClinIE token CSV not found")
    token_csv = token_csvs[0]

    token_rows: list[dict[str, str]] = []
    with token_csv.open("r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            token_rows.append(row)

    doc_ids = sorted(set(row["doc_id"] for row in token_rows if "doc_id" in row))
    groups = {doc_id: preclinie_group_id(doc_id) for doc_id in doc_ids}
    unique_groups = sorted(set(groups.values()))

    split_map = stable_split(unique_groups, seed="20260803", ratios=(80, 10, 10))
    validate_anti_leakage(split_map)

    records_by_split: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}

    for row in token_rows:
        doc_id = row["doc_id"]
        group_id = groups[doc_id]
        split = split_map[group_id]

        raw_tokens = row.get("tokens", "[]")
        raw_ner_tags = row.get("ner_tags", "[]")
        try:
            tokens = (
                ast.literal_eval(raw_tokens)
                if isinstance(raw_tokens, str) and raw_tokens.startswith("[")
                else raw_tokens
            )
        except Exception:
            tokens = [t.strip("'\" ") for t in raw_tokens.strip("[]").split(",")]

        try:
            ner_tags = (
                ast.literal_eval(raw_ner_tags)
                if isinstance(raw_ner_tags, str) and raw_ner_tags.startswith("[")
                else raw_ner_tags
            )
        except Exception:
            ner_tags = [t.strip("'\" ") for t in raw_ner_tags.strip("[]").split(",")]

        if not isinstance(tokens, list):
            tokens = [str(tokens)]
        if not isinstance(ner_tags, list):
            ner_tags = [str(ner_tags)]

        # Ensure exact matching length for tokens and entity_tags
        if len(ner_tags) < len(tokens):
            ner_tags = ner_tags + ["O"] * (len(tokens) - len(ner_tags))
        elif len(ner_tags) > len(tokens):
            ner_tags = ner_tags[: len(tokens)]

        normalized_text = " ".join(tokens)
        offsets = []
        curr = 0
        for t in tokens:
            offsets.append((curr, curr + len(t)))
            curr += len(t) + 1

        envelope = CommonEnvelope(
            record_id=f"preclinie:{doc_id}",
            source=SourceReference(
                dataset="PreClinIE",
                version=source_ref[:12],
                commit=source_ref,
                document_id=doc_id,
                segment_id=doc_id,
            ),
            split=SplitAssignment(
                name=split, authority="custom_group_stratified", group_id=group_id
            ),
            eligibility=Eligibility(
                training_eligible=(split == "train"),
                evaluation_eligible=(split in {"validation", "test"}),
                requires_review=False,
            ),
            provenance=Provenance(
                source_url="https://github.com/Ineichen-Group/Preclinical_IE_Dataset",
                sha256=archive_sha,
                transform_version="1.0.0",
            ),
            native_annotation_tier=NativeAnnotationTier.HUMAN_CURATED_GOLD,
            ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
            allowed_tasks=DATASET_TASK_POLICIES["PreClinIE"],
            forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
            task_type="token_classification",
            payload=TokenClassificationPayload(
                tokens=tokens,
                token_offsets=offsets,
                offset_authority=OffsetAuthority.DERIVED_NORMALIZED_TEXT,
                normalized_text=normalized_text,
                entity_tags=ner_tags,
                role_tags=None,
            ),
        )
        records_by_split[split].append(envelope.model_dump())

    split_counts: dict[str, int] = {}
    for split in ("train", "validation", "test"):
        out_dir = processed_root / split
        out_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
            for r in records_by_split[split]
        ]
        atomic_write_text(out_dir / "records.jsonl", "".join(lines))
        split_counts[split] = len(records_by_split[split])

    return {
        "dataset": "PreClinIE",
        "version": source_ref[:12],
        "source_ref": source_ref,
        "raw_path": str(raw_root),
        "processed_path": str(processed_root),
        # Manifest-level authority (not an upstream official train/val/test partition).
        "split_authority": "NTRUTH_GROUP_STRATIFIED_DERIVATION",
        "grouping_key": "publication_id",
        "split_seed": "20260803",
        "split_algorithm": "stable_split group-stratified 80/10/10 over publication groups",
        "split_counts": split_counts,
        "native_annotation_tier": NativeAnnotationTier.HUMAN_CURATED_GOLD,
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": [{"path": str(archive.relative_to(root)), "sha256": archive_sha}],
    }
