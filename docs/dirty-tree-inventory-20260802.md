# Dirty-tree inventory (pre-publication)

**Date:** 2026-08-02  
**Machine-readable:** `docs/dirty-tree-inventory-20260802.json`  
**Policy:** no indiscriminate commit; no push; no merge.

```yaml
DOCUMENTATION_CONTENT: APPROVED
PUBLISHABLE_GITHUB_DOCS: FAIL
PUSH_TO_REMOTE: CONDITIONAL_FAIL
MERGE_TO_MAIN: HOLD
```

Scientific gates unchanged (local narrative only until versioned):

```yaml
scientific_validation_status: NOT_STARTED
training_execution_gate: HOLD_PENDING_REAL_ANCHOR
real_anchor_status: NOT_STARTED
trial_status: HUMAN_SECOND_REVIEW_PACKET_READY
```

## Counts (approx., porcelain + untracked)

| Cluster | n | Publishability focus |
|---------|---:|----------------------|
| GRANITE_BACKEND | 18 | code/config/tests/scripts |
| REGISTRY_QUAL | 8 | registry + manifests (careful) |
| CONSTRAINED_B4 | 37 | benchmarks/scorer harness |
| TRAINING_P0 | 25 | factory, LoRA config, smoke scripts |
| ANNOTATION (visible) | 3 | guideline + validators only |
| ADR_DOCS | 48 | ADRs + technical docs |
| OTHER_CODE | ~159 | Train D / desktop / package drift — separate review |
| INFRA | 3 | ci, gitignore, env.example |
| UNCATEGORIZED | 7 | pyproject, uv.lock, etc. |

**Note:** most `data/annotations/reality-check/**` is **gitignored** and does not appear as porcelain; treat as **local by default** even if present on disk.

## Cluster commit plan (order)

### 1. Backend e migrazione Granite
**Include:** `packages/ntruth/model_backends/**`, granite configs, legacy Qwen opt-in, `acquire_granite.py`, `qualify_granite_runtime.py`, unit tests.  
**Decide:** default model = Granite; Qwen only with explicit opt-in.  
**Config SoT:** registry owns `PARTIALLY_VERIFIED`; config is template or mirrors via explicit transition — **no dual status**.

### 2. Registry e qualificazione
**Include:** `models/registry/default.json`, `training_program.json`, public manifests under `models/ntruth-granite-3b/manifests/`.  
**Exclude by default:** `qualification_ledger.sqlite3`, raw evidence blobs (or document regenerate-from-manifests only).

### 3. Constrained decoding e B4
**Include:** Outlines path (already in backends), stage schemas, B4 cases/manifest, semantic-C reports, frozen predictions if public, scripts `run_b4_*`, `score_b4_*`, tests.  
**Exclude:** host-private run noise if any.

### 4. Training P0
**Include:** synthetic factory code, p0-alpha snapshot + DATASET_CARD, LoRA config, preflight, engineering-smoke **script** (not `models/runs/**` adapters).  
**Gate:** `HOLD_PENDING_REAL_ANCHOR` / `substantive_p0_training_allowed: false` must land with this cluster.

### 5. Annotazione (whitelist only)
**Publishable:**
- `docs/annotation-reality-check-p0-v0.1.md`
- schema + empty templates (if whitelisted out of ignore)
- process README
- validators under `scripts/annotations/`
- synthetic dry-run facsimiles only if explicitly marked and free of personal data

**Never default-publish:**
- full sources, human/AI submissions, freezes, profiles, private notes, prospective data, unauthorized bundles, future test set

Do **not** globally relax `data/annotations/*/`.

### 6. ADR e documentazione tecnica
**Include:** ADR 0011/0012, related granite docs, then **regenerate/rebase** public README/status-snapshot against clean tree.  
`ef39fb4` / `22c496e` remain audit evidence; rewrite if needed after code lands.

### 7. OTHER_CODE (~159)
Separate from Train A story: desktop D0 panels, rules/ontology bumps, API, CI. Commit only with own tests; do not mix into Granite/B4 commits.

## Annotation gitignore stance (locked)

```text
Whitelist optional: guideline, JSON Schema, empty templates, process README, synthetic facsimiles, non-sensitive metadata
Keep ignored: sources, submissions, profiles, private notes, freezes, unauthorized bundles, prospective data
```

## Config Granite incoerente — opzioni ammesse

1. Config = **historical template** labeled non-authoritative for qualification; or  
2. Remove operational status fields from config; **registry only**; or  
3. Update config via **explicit auditabile transition** matching registry.

Avoid two competing SoT.

## Definitive sequence (unchanged)

```text
this inventory
→ classify publishable / local / generated / sensitive
→ separate technical commits per cluster + tests
→ clean worktree with implementations
→ rebase or regenerate docs
→ clean-checkout verification PASS
→ push
→ review
→ merge
```

```text
NO PUSH · NO MERGE
until documented_implementation_is_committed
and clean_checkout_docs_consistent
```
