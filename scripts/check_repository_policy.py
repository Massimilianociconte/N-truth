#!/usr/bin/env python3
"""Fail closed on tracked corpus, PII-like payloads, secrets and large files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ntruth.governance.repository_policy import (
    scan_tracked_repository_v8,
    tracked_paths_from_git_v8,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--max-file-bytes", type=int, default=1_048_576)
    args = parser.parse_args()
    root = args.repo.resolve()
    report = scan_tracked_repository_v8(
        root,
        tracked_paths_from_git_v8(root),
        max_file_bytes=args.max_file_bytes,
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
