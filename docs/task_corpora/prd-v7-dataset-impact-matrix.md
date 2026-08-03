# PRD v7.0 — dataset / task-corpora impact matrix

**Sources (checksum-verified 2026-08-03):**

| File | SHA-256 |
|------|---------|
| `prd-v7.0.pdf` | `00b544f04796f73f75e859c4cbff0ba4193a314661d50d5258d4bc9b0a13369f` |
| `qwen-review-assessment-v1.0.pdf` | `6dab65698d5e098b41e766f956118890958c4bfd3676442b62ee974a82820efc` |

**Scope:** dataset acquisition, task corpora, external manifests, registries.
**Not owned here:** root Experiment Graph redesign, rules-engine semantics, Quick Design, root Reality Gate schema implementation.

**Appendix AA** (Implementation Status Snapshot) is **non-normative**. No Appendix AA claim is treated as verified without code/test/clean-checkout evidence.

## Impact matrix

| # | PRD v7 theme | Dataset-side requirement | Current LEGACY_WS_B / LEGACY_WS_C status | Gap / interface |
|---|--------------|--------------------------|------------------------------------------|-----------------|
| 1 | **Reality Gate** (§0.7) | Substantive training & AI claims blocked until real anchor, licence, frozen splits, human second review, real baseline, synthetic factory calibration | Manifest provisional fields: `reality_gate_status=BLOCKED`, public/silver cannot satisfy gate | Full Reality Gate schema = **root-alignment workflow**; dataset only records provisional status |
| 2 | **Bootstrap Core vs Full Scientific Record** | Silver task corpora are **not** Bootstrap Core / Full Record gold | SourceData entity_roles = AUXILIARY token tasks only | No Bootstrap Core fields in task_corpora; do not invent Core schema here |
| 3 | **Public/silver authority** (§14.1) | Silver auditato (SourceData, PreClinIE, CRAFT, MeasEval) **does not** replace real gold | `authority_level=AUXILIARY`; forbidden gold uses enforced | Keep forever unless profile-specific protocol says otherwise |
| 4 | **Cross-domain data roles** (§14.4) | Role is **profile-relative**; decide before full label access | Lazic revised to `ROLE_DECISION_PENDING` (PR #5) | Cross-domain Data Role Protocol is a root/governance deliverable; registry only records pending state |
| 5 | **Real-anchor requirements** | Reality check 3–5 → calibration 30–50 before claims | `REAL_ANCHOR_CALIBRATION: HOLD_PENDING_REVIEWERS` | Dataset workflow does not open calibration without reviewers |
| 6 | **Synthetic preconditions** (§14.8) | SYN-G0/G1 engineering OK; training-approved only after real dev + real-only baseline + hybrid comparison + audit | C0–C1 synthetic_fraction=0%; no factory | Do not implement global synthetic % budget |
| 7 | **Engineering vs scientific readiness** | Three independent tracks: engineering / data / scientific | `engineering_readiness=VERIFIED_FOR_C0_C1`, `data_readiness=BLOCKED`, `scientific_validation=NOT_STARTED` | Engineering green ≠ scientific GO |
| 8 | **Minimum Viable Train A** (§12.3) | B0/B4 + hard verifier + human review on Methods/caption; not full ModernBERT stack | READY_FOR_B0_GO **BLOCKED** (licence + provenance + Reality Gate) | B0 may be designed later under V7_WS_B; not unblocked by silver adapters |
| 9 | **Anti-leakage** (§14.7) | Article/family leakage groups; generator/teacher no test access | SourceData: `RECORD_LEVEL_FALLBACK`, document-level **UNVERIFIED** | C1.1 required before paper-level claims |
| 10 | **Licence / use-decision** | Granular permissions; unknown fail-closed | SourceData: build/validate allowed; development/training false; evaluation unknown | Licence scope closure before development or metrics publication |

## Explicit non-promotions

```text
public_corpora + structured_decoding + engineering_smoke + SYN-G1
  ≠ Reality Gate satisfaction

silver SourceData entity_roles
  ≠ experimental_unit_gold | independent_n_gold | allocation_gold
  ≠ biological_independence_gold | interference_gold | estimand_gold
  ≠ Bootstrap Core gold | v1.0-A validation
```

## Code verification notes (not Appendix AA)

Verified in repository against LEGACY_WS_C package (PR #3 merged, PR #4 lineage):

- `packages/ntruth/task_corpora/**` exists and is tested
- SourceData licence fail-closed for training/development
- dual-run hash + LF-only JSONL contract
- **Not** verified: full Reality Gate runtime, real-anchor corpus, ModernBERT training, B0 baseline execution

## Holds preserved

```text
MODERNBERT_TRAINING: HOLD
GRANITE_GRAPH_TRAINING: HOLD
NTRUTH_END_TO_END_TRAINING: HOLD
SCIENTIFIC_VALIDATION: NOT_STARTED
REAL_ANCHOR_CALIBRATION: HOLD_PENDING_REVIEWERS
READY_FOR_B0_GO: BLOCKED
SOURCE_DATA_DOCUMENT_LEVEL_LEAKAGE: UNVERIFIED
C1_1_SOURCEDATA_DOCUMENT_PROVENANCE: REQUIRED
```
