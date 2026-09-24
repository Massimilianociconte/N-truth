# Task 5 fix round 1 report

## Status

**COMPLETE — scoped Task 5 review findings 1-13 addressed.**

- Base SHA: `91aeb2722c5d7361cde0bd5e76cbe18384045dc1`
- Task commit: this report is part of the single Task 5 fix-round-1 commit; the
  resulting SHA is reported to the parent after commit creation.
- Worktree: `/Users/massimilianociconte/Documents/N-truth/.worktrees/prd-v8-full-20260808`
- No training, model operation, network access, dataset access, or Task 6 change
  was performed.

## RED evidence

Production was unchanged when the two review regression files were first run.

```text
uv run pytest -q \
  tests/unit/test_prd_v8_task5_review_regressions.py \
  tests/unit/test_prd_v8_task5_protected_runtime.py

28 failed in 0.31s
```

The 28 failing cases covered every numbered P0/P1 item 1-11 and P2 items
12-13: self-issued File gate, parser-to-stage integration, six typed/block
reference cases, verifier status, Gold governance pins, four count-kind bypasses,
real custodial evaluation, physical extras/symlink/FIFO/stale staging,
tokenization order, External Challenge blocker, typed v7 lineage, zero payload
opens before denied gate, and four resume-pin mutations.

## Implementation

1. The Task 5 gate artifact is explicitly `UNTRUSTED_TASK5_PROPOSAL`.
   `FileRealityGateV8Protocol` can deserialize it for compatibility, but the
   production verifier always raises `SCIENTIFIC_REVIEW_REQUIRED` after normal
   shape/stale/hash/blocked diagnostics. Task 5 cannot mint an accepted grant.
2. `run_training` reads only the content-addressed manifest envelope before the
   gate. Because Task 7 authority is unavailable, production remains HOLD and
   opens zero train/valid payloads.
3. Training snapshots now require an exact physical allowlist and reject every
   extra entry, symlink, directory, FIFO, or other special file. A run-owned
   immutable view stages exactly verified `train.jsonl` and `valid.jsonl` and
   rechecks source/staged hashes against post-validation replacement.
4. Tokenization validates the complete snapshot before model resolution,
   consumes only a temporary verified train/valid view, and records snapshot,
   manifest, and content pins in its report.
5. TEST/EXTERNAL_CHALLENGE use a distinct content-addressed custodial evaluation
   manifest with split, purpose, count, payload hash, planned/executed design,
   source, custody, and lineage pins. A training validator cannot accept it.
6. External Challenge records and manifests persist family/custody/attestation
   dependency references. Task 5 admits only review-required membership and
   keeps evaluation/release blocked; actual External Challenge validation raises
   until Task 7 supplies authoritative ContaminationAttestation/custody review.
7. The public v8 parser adapter now returns one versioned `MvtAStageOutput`
   containing the lossless `ParserCandidateOutput`, typed diagnostics, coverage,
   provenance, preserved artifacts, and hard-verifier result.
8. Contrast, estimand, event, graph, alternative, and clarification references
   are type-checked and Experiment-Block-scoped. A failed verifier cannot remain
   `COMPLETE`; it transitions to `FAILED` while preserving candidate artifacts
   and provenance.
9. Active v8 count kinds use a closed reviewed candidate vocabulary. Gold,
   supervised/prepared records, manifest pins, chat/runtime validation, and the
   active stage all revalidate the canonical candidate target. The historical
   v7 `ParserCandidateBundle` vocabulary remains input-only and unchanged.
10. `GoldParserTarget` requires exactly two immutable submission references,
    explicit comparison status/material-difference ledger, adjudication, and
    reviewer identities/roles. Record provenance must match exactly; manifest
    records persist all corresponding pins.
11. Typed `CorpusSplitV7`, `CorpusAssetV7`, `CorpusSnapshotManifestV7`, and
    `ModelRunLineageV7` preserve historical lowercase artifacts. Named one-way
    migrations produce uppercase v8 targets plus explicit legacy diagnostics;
    direct v8 deserialization still rejects lowercase values.
