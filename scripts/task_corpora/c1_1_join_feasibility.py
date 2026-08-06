"""C1.1 PoC step 2: deterministic join feasibility between locked SourceData
task records and the official xml_v2.0.3 caption index.

Strategies evaluated (in order, per authorisation):
  S1 explicit stable identifier join      -> impossible (locked export has none)
  S2 official source-record ID join       -> impossible (no upstream row IDs)
  S3 exact canonical text join            -> measured here
  S4 exact tuple with unique occurrence   -> text + split-independent uniqueness
  S5 conservative deterministic composite -> reported separately when S3/S4 fail

Rules enforced:
  - no fuzzy similarity;
  - no first-match behaviour (multiply matched => UNMATCHED);
  - ambiguous matches remain unmatched;
  - only normalized-whitespace text comparison (same normalization used on
    both sides);
  - local original text is never mutated.

Outputs deterministic JSON metrics; never writes into canonical dataset paths.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_WS = re.compile(r"\s+")


def normalize_caption(text: str) -> str:
    return _WS.sub(" ", text).strip()


def load_upstream(index_path: Path) -> dict[str, list[dict]]:
    """normalized caption -> list of candidate upstream provenance rows."""
    idx: dict[str, list[dict]] = {}
    with index_path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            key = normalize_caption(rec["caption"])
            idx.setdefault(key, []).append(rec)
    return idx


def load_local(root: Path) -> list[dict]:
    """Read locked raw roles_multi JSONL (fields: words, labels, is_category, text)."""
    rows: list[dict] = []
    for split in ("train", "validation", "test"):
        path = root / "raw" / "sourcedata" / "v2.0.3" / "roles_multi" / f"{split}.jsonl"
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                rec = json.loads(line)
                rows.append({"split": split, "line_index": i, "text": rec["text"]})
    return rows


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} UPSTREAM_INDEX_JSONL DATASET_ROOT")
    upstream = load_upstream(Path(sys.argv[1]))
    local = load_local(Path(sys.argv[2]))

    # Upstream-side duplicate captions (same normalized text, multiple panels/articles)
    dup_captions = {k: v for k, v in upstream.items() if len(v) > 1}

    total = len(local)
    matched_unique = 0
    matched_ambiguous = 0
    unmatched = 0
    per_split = Counter()
    per_split_matched = Counter()
    article_group_splits: dict[str, set[str]] = {}

    for row in local:
        split = row["split"]
        per_split[split] += 1
        key = normalize_caption(row["text"])
        cands = upstream.get(key, [])
        if len(cands) == 1:
            matched_unique += 1
            per_split_matched[split] += 1
            article_group_splits.setdefault(cands[0]["article_doi"], set()).add(split)
        elif len(cands) > 1:
            matched_ambiguous += 1
        else:
            unmatched += 1

    groups_crossing = {
        doi: sorted(splits) for doi, splits in article_group_splits.items() if len(splits) > 1
    }

    metrics = {
        "strategy_order": [
            "S1_id_join:impossible",
            "S2_source_record_id:impossible",
            "S3_exact_text",
            "S4_unique_occurrence_only",
        ],
        "local_total": total,
        "upstream_captions": len(upstream),
        "upstream_duplicate_caption_keys": len(dup_captions),
        "uniquely_matched": matched_unique,
        "ambiguous_multiply_matched": matched_ambiguous,
        "unmatched": unmatched,
        "coverage_pct_unique": round(100.0 * matched_unique / total, 3) if total else 0.0,
        "per_split_total": dict(per_split),
        "per_split_uniquely_matched": dict(per_split_matched),
        "articles_covered_by_unique_matches": len(article_group_splits),
        "articles_crossing_splits_under_unique_matches": len(groups_crossing),
        "articles_crossing_splits_sample": dict(list(sorted(groups_crossing.items()))[:20]),
    }
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
