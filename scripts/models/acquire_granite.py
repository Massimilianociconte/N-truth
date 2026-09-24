#!/usr/bin/env python3
"""Acquire and verify Granite 4.1 3B MLX 4-bit bootstrap weights (not committed to Git).

Writes under models/local/ only. Does **not** update models/registry or qualification
ledger (cluster 2).

Usage:
  uv run python scripts/models/acquire_granite.py --confirm-license-and-download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Keep in sync with ntruth.model_backends.constants
DEFAULT_REPO = "mlx-community/granite-4.1-3b-4bit"
DEFAULT_REV = "b1b476b5a17c46b7d6cd663b4a8ed44b66720aef"
EXPECTED_SHA = "cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d"
EXPECTED_BYTES = 2127162429
LOCAL_DIR = REPO / "models" / "local" / "granite-4.1-3b-4bit"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-license-and-download",
        action="store_true",
        help="Confirm Apache-2.0 download (IBM Granite + MLX community conversion).",
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--revision", default=DEFAULT_REV)
    parser.add_argument("--out", type=Path, default=LOCAL_DIR)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing local weights; do not download.",
    )
    args = parser.parse_args()

    out: Path = args.out
    weight = out / "model.safetensors"

    if args.verify_only:
        if not weight.is_file():
            print(f"weight missing: {weight}", file=sys.stderr)
            return 1
        size = weight.stat().st_size
        digest = _sha256_file(weight)
        ok = size == EXPECTED_BYTES and digest == EXPECTED_SHA
        print(
            json.dumps(
                {
                    "integrity_ok": ok,
                    "weight_bytes": size,
                    "weight_sha256": digest,
                    "expected_bytes": EXPECTED_BYTES,
                    "expected_sha256": EXPECTED_SHA,
                },
                indent=2,
            )
        )
        return 0 if ok else 1

    if not args.confirm_license_and_download:
        print("Require --confirm-license-and-download", file=sys.stderr)
        return 2

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub not installed", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {args.repo}@{args.revision} -> {out}")
    snapshot_download(
        repo_id=args.repo,
        revision=args.revision,
        local_dir=str(out),
        local_dir_use_symlinks=False,
    )
    if not weight.is_file():
        print(f"weight missing: {weight}", file=sys.stderr)
        return 1
    size = weight.stat().st_size
    digest = _sha256_file(weight)
    ok = size == EXPECTED_BYTES and digest == EXPECTED_SHA
    try:
        import importlib.metadata

        mlx_lm_version = importlib.metadata.version("mlx-lm")
    except Exception:
        mlx_lm_version = None

    # Provenance next to weights only (gitignored with models/local/).
    provenance = {
        "acquired_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "canonical_model_id": "ibm-granite/granite-4.1-3b",
        "mlx_kind": "community_conversion_not_official_ibm",
        "mlx_repository": args.repo,
        "revision": args.revision,
        "local_path": str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out),
        "weight_file": "model.safetensors",
        "weight_bytes": size,
        "weight_sha256": digest,
        "expected_bytes": EXPECTED_BYTES,
        "expected_sha256": EXPECTED_SHA,
        "integrity_ok": ok,
        "mlx_lm_version_at_acquisition": mlx_lm_version,
        "license": "Apache-2.0",
        "scientifically_selected": false_to_json_false(),
        "note": "Acquisition only; does not set registry qualification.",
    }
    (out / "model-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"integrity_ok": ok, "weight_sha256": digest, "bytes": size}, indent=2))
    return 0 if ok else 1


def false_to_json_false() -> bool:
    return False


if __name__ == "__main__":
    raise SystemExit(main())