12. A canonical `RealityGatePinTuple` reconciles artifact ID/hash and both
    attestation hashes on resume.
13. Split propagation into External Challenge now fails closed when any member
    lacks family identity or the unresolved Task 7 dependency pins.

## Migration and deprecation notes

- `build_training_reality_gate_v8_artifact` remains only as an explicitly
  untrusted compatibility/negative-test proposal builder. It is never accepted
  by production.
- `ParserCandidateBundle`, its historical count vocabulary, v7 envelope, and v7
  hard-verifier dispatch remain deprecated input-only compatibility surfaces.
  The public active parser cannot return them.
- Historical lowercase lineage is accepted only by typed `*V7` models and named
  migration functions; there is no implicit v8 alias.
- Existing v8 fixtures were migrated to carry the required two-submission,
  adjudication, reviewer, family, and Task 7 dependency pins. Assertions were
  preserved or strengthened; incompatible External Challenge auto-propagation
  now expects a fail-closed custody diagnostic.

## Files

Created:

- `packages/ntruth/training/custody.py`
- `packages/ntruth/training/protected_evaluation.py`
- `tests/unit/test_prd_v8_task5_review_regressions.py`
- `tests/unit/test_prd_v8_task5_protected_runtime.py`
- this report

Modified:

- `packages/ntruth/governance/lineage.py`
- `packages/ntruth/mvt_a/stage_schema.py`
- `packages/ntruth/mvt_a/verifier.py`
- `packages/ntruth/parser_ai/adapter.py`
- `packages/ntruth/parser_ai/contract.py`
- `packages/ntruth/training/manifest.py`
- `packages/ntruth/training/mlx_inference.py`
- `packages/ntruth/training/mlx_runtime.py`
- `packages/ntruth/training/records.py`
- `packages/ntruth/training/splits.py`
- focused Task 5 fixture/regression files listed by `git show --stat`.

## GREEN validation

Focused review files after implementation:

```text
28 passed
```

Final combined review + Task 5 compatibility gate:

```text
uv run pytest -q \
  tests/unit/test_prd_v8_task5_review_regressions.py \
  tests/unit/test_prd_v8_task5_protected_runtime.py \
  tests/unit/test_prd_v8_parser_candidate_contract.py \
  tests/unit/test_prd_v8_task5_boundary.py \
  tests/unit/test_prd_v8_training_reality_gate_boundary.py \
  tests/unit/test_prd_v8_training_records_splits.py \
  tests/unit/test_prd_v3_parser_ai_contract.py \
  tests/unit/test_prd_v7_mvt_a_contracts.py \
  tests/unit/test_training_dataset_preparation.py \
  tests/unit/test_training_dedup_split_integrity.py \
  tests/unit/test_mlx_training_pipeline.py \
  tests/unit/test_mlx_snapshot_integrity.py \
  tests/unit/test_mlx_evaluation_lineage.py

137 passed
```

Static gates:

```text
ruff check: All checks passed!
ruff format --check: 185 files already formatted
mypy packages/ntruth: Success: no issues found in 175 source files
git diff --check: clean
```

No full repository suite was run in this scoped fix round, per instruction.

## Self-review and explicit blockers

- File gate production behavior is unconditionally fail-closed after validating
  local diagnostic fields; no caller-controlled issuer or hash can authorize.
- The protected evaluation schema cannot satisfy the training snapshot filename,
  schema, file-set, or split contract.
- Tokenization operates on staged verified bytes and emits content-addressed
  dataset pins.
- The active parser stage dynamically revalidates `ParserCandidateOutput`; the
  deprecated v7 bundle is reachable only through explicitly v7 surfaces.
- `run_training` and External Challenge evaluation intentionally remain blocked
  on Task 7. No issuer, signature, attestation semantics, or scientific custody
  decision was invented in Task 5.
