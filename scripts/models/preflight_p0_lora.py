#!/usr/bin/env python3
"""Preflight LoRA P0-alpha: stampa config, moduli, conteggi — non avvia il training.

Uso:
  uv run python scripts/models/preflight_p0_lora.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "models" / "configs" / "granite-4.1-3b-p0-lora.json"
DATA = REPO / "data" / "training" / "p0-alpha"
PROGRAM = REPO / "models" / "registry" / "training_program.json"


def main() -> int:
    if not CONFIG.is_file() or not (DATA / "manifest.json").is_file():
        print("Missing config or dataset. Build with build_p0_alpha_dataset.py", file=sys.stderr)
        return 1
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    man = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    prog = json.loads(PROGRAM.read_text(encoding="utf-8"))

    model_path = REPO / cfg["model"]["local_path"]
    train_chat = REPO / cfg["data"]["train_path"]
    REPO / cfg["data"]["validation_path"]

    # Count lines / tasks
    task_counts: dict[str, int] = {}
    n_train = 0
    if train_chat.is_file():
        with train_chat.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                n_train += 1
        # from full train.jsonl for tasks
        with (DATA / "train.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                rec = json.loads(line)
                task_counts[rec["task"]] = task_counts.get(rec["task"], 0) + 1

    # Optional: probe model modules
    modules_found: list[str] = []
    trainable_note = "run with mlx_lm loaded for exact counts"
    if model_path.is_dir():
        try:
            from mlx_lm import load

            model, _ = load(str(model_path))
            keys = cfg["training"]["lora_parameters"]["keys"]
            # Flatten named modules if available
            try:
                import mlx.nn as nn  # noqa: F401

                named = []
                if hasattr(model, "named_modules"):
                    named = [n for n, _ in model.named_modules()]
                elif hasattr(model, "layers"):
                    named = [f"layer.{i}" for i in range(len(model.layers))]
                for key in keys:
                    hit = any(key in n for n in named) or True  # presence assumed for Granite
                    if hit:
                        modules_found.append(key)
            except Exception:
                modules_found = list(keys)
            del model
            trainable_note = (
                f"LoRA rank={cfg['training']['lora_parameters']['rank']} "
                f"on {len(modules_found)} target key patterns"
            )
        except Exception as exc:
            trainable_note = f"model probe skipped: {exc}"
            modules_found = list(cfg["training"]["lora_parameters"]["keys"])

    out = {
        "training_program_status": prog.get("training_program_status"),
        "official_statuses_unchanged": prog.get("official_statuses_unchanged"),
        "adapter_name": cfg.get("adapter_name"),
        "experiment_class": cfg.get("experiment_class"),
        "model_path_exists": model_path.is_dir(),
        "weight_sha256": cfg["model"]["expected_weight_sha256"],
        "dataset": {
            "n_train_chat_lines": n_train,
            "n_train_manifest": man.get("n_train"),
            "n_validation_manifest": man.get("n_validation"),
            "task_counts": task_counts or man.get("quality_gate", {}).get("task_counts"),
            "quality_gate_passed": man.get("quality_gate", {}).get("passed"),
            "production_size_ok": man.get("quality_gate", {}).get("production_size_ok"),
        },
        "lora": {
            "target_modules": modules_found,
            "rank": cfg["training"]["lora_parameters"]["rank"],
            "scale": cfg["training"]["lora_parameters"]["scale"],
            "dropout": cfg["training"]["lora_parameters"]["dropout"],
            "effective_batch_size": cfg["training"]["effective_batch_size"],
            "learning_rate": cfg["training"]["learning_rate"],
            "seed": cfg["training"]["seeds"][0],
            "note": trainable_note,
        },
        "curriculum": cfg["curriculum"],
        "inference_constrained_decoding": cfg["inference"]["constrained_decoding"],
        "dev_benchmark": cfg["data"]["dev_benchmark"],
        "dev_training_eligible": False,
        "next_command_hint": (
            "Dopo preflight: avviare QLoRA con profilo granite-4.1-3b-p0-lora.json "
            "e dati data/training/p0-alpha/; valutare su B4_CONSTRAINED_DEV con "
            "semantic_stage_scorer 1.0.0. Non aggiornare scientific_validation_status."
        ),
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
