#!/usr/bin/env python3
"""Costruisce lo snapshot sintetico P0-alpha (train/val) con gate anti-DEV.

Non tocca scientific_validation_status.
I 39 casi B4 restano DEVELOPMENT / non training_eligible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "data" / "training" / "p0-alpha"
DEV_CASES = REPO / "benchmarks" / "fewshot_p0" / "cases.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--n-train", type=int, default=2000)
    parser.add_argument("--n-val", type=int, default=300)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    from ntruth.training.p0_synthetic import write_snapshot

    try:
        manifest = write_snapshot(
            args.out,
            n_train=args.n_train,
            n_val=args.n_val,
            seed=args.seed,
            dev_cases_path=DEV_CASES,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if not manifest.get("quality_gate", {}).get("passed"):
        return 1
    print(f"OK snapshot at {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
