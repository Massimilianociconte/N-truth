"""Handler for PreClinIE dataset with paper-level group-stratified splitting."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal, cast

from ntruth.data.config import DATASET_TASK_POLICIES, FORBIDDEN_NTRUTH_TARGETS, PRECLINIE_VERSION
from ntruth.data.fs import (
    atomic_extract_archive,
    atomic_write_text,
    is_ignorable_metadata,
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
from ntruth.data.source_locks import (
    ensure_pinned_archive,
    ensure_pinned_archive_verified_copy,
    load_archive_lock,
    resume_marker_matches,
    write_authenticated_resume_marker,
)
from ntruth.data.splits import preclinie_group_id, stable_split, validate_anti_leakage


class PreClinIEError(RuntimeError):
    """PreClinIE dataset error."""


def _parse_list_field(raw_value: Any, *, field_name: str) -> list[str]:
    try:
        value = ast.literal_eval(raw_value) if isinstance(raw_value, str) else raw_value
    except (SyntaxError, ValueError, TypeError) as exc:
        raise PreClinIEError(f"{field_name} is not a valid serialized list") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PreClinIEError(f"{field_name} is not a list of strings")
    return value


def _exact_normalized_content(tokens: list[str]) -> str:
    normalized = unicodedata.normalize("NFKC", " ".join(str(token) for token in tokens))
    return " ".join(normalized.casefold().split())


def _build_exact_content_families(
    parsed_rows: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, Any], dict[str, set[str]]]:
    publication_groups = sorted({str(row["publication_group"]) for row in parsed_rows})
    parent = {group_id: group_id for group_id in publication_groups}

    def find(group_id: str) -> str:
        while parent[group_id] != group_id:
            parent[group_id] = parent[parent[group_id]]
            group_id = parent[group_id]
        return group_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        lower, higher = sorted((left_root, right_root))
        parent[higher] = lower

    content_publications: dict[str, set[str]] = defaultdict(set)
    content_record_counts: dict[str, int] = defaultdict(int)
    for row in parsed_rows:
        content_key = str(row["exact_normalized_content"])
        publication_group = str(row["publication_group"])
        content_publications[content_key].add(publication_group)
        content_record_counts[content_key] += 1

    for groups in content_publications.values():
        ordered_groups = sorted(groups)
        for group_id in ordered_groups[1:]:
            union(ordered_groups[0], group_id)

    component_members: dict[str, list[str]] = defaultdict(list)
    for group_id in publication_groups:
        component_members[find(group_id)].append(group_id)

    publication_to_family: dict[str, str] = {}
    for members in component_members.values():
        ordered_members = sorted(members)
        if len(ordered_members) == 1:
            family_id = ordered_members[0]
        else:
            family_hash = hashlib.sha256("\0".join(ordered_members).encode()).hexdigest()
            family_id = f"exact_content_family:{family_hash}"
        for group_id in ordered_members:
            publication_to_family[group_id] = family_id

    duplicate_content = {
        content_key: groups
        for content_key, groups in content_publications.items()
        if content_record_counts[content_key] > 1
    }
    multi_publication_components = [
        members for members in component_members.values() if len(members) > 1
    ]
    metrics = {
        "status": "PASS",
        "policy": "EXACT_NORMALIZED_CONTENT_ONLY_NOT_SEMANTIC_EQUIVALENCE",
        "publication_group_count": len(publication_groups),
        "connected_family_count": len(component_members),
        "multi_publication_family_count": len(multi_publication_components),
        "largest_family_publication_count": max(
            (len(members) for members in component_members.values()), default=0
        ),
        "duplicate_normalized_content_count": len(duplicate_content),
        "duplicate_record_count": sum(
            content_record_counts[content_key] - 1 for content_key in duplicate_content
        ),
        "cross_split_exact_content_leakage_count": 0,
    }
    return publication_to_family, metrics, content_publications


def install_preclinie(root: Path, refresh: bool = False) -> dict[str, Any]:
    source_ref = PRECLINIE_VERSION
    archive_lock = load_archive_lock("preclinie", source_ref=source_ref)
    archive_sha = archive_lock.sha256
    archive = root / "downloads" / f"preclinie-{source_ref}.zip"
    raw_root = root / "raw" / "preclinie" / source_ref
    processed_root = root / "processed" / "preclinie" / source_ref

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

    # Discover annotation CSVs
    token_csvs = [
        p
        for p in raw_root.rglob("all_annotations_minimal_fixed_multi_tokens_tags.csv")
        if not is_ignorable_metadata(p)
    ]
    if not token_csvs:
        raise PreClinIEError("PreClinIE token CSV not found")
    token_csv = token_csvs[0]

    token_rows: list[tuple[int, dict[str, str]]] = []
    with token_csv.open("r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for csv_line_number, row in enumerate(reader, start=2):
            token_rows.append((csv_line_number, row))

    records_by_split: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    label_mismatches: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    quarantined_rows: list[dict[str, Any]] = []
    parsed_rows: list[dict[str, Any]] = []

    for csv_line_number, row in token_rows:
        doc_id = row["doc_id"]
        try:
            tokens = _parse_list_field(row.get("tokens", "[]"), field_name="tokens")
            ner_tags = _parse_list_field(row.get("ner_tags", "[]"), field_name="ner_tags")
        except PreClinIEError as exc:
            invalid = {
                "csv_line_number": csv_line_number,
                "document_id": doc_id,
                "reason": "INVALID_SERIALIZED_LIST",
                "detail": str(exc),
                "raw_tokens": row.get("tokens"),
                "raw_entity_tags": row.get("ner_tags"),
            }
            parse_errors.append(invalid)
            quarantined_rows.append(invalid)
            continue

        if len(ner_tags) != len(tokens):
            mismatch = {
                "csv_line_number": csv_line_number,
                "document_id": doc_id,
                "token_count": len(tokens),
                "entity_tag_count": len(ner_tags),
                "reason": "TOKEN_LABEL_LENGTH_MISMATCH",
            }
            label_mismatches.append(mismatch)
            quarantined_rows.append(
                {
                    **mismatch,
                    "tokens": tokens,
                    "entity_tags": ner_tags,
                }
            )
            continue

        parsed_rows.append(
            {
                "csv_line_number": csv_line_number,
                "doc_id": doc_id,
                "publication_group": preclinie_group_id(doc_id),
                "tokens": tokens,
                "ner_tags": ner_tags,
                "exact_normalized_content": _exact_normalized_content(tokens),
            }
        )

    publication_to_family, leakage_control, _content_publications = _build_exact_content_families(
        parsed_rows
    )
    unique_families = sorted(set(publication_to_family.values()))
    split_map = stable_split(unique_families, seed="20260803", ratios=(80, 10, 10))
    validate_anti_leakage(split_map)

    content_splits: dict[str, set[str]] = defaultdict(set)
    publication_splits: dict[str, str] = {}
    for parsed_row in parsed_rows:
        publication_group = str(parsed_row["publication_group"])
        family_id = publication_to_family[publication_group]
        split = split_map[family_id]
        content_splits[str(parsed_row["exact_normalized_content"])].add(split)
        publication_splits[publication_group] = split

    cross_split_exact_content_leakage_count = sum(
        1 for splits in content_splits.values() if len(splits) > 1
    )
    if cross_split_exact_content_leakage_count:
        raise PreClinIEError(
            "Exact normalized content leaked across derived splits: "
            f"{cross_split_exact_content_leakage_count} content families"
        )
    leakage_control["cross_split_exact_content_leakage_count"] = (
        cross_split_exact_content_leakage_count
    )

    for parsed_row in parsed_rows:
        doc_id = str(parsed_row["doc_id"])
        publication_group = str(parsed_row["publication_group"])
        group_id = publication_to_family[publication_group]
        split = split_map[group_id]
        tokens = parsed_row["tokens"]
        ner_tags = parsed_row["ner_tags"]

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
                name=cast(Literal["train", "validation", "test", "trial"], split),
                authority="custom_group_stratified",
                group_id=group_id,
            ),
            eligibility=Eligibility(
                training_eligible=False,
                evaluation_eligible=False,
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

    quarantine_path = root / "quarantine" / "preclinie" / source_ref / "annotation_row_issues.jsonl"
    atomic_write_text(
        quarantine_path,
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in quarantined_rows
        ),
    )
    accepted_rows = sum(split_counts.values())

    return {
        "dataset": "PreClinIE",
        "version": source_ref[:12],
        "source_ref": source_ref,
        "raw_path": str(raw_root),
        "processed_path": str(processed_root),
        # Manifest-level authority (not an upstream official train/val/test partition).
        "split_authority": "NTRUTH_GROUP_STRATIFIED_DERIVATION",
        "grouping_key": "publication_id+exact_normalized_content_family",
        "split_seed": "20260803",
        "split_algorithm": (
            "stable_split 80/10/10 over connected exact-content publication families"
        ),
        "split_counts": split_counts,
        "status": "ACQUIRED_AND_PROCESSED_NOT_TRAINING_READY",
        "split_publication_counts": {
            split: sum(1 for value in publication_splits.values() if value == split)
            for split in ("train", "validation", "test")
        },
        "split_family_counts": {
            split: sum(1 for value in split_map.values() if value == split)
            for split in ("train", "validation", "test")
        },
        "leakage_control": leakage_control,
        "model_use_status": "BLOCKED",
        "training_ready_status": "NOT_MATERIALIZED",
        "model_use_blockers": [
            "canonical_task_corpus_adapter_not_validated",
            "document_level_rights_not_adjudicated",
            "annotation_agreement_varies_by_label",
        ],
        "label_alignment": {
            "status": "PASS" if not quarantined_rows else "PARTIAL",
            "input_rows": len(token_rows),
            "accepted_rows": accepted_rows,
            "excluded_rows": len(quarantined_rows),
            "quarantine_path": str(quarantine_path.relative_to(root)),
            "mismatches": label_mismatches,
            "parse_errors": parse_errors,
        },
        "native_annotation_tier": NativeAnnotationTier.HUMAN_CURATED_GOLD,
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": [{"path": str(archive.relative_to(root)), "sha256": archive_sha}],
    }
