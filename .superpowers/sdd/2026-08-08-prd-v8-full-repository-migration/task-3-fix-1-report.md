# Task 3 fix round 1 report

## Status

`IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`

- Fix base: `50d9a8cc77151ec3d08cb40d7da87a3fba0d93d7`
- Branch: `codex/prd-v8-full-migration-20260808`
- Worktree: `/Users/massimilianociconte/Documents/N-truth/.worktrees/prd-v8-full-20260808`
- Scope: review findings 1–5 only; Minor finding 6 intentionally unchanged.

## RED evidence

Tests were added before production fixes.

```text
.venv/bin/python -m pytest \
  tests/unit/test_prd_v8_derivation_theory_conformance.py \
  tests/unit/test_release_artifacts.py -q
18 failed
```

The failures reproduced output false closure, rationale-only predicate drift,
negative/incomplete/duplicate fixture acceptance, absent profile/fixture pins,
registry join gaps and a wheel accepted without the v8 bundle.

```text
.venv/bin/python -m pytest \
  tests/integration/test_prd_v8_packaged_conformance.py -q
1 failed
ImportError: cannot import name 'load_installed_bundle'
```

## Findings addressed

1. **Bidirectional output closure**
   - Every fixture claim must belong to both Rulebook rule and Theory clause.
   - Rule outputs must be covered by fixtures.
   - The union of mapped-rule outputs must equal each clause output set.
   - New failures: `UNCOVERED_DERIVED_OUTPUT` and
     `UNIMPLEMENTED_THEORY_OUTPUT`.

2. **Theory-owned required-predicate semantics**
   - Conformance compares the complete canonical predicate requirement
     (`schema_version`, ID and rationale) under the pinned clause version.
   - All Rulebook copies now exactly match the Theory; rationale-only mutation
     produces `PREDICATE_CONTRACT_MISMATCH`.

3. **Complete v0.x fixture validation**
   - Exactly one positive, negative and minimal-counterfactual fixture is
     required per rule.
   - Every fixture must contain every required input and use a required
     decisive predicate.
   - Kind/outcome/claim shape is checked for every fixture.
   - Negative fixtures must differ on their decisive predicate; minimal pairs
     must change exactly that one predicate and change the expected claim.
   - All fixtures receive proof and output-closure checks; no first-only path
     remains.

4. **End-to-end content-addressed pins**
   - Added versioned profile predicate-closure candidate asset, explicitly
     blocked by `SRR-V8-008`; it is not represented as scientifically reviewed.
   - Added versioned fixture-set manifest with one canonical content pin per
     embedded Rulebook fixture.
   - Theory and Rulebook pin profile closure identity/version/checksum.
   - Theory and Rulebook join the reference registry identity/version.
   - Rulebook, registry and fixture manifest join fixture-set
     identity/version/checksum and canonical fixture bytes.
   - Mutation tests cover profile/fixture bytes and identity, version and
     checksum drift.

5. **Installable bundle**
   - `theories/` is force-included in wheel and sdist; package-local registry
     and fixture manifest remain package resources; v8 Rulebook remains in the
     bundled rulesets.
   - `load_canonical_bundle()` remains checkout-only.
   - `load_installed_bundle()` resolves only package resources and never falls
     back to checkout paths; every JSON asset is checksum-verified before model
     validation.
   - Distribution checks require Theory, profile closure, Rulebook, registry
     and fixture manifest in wheel and sdist.
   - Release smoke evaluates installed v8 conformance for both artifact types.

No runtime derivation, parser, pipeline, UI, training or scientific mapping was
introduced. The historical v7 Rulebook and engine remain unchanged.

## Immutable pins after the fix

| Asset | ID/version | SHA-256 |
|---|---|---|
| Theory | `ntruth-derivation-theory@0.1.0` | `aa37639893e2ba7732496f2eb6a121291e0aad2d3bae51501c8f1ea9e9b6464f` |
| Profile closure candidate | `simple-cell-culture-profile-predicate-closure@0.1.0` | `1080f48e37b719351554c406d85e8cce7c2106f9f01ee5b8168413f57a747698` |
| Rulebook | `ntruth-v8-core@0.1.0` | `3eb8de408a8874c099d8a514a9d74ea0534f1ee96f5a71cb5bd3c6896168eca3` |
| Reference registry | `ntruth-reference-role-registry@0.1.0` | `7e573af256a1365ca0e3892786f80a6a8f62710ce0e4dc39d1dfef24d2089db3` |
| Fixture set | `implementation-conformance-fixtures-simple-cell-culture@0.1.0` | `f7a9b4c0a009fcbf1ae4c7a2bb3b15d8392225cb6e040ec17e2187cb396918e6` |

Fresh canonical evaluation: `passed=True`, `failures=0`, seven clauses,
seven rules and 21 fixture pins.

## Validation

Focused + legacy + packaging tests:

```text
.venv/bin/python -m pytest \
  tests/unit/test_prd_v8_derivation_theory_conformance.py \
  tests/unit/test_release_artifacts.py \
  tests/integration/test_prd_v8_packaged_conformance.py \
  tests/unit/test_rules_contract.py \
  tests/unit/test_scientific_references.py -q
262 passed
```

Static checks:

```text
ruff check: All checks passed!
ruff format --check: 10 files already formatted
mypy: Success: no issues found in 5 source files
git diff --check: clean
```

Build and distribution gate:

```text
uv build --out-dir /tmp/ntruth-task3-fix1-dist.TNkRwx
Successfully built ntruth-0.1.0.tar.gz
Successfully built ntruth-0.1.0-py3-none-any.whl

scripts/check_distribution.py
Distribuzione verificata: ntruth-0.1.0-py3-none-any.whl, ntruth-0.1.0.tar.gz
```

Installed offline smoke:

```text
wheel: ... v8 conformance ok · ntruth-v8-core@0.1.0
sdist: ... v8 conformance ok · ntruth-v8-core@0.1.0
Release smoke test completato: wheel e sdist verificati offline.
```

## Explicit scientific blockers retained

- `SRR-V8-008`: profile coverage/closure contract not scientifically reviewed;
- `SRR-V8-012`: partial graph-scoring policy unavailable;
- `SRR-V8-014`: report aggregation precedence unavailable;
- `SRR-V8-017`: unknown interference topology cannot choose EU/exposure unit;
- `SRR-V8-021`: reviewed references, DRIVER snapshot, real cases and
  Derivation Gold absent;
- `SRR-V8-023`: positive payload contracts for non-determinate states under
  review;
- `SRR-V8-024`: RuleChallenge outcome/change semantics under review.

The structural conformance gate passing does not clear these release/scientific
review blockers.

## Commit

This report is committed atomically with the fix; the resulting SHA is returned
in the handoff because a commit cannot contain its own object ID.
