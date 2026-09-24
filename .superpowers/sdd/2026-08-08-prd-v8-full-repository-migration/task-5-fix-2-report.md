# Task 5 fix round 2 report

## Status

**COMPLETE — all eight residual P1 findings and the bounded P2 assertion defect are addressed.**

- Base SHA: `94c023558e9d5ca94da63a4ce46adb05b1a0178b`
- Worktree: `/Users/massimilianociconte/Documents/N-truth/.worktrees/prd-v8-full-20260808`
- Branch: `codex/prd-v8-full-migration-20260808`
- No training, model load/download, network access, dataset access, Task 6 change, or
  external-data mutation was performed.

## TDD evidence

The new regression file was created before production edits.

```text
uv run pytest -q tests/unit/test_prd_v8_task5_fix2_regressions.py
24 failed, 2 passed
```

The factor collision fixture was then made schema-valid and the Gold mutation
fixtures had their report checksum reconciled, proving that failures came from
the intended missing behavior rather than malformed setup. The corrected RED
remained:

```text
24 failed, 2 passed
```

The focused dependency slice became GREEN first:

```text
uv run pytest -q -x tests/unit/test_prd_v8_task5_fix2_regressions.py \
  -k 'stage_coverage or hard_verifier or candidate_ids or gold_manifest'
12 passed
```

The complete fix-round regression file then became GREEN:

```text
uv run pytest -q tests/unit/test_prd_v8_task5_fix2_regressions.py
26 passed
```

During self-review, the source DatasetManifest was strengthened from a colocated
copy to an independently resolved artifact. The two affected tests were made RED
first (`2 failed`) and then GREEN (`4 passed`, including External Challenge and
missing-design blocker cases).

## Implementation by review finding

1. **Exact request coverage and explicit legacy verifier.** `StageCoverage` is
   non-vacuous, unique, and status-coherent. A v8 stage must exactly partition
   every immutable request/provenance artifact into covered or missing IDs.
   Parser coverage mismatch yields typed `CHUNK_COVERAGE_INCOMPLETE`, with prior
   candidate artifacts preserved. `hard_verify_candidates` accepts only
   `ParserCandidateOutput`; historical bundles require the public, explicitly
   named `hard_verify_candidates_v7`.
2. **Global candidate identity.** Candidate IDs are globally unique across node,
   edge, factor, endpoint, contrast, estimand, count, event, graph, and alternative
   collections before any merged reference map is built.
3. **Complete Gold manifest reconciliation.** Prepared-record deserialization now
   checks candidate-target checksum, both submission IDs and checksums, comparison
   status, and material-difference checksum against the canonical
   `GoldParserTarget`, in addition to the existing adjudication/reviewer pins.
4. **Authoritative protected TEST membership and release pins.** A protected
   snapshot must resolve an independently located, content-addressed
   `DatasetManifest`; its ID/hash and exact TEST record membership are verified.
   TEST entries cannot train or select models and must be evaluation-eligible.
   Protected evaluation requires exact planned/executed design pins. Final TEST
   release requires release-eligible source membership, preserves distinct
   protected/training snapshot hashes, and records source/design pins. External
   Challenge remains a typed `SCIENTIFIC_REVIEW_REQUIRED` dependency on Task 7.
5. **Schema-owned physical view.** Training snapshot file names are closed by the
   runtime schema; a caller cannot authorize an extra file merely by adding it to
   `files`. The mismatch is rejected before the extra is opened.
6. **Consumer-bound staged verification.** The run-owned train/valid directory is
   exact, read-only, and rehashed immediately before the MLX training consumer.
   Tokenization verifies before model/tokenizer resolution and reads each pinned
   JSONL through the same `O_NOFOLLOW` file descriptor used for hashing, closing
   the post-validation replacement path.
7. **Fail-closed v7 EXTERNAL migration.** Historical lowercase models and named
   migrations are publicly exported. Internal splits migrate one way; generic v7
   `external` returns typed `LineageMigrationReviewRequired` with status
   `SCIENTIFIC_REVIEW_REQUIRED` and no target, so it is never promoted to the v8
   External Challenge contract.
8. **Canonical resume pins.** Resume accepts only the four canonical
   `reality_gate_*` state fields. Bare aliases, alias/canonical collisions,
   missing canonical pins, and value drift are rejected.
9. **Bounded P2 test repair.** The previous whitespace/string assertion was
   replaced with recursive key traversal against the complete forbidden-final
   field registry.

## Compatibility and migration

- The unqualified hard verifier is now v8-only; v7 tests and callers use
  `hard_verify_candidates_v7` explicitly.
- Historical `external` is intentionally incompatible with automatic migration;
  it produces a typed review-required result.
- TEST evaluation no longer accepts a training-snapshot alias. It requires a
  distinct protected snapshot, an independently resolved source manifest, exact
  membership, planned/executed pins, and explicit evaluation/release eligibility.
- Resume states carrying bare Reality Gate aliases are rejected; only canonical
  prefixed fields are accepted.
- These are deliberate v8 scientific-contract migrations, not silent aliases.

## Validation

Final Task 5 compatibility command (new regression plus all Task 5/v3/v7/MLX
compatibility files):

```text
uv run pytest -q -x <14 Task-5 compatibility files>
163 passed
```

Static gates:

```text
ruff check: All checks passed!
ruff format --check: 252 files already formatted
mypy packages/ntruth: Success: no issues found in 175 source files
git diff --check: clean
```

## Self-review and explicit blockers

- No Task 6 planned/executed semantics were invented. Task 5 only requires and
  reconciles opaque artifact IDs and SHA-256 pins. Missing authoritative design or
  independently resolved source artifacts raises typed
  `ProtectedEvaluationReviewRequired` with `SCIENTIFIC_REVIEW_REQUIRED`.
- No v7 candidate bundle can enter the unqualified v8 verifier. The compatibility
  function and imports are explicitly suffixed `_v7`.
- The staged MLX view is rehashed directly before `_stream_command`; tokenization
  additionally hashes and consumes the same opened bytes.
- Task 5 still cannot issue an accepted Reality Gate v8 decision. Training remains
  HOLD pending Task 7 authority.
- External Challenge evaluation/release remains HOLD pending Task 7
  `ContaminationAttestation` and custody authority.
- This round did not define Task 6 design content, Task 7 authority, contamination
  semantics, or external data membership; it fails closed where those are absent.

## Files

Production modified:

- `packages/ntruth/governance/__init__.py`
- `packages/ntruth/governance/lineage.py`
- `packages/ntruth/mvt_a/__init__.py`
- `packages/ntruth/mvt_a/stage_schema.py`
- `packages/ntruth/mvt_a/verifier.py`
- `packages/ntruth/parser_ai/adapter.py`
- `packages/ntruth/parser_ai/contract.py`
- `packages/ntruth/training/mlx_inference.py`
- `packages/ntruth/training/mlx_runtime.py`
- `packages/ntruth/training/protected_evaluation.py`
- `packages/ntruth/training/records.py`

Tests created/modified:

- `tests/unit/test_prd_v8_task5_fix2_regressions.py` (new)
- `tests/unit/test_mlx_evaluation_lineage.py`
- `tests/unit/test_prd_v7_mvt_a_contracts.py`
- `tests/unit/test_prd_v8_parser_candidate_contract.py`
- `tests/unit/test_prd_v8_task5_protected_runtime.py`
