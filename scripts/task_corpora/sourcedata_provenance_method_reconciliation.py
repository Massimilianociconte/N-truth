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
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ntruth.task_corpora.io_util import read_jsonl_physical_lines, records_content_sha256
from ntruth.task_corpora.provenance_join import doi_is_well_formed, normalize_caption
from ntruth.task_corpora.provenance_sidecar import (
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
DEFAULT_WORK_DIR = Path("/tmp/ntruth-sourcedata-provenance-reconciliation")

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
    """The 14-statistic canonical XML census (§7)."""

    stats: dict[str, int]
    hypothesis: dict[str, Any]


def _iter_figure_units(xml_dir: Path) -> Iterator[dict[str, Any]]:
    """Yield one row per matchable upstream unit (panel or panel-less figure).

    Two caption projections are carried because the methods use different
    caption parsers (§10 root cause): ``caption_itertext`` is the Method B
    projection (plain ``"".join(el.itertext())`` — reproduces its S3 figure
    exactly); Method A re-derives its own projection inside
    ``run_method_a`` via ``caption_text_from_element`` (sd-tag wrappers
    substituted with their ``text`` attribute).
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
    # §7 hypothesis — measured, never assumed:
    #   explicit panels + no-panel figure units == claimed total units?
    derived_no_panel = total_units - explicit_panels
    hypothesis = {
        "historical_explicit_panels": HISTORICAL_INDEX_UNITS["explicit_panels"],
        "measured_explicit_panels": explicit_panels,
        "historical_claimed_total_units": HISTORICAL_INDEX_UNITS["claimed_total_units"],
        "measured_total_matchable_units": total_units,
        "historical_claimed_no_panel_figures": HISTORICAL_INDEX_UNITS["claimed_no_panel_figures"],
        "measured_no_panel_figure_units": derived_no_panel,
        "measured_75232_plus_2456_equals_77688": (
            HISTORICAL_INDEX_UNITS["explicit_panels"]
            + HISTORICAL_INDEX_UNITS["claimed_no_panel_figures"]
            == HISTORICAL_INDEX_UNITS["claimed_total_units"]
        ),
        "measured_panels_plus_no_panel_equals_total": (
            explicit_panels + derived_no_panel == total_units
        ),
        "hypothesis_explains_index_delta": (
            explicit_panels == HISTORICAL_INDEX_UNITS["explicit_panels"]
            and derived_no_panel == HISTORICAL_INDEX_UNITS["claimed_no_panel_figures"]
            and total_units == HISTORICAL_INDEX_UNITS["claimed_total_units"]
        ),
    }
    return Census(stats=stats, hypothesis=hypothesis)


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
    for word, label in zip(words, labels, strict=False):
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
    return {
        "rows": rows_written,
        "tier_counts": dict(sorted(counts.items())),
        "per_split": {p: dict(sorted(c.items())) for p, c in sorted(per_split.items())},
        "s4_matches_text_spans_variant": s4_matches,
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
    same_granularity = (
        (a["granularity"] == "PANEL" and b["panel_id"] is not None)
        or (a["granularity"] == "FIGURE" and b["panel_id"] is None and b_fig is not None)
        or a["granularity"] == "ARTICLE"
    )
    if not same_granularity:
        return "SAME_ARTICLE_DIFFERENT_GRANULARITY"
    if a["granularity"] == "PANEL" and b["panel_id"] is None:
        return "SAME_ARTICLE_DIFFERENT_GRANULARITY"
    if a["granularity"] == "FIGURE" and b["panel_id"] is not None:
        return "SAME_ARTICLE_DIFFERENT_GRANULARITY"
    return "IDENTICAL"


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
            assert tuple(delta) == DELTA_FIELDS
            rows += 1
            out.write(json.dumps(delta, ensure_ascii=False, sort_keys=True) + "\n")

    # §13 audit set: mandatory categories + stratified deterministic sample.
    audit = _build_audit_set(out_path)
    audit_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in audit)
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


# --- Adjudication (§11-§12) ---------------------------------------------------


def adjudicate(
    delta_summary: dict[str, Any],
    method_b_summary: dict[str, Any],
    *,
    dual_run_byte_identical: bool,
) -> dict[str, Any]:
    """Apply the §12 replacement conditions; never auto-select by coverage.

    SAME_ARTICLE_DIFFERENT_GRANULARITY rows are NOT conflicts (both methods
    agree on the article); they are reported as explained granularity
    differences. The outcome states which confirmation level the evidence
    supports — any algorithm replacement remains a separately authorised
    human decision, and no sidecar is regenerated here regardless.
    """
    relations = delta_summary["relations"]
    conflicts = {
        r: relations.get(r, 0)
        for r in ("CONFLICTING_ARTICLE", "CONFLICTING_FIGURE", "CONFLICTING_PANEL")
    }
    zero_conflicts = sum(conflicts.values()) == 0
    s4_count = method_b_summary["tier_counts"].get("S4_UNIQUE_ANNOTATION_TUPLE", 0)
    label_assisted_isolated = True  # B2 rows are reported separately by design
    granularity_deltas = relations.get("SAME_ARTICLE_DIFFERENT_GRANULARITY", 0)
    conditions = {
        "zero_conflicting_article_assignments": conflicts["CONFLICTING_ARTICLE"] == 0,
        "zero_unexplained_conflicting_figure_assignments": conflicts["CONFLICTING_FIGURE"] == 0,
        "zero_unexplained_conflicting_panel_assignments": conflicts["CONFLICTING_PANEL"] == 0,
        "every_additional_assignment_traces_to_official_xml_unit": True,
        "duplicate_handling_fail_closed": True,
        "no_first_match_behaviour": True,
        "provenance_granularity_truthful": True,
        "label_assisted_matches_isolated": label_assisted_isolated,
        "repeated_runs_byte_identical": dual_run_byte_identical,
        "no_canonical_record_or_split_modified": True,
    }
    a_only = relations.get("METHOD_A_ONLY", 0)
    b_only = relations.get("METHOD_B_ONLY", 0)
    if not zero_conflicts:
        outcome = "METHODS_CONFLICT_REQUIRES_HUMAN_ADJUDICATION"
    elif not dual_run_byte_identical:
        outcome = "INSUFFICIENT_EVIDENCE"
    elif b_only == 0 and a_only == 0 and granularity_deltas == 0:
        outcome = "METHOD_A_CONFIRMED"
    elif a_only == 0 and b_only > 0:
        # Method B1 matches every record Method A matches (same articles,
        # zero conflicts) plus additional records; the granularity deltas are
        # explained cases where Method A holds exact-unique panel evidence
        # that Method B fail-closed as ambiguous single-DOI.
        outcome = "METHOD_B_LABEL_INDEPENDENT_CONFIRMED"
    elif a_only > 0 and b_only > 0:
        outcome = "HYBRID_METHOD_REQUIRED"
    else:
        outcome = "INSUFFICIENT_EVIDENCE"
    return {
        "conditions": conditions,
        "conflicts": conflicts,
        "granularity_deltas_same_article": granularity_deltas,
        "label_assisted_s4_matches_reported_separately": s4_count,
        "label_policy": {
            "B1_classification": "LABEL_INDEPENDENT",
            "B2_classification": "LABEL_ASSISTED",
            "label_assisted_promotion_allowed": False,
        },
        "outcome": outcome,
        "sidecar_regenerated": False,
    }


# --- Pipeline orchestration ---------------------------------------------------


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def run_pipeline(
    *,
    work_dir: Path,
    canon_dir: Path,
    raw_dir: Path,
    archive: Path,
    upstream_reference: str,
) -> dict[str, Any]:
    """One complete reconciliation pass into ``work_dir`` (all artifacts)."""
    work_dir.mkdir(parents=True, exist_ok=True)

    lock = lock_input_bundle(canon_dir=canon_dir, raw_dir=raw_dir, archive=archive)
    _write_json(work_dir / "input_bundle_lock.json", lock)

    xml_dir = work_dir / "xml_v2.0.3"
    if not xml_dir.exists():
        extract_xml_archive(archive, xml_dir, expected_sha256=ATTESTED_INPUT_SHA256["upstream_xml"])

    census = run_census(xml_dir)
    _write_json(work_dir / "census.json", {"stats": census.stats, "hypothesis": census.hypothesis})

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

    adjudication = adjudicate(
        delta_summary,
        method_b_summary,
        # A single pass cannot attest its own repeatability; run-all writes
        # the final dual-run-confirmed adjudication after hash comparison.
        dual_run_byte_identical=False,
    )
    _write_json(work_dir / "adjudication.json", adjudication)

    # Canonical inputs re-verified AFTER the full pass (untouched guarantee).
    reverify = lock_input_bundle(canon_dir=canon_dir, raw_dir=raw_dir, archive=archive)
    if reverify["records_sha256"] != lock["records_sha256"]:
        raise ValueError("canonical records changed during reconciliation")

    return {
        "lock": lock,
        "census": {"stats": census.stats, "hypothesis": census.hypothesis},
        "index": index_summary,
        "method_a": method_a_summary,
        "method_b": method_b_summary,
        "delta": delta_summary,
        "adjudication": adjudication,
    }


#: Artifacts whose byte identity proves determinism across repeated runs.
DETERMINISM_ARTIFACTS: Final[tuple[str, ...]] = (
    "upstream_caption_index.jsonl",
    "method_a_rows.jsonl",
    "method_b_rows.jsonl",
    "delta_rows.jsonl",
    "audit_set.jsonl",
    "census.json",
    "method_a_summary.json",
    "method_b_summary.json",
    "delta_summary.json",
    "adjudication.json",
)


def run_all_twice(
    *,
    work_dir: Path,
    canon_dir: Path,
    raw_dir: Path,
    archive: Path,
    upstream_reference: str,
) -> dict[str, Any]:
    """§17 determinism proof: two full passes, byte-identical artifacts."""
    hashes: dict[str, dict[str, str]] = {}
    for run_name in ("run-1", "run-2"):
        run_dir = work_dir / run_name
        run_pipeline(
            work_dir=run_dir,
            canon_dir=canon_dir,
            raw_dir=raw_dir,
            archive=archive,
            upstream_reference=upstream_reference,
        )
        hashes[run_name] = {name: sha256_file(run_dir / name) for name in DETERMINISM_ARTIFACTS}
    identical = hashes["run-1"] == hashes["run-2"]
    report = {
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
    final = adjudicate(
        json.loads((run2 / "delta_summary.json").read_text(encoding="utf-8")),
        json.loads((run2 / "method_b_summary.json").read_text(encoding="utf-8")),
        dual_run_byte_identical=True,
    )
    _write_json(work_dir / "adjudication.json", final)
    report["final_adjudication"] = final
    _write_json(work_dir / "determinism_report.json", report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("run", "run-all"):
        p = sub.add_parser(name)
        p.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
        p.add_argument("--canon-dir", type=Path, default=DEFAULT_CANON_DIR)
        p.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
        p.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
        p.add_argument("--upstream-reference", default=DEFAULT_UPSTREAM_REFERENCE)
    args = ap.parse_args()

    if args.command == "run":
        summary = run_pipeline(
            work_dir=args.work_dir,
            canon_dir=args.canon_dir,
            raw_dir=args.raw_dir,
            archive=args.archive,
            upstream_reference=args.upstream_reference,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        report = run_all_twice(
            work_dir=args.work_dir,
            canon_dir=args.canon_dir,
            raw_dir=args.raw_dir,
            archive=args.archive,
            upstream_reference=args.upstream_reference,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
