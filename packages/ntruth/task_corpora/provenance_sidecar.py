"""Deterministic SourceData provenance sidecar builder (schema v0.2.0).

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
  - unique panel-granularity units and unique whole-figure units (upstream
    figures with no ``sd-panel`` child) are reported as separate tiers and are
    never conflated;
  - TIER_2_ARTICLE_ONLY is never serialized as panel or figure provenance;
  - RECORD_FALLBACK rows carry no upstream identifiers at all.

Schema v0.2.0 changes over v0.1.0 (C1.1 erratum): the 175 authoritative
whole-figure XML units are split out of ``TIER_1_PANEL_UNIQUE`` into
``TIER_1_FIGURE_UNIQUE``; SidecarRow is strict (``extra="forbid"``) with
cross-field tier validation; archive extraction is hardened against hostile
member payloads.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

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

SCHEMA_VERSION: Final = "0.2.0"
ALGORITHM_VERSION: Final = "0.2.0"

ProvenanceTier = Literal[
    "TIER_1_PANEL_UNIQUE",
    "TIER_1_FIGURE_UNIQUE",
    "TIER_2_ARTICLE_ONLY",
    "RECORD_FALLBACK",
]
ProvenanceGranularity = Literal["PANEL", "FIGURE", "ARTICLE", "RECORD_FALLBACK"]

PARTITIONS: Final[tuple[Literal["train", "validation", "test"], ...]] = (
    "train",
    "validation",
    "test",
)

MATCH_BASIS_EXACT_UNIQUE_PANEL: Final = "deterministic exact unique-panel assignment"
MATCH_BASIS_EXACT_UNIQUE_FIGURE: Final = "deterministic exact unique-figure assignment"
MATCH_BASIS_EXACT_SINGLE_ARTICLE: Final = "EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL"
MATCH_BASIS_CONTAINMENT_SINGLE_ARTICLE: Final = "CONTAINMENT_SINGLE_ARTICLE"

_SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}\Z")

# Extraction safety quotas (configurable per call).
DEFAULT_MAX_FILES: Final = 20_000
DEFAULT_MAX_FILE_BYTES: Final = 50 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES: Final = 5 * 1024 * 1024 * 1024


class SidecarValidationError(ValueError):
    """A sidecar row or join violates the fail-closed provenance contract."""


class SidecarRow(BaseModel):
    """One provenance row for one canonical task record (strict schema 0.2.0)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2.0"]
    dataset_id: Literal["SourceData"]
    dataset_version: Literal["2.0.3"]
    task_corpus: Literal["entity_roles"]
    partition: Literal["train", "validation", "test"]
    source_row_index: int
    canonical_record_id: str
    exact_source_text_sha256: str
    provenance_tier: ProvenanceTier
    granularity: ProvenanceGranularity
    match_basis: str | None = None
    article_doi: str | None = None
    figure_id: str | None = None
    panel_id: str | None = None
    ambiguity_reason: str | None = None
    upstream_asset_sha256: str
    upstream_reference: str
    matching_algorithm_version: Literal["0.2.0"]

    @field_validator("source_row_index")
    @classmethod
    def row_index_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("source_row_index must be >= 0")
        return value

    @field_validator("canonical_record_id", "upstream_reference")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("value must be non-empty")
        return value

    @field_validator("exact_source_text_sha256", "upstream_asset_sha256")
    @classmethod
    def lowercase_hex_sha256(cls, value: str) -> str:
        if not _SHA256_HEX.match(value):
            raise ValueError("must be lowercase 64-char hex SHA-256")
        return value

    @model_validator(mode="after")
    def tier_cross_field_rules(self) -> SidecarRow:
        tier = self.provenance_tier
        if tier in {"TIER_1_PANEL_UNIQUE", "TIER_1_FIGURE_UNIQUE", "TIER_2_ARTICLE_ONLY"}:
            if not self.article_doi or not doi_is_well_formed(self.article_doi):
                raise ValueError(f"{tier} requires a well-formed article_doi")
            if self.ambiguity_reason is not None:
                raise ValueError(f"{tier} cannot carry ambiguity_reason")
        if tier == "TIER_1_PANEL_UNIQUE":
            if self.granularity != "PANEL":
                raise ValueError("TIER_1_PANEL_UNIQUE requires granularity PANEL")
            if not self.panel_id:
                raise ValueError("TIER_1_PANEL_UNIQUE requires an official panel_id")
            if self.match_basis != MATCH_BASIS_EXACT_UNIQUE_PANEL:
                raise ValueError("TIER_1_PANEL_UNIQUE has a fixed match_basis")
        elif tier == "TIER_1_FIGURE_UNIQUE":
            if self.granularity != "FIGURE":
                raise ValueError("TIER_1_FIGURE_UNIQUE requires granularity FIGURE")
            if not self.figure_id:
                raise ValueError("TIER_1_FIGURE_UNIQUE requires an official figure_id")
            if self.panel_id is not None:
                raise ValueError("TIER_1_FIGURE_UNIQUE must carry panel_id=null")
            if self.match_basis != MATCH_BASIS_EXACT_UNIQUE_FIGURE:
                raise ValueError("TIER_1_FIGURE_UNIQUE has a fixed match_basis")
        elif tier == "TIER_2_ARTICLE_ONLY":
            if self.granularity != "ARTICLE":
                raise ValueError("TIER_2_ARTICLE_ONLY requires granularity ARTICLE")
            if self.figure_id is not None or self.panel_id is not None:
                raise ValueError("TIER_2_ARTICLE_ONLY never carries figure/panel identifiers")
            if self.match_basis not in {
                MATCH_BASIS_EXACT_SINGLE_ARTICLE,
                MATCH_BASIS_CONTAINMENT_SINGLE_ARTICLE,
            }:
                raise ValueError("TIER_2_ARTICLE_ONLY has an invalid match_basis")
        else:  # RECORD_FALLBACK
            if self.granularity != "RECORD_FALLBACK":
                raise ValueError("RECORD_FALLBACK requires granularity RECORD_FALLBACK")
            if (
                self.article_doi is not None
                or self.figure_id is not None
                or self.panel_id is not None
            ):
                raise ValueError("RECORD_FALLBACK must carry no upstream identifiers")
            if not self.ambiguity_reason:
                raise ValueError("RECORD_FALLBACK requires ambiguity_reason")
            if self.match_basis is not None:
                raise ValueError("RECORD_FALLBACK cannot carry match_basis")
        return self

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
# Caption recovery mirrors the audited C1.1 PoC
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


