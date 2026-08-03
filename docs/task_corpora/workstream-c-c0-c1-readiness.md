# Workstream C readiness report — C0–C1

**Draft PR:** [#3](https://github.com/Massimilianociconte/N-truth/pull/3)
**Branch:** `feat/modernbert-task-corpora-v1`

## Status (maximum claimed)

```text
C0_TASK_CORPORA_SCAFFOLDING: VERIFIED
C1_SOURCEDATA_ENTITY_ROLES: VERIFIED
SOURCE_DATA_FORMAT_INTEGRITY: VERIFIED
SOURCE_DATA_TRAINING_USE: BLOCKED
SOURCE_DATA_EVALUATION_USE: PENDING_LICENCE_DECISION

WORKSTREAM_C: IN_PROGRESS
READY_FOR_B0: CANDIDATE
READY_FOR_MODERNBERT: NO

SCIENTIFIC_VALIDATION: NOT_STARTED
REAL_ANCHOR_CALIBRATION: HOLD_PENDING_REVIEWERS
SYNTHETIC_AUGMENTATION: HOLD
MEASEVAL_MODEL_USE: HOLD_PENDING_OVERLAP_POLICY
GRANITE_GRAPH_TRAINING: HOLD
NTRUTH_END_TO_END_TRAINING: HOLD
LAZIC_DATA: EXTERNAL_CHALLENGE_CANDIDATE
```

**Not claimed:** Workstream C complete, ModernBERT training, scientific validation,
promotional metrics, B0 development on SourceData without licence grants.

## Git / CI

| Item | Value |
|------|--------|
| Workstream B | PR #2 → `ff8cd89` |
| PR #3 base | `main` @ `ff8cd89` |
| Pre-closure head (C0–C1 impl) | `dabda342f3cd7182e50c0667eb5537a7e95be914` |
| CI on `dabda34` | **green** — deterministic-core, linux-portability, GitGuardian, CodeRabbit |
| Merge policy | **merge commit** (not squash); merge only after explicit user authorisation |

Final head SHA after this documentation/use-policy closure commit is recorded in the
PR once pushed (see PR commits tab).

## External corpus

| Item | Value |
|------|--------|
| Root | `/Volumes/FLASH128/N-Truth-Datasets` |
| Output | `task_corpora/entity_roles/sourcedata/v2.0.3/` |
| train / validation / test | **60266 / 8201 / 6696** |
| exclusions | **0** |
| synthetic_fraction | **0.0** |
| records_sha256 (post use-decision fields) | `0fe9c1190b10b49b8b2cd60fe32e7718f5041fda58858d79225e9c1831642fe2` |
| groups_crossing_splits | **0** |
| storage | ~298 MiB (not in git) |
| second-run idempotence | **OK** (identical hash) |

Hash changed from the first C1 build (`14638a55…`) because licence records now embed
granular use-decision fields and `evaluation_eligible` fails closed under
`evaluation_allowed=unknown`. Counts unchanged.

## Licence / use decision (SourceData)

```yaml
license_status: RESTRICTED
adapter_build_allowed: true
local_format_validation_allowed: true
development_allowed: false
training_allowed: false
evaluation_allowed: unknown          # fail closed
benchmark_metrics_publication_allowed: unknown
derived_records_redistribution_allowed: false
model_weights_redistribution_allowed: false
authority_level: AUXILIARY
```

Implications:

- Adapter build + local format validation: allowed.
- Weight training: **blocked**.
- B0 iterative development on this corpus: **blocked** until `development_allowed=true`.
- Held-out metrics / publication of benchmark numbers: **blocked** until evaluation
  and publication flags are explicitly true.
- `READY_FOR_B0` remains **CANDIDATE**, not GO.

## U+2028 / JSONL regression evidence

- Bug: `str.splitlines()` treated U+2028 inside tokens as record boundaries
  (train 60266 → 60318 phantom lines; hash drift).
- Fix: LF-only `iter_jsonl_physical_lines` + shared `records_content_sha256`.
- Contract: `docs/task_corpora/jsonl-framing-contract.md` and plan §JSONL framing.
- Tests: `test_jsonl_physical_lines_preserve_unicode_line_separator`,
  `test_cli_validate_with_unicode_line_separator_in_tokens`.

## Leakage audit

| Field | Value |
|-------|--------|
| groups_crossing_splits | **0** |
| unique_leakage_groups | 75163 (= total records) |
| leakage_group_granularity | **RECORD_LEVEL_FALLBACK** |
| document_id_present | **0** |
| document_id_missing | **75163** |

Upstream multitask snapshot has empty `document_id` / `segment_id` /
`split.group_id`. Leakage groups fall back to per-record IDs, so
`groups_crossing_splits=0` is true but **does not** yet prove paper-level isolation.
A Workstream B/C follow-up must restore document/figure family IDs before claiming
strong leakage control for encoder training.

## Acceptance checklist

| Criterion | Result |
|-----------|--------|
| Focused unit + integration tests | PASS |
| Full unit suite | PASS (run at commit) |
| ruff / mypy / `git diff --check` | PASS |
| NO_CORPUS in repository | PASS |
| Structural exclusions | 0 |
| Second-run hash identity | PASS |
| groups_crossing_splits == 0 | PASS (record-level caveat) |
| SourceData AUXILIARY, not NTRUTH_GOLD | PASS |
| No model download/train | PASS |
| Synthetic global % budget | **removed** (0% for C0–C1; no ≤10%) |

## Documentation closures in this pass

1. Plan status → C0–C1 implemented and verified; no training.
2. Synthetic ≤10% proposal → removed; task-specific mixture-search only.
3. Normative JSONL LF-only contract.
4. Granular use_decision fields with fail-closed unknown.
5. Leakage audit field `groups_crossing_splits`.
6. C2 PreClinIE design note only (`docs/task_corpora/c2-preclinie-design.md`).

## Next (out of this PR)

1. Merge PR #3 only after user authorisation (prefer **merge commit**).
2. Branch `feat/preclinie-routing-method-indicators-v1` (C2 design ready).
3. Restore document-level leakage IDs for SourceData multitask.
4. Licence scope closure for evaluation/development before B0.
5. C3 CRAFT → licence closure → B0 → C4 MeasEval → ModernBERT GO → real anchor.

## Storage

See `docs/task_corpora/storage-estimate-c0-c1.md`.
