#!/usr/bin/env python3
"""Engineering smoke LoRA: testa la tubatura MLX/Granite, non la qualità N-Truth.

- Usa snapshot runtime_smoke_only ufficiale (ntruth-ml).
- Max ~2 iterazioni (--runtime-smoke-only).
- Adapter marcato ENGINEERING_SMOKE_ONLY: non distribuibile, non promuovibile.
- Non usa i 39 B4 DEV per selezione.
- Non sblocca substantive_p0_training.

Uso:
  uv run python scripts/models/run_engineering_smoke_lora.py
  uv run python scripts/models/run_engineering_smoke_lora.py --skip-train  # solo verifica gate
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROGRAM = REPO / "models" / "registry" / "training_program.json"
PROFILE = REPO / "models" / "configs" / "granite-4.1-3b-mlx-qlora.json"
SMOKE_DATA = REPO / "local-data" / "smoke" / "engineering-pipe-granite"
SMOKE_RUN = REPO / "models" / "runs" / "engineering-smoke-p0-pipe"


def _load_program() -> dict:
    return json.loads(PROGRAM.read_text(encoding="utf-8"))


def assert_gates() -> dict:
    prog = _load_program()
    if prog.get("training_execution_gate") != "HOLD_PENDING_REAL_ANCHOR":
        raise SystemExit(
            f"expected HOLD_PENDING_REAL_ANCHOR, got {prog.get('training_execution_gate')}"
        )
    if not prog.get("engineering_smoke_training_allowed"):
        raise SystemExit("engineering_smoke_training_allowed is false")
    if prog.get("substantive_p0_training_allowed"):
        raise SystemExit("substantive_p0_training_allowed is true: refuse smoke under wrong gate")
    if prog.get("current_synthetic_snapshot_status") != "SYN_G1_UNANCHORED":
        print(
            "WARN: snapshot status unexpected:",
            prog.get("current_synthetic_snapshot_status"),
            file=sys.stderr,
        )
    return prog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-train",
        action="store_true",
        help="Solo verifica gate e prepara metadata, senza addestrare.",
    )
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    prog = assert_gates()
    stamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    meta = {
        "label": "ENGINEERING_SMOKE_ONLY",
        "purpose": "MLX QLoRA plumbing on Granite; not model quality",
        "distributable": False,
        "promotable": False,
        "training_execution_gate": prog["training_execution_gate"],
        "substantive_p0_training_allowed": False,
        "scientific_validation_status": "NOT_STARTED",
        "runtime_qualification_status": "PARTIALLY_VERIFIED",
        "started_at": stamp,
        "profile": str(PROFILE.relative_to(REPO)),
        "must_not_use_b4_dev": True,
    }

    if args.skip_train:
        out = SMOKE_RUN
        out.mkdir(parents=True, exist_ok=True)
        (out / "engineering-smoke-meta.json").write_text(
            json.dumps({**meta, "status": "gates_ok_skipped_train"}, indent=2) + "\n"
        )
        print(json.dumps({**meta, "status": "gates_ok_skipped_train"}, indent=2))
        return 0

    # 1) make smoke data
    from ntruth.training.mlx_dataset import create_runtime_smoke_dataset
    from ntruth.training.mlx_runtime import run_training

    if SMOKE_DATA.exists() and any(SMOKE_DATA.iterdir()):
        # recreate clean
        import shutil

        shutil.rmtree(SMOKE_DATA)
    SMOKE_DATA.mkdir(parents=True, exist_ok=True)
    smoke_manifest = create_runtime_smoke_dataset(SMOKE_DATA)
    print("smoke dataset:", json.dumps(smoke_manifest, indent=2)[:500])

    # 2) train max 2 iters (run dir must be empty for run_training)
    if SMOKE_RUN.exists():
        import shutil

        shutil.rmtree(SMOKE_RUN)
    SMOKE_RUN.mkdir(parents=True, exist_ok=True)
    # meta lives beside the empty run dir until train starts — use sidecar path
    sidecar = SMOKE_RUN.parent / "engineering-smoke-p0-pipe.meta.json"
    sidecar.write_text(json.dumps({**meta, "status": "running"}, indent=2) + "\n")
    try:
        result = run_training(
            PROFILE.resolve(),
            REPO.resolve(),
            SMOKE_DATA.resolve(),
            SMOKE_RUN.resolve(),
            seed=args.seed,
            smoke_test=True,
            resume=False,
        )
    except Exception as exc:
        finished_fail = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        fail_doc = {
            **meta,
            "status": "failed",
            "error": str(exc),
            "finished_at": finished_fail,
        }
        sidecar.write_text(json.dumps(fail_doc, indent=2) + "\n")
        SMOKE_RUN.mkdir(parents=True, exist_ok=True)
        (SMOKE_RUN / "engineering-smoke-meta.json").write_text(
            json.dumps(fail_doc, indent=2) + "\n"
        )
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 1

    # 3) verify adapter exists + constrained still works on base (smoke adapter optional)
    adapter_best = SMOKE_RUN / "best"
    checks = {
        "run_result_keys": list(result.keys())
        if isinstance(result, dict)
        else type(result).__name__,
        "best_dir_exists": adapter_best.is_dir(),
        "best_files": [p.name for p in adapter_best.iterdir()] if adapter_best.is_dir() else [],
    }
    # Outlines on base model still works
    try:
        from ntruth.model_backends.base import GenerationRequest
        from ntruth.model_backends.constrained import probe_outlines_mlx
        from ntruth.model_backends.factory import create_model_backend
        from ntruth.model_backends.stage_schemas import EvidenceExtractionStage
        from ntruth.training.mlx_runtime import load_profile

        cap = probe_outlines_mlx()
        checks["outlines"] = cap.status.value
        profile = load_profile(PROFILE)
        model_path = (REPO / profile["model"]["local_path"]).resolve()
        backend = create_model_backend(model_path=model_path, profile=profile, max_tokens=128)
        backend.load()
        gen = backend.generate_structured(
            GenerationRequest(
                messages=[
                    {
                        "role": "user",
                        "content": "Extract evidence from: Five donors provided cells.",
                    }
                ],
                max_tokens=128,
                constrained=True,
                output_schema=EvidenceExtractionStage,
                schema_name="evidence_extraction",
            )
        )
        checks["constrained_after_smoke"] = {
            "status": gen.constrained_status,
            "schema_try": bool(gen.text),
            "truncated": gen.truncated,
        }
        backend.unload()
    except Exception as exc:
        checks["constrained_after_smoke_error"] = str(exc)

    finished = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    final = {
        **meta,
        "status": "completed_engineering_smoke",
        "finished_at": finished,
        "checks": checks,
        "training_result": result if isinstance(result, dict) else str(result)[:2000],
        "rollback": "Delete models/runs/engineering-smoke-p0-pipe; base weights unchanged.",
    }
    (SMOKE_RUN / "engineering-smoke-meta.json").write_text(
        json.dumps(final, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    print(json.dumps({k: final[k] for k in final if k != "training_result"}, indent=2))
    print("ENGINEERING_SMOKE_ONLY complete — not promotable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
