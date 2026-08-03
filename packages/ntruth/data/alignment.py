"""SourceData NER ↔ ROLES_MULTI join key alignment, token verification, and audit report generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class AlignmentError(RuntimeError):
    """Alignment failure between SourceData NER and ROLES_MULTI configurations."""


def _words_hash(words: list[str]) -> str:
    joint = "\0".join(words).encode("utf-8")
    return hashlib.sha256(joint).hexdigest()


def align_sourcedata_configs(
    ner_records: list[dict[str, Any]],
    roles_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aligns SourceData NER and ROLES_MULTI records 1:1 by line index with token verification.

    Returns (aligned_multitask_records, alignment_report).
    """
    total_ner = len(ner_records)
    total_roles = len(roles_records)

    aligned_multitask_records: list[dict[str, Any]] = []
    token_mismatches = 0
    split_mismatches = 0
    label_length_mismatches = 0

    min_len = min(total_ner, total_roles)
    for idx in range(min_len):
        ner_rec = ner_records[idx]
        roles_rec = roles_records[idx]

        ner_words = ner_rec.get("words", ner_rec.get("tokens", []))
        roles_words = roles_rec.get("words", roles_rec.get("tokens", []))
        ner_labels = ner_rec.get("labels", ner_rec.get("entity_tags", []))
        roles_labels = roles_rec.get("labels", roles_rec.get("role_tags", []))

        if ner_words != roles_words:
            token_mismatches += 1
            continue

        # Fail-closed: every side must have label length == token length.
        if len(ner_labels) != len(ner_words) or len(roles_labels) != len(roles_words):
            label_length_mismatches += 1
            continue

        ner_split = ner_rec.get("split")
        roles_split = roles_rec.get("split")
        if ner_split and roles_split and ner_split != roles_split:
            split_mismatches += 1
            continue

        merged_record = dict(ner_rec)
        merged_record["entity_tags"] = ner_labels
        merged_record["role_tags"] = roles_labels
        aligned_multitask_records.append(merged_record)

    unmatched_ner = (
        max(0, total_ner - min_len) + token_mismatches + split_mismatches + label_length_mismatches
    )
    unmatched_roles = (
        max(0, total_roles - min_len) + token_mismatches + split_mismatches + label_length_mismatches
    )

    # SourceData v2.0.3 token_classification JSONL exports used here have no panel_id.
    # Join is revision-bound: same physical line index in paired ner/{split}.jsonl and
    # roles_multi/{split}.jsonl at the locked HF revision, plus identical words (words_sha256).
    report = {
        "raw_ner_count": total_ner,
        "raw_roles_count": total_roles,
        "matched_count": len(aligned_multitask_records),
        "ner_only_count": unmatched_ner,
        "roles_only_count": unmatched_roles,
        "duplicate_count": 0,
        "token_mismatches": token_mismatches,
        "split_mismatches": split_mismatches,
        "label_length_mismatches": label_length_mismatches,
        "excluded_count_by_reason": {
            "token_mismatches": token_mismatches,
            "split_mismatches": split_mismatches,
            "label_length_mismatches": label_length_mismatches,
            "length_mismatch": abs(total_ner - total_roles),
        },
        "join_key": {
            "source_configuration": "token_classification/v_2.0.3",
            "upstream_split": "inherited_from_paired_file_path",
            "source_file_or_config": "ner/{split}.jsonl paired with roles_multi/{split}.jsonl",
            "source_record_index": "0-based_physical_line_index_within_split_file",
            "words_sha256": "sha256(NUL-joined words); required equal at matching indices",
            "revision_bound": True,
            "stable_across_revisions": False,
            "panel_id_field_present": False,
        },
        "join_key_note": (
            "Fail-closed on token sequence mismatch or label/token length mismatch. Not stable if a "
            "future SourceData revision reorders lines within a split file."
        ),
        "label_length_checked": True,
        "upstream_raw_split_names_preserved": True,
        "counts_are_derived_multitask": True,
    }

    return aligned_multitask_records, report
