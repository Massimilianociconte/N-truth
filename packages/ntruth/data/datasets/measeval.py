"""Handler for MeasEval dataset handling text/txt structure, trial isolation, and review-required missing TSVs."""

from __future__ import annotations

import csv
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from ntruth.data.config import DATASET_TASK_POLICIES, FORBIDDEN_NTRUTH_TARGETS, MEASEVAL_VERSION
from ntruth.data.fs import atomic_extract_archive, atomic_write_text, is_ignorable_metadata, sha256_file
from ntruth.data.schemas import (
    CommonEnvelope,
    Eligibility,
    NativeAnnotationTier,
    NTruthUsageTier,
    Provenance,
    RelationRecord,
    SourceReference,
    SpanRecord,
    SpanRelationPayload,
    SplitAssignment,
)
from ntruth.data.splits import measeval_article_id, stable_split, validate_anti_leakage

TEXT_ONLY_TRAIN_STEMS = {
    "S0019103512003995-3420",
    "S0019103512004009-2930",
    "S0022000014000026-7850",
    "S0164121213002641-2930",
    "S0167739X12001525-5094",
}


class MeasEvalError(RuntimeError):
    """MeasEval processing error."""


def _find_text_tsv_dirs(split_root: Path) -> tuple[Path, Path]:
    text_dir = split_root / "text"
    if not text_dir.exists():
        text_dir = split_root / "txt"
    tsv_dir = split_root / "tsv"

    if not text_dir.is_dir() or not tsv_dir.is_dir():
        raise MeasEvalError(f"MeasEval split lacks text/txt or tsv directory: {split_root}")
    return text_dir, tsv_dir


def _parse_tsv_annotations(tsv_path: Path) -> tuple[list[SpanRecord], list[RelationRecord]]:
    spans: list[SpanRecord] = []
    relations: list[RelationRecord] = []
    if not tsv_path.exists():
        return spans, relations

    with tsv_path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if not row or row[0].startswith("docId") or row[0].startswith("#"):
                continue
            if len(row) >= 7:
                # docId, annotSet, annotType, startOffset, endOffset, annotId, text
                annot_type = row[2]
                try:
                    start = int(row[3])
                    end = int(row[4])
                    annot_id = row[5]
                    text = row[6]
                    spans.append(SpanRecord(span_id=annot_id, label=annot_type, start=start, end=end, text=text))
                except ValueError:
                    continue
    return spans, relations


