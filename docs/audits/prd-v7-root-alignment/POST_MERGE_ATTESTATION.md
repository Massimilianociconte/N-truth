# Post-merge attestation — PR #6 (PRD v7 root alignment)

**Engineering status only.** Does not resolve scientific blockers or modify FLASH128 dataset checkpoint.

## Merge record

| Field | Value |
|-------|--------|
| PR | [#6](https://github.com/Massimilianociconte/N-truth/pull/6) |
| Pre-merge head | `1ab2625d118862f2f055e6cbc859254c18dbe1de` |
| Base | `main` @ `fcce7bc871e08bdbaf89621a5bcb5b48f386715e` |
| Method | **merge commit** (not squash) |
| Merge SHA | `f2faace471788bdc4255e42fa88d5868f906e732` |
| Merged at (UTC) | `2026-08-03T18:21:21Z` |
| Final main (post-merge) | `f2faace471788bdc4255e42fa88d5868f906e732` |

### Pre-merge CI (green)

| Check | Runs |
|-------|------|
| deterministic-core SUCCESS | [30839860750](https://github.com/Massimilianociconte/N-truth/actions/runs/30839860750), [30839861968](https://github.com/Massimilianociconte/N-truth/actions/runs/30839861968) |
| linux-portability SUCCESS | same runs |
| GitGuardian | pass |
| CodeRabbit | pass (rate limited) |

Historical worktree `docs/full-documentation-refresh-20260802`: **untouched**.

## Clean worktree verification @ `f2faace`

Isolated worktree: `…/dataset-acquisition-pipeline` on `main`.

| Gate | Result |
|------|--------|
| `uv sync --extra dev --extra api --locked` | OK |
| `ruff check .` | PASS |
| `ruff format --check .` | PASS |
| `mypy packages` | PASS (145 source files) |
| `pytest --disable-warnings` | PASS (full suite) |
| `uv build` | PASS (wheel + sdist) |
| `scripts/smoke_release.py` | PASS |
| `scripts/check_distribution.py` | FAIL without UI assets in wheel unless desktop built first; UI `pnpm build` PASS separately |
| `git diff --check` | clean |
| Desktop vitest | 11/11 PASS |
| Desktop vite build | PASS |
| `tests/unit/test_prd_v7_*` focused set | PASS |
| `tests/unit/task_corpora` | PASS |
| NO_CORPUS | PASS |
| Public registry privacy (no emails) | PASS |

## Contract confirmations

```text
DeterminabilityStateV7: exactly 7 states
  DETERMINATE | CONDITIONALLY_DETERMINATE | MULTIPLE_PLAUSIBLE_GRAPHS
  | INSUFFICIENT_INFORMATION | CONFLICTING_INFORMATION | INVALID_GRAPH | OUT_OF_SCOPE

evaluate_reality_gate(()):
  data_readiness: BLOCKED
  scientific_validation: NOT_STARTED
  substantive_training_allowed: false
  ai_claims_allowed: false

EXPECTED_CURRENT_STATE:
  engineering_readiness: PARTIAL_OR_VERIFIED_BY_COMPONENT
  data_readiness: BLOCKED
  scientific_validation: NOT_STARTED
  substantive_training: HOLD_PENDING_REAL_ANCHOR
  modernbert_training: HOLD
  granite_promotion: HOLD

Lazic (registry):
  ROLE_DECISION_PENDING
  NOT_RECEIVED
  proposed_role: null
```

## Explicit non-actions this operation

- No FLASH128 access
- No SourceData rebuild
- No C1.1 / C2 / B0 / model training

## Maximum status claims (this attestation)

```text
PRD_V7_ROOT_CONTRACTS: IMPLEMENTED_OR_PARTIAL_BY_COMPONENT
ENGINEERING_READINESS: VERIFIED_BY_COMPONENT_ONLY
DATA_READINESS: BLOCKED
SCIENTIFIC_VALIDATION: NOT_STARTED
SUBSTANTIVE_TRAINING: HOLD_PENDING_REAL_ANCHOR
MODERNBERT_TRAINING: HOLD
GRANITE_PROMOTION: HOLD
```

## Dataset workflow unpark

The FLASH128 / dataset workflow may now be **unparked exclusively** for the
**root-to-dataset contract compatibility pass**, using:

```text
main @ f2faace471788bdc4255e42fa88d5868f906e732
```

Do **not** reopen acquisition, SourceData rebuild, or C2 unless that compatibility
pass determines a serialized record format change.

Dataset scientific holds remain:

```text
C1_1_SOURCEDATA_DOCUMENT_PROVENANCE: REQUIRED
SOURCE_DATA_DOCUMENT_LEVEL_LEAKAGE: UNVERIFIED
SOURCE_DATA_*_USE: BLOCKED / PENDING_LICENCE_DECISION
READY_FOR_B0_GO: BLOCKED
```
