"""C1.1 PoC step 3: sample diagnostics for unmatched / ambiguous local records."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_WS = re.compile(r"\s+")


def normalize_caption(text: str) -> str:
    return _WS.sub(" ", text).strip()


def main() -> None:
    index_path = Path(sys.argv[1])
    dataset_root = Path(sys.argv[2])
    upstream: dict[str, list[dict]] = {}
    with index_path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            upstream.setdefault(normalize_caption(rec["caption"]), []).append(rec)

    unmatched_samples: list[dict] = []
    ambiguous_samples: list[dict] = []
    dup_local = Counter()
    ner_vs_roles = Counter()

    for split in ("train", "validation", "test"):
        ner_path = dataset_root / "raw/sourcedata/v2.0.3/ner" / f"{split}.jsonl"
        roles_path = dataset_root / "raw/sourcedata/v2.0.3/roles_multi" / f"{split}.jsonl"
        with ner_path.open(encoding="utf-8") as fn, roles_path.open(encoding="utf-8") as fr:
            for i, (nl, rl) in enumerate(zip(fn, fr, strict=True)):
                nrec = json.loads(nl)
                rrec = json.loads(rl)
                ner_vs_roles["text_equal_at_index"] += int(nrec["text"] == rrec["text"])
                ner_vs_roles["pairs"] += 1
                key = normalize_caption(rrec["text"])
                dup_local[key] += 1
                cands = upstream.get(key, [])
                if not cands and len(unmatched_samples) < 5:
                    unmatched_samples.append({"split": split, "idx": i, "text": rrec["text"][:200]})
                if len(cands) > 1 and len(ambiguous_samples) < 3:
                    ambiguous_samples.append(
                        {
                            "split": split,
                            "idx": i,
                            "text": rrec["text"][:200],
                            "n_candidates": len(cands),
                            "candidate_ids": [
                                {"doi": c["article_doi"], "panel_id": c["panel_id"]}
                                for c in cands[:4]
                            ],
                        }
                    )

    local_duplicate_texts = sum(1 for k, v in dup_local.items() if v > 1)
    print(
        json.dumps(
            {
                "ner_roles_text_equal_pairs": dict(ner_vs_roles),
                "local_duplicate_distinct_texts": local_duplicate_texts,
                "unmatched_samples": unmatched_samples,
                "ambiguous_samples": ambiguous_samples,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
