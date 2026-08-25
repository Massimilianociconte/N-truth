#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/Volumes/FLASH128/N-Truth-Datasets}"

echo "=== Executing N-Truth Dataset Acquisition Wrapper ==="
uv run python -m ntruth.data.acquire all --root "$ROOT_DIR" --resume
