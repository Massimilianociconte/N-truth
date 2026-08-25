"""C1.1 PoC step 4: conservative containment join (S5 composite).

The locked export contains sentence-level segments of figure legends while the
official XML v2.0.3 is organized per sd-panel. This script evaluates a
conservative two-tier deterministic join:

  tier 1: exact normalized-text equality with a unique upstream caption
  tier 2: segment containment — local text appears verbatim inside upstream
          caption(s); if ALL containing captions share one article DOI, the
          record is assigned article-level provenance only (panel_id withheld)

Hard rules:
  - no fuzzy similarity, no first-match behaviour;
  - containment candidates must be measured and collisions reported;
  - records with candidates spanning multiple DOIs remain UNMATCHED;
  - containment is verified on the full retained original text;
  - outputs metrics only; no canonical dataset files are written.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_WS = re.compile(r"\s+")
_DOI = re.compile(r"^10\.\d{4,9}/\S+\Z")
_MIN_SEGMENT_LEN = 40  # chars; very short segments cannot support containment evidence


def normalize_caption(text: str) -> str:
    return _WS.sub(" ", text).strip()


def doi_is_well_formed(value: str) -> bool:
    """Malformed/missing DOIs can never serve as article provenance."""
    return _DOI.match(value) is not None


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} UPSTREAM_INDEX_JSONL DATASET_ROOT")
    index_path = Path(sys.argv[1])
    dataset_root = Path(sys.argv[2])

    exact: dict[str, list[dict]] = {}
    captions: list[tuple[str, str]] = []  # (doi, caption_text) for containment scan
    with index_path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            cap = normalize_caption(rec["caption"])
            exact.setdefault(cap, []).append(rec)
            captions.append((rec["article_doi"], cap))

    stats = Counter()
    per_split = {}
    article_splits: dict[str, set[str]] = {}
    panel_splits: dict[str, set[str]] = {}
    containment_scan_cost = 0
    ambiguous_examples: list[dict] = []

    for split in ("train", "validation", "test"):
        sp = Counter()
        path = dataset_root / "raw/sourcedata/v2.0.3/roles_multi" / f"{split}.jsonl"
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                rec = json.loads(line)
                key = normalize_caption(rec["text"])
                sp["total"] += 1
                cands = exact.get(key, [])
                if any(not doi_is_well_formed(c["article_doi"]) for c in cands):
                    # Fail-closed: unverifiable article identity withholds assignment.
                    sp["unmatched_invalid_doi"] += 1
                    continue
                if len(cands) == 1:
                    sp["tier1_unique"] += 1
                    doi = cands[0]["article_doi"]
                    article_splits.setdefault(doi, set()).add(split)
                    panel_splits.setdefault(f"{doi}:{cands[0]['panel_id']}", set()).add(split)
                    continue
                if len(cands) > 1:
                    # ambiguous exact: collapse to DOI tier if single DOI
                    dois = {c["article_doi"] for c in cands}
                    if len(dois) == 1:
                        sp["tier2_ambiguous_single_doi"] += 1
                        article_splits.setdefault(next(iter(dois)), set()).add(split)
                    else:
                        sp["unmatched_multi_doi"] += 1
                    continue
                # tier 2 containment
                if len(key) < _MIN_SEGMENT_LEN:
                    sp["unmatched_short_segment"] += 1
                    continue
                hits = [doi for doi, cap in captions if key in cap]
                containment_scan_cost += len(captions)
                if any(not doi_is_well_formed(d) for d in hits):
                    sp["unmatched_containment_invalid_doi"] += 1
                    continue
                dois = set(hits)
                if len(dois) == 1:
                    sp["tier2_containment_single_doi"] += 1
                    article_splits.setdefault(next(iter(dois)), set()).add(split)
                elif len(dois) > 1:
                    sp["unmatched_containment_multi_doi"] += 1
                    if len(ambiguous_examples) < 5:
                        ambiguous_examples.append(
                            {"split": split, "idx": i, "dois": sorted(dois)[:6]}
                        )
                else:
                    sp["unmatched_no_containment"] += 1
                    if len(ambiguous_examples) < 5:
                        ambiguous_examples.append(
                            {"split": split, "idx": i, "text": rec["text"][:120]}
                        )
        per_split[split] = dict(sp)
        stats.update(sp)

    total = stats["total"]
    doi_crossing = {d: sorted(s) for d, s in article_splits.items() if len(s) > 1}
    panel_crossing = {p: sorted(s) for p, s in panel_splits.items() if len(s) > 1}
    print(
        json.dumps(
            {
                "local_total": total,
                "tier_totals": dict(stats),
                "matched_any_tier": total
                - stats["unmatched_multi_doi"]
                - stats["unmatched_short_segment"]
                - stats["unmatched_containment_multi_doi"]
                - stats["unmatched_no_containment"]
                - stats["unmatched_invalid_doi"]
                - stats["unmatched_containment_invalid_doi"],
                "per_split": per_split,
                "articles_covered": len(article_splits),
                "articles_crossing_splits": len(doi_crossing),
                "articles_crossing_splits_sample": dict(list(sorted(doi_crossing.items()))[:20]),
                "panels_crossing_splits_tier1": len(panel_crossing),
                "panels_crossing_splits_sample": dict(list(sorted(panel_crossing.items()))[:20]),
                "containment_scan_pairs": containment_scan_cost,
                "examples": ambiguous_examples,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
