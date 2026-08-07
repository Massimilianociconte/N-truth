# Legacy ML profiles (unsupported as default)

Profiles here are **never** selected automatically by CLI, tests, or CI.

Rules:

1. No generic config may silently fall back to Qwen.
2. Opt-in only: `allow_legacy=True` **or** `NTRUTH_ALLOW_LEGACY_QWEN=1`.
3. Without opt-in, factory/registry raise.

- `qwen3-4b-instruct-2507-mlx-qlora.json` — historical Qwen3-4B bootstrap
  (pre–Granite migration). Ablation only.

Active default: `../granite-4.1-3b-mlx-qlora.json`
