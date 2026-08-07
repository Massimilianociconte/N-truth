#!/usr/bin/env python3
"""Calcola SHA-256 di un file sorgente per il campo sources[].sha256 del bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    digest = hashlib.sha256(args.path.read_bytes()).hexdigest()
    print(
        json.dumps(
            {
                "path": str(args.path),
                "sha256": digest,
                "size_bytes": args.path.stat().st_size,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
