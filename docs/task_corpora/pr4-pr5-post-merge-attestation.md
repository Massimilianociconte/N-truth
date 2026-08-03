# Post-merge attestation — PR #4 + PR #5

**Generated:** 2026-08-03T17:20:00Z (approx.)
**Final main SHA:** `c20ff395198728f878ecb0129d295b144500acca`
**Does not rewrite** historical C0–C1 readiness or PR #3 attestation.

## 1. Merges

| PR | Pre-merge head | Merge method | Merge SHA | Merged at (UTC) |
|----|----------------|--------------|-----------|-----------------|
| #4 | `b3418198a93a3e8af1a7a767f0351e2fb1ee7264` | merge commit | `02777c3323c90ce4c3c20b3fde08c8f1f5ec5fe2` | 2026-08-03T17:08:40Z |
| #5 | `68f0905be110818911472eee9e1bde15a6ae1138` (after merge of main) | merge commit | `c20ff395198728f878ecb0129d295b144500acca` | 2026-08-03T17:14:28Z |

### PR #4 CI (pre-merge)

- deterministic-core: SUCCESS — [30833720596](https://github.com/Massimilianociconte/N-truth/actions/runs/30833720596), [30833723173](https://github.com/Massimilianociconte/N-truth/actions/runs/30833723173)
- linux-portability: SUCCESS (same runs)
- GitGuardian / CodeRabbit: pass

### PR #5 update and CI (post–PR #4 main)

- Branch updated with `git merge origin/main` (no rebase, no force-push)
- Lazic semantics preserved: `ROLE_DECISION_PENDING`, `proposed_role: null`
- Fresh CI green:
  - deterministic-core: [30835595239](https://github.com/Massimilianociconte/N-truth/actions/runs/30835595239), [30835604544](https://github.com/Massimilianociconte/N-truth/actions/runs/30835604544)
  - linux-portability: SUCCESS (same runs)

## 2. Clean-checkout verification on final main

Worktree: `dataset-acquisition-pipeline` @ `c20ff39`
Historical worktree `docs/full-documentation-refresh-20260802`: **not modified**.

| Gate | Result |
|------|--------|
| full `tests/unit` | PASS |
| `tests/unit/task_corpora` | PASS |
| ruff check / format --check | PASS |
| mypy packages | PASS |
| `git diff --check` | clean |
| NO_CORPUS | PASS |
| privacy/PII registry scan | PASS (no emails in public registry) |
| smoke_release (wheel/sdist) | PASS |
| check_distribution UI assets | FAIL expected without desktop build (`ntruth/_ui/*` absent in local wheel) — not a scientific gate |

## 3. SourceData entity_roles rebuild (FLASH128)

Root: `/Volumes/FLASH128/N-Truth-Datasets`
Output: `task_corpora/entity_roles/sourcedata/v2.0.3/`

| Field | Value |
|-------|--------|
| train / validation / test | **60266 / 8201 / 6696** |
| exclusions | **0** |
| schema_version | **0.2.0** |
| transform_version | **0.2.0** |
| previous_records_sha256 | `0fe9c1190b10b49b8b2cd60fe32e7718f5041fda58858d79225e9c1831642fe2` |
| records_sha256 | `562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10` |
| manifest file sha256 | `0d0d3dff3925bf422797d655863df151544b9508d064bd94a521a5dd0a9f630f` |
| dual-run idempotence | **OK** |
| validate | **OK** |
| groups_crossing_splits | **0** (not paper-level proof) |
| leakage_group_granularity | **RECORD_LEVEL_FALLBACK** |
| document_id_present / missing | **0 / 75163** |
| partition_origin | UPSTREAM_SOURCEDATA |
| ntruth_partition_approved | false |
| model_use_status | BLOCKED |
| authority sample | AUXILIARY; training_eligible=false; evaluation_eligible=false |
| licence | training_allowed=false; development_allowed=false; evaluation_allowed=unknown |

### Content lineage (preserved)

1. `14638a55…` — initial C1
2. `0fe9c119…` — granular use-decision + evaluation fail-closed
3. `562b6ac9…` — schema/transform 0.2.0 + interference/estimand gold bans + readiness triad

## 4. Reality Gate / readiness triad

```text
engineering_readiness: VERIFIED_FOR_C0_C1
data_readiness: BLOCKED
scientific_validation: NOT_STARTED
reality_gate_status: BLOCKED
reality_gate_satisfied_by_public_corpora: false
reality_gate_satisfied_by_silver_adapter: false
```

## 5. Holds (explicit)

```text
SOURCE_DATA_DOCUMENT_LEVEL_LEAKAGE: UNVERIFIED
C1_1_SOURCEDATA_DOCUMENT_PROVENANCE: REQUIRED
READY_FOR_B0: CANDIDATE
READY_FOR_B0_GO: BLOCKED
SOURCE_DATA_DEVELOPMENT_USE: BLOCKED
SOURCE_DATA_TRAINING_USE: BLOCKED
SOURCE_DATA_EVALUATION_USE: PENDING_LICENCE_DECISION
MODERNBERT_TRAINING: HOLD
GRANITE_GRAPH_TRAINING: HOLD
NTRUTH_END_TO_END_TRAINING: HOLD
SCIENTIFIC_VALIDATION: NOT_STARTED
REAL_ANCHOR_CALIBRATION: HOLD_PENDING_REVIEWERS
LAZIC: ROLE_DECISION_PENDING, NOT_RECEIVED
NC3RS_ARRIVE: ANNOUNCED_NOT_RELEASED / AUXILIARY_CANDIDATE (no endorsement)
```

**Note:** `groups_crossing_splits=0` with `RECORD_LEVEL_FALLBACK` is **not** paper-level leakage protection.

## 6. Registry / Lazic (from merged PR #5)

```yaml
status: OFFERED_IN_PRINCIPLE_DETAILS_PENDING
cross_domain_role_status: ROLE_DECISION_PENDING
proposed_role: null
training_eligible: false
```

## 7. Ready for Qwen PRD-v7 root alignment

**Yes**, repository `main` is ready for the root-alignment workflow starting from:

```text
main @ c20ff395198728f878ecb0129d295b144500acca
```

Not from the older `0dcef3e`.

External mirror of this report (may include command logs):

`/Volumes/FLASH128/N-Truth-Datasets/reports/workstream_c/pr4_pr5_post_merge_attestation.md`

## Explicit non-actions in this operation

- No ModernBERT training
- No Granite download/promotion
- No Lazic data access
- No C2 PreClinIE implementation
- No Qwen root-alignment branch started here