class ArchiveExtractionError(ValueError):
    """The provenance archive failed a safety or integrity gate."""


def _validate_member(
    member: tarfile.TarInfo, seen_names: set[str], seen_basenames: set[str]
) -> str | None:
    """Screen one archive member; returns the output basename for XML members.

    ``None`` marks a tolerated benign entry that is never extracted: directory
    members and non-XML payloads (the official archive carries jsonl exports
    under sibling directories). Every hostile member class raises instead.
    """
    if member.name.startswith("/") or Path(member.name).is_absolute():
        raise ArchiveExtractionError(f"absolute path in archive: {member.name!r}")
    parts = Path(member.name).parts
    if not parts or any(p in {"..", "."} for p in parts):
        raise ArchiveExtractionError(f"path traversal in archive: {member.name!r}")
    if member.issym() or member.islnk():
        raise ArchiveExtractionError(f"link member not allowed: {member.name!r}")
    if member.isdir():
        return None  # benign directory entry: tolerated, nothing extracted
    if not member.isfile():
        raise ArchiveExtractionError(f"non-file member not allowed: {member.name!r}")
    base = Path(member.name).name
    if not base or base.startswith("."):
        raise ArchiveExtractionError(f"hidden payload not allowed: {member.name!r}")
    if not base.endswith(".xml"):
        return None  # benign non-XML payload: tolerated, never extracted
    if member.name in seen_names:
        raise ArchiveExtractionError(f"duplicate member name: {member.name!r}")
    if base in seen_basenames:
        raise ArchiveExtractionError(f"duplicate output basename: {base!r}")
    seen_names.add(member.name)
    seen_basenames.add(base)
    return base


