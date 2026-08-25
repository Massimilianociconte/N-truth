# PRD v7.0 Implementation Gap Report — Clean Checkout

**Report ID:** GAP-PRDV7-ROOT-001 · **Date:** 2026-08-03 · Base `origin/main` @ `0dcef3e`.
Derived from [REQUIREMENT_TRACEABILITY_MATRIX.md](REQUIREMENT_TRACEABILITY_MATRIX.md).

## 1. Confirmed clean-checkout baseline

- Full unit/integration suite: **green** at base SHA (verified locally before changes).
- Import boundary `graph/rules ⊬ parser_ai`: **holds** (0 hits).
- Deterministic core has no ML/network dependency; ML extra is Darwin/arm64-only.
- `models/registry/` and `models/ntruth-granite-3b/` referenced by v6.1 docs are **not**
  part of the clean checkout.

## 2. Critical gaps (block v7 contracts)

| Gap | Severity | Notes |
|-----|----------|-------|
| Reality Gate absent from code | Critical | v6.1 gate values existed only in uncommitted registry JSON; no fail-closed predicate model in the repo. |
| DeterminabilityState incomplete | Critical | 4 of 8 v7 states; CONDITIONALLY_DETERMINATE / INSUFFICIENT_INFORMATION / INVALID_GRAPH / OUT_OF_SCOPE missing from the enum even though docs claim seven states. |
| Authority/conflict model absent | Critical | No AuthorityType, ConfirmationEvent, or append-only ConflictRecord; only `Contradiction` with coarse statuses. |
| Quick Design Session absent | High | No domain service, CLI, fixtures or export for `simple_cell_culture`. |
| MVT-A harness absent | High | Parser contract v2 exists (candidate-only) but HumanRevisionPatch, burden recording, false-certainty recording, decisive correction count and benchmark manifest do not. |
| Cross-domain role policy absent | High | No profile-relative role object; Lazic dataset role must be decided before label access. |

## 3. Partial implementations to preserve (do not rewrite)

- `NScope`/`NKind`/`NStatement` scope-aware counts (v3 GEN-006) — extend, keep.
- `ConditionalScenario` — upgrade in place to v7 ConditionRecord semantics via a
  v7-specific type; keep the v3 type for existing reports.
- `Determinability` (4-state) — keep as `DeterminabilityStateV3` for migration; v7 enum is
  additive with an explicit alias map.
- `EvidenceType` / `EvidenceSpan` / `Provenance` — keep; v7 support levels layer on top.
- `governance/` (GovernanceRecord, lineage, privacy) — keep; authority/conflict reuse
  `FrozenModel` + `content_checksum` conventions.
- `task_corpora/` authority/license enums — keep; cross-domain policy composes them.

## 4. Documentation drift found (must be corrected, Phase 13)

1. `docs/status-snapshot.md` cites `models/registry/default.json` /
   `training_program.json` which are absent from the clean checkout.
2. README claims "seven determinability states" while `schemas/core.py` defines four.
3. `docs/public-specification-v0.1.md` likewise describes seven states.
4. v6.1-era docs (`data-and-model-development.md`, `mlx-training-pipeline.md`,
   `granite-migration-report.md`) describe Granite/MLX work whose code is not in this
   checkout.

## 5. What this PR deliberately does NOT do

- No dataset download, corpus build, or model weight acquisition.
- No training/fine-tuning and no promotion of any challenger model.
- No change to PR #4 / PR #5 branches.
- No rewrite of historical audit reports or signed documents.
- No claim of scientific validation, NC3Rs/DRIVER endorsement, or gold corpus.
- No hard-coded 2–8 h, IAA 0.60, 70% indeterminacy, or disputed 50% rule constants.

## 6. Residual risks after this PR

- Scientific-review blockers BLK-SCIENTIFIC-001…004 remain open (see ERRATA_REGISTER.md).
- Reality Gate stays BLOCKED on data readiness by design.
- Documentation truth sync is only as good as the clean checkout at merge time; the
  historical dirty worktree remains out of scope and uncommitted.


## 7. Post-implementation update (2026-08-03, branch `feat/prd-v7-root-alignment`)

Implemented on the clean worktree (additive; no historical audit rewrite):

| Gap | Status after PR |
|-----|-----------------|
| Reality Gate | **IMPLEMENTED** (fail-closed; data still BLOCKED) |
| DeterminabilityState v7 | **IMPLEMENTED** (8 states + derive; v3 enum preserved) |
| Authority/conflict | **IMPLEMENTED** (append-only ledger) |
| Quick Design Session | **IMPLEMENTED** vertical slice + CLI |
| MVT-A harness | **IMPLEMENTED** contracts only (no train/download) |
| Cross-domain role policy | **IMPLEMENTED** (fail-closed; no Lazic hard-code) |
| Complexity/burden | **IMPLEMENTED** structures (no hard-coded thresholds) |
| Docs truth sync | **PARTIAL→UPDATED** clean-checkout status + README gates |

Still open: scientific errata BLK-SCIENTIFIC-001…004; BLK-DATA-001 licences; real anchor.
