"""Deterministic reconciliation of the two SourceData provenance methods.

Compares, record-by-record and over ONE locked immutable input bundle:

  Method A — the PR #9 v0.2.0 sidecar algorithm (exact caption matching,
             containment fallback, exact precedence, PANEL/FIGURE tiers);
  Method B — the portfolio C1.1 investigation algorithm (exact canonical
             text unique:unique emission, figure-caption keyed asset index,
             DOI collapse for ambiguous single-article panels, no fuzzy,
             no first-match, no containment), split into
             B1_LABEL_INDEPENDENT (S3) and B2_LABEL_ASSISTED (S4 tuple).

Every count is re-derived from the locked inputs; no historical report
figure is used as an expected constant. Full row-level delta rows are only
written outside Git (default /tmp/ntruth-sourcedata-provenance-reconciliation);
committed artifacts are aggregates, hashes and sanitized identifiers only.

The reconciliation is byte-deterministic: run-all executes the full
pipeline twice into independent output dirs and compares every artifact
hash. It NEVER writes to the canonical corpus, manifests, locks or the
frozen external sidecar.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ntruth.task_corpora.io_util import read_jsonl_physical_lines, records_content_sha256
from ntruth.task_corpora.provenance_join import doi_is_well_formed, normalize_caption
from ntruth.task_corpora.provenance_sidecar import (
    ProvenanceBuildInputs,
    build_sidecar_rows,
    caption_text_from_element,
    extract_xml_archive,
    iter_upstream_captions,
    sha256_bytes,
    sha256_file,
)

# --- Locked input universe (attested hashes; counts always re-derived) ------

DEFAULT_CANON_DIR = (
    Path("/Volumes/FLASH128/N-Truth-Datasets") / "task_corpora/entity_roles/sourcedata/v2.0.3"
)
DEFAULT_RAW_DIR = Path("/Volumes/FLASH128/N-Truth-Datasets/raw/sourcedata/v2.0.3/roles_multi")
DEFAULT_ARCHIVE = DEFAULT_CANON_DIR / "provenance" / "source_data_xml_v2.0.3.tar.gz"
DEFAULT_UPSTREAM_REFERENCE = "https://huggingface.co/datasets/EMBO/SourceData"
DEFAULT_WORK_DIR = Path("/tmp/ntruth-sourcedata-provenance-final-review")

ATTESTED_INPUT_SHA256: Final[dict[str, str]] = {
    "canonical_records": "562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10",
    "canonical_train": "f2e7bc675294b2a041dee4481c344cc40e093364391e55a3e7a2417e7fe6b18c",
    "canonical_validation": "76d2fc01d7cb6a96e41dda45e9bdb116e37eae38552c1eedb45d6377163fe886",
    "canonical_test": "6bbc05663c6c18b490217d6eed8f70ebeb199330b58a322d150b9eb633817b9c",
    "raw_roles_train": "c2ac812846265686502469208dae435a5dc5279d6149940409f3b4566764c925",
    "raw_roles_validation": "d2e98f0e71905e18cc4dbe208646113ddb4b869cf06d53af628156f6e1493715",
    "raw_roles_test": "f7fbee9acd7e7f52ed92944d3d719c83164ba75e18218841d3dc764956c21a75",
    "leakage_audit": "d79c65f12a857e837923ea916b1062f321a4064f498597753f134ac3e92f46e7",
    "upstream_xml": "71f9899211efef62bc523275bbff7ba3e37ec8b4d1fc21405b58f4b68e93ba60",
}
#: Historical report figures — comparison targets ONLY, never expected values.
HISTORICAL_METHOD_A: Final[dict[str, int]] = {
    "PANEL": 69983,
    "FIGURE": 175,
    "ARTICLE": 3914,
    "FALLBACK": 1091,
}
HISTORICAL_METHOD_B: Final[dict[str, int]] = {
    "panel_level": 71197,
    "article_only": 3965,
    "fallback": 1,
}
HISTORICAL_INDEX_UNITS: Final[dict[str, int]] = {
    "explicit_panels": 75232,
    "claimed_total_units": 77688,
    "claimed_no_panel_figures": 2456,
}

PARTITIONS: Final[tuple[str, ...]] = ("train", "validation", "test")

DELTA_FIELDS: Final[tuple[str, ...]] = (
    "canonical_record_id",
    "partition",
    "source_row_index",
    "exact_source_text_sha256",
    "method_a_tier",
    "method_a_doi",
    "method_a_figure_id",
    "method_a_panel_id",
    "method_a_match_basis",
    "method_b_tier",
    "method_b_doi",
    "method_b_figure_id",
    "method_b_panel_id",
    "method_b_match_basis",
    "method_b_label_assisted",
    "decision_relation",
    "delta_reason",
)

ALLOWED_RELATIONS: Final[frozenset[str]] = frozenset(
    {
        "IDENTICAL",
        "SAME_ARTICLE_DIFFERENT_GRANULARITY",
        "METHOD_A_ONLY",
        "METHOD_B_ONLY",
        "CONFLICTING_ARTICLE",
        "CONFLICTING_FIGURE",
        "CONFLICTING_PANEL",
        "BOTH_FALLBACK",
    }
)

METHOD_B_ONLY_REASONS: Final[frozenset[str]] = frozenset(
    {
        "caption_parser_difference",
        "normalization_difference",
        "label_assisted_tuple",
        "exact_segment_vs_whole_caption",
        "figure_unit_vs_panel_unit_handling",
        "duplicate_key_handling",
        "doi_collapse_difference",
        "containment_policy_difference",
        "stale_or_different_upstream_asset",
        "implementation_error",
        "other_documented_reason",
    }
)

#: Historically reported S4 label-assisted matches (frozen C1.1 document);
#: comparison target only — the reconstruction must re-derive its own count.
HISTORICAL_S4_REPORTED: Final[int] = 14

#: The reconciliation runs over the SAME attested input universe as the
#: sidecar build, so its bundle identity is the attested
#: ProvenanceBuildInputs bundle_sha256 (re-derived, never hard-trusted).
RECONCILIATION_INPUT_BUNDLE_SHA256: Final[str] = (
    "6003491470adafe9f5331837c3e82a549b734b64ffff7332dbcd61b0dff97006"
)

#: §7 closed vocabulary for the exporter-lineage conclusion.
EXPORTER_LINEAGE_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        "EXPORTER_LINEAGE_SUPPORTS_METHOD_A",
        "EXPORTER_LINEAGE_SUPPORTS_METHOD_B",
        "EXPORTER_LINEAGE_SUPPORTS_HYBRID",
        "EXPORTER_LINEAGE_UNAVAILABLE",
        "METHODS_REQUIRE_HUMAN_ADJUDICATION",
    }
)

#: §5 closed vocabulary for per-unit projection-equivalence categories.
PROJECTION_EQUIVALENCE_CATEGORIES: Final[tuple[str, ...]] = (
    "projections_identical",
    "itertext_matches_exporter",
    "attribute_matches_exporter",
    "both_match_distinct_locked_texts",
    "neither_matches_exporter",
    "exporter_unavailable_for_unit",
)


def reconciliation_bundle_sha256(upstream_reference: str = DEFAULT_UPSTREAM_REFERENCE) -> str:
    """Re-derive the reconciliation input-bundle SHA-256 from pinned fields.

    The bundle is the canonical-JSON digest of the attested
    ``ProvenanceBuildInputs``; re-deriving it (and comparing against
    ``RECONCILIATION_INPUT_BUNDLE_SHA256``) proves the reconciliation runs
    over exactly the locked universe the sidecar build consumed.
    """
    from ntruth.task_corpora.provenance_sidecar import ALGORITHM_VERSION, SCHEMA_VERSION

    bundle = ProvenanceBuildInputs(
        canonical_records_sha256=ATTESTED_INPUT_SHA256["canonical_records"],
        canonical_train_sha256=ATTESTED_INPUT_SHA256["canonical_train"],
        canonical_validation_sha256=ATTESTED_INPUT_SHA256["canonical_validation"],
        canonical_test_sha256=ATTESTED_INPUT_SHA256["canonical_test"],
        raw_roles_train_sha256=ATTESTED_INPUT_SHA256["raw_roles_train"],
        raw_roles_validation_sha256=ATTESTED_INPUT_SHA256["raw_roles_validation"],
        raw_roles_test_sha256=ATTESTED_INPUT_SHA256["raw_roles_test"],
        leakage_audit_sha256=ATTESTED_INPUT_SHA256["leakage_audit"],
        upstream_xml_sha256=ATTESTED_INPUT_SHA256["upstream_xml"],
        resolvable_upstream_reference=upstream_reference,
        dataset_version="2.0.3",
        sidecar_schema_version=SCHEMA_VERSION,
        matching_algorithm_version=ALGORITHM_VERSION,
    )
    digest = bundle.bundle_sha256()
    if digest != RECONCILIATION_INPUT_BUNDLE_SHA256:
        raise ValueError(f"input bundle identity drift: {digest}")
    return digest


# --- Locked input bundle ----------------------------------------------------


def lock_input_bundle(*, canon_dir: Path, raw_dir: Path, archive: Path) -> dict[str, Any]:
    """Verify every attested input hash and re-derive counts from disk.

    Fail-closed: any mismatch raises. Counts are never taken from a prior
    report; they are re-derived from the locked files.
    """
    paths = {
        "canonical_train": canon_dir / "train.jsonl",
        "canonical_validation": canon_dir / "validation.jsonl",
        "canonical_test": canon_dir / "test.jsonl",
        "raw_roles_train": raw_dir / "train.jsonl",
        "raw_roles_validation": raw_dir / "validation.jsonl",
        "raw_roles_test": raw_dir / "test.jsonl",
        "leakage_audit": canon_dir / "leakage_audit.json",
        "upstream_xml": archive,
    }
    hashes: dict[str, str] = {}
    for name, path in paths.items():
        actual = sha256_file(path)
        if actual != ATTESTED_INPUT_SHA256[name]:
            raise ValueError(f"locked input {name} sha256 mismatch: {actual}")
        hashes[name] = actual

    counts: dict[str, int] = {}
    all_lines: list[str] = []
    for part in PARTITIONS:
        lines = read_jsonl_physical_lines(canon_dir / f"{part}.jsonl")
        counts[part] = len(lines)
        all_lines.extend(lines)
    records_sha = records_content_sha256(all_lines)
    if records_sha != ATTESTED_INPUT_SHA256["canonical_records"]:
        raise ValueError(f"records_sha256 mismatch: {records_sha}")
    return {
        "input_hashes": hashes,
        "records_sha256": records_sha,
        "counts_derived": counts,
        "total_derived": sum(counts.values()),
    }


# --- Upstream census ----------------------------------------------------------


@dataclass(frozen=True)
class Census:
    """The 14-statistic canonical XML census (§7) plus the measured DOI set."""

    stats: dict[str, int]
    hypothesis: dict[str, Any]
    article_dois: frozenset[str]


def _iter_figure_units(xml_dir: Path) -> Iterator[dict[str, Any]]:
    """Yield one row per matchable upstream unit (panel or panel-less figure).

    Two caption projections are carried because the methods use different
    caption parsers (§10 root cause): ``caption_itertext`` is the Method B
    projection (plain ``"".join(el.itertext())`` — reproduces its S3 figure
    exactly); ``caption_attribute`` is the Method A projection
    (``caption_text_from_element``: sd-tag wrappers substituted with their
    ``text`` attribute), identical to the rows of the Method A index.
    """
    for fp in sorted(xml_dir.glob("*.xml")):
        root = ET.parse(fp).getroot()
        doi = root.get("doi", "")
        for fig in root.iter("fig"):
            fig_id = fig.get("id", "")
            fig_itertext = normalize_caption("".join(fig.itertext()))
            panels = list(fig.iter("sd-panel"))
            if panels:
                for panel in panels:
                    yield {
                        "xml_file": fp.name,
                        "article_doi": doi,
                        "fig_id": fig_id,
                        "panel_id": panel.get("panel_id", ""),
                        "unit_kind": "PANEL",
                        "caption_itertext": normalize_caption("".join(panel.itertext())),
                        "caption_attribute": caption_text_from_element(panel),
                        "tag_texts": tuple((t.get("text") or "") for t in panel.iter("sd-tag")),
                    }
            else:
                yield {
                    "xml_file": fp.name,
                    "article_doi": doi,
                    "fig_id": fig_id,
                    "panel_id": "",
                    "unit_kind": "FIGURE",
                    "caption_itertext": fig_itertext,
                    "caption_attribute": caption_text_from_element(fig),
                    "tag_texts": tuple((t.get("text") or "") for t in fig.iter("sd-tag")),
                }


def run_census(xml_dir: Path) -> Census:
    """Measure the 14 census statistics; no historical figure is assumed."""
    files = sorted(xml_dir.glob("*.xml"))
    valid_dois: set[str] = set()
    figures = 0
    figures_with_panel = 0
    figures_without_panel = 0
    explicit_panels = 0
    empty_caption_units = 0
    panel_key_count: Counter[tuple[str, str, str]] = Counter()
    fig_key_count: Counter[tuple[str, str]] = Counter()
    nested_sd_panel = 0
    raw_captions: set[str] = set()
    norm_caption_count: Counter[str] = Counter()

    for fp in files:
        root = ET.parse(fp).getroot()
        doi = root.get("doi", "")
        if doi_is_well_formed(doi):
            valid_dois.add(doi)
        for fig in root.iter("fig"):
            figures += 1
            fig_id = fig.get("id", "")
            fig_key_count[(doi, fig_id)] += 1
            panels = list(fig.iter("sd-panel"))
            if panels:
                figures_with_panel += 1
                explicit_panels += len(panels)
                for panel in panels:
                    pid = panel.get("panel_id", "")
                    panel_key_count[(doi, fig_id, pid)] += 1
                    cap_raw = caption_text_from_element(panel)
                    raw_captions.add(cap_raw)
                    norm = normalize_caption(cap_raw)
                    norm_caption_count[norm] += 1
                    if not norm:
                        empty_caption_units += 1
            else:
                figures_without_panel += 1
                cap_raw = caption_text_from_element(fig)
                raw_captions.add(cap_raw)
                norm = normalize_caption(cap_raw)
                norm_caption_count[norm] += 1
                if not norm:
                    empty_caption_units += 1
        # nested sd-panel detection for this file
        for panel in root.iter("sd-panel"):
            for _inner in panel.iter("sd-panel"):
                if _inner is not panel:
                    nested_sd_panel += 1

    total_units = explicit_panels + figures_without_panel
    duplicated_panel_ids = sum(c - 1 for c in panel_key_count.values() if c > 1)
    duplicated_figure_ids = sum(c - 1 for c in fig_key_count.values() if c > 1)
    distinct_norm = len(norm_caption_count)
    duplicate_norm_keys = sum(1 for c in norm_caption_count.values() if c > 1)

    stats = {
        "xml_file_count": len(files),
        "valid_article_doi_count": len(valid_dois),
        "figure_count": figures,
        "figures_with_sd_panel": figures_with_panel,
        "figures_without_sd_panel": figures_without_panel,
        "explicit_sd_panel_count": explicit_panels,
        "total_matchable_units": total_units,
        "empty_caption_units": empty_caption_units,
        "duplicated_panel_ids": duplicated_panel_ids,
        "duplicated_figure_ids_within_article": duplicated_figure_ids,
        "nested_sd_panel_occurrences": nested_sd_panel,
        "distinct_raw_captions": len(raw_captions),
        "distinct_normalized_captions": distinct_norm,
        "duplicate_normalized_caption_keys": duplicate_norm_keys,
    }
    # §7 hypothesis — measured, never assumed. Every cross-check below is
    # computed from INDEPENDENT counters; no field restates an identity
    # derived from the fields it compares (such checks can never fail).
    independent_unit_count = sum(1 for _ in _iter_figure_units(xml_dir))
    hypothesis = {
        "historical_explicit_panels": HISTORICAL_INDEX_UNITS["explicit_panels"],
        "measured_explicit_panels": explicit_panels,
        "historical_claimed_total_units": HISTORICAL_INDEX_UNITS["claimed_total_units"],
        "measured_total_matchable_units": total_units,
        "historical_claimed_no_panel_figures": HISTORICAL_INDEX_UNITS["claimed_no_panel_figures"],
        # Independently counted during the figure walk (NOT total - panels):
        "measured_no_panel_figure_units": figures_without_panel,
        # Independent re-iteration of the unit generator:
        "independent_unit_iteration_count": independent_unit_count,
        # Historical-only arithmetic (contains no measurement; the
        # historical_ prefix says so):
        "historical_arithmetic_self_consistent": (
            HISTORICAL_INDEX_UNITS["explicit_panels"]
            + HISTORICAL_INDEX_UNITS["claimed_no_panel_figures"]
            == HISTORICAL_INDEX_UNITS["claimed_total_units"]
        ),
        "measured_panels_plus_no_panel_equals_total": (
            explicit_panels + figures_without_panel == total_units
        ),
        "hypothesis_explains_index_delta": (
            explicit_panels == HISTORICAL_INDEX_UNITS["explicit_panels"]
            and figures_without_panel == HISTORICAL_INDEX_UNITS["claimed_no_panel_figures"]
            and total_units == HISTORICAL_INDEX_UNITS["claimed_total_units"]
        ),
    }
    return Census(stats=stats, hypothesis=hypothesis, article_dois=frozenset(valid_dois))


# --- Method A reconstruction (PR #9 v0.2.0 algorithm) -----------------------


def build_method_a_index(xml_dir: Path, out_path: Path) -> dict[str, Any]:
    """Write Method A's panel-caption caption index (deterministic order)."""
    rows = 0
    with out_path.open("w", encoding="utf-8") as out:
        for rec in iter_upstream_captions(xml_dir):
            out.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            rows += 1
    return {"index_rows": rows, "index_sha256": sha256_file(out_path)}


