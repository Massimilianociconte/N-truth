"""Sidecar migration step 2: deterministic dual-build + validation + write.

Fail-closed orchestrator for the SourceData provenance sidecar (schema 0.2.0):

  1. preflight against the attested ProvenanceBuildInputs bundle: canonical
     records_sha256, per-file canonical JSONL hashes, raw roles_multi hashes,
     and the MANDATORY leakage_audit.json hash (a missing or replaced audit
     file stops the build before any generation or write);
  2. build the complete sidecar twice in separate staging directories;
  3. require byte-for-byte equality (content, order, SHA-256, tiers, keys);
  4. schema-validate every row and join 1:1 back to the canonical records;
  5. require the audited tier counts exactly
     (69,983 panel / 175 figure / 3,914 article / 1,091 fallback);
  6. only then (--write) atomically write the sidecar to the external
     provenance directory, re-hash it after rename and re-verify every
     canonical input hash. ``--replace`` permits superseding an existing
     sidecar, but only when its pre-hash matches the explicitly expected
     superseded SHA-256;
  7. publish the SUCCESS build report ONLY after all of the above passed;
     on any partial failure write an explicitly FAILED/ABORTED report.

Every report records ``input_bundle_sha256`` so a report from one input
bundle can never be accepted for an artifact generated from another.

Canonical TaskRecord JSONL, manifests and leakage audit are never touched
here; the external manifest metadata update is a separate, explicitly
authorised step.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ntruth.data.fs import atomic_write_text
from ntruth.task_corpora.io_util import read_jsonl_physical_lines, records_content_sha256
from ntruth.task_corpora.provenance_sidecar import (
    ALGORITHM_VERSION,
    PARTITIONS,
    SCHEMA_VERSION,
    ProvenanceBuildInputs,
    SidecarRow,
    abort_build_report,
    build_sidecar_rows,
    publish_build_report,
    sha256_bytes,
    sha256_file,
    validate_sidecar_rows,
    verify_provenance_build_inputs,
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

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def attest_caption_index(*, actual_sha256: str, expected_sha256: str) -> None:
    """Fail-closed attestation of the caption index BEFORE any build reads it.

    The index is derived from the attested upstream archive; every build must
    pin its SHA explicitly (the CLI makes ``--expect-index-sha`` mandatory),
    so an unattested or substituted index stops the build in preflight, not
    after the dual build or an external write.
    """
    if not _SHA256_HEX.fullmatch(expected_sha256):
        raise ValueError(f"--expect-index-sha must be a lowercase hex SHA-256: {expected_sha256!r}")
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"caption index sha256 {actual_sha256} != expected {expected_sha256}; "
            "refusing to build against an unattested caption index"
        )


def _attested_bundle(upstream_reference: str) -> ProvenanceBuildInputs:
    """Pin the immutable input contract consumed by every workflow stage."""
    return ProvenanceBuildInputs(
        canonical_records_sha256=EXPECTED_RECORDS_SHA256,
        canonical_train_sha256=EXPECTED_CANONICAL_JSONL_SHA256["train"],
        canonical_validation_sha256=EXPECTED_CANONICAL_JSONL_SHA256["validation"],
        canonical_test_sha256=EXPECTED_CANONICAL_JSONL_SHA256["test"],
        raw_roles_train_sha256=EXPECTED_RAW_SHA256["train"],
        raw_roles_validation_sha256=EXPECTED_RAW_SHA256["validation"],
        raw_roles_test_sha256=EXPECTED_RAW_SHA256["test"],
        leakage_audit_sha256=EXPECTED_LEAKAGE_AUDIT_SHA256,
        upstream_xml_sha256=EXPECTED_XML_SHA256,
        resolvable_upstream_reference=upstream_reference,
        dataset_version="2.0.3",
        sidecar_schema_version=SCHEMA_VERSION,
        matching_algorithm_version=ALGORITHM_VERSION,
    )


def parse_jsonl_blob(blob: bytes) -> list[dict[str, Any]]:
    """Parse a sidecar JSONL blob with U+2028-safe physical-line semantics.

    ``str.splitlines()`` is FORBIDDEN here: it also splits on U+000B,
    U+000C, U+001C-U+001E, U+0085, U+2028 and U+2029, and
    ``json.dumps(..., ensure_ascii=False)`` leaves several of those
    unescaped inside string values — one caption containing U+2028 would
    fragment a valid row into two invalid ones. The writer joins rows with
    ``"\\n"`` only, so the reader must split on ``"\\n"`` only.
    """
    return [json.loads(line) for line in blob.decode("utf-8").split("\n") if line]


def _build_once(
    *, index: Path, raw_dir: Path, canon_dir: Path, upstream_reference: str
) -> tuple[bytes, list[SidecarRow]]:
    """One full sidecar build pass; returns its canonical JSONL bytes + rows."""
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
    """Count matched-subset articles whose records cross existing splits.

    Fallback records carry no upstream DOI and are excluded by definition;
    the exclusion count is reported so the diagnostic is self-auditing.
    """
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
    ap.add_argument(
        "--expect-index-sha",
        required=True,
        help=(
            "SHA-256 the caption index must hash to; mandatory and verified "
            "in preflight, before any build or external write"
        ),
    )
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

    bundle = _attested_bundle(args.upstream_reference)
    bundle_sha = bundle.bundle_sha256()
    build_a = args.staging_root / "build-a"
    build_a.mkdir(parents=True, exist_ok=True)
    (args.staging_root / "build-b").mkdir(parents=True, exist_ok=True)
    stage = "preflight"
    try:
        # -- preflight: attested bundle vs disk (leakage audit mandatory) ----
        verify_provenance_build_inputs(bundle, canon_dir=args.canon_dir, raw_dir=args.raw_dir)
        # Attest the caption index BEFORE any build reads it. The index is
        # derived from the attested upstream archive; the operator MUST pin
        # its SHA (--expect-index-sha is mandatory) and we fail closed here,
        # not after the dual build.
        index_sha = sha256_file(args.index)
        attest_caption_index(actual_sha256=index_sha, expected_sha256=args.expect_index_sha)
        canon_lines: list[str] = []
        for part in PARTITIONS:
            canon_lines.extend(read_jsonl_physical_lines(args.canon_dir / f"{part}.jsonl"))
        actual_records = records_content_sha256(canon_lines)
        if actual_records != bundle.canonical_records_sha256:
            raise ValueError(f"records_sha256 mismatch: {actual_records}")
        if len(canon_lines) != EXPECTED_TOTAL:
            raise ValueError(f"canonical record count mismatch: {len(canon_lines)}")

        # -- deterministic dual build -----------------------------------------
        stage = "dual_build"
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
            raise ValueError("deterministic dual-build mismatch: builds are not byte-identical")

        # -- schema validation + 1:1 join -------------------------------------
        stage = "validation"
        payload = parse_jsonl_blob(blob_a)
        canonical_ids = set()
        for line in canon_lines:
            canonical_ids.add(json.loads(line)["record_id"])
        validation = validate_sidecar_rows(payload, canonical_record_ids=canonical_ids)

        tier_counts = validation["tier_counts"]
        assert isinstance(tier_counts, dict)
        if tier_counts != EXPECTED_TIER_COUNTS:
            raise ValueError(f"tier count drift: {tier_counts} != {EXPECTED_TIER_COUNTS}")
        diagnostic = _article_crossing_diagnostic(rows_a)

        sidecar_sha = sha256_bytes(blob_a)
        report: dict[str, object] = {
            "status": "SUCCESS",
            "sidecar_rows": len(rows_a),
            "sidecar_bytes": len(blob_a),
            "sidecar_sha256": sidecar_sha,
            "schema_version": SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "input_bundle_sha256": bundle_sha,
            "input_records_sha256": actual_records,
            "caption_index_sha256": index_sha,
            "upstream_archive_sha256": bundle.upstream_xml_sha256,
            "upstream_reference": args.upstream_reference,
            "dual_build_byte_identical": True,
            "validation": validation,
            "tier_counts": tier_counts,
            "diagnostic": diagnostic,
        }
        (build_a / "sidecar.jsonl").write_bytes(blob_a)

        # -- optional external write + post-write verification ----------------
        stage = "write"
        if args.write is not None:
            if args.write.exists():
                if not args.replace:
                    raise ValueError(f"refusing to overwrite existing sidecar: {args.write}")
                if not args.expect_superseded_sha:
                    raise ValueError("--replace requires --expect-superseded-sha")
                pre = sha256_file(args.write)
                if pre != args.expect_superseded_sha:
                    raise ValueError(
                        f"existing sidecar sha256 {pre} != expected superseded "
                        f"sha256 {args.expect_superseded_sha}; refusing to replace"
                    )
                report["superseded_sidecar_sha256"] = pre
            atomic_write_text(args.write, blob_a.decode("utf-8"))
            post = sha256_file(args.write)
            if post != sidecar_sha:
                raise ValueError(f"post-rename re-hash mismatch: {post} != {sidecar_sha}")
            report["written_path"] = str(args.write)
            report["post_rename_sha256"] = post

        # -- canonical inputs re-verified AFTER any write ---------------------
        stage = "canonical_reverification"
        verify_provenance_build_inputs(bundle, canon_dir=args.canon_dir, raw_dir=args.raw_dir)
        report["canonical_input_reverification"] = "PASSED"

        # -- success report published only after all verification -------------
        stage = "report"
        report["final_verification_complete"] = True
        publish_build_report(build_a, report)
    except KeyboardInterrupt as exc:
        abort_build_report(build_a, stage=stage, error=str(exc) or "interrupted", status="ABORTED")
        raise SystemExit(130) from exc
    except BaseException as exc:
        abort_build_report(build_a, stage=stage, error=str(exc))
        raise
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
