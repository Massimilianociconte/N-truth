#!/usr/bin/env python3
"""Baseline B4: zero-shot e few-shot Granite su fixture P0 CandidateGraphSet.

Non aggiorna scientific_validation_status. Non passa a VERIFIED.
Misura conformità di contratto e F1 candidate-only vs gold minimo.

Uso:
  uv run python scripts/models/run_granite_fewshot_baseline.py --materialize-only
  uv run python scripts/models/run_granite_fewshot_baseline.py --mode both --limit 6
  uv run python scripts/models/run_granite_fewshot_baseline.py --mode both
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = REPO / "benchmarks" / "fewshot_p0"
DEFAULT_PROFILE = REPO / "models" / "configs" / "granite-4.1-3b-mlx-qlora.json"
DEFAULT_OUT = REPO / "benchmarks" / "fewshot_p0" / "results"


def materialize(suite_dir: Path) -> dict[str, Any]:
    from ntruth.training.fewshot_p0_fixtures import write_fixture_suite

    return write_fixture_suite(suite_dir)


def load_cases(suite_dir: Path) -> list[dict[str, Any]]:
    path = suite_dir / "cases.jsonl"
    if not path.is_file():
        materialize(suite_dir)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _system_prompt() -> str:
    from ntruth.training.mlx_dataset import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _build_messages(
    case: dict[str, Any],
    demos: list[dict[str, Any]],
    *,
    mode: Literal["zero_shot", "few_shot"],
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": _system_prompt()}]
    if mode == "few_shot":
        for demo in demos:
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        demo["parser_input"],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        demo["gold"],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )
    messages.append(
        {
            "role": "user",
            "content": json.dumps(
                case["parser_input"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
    )
    return messages


def run_baseline(
    *,
    suite_dir: Path,
    profile_path: Path,
    out_dir: Path,
    mode: Literal["zero_shot", "few_shot", "both"],
    limit: int | None,
    max_tokens: int,
    n_demos: int,
) -> dict[str, Any]:
    from ntruth.model_backends.base import GenerationRequest
    from ntruth.model_backends.factory import create_model_backend
    from ntruth.parser_ai import ParserAIInput
    from ntruth.parser_ai.stages import CandidateGraphSet
    from ntruth.training.candidate_conformance import (
        aggregate_conformance,
        assess_prediction,
    )
    from ntruth.training.mlx_runtime import load_profile

    cases = load_cases(suite_dir)
    demos = [c for c in cases if c["split"] == "demo"][:n_demos]
    evals = [c for c in cases if c["split"] == "eval"]
    if limit is not None:
        evals = evals[:limit]

    profile = load_profile(profile_path)
    model_path = (REPO / profile["model"]["local_path"]).resolve()
    if not model_path.exists():
        raise SystemExit(f"modello assente: {model_path}")

    backend = create_model_backend(
        model_path=model_path,
        profile=profile,
        max_tokens=max_tokens,
    )
    backend.load()

    modes: list[Literal["zero_shot", "few_shot"]]
    modes = ["zero_shot", "few_shot"] if mode == "both" else [mode]

    report: dict[str, Any] = {
        "suite": "fewshot_p0_v1",
        "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "model_path": str(model_path.relative_to(REPO)),
        "profile": str(profile_path.relative_to(REPO)),
        "mlx_revision": profile.get("model", {}).get("revision"),
        "weight_sha256": profile.get("model", {}).get("expected_weight_sha256"),
        "scientific_validation_status": "NOT_STARTED",
        "runtime_note": "B4 baseline only; does not advance scientific status",
        "n_demos": len(demos),
        "demo_ids": [d["case_id"] for d in demos],
        "n_eval": len(evals),
        "modes": {},
    }

    try:
        for run_mode in modes:
            rows: list[dict[str, Any]] = []
            for case in evals:
                messages = _build_messages(case, demos, mode=run_mode)
                task = (case.get("tasks") or ["TASK_CANDIDATE_GRAPH"])[0]
                t0 = time.perf_counter()
                gen = backend.generate_structured(
                    GenerationRequest(
                        messages=messages,
                        max_tokens=max_tokens,
                        task_tag=task,
                    )
                )
                latency_ms = (time.perf_counter() - t0) * 1000.0
                parser_input = ParserAIInput.model_validate(case["parser_input"])
                gold = CandidateGraphSet.model_validate(case["gold"])
                assessment = assess_prediction(
                    gen.text,
                    parser_input=parser_input,
                    gold=gold,
                    apply_safe_normalize=True,
                )
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "kind": case["kind"],
                        "tasks": case["tasks"],
                        "latency_ms": latency_ms,
                        "input_tokens": gen.input_tokens,
                        "output_tokens": gen.output_tokens,
                        "raw_preview": gen.text[:1500],
                        **assessment,
                    }
                )
                print(
                    f"[{run_mode}] {case['case_id']}: "
                    f"json={assessment['json_extractable']} "
                    f"schema={assessment['schema_valid']} "
                    f"schema_norm={assessment['schema_valid_after_safe_normalize']} "
                    f"cand_only={assessment['candidate_only_ok']} "
                    f"ms={latency_ms:.0f}",
                    flush=True,
                )
            summary = aggregate_conformance(rows)
            report["modes"][run_mode] = {
                "summary": summary,
                "rows": rows,
            }
    finally:
        backend.unload()

    report["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"baseline-{stamp}.json"
    latest = out_dir / "baseline-latest.json"
    payload = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    out_path.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    report["output_path"] = str(out_path.relative_to(REPO))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--mode",
        choices=("zero_shot", "few_shot", "both"),
        default="both",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max eval cases (smoke).")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--n-demos", type=int, default=3)
    parser.add_argument(
        "--materialize-only",
        action="store_true",
        help="Scrive solo fixture/manifest senza inferenza.",
    )
    args = parser.parse_args()

    if args.materialize_only:
        manifest = materialize(args.suite)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    report = run_baseline(
        suite_dir=args.suite,
        profile_path=args.profile,
        out_dir=args.out,
        mode=args.mode,
        limit=args.limit,
        max_tokens=args.max_tokens,
        n_demos=args.n_demos,
    )
    # Compact summary for stdout
    compact = {
        "output_path": report.get("output_path"),
        "n_eval": report.get("n_eval"),
        "n_demos": report.get("n_demos"),
        "modes": {name: data["summary"] for name, data in report.get("modes", {}).items()},
        "scientific_validation_status": "NOT_STARTED",
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
