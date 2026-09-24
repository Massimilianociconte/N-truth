#!/usr/bin/env python3
"""Acquire and verify MiniCPM5-2B official MLX 4-bit weights (not committed to Git).

Writes under models/local/ only. Does **not** update models/registry or qualification
ledger (cluster 2). Use --variant 1b for the MiniCPM5-1B ablation arm.

Usage:
  uv run python scripts/models/acquire_minicpm.py --confirm-license-and-download
  uv run python scripts/models/acquire_minicpm.py --variant 1b --confirm-license-and-download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Keep in sync with ntruth.model_backends.constants and the pinned profiles in
# models/configs/minicpm5-{2b,1b}-mlx-qlora.json.
VARIANTS = {
    "2b": {
        "repo": "openbmb/MiniCPM5-2B-MLX",
        "revision": "8a9ad7539ac86281d0ac2b017ba04a5de53fe9a3",
        "expected_sha": "c207798696a4a454e7ac211b25227625466c693335941cee8904fb922f295cc1",
        "expected_bytes": 1_416_035_216,
        "local_dir": REPO / "models" / "local" / "minicpm5-2b-4bit",
        "canonical_model_id": "openbmb/MiniCPM5-2B",
        "canonical_revision": "12a3808a956f869c767195e9266b59c4d21d92e2",
    },
    "1b": {
        "repo": "openbmb/MiniCPM5-1B-MLX",
        "revision": "9879b18bf2928355fcdf4287635388a3665a40cb",
        "expected_sha": "a23e0c5c79944a0b2cc92cb9ab79376b4dce41e2312383727e21ee43fe19cb4f",
        "expected_bytes": 608_026_621,
        "local_dir": REPO / "models" / "local" / "minicpm5-1b-4bit",
        "canonical_model_id": "openbmb/MiniCPM5-1B",
        "canonical_revision": "87179e5c1f455ef22e6223592d2d61351b525bfc",
    },
}


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
        help="Confirm Apache-2.0 download (OpenBMB MiniCPM5 official MLX).",
    )
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="2b")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing local weights; do not download.",
    )
    args = parser.parse_args()

    spec = VARIANTS[args.variant]
    repo = args.repo or spec["repo"]
    revision = args.revision or spec["revision"]
    out: Path = args.out or spec["local_dir"]
    expected_sha = spec["expected_sha"]
    expected_bytes = spec["expected_bytes"]
    weight = out / "model.safetensors"

    if args.verify_only:
        if not weight.is_file():
            print(f"weight missing: {weight}", file=sys.stderr)
            return 1
        size = weight.stat().st_size
        digest = _sha256_file(weight)
        ok = size == expected_bytes and digest == expected_sha
        print(
            json.dumps(
                {
                    "integrity_ok": ok,
                    "weight_bytes": size,
                    "weight_sha256": digest,
                    "expected_bytes": expected_bytes,
                    "expected_sha256": expected_sha,
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
    print(f"Downloading {repo}@{revision} -> {out}")
    snapshot_download(
        repo_id=repo,
        revision=revision,
        local_dir=str(out),
        local_dir_use_symlinks=False,
    )
    if not weight.is_file():
        print(f"weight missing: {weight}", file=sys.stderr)
        return 1
    size = weight.stat().st_size
    digest = _sha256_file(weight)
    ok = size == expected_bytes and digest == expected_sha
    try:
        import importlib.metadata

        mlx_lm_version = importlib.metadata.version("mlx-lm")
    except Exception:
        mlx_lm_version = None

    # Provenance next to weights only (gitignored with models/local/).
    provenance = {
        "acquired_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "canonical_model_id": spec["canonical_model_id"],
        "canonical_revision": spec["canonical_revision"],
        "mlx_kind": "official_vendor_mlx_openbmb",
        "mlx_repository": repo,
        "revision": revision,
        "local_path": str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out),
        "weight_file": "model.safetensors",
        "weight_bytes": size,
        "weight_sha256": digest,
        "expected_bytes": expected_bytes,
        "expected_sha256": expected_sha,
        "integrity_ok": ok,
        "mlx_lm_version_at_acquisition": mlx_lm_version,
        "license": "Apache-2.0",
        "scientifically_selected": False,
        "note": "Acquisition only; does not set registry qualification.",
    }
    (out / "model-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"integrity_ok": ok, "weight_sha256": digest, "bytes": size}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
