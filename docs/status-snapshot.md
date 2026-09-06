# N-Truth clean-checkout status — PRD v9 unified baseline

**Date:** 2026-08-25
**Baseline:** branch `integration/prd-v9-unified` (merge unificato v6-hardening + contratti sidecar v8/v9, HEAD `cb270e3`).
**Binding specification (programma corrente):** **N-Truth PRD v9.0**, con cinque Contract Packages (`contracts/`) e registry pin `reviewed-evaluator-registry-0.1.2`.
**Repository implementation status:** **`IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`**.
**Scientific validation:** **`NOT_STARTED`**.
**Training:** **`HOLD_PENDING_REAL_ANCHOR`**.
**External Challenge:** lifecycle implementato, **nessuna custodia reale esistente**.

This is a clean-checkout status document. It does not convert code, synthetic fixtures,
an AI review, a repository scan or green CI into scientific evidence.

## Post-merge engineering truth

- La suite deterministica è verde sulla baseline unificata: unit/integration,
  invariant gate, lint/format, `mypy packages`, contract-package checker,
  normative-examples checker e SBOM check passano in CI e in locale.
- Il clean-checkout verifier (`scripts/verify_clean_checkout.sh`) del 2026-08-25 ha
  confermato sync locked, lock up-to-date, ruff, mypy e SBOM riproducibile da
  worktree vergine; la selezione unit completa con `-m "not performance"` ha invece
  fallito su `test_prd_v8_derivation_runtime.py`: in un ambiente fresco `uv` risolve
  Python 3.14 (il progetto dichiara solo `>=3.12`) e i pin dell'evaluator, derivati
  dal bytecode, non possono combaciare tra interpreti diversi. Conferma sperimentale:
  lo stesso file passa 16/16 sullo stesso commit pinnando Python 3.12. Dettaglio nel
  [report clean-checkout 2026-08-25](clean-checkout-report-2026-08-25.md): è un
  BLOCKER ingegneristico residuo (portabilità interprete), non una nota estetica.
- Registry pin corrente: `theories/reviewed-evaluator-registry-0.1.2.json`
  (transizione 0.1.1 → 0.1.2 per la semantica v9 di ScenarioCompleteness).

## Capability ladder

| Level | Current evidence |
|---|---|
| Designed | PRD v9 (programma), PRD v8 contracts, ADR-0013…0018, schemas/contracts |
| Implemented | Kernel v8 + sidecar v9: ScenarioCompleteness assumption-bounded, FactorRole/ContrastType session, CP manifests, team protocol models, confidence/OOD/MQR, challenge lifecycle, DataUseGrant, C0–C4, safe Methods AN |
| Engineering-tested | Unit/integration/E2E/package tests, invariant gate, desktop build |
| Runtime-verified | Deterministic package/conformance assets only |
| Evaluated on independent real reference | **Not available** |
| Validated on real gold | **Not available — gold data non ancora annotati** |
| Scientifically validated | **`NOT_STARTED`** |
| Production-ready scientific product | **Not claimed** |

## Reality Gate

Il gate canonico resta `packages/ntruth/reality_gate/v8.py` con sei dimensioni di
readiness e decisione corrente **HOLD**: reference stability, end-to-end evaluation,
contamination/custody e data/training authorization restano bloccati per assenza di
evidenza esterna reale. Non esistono flag v9 aggiuntivi implementati: ogni futura
estensione del gate richiede contratto, test e ADR.

```bash
uv run ntruth quick-design reality-gate   # riporta lo HOLD canonico
```

## Residual gaps (onesti, non negoziabili)

1. **Gold data assenti:** nessun Derivation Gold annotato né adjudicato.
   Protocollo di ingresso definito (bozza non approvata) in
   [real-anchor-protocol.md](real-anchor-protocol.md); nessun gate modificato.
2. **Training:** `HOLD_PENDING_REAL_ANCHOR`; nessun run autorizzato o eseguito.
3. **External Challenge:** nessun corpus custodito; lifecycle e policy feedback
   (ADR-0017) sono contratti pronti ma senza round reale.
4. RISOLTO passo meccanico (2026-08-27): il content hash dello snapshot
   driver→ARRIVE ([docs/driver-arrive-crosswalk.md](driver-arrive-crosswalk.md))
   è stato pinnato dal custodian tecnico via `ExternalReferenceFreeze`
   (`data_manifests/driver-arrive-crosswalk-freeze.json`). La chiusura
   scientifica del crosswalk (review, rights closure, mapping claim-grade) resta
   bloccata come SRR-V8-021.
5. RISOLTO (2026-08-27): il fallimento di portabilità interprete da checkout vergine è
   chiuso dal pin dell'interprete (`requires-python = ">=3.12,<3.14"` con
   `.python-version` a `3.12`): il verifier su HEAD `cd17cb2` risolve Python 3.12.13
   nell'ambiente effimero e riporta overall PASS sull'intera selezione unit
   ([report clean-checkout 2026-08-27](clean-checkout-report-2026-08-27.md)).
6. Blockers scientifici registrati in `SCIENTIFIC_REVIEW_REGISTER.md` invariati:
   Theory Reference Set, Real Anchor, reference stability, residual evidence.
7. Lane ausiliaria locale (2026-08-27/28, fuori repository): trainer ausiliario
   v4.1 con checkpoint/resume/eval-only, baseline ingegneristiche misurate
   (entity test 0.8207 con context L384; ensemble intersezione 0.8222 in unità
   ufficiali) e staging dati esterni ratificato (v2.1.0 train-only, leakage
   screen). Dettagli e non-claim in
   [auxiliary-training-lane-status-2026-08-28.md](auxiliary-training-lane-status-2026-08-28.md).
   Campagna **CHIUSA il 2026-08-29** su decisione del proprietario: config di
   produzione ausiliaria = ensemble intersezione entity (test 0.8222) + bio-base
   L384 roles (test 0.7966); esterni v2.1.0 = trasferimento negativo archiviato.
   Non modifica alcun confine di questo documento: validation NOT_STARTED,
   training primario HOLD, Reality Gate HOLD.

## Reproducible truth gates

```bash
uv lock --check
uv run pytest -m "not performance" --disable-warnings
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run python scripts/check_prd_v8_contracts.py
uv run python scripts/check_contract_packages.py
uv run python scripts/check_normative_examples.py
uv run python scripts/check_repository_policy.py
bash scripts/verify_clean_checkout.sh
```

`check_repository_policy.py` reports findings over the tracked tree. A clean result is
`NO_FINDING_DETECTED_NOT_AN_ATTESTATION`; it is not proof of privacy, licensing or
absence of contamination.

## Final interpretation

La baseline unificata fornisce un confine ingegneristico PRD v9 implementato con
blocker espliciti fail-closed. Non può rivendicare conformità scientifica completata,
performance validata, training autorizzato, rilascio External Challenge sicuro o
production readiness.

## Record storico — verifica Task9 (preservato)

**Verified scope:** repository engineering contracts, 2026-08-13.
**Scientific validation:** **`NOT_STARTED`**.
**Training and External Challenge:** **`HOLD`**.

