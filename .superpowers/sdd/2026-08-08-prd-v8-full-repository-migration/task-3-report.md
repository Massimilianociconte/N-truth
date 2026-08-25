# Task 3 report — Derivation Theory, Rulebook and conformance assets

## Status

`IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`

Task 3 adds an isolated PRD v8 Derivation Theory contract, a separate Rulebook
conformance mapping, versioned reference-role registry, deterministic checksum
loader and structural conformance gate. It deliberately does **not** add runtime
derivation; that remains Task 4. The historical 32-rule v7 asset and its engine
were not modified.

- Start SHA: `79bf05784186f10c433fc29adee31e1c36429db2`
- Branch: `codex/prd-v8-full-migration-20260808`
- Worktree: `/Users/massimilianociconte/Documents/N-truth/.worktrees/prd-v8-full-20260808`

## TDD RED evidence

Before production modules/assets existed:

```text
.venv/bin/python -m pytest tests/unit/test_prd_v8_derivation_theory_conformance.py
11 failed
```

All eleven failures were the intended `Task 3 API is missing` assertion; there
were no collection errors. The tests covered the brief's six mandatory RED
cases plus fixture-kind, proof-trace and checksum/pin regressions.

## Artifacts and immutable pins

| Artifact | ID/version | SHA-256 semantic pin |
|---|---|---|
| Derivation Theory | `ntruth-derivation-theory@0.1.0` | `3980e9583ac323c3c88570a09dc75e0ce60d9b63daf8be77bf074c7a74f76367` |
| v8 Rulebook | `ntruth-v8-core@0.1.0` | `7971c50868f36258fde9c283bf2eda7f64782a759c2c7a4882a57a933664c3c3` |
| Reference-role registry | `ntruth-reference-role-registry@0.1.0` | `4dcf9cc55ba272c715bac62df10ecff250bb4d02a3cc0a8716998bdc373136be` |
| Implementation fixture set | `implementation-conformance-fixtures-simple-cell-culture@0.1.0` | `be1c46734b1c7f952c98a756be7737ee3998de83b6e4d34bf852f997e3be2e7f` |
| Profile pin | `simple_cell_culture@0.1.0` | version pin in theory and Rulebook |

The Rulebook pins theory, profile, reference registry and fixture-set versions
and checksums. Loaders recompute canonical JSON hashes and fail closed on any
content drift.

## Conformance result

Fresh canonical evaluation:

```text
passed=True
clauses=7 rules=7 fixtures=21
covered=DT-A-ASSIGNMENT-UNIT,DT-B-EXPERIMENTAL-UNIT,
        DT-C-EXPERIMENTAL-UNIT-COUNT,DT-D-BIOLOGICAL-SOURCE-COUNT,
        DT-E-INTERFERENCE-ESTIMAND,DT-F-ANALYTICAL-DEPENDENCE,
        DT-G-INFERENCE-SCOPE
```

The gate verifies:

- every v8 rule maps to a versioned theory clause and cannot add an output;
- theory/rule predicate sets and version/checksum pins agree;
- positive, negative and minimal-counterfactual fixtures exist;
- minimal counterfactuals change only the decisive predicate and change the
  expected claim signature;
- expected proof traces join the mapped clause/rule and cover required
  predicates;
- open known gaps have fail-closed handling;
- one asset identity/checksum cannot be reused across Theory Reference Set,
  Implementation Conformance Fixtures and Derivation Gold.

Reference roles remain deliberately distinct: synthetic conformance fixtures
are available; reviewed Theory Reference Set and real Derivation Gold remain
blocked and are not promoted from engineering fixtures.

## Scientific review blockers retained

The canonical conformance structure passes, but release remains blocked by:

- `SRR-V8-012`: partial graph-scoring weights/tolerances unavailable;
- `SRR-V8-014`: report aggregation precedence unavailable;
- `SRR-V8-017`: unknown interference topology cannot choose EU/exposure unit;
- `SRR-V8-021`: reviewed references, DRIVER snapshot, real cases and
  Derivation Gold absent;
- `SRR-V8-023`: positive payload contracts for non-determinate states under
  review;
- `SRR-V8-024`: RuleChallenge outcome/change semantics under review.

The E mapping binds `SRR-V8-017` to
`BLOCK_AND_EMIT_SCIENTIFIC_REVIEW_REQUIRED`; no interference topology,
aggregation precedence, support conversion or graph scoring policy was
invented.

## Files added

- `packages/ntruth/derivation_theory/__init__.py`
- `packages/ntruth/derivation_theory/contracts.py`
- `packages/ntruth/derivation_theory/loader.py`
- `packages/ntruth/conformance/__init__.py`
- `packages/ntruth/conformance/harness.py`
- `packages/ntruth/conformance/assets/reference-role-registry-0.1.0.json`
- `theories/ntruth-derivation-theory-0.1.0.json`
- `rulesets/ntruth-v8-core-0.1.0.json`
- `tests/unit/test_prd_v8_derivation_theory_conformance.py`
- `.superpowers/sdd/2026-08-08-prd-v8-full-repository-migration/task-3-report.md`

## Fresh validation

```text
.venv/bin/python -m pytest \
  tests/unit/test_prd_v8_derivation_theory_conformance.py \
  tests/unit/test_rules_contract.py \
  tests/unit/test_scientific_references.py -q
225 passed

.venv/bin/ruff check packages/ntruth/derivation_theory \
  packages/ntruth/conformance \
  tests/unit/test_prd_v8_derivation_theory_conformance.py
All checks passed!

.venv/bin/ruff format --check packages/ntruth/derivation_theory \
  packages/ntruth/conformance \
  tests/unit/test_prd_v8_derivation_theory_conformance.py
6 files already formatted

.venv/bin/mypy packages/ntruth/derivation_theory packages/ntruth/conformance
Success: no issues found in 5 source files

git diff --check
clean
```

## Self-review and integration concern

- Scope is limited to contracts, assets and conformance; no parser, pipeline,
  report, UI, training, external data or runtime derivation code was added.
- No legacy Rulebook asset or audited historical artifact was edited.
- The current distribution configuration force-includes top-level `rulesets/`
  but not top-level `theories/`. Adding the theory asset to built wheels needs a
  later packaging integration change outside this task's ownership before a
  wheel can claim the same repository-root conformance truth.

## Commit

This report is committed atomically with the Task 3 implementation; the final
commit SHA is returned in the handoff message because it cannot self-contain
its own Git object ID.
