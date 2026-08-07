# ADR-0013 — Migrazione al contratto scientifico PRD v8.0

**Stato:** accettato  
**Data:** 2026-08-07

## Contesto

Il repository contiene un working tree v7-era (inventariato in
`docs/dirty-tree-inventory-20260802.md`) congelato nello snapshot
`baseline/pre-v8-migration-20260807`. Il PRD v8.0 ridefinisce il contratto
scientifico del sistema; la migrazione deve avvenire senza perdita di
evidenza, senza riscrittura silenziosa della storia e senza decisioni
scientifiche non autorizzate.

## Decisione

1. **PRD v8.0 come fonte normativa.** Ogni contratto scientifico migra
   verso il testo del PRD v8.0; l'**Appendice AE** è la mappa ufficiale di
   migrazione v7→v8 e l'unico riferimento per la corrispondenza tra i due
   contratti.
2. **Migrazione additiva (AE.1).** Sono preservati: evidenza grezza, storia
   del grafo, submission umane. Gli output v7 esistenti sono **immutabili**;
   le claim vengono **ri-derivate** sotto versione dichiarata di teoria e
   regole, mai sovrascritte.
3. **Finestra di doppia rappresentazione.** Durante la transizione, le
   valutazioni v7 restano visibili come **proiezioni read-only deprecate**
   del `DerivedClaimSet` v8; nessuna scrittura avviene più sui contratti v7.
4. **Politica fail-closed `SCIENTIFIC_REVIEW_REQUIRED`.** Ogni decisione
   scientifica non determinabile dal testo del PRD v8.0 riceve un contratto
   fail-closed e una voce nello
   [Scientific Review Register](../scientific-review-register.md), invece di
   una risposta inventata.
5. **Artefatti storici immutabili.** `tests/golden/*`, risultati benchmark,
   ruleset `0.2.0` e ontologia non vengono modificati: la storia di
   valutazione v7 deve restare riproducibile.
6. **Isolamento del lavoro.** Tutta la migrazione avviene nel worktree
   `.worktrees/prd-v8-migration` sul branch
   `migration/prd-v8-scientific-contract`; nessun merge senza autorizzazione
   esplicita.

## Conseguenze

- La baseline di validazione pre-migrazione (ruff/mypy/pytest) è fissata
  sullo snapshot `baseline/pre-v8-migration-20260807` e i suoi valori
  registrati fanno da riferimento per ogni fase successiva.
- I contratti congelati `SCIENTIFIC_REVIEW_REQUIRED` richiedono revisione
  umana registrata prima di qualsiasi sblocco.
- La doppia rappresentazione introduce debito di proiezione: le viste v7
  deprecate vanno rimosse solo a migrazione approvata e completata.

## Riferimenti

- PRD v8.0 (`prd/N-Truth_PRD_scientifico_completo_v8.0.md`) e Appendice AE
- Registro: `docs/scientific-review-register.md`
- Inventario dirty tree: `docs/dirty-tree-inventory-20260802.md`
- Snapshot baseline: `baseline/pre-v8-migration-20260807`
