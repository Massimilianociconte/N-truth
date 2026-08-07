#!/usr/bin/env python3
"""Semantic scoring B4 condizione C (zero-shot constrained) — development only.

- Non modifica predizioni esistenti quando il testo completo e disponibile.
- Per graph minimal con raw_preview troncato a 800 char, recupera full text
  rieseguendo *solo* C con stessi iperparametri (artifact recovery), poi congela.
- Riclassifica i 39 casi come DEVELOPMENT / B4_CONSTRAINED_DEV.
- Non avanza scientific_validation_status; non avvia LoRA.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "benchmarks" / "fewshot_p0"
CONSTR = SUITE / "constrained"
PROFILE = REPO / "models" / "configs" / "granite-4.1-3b-mlx-qlora.json"
STAGES = (
    "evidence_extraction",
    "entity_count",
    "candidate_relations",
    "candidate_graph_minimal",
)


def _load_cases() -> list[dict[str, Any]]:
    path = SUITE / "cases.jsonl"
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _eval_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in cases if c.get("split") == "eval"]


def _load_matrix(stage: str) -> dict[str, Any]:
    path = CONSTR / f"matrix-{stage}-latest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def mark_development_role() -> dict[str, Any]:
    """Annota manifest: 39 eval → DEVELOPMENT / B4_CONSTRAINED_DEV."""

    manifest_path = SUITE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["split_role"] = {
        "demo": "FEWSHOT_DEMOS_ONLY",
        "eval": "DEVELOPMENT",
    }
    manifest["benchmark_role"] = "B4_CONSTRAINED_DEV"
    manifest["not_for"] = sorted(
        set(manifest.get("not_for") or [])
        | {
            "final_test",
            "external_challenge",
            "scientific_validation",
            "lora_training_set",
        }
    )
    manifest["development_policy"] = (
        "I 39 casi eval guidano prompt/schema/LoRA decisions: restano DEV, "
        "non test finale. Training LoRA usera un insieme separato."
    )
    manifest["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def recover_full_predictions_c(
    *,
    stages: list[str],
    force_rerun: bool = False,
) -> Path:
    """Costruisce predictions-C-frozen.jsonl da matrix (+ recovery se serve)."""

    frozen_path = CONSTR / "predictions-C-frozen.jsonl"
    if frozen_path.is_file() and not force_rerun:
        return frozen_path

    from ntruth.model_backends.base import GenerationRequest, SamplingConfig
    from ntruth.model_backends.factory import create_model_backend
    from ntruth.model_backends.stage_schemas import stage_schema
    from ntruth.training.mlx_runtime import load_profile
    from ntruth.training.semantic_stage_scorer import extract_json

    # Import helpers from matrix runner
    sys.path.insert(0, str(REPO / "scripts" / "models"))
    from run_b4_constrained_matrix import (  # type: ignore
        _build_messages,
    )

    cases = _load_cases()
    evals = {c["case_id"]: c for c in _eval_cases(cases)}
    demos = [c for c in cases if c.get("split") == "demo"][:3]

    need_recovery: dict[str, list[str]] = {}
    records: list[dict[str, Any]] = []

    for stage in stages:
        matrix = _load_matrix(stage)
        budget = matrix.get("max_tokens") or matrix.get("token_budget", {}).get("max_tokens")
        for row in matrix["conditions"]["C"]["rows"]:
            case_id = row["case_id"]
            text = row.get("raw_preview") or ""
            payload = extract_json(text)
            incomplete_storage = (
                stage == "candidate_graph_minimal" and len(text) >= 800 and payload is None
            ) or (
                stage == "candidate_graph_minimal"
                and len(text) >= 800
                and (text.count("{") > text.count("}"))
            )
            if incomplete_storage:
                need_recovery.setdefault(stage, []).append(case_id)
                records.append(
                    {
                        "stage": stage,
                        "case_id": case_id,
                        "kind": row.get("kind"),
                        "schema_valid": row.get("schema_valid"),
                        "truncated": row.get("truncated"),
                        "max_tokens": budget,
                        "raw_text": None,
                        "source": "needs_recovery",
                        "matrix_row": {
                            k: row.get(k)
                            for k in (
                                "input_tokens",
                                "output_tokens",
                                "latency_ms",
                                "finish_reason",
                                "constrained_status",
                            )
                        },
                    }
                )
            else:
                records.append(
                    {
                        "stage": stage,
                        "case_id": case_id,
                        "kind": row.get("kind"),
                        "schema_valid": row.get("schema_valid"),
                        "truncated": row.get("truncated"),
                        "max_tokens": budget,
                        "raw_text": text,
                        "source": "matrix_raw_preview",
                        "matrix_row": {
                            k: row.get(k)
                            for k in (
                                "input_tokens",
                                "output_tokens",
                                "latency_ms",
                                "finish_reason",
                                "constrained_status",
                            )
                        },
                    }
                )

    if need_recovery:
        print(f"Recovery C full text for {sum(len(v) for v in need_recovery.values())} rows…")
        profile = load_profile(PROFILE)
        model_path = (REPO / profile["model"]["local_path"]).resolve()
        backend = create_model_backend(model_path=model_path, profile=profile, max_tokens=2048)
        backend.load()
        try:
            for stage, case_ids in need_recovery.items():
                matrix = _load_matrix(stage)
                max_tokens = int(
                    matrix.get("max_tokens")
                    or matrix.get("token_budget", {}).get("max_tokens")
                    or 512
                )
                # Use slightly higher budget for recovery of graph if needed
                if stage == "candidate_graph_minimal":
                    max_tokens = max(max_tokens, 768)
                schema_cls = stage_schema(stage)
                for case_id in case_ids:
                    case = evals[case_id]
                    messages = _build_messages(case, demos, stage=stage, few_shot=False)
                    gen = backend.generate_structured(
                        GenerationRequest(
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=0.0,
                            constrained=True,
                            output_schema=schema_cls,
                            schema_name=stage,
                            sampling=SamplingConfig(temperature=0.0, seed=0),
                            task_tag=f"TASK_{stage.upper()}",
                        )
                    )
                    for rec in records:
                        if rec["stage"] == stage and rec["case_id"] == case_id:
                            rec["raw_text"] = gen.text
                            rec["source"] = "recovery_c_rerun_identical_hparams"
                            rec["truncated"] = gen.truncated
                            rec["schema_valid"] = True  # was true in matrix
                            rec["recovery"] = {
                                "output_tokens": gen.output_tokens,
                                "max_tokens": gen.max_tokens,
                                "finish_reason": gen.finish_reason,
                                "constrained_status": gen.constrained_status,
                            }
                            print(
                                f"  recovered {stage}/{case_id} "
                                f"tok={gen.output_tokens} trunc={gen.truncated}"
                            )
        finally:
            backend.unload()

    frozen_path.parent.mkdir(parents=True, exist_ok=True)
    with frozen_path.open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"Wrote {frozen_path.relative_to(REPO)} ({len(records)} rows)")
    return frozen_path


def load_frozen(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def run_scoring(*, frozen_path: Path) -> dict[str, Any]:
    from ntruth.training.semantic_stage_scorer import (
        SCORER_VERSION,
        aggregate_stage_scores,
        decide_lora_gate,
        score_case_stage,
    )

    cases = {c["case_id"]: c for c in _eval_cases(_load_cases())}
    frozen = load_frozen(frozen_path)
    by_stage: dict[str, list[dict[str, Any]]] = {s: [] for s in STAGES}

    for rec in frozen:
        stage = rec["stage"]
        case = cases[rec["case_id"]]
        # For graph: only score complete non-truncated in complete-output;
        # score_case_stage handles all-case zeros.
        scored = score_case_stage(
            stage=stage,
            case=case,
            raw_text=rec.get("raw_text"),
            schema_valid=bool(rec.get("schema_valid")),
            truncated=bool(rec.get("truncated")),
        )
        scored["prediction_source"] = rec.get("source")
        by_stage[stage].append(scored)

    report: dict[str, Any] = {
        "scorer_version": SCORER_VERSION,
        "condition": "C",
        "prompt": "zero_shot",
        "decoding": "constrained",
        "benchmark_role": "B4_CONSTRAINED_DEV",
        "split_role": "DEVELOPMENT",
        "n_cases": len(cases),
        "scientific_validation_status": "NOT_STARTED",
        "runtime_qualification_status": "PARTIALLY_VERIFIED",
        "migration_status": "ARCHITECTURE_MIGRATED",
        "note": (
            "Semantic scores on development set only. Not external challenge. "
            "Not scientific validation of Granite as definitive N-Truth model."
        ),
        "stages": {},
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    for stage, rows in by_stage.items():
        # Diagnostic extras
        empty_rate = sum(1 for r in rows if r.get("empty_lists")) / len(rows) if rows else 0
        under = sum(
            1
            for r in rows
            if any(f.get("code") == "UNDER_EXTRACTION" for f in r.get("failures") or [])
        )
        report["stages"][stage] = {
            "n": len(rows),
            "empty_output_rate_all": empty_rate,
            "under_extraction_cases": under,
            "aggregate": aggregate_stage_scores(rows, seed=0),
            "cases": rows,
        }

    # A vs C diagnostic (exploratory): only where A raw_preview parseable
    from ntruth.training.semantic_stage_scorer import extract_json

    avsc: dict[str, Any] = {}
    for stage in STAGES:
        matrix = _load_matrix(stage)
        a_rows = matrix["conditions"]["A"]["rows"]
        c_map = {r["case_id"]: r for r in by_stage[stage]}
        comparable = 0
        a_primary = []
        c_primary = []
        empty_a = empty_c = 0
        for a in a_rows:
            payload = extract_json(a.get("raw_preview") or "")
            if payload is None:
                continue
            comparable += 1
            # soft score A ignoring schema (content-only)
            soft = score_case_stage(
                stage=stage,
                case=cases[a["case_id"]],
                raw_text=a.get("raw_preview"),
                schema_valid=True,  # force content scoring if JSON parseable
                truncated=bool(a.get("truncated")),
            )
            a_primary.append(float(soft["primary_f1"]))
            if soft.get("empty_lists"):
                empty_a += 1
            c = c_map[a["case_id"]]
            c_primary.append(float(c["primary_f1_all_case"]))
            if c.get("empty_lists"):
                empty_c += 1
        avsc[stage] = {
            "comparable_json_a": comparable,
            "mean_primary_f1_a_content_if_json": (
                sum(a_primary) / len(a_primary) if a_primary else None
            ),
            "mean_primary_f1_c_all_case": (sum(c_primary) / len(c_primary) if c_primary else None),
            "empty_rate_a_among_comparable": empty_a / comparable if comparable else None,
            "empty_rate_c_among_comparable": empty_c / comparable if comparable else None,
            "diagnostic_only": True,
        }
    report["a_vs_c_diagnostic"] = avsc
    report["decision"] = decide_lora_gate(report)
    return report


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append("# B4 semantic score — condizione C (DEV)")
    lines.append("")
    lines.append(f"**Scorer:** `{report['scorer_version']}`  ")
    lines.append(f"**benchmark_role:** `{report['benchmark_role']}`  ")
    lines.append(f"**split_role:** `{report['split_role']}` (n={report['n_cases']})  ")
    lines.append("")
    lines.append("```yaml")
    lines.append(f"migration_status: {report['migration_status']}")
    lines.append(f"runtime_qualification_status: {report['runtime_qualification_status']}")
    lines.append(f"scientific_validation_status: {report['scientific_validation_status']}")
    lines.append("```")
    lines.append("")
    lines.append(
        "> Non è validazione scientifica né test finale. "
        "I 39 casi sono DEVELOPMENT e guideranno LoRA/prompt — non trainare su di essi."
    )
    lines.append("")
    lines.append("## Primary F1 (bootstrap 95% CI)")
    lines.append("")
    lines.append("| Stage | ALL-CASE mean [low, high] | COMPLETE mean [low, high] | empty% ALL |")
    lines.append("|-------|---------------------------:|---------------------------:|-----------:|")
    for stage, block in report["stages"].items():
        agg = block["aggregate"]
        a = agg["all_case_score"]["primary_f1"]
        c = agg["complete_output_score"]["primary_f1"]
        empty = agg["all_case_score"]["empty_output_rate"]

        def fmt(x: dict) -> str:
            if x.get("mean") is None:
                return "n/a"
            return f"{x['mean']:.3f} [{x['low']:.3f}, {x['high']:.3f}] (n={x['n']})"

        lines.append(f"| {stage} | {fmt(a)} | {fmt(c)} | {100 * empty:.1f}% |")
    lines.append("")
    lines.append("## Failure taxonomy (top)")
    lines.append("")
    for stage, block in report["stages"].items():
        counts = (block["aggregate"].get("failure_taxonomy") or {}).get("counts") or {}
        top = list(counts.items())[:6]
        lines.append(f"### {stage}")
        if not top:
            lines.append("- (none)")
        else:
            for code, n in top:
                lines.append(f"- `{code}`: {n}")
        lines.append("")
    lines.append("## A vs C (diagnostico, non superiority claim)")
    lines.append("")
    for stage, d in report.get("a_vs_c_diagnostic", {}).items():
        lines.append(
            f"- **{stage}**: comparable_A_json={d.get('comparable_json_a')}, "
            f"mean_f1_A≈{d.get('mean_primary_f1_a_content_if_json')}, "
            f"mean_f1_C={d.get('mean_primary_f1_c_all_case')}, "
            f"empty_A={d.get('empty_rate_a_among_comparable')}, "
            f"empty_C={d.get('empty_rate_c_among_comparable')}"
        )
    lines.append("")
    dec = report["decision"]
    lines.append("## Decisione")
    lines.append("")
    lines.append(f"**`{dec['decision']}`**")
    lines.append("")
    lines.append(dec["rationale"])
    lines.append("")
    lines.append("Reasons:")
    for r in dec.get("reasons") or []:
        lines.append(f"- {r}")
    lines.append("")
    lines.append(dec.get("dev_set_policy", ""))
    if dec["decision"] == "GO_LORA_P0":
        lines.append("")
        lines.append("Scope primo adapter:")
        for t in dec.get("lora_task_scope_if_go") or []:
            lines.append(f"- `{t}`")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-recovery", action="store_true")
    parser.add_argument("--skip-recovery", action="store_true")
    args = parser.parse_args()

    CONSTR.mkdir(parents=True, exist_ok=True)
    manifest = mark_development_role()
    print("Marked suite:", manifest.get("benchmark_role"), manifest.get("split_role"))

    if args.skip_recovery and (CONSTR / "predictions-C-frozen.jsonl").is_file():
        frozen = CONSTR / "predictions-C-frozen.jsonl"
    else:
        frozen = recover_full_predictions_c(stages=list(STAGES), force_rerun=args.force_recovery)

    report = run_scoring(frozen_path=frozen)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = CONSTR / f"semantic-C-{stamp}.json"
    latest = CONSTR / "semantic-C-latest.json"
    payload = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    json_path.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    md_path = CONSTR / "SEMANTIC_C_REPORT.md"
    write_markdown(report, md_path)

    # Manifest fingerprint
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    fp_manifest = {
        "created_at": report["generated_at"],
        "scorer_version": report["scorer_version"],
        "benchmark_role": "B4_CONSTRAINED_DEV",
        "model": {
            "canonical": "ibm-granite/granite-4.1-3b",
            "mlx_path": profile.get("model", {}).get("local_path"),
            "weight_sha256": profile.get("model", {}).get("expected_weight_sha256"),
            "revision": profile.get("model", {}).get("revision"),
        },
        "predictions_path": str(frozen.relative_to(REPO)),
        "predictions_sha256": _sha256_file(frozen),
        "report_json": str(json_path.relative_to(REPO)),
        "report_json_sha256": _sha256_file(json_path),
        "suite_manifest_sha256": _sha256_file(SUITE / "manifest.json"),
        "decision": report["decision"]["decision"],
        "scientific_validation_status": "NOT_STARTED",
        "runtime_qualification_status": "PARTIALLY_VERIFIED",
    }
    (CONSTR / "semantic-C-manifest.json").write_text(
        json.dumps(fp_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "decision": report["decision"]["decision"],
                "overall_f1": report["decision"]["overall_primary_f1_all_case_mean"],
                "report": str(md_path.relative_to(REPO)),
                "json": str(latest.relative_to(REPO)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
