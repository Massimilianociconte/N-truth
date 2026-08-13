"""MeasEval acquisition with family-safe splits and traceable upstream partitions."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, cast

from ntruth.data.config import DATASET_TASK_POLICIES, FORBIDDEN_NTRUTH_TARGETS, MEASEVAL_VERSION
from ntruth.data.fs import (
    atomic_extract_archive,
    atomic_write_json,
    atomic_write_text,
    is_ignorable_metadata,
)
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
from ntruth.data.source_locks import (
    ensure_pinned_archive,
    ensure_pinned_archive_verified_copy,
    load_archive_lock,
    resume_marker_matches,
    write_authenticated_resume_marker,
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


def _ntruth_split_assignment(split: str, article_id: str) -> SplitAssignment:
    return SplitAssignment(
        name=cast(Literal["train", "validation", "test", "trial"], split),
        authority="ntruth_measeval_article_family_v1",
        group_id=article_id,
    )


def _build_ntruth_article_family_split(
    *,
    train_stems: set[str],
    eval_stems: set[str],
    trial_stems: set[str],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Reconcile upstream partitions into one leakage-safe N-Truth family split."""
    source_articles = {
        "train": {measeval_article_id(stem) for stem in train_stems},
        "eval": {measeval_article_id(stem) for stem in eval_stems},
        "trial": {measeval_article_id(stem) for stem in trial_stems},
    }
    protected_test_articles = source_articles["eval"] | source_articles["trial"]
    development_articles = sorted(source_articles["train"] - protected_test_articles)
    split_map = stable_split(development_articles, seed="20260803", ratios=(90, 10, 0))
    split_map.update({article_id: "test" for article_id in protected_test_articles})
    validate_anti_leakage(split_map)

    overlap_pairs: dict[str, dict[str, Any]] = {}
    overlap_union: set[str] = set()
    for left, right in (("train", "eval"), ("train", "trial"), ("eval", "trial")):
        overlap_ids = sorted(source_articles[left] & source_articles[right])
        overlap_union.update(overlap_ids)
        overlap_pairs[f"{left}_{right}"] = {
            "count": len(overlap_ids),
            "article_ids": overlap_ids,
        }

    source_partition_to_ntruth_split_counts: dict[str, dict[str, int]] = {}
    stems_by_partition = {
        "train": train_stems,
        "eval": eval_stems,
        "trial": trial_stems,
    }
    for source_partition, stems in stems_by_partition.items():
        counts = {"train": 0, "validation": 0, "test": 0}
        for stem in stems:
            counts[split_map[measeval_article_id(stem)]] += 1
        source_partition_to_ntruth_split_counts[source_partition] = counts

    return split_map, {
        "authority": "ntruth_measeval_article_family_v1",
        "seed": "20260803",
        "development_ratios": {"train": 90, "validation": 10, "test": 0},
        "protected_test_policy": {
            "official_eval_families": True,
            "upstream_trial_families": True,
            "trial_records_format_smoke_only": True,
        },
        "trial_format_smoke_only_record_count": len(trial_stems),
        "trial_model_eligible_record_count": 0,
        "source_partition_counts": {
            partition: len(stems) for partition, stems in stems_by_partition.items()
        },
        "source_article_family_counts": {
            partition: len(article_ids) for partition, article_ids in source_articles.items()
        },
        "source_partition_to_ntruth_split_counts": source_partition_to_ntruth_split_counts,
        "ntruth_split_article_family_counts": {
            split_name: sum(assigned == split_name for assigned in split_map.values())
            for split_name in ("train", "validation", "test")
        },
        "upstream_article_overlap": {
            "has_overlap": bool(overlap_union),
            "cross_partition_family_count": len(overlap_union),
            "pairs": overlap_pairs,
        },
        "model_development_group_leakage_count": 0,
    }


