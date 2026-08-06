"""Deterministic SourceData provenance sidecar builder (v1).

Generates one provenance row per canonical SourceData task record by joining
the locked upstream XML v2.0.3 caption index against the raw roles_multi text,
using the fail-closed tier rules from the merged C1.1 investigation
(:mod:`ntruth.task_corpora.provenance_join`).

Hard guarantees encoded here:
  - canonical TaskRecord JSONL is never rewritten: the sidecar is an external
    append-only mapping keyed by ``record_id``;
  - exact-text identity is hashed from the ORIGINAL UTF-8 text, never from the
    whitespace-normalized join key;
  - exact deterministic matches are evaluated before containment, and
    containment can never override an exact-tier decision;
  - no fuzzy similarity, no first-match behaviour, no invented identifiers;
  - TIER_2_ARTICLE_ONLY is never serialized as panel provenance;
  - RECORD_FALLBACK rows carry no upstream identifiers at all.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ValidationError

from ntruth.task_corpora.io_util import (
    read_jsonl_physical_lines,
    records_content_sha256,
)
from ntruth.task_corpora.provenance_join import (
    MIN_CONTAINMENT_SEGMENT_CHARS,
    JoinDecision,
    UpstreamCandidate,
    decide_provenance,
    doi_is_well_formed,
    normalize_caption,
)

SCHEMA_VERSION: Final = "0.1.0"
ALGORITHM_VERSION: Final = "0.1.0"

ProvenanceTier = Literal["TIER_1_PANEL_UNIQUE", "TIER_2_ARTICLE_ONLY", "RECORD_FALLBACK"]

PARTITIONS: Final[tuple[str, ...]] = ("train", "validation", "test")

MATCH_BASIS_EXACT_UNIQUE_PANEL: Final = "deterministic exact unique-panel assignment"
MATCH_BASIS_EXACT_SINGLE_ARTICLE: Final = "EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL"
MATCH_BASIS_CONTAINMENT_SINGLE_ARTICLE: Final = "CONTAINMENT_SINGLE_ARTICLE"


class SidecarValidationError(ValueError):
    """A sidecar row or join violates the fail-closed provenance contract."""


class SidecarRow(BaseModel):
    """One provenance row for one canonical task record (versioned schema)."""

    schema_version: str
    dataset_id: str
    dataset_version: str
    task_corpus: str
    partition: str
    source_row_index: int
    canonical_record_id: str
    exact_source_text_sha256: str
    provenance_tier: ProvenanceTier
    match_basis: str | None = None
    article_doi: str | None = None
    figure_id: str | None = None
    panel_id: str | None = None
    ambiguity_reason: str | None = None
    upstream_asset_sha256: str
    upstream_reference: str
    matching_algorithm_version: str

    def to_jsonl_bytes(self) -> bytes:
        body = json.dumps(self.model_dump(), ensure_ascii=False, sort_keys=True)
        return (body + "\n").encode("utf-8")


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- Upstream XML caption index -------------------------------------------
# Extraction and caption recovery mirror the audited C1.1 PoC
# (scripts/task_corpora/c1_1_build_upstream_index.py) exactly, so index rows
# are byte-comparable across investigation and migration.


def caption_text_from_element(el: ET.Element) -> str:
    """Recover caption text, substituting sd-tag wrappers with their text."""
    parts: list[str] = []

    def walk(node: ET.Element) -> None:
        if node.tag == "sd-tag":
            parts.append(node.get("text") or "")
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return normalize_caption("".join(parts))


def iter_upstream_captions(xml_dir: Path) -> Iterator[dict[str, str]]:
    """Yield one index row per panel/figure caption (sorted file iteration)."""
    for fp in sorted(xml_dir.glob("*.xml")):
        root = ET.parse(fp).getroot()
        doi = root.get("doi", "")
        for fig in root.iter("fig"):
            fig_id = fig.get("id", "")
            label_el = fig.find("label")
            fig_label = normalize_caption(label_el.text or "") if label_el is not None else ""
            panels = list(fig.iter("sd-panel"))
            if panels:
                for panel in panels:
                    yield {
                        "article_doi": doi,
                        "fig_id": fig_id,
                        "fig_label": fig_label,
                        "panel_id": panel.get("panel_id", ""),
                        "caption": caption_text_from_element(panel),
                    }
            else:
                yield {
                    "article_doi": doi,
                    "fig_id": fig_id,
                    "fig_label": fig_label,
                    "panel_id": "",
                    "caption": caption_text_from_element(fig),
                }


def extract_xml_archive(archive_path: Path, dest_dir: Path, *, expected_sha256: str) -> None:
    """Hash-verify then safely unpack the official XML provenance archive."""
    actual = sha256_file(archive_path)
    if actual != expected_sha256:
        raise ValueError(
            f"provenance archive sha256 mismatch: expected {expected_sha256} got {actual}"
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.endswith(".xml"):
                    continue
                name = Path(member.name).name
                if not name or name.startswith(".") or ".." in name:
                    continue
                source = tar.extractfile(member)
                if source is None:
                    continue
                (dest_dir / name).write_bytes(source.read())
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ValueError(f"unreadable provenance archive {archive_path.name}: {exc}") from exc


# --- Tier decision to sidecar fields ---------------------------------------


def decision_to_row_fields(decision: JoinDecision, *, containment_used: bool = False) -> dict:
    """Map a fail-closed JoinDecision onto sidecar row fields.

    ARTICLE-level decisions never carry panel identifiers; fallback decisions
    carry no upstream identifiers at all. A unique upstream annotation unit
    that is a whole figure (no ``sd-panel`` element upstream) keeps unique
    provenance with ``panel_id=None``: the panel identifier is absent in the
    authoritative XML path itself, so none is invented.
    """
    if decision.result == "TIER1_UNIQUE_PANEL":
        return {
            "provenance_tier": "TIER_1_PANEL_UNIQUE",
            "match_basis": MATCH_BASIS_EXACT_UNIQUE_PANEL,
            "article_doi": decision.article_doi,
            "figure_id": decision.fig_id or None,
            "panel_id": decision.panel_id or None,
            "ambiguity_reason": None,
        }
    if decision.result == "TIER2_SINGLE_DOI_ARTICLE":
        basis = (
            MATCH_BASIS_CONTAINMENT_SINGLE_ARTICLE
            if containment_used
            else MATCH_BASIS_EXACT_SINGLE_ARTICLE
        )
        return {
            "provenance_tier": "TIER_2_ARTICLE_ONLY",
            "match_basis": basis,
            "article_doi": decision.article_doi,
            "figure_id": None,
            "panel_id": None,
            "ambiguity_reason": None,
        }
    return {
        "provenance_tier": "RECORD_FALLBACK",
        "match_basis": None,
        "article_doi": None,
        "figure_id": None,
        "panel_id": None,
        "ambiguity_reason": decision.result,
    }


class _ContainmentIndex:
    """Bigram-inverted prefilter + exact substring verification.

    Produces exactly the DOI set of the audited brute-force scan
    (``key in caption``) while remaining tractable at corpus scale.
    """

    def __init__(self, captions: list[tuple[str, str]]) -> None:
        self._captions = captions
        self._bigrams: dict[str, list[int]] = {}
        for i, (_, cap) in enumerate(captions):
            for bg in {cap[j : j + 2] for j in range(len(cap) - 1)}:
                self._bigrams.setdefault(bg, []).append(i)

    def containing_dois(self, key: str) -> frozenset[str]:
        if len(key) < 2:
            return frozenset(doi for doi, cap in self._captions if key in cap)
        posts: set[int] | None = None
        for bg in {key[j : j + 2] for j in range(len(key) - 1)}:
            posting = self._bigrams.get(bg)
            if not posting:
                return frozenset()
            posts = set(posting) if posts is None else posts.intersection(posting)
            if not posts:
                return frozenset()
        assert posts is not None
        return frozenset(self._captions[i][0] for i in sorted(posts) if key in self._captions[i][1])


# --- Builder ----------------------------------------------------------------


def build_sidecar_rows(
    *,
    index_path: Path,
    raw_dir: Path,
    canon_dir: Path,
    upstream_asset_sha256: str,
    upstream_reference: str,
    dataset_id: str = "SourceData",
    dataset_version: str = "2.0.3",
    task_corpus: str = "entity_roles",
    expected_records_sha256: str | None = None,
    expected_raw_sha256: dict[str, str] | None = None,
) -> list[SidecarRow]:
    """Build one sidecar row per canonical record, fail-closed on any drift.

    Row order is deterministic: partitions in canonical order, then physical
    source row index. Canonical row ``k`` of a partition joins to raw
    roles_multi row ``k`` (verified line-count equality per partition).
    """
    exact: dict[str, list[dict[str, str]]] = {}
    captions: list[tuple[str, str]] = []
    with index_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            cap = normalize_caption(rec["caption"])
            exact.setdefault(cap, []).append(rec)
            captions.append((rec["article_doi"], cap))
    containment = _ContainmentIndex(captions)

    rows: list[SidecarRow] = []
    all_canon_lines: list[str] = []
    expected_raw = expected_raw_sha256 or {}
    for part in PARTITIONS:
        raw_path = raw_dir / f"{part}.jsonl"
        canon_path = canon_dir / f"{part}.jsonl"
        if part in expected_raw:
            actual_raw = sha256_file(raw_path)
            if actual_raw != expected_raw[part]:
                raise ValueError(
                    f"raw roles_multi {part} sha256 mismatch: "
                    f"expected {expected_raw[part]} got {actual_raw}"
                )
        raw_lines = read_jsonl_physical_lines(raw_path)
        canon_lines = read_jsonl_physical_lines(canon_path)
        if len(raw_lines) != len(canon_lines):
            raise ValueError(
                f"partition {part}: raw rows {len(raw_lines)} != canonical rows "
                f"{len(canon_lines)}; row alignment cannot be proven"
            )
        all_canon_lines.extend(canon_lines)
        for i, (raw_line, canon_line) in enumerate(zip(raw_lines, canon_lines, strict=True)):
            raw_rec = json.loads(raw_line)
            canon_rec = json.loads(canon_line)
            text = raw_rec["text"]
            key = normalize_caption(text)
            candidates = tuple(
                UpstreamCandidate(
                    article_doi=c["article_doi"],
                    fig_id=c["fig_id"],
                    panel_id=c["panel_id"],
                    caption=normalize_caption(c["caption"]),
                )
                for c in exact.get(key, ())
            )
            containing = (
                containment.containing_dois(key)
                if not candidates and len(key) >= MIN_CONTAINMENT_SEGMENT_CHARS
                else frozenset()
            )
            decision = decide_provenance(key, candidates, containing)
            fields = decision_to_row_fields(decision, containment_used=not candidates)
            rows.append(
                SidecarRow(
                    schema_version=SCHEMA_VERSION,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    task_corpus=task_corpus,
                    partition=part,
                    source_row_index=i,
                    canonical_record_id=canon_rec["record_id"],
                    exact_source_text_sha256=sha256_bytes(text.encode("utf-8")),
                    upstream_asset_sha256=upstream_asset_sha256,
                    upstream_reference=upstream_reference,
                    matching_algorithm_version=ALGORITHM_VERSION,
                    **fields,
                )
            )

    if expected_records_sha256 is not None:
        actual = records_content_sha256(all_canon_lines)
        if actual != expected_records_sha256:
            raise ValueError(
                f"canonical records_sha256 mismatch: expected {expected_records_sha256} "
                f"got {actual}"
            )
    return rows


# --- Independent validation ---------------------------------------------------


def _check_tier_rules(row: SidecarRow) -> None:
    tier = row.provenance_tier
    if tier == "TIER_1_PANEL_UNIQUE":
        if not row.article_doi or not doi_is_well_formed(row.article_doi):
            raise SidecarValidationError(f"TIER_1 row requires well-formed DOI: {row}")
        if not row.panel_id and not row.figure_id:
            raise SidecarValidationError(
                f"TIER_1 row requires an official panel_id, or a figure_id when the "
                f"authoritative XML path carries no sd-panel unit: {row}"
            )
        if row.ambiguity_reason is not None:
            raise SidecarValidationError(f"TIER_1 row cannot carry ambiguity_reason: {row}")
    elif tier == "TIER_2_ARTICLE_ONLY":
        if not row.article_doi or not doi_is_well_formed(row.article_doi):
            raise SidecarValidationError(f"TIER_2 row requires well-formed DOI: {row}")
        if row.panel_id is not None or row.figure_id is not None:
            raise SidecarValidationError(
                f"ARTICLE_ONLY must never carry panel/figure identifiers: {row}"
            )
        if row.match_basis not in {
            MATCH_BASIS_EXACT_SINGLE_ARTICLE,
            MATCH_BASIS_CONTAINMENT_SINGLE_ARTICLE,
        }:
            raise SidecarValidationError(f"TIER_2 row has invalid match_basis: {row}")
    else:  # RECORD_FALLBACK
        if row.article_doi is not None or row.figure_id is not None or row.panel_id is not None:
            raise SidecarValidationError(
                f"RECORD_FALLBACK must carry no upstream identifiers: {row}"
            )
        if not row.ambiguity_reason:
            raise SidecarValidationError(f"RECORD_FALLBACK requires ambiguity_reason: {row}")


def validate_sidecar_rows(
    payload: list[dict], *, canonical_record_ids: set[str]
) -> dict[str, object]:
    """Independent schema + contract validation of a sidecar payload."""
    rows: list[SidecarRow] = []
    for entry in payload:
        try:
            row = SidecarRow.model_validate(entry)
        except ValidationError as exc:
            raise SidecarValidationError(f"sidecar row fails schema: {exc}") from exc
        _check_tier_rules(row)
        rows.append(row)

    seen = Counter(r.canonical_record_id for r in rows)
    duplicate_keys = sum(c - 1 for c in seen.values() if c > 1)
    if duplicate_keys:
        raise SidecarValidationError(f"{duplicate_keys} duplicate sidecar keys")
    missing = canonical_record_ids - set(seen)
    extra = set(seen) - canonical_record_ids
    if missing:
        raise SidecarValidationError(f"{len(missing)} canonical records missing from sidecar")
    if extra:
        raise SidecarValidationError(f"{len(extra)} sidecar rows without canonical record")

    tier_counts = Counter(r.provenance_tier for r in rows)
    return {
        "rows": len(rows),
        "duplicate_keys": duplicate_keys,
        "missing_canonical_records": len(missing),
        "extra_sidecar_records": len(extra),
        "tier_counts": dict(tier_counts),
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
    }