def extract_xml_archive(
    archive_path: Path,
    dest_dir: Path,
    *,
    expected_sha256: str,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> None:
    """Hash-verify then safely unpack the official XML provenance archive.

    Fail-closed hardening: the archive must hash-verify BEFORE any extraction;
    the destination must not pre-exist (no stale or populated targets); member
    names are screened for absolute paths, traversal, links, duplicates and
    non-XML payloads; per-file and total decompressed quotas are enforced;
    output is staged in a fresh temporary directory and published with a
    single atomic rename; any partial output is removed on failure.
    """
    actual = sha256_file(archive_path)
    if actual != expected_sha256:
        raise ArchiveExtractionError(
            f"provenance archive sha256 mismatch: expected {expected_sha256} got {actual}"
        )
    if dest_dir.exists():
        raise ArchiveExtractionError(
            f"destination already exists (stale or populated target refused): {dest_dir}"
        )
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest_dir.name}.", dir=dest_dir.parent))
    try:
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
        except (tarfile.TarError, OSError, EOFError) as exc:
            raise ArchiveExtractionError(
                f"unreadable provenance archive {archive_path.name}: {exc}"
            ) from exc
        seen_names: set[str] = set()
        seen_basenames: set[str] = set()
        plan: list[tuple[tarfile.TarInfo, str]] = []
        total = 0
        for member in members:
            base = _validate_member(member, seen_names, seen_basenames)
            if base is None:
                continue  # tolerated directory entry
            if member.size > max_file_bytes:
                raise ArchiveExtractionError(
                    f"member exceeds maximum file size: {member.name!r} ({member.size} bytes)"
                )
            total += member.size
            if total > max_total_bytes:
                raise ArchiveExtractionError("decompressed total exceeds maximum")
            plan.append((member, base))
        if len(plan) > max_files:
            raise ArchiveExtractionError(f"archive contains more than {max_files} files")

        with tarfile.open(archive_path, "r:gz") as tar:
            for member, base in plan:
                source = tar.extractfile(member)
                if source is None:
                    raise ArchiveExtractionError(f"unreadable member: {member.name!r}")
                data = source.read()
                if len(data) > max_file_bytes:
                    raise ArchiveExtractionError(
                        f"member exceeds maximum file size: {member.name!r}"
                    )
                target = staging / base
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                try:
                    os.write(fd, data)
                    os.fsync(fd)
                finally:
                    os.close(fd)
        try:
            dir_fd = os.open(staging, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass  # directory fsync unsupported on this platform
        os.replace(staging, dest_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


# --- Tier decision to sidecar fields ---------------------------------------


def decision_to_row_fields(decision: JoinDecision, *, containment_used: bool = False) -> dict:
    """Map a fail-closed JoinDecision onto sidecar row fields.

    ARTICLE-level decisions never carry panel or figure identifiers; fallback
    decisions carry no upstream identifiers at all. A unique upstream unit is
    panel-granularity when the authoritative XML path carries an ``sd-panel``
    element; a whole-figure unit (no ``sd-panel`` child upstream) is reported
    as ``TIER_1_FIGURE_UNIQUE`` with ``panel_id=None`` — no panel identifier
    is invented, and a figure unit is never claimed as panel provenance.
    """
    if decision.result == "TIER1_UNIQUE_PANEL":
        if decision.panel_id:
            return {
                "provenance_tier": "TIER_1_PANEL_UNIQUE",
                "granularity": "PANEL",
                "match_basis": MATCH_BASIS_EXACT_UNIQUE_PANEL,
                "article_doi": decision.article_doi,
                "figure_id": decision.fig_id or None,
                "panel_id": decision.panel_id,
                "ambiguity_reason": None,
            }
        if not decision.fig_id:
            raise SidecarValidationError(
                "unique upstream unit has neither panel_id nor figure_id; "
                "refusing to invent identifiers"
            )
        return {
            "provenance_tier": "TIER_1_FIGURE_UNIQUE",
            "granularity": "FIGURE",
            "match_basis": MATCH_BASIS_EXACT_UNIQUE_FIGURE,
            "article_doi": decision.article_doi,
            "figure_id": decision.fig_id,
            "panel_id": None,
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
            "granularity": "ARTICLE",
            "match_basis": basis,
            "article_doi": decision.article_doi,
            "figure_id": None,
            "panel_id": None,
            "ambiguity_reason": None,
        }
    return {
        "provenance_tier": "RECORD_FALLBACK",
        "granularity": "RECORD_FALLBACK",
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
    dataset_id: Literal["SourceData"] = "SourceData",
    dataset_version: Literal["2.0.3"] = "2.0.3",
    task_corpus: Literal["entity_roles"] = "entity_roles",
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

ALL_TIERS: Final[tuple[ProvenanceTier, ...]] = (
    "TIER_1_PANEL_UNIQUE",
    "TIER_1_FIGURE_UNIQUE",
    "TIER_2_ARTICLE_ONLY",
    "RECORD_FALLBACK",
)


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
        "tier_counts": {tier: tier_counts.get(tier, 0) for tier in ALL_TIERS},
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
    }
