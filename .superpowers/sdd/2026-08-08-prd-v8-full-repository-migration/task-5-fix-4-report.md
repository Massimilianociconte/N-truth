# Task 5 fix round 4 report

## Status

**COMPLETE for the single scoped P1 consumer-inode race.**

- Base SHA: `bacd2f19f163f72dd32f0f613ea548738e9f9cb4`
- Worktree: `/Users/massimilianociconte/Documents/N-truth/.worktrees/prd-v8-full-20260808`
- Branch: `codex/prd-v8-full-migration-20260808`
- No training, MLX/model import in the parent, model load/download, network access,
  external dataset access, or Task 6/7 implementation was performed.

## TDD checkpoints

The post-verification substitution and exact-FD child contracts were encoded
before production changes:

```text
uv run pytest -q tests/unit/test_prd_v8_task5_fix4_regressions.py
9 failed
```

The failures were specific to the reviewed defect: raw `mlx_lm` plus a directory
FD, absent child entrypoint/mapping/loader, no anonymous-file lifecycle, and a
dataset path in the config.

After implementation:

```text
uv run pytest -q -x tests/unit/test_prd_v8_task5_fix4_regressions.py
9 passed
```

## Implementation

### Parent-side anonymous seal

- The directory-FD handoff was removed. The parent opens every exact staged entry
  relative to a no-follow directory FD and verifies the complete allowlist.
- Required `train.jsonl`, `valid.jsonl`, or validation-derived `test.jsonl` bytes
  are streamed into `TemporaryFile` objects while SHA-256 and byte count are
  computed. Source and anonymous-file metadata are verified before handoff.
- Anonymous files must be regular, unlinked (`st_nlink == 0`), the exact expected
  size, rewound, and alive for the entire child call. Platforms unable to provide
  that invariant fail closed.
- Training inherits exactly two file FDs (`train`, `valid`). Model selection
  inherits exactly one file FD (`test`); the validation view manifest is verified
  but never passed to MLX.
- The MLX config contains only the literal
  `ntruth://mlx/inherited-jsonl-fds/v1`, never a dataset directory or `/dev/fd`
  path. The exact split-to-FD mapping is passed through a protected environment
  key and the same FD tuple is supplied via `pass_fds`.
- Callers cannot override the reserved FD environment key.
- `ExitStack` owns every anonymous file. Normal completion, subprocess-start
  failure, and non-zero command errors close every file exactly once; source and
  directory FDs are closed before child execution.

### Child-only packaged entrypoint

- Added `ntruth.training.mlx_fd_entrypoint`, whose module-level imports are stdlib
  only. It validates the sentinel, exact mode, exact mapping keys, unique open
  descriptors, anonymous regular-file status, UTF-8 JSONL shape, and non-empty
  rows before importing MLX.
- The child enforces the pinned `mlx-lm==0.31.3` runtime, lazily imports
  `mlx_lm.lora`, and replaces its already-bound `load_dataset` with a loader that
  constructs MLX datasets solely from the inherited JSON rows.
- The original inherited FDs remain alive for the child process lifetime. Reads
  use short-lived duplicates, so the mapping descriptors themselves are neither
  consumed nor closed before MLX executes.
- Hatch wheel discovery already includes every module under `packages/ntruth`;
  the separate wheel-content proof remains correctly owned by Task 9.

## Deterministic race and negative coverage

- Both training and model-selection tests replace the original directory entries
  after the anonymous copy but immediately before simulated child consumption.
  The child helper reads the original verified rows and never the injected
  `PROTECTED-REPLACEMENT` bytes.
- Missing and extra split mappings fail closed.
- The bound child loader returns datasets created from inherited rows only; the
  previous path loader cannot execute.
- Command, sentinel config, environment mapping, exact `pass_fds`, regular/unlinked
  metadata, absence of dataset paths, and cleanup for all subprocess outcomes are
  asserted.

## Compatibility migration

The fix-round-3 consumer test was migrated from its obsolete directory-FD
expectation to the anonymous file-FD contract. No legacy directory-path escape or
fallback remains.

## Validation

Final Task 5 compatibility gate, covering the new fix file and the prior 15 Task
5/parser/v3/v7/dataset/snapshot/MLX/evaluation files:

```text
uv run pytest -x <16 Task-5 compatibility files>
184 passed in 0.53s
```

Static gates:

```text
uv run ruff check packages/ntruth <focused tests>
All checks passed!

uv run ruff format --check packages/ntruth <focused tests>
178 files already formatted

uv run mypy packages/ntruth
Success: no issues found in 176 source files

git diff --check
clean
```

## Explicit scientific blockers

- Production training remains HOLD pending Task 7 Reality Gate authority.
- External Challenge remains HOLD pending the Task 7 contamination/custody
  decision.
- This change introduces no Task 6 design semantics and no scientific authority.

## Files

Production created/modified:

- `packages/ntruth/training/mlx_fd_entrypoint.py` (new)
- `packages/ntruth/training/mlx_runtime.py`

Tests created/modified:

- `tests/unit/test_prd_v8_task5_fix4_regressions.py` (new; 9 cases)
- `tests/unit/test_prd_v8_task5_fix3_regressions.py`
