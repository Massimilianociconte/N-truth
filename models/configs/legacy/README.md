# Legacy ML profiles (unsupported as default)

Profiles here are **never** selected automatically by CLI, tests, or CI.

Rules:

1. No generic config may silently fall back to Granite or Qwen.
2. Opt-in only: `allow_legacy=True` **or** `NTRUTH_ALLOW_LEGACY_GRANITE=1`
   (Granite) / `NTRUTH_ALLOW_LEGACY_QWEN=1` (Qwen).
3. Without opt-in, factory/registry raise.

- `granite-4.1-3b-mlx-qlora.json` — Granite 4.1 3B default profile until
  ADR-0019. Historical comparison arm only.
- `granite-4.1-3b-mlx.json` — Granite load-only technical profile (legacy).
- `granite-4.1-3b-p0-lora.json` — Granite P0 experiment (legacy).
- `qwen3-4b-instruct-2507-mlx-qlora.json` — historical Qwen3-4B bootstrap
  (pre–Granite migration). Ablation only.

Active default: `../minicpm5-2b-mlx-qlora.json`