def install_measeval(root: Path, refresh: bool = False) -> dict[str, Any]:
    source_ref = MEASEVAL_VERSION
    archive_url = f"https://codeload.github.com/harperco/MeasEval/zip/{source_ref}"
    archive = root / "downloads" / f"measeval-{source_ref}.zip"
    raw_root = root / "raw" / "measeval" / source_ref
    processed_root = root / "processed" / "measeval" / source_ref

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
        atomic_extract_archive(archive, raw_root, {"dataset": "measeval", "source_ref": source_ref})

    data_root = raw_root / "data"

    # 1. Process Train -> Train (90%) and Validation (10%)
    train_text_dir, train_tsv_dir = _find_text_tsv_dirs(data_root / "train")
    train_texts = {p.stem: p for p in train_text_dir.glob("*.txt") if not is_ignorable_metadata(p)}
    train_tsvs = {p.stem: p for p in train_tsv_dir.glob("*.tsv") if not is_ignorable_metadata(p)}

    # Check for unexpected missing text files
    missing_texts = set(train_tsvs.keys()) - set(train_texts.keys())
    if missing_texts:
        raise MeasEvalError(f"MeasEval TSV files without TXT found: {sorted(missing_texts)}")

    articles = sorted(set(measeval_article_id(stem) for stem in train_texts.keys()))
    article_split_map = stable_split(articles, seed="20260803", ratios=(90, 10, 0))

    split_counts: dict[str, int] = {"train": 0, "validation": 0, "test": 0, "trial": 0}

    for stem, text_path in train_texts.items():
        article_id = measeval_article_id(stem)
        split = article_split_map[article_id]
        tsv_path = train_tsvs.get(stem)
        text_content = text_path.read_text(encoding="utf-8")

        is_missing_tsv = tsv_path is None or stem in TEXT_ONLY_TRAIN_STEMS

        if is_missing_tsv:
            native_tier = NativeAnnotationTier.MISSING_ANNOTATION
            annot_status = "missing_annotation_file"
            eligibility = Eligibility(training_eligible=False, evaluation_eligible=False, requires_review=True)
            spans, relations = [], []
        else:
            native_tier = NativeAnnotationTier.HUMAN_CURATED_GOLD
            annot_status = "annotated"
            eligibility = Eligibility(
                training_eligible=(split == "train"),
                evaluation_eligible=(split == "validation"),
                requires_review=False,
            )
            spans, relations = _parse_tsv_annotations(tsv_path)

        envelope = CommonEnvelope(
            record_id=f"measeval:{stem}",
            source=SourceReference(
                dataset="MeasEval",
                version=source_ref[:12],
                commit=source_ref,
                document_id=article_id,
                segment_id=stem,
            ),
            split=SplitAssignment(name=split, authority="official_train_article_split", group_id=article_id),
            eligibility=eligibility,
            provenance=Provenance(
                source_url="https://github.com/harperco/MeasEval",
                sha256=archive_sha,
                transform_version="1.0.0",
            ),
            native_annotation_tier=native_tier,
            ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
            allowed_tasks=DATASET_TASK_POLICIES["MeasEval"],
            forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
            annotation_status=annot_status,
            task_type="span_relation",
            payload=SpanRelationPayload(text=text_content, spans=spans, relations=relations),
        )

        out_dir = processed_root / split
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "records.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(envelope.model_dump_json() + "\n")
        split_counts[split] += 1

    # 2. Process Official Test Set (eval)
    eval_text_dir, eval_tsv_dir = _find_text_tsv_dirs(data_root / "eval")
    eval_texts = {p.stem: p for p in eval_text_dir.glob("*.txt") if not is_ignorable_metadata(p)}
    eval_tsvs = {p.stem: p for p in eval_tsv_dir.glob("*.tsv") if not is_ignorable_metadata(p)}

    out_test = processed_root / "test"
    out_test.mkdir(parents=True, exist_ok=True)

    for stem, text_path in eval_texts.items():
        article_id = measeval_article_id(stem)
        tsv_path = eval_tsvs.get(stem)
        text_content = text_path.read_text(encoding="utf-8")
        spans, relations = _parse_tsv_annotations(tsv_path) if tsv_path else ([], [])

        envelope = CommonEnvelope(
            record_id=f"measeval:{stem}",
            source=SourceReference(
                dataset="MeasEval",
                version=source_ref[:12],
                commit=source_ref,
                document_id=article_id,
                segment_id=stem,
            ),
            split=SplitAssignment(name="test", authority="upstream_official", group_id=article_id),
            eligibility=Eligibility(training_eligible=False, evaluation_eligible=True, requires_review=False),
            provenance=Provenance(
                source_url="https://github.com/harperco/MeasEval",
                sha256=archive_sha,
                transform_version="1.0.0",
            ),
            native_annotation_tier=NativeAnnotationTier.HUMAN_CURATED_GOLD,
            ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
            allowed_tasks=DATASET_TASK_POLICIES["MeasEval"],
            forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
            task_type="span_relation",
            payload=SpanRelationPayload(text=text_content, spans=spans, relations=relations),
        )

        with (out_test / "records.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(envelope.model_dump_json() + "\n")
        split_counts["test"] += 1

    # 3. Process Trial Partition (Isolated format smoke test)
    trial_text_dir, trial_tsv_dir = _find_text_tsv_dirs(data_root / "trial")
    trial_texts = {p.stem: p for p in trial_text_dir.glob("*.txt") if not is_ignorable_metadata(p)}
    trial_tsvs = {p.stem: p for p in trial_tsv_dir.glob("*.tsv") if not is_ignorable_metadata(p)}

    out_trial = processed_root / "trial"
    out_trial.mkdir(parents=True, exist_ok=True)

    for stem, text_path in trial_texts.items():
        article_id = measeval_article_id(stem)
        tsv_path = trial_tsvs.get(stem)
        text_content = text_path.read_text(encoding="utf-8")
        spans, relations = _parse_tsv_annotations(tsv_path) if tsv_path else ([], [])

        envelope = CommonEnvelope(
            record_id=f"measeval:{stem}",
            source=SourceReference(
                dataset="MeasEval",
                version=source_ref[:12],
                commit=source_ref,
                document_id=article_id,
                segment_id=stem,
            ),
            split=SplitAssignment(name="trial", authority="upstream_trial", group_id=article_id),
            eligibility=Eligibility(training_eligible=False, evaluation_eligible=False, requires_review=False),
            provenance=Provenance(
                source_url="https://github.com/harperco/MeasEval",
                sha256=archive_sha,
                transform_version="1.0.0",
            ),
            native_annotation_tier=NativeAnnotationTier.HUMAN_CURATED_PARTIAL,
            ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
            allowed_tasks=DATASET_TASK_POLICIES["MeasEval"],
            forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
            annotation_status="format_smoke_test",
            task_type="span_relation",
            payload=SpanRelationPayload(text=text_content, spans=spans, relations=relations),
        )

        with (out_trial / "records.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(envelope.model_dump_json() + "\n")
        split_counts["trial"] += 1

    return {
        "dataset": "MeasEval",
        "version": source_ref[:12],
        "source_ref": source_ref,
        "raw_path": str(raw_root),
        "processed_path": str(processed_root),
        "split_authority": "official_eval_plus_custom_train_validation",
        "split_counts": split_counts,
        "native_annotation_tier": NativeAnnotationTier.HUMAN_CURATED_GOLD,
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": [{"path": str(archive.relative_to(root)), "sha256": archive_sha}],
    }
