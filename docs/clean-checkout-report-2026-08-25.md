# Clean-checkout verification report — 2026-08-25 22:29 UTC

- **Head verified:** `cb270e3af85057197e44803a6f6fd4dd57182fb8` (ephemeral detached worktree; working-tree files excluded by construction)
- **Branch label at run time:** integration/prd-v9-unified
- **Toolchain:** uv 0.11.6 (65950801c 2026-04-09 aarch64-apple-darwin), Python 3.12.13
- **Pytest selection:** tests/unit -m "not performance" -x (full unit tree)
- **Verifier:** `scripts/verify_clean_checkout.sh` (PRD v9 §26.10 / NFR-06)

| Check | Result | Detail |
|---|---|---|
| `worktree_add` | PASS | detached HEAD cb270e3af85057197e44803a6f6fd4dd57182fb8 at /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T//ntruth-clean-checkout.iqgvpR/worktree |
| `uv_sync` | PASS | variant: --frozen --extra dev --extra api |
| `lock_up_to_date` | PASS | log: /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T/ntruth-clean-checkout.iqgvpR/logs/lock_up_to_date.log |
| `pytest_unit` | FAIL | exit=1, stopped by `-x` at ~19% of the collection; see diagnosis below |
| `ruff_check_packages` | PASS | log: /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T/ntruth-clean-checkout.iqgvpR/logs/ruff_check_packages.log |
| `mypy_packages` | PASS | log: /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T/ntruth-clean-checkout.iqgvpR/logs/mypy_packages.log |
| `sbom_reproducible` | PASS | `generate_sbom.py --check sbom.cdx.json`; SBOM rigenerabile dal lockfile |

**Overall:** FAIL

Residual blockers above are real failures observed on this run; they are not waived or
reinterpreted.

## Failure diagnosis (root-caused, reproducible)

`pytest_unit` failed on the first pipeline test reached:

```text
FAILED tests/unit/test_prd_v8_derivation_runtime.py::
       test_source_independence_never_promotes_assignment_eu_or_count
ntruth.derivation_theory.runtime.V8EvaluatorReviewRequired:
SCIENTIFIC_REVIEW_REQUIRED: no engineering-pinned v8 evaluator identity
```

Because of `-x`, roughly the last 80% of the unit selection was not executed; this is a
declared limitation of the official command, not a pass.

Follow-up experiments were run inside the same ephemeral worktree of the same commit,
after the verifier kept its artifacts:

1. Running the whole file `tests/unit/test_prd_v8_derivation_runtime.py` in the virgin
   worktree produced 10 failures with the identical `V8EvaluatorReviewRequired` error.
   Not test pollution: the error is raised deterministically by
   `require_reviewed_evaluator_bundle`.
2. The dependency-closure checksum computed by
   `ntruth.derivation_theory.runtime._derivation_dependency_checksum()` differs between
   the developer venv and the fresh worktree venv even though every locked dependency
   version is identical (pydantic 2.13.4, networkx 3.6.1). Every callable semantic
   checksum differs, including stdlib `json.dumps`.
3. Root cause: the closure checksum hashes CPython bytecode (`co_code`,
   `co_exceptiontable`, code flags/stacksize) via `_reviewed_code_payload`. The project
   declares only `requires-python = ">=3.12"`, so `uv sync` in a fresh environment
   resolved **Python 3.14.6**, while the developer venv runs **Python 3.12.13**.
   Bytecode differs across interpreter versions → the engineering-pinned evaluator
   identity can never match under 3.14.
4. Confirmation: pinning the ephemeral worktree to Python 3.12 (`uv python pin 3.12`),
   re-syncing and rerunning the same file gives **16/16 passed** on the very same
   commit.

## Disposition

- Engineering BLOCKER residuo (2026-08-25): HEAD non è portable sull'intera gamma di
  interpreti ammessi da `requires-python = ">=3.12"`; un checkout vergine su una
  macchina con Python 3.14 disponibile fallisce la suite runtime. La CI passa solo
  perché il runner risolve un interprete più vecchio.
- Fix raccomandato (richiede decisione su codice, fuori dal perimetro doc/script di
  questo report): vincolare l'interprete (`.python-version` con major.minor e/o bound
  superiore in `requires-python`) oppure ridefinire i pin dell'evaluator affinché non
  derivino da bytecode legato alla versione dell'interprete (per esempio normalizzando
  il payload o pinnando per interprete). In entrambi i casi serve transizione
  registrata del pin e nuovo run di questo verificatore.
- Il gate scientifico è immutato: nessun risultato qui costituisce validazione
  scientifica. `scientific_validation_status: NOT_STARTED`,
  `training_execution_gate: HOLD_PENDING_REAL_ANCHOR`.

## Verdict

```text
CLEAN_CHECKOUT_ENGINEERING_TRUTH: CONDITIONAL_FAIL
BLOCKER_RESIDUO: interpreter-version-bound evaluator pins (Python 3.14 default resolution)
PUSH_TO_REMOTE: unchanged policy — conditional, blocker must be recorded
NEXT_ACTION: fix interprete/pin + re-run scripts/verify_clean_checkout.sh fino a PASS
```