def _find_text_tsv_dirs(split_root: Path) -> tuple[Path, Path]:
    text_dir = split_root / "text"
    if not text_dir.exists():
        text_dir = split_root / "txt"
    tsv_dir = split_root / "tsv"

    if not text_dir.is_dir() or not tsv_dir.is_dir():
        raise MeasEvalError(f"MeasEval split lacks text/txt or tsv directory: {split_root}")
    return text_dir, tsv_dir


def _parse_tsv_annotations(
    tsv_path: Path, *, document_text: str
) -> tuple[list[SpanRecord], list[RelationRecord]]:
    spans: list[SpanRecord] = []
    relations: list[RelationRecord] = []
    if not tsv_path.exists():
        return spans, relations

    parsed_rows: list[tuple[str, dict[str, Any]]] = []
    with tsv_path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, row in enumerate(reader, start=1):
            if not row or row[0].startswith("docId") or row[0].startswith("#"):
                continue
            if len(row) < 8:
                raise MeasEvalError(
                    f"Malformed MeasEval TSV row at {tsv_path}:{line_number}: expected 8 columns"
                )
            try:
                start = int(row[3])
                end = int(row[4])
                metadata = json.loads(row[7]) if row[7].strip() else {}
            except (ValueError, json.JSONDecodeError) as exc:
                raise MeasEvalError(
                    f"Malformed MeasEval TSV row at {tsv_path}:{line_number}"
                ) from exc
            if not isinstance(metadata, dict):
                raise MeasEvalError(f"Malformed MeasEval TSV metadata at {tsv_path}:{line_number}")
            annot_id = row[5]
            annotated_text = row[6]
            if start < 0 or end <= start or end > len(document_text):
                raise MeasEvalError(
                    f"MeasEval invalid span offsets at {tsv_path}:{line_number}: "
                    f"start={start}, end={end}, document_length={len(document_text)}"
                )
            document_slice = document_text[start:end]
            if document_slice != annotated_text:
                raise MeasEvalError(
                    f"MeasEval span text does not match document text at "
                    f"{tsv_path}:{line_number}: annotated={annotated_text!r}, "
                    f"document_slice={document_slice!r}"
                )
            spans.append(
                SpanRecord(
                    span_id=annot_id,
                    label=row[2],
                    start=start,
                    end=end,
                    text=annotated_text,
                    source_metadata={
                        "annotation_set": row[1],
                        "attributes": metadata,
                    },
                )
            )
            parsed_rows.append((annot_id, metadata))

    span_ids = {span.span_id for span in spans}
    relation_keys = {"HasQuantity", "HasProperty", "Qualifies"}
    for source_span_id, metadata in parsed_rows:
        for relation_type, target_span_id in metadata.items():
            if relation_type not in relation_keys:
                continue
            if not isinstance(target_span_id, str) or target_span_id not in span_ids:
                raise MeasEvalError(
                    f"MeasEval relation from {source_span_id} has unknown target span "
                    f"{target_span_id!r} in {tsv_path}"
                )
            relations.append(
                RelationRecord(
                    relation_id=f"R{len(relations) + 1}",
                    source_span_id=source_span_id,
                    target_span_id=target_span_id,
                    relation_type=relation_type,
                )
            )
    return spans, relations


def _partition_inventory(
    text_dir: Path, tsv_dir: Path
) -> tuple[dict[str, Path], dict[str, Path], dict[str, Any]]:
    texts = {p.stem: p for p in text_dir.glob("*.txt") if not is_ignorable_metadata(p)}
    tsvs = {p.stem: p for p in tsv_dir.glob("*.tsv") if not is_ignorable_metadata(p)}
    orphan_tsvs = sorted(set(tsvs) - set(texts))
    if orphan_tsvs:
        raise MeasEvalError(f"MeasEval TSV files without TXT found: {orphan_tsvs}")
    missing_tsvs = sorted(set(texts) - set(tsvs))
    return (
        texts,
        tsvs,
        {
            "text_count": len(texts),
            "tsv_count": len(tsvs),
            "missing_tsv_count": len(missing_tsvs),
            "missing_tsv_document_ids": missing_tsvs,
        },
    )


