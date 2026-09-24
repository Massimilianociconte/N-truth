# Task 3 fix round 2 report

## Status

`ADDRESSED`

- Base: `636dc0c2a1595c11fb080172667e54921b25f9f7`
- Branch: `codex/prd-v8-full-migration-20260808`
- Scope: residual finding 3 only.
- Untouched: assets, checksums/pins, packaging, loader and runtime derivation.

## TDD RED

Two focused regressions were added before the production change:

```text
.venv/bin/python -m pytest \
  tests/unit/test_prd_v8_derivation_theory_conformance.py::test_provenance_only_change_is_not_a_scientific_counterfactual \
  tests/unit/test_prd_v8_derivation_theory_conformance.py::test_fixture_rejects_predicate_input_outside_required_or_irrelevant_contract -q
FF
```

- A minimal counterfactual made scientifically identical to its positive but
  changed only in evidence/source/rationale metadata lacked
  `NON_DISCRIMINATING_FIXTURE`.
- An undeclared fixture predicate input lacked
  `FIXTURE_PREDICATE_CONTRACT_MISMATCH`.

## Fix

### Provenance-free scientific predicate signature

Predicate discrimination now compares only:

- `KnowledgeState`;
- canonical normalized scientific `value`;
- order-normalized canonical `conflicting_values`.

Evidence IDs, source-scope IDs, rationale and other provenance metadata do not
participate. Query scope is already represented by the explicit
`inferential_query` scientific predicate in these fixtures, so no metadata scope
identifier is required in this signature.

Negative fixtures must differ from the positive on at least one scientific
predicate. Minimal counterfactuals retain the stronger rule: exactly one
scientific change, on the declared decisive predicate, plus a changed expected
claim signature.

### Closed fixture predicate inputs

For every fixture:

```text
predicate_values.keys() <= required_predicates ∪ irrelevant_predicates
```

Required completeness and decisive-required checks remain in force. Unexpected
inputs produce `FIXTURE_PREDICATE_CONTRACT_MISMATCH` with explicit missing and
unexpected predicate lists.

## Canonical fixture compatibility

Four canonical negative fixtures differ scientifically from their positive on
another declared required predicate rather than on the fixture's
`decisive_predicate_id`. Because negative fixtures require discrimination but
are not minimal pairs, the gate accepts those real scientific differences.
Only minimal counterfactuals enforce the exact one-decisive-change contract.
No fixture asset or pin was rewritten.

## GREEN validation

```text
.venv/bin/python -m pytest \
  tests/unit/test_prd_v8_derivation_theory_conformance.py -q
37 passed

.venv/bin/ruff check \
  packages/ntruth/conformance/harness.py \
  tests/unit/test_prd_v8_derivation_theory_conformance.py
All checks passed!

.venv/bin/ruff format --check \
  packages/ntruth/conformance/harness.py \
  tests/unit/test_prd_v8_derivation_theory_conformance.py
2 files already formatted

.venv/bin/mypy packages/ntruth/derivation_theory packages/ntruth/conformance
Success: no issues found in 5 source files

git diff --check
clean
```

## Files changed

- `packages/ntruth/conformance/harness.py`
- `tests/unit/test_prd_v8_derivation_theory_conformance.py`
- `.superpowers/sdd/2026-08-08-prd-v8-full-repository-migration/task-3-fix-2-report.md`

## Commit

The report is committed atomically with the fix; the resulting SHA is returned
in the handoff because a commit cannot contain its own object ID.
