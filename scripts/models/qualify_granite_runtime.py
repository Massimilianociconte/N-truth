#!/usr/bin/env python3
"""Runtime qualification tooling — verification vs re-qualification are distinct.

VERIFY_PUBLISHED_QUALIFICATION (default)
  - No model weights required
  - Verifies public JSONL chain, tip manifest, evidence digests, registry mirror
  - Does **not** re-run host benchmarks
  - Does **not** issue a new qualification
  - Does **not** promote Granite to factory default

CHECK_LOCAL_WEIGHTS (optional --check-weights)
  - Verifies local weight bytes/sha256 if present
  - Still does **not** re-qualify the runtime

RUN_LOCAL_QUALIFICATION
  - Requires --run-local-qualification and local weights + mlx-lm
  - Produces evidence JSON only; does **not** auto-publish PARTIALLY_VERIFIED
  - Publishing still requires reviewed export of the public chain

Usage:
  uv run python scripts/models/qualify_granite_runtime.py
  uv run python scripts/models/qualify_granite_runtime.py --check-weights
  uv run python scripts/models/qualify_granite_runtime.py --run-local-qualification
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

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


def _base_report(operation: str) -> dict[str, Any]:
    return {
        "operation": operation,
        "runtime_reexecuted": False,
        "new_qualification_issued": False,
        "chain_valid": None,
        "evidence_integrity_valid": None,
        "registry_mirror_consistent": None,
        "factory_default_provider": None,
        "published_runtime_status": None,
        "published_scientific_status": None,
        "checks": [],
        "ok": False,
    }


def _add(report: dict[str, Any], name: str, ok: bool, detail: str = "") -> None:
    report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})


def verify_published() -> dict[str, Any]:
    report = _base_report("VERIFY_PUBLISHED_QUALIFICATION")
    sys.path.insert(0, str(REPO / "packages"))
    from ntruth.model_backends.base import ModelProvider
    from ntruth.model_backends.factory import resolve_provider
    from ntruth.model_backends.registry import (
        claim_gates,
        load_registry,
        qualification_status,
        verify_public_chain,
    )

    try:
        chain = verify_public_chain(repo_root=REPO, verify_evidence=True)
        report["chain_valid"] = True
        report["evidence_integrity_valid"] = True
        _add(report, "public_chain", True, json.dumps(chain, sort_keys=True))
    except Exception as exc:
        report["chain_valid"] = False
        report["evidence_integrity_valid"] = False
        _add(report, "public_chain", False, str(exc))
        report["ok"] = False
        return report

    try:
        registry = load_registry(verify_public_chain_integrity=True)
        status = qualification_status(registry)
        gates = claim_gates(registry)
        report["registry_mirror_consistent"] = True
        report["factory_default_provider"] = registry.get("factory_default_provider")
        report["published_runtime_status"] = status["runtime_qualification_status"]
        report["published_scientific_status"] = status["scientific_validation_status"]
        _add(report, "registry_load", True, json.dumps(status, sort_keys=True))
        _add(
            report,
            "factory_default_legacy_qwen",
            registry.get("factory_default_provider") == "legacy_qwen",
            str(registry.get("factory_default_provider")),
        )
        _add(
            report,
            "science_not_started",
            status["scientific_validation_status"] == "NOT_STARTED",
            status["scientific_validation_status"],
        )
        _add(
            report,
            "not_scientifically_releasable",
            gates["scientifically_releasable"]["allowed"] is False,
            gates["scientifically_releasable"]["reason"],
        )
        _add(
            report,
            "resolve_provider_default_qwen",
            resolve_provider() is ModelProvider.LEGACY_QWEN,
            str(resolve_provider()),
        )
        # Explicit: this path never re-qualifies.
        report["runtime_reexecuted"] = False
        report["new_qualification_issued"] = False
        _add(report, "no_requalification_without_weights", True, "verify-only path")
    except Exception as exc:
        report["registry_mirror_consistent"] = False
        _add(report, "registry_load", False, str(exc))

    report["ok"] = all(c["ok"] for c in report["checks"])
    return report


def check_local_weights(report: dict[str, Any]) -> dict[str, Any]:
    report["operation"] = "VERIFY_PUBLISHED_QUALIFICATION_PLUS_LOCAL_WEIGHTS"
    # Still not a re-qualification of runtime on this host.
    report["runtime_reexecuted"] = False
    report["new_qualification_issued"] = False
    if not LOCAL_WEIGHT.is_file():
        _add(report, "local_weights", False, f"missing {LOCAL_WEIGHT}")
    else:
        size = LOCAL_WEIGHT.stat().st_size
        digest = _sha256_file(LOCAL_WEIGHT)
        ok = size == EXPECTED_BYTES and digest == EXPECTED_SHA
        _add(
            report,
            "local_weights",
            ok,
            json.dumps({"bytes": size, "sha256": digest, "ok": ok}),
        )
    report["ok"] = all(c["ok"] for c in report["checks"])
    return report


def run_local_qualification() -> dict[str, Any]:
    """Optional host path: requires weights; does not auto-publish."""

    report = _base_report("RUN_LOCAL_QUALIFICATION")
    if not LOCAL_WEIGHT.is_file():
        _add(report, "weights_present", False, f"missing {LOCAL_WEIGHT}")
        report["ok"] = False
        return report
    _add(report, "weights_present", True, str(LOCAL_WEIGHT))

    try:
        from mlx_lm import load  # type: ignore
    except ImportError as exc:
        _add(report, "mlx_lm_import", False, str(exc))
        report["ok"] = False
        return report
    _add(report, "mlx_lm_import", True, "ok")

    try:
        sys.path.insert(0, str(REPO / "packages"))
        from ntruth.model_backends.base import GenerationRequest
        from ntruth.model_backends.granite import GraniteBackend

        backend = GraniteBackend(model_path=LOCAL_WEIGHT.parent)
        backend.load()
        backend.unload()
        backend.reload()
        # Minimal candidate-only generation (free decode; constrained not in this cluster)
        result = backend.generate_structured(
            GenerationRequest(
                messages=[{"role": "user", "content": "Return empty JSON object {}"}],
                max_tokens=32,
                task_tag="TASK_SMOKE",
            )
        )
        backend.unload()
        report["runtime_reexecuted"] = True
        report["new_qualification_issued"] = False  # never auto-publish
        _add(
            report,
            "load_unload_reload_generate",
            True,
            json.dumps(
                {
                    "finish_reason": result.finish_reason,
                    "output_chars": len(result.text or ""),
                    "note": "Local smoke only; does not update published PARTIALLY_VERIFIED",
                }
            ),
        )
    except Exception as exc:
        report["runtime_reexecuted"] = True
        report["new_qualification_issued"] = False
        _add(report, "load_unload_reload_generate", False, str(exc))

    # Always re-verify published chain after local run (does not issue transition).
    published = verify_published()
    report["chain_valid"] = published.get("chain_valid")
    report["evidence_integrity_valid"] = published.get("evidence_integrity_valid")
    report["checks"].extend(
        [{"check": f"published::{c['check']}", "ok": c["ok"], "detail": c["detail"]} for c in published["checks"]]
    )
    report["ok"] = all(c["ok"] for c in report["checks"])
    report["publish_required_for_status_change"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-weights",
        action="store_true",
        help="Also verify local weight sha256/bytes if present (still not re-qualification).",
    )
    parser.add_argument(
        "--run-local-qualification",
        action="store_true",
        help="Execute real load/generate on local weights; does not publish new status.",
    )
    parser.add_argument(
        "--apply-transition",
        action="store_true",
        help="Disabled in cluster 2: publishing requires reviewed JSONL export.",
    )
    args = parser.parse_args()

    if args.apply_transition:
        print(
            json.dumps(
                {
                    "operation": "APPLY_TRANSITION",
                    "ok": False,
                    "error": "disabled_in_cluster_2_use_reviewed_public_export",
                    "runtime_reexecuted": False,
                    "new_qualification_issued": False,
                },
                indent=2,
            )
        )
        return 2

    if args.run_local_qualification:
        report = run_local_qualification()
    else:
        report = verify_published()
        if args.check_weights:
            report = check_local_weights(report)

    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
