# Clean-checkout verification report — 2026-08-27 10:15 UTC

- **Head verified:** `cd17cb209eb80ed169df11b8d8f6a322663dc2b1` (ephemeral detached worktree; working-tree files excluded by construction)
- **Branch label at run time:** integration/prd-v9-unified
- **Toolchain:** uv 0.11.6 (65950801c 2026-04-09 aarch64-apple-darwin), Python 3.12.13
- **Pytest selection:** tests/unit -m "not performance" -x (full unit tree)
- **Verifier:** `scripts/verify_clean_checkout.sh` (PRD v9 §26.10 / NFR-06)
- **Wall-clock:** ~27 min (11:48–12:15 CEST), coerente con i budget CI (`timeout-minutes: 20/30`)

| Check | Result | Detail |
|---|---|---|
| `worktree_add` | PASS | detached HEAD cd17cb209eb80ed169df11b8d8f6a322663dc2b1 at /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T//ntruth-clean-checkout.S4OSLj/worktree |
| `uv_sync` | PASS | variant: --frozen --extra dev --extra api |
| `lock_up_to_date` | PASS | log: /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T//ntruth-clean-checkout.S4OSLj/logs/lock_up_to_date.log |
| `pytest_unit` | PASS | log: /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T//ntruth-clean-checkout.S4OSLj/logs/pytest_unit.log |
| `ruff_check_packages` | PASS | log: /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T//ntruth-clean-checkout.S4OSLj/logs/ruff_check_packages.log |
| `mypy_packages` | PASS | log: /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T//ntruth-clean-checkout.S4OSLj/logs/mypy_packages.log |
| `sbom_reproducible` | PASS | log: /var/folders/rb/gltk48212j39qn2wskhlj3s80000gn/T//ntruth-clean-checkout.S4OSLj/logs/sbom_reproducible.log |

**Overall:** PASS

All enabled engineering checks passed from a virgin checkout of the verified commit.
This is a portability/reproducibility gate (PRD v9 §26.10, NFR-06); it is not scientific
validation. Nessun risultato qui costituisce validazione scientifica:
`scientific_validation_status: NOT_STARTED`, `training_execution_gate: HOLD_PENDING_REAL_ANCHOR`.

Nota sui path: al termine con esito PASS il verifier rimuove la directory di run; i
path dei log sopra sono quelli emessi durante l'esecuzione (stdout del verifier),
non artefatti conservati.

## Interpreter resolution evidence (blocker del 2026-08-25 chiuso)

Il blocker del [report clean-checkout 2026-08-25](clean-checkout-report-2026-08-25.md) era la
portabilità interprete: in ambienti freschi `uv` risolveva Python 3.14 e i pin dell'evaluator,
derivati dal bytecode, non potevano combaciare. Il fix è presente nel tree dalla commit
`c464cb7` ("chore: pin interpreter <3.14 for evaluator bytecode pins, regenerate SBOM,
preserve Task9 record"):

- `pyproject.toml`: `requires-python = ">=3.12,<3.14"`;
- `.python-version`: `3.12`.

Evidenza sperimentale raccolta il 2026-08-27, stesso commit verificato:

1. Nel worktree effimero creato dal verifier, `uv sync --frozen --extra dev --extra api`
   è riuscito senza override manuali di interprete: nessun intervento esterno quindi
   ha potuto forzare la versione risolta.
2. Sonda indipendente dedicata (worktree detach della stessa commit in directory
   temporanea, stesso lock): `uv run python -V` → `Python 3.12.13`, eseguibile
   `<worktree>/.venv/bin/python3`; `uv lock --check` → OK (99 packages resolved).
   L'ambiente vergine risolve quindi Python 3.12.13, non 3.14.
3. Conferma comportamentale: sotto un interprete 3.14 la suite
   `tests/unit/test_prd_v8_derivation_runtime.py` fallisce in modo deterministico con
   `V8EvaluatorReviewRequired` (diagnosi nel report 2026-08-25). Il PASS di `pytest_unit`
   sull'intero albero unitario esclude per costruzione la risoluzione di 3.14.

## Disposition

- Engineering gate (2026-08-27): HEAD `cd17cb2` è portable da checkout vergine entro la
  gamma dichiarata `>=3.12,<3.14`; l'intera selezione unit (`-m "not performance"`), lint,
  type check, lock e SBOM passano dall'ambiente effimero. Il blocker interprete del
  2026-08-25 è chiuso da verifica datata, non prescritto.
- Restano immutati gli altri confini onesti: nessuna evidenza reale esterna, gold data
  assenti, training HOLD, External Challenge senza custodia reale. I residual gaps elencati
  in `docs/status-snapshot.md` restano validi salvo il punto sulla portabilità interprete,
  chiuso da questo report.
- Il gate scientifico è immutato: nessun risultato qui costituisce validazione scientifica.

## Verdict

```text
CLEAN_CHECKOUT_ENGINEERING_TRUTH: PASS
INTERPRETER_CAP: requires-python = ">=3.12,<3.14", .python-version = 3.12 (fix c464cb7)
PRIOR_BLOCKER_2026_08_25: interpreter-version-bound evaluator pins — CLOSED by dated re-run
PUSH_TO_REMOTE: unchanged policy — conditional; green checks are not scientific validation
NEXT_ACTION: none for this gate; keep periodic re-runs of scripts/verify_clean_checkout.sh before pushes
```
