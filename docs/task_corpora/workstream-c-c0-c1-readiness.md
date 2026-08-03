# Workstream C readiness report — C0–C1 (draft)

**Status (maximum after this stage):**

```text
C0_TASK_CORPORA_SCAFFOLDING: VERIFIED
C1_SOURCEDATA_ENTITY_ROLES: VERIFIED
WORKSTREAM_C: IN_PROGRESS
READY_FOR_B0: CANDIDATE
```

**Not claimed:** Workstream C complete, ModernBERT training, scientific validation,
synthetic augmentation, N-Truth end-to-end training, Granite promotion.

## Baseline

| Item | Value |
|------|--------|
| Workstream B | `MERGED_AND_VERIFIED` (PR #2 → `ff8cd89`) |
| Branch | `feat/modernbert-task-corpora-v1` |
| Design docs | `docs/plans/modernbert-task-corpora-v1.md`, `docs/scientific/real-anchor-protocol-v0.1.md` |
| External root | `/Volumes/FLASH128/N-Truth-Datasets` |
| Output path | `task_corpora/entity_roles/sourcedata/v2.0.3/` |

## Decisions applied (approved)

1. MeasEval: hold pending overlap report; not implemented in C0–C1.
2. Licensing: machine-readable decision required; SourceData `RESTRICTED`, `training_allowed=false`.
3. Routing inventory labels reserved in config (adapter later).
4. Synthetic: **0%** for C0–C1 (`synthetic_fraction=0.0`).
5. Real anchor calibration: HOLD pending reviewers.
6. Lazic: EXTERNAL_CHALLENGE_CANDIDATE, not accessed.
7. ModernBERT checkpoint: deferred.

## Delivered

### C0 — task corpora scaffolding

Package `packages/ntruth/task_corpora/`:

- Canonical `TaskRecord` / `EntityRolesPayload` schemas (Pydantic)
- Enums: supervision, authority, licence status, exclusion reasons
- Fail-closed validators (token/label lengths, BIO known types, record invariants)
- Leakage group + split eligibility invariants
- License decision loader (fail-closed for training when restricted/unknown)
- Manifest, stats, exclusion reports
- Idempotent JSONL writers; LF-only JSONL readers (U+2028-safe)
- CLI: `build` / `validate` / `stats` / `status`

```bash
uv run python -m ntruth.task_corpora build --task entity_roles --source sourcedata --root "$NTRUTH_DATA_ROOT"
uv run python -m ntruth.task_corpora validate --task entity_roles --root "$NTRUTH_DATA_ROOT"
uv run python -m ntruth.task_corpora stats --task entity_roles --root "$NTRUTH_DATA_ROOT"
```

### C1 — SourceData → entity_roles

- Adapter: `adapters/sourcedata_entity_roles.py`
- Label map (code + doc): `label_maps/sourcedata_entity_roles.json`, `docs/task_corpora/sourcedata-entity-roles-label-map.md`
- License decision: `license_decisions/sourcedata.json`
- Authority: `AUXILIARY`; forbidden experimental-unit / n / verdict / allocation / independence gold
- `training_eligible=false` while licence `training_allowed=false`
- Upstream official splits preserved; leakage_group = document_id (fallback segment/record)

## Build evidence (FLASH128)

| Metric | Value |
|--------|--------|
| train | 60 266 |
| validation | 8 201 |
| test | 6 696 |
| exclusions | 0 |
| synthetic_fraction | 0.0 |
| training_allowed_by_licence | false |
| records_sha256 | `14638a55e96d7dd458d312774b7b1e93072383eedf5e70147d2991eb4a7b342c` |
| storage (corpus tree) | ~298 MiB |
| train.jsonl | ~239 MiB |
| validation.jsonl | ~33 MiB |
| test.jsonl | ~26 MiB |

Idempotence: second clean build and validate reproduce the same `records_sha256`.
Clean-run log (external only):  
`/Volumes/FLASH128/N-Truth-Datasets/task_corpora/entity_roles/sourcedata/v2.0.3/clean_run_log.txt`

### JSONL / U+2028 note

Scientific text includes U+2028 LINE SEPARATOR inside tokens. Readers must use
LF-only splitting (`str.split("\n")`), never `str.splitlines()`. Validate was
fixed accordingly; unit tests cover the trap.

## Acceptance checklist

| Criterion | Result |
|-----------|--------|
| Focused unit + integration tests | PASS |
| Full unit suite | PASS |
| ruff | PASS |
| mypy (`packages/ntruth/task_corpora`) | PASS |
| `git diff --check` | clean |
| No corpus in repository | PASS (no `task_corpora/` data at repo root; no `*.jsonl` under package) |
| No structural errors emitted | PASS (0 exclusions) |
| Reproducible splits (upstream) | PASS |
| Provenance + leakage_group on every record | PASS |
| Second-run hash identity | PASS |
| SourceData AUXILIARY, not NTRUTH_GOLD | PASS |
| No model download/train | PASS |

## Holds (unchanged)

```text
TRAINING_PROGRAM: HOLD_PENDING_REAL_ANCHOR
SCIENTIFIC_VALIDATION: NOT_STARTED
MODERNBERT_TRAINING: HOLD
SYNTHETIC_AUGMENTATION: HOLD
NTRUTH_END_TO_END_TRAINING: HOLD
GRANITE_GRAPH_TRAINING: HOLD
GRANITE_DEFAULT_PROMOTION: HOLD
MEASEVAL_TRAINING_USE: HOLD_PENDING_OVERLAP_REPORT
REAL_ANCHOR_CALIBRATION: HOLD_PENDING_REVIEWERS
```

## Next (out of scope for this PR)

1. Remaining adapters (MeasEval, PreClinIE, quantities, relations, …) under same scaffolding.
2. License scope closure → flip SourceData `training_allowed` only with written basis.
3. B0 encoder baseline after more corpora + resource benchmarks + checkpoint protocol.
4. Real-anchor calibration when wet-lab + biostat reviewers are available.

## Storage estimate (summary)

See `docs/task_corpora/storage-estimate-c0-c1.md`.
