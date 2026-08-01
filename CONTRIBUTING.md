# Contributing to N-Truth

N-Truth accetta contributi software, scientifici e documentali, ma richiede confini di
evidenza più rigorosi di un progetto applicativo ordinario. Una suite verde non rende
una regola scientificamente approvata e un esempio sintetico non diventa gold.

## Prima di iniziare

- Leggere la [specifica pubblica](docs/public-specification-v0.1.md), la
  [struttura del repository](docs/repository-structure.md) e i
  [riferimenti scientifici](docs/scientific-references.md).
- Aprire o collegare una issue che descriva il problema, il perimetro e il rischio
  scientifico.
- Non allegare paper non redistribuibili, dati di laboratorio, identificatori,
  credenziali o sample ID reali.
- Usare una fixture sintetica minima per riprodurre bug e richieste.
- Dichiarare se il cambiamento modifica schema, ruleset, guideline, parser contract,
  corpus o output pubblico: sono versionati separatamente.

## Invarianti da preservare

- Distinguere `DESIGN_REPLICATION`, `ANALYTICAL_DEPENDENCE` e `INFERENCE_SCOPE`.
- Non fondere `allocation_level` e `application_level`.
- Non creare un'unità sperimentale globale per l'intero paper.
- Non sostituire `n_independent = null` con `n_declared` o `n_observational`.
- Conservare alternative, conflitti, evidenze e provenance.
- Trattare author assertion e codice statistico come evidenza con limiti espliciti.
- Non assegnare probabilità alle conseguenze deterministiche.
- Non scegliere automaticamente test, formula o power analysis come verità.
- Non promuovere candidate annotation/AI output a gold senza review.
- Non suggerire conformità o endorsement DRIVER/NC3Rs.

## Modifiche alle regole

Ogni nuova regola o modifica semantica richiede:

1. `rule_id` e versione;
2. una delle tre classi scientifiche e severity separata;
3. precondizioni eseguibili;
4. eccezioni e/o astensione, quando pertinenti;
5. messaggio italiano e inglese;
6. rule trace e riferimenti scientifici;
7. scenari positivo, negativo, ambiguo ed eccezione;
8. fixture canonica completa con grafo, output, controesempio e riferimento;
9. review di biostatistico e domain expert prima di chiamarla “approvata”.

Il generatore di contesti di test dimostra copertura del codice; non sostituisce la
fixture scientifica completa.

## Modifiche allo schema o al parser contract

- Mantenere validazione fail-closed dei riferimenti e `extra=forbid` dove previsto.
- Aggiungere migrazione/adapter esplicito per modifiche incompatibili.
- Aggiornare JSON Schema, esempi, documentazione e versioni applicabili.
- Aggiungere test di round-trip, riferimenti pendenti, coordinate ed evidence span.
- Non inserire un campo verdetto nell'output del parser AI.

## Dati, fixture e modelli

- Non aggiungere asset reali senza checksum, provenienza, prova della licenza o
  autorizzazione e usi granulari.
- L'analisi locale non implica `train`, `share` o `redistribute`.
- Synthetic è solo train/stress test; silver non entra nel test gold senza review.
- Non iniziare training senza i gate elencati in `models/cards/README.md`.
- Non pubblicare metriche senza snapshot, split, lineage, seed e protocollo.

## Verifica locale

```bash
uv sync --extra dev --extra api --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run pytest
pnpm --dir apps/desktop install --frozen-lockfile
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build
uv run python scripts/generate_sbom.py --check sbom.cdx.json
uv build
uv run python scripts/check_distribution.py
uv run python scripts/smoke_release.py
```

Documentare quali comandi sono stati eseguiti e su quale piattaforma. Non descrivere un
test locale come CI cross-platform o validazione scientifica.

## Pull request / change note

La descrizione deve includere:

- problema e comportamento atteso;
- file e versioni toccati;
- impatto scientifico e compatibility note;
- test/fixture aggiunti;
- dati o licenze coinvolti (oppure “nessuno”);
- limiti e gate ancora aperti;
- reviewer richiesti: software, wet-lab, biostatistica, governance.

Un maintainer può accettare una modifica per sviluppo lasciando aperta la review
scientifica. Questo stato deve rimanere visibile nel changelog e nelle card.

Per problemi di installazione e release consultare rispettivamente
[Troubleshooting](docs/troubleshooting.md) e la [procedura di release](docs/releasing.md).
