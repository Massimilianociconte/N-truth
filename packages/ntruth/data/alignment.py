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
    """Aligns SourceData NER and ROLES_MULTI records by (panel_id, sha256(words)).

    Returns (aligned_multitask_records, alignment_report).
    """
    ner_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    ner_duplicate_keys: set[tuple[str, str]] = set()

    for rec in ner_records:
        panel_id = str(rec.get("panel_id", rec.get("document_id", "")))
        words = rec.get("words", rec.get("tokens", []))
        w_hash = _words_hash(words)
        key = (panel_id, w_hash)
        if key in ner_by_key:
            ner_duplicate_keys.add(key)
        else:
            ner_by_key[key] = rec

    roles_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    roles_duplicate_keys: set[tuple[str, str]] = set()

    for rec in roles_records:
        panel_id = str(rec.get("panel_id", rec.get("document_id", "")))
        words = rec.get("words", rec.get("tokens", []))
        w_hash = _words_hash(words)
        key = (panel_id, w_hash)
        if key in roles_by_key:
            roles_duplicate_keys.add(key)
        else:
            roles_by_key[key] = rec

    matched_keys = sorted(set(ner_by_key.keys()) & set(roles_by_key.keys()))
    unmatched_ner_keys = sorted(set(ner_by_key.keys()) - set(roles_by_key.keys()))
    unmatched_roles_keys = sorted(set(roles_by_key.keys()) - set(ner_by_key.keys()))

    aligned_multitask_records: list[dict[str, Any]] = []
    token_mismatches = 0
    split_mismatches = 0

    for key in matched_keys:
        ner_rec = ner_by_key[key]
        roles_rec = roles_by_key[key]

        ner_words = ner_rec.get("words", ner_rec.get("tokens", []))
        roles_words = roles_rec.get("words", roles_rec.get("tokens", []))

        if ner_words != roles_words:
            token_mismatches += 1
            continue

        ner_split = ner_rec.get("split")
        roles_split = roles_rec.get("split")
        if ner_split and roles_split and ner_split != roles_split:
            split_mismatches += 1
            continue

        merged_record = dict(ner_rec)
        merged_record["entity_tags"] = ner_rec.get("labels", ner_rec.get("entity_tags", []))
        merged_record["role_tags"] = roles_rec.get("labels", roles_rec.get("role_tags", []))
        aligned_multitask_records.append(merged_record)

    report = {
        "total_ner_records": len(ner_records),
        "total_roles_records": len(roles_records),
        "unique_ner_keys": len(ner_by_key),
        "unique_roles_keys": len(roles_by_key),
        "matched_keys_count": len(matched_keys),
        "unmatched_ner_count": len(unmatched_ner_keys),
        "unmatched_roles_count": len(unmatched_roles_keys),
        "ner_duplicate_keys_count": len(ner_duplicate_keys),
        "roles_duplicate_keys_count": len(roles_duplicate_keys),
        "token_mismatches": token_mismatches,
        "split_mismatches": split_mismatches,
        "aligned_multitask_count": len(aligned_multitask_records),
        "unmatched_ner_sample": [k[0] for k in unmatched_ner_keys[:20]],
        "unmatched_roles_sample": [k[0] for k in unmatched_roles_keys[:20]],
    }

    return aligned_multitask_records, report