def discover_measeval_partition(split_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Discover documents in a MeasEval partition and flag missing TSVs per document."""
    text_dir, tsv_dir = _find_text_tsv_dirs(split_root)
    texts = {p.stem: p for p in text_dir.glob("*.txt") if not is_ignorable_metadata(p)}
    tsvs = {p.stem: p for p in tsv_dir.glob("*.tsv") if not is_ignorable_metadata(p)}

    documents: dict[str, Any] = {}
    missing: list[str] = []
    for stem in sorted(texts):
        # TEXT_ONLY stems are known missing; also any txt without tsv
        is_missing = (stem not in tsvs) or (stem in TEXT_ONLY_TRAIN_STEMS)
        if is_missing:
            missing.append(stem)
            documents[stem] = type(
                "Doc",
                (),
                {
                    "native_annotation_tier": NativeAnnotationTier.MISSING_ANNOTATION,
                    "requires_review": True,
                },
            )()
        else:
            documents[stem] = type(
                "Doc",
                (),
                {
                    "native_annotation_tier": NativeAnnotationTier.HUMAN_CURATED_GOLD,
                    "requires_review": False,
                },
            )()
    report = {"missing_tsv_document_ids": missing}
    return documents, report


def install_measeval(root: Path, refresh: bool = False) -> dict[str, Any]:
    source_ref = MEASEVAL_VERSION
    archive_lock = load_archive_lock("measeval", source_ref=source_ref)
    archive_sha = archive_lock.sha256
    archive = root / "downloads" / f"measeval-{source_ref}.zip"
    raw_root = root / "raw" / "measeval" / source_ref
    processed_root = root / "processed" / "measeval" / source_ref

    marker = raw_root / ".ntruth_complete.json"
    if refresh or not resume_marker_matches(marker, archive_lock):
        with ensure_pinned_archive_verified_copy(
            archive, archive_lock, refresh=refresh, root=root
        ) as verified_archive:
            atomic_extract_archive(
                verified_archive,
                raw_root,
                {"dataset": archive_lock.marker_dataset, "source_ref": archive_lock.source_ref},
                trusted_root=root,
            )
        write_authenticated_resume_marker(raw_root, archive_lock)
    else:
        ensure_pinned_archive(archive, archive_lock, refresh=False, root=root)

    data_root = raw_root / "data"

    # Collect records in memory then write atomically (idempotent overwrite).
    records_by_split: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    source_partition_assignments: list[dict[str, str]] = []

    # Reconcile every upstream partition before any record is serialized.
    train_text_dir, train_tsv_dir = _find_text_tsv_dirs(data_root / "train")
    train_texts, train_tsvs, train_inventory = _partition_inventory(train_text_dir, train_tsv_dir)

    eval_text_dir, eval_tsv_dir = _find_text_tsv_dirs(data_root / "eval")
    eval_texts, eval_tsvs, eval_inventory = _partition_inventory(eval_text_dir, eval_tsv_dir)
    trial_text_dir, trial_tsv_dir = _find_text_tsv_dirs(data_root / "trial")
    trial_texts, trial_tsvs, trial_inventory = _partition_inventory(trial_text_dir, trial_tsv_dir)
    article_split_map, split_reconciliation = _build_ntruth_article_family_split(
        train_stems=set(train_texts),
        eval_stems=set(eval_texts),
        trial_stems=set(trial_texts),
    )

    legacy_trial_path = processed_root / "trial"
    legacy_trial_quarantine = (
        root / "quarantine" / "processed" / "measeval" / source_ref / "legacy-upstream-trial-split"
    )
    legacy_processed_trial_quarantined_to: str | None = (
        str(legacy_trial_quarantine) if legacy_trial_quarantine.exists() else None
    )
    if legacy_trial_path.exists():
        if legacy_trial_quarantine.exists():
            raise MeasEvalError(
                "Cannot quarantine the legacy MeasEval trial split because the destination "
                f"already exists: {legacy_trial_quarantine}"
            )
        legacy_trial_quarantine.parent.mkdir(parents=True, exist_ok=True)
        legacy_trial_path.replace(legacy_trial_quarantine)
        legacy_processed_trial_quarantined_to = str(legacy_trial_quarantine)

    for stem in sorted(train_texts.keys()):
        text_path = train_texts[stem]
        article_id = measeval_article_id(stem)
        split = article_split_map[article_id]
        source_partition_assignments.append(
            {
                "segment_id": stem,
                "article_family_id": article_id,
                "source_partition": "train",
                "ntruth_split": split,
            }
        )
        tsv_path = train_tsvs.get(stem)
        text_content = text_path.read_text(encoding="utf-8")

        is_missing_tsv = tsv_path is None

        if is_missing_tsv:
            native_tier = NativeAnnotationTier.MISSING_ANNOTATION
            annot_status = "missing_annotation_file"
            eligibility = Eligibility(
                training_eligible=False, evaluation_eligible=False, requires_review=True
            )
            train_spans: list[SpanRecord] = []
            train_relations: list[RelationRecord] = []
        else:
            native_tier = NativeAnnotationTier.HUMAN_CURATED_GOLD
            annot_status = "annotated"
            eligibility = Eligibility(
                training_eligible=False, evaluation_eligible=False, requires_review=False
            )
            assert tsv_path is not None
            train_spans, train_relations = _parse_tsv_annotations(
                tsv_path, document_text=text_content
            )

        envelope = CommonEnvelope(
            record_id=f"measeval:{stem}",
            source=SourceReference(
                dataset="MeasEval",
                version=source_ref[:12],
                commit=source_ref,
                document_id=article_id,
                segment_id=stem,
            ),
            split=_ntruth_split_assignment(split, article_id),
            eligibility=eligibility,
            provenance=Provenance(
                source_url="https://github.com/harperco/MeasEval",
                sha256=archive_sha,
                transform_version="2.1.0",
            ),
            native_annotation_tier=native_tier,
            ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
            allowed_tasks=DATASET_TASK_POLICIES["MeasEval"],
            forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
            annotation_status=annot_status,
            task_type="span_relation",
            payload=SpanRelationPayload(
                text=text_content,
                spans=train_spans,
                relations=train_relations,
            ),
        )
        records_by_split[split].append(envelope.model_dump_json())

    # Preserve the official eval source partition, while using the family-safe role.
    for stem in sorted(eval_texts.keys()):
        text_path = eval_texts[stem]
        article_id = measeval_article_id(stem)
        split = article_split_map[article_id]
        source_partition_assignments.append(
            {
                "segment_id": stem,
                "article_family_id": article_id,
                "source_partition": "eval",
                "ntruth_split": split,
            }
        )
        tsv_path = eval_tsvs.get(stem)
        text_content = text_path.read_text(encoding="utf-8")
        is_missing_tsv = tsv_path is None
        if is_missing_tsv:
            native_tier = NativeAnnotationTier.MISSING_ANNOTATION
            annot_status = "missing_annotation_file"
            eligibility = Eligibility(
                training_eligible=False, evaluation_eligible=False, requires_review=True
            )
            eval_spans: list[SpanRecord] = []
            eval_relations: list[RelationRecord] = []
        else:
            native_tier = NativeAnnotationTier.HUMAN_CURATED_GOLD
            annot_status = "annotated"
            eligibility = Eligibility(
                training_eligible=False, evaluation_eligible=False, requires_review=False
            )
            assert tsv_path is not None
            eval_spans, eval_relations = _parse_tsv_annotations(
                tsv_path, document_text=text_content
            )

        envelope = CommonEnvelope(
            record_id=f"measeval:{stem}",
            source=SourceReference(
                dataset="MeasEval",
                version=source_ref[:12],
                commit=source_ref,
                document_id=article_id,
                segment_id=stem,
            ),
            split=_ntruth_split_assignment(split, article_id),
            eligibility=eligibility,
            provenance=Provenance(
                source_url="https://github.com/harperco/MeasEval",
                sha256=archive_sha,
                transform_version="2.1.0",
            ),
            native_annotation_tier=native_tier,
            ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
            allowed_tasks=DATASET_TASK_POLICIES["MeasEval"],
            forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
            annotation_status=annot_status,
            task_type="span_relation",
            payload=SpanRelationPayload(
                text=text_content,
                spans=eval_spans,
                relations=eval_relations,
            ),
        )
        records_by_split[split].append(envelope.model_dump_json())

    # Trial remains format-smoke-only; its families use the protected N-Truth role.
    for stem in sorted(trial_texts.keys()):
        text_path = trial_texts[stem]
        article_id = measeval_article_id(stem)
        split = article_split_map[article_id]
        source_partition_assignments.append(
            {
                "segment_id": stem,
                "article_family_id": article_id,
                "source_partition": "trial",
                "ntruth_split": split,
            }
        )
        tsv_path = trial_tsvs.get(stem)
        text_content = text_path.read_text(encoding="utf-8")
        spans, relations = (
            _parse_tsv_annotations(tsv_path, document_text=text_content) if tsv_path else ([], [])
        )

        envelope = CommonEnvelope(
            record_id=f"measeval:{stem}",
            source=SourceReference(
                dataset="MeasEval",
                version=source_ref[:12],
                commit=source_ref,
                document_id=article_id,
                segment_id=stem,
            ),
            split=_ntruth_split_assignment(split, article_id),
            eligibility=Eligibility(
                training_eligible=False, evaluation_eligible=False, requires_review=False
            ),
            provenance=Provenance(
                source_url="https://github.com/harperco/MeasEval",
                sha256=archive_sha,
                transform_version="2.1.0",
            ),
            native_annotation_tier=NativeAnnotationTier.HUMAN_CURATED_PARTIAL,
            ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
            allowed_tasks=DATASET_TASK_POLICIES["MeasEval"],
            forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
            annotation_status="format_smoke_test",
            task_type="span_relation",
            payload=SpanRelationPayload(text=text_content, spans=spans, relations=relations),
        )
        records_by_split[split].append(envelope.model_dump_json())

    split_counts: dict[str, int] = {}
    for split, lines in records_by_split.items():
        out_dir = processed_root / split
        out_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out_dir / "records.jsonl", "".join(line + "\n" for line in lines))
        split_counts[split] = len(lines)

    assignment_text = "".join(
        json.dumps(assignment, sort_keys=True, separators=(",", ":")) + "\n"
        for assignment in sorted(
            source_partition_assignments,
            key=lambda item: (item["source_partition"], item["segment_id"]),
        )
    )
    assignment_path = processed_root / "source_partition_assignments.jsonl"
    atomic_write_text(assignment_path, assignment_text)
    assignment_sha256 = hashlib.sha256(assignment_text.encode("utf-8")).hexdigest()
    reconciliation_document = {
        **split_reconciliation,
        "source_ref": source_ref,
        "assignment_manifest": {
            "path": assignment_path.name,
            "sha256": assignment_sha256,
            "record_count": len(source_partition_assignments),
        },
    }
    reconciliation_path = processed_root / "split_reconciliation.json"
    atomic_write_json(reconciliation_path, reconciliation_document)

    official_eval_articles = {measeval_article_id(stem) for stem in eval_texts}
    trial_articles = {measeval_article_id(stem) for stem in trial_texts}
    upstream_train_articles = {measeval_article_id(stem) for stem in train_texts}
    initial_development_map = stable_split(
        sorted(upstream_train_articles), seed="20260803", ratios=(90, 10, 0)
    )
    train_articles = {
        article_id
        for article_id, split_name in initial_development_map.items()
        if split_name == "train"
    }
    validation_articles = {
        article_id
        for article_id, split_name in initial_development_map.items()
        if split_name == "validation"
    }
    article_sets = {
        "train": train_articles,
        "validation": validation_articles,
        "test": official_eval_articles,
        "trial": trial_articles,
    }
    overlap_pairs: dict[str, dict[str, Any]] = {}
    for left, right in (
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
        ("train", "trial"),
        ("validation", "trial"),
        ("test", "trial"),
    ):
        overlap_ids = sorted(article_sets[left] & article_sets[right])
        overlap_pairs[f"{left}_{right}"] = {
            "count": len(overlap_ids),
            "article_ids": overlap_ids,
        }
    has_article_overlap = any(pair["count"] for pair in overlap_pairs.values())
    article_overlap = {
        "has_overlap": has_article_overlap,
        "pairs": overlap_pairs,
    }

    training_ready_path = root / "training_ready" / "measeval" / source_ref
    training_ready_quarantine = root / "quarantine" / "training_ready" / "measeval" / source_ref
    stale_training_ready_quarantined_to: str | None = (
        str(training_ready_quarantine) if training_ready_quarantine.exists() else None
    )
    if training_ready_path.exists():
        if training_ready_quarantine.exists():
            raise MeasEvalError(
                "Cannot quarantine stale MeasEval training export because the destination "
                f"already exists: {training_ready_quarantine}"
            )
        training_ready_quarantine.parent.mkdir(parents=True, exist_ok=True)
        training_ready_path.replace(training_ready_quarantine)
        stale_training_ready_quarantined_to = str(training_ready_quarantine)

    model_use_blockers = [
        "canonical_task_corpus_adapter_not_validated",
        "license_training_use_not_adjudicated",
    ]
    return {
        "dataset": "MeasEval",
        "version": source_ref[:12],
        "source_ref": source_ref,
        "raw_path": str(raw_root),
        "processed_path": str(processed_root),
        "split_authority": "ntruth_measeval_article_family_v1",
        "split_counts": split_counts,
        "split_reconciliation": split_reconciliation,
        "source_partition_assignment_manifest": {
            "path": str(assignment_path),
            "sha256": assignment_sha256,
            "record_count": len(source_partition_assignments),
        },
        "split_reconciliation_manifest": {
            "path": str(reconciliation_path),
            "sha256": hashlib.sha256(reconciliation_path.read_bytes()).hexdigest(),
        },
        "status": "ACQUIRED_AND_PROCESSED_NOT_TRAINING_READY",
        "training_ready_status": "BLOCKED_BY_MODEL_USE_GATES",
        "training_ready_present": False,
        "stale_training_ready_quarantined_to": stale_training_ready_quarantined_to,
        "legacy_processed_trial_quarantined_to": legacy_processed_trial_quarantined_to,
        "model_use_status": "BLOCKED",
        "model_use_blockers": model_use_blockers,
        "article_overlap": article_overlap,
        "annotation_integrity": {
            "train": train_inventory,
            "eval": eval_inventory,
            "trial": trial_inventory,
        },
        "semantic_preservation": {
            "unit_and_mods": "payload.spans[].source_metadata.attributes",
            "upstream_relation_attributes": "payload.spans[].source_metadata.attributes",
            "normalized_relations": "payload.relations",
            "span_offsets": "validated_against_payload.text",
            "metadata_values": "preserved_without_label_inference",
        },
        "native_annotation_tier_counts": {
            NativeAnnotationTier.HUMAN_CURATED_GOLD: (
                train_inventory["tsv_count"] + eval_inventory["tsv_count"]
            ),
            NativeAnnotationTier.HUMAN_CURATED_PARTIAL: trial_inventory["text_count"],
            NativeAnnotationTier.MISSING_ANNOTATION: (
                train_inventory["missing_tsv_count"] + eval_inventory["missing_tsv_count"]
            ),
        },
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": [{"path": str(archive.relative_to(root)), "sha256": archive_sha}],
    }
