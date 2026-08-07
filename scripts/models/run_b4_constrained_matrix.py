#!/usr/bin/env python3
"""Matrice B4 A/B/C/D: free vs constrained decoding su stage P0.

Condizioni (stesso fingerprint, seed, casi, max_tokens, template):
  A  zero-shot, free
  B  few-shot k=3 SHORT, free
  C  zero-shot, constrained
  D  few-shot k=3 SHORT, constrained

Non modifica runtime PARTIALLY_VERIFIED ne scientific NOT_STARTED.
Non avvia LoRA.

Uso:
  uv run python scripts/models/run_b4_constrained_matrix.py --audit-only
  uv run python scripts/models/run_b4_constrained_matrix.py --stage evidence_extraction --limit 5
  uv run python scripts/models/run_b4_constrained_matrix.py --all-stages
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "benchmarks" / "fewshot_p0"
OUT = REPO / "benchmarks" / "fewshot_p0" / "constrained"
PROFILE = REPO / "models" / "configs" / "granite-4.1-3b-mlx-qlora.json"

Condition = Literal["A", "B", "C", "D"]
StageName = Literal[
    "evidence_extraction",
    "entity_count",
    "candidate_relations",
    "candidate_graph_minimal",
]

CONDITIONS: dict[Condition, dict[str, Any]] = {
    "A": {"prompt": "zero_shot", "decoding": "free"},
    "B": {"prompt": "few_shot", "decoding": "free", "k": 3, "demo_kind": "short"},
    "C": {"prompt": "zero_shot", "decoding": "constrained"},
    "D": {"prompt": "few_shot", "decoding": "constrained", "k": 3, "demo_kind": "short"},
}


def _load_cases() -> list[dict[str, Any]]:
    path = SUITE / "cases.jsonl"
    if not path.is_file():
        from ntruth.training.fewshot_p0_fixtures import write_fixture_suite

        write_fixture_suite(SUITE)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _short_gold_for_stage(case: dict[str, Any], stage: StageName) -> dict[str, Any]:
    """Demo SHORT: output minimo conforme allo stage, derivato dal gold completo."""

    gold = case["gold"]
    case_id = case["case_id"]
    file_id = f"file-{case_id}"
    spans = gold.get("evidence_spans") or []
    nodes = gold.get("candidate_nodes") or []
    counts = gold.get("counts") or []
    edges = gold.get("candidate_edges") or []
    factors = gold.get("factors") or []
    endpoints = gold.get("endpoints") or []

    mini_spans = [
        {
            "evidence_id": s.get("evidence_id", f"ev-{i}"),
            "file_id": s.get("file_id", file_id),
            "text": s.get("text", "")[:120],
            "start": int(s.get("start") or 0),
            "end": int(s.get("end") or max(1, len(s.get("text") or "x"))),
            "confidence": float(s.get("confidence") or 0.5),
        }
        for i, s in enumerate(spans[:3])
    ]
    mini_entities = [
        {
            "node_id": n.get("node_id", f"n-{i}"),
            "label": n.get("label", ""),
            "node_type": (
                (n.get("node_type") or {}).get("value")
                if isinstance(n.get("node_type"), dict)
                else str(n.get("node_type") or "OTHER")
            ),
            "evidence_ids": list(n.get("evidence_ids") or []),
            "confidence": float(n.get("confidence") or 0.5),
        }
        for i, n in enumerate(nodes[:4])
    ]
    mini_counts = []
    for i, c in enumerate(counts[:3]):
        mini_counts.append(
            {
                "count_id": c.get("count_id", f"c-{i}"),
                "quantifier": c.get("quantifier") or "UNKNOWN",
                "value": c.get("value"),
                "lower_bound": c.get("lower_bound"),
                "upper_bound": c.get("upper_bound"),
                "unit_label": str(
                    ((c.get("unit_type") or {}) or {}).get("value")
                    if isinstance(c.get("unit_type"), dict)
                    else c.get("population_scope") or ""
                ),
                "evidence_ids": list(c.get("evidence_ids") or []),
                "confidence": float(c.get("confidence") or 0.5),
            }
        )
    node_by_id = {n.get("node_id"): n for n in nodes}
    mini_rels = []
    for i, e in enumerate(edges[:3]):
        src = node_by_id.get(e.get("source_id"), {})
        tgt = node_by_id.get(e.get("target_id"), {})
        rel = e.get("relation_type") or {}
        rel_v = rel.get("value") if isinstance(rel, dict) else str(rel)
        if rel_v not in {"nested_in", "derived_from"}:
            rel_v = "other"
        mini_rels.append(
            {
                "edge_id": e.get("edge_id", f"e-{i}"),
                "source_label": src.get("label", e.get("source_id", "")),
                "target_label": tgt.get("label", e.get("target_id", "")),
                "relation_type": rel_v,
                "evidence_ids": list(e.get("evidence_ids") or []),
                "confidence": float(e.get("confidence") or 0.5),
            }
        )

    prov = {
        "stage_run_id": f"demo-{case_id}",
        "stage": stage if stage != "candidate_graph_minimal" else "candidate_graph_set",
        "authority": "model",
        "producer": "ntruth-short-demo",
        "producer_version": "1.0.0",
    }
    if stage == "evidence_extraction":
        return {
            "schema_version": "1.0.0",
            "stage": "evidence_extraction",
            "result_id": f"demo-ev-{case_id}",
            "status": "complete",
            "provenance": {**prov, "stage": "evidence_extraction"},
            "evidence_spans": mini_spans,
        }
    if stage == "entity_count":
        return {
            "schema_version": "1.0.0",
            "stage": "entity_count",
            "result_id": f"demo-ec-{case_id}",
            "status": "complete",
            "provenance": {**prov, "stage": "entity_count"},
            "entities": mini_entities,
            "counts": mini_counts,
        }
    if stage == "candidate_relations":
        return {
            "schema_version": "1.0.0",
            "stage": "candidate_relations",
            "result_id": f"demo-rel-{case_id}",
            "status": "complete",
            "provenance": {**prov, "stage": "candidate_relations"},
            "relations": mini_rels,
        }
    # minimal graph
    return {
        "schema_version": "1.0.0",
        "stage": "candidate_graph_set",
        "result_id": f"demo-g-{case_id}",
        "graph_set_id": f"demo-graph-{case_id}",
        "status": "complete",
        "provenance": {**prov, "stage": "candidate_graph_set"},
        "experiment_block_title": (gold.get("experiment_blocks") or [{}])[0].get(
            "title", ""
        )
        if gold.get("experiment_blocks")
        else "",
        "evidence_spans": mini_spans,
        "entities": mini_entities,
        "counts": mini_counts,
        "factors": [
            {
                "factor_id": f.get("factor_id", f"f-{i}"),
                "name": f.get("name", ""),
                "levels": list(f.get("levels") or []),
                "evidence_ids": list(f.get("evidence_ids") or []),
            }
            for i, f in enumerate(factors[:2])
        ],
        "endpoints": [
            {
                "endpoint_id": e.get("endpoint_id", f"ep-{i}"),
                "name": e.get("name", ""),
                "evidence_ids": list(e.get("evidence_ids") or []),
            }
            for i, e in enumerate(endpoints[:2])
        ],
        "relations": mini_rels,
        "missing_fact_predicates": [
            m.get("predicate", "")
            for m in (gold.get("missing_facts") or [])[:2]
            if m.get("predicate")
        ],
    }


def _system_for_stage(stage: StageName) -> str:
    from ntruth.model_backends.stage_schemas import STAGE_PROMPTS

    return (
        "You are the local N-Truth candidate-fact parser. "
        + STAGE_PROMPTS[stage]
        + " Return exactly one JSON object. No markdown."
    )


def _build_messages(
    case: dict[str, Any],
    demos: list[dict[str, Any]],
    *,
    stage: StageName,
    few_shot: bool,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _system_for_stage(stage)}
    ]
    user_payload = {
        "parser_input": case["parser_input"],
        "source_text": case.get("source_text", ""),
        "case_id": case["case_id"],
    }
    if few_shot:
        for demo in demos:
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "parser_input": demo["parser_input"],
                            "source_text": demo.get("source_text", ""),
                            "case_id": demo["case_id"],
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        _short_gold_for_stage(demo, stage),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                }
            )
    messages.append(
        {
            "role": "user",
            "content": json.dumps(
                user_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
        }
    )
    return messages


def _assess_stage(raw: str, stage: StageName) -> dict[str, Any]:
    from ntruth.model_backends.base import MODEL_MUST_NOT_EMIT
    from ntruth.model_backends.stage_schemas import stage_schema
    from ntruth.training.candidate_conformance import extract_json_object, find_forbidden_keys

    schema_cls = stage_schema(stage)
    payload, err = extract_json_object(raw)
    out: dict[str, Any] = {
        "json_parse": payload is not None,
        "schema_valid": False,
        "candidate_only": True,
        "forbidden_keys": [],
        "validation_error": err,
        "required_field_completeness": 0.0,
    }
    if payload is None:
        return out
    forbidden = find_forbidden_keys(payload)
    # Also scan nested string keys lightly
    blob = json.dumps(payload)
    for key in MODEL_MUST_NOT_EMIT:
        if f'"{key}"' in blob:
            forbidden.append(key)
    out["forbidden_keys"] = sorted(set(forbidden))
    out["candidate_only"] = len(out["forbidden_keys"]) == 0
    try:
        model = schema_cls.model_validate(payload)
        out["schema_valid"] = True
        out["validation_error"] = None
        dumped = model.model_dump(mode="json")
        # completeness: fraction of list fields non-empty if gold would have items — here structural
        list_fields = [
            k for k, v in dumped.items() if isinstance(v, list)
        ]
        out["required_field_completeness"] = 1.0  # schema valid ⇒ required present
        out["list_field_counts"] = {k: len(dumped[k]) for k in list_fields}
    except Exception as exc:  # noqa: BLE001
        out["validation_error"] = str(exc)
    return out


def compute_max_tokens_budget(cases: list[dict[str, Any]], stage: StageName, backend: Any) -> dict[str, Any]:
    """max_tokens ≥ p95(gold_output_tokens) × 1.5, capped."""

    token_counts: list[int] = []
    for case in cases:
        gold = _short_gold_for_stage(case, stage)
        text = json.dumps(gold, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        token_counts.append(len(backend.tokenize(text)))
    token_counts.sort()
    if not token_counts:
        p95 = 256
    else:
        idx = min(len(token_counts) - 1, int(round(0.95 * (len(token_counts) - 1))))
        p95 = token_counts[idx]
    budget = max(256, int(p95 * 1.5))
    # Cap runtime-friendly for stage outputs
    budget = min(budget, 1024 if stage != "candidate_graph_minimal" else 1536)
    return {
        "gold_output_token_counts": token_counts,
        "p50": int(statistics.median(token_counts)) if token_counts else 0,
        "p95": p95,
        "max_tokens": budget,
        "formula": "max(256, p95*1.5) capped",
    }


def audit_baseline(backend: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    demos = [c for c in cases if c["split"] == "demo"][:3]
    evals = [c for c in cases if c["split"] == "eval"]
    demo_lens = []
    for d in demos:
        full = json.dumps(d["gold"], separators=(",", ":"), sort_keys=True)
        short = json.dumps(
            _short_gold_for_stage(d, "candidate_graph_minimal"),
            separators=(",", ":"),
            sort_keys=True,
        )
        demo_lens.append(
            {
                "case_id": d["case_id"],
                "full_chars": len(full),
                "full_tokens": len(backend.tokenize(full)),
                "short_chars": len(short),
                "short_tokens": len(backend.tokenize(short)),
            }
        )
    from ntruth.model_backends.stage_schemas import stage_json_schema
    from ntruth.model_backends.constrained import compile_schema_probe, probe_outlines_mlx
    from ntruth.model_backends.stage_schemas import STAGE_SCHEMA_REGISTRY

    schema_sizes = {}
    for name, cls in STAGE_SCHEMA_REGISTRY.items():
        schema_sizes[name] = compile_schema_probe(cls)

    return {
        "mlx_library_default_max_tokens": backend.MLX_LIBRARY_DEFAULT_MAX_TOKENS,
        "eos_token": getattr(backend._tokenizer, "eos_token", None),
        "constrained": (
            lambda c: {
                "status": c.status.value,
                "backend": c.backend,
                "detail": c.detail,
            }
        )(probe_outlines_mlx()),
        "n_eval": len(evals),
        "n_demo_available": len([c for c in cases if c["split"] == "demo"]),
        "demo_lengths": demo_lens,
        "schema_compile": schema_sizes,
        "schema_json_bytes": {
            k: len(json.dumps(stage_json_schema(k)).encode())
            for k in STAGE_SCHEMA_REGISTRY
        },
        "official_status": {
            "migration_status": "ARCHITECTURE_MIGRATED",
            "runtime_qualification_status": "PARTIALLY_VERIFIED",
            "scientific_validation_status": "NOT_STARTED",
        },
    }


def run_matrix(
    *,
    stage: StageName,
    conditions: list[Condition],
    limit: int | None,
    seed: int,
    temperature: float,
) -> dict[str, Any]:
    from ntruth.model_backends.base import GenerationRequest, SamplingConfig
    from ntruth.model_backends.factory import create_model_backend
    from ntruth.model_backends.stage_schemas import stage_schema
    from ntruth.training.mlx_runtime import load_profile

    cases = _load_cases()
    demos_all = [c for c in cases if c["split"] == "demo"]
    evals = [c for c in cases if c["split"] == "eval"]
    if limit is not None:
        evals = evals[:limit]
    # SHORT demos: prefer empty/simple first then others; exclude same case ids
    demos = demos_all[:3]

    profile = load_profile(PROFILE)
    model_path = (REPO / profile["model"]["local_path"]).resolve()
    backend = create_model_backend(model_path=model_path, profile=profile, max_tokens=2048)
    backend.load()

    try:
        audit = audit_baseline(backend, cases)
        budget = compute_max_tokens_budget(
            demos_all + evals[: min(20, len(evals))], stage, backend
        )
        max_tokens = budget["max_tokens"]
        report: dict[str, Any] = {
            "experiment": "B4_constrained_matrix",
            "stage": stage,
            "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "fingerprint_note": "same PARTIALLY_VERIFIED MLX artifact",
            "weight_sha256": profile.get("model", {}).get("expected_weight_sha256"),
            "seed": seed,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "token_budget": budget,
            "audit": audit,
            "eval_case_ids": [c["case_id"] for c in evals],
            "demo_case_ids": [d["case_id"] for d in demos],
            "conditions": {},
            "scientific_validation_status": "NOT_STARTED",
            "runtime_qualification_status": "PARTIALLY_VERIFIED",
        }

        schema_cls = stage_schema(stage)
        for cond in conditions:
            meta = CONDITIONS[cond]
            few_shot = meta["prompt"] == "few_shot"
            constrained = meta["decoding"] == "constrained"
            rows: list[dict[str, Any]] = []
            for case in evals:
                messages = _build_messages(
                    case, demos, stage=stage, few_shot=few_shot
                )
                # Prompt token count
                prompt = backend.apply_chat_template(messages, add_generation_prompt=True)
                prompt_tokens = len(backend.tokenize(prompt))
                req = GenerationRequest(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    constrained=constrained,
                    output_schema=schema_cls if constrained else None,
                    schema_name=stage if constrained else None,
                    sampling=SamplingConfig(temperature=temperature, seed=seed),
                    task_tag=f"TASK_{stage.upper()}",
                )
                t0 = time.perf_counter()
                try:
                    gen = backend.generate_structured(req)
                    error = None
                except Exception as exc:  # noqa: BLE001
                    gen = None
                    error = str(exc)
                latency = (time.perf_counter() - t0) * 1000.0
                if gen is None:
                    row = {
                        "case_id": case["case_id"],
                        "kind": case["kind"],
                        "error": error,
                        "json_parse": False,
                        "schema_valid": False,
                        "candidate_only": True,
                        "truncated": False,
                        "input_tokens": prompt_tokens,
                        "output_tokens": 0,
                        "max_tokens": max_tokens,
                        "latency_ms": latency,
                    }
                else:
                    assess = _assess_stage(gen.text, stage)
                    row = {
                        "case_id": case["case_id"],
                        "kind": case["kind"],
                        "input_tokens": gen.input_tokens,
                        "output_tokens": gen.output_tokens,
                        "max_tokens": gen.max_tokens or max_tokens,
                        "terminated_by_eos": gen.terminated_by_eos,
                        "terminated_by_stop": gen.terminated_by_stop,
                        "truncated": gen.truncated,
                        "finish_reason": gen.finish_reason,
                        "constrained_status": gen.constrained_status,
                        "json_parse": assess["json_parse"],
                        "schema_valid": assess["schema_valid"],
                        "candidate_only": assess["candidate_only"],
                        "forbidden_keys": assess["forbidden_keys"],
                        "validation_error": assess.get("validation_error"),
                        "required_field_completeness": assess.get(
                            "required_field_completeness"
                        ),
                        "latency_ms": latency,
                        "raw_preview": (gen.text or "")[:800],
                        "prompt_tokens_est": prompt_tokens,
                    }
                rows.append(row)
                print(
                    f"[{cond}/{stage}] {case['case_id']}: "
                    f"json={row.get('json_parse')} schema={row.get('schema_valid')} "
                    f"trunc={row.get('truncated')} cand={row.get('candidate_only')} "
                    f"out_tok={row.get('output_tokens')} ms={row.get('latency_ms'):.0f}",
                    flush=True,
                )

            n = len(rows) or 1
            summary = {
                "records": len(rows),
                "json_extractable_rate": sum(bool(r.get("json_parse")) for r in rows) / n,
                "schema_valid_rate": sum(bool(r.get("schema_valid")) for r in rows) / n,
                "candidate_only_rate": sum(bool(r.get("candidate_only")) for r in rows) / n,
                "truncation_rate": sum(bool(r.get("truncated")) for r in rows) / n,
                "forbidden_field_rate": sum(bool(r.get("forbidden_keys")) for r in rows) / n,
                "mean_latency_ms": sum(float(r.get("latency_ms") or 0) for r in rows) / n,
                "mean_output_tokens": sum(int(r.get("output_tokens") or 0) for r in rows) / n,
                "mean_input_tokens": sum(int(r.get("input_tokens") or 0) for r in rows) / n,
            }
            report["conditions"][cond] = {
                "meta": meta,
                "summary": summary,
                "rows": rows,
            }
        report["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return report
    finally:
        backend.unload()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=[
            "evidence_extraction",
            "entity_count",
            "candidate_relations",
            "candidate_graph_minimal",
        ],
        default="evidence_extraction",
    )
    parser.add_argument(
        "--conditions",
        default="A,B,C,D",
        help="Comma-separated subset of A,B,C,D",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument(
        "--all-stages",
        action="store_true",
        help="Esegue i 4 stage in sequenza (A→D per ciascuno).",
    )
    args = parser.parse_args()
    conditions = [c.strip().upper() for c in args.conditions.split(",") if c.strip()]
    for c in conditions:
        if c not in CONDITIONS:
            print(f"condizione sconosciuta: {c}", file=sys.stderr)
            return 2

    OUT.mkdir(parents=True, exist_ok=True)

    if args.audit_only:
        from ntruth.model_backends.factory import create_model_backend
        from ntruth.training.mlx_runtime import load_profile

        profile = load_profile(PROFILE)
        model_path = (REPO / profile["model"]["local_path"]).resolve()
        backend = create_model_backend(
            model_path=model_path, profile=profile, max_tokens=512
        )
        backend.load()
        try:
            report = audit_baseline(backend, _load_cases())
        finally:
            backend.unload()
        path = OUT / "audit.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    stages: list[StageName]
    if args.all_stages:
        stages = [
            "evidence_extraction",
            "entity_count",
            "candidate_relations",
            "candidate_graph_minimal",
        ]
    else:
        stages = [args.stage]  # type: ignore[list-item]

    combined: dict[str, Any] = {
        "experiment": "B4_constrained_matrix",
        "stages": {},
        "scientific_validation_status": "NOT_STARTED",
        "runtime_qualification_status": "PARTIALLY_VERIFIED",
    }
    for stage in stages:
        print(f"\n===== STAGE {stage} =====", flush=True)
        report = run_matrix(
            stage=stage,
            conditions=conditions,  # type: ignore[arg-type]
            limit=args.limit,
            seed=args.seed,
            temperature=args.temperature,
        )
        combined["stages"][stage] = {
            "max_tokens": report["max_tokens"],
            "token_budget": report["token_budget"],
            "summaries": {
                cond: data["summary"]
                for cond, data in report["conditions"].items()
            },
        }
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = OUT / f"matrix-{stage}-{stamp}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        latest = OUT / f"matrix-{stage}-latest.json"
        latest.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"wrote {path.relative_to(REPO)}")

    combined_path = OUT / "matrix-summary-latest.json"
    combined_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    print(json.dumps(combined, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
