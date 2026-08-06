"""Sidecar migration step 2: deterministic dual-build + validation + write.

Fail-closed orchestrator for the SourceData provenance sidecar (schema 0.2.0):

  1. preflight: canonical records_sha256, per-file canonical JSONL hashes,
     raw roles_multi hashes and counts;
  2. build the complete sidecar twice in separate staging directories;
  3. require byte-for-byte equality (content, order, SHA-256, tiers, keys);
  4. schema-validate every row and join 1:1 back to the canonical records;
  5. require the audited tier counts exactly
     (69,983 panel / 175 figure / 3,914 article / 1,091 fallback);
  6. only then (--write) atomically write the sidecar to the external
     provenance directory and re-hash it after rename. ``--replace`` permits
     superseding an existing sidecar, but only when its pre-hash matches the
     explicitly expected superseded SHA-256.

Canonical TaskRecord JSONL, manifests and leakage audit are never touched
here; the external manifest metadata update is a separate, explicitly
authorised step.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ntruth.data.fs import atomic_write_text
from ntruth.task_corpora.io_util import read_jsonl_physical_lines, records_content_sha256
from ntruth.task_corpora.provenance_sidecar import (
    ALGORITHM_VERSION,
    PARTITIONS,
    SCHEMA_VERSION,
    SidecarRow,
    build_sidecar_rows,
    sha256_bytes,
    sha256_file,
    validate_sidecar_rows,
)

EXPECTED_RECORDS_SHA256 = "562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10"
EXPECTED_CANONICAL_JSONL_SHA256 = {
    "train": "f2e7bc675294b2a041dee4481c344cc40e093364391e55a3e7a2417e7fe6b18c",
    "validation": "76d2fc01d7cb6a96e41dda45e9bdb116e37eae38552c1eedb45d6377163fe886",
    "test": "6bbc05663c6c18b490217d6eed8f70ebeb199330b58a322d150b9eb633817b9c",
}
EXPECTED_LEAKAGE_AUDIT_SHA256 = "d79c65f12a857e837923ea916b1062f321a4064f498597753f134ac3e92f46e7"
EXPECTED_RAW_SHA256 = {
    "train": "c2ac812846265686502469208dae435a5dc5279d6149940409f3b4566764c925",
    "validation": "d2e98f0e71905e18cc4dbe208646113ddb4b869cf06d53af628156f6e1493715",
    "test": "f7fbee9acd7e7f52ed92944d3d719c83164ba75e18218841d3dc764956c21a75",
}
EXPECTED_XML_SHA256 = "71f9899211efef62bc523275bbff7ba3e37ec8b4d1fc21405b58f4b68e93ba60"
EXPECTED_TIER_COUNTS = {
    "TIER_1_PANEL_UNIQUE": 69983,
    "TIER_1_FIGURE_UNIQUE": 175,
    "TIER_2_ARTICLE_ONLY": 3914,
    "RECORD_FALLBACK": 1091,
}
EXPECTED_TOTAL = 75163


def _build_once(
    *, index: Path, raw_dir: Path, canon_dir: Path, upstream_reference: str
) -> tuple[bytes, list[SidecarRow]]:
    rows = build_sidecar_rows(
        index_path=index,
        raw_dir=raw_dir,
        canon_dir=canon_dir,
        upstream_asset_sha256=EXPECTED_XML_SHA256,
        upstream_reference=upstream_reference,
        expected_records_sha256=EXPECTED_RECORDS_SHA256,
        expected_raw_sha256=EXPECTED_RAW_SHA256,
    )
    blob = b"".join(r.to_jsonl_bytes() for r in rows)
    return blob, rows


def _article_crossing_diagnostic(rows: list[SidecarRow]) -> dict[str, object]:
    article_splits: dict[str, set[str]] = {}
    matched = 0
    for r in rows:
        if r.provenance_tier == "RECORD_FALLBACK":
            continue  # diagnostic explicitly excludes fallback records
        matched += 1
        assert r.article_doi is not None
        article_splits.setdefault(r.article_doi, set()).add(r.partition)
    crossing = {d: sorted(s) for d, s in article_splits.items() if len(s) > 1}
    return {
        "matched_subset_records": matched,
        "matched_subset_articles": len(article_splits),
        "matched_subset_articles_crossing_existing_splits": len(crossing),
        "fallback_records_excluded_from_diagnostic": len(rows) - matched,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--canon-dir", required=True, type=Path)
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--staging-root", required=True, type=Path)
    ap.add_argument("--upstream-reference", required=True)
    ap.add_argument("--write", type=Path, default=None, help="atomic external write target")
    ap.add_argument(
        "--replace",
        action="store_true",
        help="permit superseding an existing sidecar (requires --expect-superseded-sha)",
    )
    ap.add_argument(
        "--expect-superseded-sha",
        default=None,
        help="SHA-256 the pre-existing sidecar must hash to before replacement",
    )
    args = ap.parse_args()

    # -- preflight ------------------------------------------------------------
    canon_lines: list[str] = []
    for part in PARTITIONS:
        canon_path = args.canon_dir / f"{part}.jsonl"
        actual_file_sha = sha256_file(canon_path)
        if actual_file_sha != EXPECTED_CANONICAL_JSONL_SHA256[part]:
            raise SystemExit(
                f"canonical {part}.jsonl sha256 mismatch: {actual_file_sha} "
                f"!= {EXPECTED_CANONICAL_JSONL_SHA256[part]}"
            )
        canon_lines.extend(read_jsonl_physical_lines(canon_path))
    leakage_audit_path = args.canon_dir / "leakage_audit.json"
    if leakage_audit_path.exists():
        actual_leakage = sha256_file(leakage_audit_path)
        if actual_leakage != EXPECTED_LEAKAGE_AUDIT_SHA256:
            raise SystemExit(f"leakage_audit.json sha256 mismatch: {actual_leakage}")
    actual_records = records_content_sha256(canon_lines)
    if actual_records != EXPECTED_RECORDS_SHA256:
        raise SystemExit(f"records_sha256 mismatch: {actual_records}")
    if len(canon_lines) != EXPECTED_TOTAL:
        raise SystemExit(f"canonical record count mismatch: {len(canon_lines)}")

    # -- deterministic dual build ----------------------------------------------
    build_a = args.staging_root / "build-a"
    build_b = args.staging_root / "build-b"
    build_a.mkdir(parents=True, exist_ok=True)
    build_b.mkdir(parents=True, exist_ok=True)
    blob_a, rows_a = _build_once(
        index=args.index,
        raw_dir=args.raw_dir,
        canon_dir=args.canon_dir,
        upstream_reference=args.upstream_reference,
    )
    blob_b, _ = _build_once(
        index=args.index,
        raw_dir=args.raw_dir,
        canon_dir=args.canon_dir,
        upstream_reference=args.upstream_reference,
    )
    if blob_a != blob_b:
        raise SystemExit("deterministic dual-build mismatch: builds are not byte-identical")

    # -- schema validation + 1:1 join -------------------------------------------
    payload = [json.loads(line) for line in blob_a.decode("utf-8").splitlines()]
    canonical_ids = set()
    for line in canon_lines:
        canonical_ids.add(json.loads(line)["record_id"])
    validation = validate_sidecar_rows(payload, canonical_record_ids=canonical_ids)

    # -- tier counts must reproduce exactly --------------------------------------
    tier_counts = validation["tier_counts"]
    assert isinstance(tier_counts, dict)
    if tier_counts != EXPECTED_TIER_COUNTS:
        raise SystemExit(f"tier count drift: {tier_counts} != {EXPECTED_TIER_COUNTS}")
    diagnostic = _article_crossing_diagnostic(rows_a)

    sidecar_sha = sha256_bytes(blob_a)
    report = {
        "sidecar_rows": len(rows_a),
        "sidecar_bytes": len(blob_a),
        "sidecar_sha256": sidecar_sha,
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "input_records_sha256": actual_records,
        "upstream_archive_sha256": EXPECTED_XML_SHA256,
        "upstream_reference": args.upstream_reference,
        "dual_build_byte_identical": True,
        "validation": validation,
        "tier_counts": tier_counts,
        "diagnostic": diagnostic,
    }
    (build_a / "sidecar.jsonl").write_bytes(blob_a)
    (build_a / "build_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if args.write is not None:
        if args.write.exists():
            if not args.replace:
                raise SystemExit(f"refusing to overwrite existing sidecar: {args.write}")
            if not args.expect_superseded_sha:
                raise SystemExit("--replace requires --expect-superseded-sha")
            pre = sha256_file(args.write)
            if pre != args.expect_superseded_sha:
                raise SystemExit(
                    f"existing sidecar sha256 {pre} != expected superseded "
                    f"sha256 {args.expect_superseded_sha}; refusing to replace"
                )
            report["superseded_sidecar_sha256"] = pre
        atomic_write_text(args.write, blob_a.decode("utf-8"))
        post = sha256_file(args.write)
        if post != sidecar_sha:
            raise SystemExit(f"post-rename re-hash mismatch: {post} != {sidecar_sha}")
        report["written_path"] = str(args.write)
        report["post_rename_sha256"] = post
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
