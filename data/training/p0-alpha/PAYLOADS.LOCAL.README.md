# Payload relocation notice (2026-08-27)

Repository policy (`scripts/check_repository_policy.py`) forbids tracking files
with corpus-payload semantics. The synthetic JSONL payloads of this snapshot and
this card's sibling `DATASET_CARD.md` are therefore **not git-tracked** anymore;
they remain in this local working tree at their canonical paths so that local
consumers (`scripts/models/preflight_p0_lora.py`,
`models/configs/granite-4.1-3b-p0-lora.json`) keep working unchanged.

## What stays tracked here

- `manifest.json` — frozen build parameters, checksums of train/validation
  payloads, gate results, statuses
- `TEST_REAL_PLACEHOLDER.README.md`
- `engineering-smoke-subset/README.md`, `engineering-smoke-subset/meta.json`

## How to restore payloads

```bash
uv run python scripts/regenerate_relocated_payloads.py --suite all --verify
```

- The B4 DEV suite input is rebuilt byte-identically from its deterministic
  factory.
- The p0-alpha rebuild runs the current renderer with the frozen parameters
  (2000/300, seed=13) but does **not** guarantee byte-equality with the frozen
  SYN_G1_UNANCHORED artifacts: family ordering inside the factory is not
  canonicalized. A regenerated snapshot is a NEW local snapshot; the writer
  refreshes `manifest.json` checksums itself.
- `engineering-smoke-subset/*.jsonl` has no tracked generator; preserve local
  copies manually (`ENGINEERING_SMOKE_ONLY`, not distributable). For plumbing
  checks prefer `ntruth-ml train --runtime-smoke-only`.

All payloads here are synthetic pre-adaptation material: NOT gold corpus, NOT
scientific validation, training execution gate remains HOLD_PENDING_REAL_ANCHOR.
