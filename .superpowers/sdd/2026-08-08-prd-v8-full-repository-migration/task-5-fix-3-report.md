# Task 5 fix round 3 report

## Status

**COMPLETE for the two scoped P1 review findings.**

- Base SHA: `f10b9224bf8dba42a59f112d043b4da21d2658c6`
- Worktree: `/Users/massimilianociconte/Documents/N-truth/.worktrees/prd-v8-full-20260808`
- Branch: `codex/prd-v8-full-migration-20260808`
- No training, model load/download, network access, external dataset access, Task 6
  implementation, or Task 7 authority was exercised.

## TDD checkpoints

The two P1 contracts were first encoded in the new focused regression file and
run before production changes:

```text
uv run pytest -q tests/unit/test_prd_v8_task5_fix3_regressions.py
11 failed
```

After the minimal implementation, the first focused GREEN was:

```text
uv run pytest -q -x tests/unit/test_prd_v8_task5_fix3_regressions.py
11 passed
```

The final self-review added the explicit public `predict_and_score()` protected
TEST integration from a real persisted sealed run-state. The final focused file
contains 12 passing regressions and is included in the 175-test compatibility
gate below.

## P1 A — Public protected TEST lineage

- Added the content-addressed, typed `TrainingDesignLineagePins` artifact. It
  carries only opaque planned/executed artifact IDs and SHA-256 pins; it assigns
  no scientific meaning and does not implement Task 6.
- `run_training()` and the CLI require the typed Task 6 artifact path and an
  independently resolved protected-source `DatasetManifest`. Missing or invalid
  inputs raise typed `TrainingLineageReviewRequired` with
  `SCIENTIFIC_REVIEW_REQUIRED` before snapshot or Reality Gate access.
- The run-state persists the typed artifact identity/file hash/path, all four
  planned/executed pins, and protected-source manifest ID/hash/path/records hash.
  Resume reconciles every field exactly.
- `_verify_best_run()` reloads both authoritative files, recomputes their pins,
  rejects drift, and surfaces the sealed lineage to the public evaluation path.
- `_verify_evaluation_snapshot()` independently validates the protected source
  manifest and reconciles its ID/hash with the run-state and custodial manifest.
- The public `predict_and_score()` regression starts with a real run-state and
  real protected manifest/source artifacts; it passes the actual `_verify_best_run`
  and protected snapshot validation boundaries without a hand-built lineage map.
- Final TEST release independently recomputes exact TEST record IDs, record count,
  and membership checksum from the embedded source `DatasetManifest`.

## P1 B — Actual MLX consumer seal

- Replaced the plain validation-as-test copy with a content-addressed
  `ValidationConsumerViewManifest`, exact two-file allowlist, source/payload hash
  reconciliation, and read-only directory/files.
- Both training and model-selection consumers open the staged directory with
  `O_DIRECTORY`/`O_NOFOLLOW` where available, enumerate and hash exact regular
  read-only files through that directory FD, and fail closed when `/dev/fd`
  handoff is unavailable.
- The MLX config receives `/dev/fd/<n>` rather than a reopenable workspace path;
  `_stream_command()` passes exactly that FD to the child with `pass_fds`.
- The context manager closes each file FD after hashing and closes the directory
  FD in `finally`, including config-write, subprocess-start, and subprocess
  failure paths.
- Replacement, symlink, unexpected-file, and protected-payload mutations are
  blocked before the subprocess. Tests also inspect both the emitted FD-backed
  config and the exact `pass_fds` tuple.

## Compatibility migrations

- Historical Task 5 tests that constructed partial run-lineage mappings now use
  real typed design/source fixtures where they exercise the public verifier.
- Protected release fixtures now carry exact `record_count` and
  `record_ids_checksum` pins.
- Existing Reality Gate tests supply valid opaque lineage inputs so they retain
  their original assertion: untrusted/stale Task 7 proposals block before any
  training payload or command runner.
- No legacy alias bypass was introduced.

## Validation

Final Task 5 compatibility gate (new fix-round file plus the prior 14 Task 5,
parser, v3/v7, dataset, snapshot, MLX, and evaluation-lineage files):

```text
uv run pytest -x <15 Task-5 compatibility files>
175 passed in 0.53s
```

Static gates:

```text
uv run ruff check <Task-5 production and focused tests>
All checks passed!

uv run ruff format --check <Task-5 production and focused tests>
180 files already formatted

uv run mypy packages/ntruth
Success: no issues found in 175 source files

git diff --check
clean
```

## Explicit blockers and scientific boundary

- Task 5 consumes only opaque Task 6 artifact pins. It does not define planned or
  executed design semantics. Absent authoritative pins remain
  `SCIENTIFIC_REVIEW_REQUIRED`.
- Task 5 still cannot issue an accepted Reality Gate v8 decision. Production
  training remains HOLD pending Task 7 authority.
- External Challenge evaluation/release remains HOLD pending Task 7's reviewed
  `ContaminationAttestation` and custody authority.

## Files

Production modified:

- `packages/ntruth/training/cli.py`
- `packages/ntruth/training/mlx_inference.py`
- `packages/ntruth/training/mlx_runtime.py`

Tests created/modified:

- `tests/unit/test_prd_v8_task5_fix3_regressions.py` (new; 12 tests)
- `tests/unit/test_mlx_evaluation_lineage.py`
- `tests/unit/test_prd_v8_task5_fix2_regressions.py`
- `tests/unit/test_prd_v8_task5_protected_runtime.py`
- `tests/unit/test_prd_v8_training_reality_gate_boundary.py`
