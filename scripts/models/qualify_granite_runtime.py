#!/usr/bin/env python3
"""Verify published runtime qualification chain (cluster 2).

Does **not** require training_program, B4, or constrained decoding.
Does **not** promote Granite to factory default.

Modes:
  default           Verify public chain + registry coherence (no weights required)
  --check-weights   Also verify local models/local weights if present
  --apply-transition  Reserved; cluster 2 publish path uses pre-exported chain

Usage:
  uv run python scripts/models/qualify_granite_runtime.py
  uv run python scripts/models/qualify_granite_runtime.py --check-weights
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPECTED_SHA = "cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d"
EXPECTED_BYTES = 2_127_162_429
LOCAL_WEIGHT = REPO / "models" / "local" / "granite-4.1-3b-4bit" / "model.safetensors"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-weights", action="store_true")
    parser.add_argument(
        "--apply-transition",
        action="store_true",
        help="Not used for publish; public chain is exported in-repo. Exit 2 if set.",
    )
    args = parser.parse_args()
    if args.apply_transition:
        print(
            "--apply-transition is not enabled in cluster 2 publish path; "
            "edit public chain via reviewed export process.",
            file=sys.stderr,
        )
        return 2

    sys.path.insert(0, str(REPO / "packages"))
    from ntruth.model_backends.factory import resolve_provider
    from ntruth.model_backends.base import ModelProvider
    from ntruth.model_backends.registry import (
        claim_gates,
        load_registry,
        qualification_status,
        verify_public_chain,
    )

    report: dict = {"checks": []}

    def add(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"check": name, "ok": ok, "detail": detail})

    try:
        chain = verify_public_chain(repo_root=REPO, verify_evidence=True)
        add("public_chain", True, json.dumps(chain, sort_keys=True))
    except Exception as exc:
        add("public_chain", False, str(exc))
        print(json.dumps(report, indent=2))
        return 1

    try:
        registry = load_registry(verify_public_chain_integrity=True)
        status = qualification_status(registry)
        gates = claim_gates(registry)
        add("registry_load", True, json.dumps(status, sort_keys=True))
        add(
            "factory_default_legacy_qwen",
            registry.get("factory_default_provider") == "legacy_qwen",
            str(registry.get("factory_default_provider")),
        )
        add(
            "runtime_partial",
            status["runtime_qualification_status"] == "PARTIALLY_VERIFIED",
            status["runtime_qualification_status"],
        )
        add(
            "science_not_started",
            status["scientific_validation_status"] == "NOT_STARTED",
            status["scientific_validation_status"],
        )
        add(
            "not_scientifically_releasable",
            gates["scientifically_releasable"]["allowed"] is False,
            gates["scientifically_releasable"]["reason"],
        )
        add(
            "resolve_provider_default_qwen",
            resolve_provider() is ModelProvider.LEGACY_QWEN,
            str(resolve_provider()),
        )
    except Exception as exc:
        add("registry_load", False, str(exc))
        print(json.dumps(report, indent=2))
        return 1

    if args.check_weights:
        if not LOCAL_WEIGHT.is_file():
            add("local_weights", False, f"missing {LOCAL_WEIGHT}")
        else:
            size = LOCAL_WEIGHT.stat().st_size
            digest = _sha256_file(LOCAL_WEIGHT)
            ok = size == EXPECTED_BYTES and digest == EXPECTED_SHA
            add(
                "local_weights",
                ok,
                json.dumps({"bytes": size, "sha256": digest, "ok": ok}),
            )

    ok_all = all(c["ok"] for c in report["checks"])
    report["ok"] = ok_all
    print(json.dumps(report, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