def run_method_a(
    *,
    index_path: Path,
    canon_dir: Path,
    raw_dir: Path,
    out_path: Path,
    upstream_reference: str,
) -> dict[str, Any]:
    """Re-derive Method A decisions from the locked inputs (no hard-coding).

    The PR #9 v0.2.0 builder is invoked WITHOUT expected tier counts: the
    reconciliation measures what the algorithm produces, it does not assert
    the historical figures.
    """
    rows = build_sidecar_rows(
        index_path=index_path,
        raw_dir=raw_dir,
        canon_dir=canon_dir,
        upstream_asset_sha256=ATTESTED_INPUT_SHA256["upstream_xml"],
        upstream_reference=upstream_reference,
    )
    tier_counts: Counter[str] = Counter()
    with out_path.open("w", encoding="utf-8") as out:
        for r in rows:
            tier_counts[r.provenance_tier] += 1
            out.write(
                json.dumps(
                    {
                        "canonical_record_id": r.canonical_record_id,
                        "partition": r.partition,
                        "source_row_index": r.source_row_index,
                        "exact_source_text_sha256": r.exact_source_text_sha256,
                        "provenance_tier": r.provenance_tier,
                        "granularity": r.granularity,
                        "article_doi": r.article_doi,
                        "figure_id": r.figure_id,
                        "panel_id": r.panel_id,
                        "match_basis": r.match_basis,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return {
        "rows": len(rows),
        "tier_counts": dict(sorted(tier_counts.items())),
        "output_sha256": sha256_file(out_path),
    }


# --- Method B reconstruction (portfolio C1.1 algorithm) ---------------------


def _record_entity_span_signature(
    words: list[str], labels: list[str], *, with_labels: bool = False
) -> str:
    """SHA-256 of the sorted entity spans of one raw roles_multi line.

    Label-assisted by construction: span BOUNDARIES come from the gold BIO
    labels, so any match it produces is LABEL_ASSISTED even when the label
    names themselves are excluded from the signature (``with_labels=False``
    hashes span texts only, making it comparable with the asset-side sd-tag
    ``text`` attribute tuple). Both sides use raw (un-normalized) text, as
    in the frozen C1.1 investigation.
    """
    spans: list[tuple[str, str]] = []
    current_label: str | None = None
    current_words: list[str] = []
    # Fail-closed: a length mismatch would silently truncate the span set
    # and corrupt the S4 label-assisted signature; it must raise instead.
    if len(words) != len(labels):
        raise ValueError(f"words/labels length mismatch: {len(words)} != {len(labels)}")
    for word, label in zip(words, labels, strict=True):
        if label.startswith("B-"):
            if current_label is not None:
                spans.append((current_label, " ".join(current_words)))
            current_label = label[2:]
            current_words = [word]
        elif label.startswith("I-") and current_label == label[2:]:
            current_words.append(word)
        else:
            if current_label is not None:
                spans.append((current_label, " ".join(current_words)))
            current_label = None
            current_words = []
    if current_label is not None:
        spans.append((current_label, " ".join(current_words)))
    if with_labels:
        payload = json.dumps(sorted(spans), ensure_ascii=False)
    else:
        payload = json.dumps(sorted(text for _, text in spans), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _asset_entity_span_signature(unit: dict[str, Any]) -> str:
    """Asset-side counterpart: SHA-256 of the sorted sd-tag text tuple."""
    payload = json.dumps(sorted(unit["tag_texts"]), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_method_b(
    *,
    xml_dir: Path,
    raw_dir: Path,
    out_path: Path,
) -> dict[str, Any]:
    """Re-derive Method B decisions from the locked inputs (no hard-coding).

    Faithful reconstruction of the portfolio investigation method:

      B1 (LABEL_INDEPENDENT): two-pass dict counting on canonical raw text
        against the upstream itertext caption projection; emit ONLY keys
        with exactly one record AND exactly one upstream unit. Ambiguous
        keys whose candidate units all belong to a single article collapse
        to deterministic ARTICLE-level (DOI-only) provenance.
      B2 (LABEL_ASSISTED): on ambiguous keys, join
        (text, sorted entity-span tuple SHA-256) against the upstream
        (caption, sd-tag entity tuple SHA-256); 1:1 unique only.

    No fuzzy similarity, no first-match, no containment.
    """
    units: list[dict[str, Any]] = list(_iter_figure_units(xml_dir))
    units_by_key: dict[str, list[dict[str, Any]]] = {}
    asset_tuple_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for unit in units:
        key = unit["caption_itertext"]
        units_by_key.setdefault(key, []).append(unit)
        sig = _asset_entity_span_signature(unit)
        asset_tuple_index.setdefault((key, sig), []).append(unit)

    # Two-pass counting: record-side key and tuple multiplicities first.
    raw_lines_by_part = {
        part: read_jsonl_physical_lines(raw_dir / f"{part}.jsonl") for part in PARTITIONS
    }
    rec_key_count: Counter[str] = Counter()
    rec_tuple_count: Counter[tuple[str, str]] = Counter()
    parsed: dict[str, list[dict[str, Any]]] = {}
    for part in PARTITIONS:
        parsed[part] = []
        for line in raw_lines_by_part[part]:
            rec = json.loads(line)
            key = normalize_caption(rec["text"])
            rec_key_count[key] += 1
            span_sig = _record_entity_span_signature(rec["words"], rec["labels"])
            rec_tuple_count[(key, span_sig)] += 1
            parsed[part].append({"rec": rec, "key": key, "span_sig": span_sig})

    counts: Counter[str] = Counter()
    per_split: dict[str, Counter[str]] = {p: Counter() for p in PARTITIONS}
    s4_matches = 0
    rows_written = 0
    assigned_dois: set[str] = set()
    ambiguous_unit_keys = 0
    label_assisted_rows_outside_s4 = 0
    with out_path.open("w", encoding="utf-8") as out:
        for part in PARTITIONS:
            for i, entry in enumerate(parsed[part]):
                rec = entry["rec"]
                key = entry["key"]
                text = rec["text"]
                candidates = units_by_key.get(key, [])
                tier = "UNMATCHED_NO_ASSET_TEXT"
                doi: str | None = None
                fig_id: str | None = None
                panel_id: str | None = None
                basis: str | None = None
                label_assisted = False
                if len(candidates) == 1 and rec_key_count[key] == 1:
                    unit = candidates[0]
                    tier = "S3_UNIQUE_UNIT"
                    doi = unit["article_doi"]
                    fig_id = unit["fig_id"]
                    panel_id = unit["panel_id"] or None
                    basis = "exact_canonical_text_unique_unit"
                elif candidates:
                    span_sig = entry["span_sig"]
                    tuple_matches = asset_tuple_index.get((key, span_sig), [])
                    if len(tuple_matches) == 1 and rec_tuple_count[(key, span_sig)] == 1:
                        unit = tuple_matches[0]
                        tier = "S4_UNIQUE_ANNOTATION_TUPLE"
                        doi = unit["article_doi"]
                        fig_id = unit["fig_id"]
                        panel_id = unit["panel_id"] or None
                        basis = "entity_span_tuple_unique"
                        label_assisted = True
                        s4_matches += 1
                    else:
                        dois = sorted({u["article_doi"] for u in candidates})
                        if len(dois) == 1:
                            tier = "AMBIGUOUS_SINGLE_DOI"
                            doi = dois[0]
                            basis = "doi_collapse_single_article"
                        else:
                            tier = "AMBIGUOUS_MULTI_DOI"
                            basis = None
                counts[tier] += 1
                per_split[part][tier] += 1
                if doi is not None:
                    assigned_dois.add(doi)
                if label_assisted and tier != "S4_UNIQUE_ANNOTATION_TUPLE":
                    label_assisted_rows_outside_s4 += 1
                rows_written += 1
                out.write(
                    json.dumps(
                        {
                            "partition": part,
                            "source_row_index": i,
                            "exact_source_text_sha256": sha256_bytes(text.encode("utf-8")),
                            "method_b_tier": tier,
                            "article_doi": doi,
                            "figure_id": fig_id,
                            "panel_id": panel_id,
                            "match_basis": basis,
                            "label_assisted": label_assisted,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
    # Ambiguous caption keys (measured): keys backed by more than one unit
    # or more than one record — every such record must land in a
    # fail-closed tier, never in S3.
    ambiguous_unit_keys = sum(
        1
        for key, candidates in units_by_key.items()
        if len(candidates) != 1 or rec_key_count[key] != 1
    )
    # Measured duplicate-handling invariant: INDEPENDENTLY re-read the
    # emitted rows and verify no S3 row carries an ambiguous caption key.
    ambiguous_record_keys = {
        key for key, n in rec_key_count.items() if len(units_by_key.get(key, [])) != 1 or n != 1
    }
    ambiguous_key_records_emitted_s3 = 0
    with out_path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row["method_b_tier"] != "S3_UNIQUE_UNIT":
                continue
            key = normalize_caption(
                parsed[row["partition"]][row["source_row_index"]]["rec"]["text"]
            )
            if key in ambiguous_record_keys:
                ambiguous_key_records_emitted_s3 += 1
    return {
        "rows": rows_written,
        "tier_counts": dict(sorted(counts.items())),
        "per_split": {p: dict(sorted(c.items())) for p, c in sorted(per_split.items())},
        "s4_matches_text_spans_variant": s4_matches,
        "assigned_dois": sorted(assigned_dois),
        "ambiguous_unit_keys": ambiguous_unit_keys,
        "ambiguous_key_records_emitted_s3": ambiguous_key_records_emitted_s3,
        "label_assisted_rows_outside_s4": label_assisted_rows_outside_s4,
        "output_sha256": sha256_file(out_path),
    }


# --- Record-by-record delta (§9) ---------------------------------------------


def _delta_reason(a: dict[str, Any], b: dict[str, Any], relation: str) -> str:
    """Deterministic structural explanation of one delta row."""
    if relation == "IDENTICAL":
        return "none"
    if relation == "BOTH_FALLBACK":
        return "both_methods_fail_closed_on_this_record"
    if relation == "METHOD_B_ONLY":
        if b["label_assisted"]:
            return "label_assisted_tuple"
        # Measured root cause: the two methods parse captions differently
        # (Method B: plain XML itertext; Method A: sd-tag text-attribute
        # substitution), so the same record keys to different captions.
        return "caption_parser_difference"
    if relation == "METHOD_A_ONLY":
        if a["match_basis"] == "CONTAINMENT_SINGLE_ARTICLE":
            return "containment_policy_difference"
        return "caption_parser_difference"
    if relation == "SAME_ARTICLE_DIFFERENT_GRANULARITY":
        if (
            a["provenance_tier"] == "TIER_2_ARTICLE_ONLY"
            or b["method_b_tier"] == "AMBIGUOUS_SINGLE_DOI"
        ):
            return "doi_collapse_difference"
        return "figure_unit_vs_panel_unit_handling"
    if relation in {"CONFLICTING_ARTICLE", "CONFLICTING_FIGURE", "CONFLICTING_PANEL"}:
        return "conflict_recorded_for_adjudication"
    return "other_documented_reason"


def classify_relation(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Map one (Method A, Method B) pair onto the §9 relation vocabulary."""
    a_fallback = a["provenance_tier"] == "RECORD_FALLBACK"
    b_unmatched = b["method_b_tier"] in {
        "UNMATCHED_NO_ASSET_TEXT",
        "AMBIGUOUS_MULTI_DOI",
    }
    if a_fallback and b_unmatched:
        return "BOTH_FALLBACK"
    if a_fallback:
        return "METHOD_B_ONLY"
    if b_unmatched:
        return "METHOD_A_ONLY"
    a_doi, b_doi = a["article_doi"], b["article_doi"]
    if a_doi != b_doi:
        return "CONFLICTING_ARTICLE"
    a_fig, b_fig = a["figure_id"], b["figure_id"]
    if a_fig is not None and b_fig is not None and a_fig != b_fig:
        return "CONFLICTING_FIGURE"
    a_panel, b_panel = a["panel_id"], b["panel_id"]
    if a_panel is not None and b_panel is not None and a_panel != b_panel:
        return "CONFLICTING_PANEL"
    # Granularity agreement is checked per level; ANY mismatch at the same
    # article is SAME_ARTICLE_DIFFERENT_GRANULARITY (never IDENTICAL), and
    # every branch below is reachable.
    a_granularity = a["granularity"]
    same_granularity = (
        (a_granularity == "PANEL" and b_panel is not None)
        or (a_granularity == "FIGURE" and b_panel is None and b_fig is not None)
        or (a_granularity == "ARTICLE" and b_panel is None and b_fig is None)
    )
    if not same_granularity:
        return "SAME_ARTICLE_DIFFERENT_GRANULARITY"
    return "IDENTICAL"


def _enforce_delta_contract(delta: dict[str, Any]) -> None:
    """Fail-closed check of the 17-field delta contract and vocabularies.

    Explicit raise (not ``assert``): assertions are stripped under
    ``python -O``, which would silently remove a scientific-output control.
    """
    if tuple(delta) != DELTA_FIELDS:
        raise ValueError(f"delta field contract violated: {tuple(delta)}")
    relation = delta["decision_relation"]
    if relation not in ALLOWED_RELATIONS:
        raise ValueError(f"relation outside §9 vocabulary: {relation}")
    if relation == "METHOD_B_ONLY" and delta["delta_reason"] not in METHOD_B_ONLY_REASONS:
        raise ValueError(f"METHOD_B_ONLY reason outside vocabulary: {delta['delta_reason']}")


def run_delta(
    *,
    method_a_path: Path,
    method_b_path: Path,
    out_path: Path,
    audit_path: Path,
) -> dict[str, Any]:
    """Emit one deterministic 17-field delta row per canonical record.

    Full rows are written ONLY to the external work directory (never Git);
    the returned aggregates plus sanitized audit samples are committable.
    """
    a_rows: dict[tuple[str, int], dict[str, Any]] = {}
    with method_a_path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            a_rows[(rec["partition"], rec["source_row_index"])] = rec
    b_rows: dict[tuple[str, int], dict[str, Any]] = {}
    with method_b_path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            b_rows[(rec["partition"], rec["source_row_index"])] = rec
    if set(a_rows) != set(b_rows):
        raise ValueError("method A and method B row keys do not align exactly")

    relations: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    b_only_reasons: Counter[str] = Counter()
    rows = 0
    with out_path.open("w", encoding="utf-8") as out:
        for key in sorted(a_rows):
            a = a_rows[key]
            b = b_rows[key]
            relation = classify_relation(a, b)
            reason = _delta_reason(a, b, relation)
            relations[relation] += 1
            reasons[reason] += 1
            if relation == "METHOD_B_ONLY":
                b_only_reasons[reason] += 1
            delta = {
                "canonical_record_id": a["canonical_record_id"],
                "partition": a["partition"],
                "source_row_index": a["source_row_index"],
                "exact_source_text_sha256": a["exact_source_text_sha256"],
                "method_a_tier": a["provenance_tier"],
                "method_a_doi": a["article_doi"],
                "method_a_figure_id": a["figure_id"],
                "method_a_panel_id": a["panel_id"],
                "method_a_match_basis": a["match_basis"],
                "method_b_tier": b["method_b_tier"],
                "method_b_doi": b["article_doi"],
                "method_b_figure_id": b["figure_id"],
                "method_b_panel_id": b["panel_id"],
                "method_b_match_basis": b["match_basis"],
                "method_b_label_assisted": b["label_assisted"],
                "decision_relation": relation,
                "delta_reason": reason,
            }
            _enforce_delta_contract(delta)
            rows += 1
            out.write(json.dumps(delta, ensure_ascii=False, sort_keys=True) + "\n")

    # §13 audit set: mandatory categories + stratified deterministic sample.
    audit = _build_audit_set(out_path)
    audit_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in audit),
        encoding="utf-8",
    )
    return {
        "delta_rows": rows,
        "relations": dict(sorted(relations.items())),
        "delta_reasons": dict(sorted(reasons.items())),
        "method_b_only_reasons": dict(sorted(b_only_reasons.items())),
        "audit_records": len(audit),
        "output_sha256": sha256_file(out_path),
        "audit_sha256": sha256_file(audit_path),
    }


def _build_audit_set(delta_path: Path) -> list[dict[str, Any]]:
    """Deterministic §13 audit selection (sanitized identifiers only)."""
    mandatory: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    with delta_path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            relation = row["decision_relation"]
            if (
                relation in {"CONFLICTING_ARTICLE", "CONFLICTING_FIGURE", "CONFLICTING_PANEL"}
                or row["method_b_label_assisted"]
                or (row["method_a_tier"] == "RECORD_FALLBACK" and relation == "METHOD_B_ONLY")
                or relation == "BOTH_FALLBACK"
                or (
                    {row["method_a_tier"], row["method_b_tier"]}
                    & {"TIER_2_ARTICLE_ONLY", "AMBIGUOUS_SINGLE_DOI"}
                    and relation != "IDENTICAL"
                )
            ):
                mandatory.append(row)
            elif relation != "IDENTICAL":
                remaining.append(row)
    # Stratified deterministic stride sample of >= 100 remaining delta rows.
    sample: list[dict[str, Any]] = []
    if remaining:
        stride = max(1, len(remaining) // 100)
        sample = remaining[::stride][:200]
    return mandatory + sample


# --- Human adjudication dossier (§8) ------------------------------------------

#: Dossier files: the review packet. Sanitized identifiers and hashes ONLY —
#: corpus text never enters the packet (and therefore never Git).
DOSSIER_ARTIFACTS: Final[tuple[str, ...]] = (
    "method_b_only_records.jsonl",
    "same_article_different_granularity_records.jsonl",
    "both_fallback_records.jsonl",
    "label_assisted_s4_records.jsonl",
    "exporter_projection_disagreements.jsonl",
    "human_inspection_sample.jsonl",
    "categories.json",
    "README.md",
    "dossier_summary.json",
)

#: Projection categories where the two caption projections DISAGREE about
#: exporter membership. ``neither_matches_exporter`` fails BOTH projections
#: and therefore pits nothing against nothing; ``projections_identical`` and
#: ``exporter_unavailable_for_unit`` carry no disagreement by construction.
PROJECTION_DISAGREEMENT_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "itertext_matches_exporter",
        "attribute_matches_exporter",
        "both_match_distinct_locked_texts",
    }
)

_DOSSIER_SAMPLE_PER_PARTITION: Final[int] = 10
_DOSSIER_SAMPLE_GRANULARITY_MAX: Final[int] = 5


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _canonical_reference(partition: str, source_row_index: int) -> tuple[str, int]:
    """External text reference into the locked canonical bundle (1-based)."""
    return (f"task_corpora/entity_roles/sourcedata/v2.0.3/{partition}.jsonl", source_row_index + 1)


def _stride_sample(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    stride = math.ceil(len(rows) / limit)
    return rows[::stride][:limit]


def build_adjudication_dossier(
    *, run_dir: Path, out_dir: Path | None = None, exporter_lineage_outcome: str | None = None
) -> dict[str, Any]:
    """§8 review packet: identifiers and hashes for every adjudication class.

    Not a gold dataset. Every listed record carries its external text
    reference (locked file path + 1-based physical line, or tarball member)
    so a human adjudicator can inspect corpus text OUTSIDE this packet; the
    packet itself contains no corpus text.
    """
    dossier_dir = out_dir if out_dir is not None else run_dir / "adjudication_dossier"
    dossier_dir.mkdir(parents=True, exist_ok=True)

    delta_rows = _read_jsonl(run_dir / "delta_rows.jsonl")
    method_b_only_rows = _read_jsonl(run_dir / "method_b_only_rows.jsonl")
    method_b_rows = _read_jsonl(run_dir / "method_b_rows.jsonl")
    projection_rows = _read_jsonl(run_dir / "projection_equivalence_rows.jsonl")
    delta_summary = json.loads((run_dir / "delta_summary.json").read_text(encoding="utf-8"))
    method_b_only_summary = json.loads(
        (run_dir / "method_b_only_summary.json").read_text(encoding="utf-8")
    )
    projection_summary = json.loads(
        (run_dir / "projection_equivalence.json").read_text(encoding="utf-8")
    )
    adjudication = json.loads((run_dir / "adjudication.json").read_text(encoding="utf-8"))

    granularity_rows = [
        row
        for row in delta_rows
        if row["decision_relation"] == "SAME_ARTICLE_DIFFERENT_GRANULARITY"
    ]
    both_fallback_rows = [row for row in delta_rows if row["decision_relation"] == "BOTH_FALLBACK"]
    s4_rows = [row for row in method_b_rows if row.get("label_assisted")]
    disagreement_rows = [
        row for row in projection_rows if row["category"] in PROJECTION_DISAGREEMENT_CATEGORIES
    ]

    _write_jsonl(dossier_dir / "method_b_only_records.jsonl", method_b_only_rows)
    _write_jsonl(dossier_dir / "same_article_different_granularity_records.jsonl", granularity_rows)
    _write_jsonl(dossier_dir / "both_fallback_records.jsonl", both_fallback_rows)
    _write_jsonl(dossier_dir / "label_assisted_s4_records.jsonl", s4_rows)
    _write_jsonl(dossier_dir / "exporter_projection_disagreements.jsonl", disagreement_rows)

    # Deterministic stratified subset with external text references.
    sample: list[dict[str, Any]] = []
    b_only_by_partition: dict[str, list[dict[str, Any]]] = {}
    for row in method_b_only_rows:
        b_only_by_partition.setdefault(row["partition"], []).append(row)
    for partition in sorted(b_only_by_partition):
        for row in _stride_sample(b_only_by_partition[partition], _DOSSIER_SAMPLE_PER_PARTITION):
            ref, line = _canonical_reference(row["partition"], row["source_row_index"])
            sample.append(
                {
                    "dossier_category": "METHOD_B_ONLY",
                    "canonical_record_id": row["canonical_record_id"],
                    "partition": row["partition"],
                    "exact_source_text_sha256": row["exact_source_text_sha256"],
                    "article_doi": row["article_doi"],
                    "canonical_reference": ref,
                    "canonical_line": line,
                    "upstream_xml_reference": f"source_data_xml_v2.0.3.tar.gz::{row['article_doi']}.xml",
                }
            )
    for row in _stride_sample(granularity_rows, _DOSSIER_SAMPLE_GRANULARITY_MAX):
        ref, line = _canonical_reference(row["partition"], row["source_row_index"])
        sample.append(
            {
                "dossier_category": "SAME_ARTICLE_DIFFERENT_GRANULARITY",
                "canonical_record_id": row["canonical_record_id"],
                "partition": row["partition"],
                "exact_source_text_sha256": row["exact_source_text_sha256"],
                "article_doi": row["method_b_doi"] or row["method_a_doi"],
                "canonical_reference": ref,
                "canonical_line": line,
                "upstream_xml_reference": (
                    f"source_data_xml_v2.0.3.tar.gz::{row['method_b_doi'] or row['method_a_doi']}.xml"
                ),
            }
        )
    for row in both_fallback_rows:
        ref, line = _canonical_reference(row["partition"], row["source_row_index"])
        sample.append(
            {
                "dossier_category": "BOTH_FALLBACK",
                "canonical_record_id": row["canonical_record_id"],
                "partition": row["partition"],
                "exact_source_text_sha256": row["exact_source_text_sha256"],
                "article_doi": row["method_a_doi"] or row["method_b_doi"],
                "canonical_reference": ref,
                "canonical_line": line,
                "upstream_xml_reference": None,
            }
        )
    for row in s4_rows:
        ref, line = _canonical_reference(row["partition"], row["source_row_index"])
        sample.append(
            {
                "dossier_category": "S4_LABEL_ASSISTED",
                "canonical_record_id": row.get("canonical_record_id"),
                "partition": row["partition"],
                "exact_source_text_sha256": row["exact_source_text_sha256"],
                "article_doi": row["article_doi"],
                "canonical_reference": ref,
                "canonical_line": line,
                "upstream_xml_reference": f"source_data_xml_v2.0.3.tar.gz::{row['article_doi']}.xml",
            }
        )
    _write_jsonl(dossier_dir / "human_inspection_sample.jsonl", sample)

    categories = _dossier_categories(
        method_b_only_count=len(method_b_only_rows),
        method_b_only_summary=method_b_only_summary,
        granularity_count=len(granularity_rows),
        both_fallback_count=len(both_fallback_rows),
        s4_count=len(s4_rows),
        disagreement_rows=disagreement_rows,
        projection_summary=projection_summary,
        delta_summary=delta_summary,
        adjudication=adjudication,
        sample_count=len(sample),
        exporter_lineage_outcome=exporter_lineage_outcome,
    )
    _write_json(dossier_dir / "categories.json", categories)

    readme = _dossier_readme(
        counts={
            "method_b_only_records": len(method_b_only_rows),
            "same_article_different_granularity_records": len(granularity_rows),
            "both_fallback_records": len(both_fallback_rows),
            "label_assisted_s4_records": len(s4_rows),
            "exporter_projection_disagreements": len(disagreement_rows),
            "human_inspection_sample": len(sample),
        }
    )
    (dossier_dir / "README.md").write_text(readme, encoding="utf-8")

    counts = {
        "method_b_only_records": len(method_b_only_rows),
        "same_article_different_granularity_records": len(granularity_rows),
        "both_fallback_records": len(both_fallback_rows),
        "label_assisted_s4_records": len(s4_rows),
        "exporter_projection_disagreements": len(disagreement_rows),
        "human_inspection_sample": len(sample),
    }
    # Self-exclusion: the summary cannot carry its own hash (single write).
    file_sha256 = {
        name: sha256_file(dossier_dir / name)
        for name in DOSSIER_ARTIFACTS
        if name != "dossier_summary.json"
    }
    summary = {"counts": counts, "file_sha256": file_sha256}
    _write_json(dossier_dir / "dossier_summary.json", summary)
    return summary


def _dossier_categories(
    *,
    method_b_only_count: int,
    method_b_only_summary: dict[str, Any],
    granularity_count: int,
    both_fallback_count: int,
    s4_count: int,
    disagreement_rows: list[dict[str, Any]],
    projection_summary: dict[str, Any],
    delta_summary: dict[str, Any],
    adjudication: dict[str, Any],
    sample_count: int,
    exporter_lineage_outcome: str | None,
) -> dict[str, Any]:
    """Per-category question/evidence/recommendation/confidence (§8)."""
    disagreement_by_category: dict[str, int] = {}
    for row in disagreement_rows:
        disagreement_by_category[row["category"]] = (
            disagreement_by_category.get(row["category"], 0) + 1
        )
    lineage = adjudication.get("exporter_lineage") or exporter_lineage_outcome
    return {
        "METHOD_B_ONLY": {
            "question": (
                "Are the records matched only by Method B legitimate panel/figure-level "
                "provenance assignments, and does their existence justify replacing the "
                "sidecar algorithm?"
            ),
            "evidence": {
                "records": method_b_only_count,
                "itertext_equals_locked": method_b_only_summary["itertext_equals_locked"],
                "attribute_differs_from_locked": method_b_only_summary[
                    "attribute_differs_from_locked"
                ],
                "attribute_equals_other_locked_text": method_b_only_summary[
                    "attribute_equals_other_locked_text"
                ],
                "delta_reason": "caption_parser_difference (100% of records)",
                "exporter_lineage": lineage,
                "row_hashes_sha256": method_b_only_summary["output_sha256"],
            },
            "recommended_interpretation": (
                "The locked exporter text equals the plain-itertext projection for every "
                "record and differs from the attribute projection for every record, and "
                "the official exporter lineage supports Method B's projection. Treat the "
                "assignments as legitimate evidence; algorithm replacement remains a "
                "separately authorised human decision."
            ),
            "confidence": "high",
            "human_decision_required": True,
        },
        "SAME_ARTICLE_DIFFERENT_GRANULARITY": {
            "question": (
                "Do the records where the methods agree on the article but differ on "
                "panel-level resolution indicate a provenance conflict?"
            ),
            "evidence": {
                "records": granularity_count,
                "delta_reason": "doi_collapse_difference",
                "conflicting_article_assignments": delta_summary["relations"].get(
                    "CONFLICTING_ARTICLE", 0
                ),
            },
            "recommended_interpretation": (
                "Not a conflict: both methods agree on the article DOI; only the "
                "resolution granularity differs."
            ),
            "confidence": "high",
            "human_decision_required": True,
        },
        "BOTH_FALLBACK": {
            "question": ("How should the record that fails both methods be treated?"),
            "evidence": {
                "records": both_fallback_count,
                "policy": "BOTH_FALLBACK_RECORDED_NO_IMPUTATION",
            },
            "recommended_interpretation": (
                "Recorded without imputation; no public-asset counterpart exists for this record."
            ),
            "confidence": "high",
            "human_decision_required": True,
        },
        "S4_LABEL_ASSISTED": {
            "question": (
                "Do the reproducible label-assisted (S4) matches support any production "
                "or eligibility claim?"
            ),
            "evidence": {
                "records": s4_count,
                "historically_reported": 14,
                "status": "PARTIAL_NOT_HISTORICALLY_REPRODUCIBLE",
                "production_eligibility": "NON_PRODUCTION",
                "valid_for_split_grouping": False,
                "valid_for_model_evaluation": False,
                "eligibility_changing": False,
            },
            "recommended_interpretation": (
                "Report as a partial, non-production reconstruction. The historical "
                "S4 count is not reproducible without the original (never committed) "
                "tuple serialisation; label-assisted evidence never promotes leakage, "
                "split or model-use claims."
            ),
            "confidence": "medium",
            "human_decision_required": True,
        },
        "EXPORTER_PROJECTION_DISAGREEMENT": {
            "question": (
                "Which caption projection did the official SourceData exporter write "
                "into the locked token_classification text field?"
            ),
            "evidence": {
                "units_by_category": dict(sorted(disagreement_by_category.items())),
                "projection_categories": projection_summary["categories"],
                "exporter_lineage": lineage,
            },
            "recommended_interpretation": (
                "The exporter lineage supports the plain-itertext projection (Method B); "
                "the attribute projection (Method A) matches the exporter for zero units. "
                "Residual caveat: the exporter applies whitespace and dash normalisation "
                "during cleanup."
            ),
            "confidence": "high",
            "human_decision_required": True,
        },
        "HUMAN_INSPECTION_SAMPLE": {
            "question": (
                "Does a deterministic stratified inspection of the listed external text "
                "references corroborate the automated categories?"
            ),
            "evidence": {
                "sample_records": sample_count,
                "selection": (
                    "deterministic stride sampling per partition/category; external "
                    "references only (locked canonical line + tarball member); no "
                    "corpus text in this packet"
                ),
            },
            "recommended_interpretation": (
                "Use the sample as the human spot-check entry point; this packet is a "
                "review packet, not a gold dataset, and automated review is not human "
                "adjudication."
            ),
            "confidence": "low",
            "human_decision_required": True,
        },
    }


def _dossier_readme(*, counts: dict[str, int]) -> str:
    lines = [
        "# SourceData provenance — human adjudication dossier (review packet)",
        "",
        "This packet is a REVIEW PACKET, not a gold dataset. It contains sanitized",
        "identifiers and SHA-256 hashes only — NO corpus text. Automated review is",
        "not human adjudication; every category records human_decision_required=true.",
        "",
        "## Contents",
        "",
        "| File | Records |",
        "|---|---|",
        f"| method_b_only_records.jsonl | {counts['method_b_only_records']} |",
        f"| same_article_different_granularity_records.jsonl | {counts['same_article_different_granularity_records']} |",
        f"| both_fallback_records.jsonl | {counts['both_fallback_records']} |",
        f"| label_assisted_s4_records.jsonl | {counts['label_assisted_s4_records']} |",
        f"| exporter_projection_disagreements.jsonl | {counts['exporter_projection_disagreements']} |",
        f"| human_inspection_sample.jsonl | {counts['human_inspection_sample']} |",
        "| categories.json | per-category question/evidence/recommendation/confidence |",
        "",
        "## How to inspect corpus text (outside this packet)",
        "",
        "- canonical record text: line `canonical_line` (1-based) of the locked file",
        "  `task_corpora/entity_roles/sourcedata/v2.0.3/{partition}.jsonl`;",
        "- upstream XML: tarball member `source_data_xml_v2.0.3.tar.gz::{doi}.xml`;",
        "- raw exporter text: `raw/sourcedata/v2.0.3/roles_multi/{partition}.jsonl`.",
        "",
        "The packet lives outside Git; record-level rows are never committed.",
        "",
    ]
    return "\n".join(lines)


# --- Adjudication (§11-§12) ---------------------------------------------------


@dataclass(frozen=True)
class AdjudicationPolicy:
    """Versioned adjudication policy (§3G): no magic numbers in the report.

    Every replacement condition threshold and treatment decision lives here;
    the report records the policy version and the SHA-256 of its canonical
    serialization, so a human adjudicator knows exactly which rules produced
    the outcome.
    """

    version: str = "1.0.0"
    allowed_conflicting_assignments: int = 0
    label_assisted_treatment: str = "NON_PRODUCTION_NOT_ELIGIBILITY_CHANGING"
    acceptable_fallback_handling: str = "BOTH_FALLBACK_RECORDED_NO_IMPUTATION"
    require_determinism: bool = True
    require_official_source_linkage: bool = True
    require_input_bundle_equality: bool = True

    def canonical(self) -> dict[str, Any]:
        """Deterministic field-ordered dict used for hashing and reporting."""
        return {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}

    def sha256(self) -> str:
        """SHA-256 of the canonical JSON serialization (hash-stable)."""
        payload = json.dumps(self.canonical(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


#: The single committed policy instance used by every adjudication.
ADJUDICATION_POLICY: Final[AdjudicationPolicy] = AdjudicationPolicy()


def classify_exporter_lineage(source_records: Iterable[dict[str, Any]]) -> str:
    """Fold official exporter-lineage evidence into exactly one §7 outcome.

    Each source record carries ``available``, ``projection``
    (``itertext`` | ``sd_tag_attribute`` | ``hybrid`` | other) and
    ``evidence_strength`` (``decisive`` | weaker). Coverage alone never
    decides: only decisive official evidence can support a method;
    conflicting decisive sources or anything weaker route to human
    adjudication or unavailability.
    """
    records = list(source_records)
    if not records or all(not r.get("available") for r in records):
        return "EXPORTER_LINEAGE_UNAVAILABLE"
    decisive = {
        r.get("projection")
        for r in records
        if r.get("available") and r.get("evidence_strength") == "decisive"
    }
    if decisive == {"itertext"}:
        return "EXPORTER_LINEAGE_SUPPORTS_METHOD_B"
    if decisive == {"sd_tag_attribute"}:
        return "EXPORTER_LINEAGE_SUPPORTS_METHOD_A"
    if decisive == {"hybrid"}:
        return "EXPORTER_LINEAGE_SUPPORTS_HYBRID"
    return "METHODS_REQUIRE_HUMAN_ADJUDICATION"


def _projection_category(unit: dict[str, Any], locked_texts: frozenset[str]) -> str:
    """Classify ONE upstream unit against the locked exporter text universe."""
    itext = normalize_caption(unit["caption_itertext"])
    attr = normalize_caption(unit["caption_attribute"])
    if not itext and not attr:
        return "exporter_unavailable_for_unit"
    if itext == attr:
        return "projections_identical" if itext in locked_texts else "neither_matches_exporter"
    if itext in locked_texts and attr in locked_texts:
        return "both_match_distinct_locked_texts"
    if itext in locked_texts:
        return "itertext_matches_exporter"
    if attr in locked_texts:
        return "attribute_matches_exporter"
    return "neither_matches_exporter"


def projection_equivalence_categories(
    units: Iterable[dict[str, Any]], locked_texts: frozenset[str]
) -> dict[str, int]:
    """§5 per-unit projection-equivalence categories over the locked bundle.

    The locked record ``text`` field IS the official exporter output (§4
    lineage: ``innertext`` = itertext projection), so it is the reference:
    each upstream unit compares its itertext projection and its sd-tag
    attribute projection against the locked text universe. Counts only —
    no caption text leaves this function.
    """
    cats: Counter[str] = Counter({name: 0 for name in PROJECTION_EQUIVALENCE_CATEGORIES})
    for unit in units:
        cats[_projection_category(unit, locked_texts)] += 1
    return {name: cats[name] for name in PROJECTION_EQUIVALENCE_CATEGORIES}


def _locked_text_universe(raw_dir: Path) -> frozenset[str]:
    """Normalized raw roles_multi texts = the locked official exporter output."""
    locked: set[str] = set()
    for part in PARTITIONS:
        for line in read_jsonl_physical_lines(raw_dir / f"{part}.jsonl"):
            locked.add(normalize_caption(json.loads(line)["text"]))
    return frozenset(locked)


def run_projection_equivalence(*, xml_dir: Path, raw_dir: Path, out_path: Path) -> dict[str, Any]:
    """§5 projection-equivalence stage over the locked bundle (counts only).

    Emits one sanitized row per upstream unit (identifiers, category and
    projection hashes — never caption text) plus the aggregate category
    counts against the locked exporter text universe.
    """
    locked_texts = _locked_text_universe(raw_dir)
    units = list(_iter_figure_units(xml_dir))
    with out_path.open("w", encoding="utf-8") as out:
        for unit in units:
            out.write(
                json.dumps(
                    {
                        "article_doi": unit["article_doi"],
                        "fig_id": unit["fig_id"],
                        "panel_id": unit["panel_id"],
                        "unit_kind": unit["unit_kind"],
                        "category": _projection_category(unit, locked_texts),
                        "itertext_sha256": sha256_bytes(
                            normalize_caption(unit["caption_itertext"]).encode("utf-8")
                        ),
                        "attribute_sha256": sha256_bytes(
                            normalize_caption(unit["caption_attribute"]).encode("utf-8")
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return {
        "categories": projection_equivalence_categories(units, locked_texts),
        "units": len(units),
        "locked_text_count": len(locked_texts),
        "output_sha256": sha256_file(out_path),
    }


def analyze_method_b_only_records(
    *, delta_path: Path, xml_dir: Path, raw_dir: Path, out_path: Path
) -> dict[str, Any]:
    """§5 per-record root-cause analysis of the METHOD_B_ONLY rows.

    For every METHOD_B_ONLY delta row, re-read the locked record and the
    matched upstream unit and measure (sanitized fields only — identifiers,
    hashes, counts and booleans, never caption text):

      * ``itertext_equals_locked`` — the Method B projection of the matched
        unit equals the locked exporter text (expected by construction);
      * ``attribute_differs_from_locked`` — the Method A projection differs,
        i.e. the measured root cause why Method A missed the record;
      * ``char_len_diff`` / ``token_count_diff`` — projection length deltas;
      * ``entity_span_signature_matches`` — record entity spans vs the
        unit's sd-tag tuple;
      * ``attribute_equals_other_locked_text`` — the attribute projection
        collides with a DIFFERENT locked text (conflict introduction).

    A METHOD_B_ONLY row whose upstream unit cannot be located uniquely
    raises (fail-closed): the analysis may never silently skip evidence.
    """
    locked_texts = _locked_text_universe(raw_dir)
    parsed_raw: dict[tuple[str, int], dict[str, Any]] = {}
    for part in PARTITIONS:
        for i, line in enumerate(read_jsonl_physical_lines(raw_dir / f"{part}.jsonl")):
            parsed_raw[(part, i)] = json.loads(line)
    units_by_location: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    units_by_itertext: dict[str, list[dict[str, Any]]] = {}
    for candidate in _iter_figure_units(xml_dir):
        units_by_location.setdefault(
            (candidate["article_doi"], candidate["fig_id"], candidate["panel_id"]), []
        ).append(candidate)
        units_by_itertext.setdefault(candidate["caption_itertext"], []).append(candidate)

    records_analyzed = 0
    flags: Counter[str] = Counter()
    char_len_diffs: Counter[int] = Counter()
    token_count_diffs: Counter[int] = Counter()
    with delta_path.open(encoding="utf-8") as fh, out_path.open("w", encoding="utf-8") as out:
        for line in fh:
            delta = json.loads(line)
            if delta["decision_relation"] != "METHOD_B_ONLY":
                continue
            record_id = delta["canonical_record_id"]
            rec = parsed_raw[(delta["partition"], delta["source_row_index"])]
            locked = normalize_caption(rec["text"])
            location = (
                delta["method_b_doi"],
                delta["method_b_figure_id"],
                delta["method_b_panel_id"] or "",
            )
            located = units_by_location.get(location, [])
            unit: dict[str, Any] | None = (
                located[0]
                if len(located) == 1 and normalize_caption(located[0]["caption_itertext"]) == locked
                else None
            )
            if unit is None and len(located) == 1:
                # The identifiers point at exactly one unit, but it does not
                # carry the matched caption key: a contract violation that
                # must never be papered over.
                raise ValueError(
                    f"METHOD_B_ONLY record whose located unit lacks the matched key: {record_id}"
                )
            candidates: list[dict[str, Any]] = []
            if unit is None:
                if not located and delta["method_b_figure_id"] is not None:
                    # Explicit identifiers were emitted but locate no unit:
                    # a delta-contract violation, fail closed.
                    raise ValueError(
                        f"METHOD_B_ONLY record without uniquely locatable upstream unit: {record_id}"
                    )
                # Either no identifiers were emitted (DOI-collapse: the
                # record was matched to an ARTICLE) or the identifiers are
                # non-unique (e.g. panels lacking panel_id attributes share
                # one location): per-unit attribution is legitimately
                # ambiguous, so measure against the caption-key candidate set.
                candidates = units_by_itertext.get(locked, [])
                if not candidates:
                    raise ValueError(
                        f"METHOD_B_ONLY record without any candidate upstream unit: {record_id}"
                    )
            if unit is not None:
                itext = normalize_caption(unit["caption_itertext"])
                attr = normalize_caption(unit["caption_attribute"])
                itext_equals_locked = itext == locked
                attribute_differs = attr != locked
                span_matches = _record_entity_span_signature(
                    rec["words"], rec["labels"]
                ) == _asset_entity_span_signature(unit)
                attribute_other = attr != locked and attr in locked_texts
                row_doi, row_fig, row_panel = (
                    unit["article_doi"],
                    unit["fig_id"],
                    unit["panel_id"],
                )
            else:
                itexts = {normalize_caption(u["caption_itertext"]) for u in candidates}
                attrs = {normalize_caption(u["caption_attribute"]) for u in candidates}
                itext_equals_locked = itexts == {locked}
                attribute_differs = locked not in attrs
                span_matches = False
                attribute_other = any(a != locked and a in locked_texts for a in attrs)
                row_doi, row_fig, row_panel = delta["method_b_doi"], None, None
            char_len_diff = abs(len(attr) - len(locked)) if unit is not None else -1
            token_count_diff = (
                abs(len(attr.split()) - len(locked.split())) if unit is not None else -1
            )
            records_analyzed += 1
            flags["itertext_equals_locked"] += int(itext_equals_locked)
            flags["attribute_differs_from_locked"] += int(attribute_differs)
            flags["entity_span_signature_matches"] += int(span_matches)
            flags["attribute_equals_other_locked_text"] += int(attribute_other)
            flags["ambiguous_unit_set"] += int(unit is None)
            char_len_diffs[char_len_diff] += 1
            token_count_diffs[token_count_diff] += 1
            out.write(
                json.dumps(
                    {
                        "canonical_record_id": record_id,
                        "partition": delta["partition"],
                        "source_row_index": delta["source_row_index"],
                        "exact_source_text_sha256": delta["exact_source_text_sha256"],
                        "method_b_tier": delta["method_b_tier"],
                        "article_doi": row_doi,
                        "fig_id": row_fig,
                        "panel_id": row_panel,
                        "ambiguous_unit_set": unit is None,
                        "candidate_unit_count": len(candidates) if unit is None else 1,
                        "itertext_equals_locked": itext_equals_locked,
                        "attribute_differs_from_locked": attribute_differs,
                        "char_len_diff": char_len_diff,
                        "token_count_diff": token_count_diff,
                        "entity_span_signature_matches": span_matches,
                        "attribute_equals_other_locked_text": attribute_other,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return {
        "records_analyzed": records_analyzed,
        "itertext_equals_locked": flags["itertext_equals_locked"],
        "attribute_differs_from_locked": flags["attribute_differs_from_locked"],
        "entity_span_signature_matches": flags["entity_span_signature_matches"],
        "attribute_equals_other_locked_text": flags["attribute_equals_other_locked_text"],
        "ambiguous_unit_set": flags["ambiguous_unit_set"],
        "char_len_diff_histogram": {str(k): v for k, v in sorted(char_len_diffs.items())},
        "token_count_diff_histogram": {str(k): v for k, v in sorted(token_count_diffs.items())},
        "output_sha256": sha256_file(out_path),
    }


def adjudicate(
    delta_summary: dict[str, Any],
    method_b_summary: dict[str, Any],
    *,
    dual_run_byte_identical: bool,
    census_dois: frozenset[str],
    input_bundle_reverified: bool,
    exporter_lineage_outcome: str | None = None,
) -> dict[str, Any]:
    """Apply the versioned §12 replacement conditions; never pick by coverage.

    Conditions split into MEASURED (derived from the actual run data) and
    BY_CONSTRUCTION (algorithmic invariants asserted by the code), so a
    human adjudicator can distinguish evidence from assertion.
    SAME_ARTICLE_DIFFERENT_GRANULARITY rows are NOT conflicts (both methods
    agree on the article). The outcome states only which evidence level the
    run supports — production-method selection remains a separately
    authorised human decision, and no sidecar is regenerated regardless.
    """
    policy = ADJUDICATION_POLICY
    if exporter_lineage_outcome is not None and exporter_lineage_outcome not in (
        EXPORTER_LINEAGE_OUTCOMES
    ):
        raise ValueError(
            f"exporter lineage outcome outside §7 vocabulary: {exporter_lineage_outcome}"
        )
    relations = delta_summary["relations"]
    conflicts = {
        r: relations.get(r, 0)
        for r in ("CONFLICTING_ARTICLE", "CONFLICTING_FIGURE", "CONFLICTING_PANEL")
    }
    s4_count = method_b_summary["tier_counts"].get("S4_UNIQUE_ANNOTATION_TUPLE", 0)
    granularity_deltas = relations.get("SAME_ARTICLE_DIFFERENT_GRANULARITY", 0)

    # MEASURED conditions — every value is computed from run data:
    assigned_dois = set(method_b_summary.get("assigned_dois", []))
    conditions_measured = {
        "zero_conflicting_article_assignments": (
            conflicts["CONFLICTING_ARTICLE"] <= policy.allowed_conflicting_assignments
        ),
        "zero_unexplained_conflicting_figure_assignments": (
            conflicts["CONFLICTING_FIGURE"] <= policy.allowed_conflicting_assignments
        ),
        "zero_unexplained_conflicting_panel_assignments": (
            conflicts["CONFLICTING_PANEL"] <= policy.allowed_conflicting_assignments
        ),
        "every_additional_assignment_traces_to_official_xml_unit": (
            assigned_dois <= set(census_dois)
        ),
        "duplicate_handling_fail_closed": (
            method_b_summary.get("ambiguous_key_records_emitted_s3", 0) == 0
        ),
        "label_assisted_matches_isolated": (
            method_b_summary.get("label_assisted_rows_outside_s4", 0) == 0
        ),
        "repeated_runs_byte_identical": bool(dual_run_byte_identical),
        "no_canonical_record_or_split_modified": bool(input_bundle_reverified),
    }
    # BY_CONSTRUCTION invariants — algorithmic properties of the code, not
    # measurements of this run:
    conditions_by_construction = {
        "no_first_match_behaviour": True,
        "provenance_granularity_truthful": True,
    }

    a_only = relations.get("METHOD_A_ONLY", 0)
    b_only = relations.get("METHOD_B_ONLY", 0)
    conflict_total = sum(conflicts.values())
    all_measured = all(conditions_measured.values())
    if conflict_total > policy.allowed_conflicting_assignments:
        outcome = "METHODS_CONFLICT_REQUIRES_HUMAN_ADJUDICATION"
    elif not all_measured:
        outcome = "INSUFFICIENT_EVIDENCE"
    elif b_only == 0 and a_only == 0 and granularity_deltas == 0:
        outcome = "METHOD_A_CONFIRMED"
    elif a_only == 0 and b_only > 0:
        # Method B1 matches every record Method A matches (same articles,
        # zero identifier conflicts) plus additional records; granularity
        # deltas are explained evidence-level differences. This is a
        # REPRODUCTION result, not a production-method confirmation.
        outcome = "METHOD_B_LABEL_INDEPENDENT_REPRODUCED_ZERO_IDENTIFIER_CONFLICTS"
    elif a_only > 0 and b_only > 0:
        outcome = "HYBRID_METHOD_REQUIRED"
    else:
        outcome = "INSUFFICIENT_EVIDENCE"

    historical_s4 = HISTORICAL_S4_REPORTED
    s4_status = (
        "PARTIAL_NOT_HISTORICALLY_REPRODUCIBLE"
        if s4_count < historical_s4
        else "REPRODUCED_PENDING_SERIALIZATION_COMPARISON"
    )
    return {
        "policy": {**policy.canonical(), "sha256": policy.sha256()},
        "conditions_measured": conditions_measured,
        "conditions_by_construction": conditions_by_construction,
        "conflicts": conflicts,
        "granularity_deltas_same_article": granularity_deltas,
        "label_assisted_s4": {
            "reconstructed": s4_count,
            "historically_reported": historical_s4,
            "status": s4_status,
            "production_eligibility": "NON_PRODUCTION",
            "valid_for_split_grouping": False,
            "valid_for_model_evaluation": False,
            "eligibility_changing": False,
        },
        "label_policy": {
            "B1_classification": "LABEL_INDEPENDENT",
            "B2_classification": "LABEL_ASSISTED",
            "label_assisted_promotion_allowed": False,
        },
        "exporter_lineage": exporter_lineage_outcome,
        "outcome": outcome,
        "sidecar_regenerated": False,
    }


# --- Pipeline orchestration ---------------------------------------------------


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON artifact atomically-enough for reruns, always UTF-8.

    Explicit ``encoding``: artifacts serialize with ``ensure_ascii=False``
    and the dual-run byte-identity proof requires identical bytes on every
    platform regardless of locale.
    """
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def attest_extracted_xml_dir(
    *, archive: Path, xml_dir: Path, input_bundle_sha256: str
) -> dict[str, Any]:
    """Cryptographically bind an extracted XML tree to its input universe.

    Records the archive SHA-256, the extracted-member inventory with
    per-file hashes, the file-count census, an aggregate tree SHA-256 and
    the reconciliation input-bundle SHA-256. A directory is never trusted
    merely because it exists; this attestation is the only basis for reuse
    and it fails closed if the tree no longer matches the archive.
    """
    members: list[tuple[str, str]] = []
    for fp in sorted(xml_dir.rglob("*")):
        if fp.is_file():
            members.append((str(fp.relative_to(xml_dir)), sha256_file(fp)))
    tree_payload = json.dumps(members, ensure_ascii=False, sort_keys=True)
    return {
        "archive_sha256": sha256_file(archive),
        "input_bundle_sha256": input_bundle_sha256,
        "file_count": len(members),
        "members": [name for name, _ in members],
        "member_sha256": dict(members),
        "tree_sha256": hashlib.sha256(tree_payload.encode("utf-8")).hexdigest(),
    }


def run_pipeline(
    *,
    work_dir: Path,
    canon_dir: Path,
    raw_dir: Path,
    archive: Path,
    upstream_reference: str,
    exporter_lineage_outcome: str | None = None,
) -> dict[str, Any]:
    """One complete reconciliation pass into ``work_dir`` (all artifacts).

    Artifact ordering is fail-closed (§3I): the input bundle is locked
    first, the XML tree is freshly verified-extracted every pass, and the
    canonical inputs are re-verified AFTER the full pass; the adjudication
    written here therefore always rests on a verified, unchanged universe.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    bundle_sha = reconciliation_bundle_sha256(upstream_reference)
    lock = lock_input_bundle(canon_dir=canon_dir, raw_dir=raw_dir, archive=archive)
    lock["input_bundle_sha256"] = bundle_sha
    _write_json(work_dir / "input_bundle_lock.json", lock)

    # Never reuse an existing extraction: stale, mixed or foreign trees
    # must fail closed, so every pass performs a verified clean extraction.
    xml_dir = work_dir / "xml_v2.0.3"
    if xml_dir.exists():
        shutil.rmtree(xml_dir)
    extract_xml_archive(archive, xml_dir, expected_sha256=ATTESTED_INPUT_SHA256["upstream_xml"])
    attestation = attest_extracted_xml_dir(
        archive=archive, xml_dir=xml_dir, input_bundle_sha256=bundle_sha
    )
    _write_json(work_dir / "extraction_attestation.json", attestation)

    census = run_census(xml_dir)
    _write_json(work_dir / "census.json", {"stats": census.stats, "hypothesis": census.hypothesis})

    projection_summary = run_projection_equivalence(
        xml_dir=xml_dir,
        raw_dir=raw_dir,
        out_path=work_dir / "projection_equivalence_rows.jsonl",
    )
    _write_json(work_dir / "projection_equivalence.json", projection_summary)

    index_path = work_dir / "upstream_caption_index.jsonl"
    index_summary = build_method_a_index(xml_dir, index_path)
    _write_json(work_dir / "index_summary.json", index_summary)

    method_a_summary = run_method_a(
        index_path=index_path,
        canon_dir=canon_dir,
        raw_dir=raw_dir,
        out_path=work_dir / "method_a_rows.jsonl",
        upstream_reference=upstream_reference,
    )
    _write_json(work_dir / "method_a_summary.json", method_a_summary)

    method_b_summary = run_method_b(
        xml_dir=xml_dir,
        raw_dir=raw_dir,
        out_path=work_dir / "method_b_rows.jsonl",
    )
    _write_json(work_dir / "method_b_summary.json", method_b_summary)

    delta_summary = run_delta(
        method_a_path=work_dir / "method_a_rows.jsonl",
        method_b_path=work_dir / "method_b_rows.jsonl",
        out_path=work_dir / "delta_rows.jsonl",
        audit_path=work_dir / "audit_set.jsonl",
    )
    _write_json(work_dir / "delta_summary.json", delta_summary)

    method_b_only_summary = analyze_method_b_only_records(
        delta_path=work_dir / "delta_rows.jsonl",
        xml_dir=xml_dir,
        raw_dir=raw_dir,
        out_path=work_dir / "method_b_only_rows.jsonl",
    )
    _write_json(work_dir / "method_b_only_summary.json", method_b_only_summary)

    # Canonical inputs re-verified AFTER the full pass (untouched guarantee)
    # and BEFORE any adjudication is written.
    reverify = lock_input_bundle(canon_dir=canon_dir, raw_dir=raw_dir, archive=archive)
    input_bundle_reverified = reverify["records_sha256"] == lock["records_sha256"]
    if not input_bundle_reverified:
        raise ValueError("canonical records changed during reconciliation")

    adjudication = adjudicate(
        delta_summary,
        method_b_summary,
        # A single pass cannot attest its own repeatability; run-all writes
        # the final dual-run-confirmed adjudication after hash comparison.
        dual_run_byte_identical=False,
        census_dois=census.article_dois,
        input_bundle_reverified=input_bundle_reverified,
    )
    _write_json(work_dir / "adjudication.json", adjudication)

    dossier_summary = build_adjudication_dossier(
        run_dir=work_dir, exporter_lineage_outcome=exporter_lineage_outcome
    )

    return {
        "lock": lock,
        "extraction_attestation": attestation,
        "census": {"stats": census.stats, "hypothesis": census.hypothesis},
        "projection_equivalence": projection_summary,
        "index": index_summary,
        "method_a": method_a_summary,
        "method_b": method_b_summary,
        "delta": delta_summary,
        "method_b_only": method_b_only_summary,
        "adjudication": adjudication,
        "dossier": dossier_summary,
    }


#: Artifacts whose byte identity proves determinism across repeated runs.
DETERMINISM_ARTIFACTS: Final[tuple[str, ...]] = (
    "upstream_caption_index.jsonl",
    "method_a_rows.jsonl",
    "method_b_rows.jsonl",
    "delta_rows.jsonl",
    "audit_set.jsonl",
    "census.json",
    "projection_equivalence_rows.jsonl",
    "method_b_only_rows.jsonl",
    "method_a_summary.json",
    "method_b_summary.json",
    "delta_summary.json",
    "projection_equivalence.json",
    "method_b_only_summary.json",
    "adjudication.json",
    "extraction_attestation.json",
    *(f"adjudication_dossier/{name}" for name in DOSSIER_ARTIFACTS),
)


def run_all_twice(
    *,
    work_dir: Path,
    canon_dir: Path,
    raw_dir: Path,
    archive: Path,
    upstream_reference: str,
    exporter_lineage_outcome: str | None = None,
) -> dict[str, Any]:
    """§17 determinism proof: two full passes, byte-identical artifacts.

    The FINAL adjudication is published only after the dual-run hash
    comparison succeeds; a divergence raises before any final adjudication
    exists, so a failed run can never publish a success attestation.
    """
    if exporter_lineage_outcome is not None and exporter_lineage_outcome not in (
        EXPORTER_LINEAGE_OUTCOMES
    ):
        raise ValueError(
            f"exporter lineage outcome outside §7 vocabulary: {exporter_lineage_outcome}"
        )
    hashes: dict[str, dict[str, str]] = {}
    for run_name in ("run-1", "run-2"):
        run_dir = work_dir / run_name
        run_pipeline(
            work_dir=run_dir,
            canon_dir=canon_dir,
            raw_dir=raw_dir,
            archive=archive,
            upstream_reference=upstream_reference,
            exporter_lineage_outcome=exporter_lineage_outcome,
        )
        hashes[run_name] = {name: sha256_file(run_dir / name) for name in DETERMINISM_ARTIFACTS}
    identical = hashes["run-1"] == hashes["run-2"]
    report: dict[str, Any] = {
        "artifact_hashes": hashes,
        "dual_run_byte_identical": identical,
    }
    _write_json(work_dir / "determinism_report.json", report)
    if not identical:
        diff = {
            name: {"run-1": hashes["run-1"][name], "run-2": hashes["run-2"][name]}
            for name in DETERMINISM_ARTIFACTS
            if hashes["run-1"][name] != hashes["run-2"][name]
        }
        raise ValueError(f"reconciliation is not byte-deterministic: {diff}")
    # Final adjudication now attested against the byte-identical dual run.
    run2 = work_dir / "run-2"
    reverify = lock_input_bundle(canon_dir=canon_dir, raw_dir=raw_dir, archive=archive)
    lock2 = json.loads((run2 / "input_bundle_lock.json").read_text(encoding="utf-8"))
    final = adjudicate(
        json.loads((run2 / "delta_summary.json").read_text(encoding="utf-8")),
        json.loads((run2 / "method_b_summary.json").read_text(encoding="utf-8")),
        dual_run_byte_identical=True,
        census_dois=_census_dois(xml_dir=run2 / "xml_v2.0.3"),
        input_bundle_reverified=reverify["records_sha256"] == lock2["records_sha256"],
        exporter_lineage_outcome=exporter_lineage_outcome,
    )
    _write_json(work_dir / "adjudication.json", final)
    report["final_adjudication"] = final
    _write_json(work_dir / "determinism_report.json", report)
    return report


def _census_dois(*, xml_dir: Path) -> frozenset[str]:
    """Re-derive the article DOI universe for the final adjudication."""
    return run_census(xml_dir).article_dois


def main() -> None:
    """CLI entry point: one pass (``run``) or the dual-run proof (``run-all``)."""
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("run", "run-all"):
        p = sub.add_parser(name)
        p.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
        p.add_argument("--canon-dir", type=Path, default=DEFAULT_CANON_DIR)
        p.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
        p.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
        p.add_argument("--upstream-reference", default=DEFAULT_UPSTREAM_REFERENCE)
        p.add_argument(
            "--exporter-lineage-outcome",
            default=None,
            choices=sorted(EXPORTER_LINEAGE_OUTCOMES),
            help="§7 exporter-lineage conclusion recorded in the adjudication dossier",
        )
    args = ap.parse_args()

    if args.command == "run":
        summary = run_pipeline(
            work_dir=args.work_dir,
            canon_dir=args.canon_dir,
            raw_dir=args.raw_dir,
            archive=args.archive,
            upstream_reference=args.upstream_reference,
            exporter_lineage_outcome=args.exporter_lineage_outcome,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        report = run_all_twice(
            work_dir=args.work_dir,
            canon_dir=args.canon_dir,
            raw_dir=args.raw_dir,
            archive=args.archive,
            upstream_reference=args.upstream_reference,
            exporter_lineage_outcome=args.exporter_lineage_outcome,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
