"""Recover paper / experiment / family identity only from corpus-present fields.

Internal filenames (``My_pdf*``) and conservative placeholders
(``unknown_document_scope:…``) are not scholarly paper identifiers.
Missing fields stay missing. Nothing is invented.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ntruth.data.rights import REQUIRED_IDENTITY_FIELDS, StableIdentity
from ntruth.data.schemas import CommonEnvelope

_PMC = re.compile(r"^PMC\d+$")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
# Elsevier PII: S + 16-17 chars; the check character may be a digit or X.
_PII = re.compile(r"^S[0-9Xx]{16,17}$")
_PMID_PREFIX = re.compile(r"^PMID:\s*\d{5,9}$", re.IGNORECASE)
_UNKNOWN_FAMILY = "unknown_document_scope:"


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def scholarly_paper_id(document_id: str | None) -> str | None:
    """Accept only PMCID, DOI, Elsevier PII, or PMID:N. Reject internal names."""

    text = _text(document_id)
    if text is None:
        return None
    if _PMC.fullmatch(text) or _DOI.fullmatch(text) or _PII.fullmatch(text):
        return text
    if _PMID_PREFIX.fullmatch(text):
        return f"PMID:{text.split(':', 1)[1].strip()}"
    return None


def corpus_family_id(group_id: str | None) -> str | None:
    text = _text(group_id)
    if text is None or text.startswith(_UNKNOWN_FAMILY):
        return None
    return text


def explicit_experiment_id(envelope: Mapping[str, Any] | CommonEnvelope) -> str | None:
    if isinstance(envelope, CommonEnvelope):
        payload = envelope.payload
        metadata = getattr(payload, "source_metadata", None)
        mapping: dict[str, Any] = {
            "experiment_id": None,
            "source": envelope.source.model_dump(mode="json"),
            "payload": {"source_metadata": metadata or {}},
        }
    else:
        mapping = dict(envelope)
    for candidate in (
        mapping.get("experiment_id"),
        (mapping.get("source") or {}).get("experiment_id")
        if isinstance(mapping.get("source"), Mapping)
        else None,
    ):
        found = _text(candidate)
        if found is not None:
            return found
    payload = mapping.get("payload")
    if isinstance(payload, Mapping):
        metadata = payload.get("source_metadata")
        if isinstance(metadata, Mapping):
            found = _text(metadata.get("experiment_id"))
            if found is not None:
                return found
    return None


def extract_stable_identity(
    envelope: Mapping[str, Any] | CommonEnvelope,
    *,
    source_asset_id: str,
    source_ref: str,
) -> StableIdentity:
    if isinstance(envelope, CommonEnvelope):
        document_id = envelope.source.document_id
        group_id = envelope.split.group_id
        source_name = envelope.source.dataset
    else:
        source = envelope.get("source") if isinstance(envelope.get("source"), Mapping) else {}
        split = envelope.get("split") if isinstance(envelope.get("split"), Mapping) else {}
        document_id = source.get("document_id") if isinstance(source, Mapping) else None
        group_id = split.get("group_id") if isinstance(split, Mapping) else None
        source_name = source.get("dataset") if isinstance(source, Mapping) else None
    paper = scholarly_paper_id(document_id if isinstance(document_id, str) else None)
    family = corpus_family_id(group_id if isinstance(group_id, str) else None)
    experiment = explicit_experiment_id(envelope)
    asset = _text(source_asset_id) or (
        _text(source_name) if isinstance(source_name, str) else None
    ) or "unknown-asset"
    return StableIdentity(
        paper_id=paper,
        experiment_id=experiment,
        family_id=family,
        source_asset_id=asset,
        source_ref=source_ref,
    )


def identity_as_mapping(identity: StableIdentity) -> dict[str, str | None]:
    return {
        field: getattr(identity, field)
        for field in (*REQUIRED_IDENTITY_FIELDS, "source_asset_id", "source_ref")
    }
