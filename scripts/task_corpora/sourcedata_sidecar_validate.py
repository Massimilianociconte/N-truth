"""Sidecar migration step 3: independent post-write validation.

Re-validates the externally written sidecar from disk (independent of the
build process): schema + tier-rule contract, exact 1:1 join back to the
canonical corpus, audited tier counts, zero duplicate keys, and the
matched-subset article-crossing diagnostic (fallback records excluded).

Also re-confirms that the canonical records hash is unchanged after the write.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ntruth.task_corpora.io_util import read_jsonl_physical_lines, records_content_sha256
from ntruth.task_corpora.provenance_sidecar import (
    PARTITIONS,
    validate_sidecar_rows,
)

EXPECTED_RECORDS_SHA256 = "562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10"
EXPECTED_TIER_COUNTS = {
    "TIER_1_PANEL_UNIQUE": 70158,
    "TIER_2_ARTICLE_ONLY": 3914,
    "RECORD_FALLBACK": 1091,
}
EXPECTED_TOTAL = 75163


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sidecar", required=True, type=Path)
    ap.add_argument("--canon-dir", required=True, type=Path)
    args = ap.parse_args()

    payload = [
        json.loads(line)
        for line in args.sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    canon_lines: list[str] = []
    canonical_ids: set[str] = set()
    for part in PARTITIONS:
        for line in read_jsonl_physical_lines(args.canon_dir / f"{part}.jsonl"):
            canon_lines.append(line)
            canonical_ids.add(json.loads(line)["record_id"])

    result = validate_sidecar_rows(payload, canonical_record_ids=canonical_ids)
    tier_counts = result["tier_counts"]
    problems: list[str] = []
    if result["rows"] != EXPECTED_TOTAL:
        problems.append(f"rows {result['rows']} != {EXPECTED_TOTAL}")
    if tier_counts != EXPECTED_TIER_COUNTS:
        problems.append(f"tier counts {tier_counts} != {EXPECTED_TIER_COUNTS}")
    records_sha = records_content_sha256(canon_lines)
    if records_sha != EXPECTED_RECORDS_SHA256:
        problems.append(f"records_sha256 changed: {records_sha}")

    article_splits: dict[str, set[str]] = {}
    for row in payload:
        if row["provenance_tier"] == "RECORD_FALLBACK":
            continue
        article_splits.setdefault(row["article_doi"], set()).add(row["partition"])
    crossing = sum(1 for splits in article_splits.values() if len(splits) > 1)
    result["matched_subset_articles_crossing_existing_splits"] = crossing
    result["records_sha256"] = records_sha
    result["problems"] = problems
    print(json.dumps(result, indent=2, sort_keys=True))
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
