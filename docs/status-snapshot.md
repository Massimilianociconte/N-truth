# N-Truth — verified project status snapshot

**Document role:** human-readable mirror of machine-readable gates.  
**Does not override** `models/registry/default.json` or `models/registry/training_program.json`.  
**Verified against those files on:** 2026-08-02 (documentation refresh).  
**Scientific validation has not started.** Software is experimental and not intended for scientific decision-making without human review.

## Capability ladder (do not collapse)

| Level | Meaning for N-Truth today |
|-------|---------------------------|
| Designed | PRD / ADRs / protocols describe the target |
| Implemented | Code paths exist in the repository |
| Tested | Automated software tests exist and (when run) exercise contracts |
| Runtime-verified | Artifact-bound host qualification for a **registered fingerprint** |
| Evaluated on development | Frozen B4_CONSTRAINED_DEV (39 cases) — not final test, not train |
| Validated on real gold | Independent real annotated gold — **not available** |
| Scientifically validated | External challenge / approved protocols — **`NOT_STARTED`** |
| Production-ready | **Not claimed** |

## Machine-readable gates (verified)

| Gate | Value | Source of truth |
|------|-------|-----------------|
| `migration_status` | `ARCHITECTURE_MIGRATED` | `models/registry/default.json` → `qualification` |
| `runtime_qualification_status` | `PARTIALLY_VERIFIED` | same (artifact-bound MLX community 4-bit only) |
| `scientific_validation_status` | `NOT_STARTED` | same |
| `training_program_status` | `P0_LORA_APPROVED` | `models/registry/training_program.json` |
| `training_execution_gate` | `HOLD_PENDING_REAL_ANCHOR` | same |
| `engineering_smoke_training_allowed` | `true` | same |
| `substantive_p0_training_allowed` | `false` | same |
| `current_synthetic_snapshot_status` | `SYN_G1_UNANCHORED` | same + `data/training/p0-alpha/manifest.json` |
| `annotation_protocol_status` | `REALITY_CHECK_PROTOCOL_DRAFT` | training program |
| `real_anchor_status` | `NOT_STARTED` | training program |
| First public trial status | `HUMAN_SECOND_REVIEW_PACKET_READY` | `first_public_source_protocol_trial` |

### Qualified runtime artifact (when PARTIALLY_VERIFIED)

- MLX repository: `mlx-community/granite-4.1-3b-4bit` (**community conversion, not official IBM**)
- Canonical model: `ibm-granite/granite-4.1-3b`
- Weights SHA-256 (registered): `cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d`
- MLX model revision: `b1b476b5a17c46b7d6cd663b4a8ed44b66720aef`
- Backend: `mlx-lm` (lock/registry: 0.31.3)

`PARTIALLY_VERIFIED` is **not** `VERIFIED`, **not** scientific validation, and does **not** transfer to adapters, GGUF, BF16 Transformers, other revisions, tokenizers, or chat templates.

## Neuro-symbolic architecture (normative description)

```text
experimental documents
  → AI parser (candidate facts only)
  → candidate evidence / entities / relations / graphs
  → human review or confirmation when required
  → Experiment Graph
  → deterministic rules engine
  → conditional derivations + rule/premise trace
```

The model **must not** be described as authorized to emit final:

- independent `n`;
- scientific verdicts;
- pseudoreplication verdicts as product truth;
- definitive statistical test choice;
- `RuleResult` as free-form model text;
- definitive inferential conclusions.

## Train A evaluation notes (development only)

- B4: **39** cases, `split_role=DEVELOPMENT`, `benchmark_role=B4_CONSTRAINED_DEV`, **not** training-eligible, **not** final test, **not** external challenge.
- Condition C (zero-shot + constrained decoding): schema/JSON validity high; semantic primary F1 all-case mean ≈ **0.17** (scorer 1.0.0; bootstrap CIs in `benchmarks/fewshot_p0/constrained/`).
- Decision recorded: `GO_LORA_P0` as **protocol design**, while `training_execution_gate` remains **HOLD**.
- P0-alpha: synthetic graph-first **2000** train / **300** validation, `SYN_G1_UNANCHORED`.
- Engineering smoke LoRA: label **`ENGINEERING_SMOKE_ONLY`** — not distributable, not promotable, not a scientific pre/post result.

## Annotation / real data

| Item | Status |
|------|--------|
| Protocol | `REALITY_CHECK_PROTOCOL_DRAFT` (guideline v0.1) |
| Dry-runs `reb-20260802-001/002` | `PROTOCOL_DRY_RUN` (not real gold) |
| First public trial `reb-20260802-003` | `REAL_SOURCE_PROTOCOL_TRIAL`; CC BY source registered |
| Primary freeze | yes |
| AI path-restricted second | yes (diagnostic only; **not** human IAA) |
| Human second review | **packet ready**, not started / not frozen |
| gold / training_eligible / evaluation_eligible / real_anchor_eligible | **false** |

Do not document: dry-run as real data; AI agreement as human IAA; packet-ready as review complete; single real trial as real anchor or gold.

## What this snapshot does **not** claim

- Production readiness  
- Scientific validation  
- That constrained decoding guarantees semantic correctness  
- That synthetic P0-alpha is human gold  
- That substantive LoRA has run or improved the model scientifically  

For operational HOLD rationale see [DECISION-hold-pending-real-anchor.md](training/DECISION-hold-pending-real-anchor.md).
