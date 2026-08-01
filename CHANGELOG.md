# Changelog

Tutte le modifiche rilevanti sono registrate in questo file. Il progetto segue
[Semantic Versioning](https://semver.org/) per codice, schema, grafo, parser, ruleset e
ontologia; queste versioni possono avanzare indipendentemente.

## [Unreleased]

### Added

- Contratti PRD v3 per evidenze tipizzate, determinabilità, provenance e grafo esteso.
- Separazione tra `allocation_level` e `application_level`, supporto a contrasti
  multifattoriali ed estimando minimo esplicito.
- Scenari condizionali di `n` e supporto di schema/motore/report alle tre classi
  scientifiche di alert: `DESIGN_REPLICATION`, `ANALYTICAL_DEPENDENCE` e
  `INFERENCE_SCOPE`; tutte le 32 regole dichiarano una classe e un test vieta il
  fallback implicito e congela la mappatura candidata (10/17/5).
- Baseline deterministica locale per ingestione, parsing, estrazione, grafo, regole e report.
- Dodici casi sintetici di regressione, matrice di 128 scenari di contratto per le
  32 regole e test di sicurezza/offline. Le fixture non sono gold né expert-reviewed.
- Draft di Annotation Guideline, Data Management Plan, validation protocol e cards.
- Segmentazione multi-blocco, coreference deterministica e grafo instance-level da sample sheet.
- Target inferenziale, estimando esplicito e compilatore conservativo della
  `DesignSpecification`.
- Correzioni append-only con audit trail, undo/redo, ricalcolo ed export candidate annotations.
- API FastAPI loopback, export RO-Crate/JSON-LD e interfaccia locale di revisione.
- Contratto di fixture positive, negative, ambigue ed eccezioni per tutte le 32 regole.
- Fixture end-to-end generate come file DOCX, XLSX, PDF e JATS autentici; challenge set ampliato.
- Workflow CI, lockfile riproducibili, SBOM e benchmark locale rules-only.
- Run e revisioni append-only isolati, pubblicazione atomica e lock di sessione contro lost update;
  RO-Crate finale con candidate annotations, audit e stato undo/redo/branching verificati.
- Import R/Python/R Markdown read-only (`never_execute`), con estrazione del clustering
  dichiarato come evidenza silver e senza inferire l'allocazione.
- Contratto parser AI v2.0.0 con JSON Schema, validazione dei candidate fact e adapter
  sostituibile; nessun backend o modello viene attivato dalla sua presenza.
- Contratti fail-closed per autorizzazioni, licenze, snapshot corpus, gruppi anti-leakage,
  lineage e scansione privacy stand-off.
- `privacy-scan.json`, `share-readiness.json`, endpoint e comando CLI per valutare
  esplicitamente `share`/`redistribute`; il gate non esegue trasferimenti e non inferisce
  diritti dai documenti.
- JSON Schema del parser AI inclusi negli export/RO-Crate; la crate attribuisce
  Apache-2.0 al software ma non inferisce o sostituisce licenze e diritti del dataset/input.
- Percorso positivo bilingue con Methods statement, tabella di `n`, livelli epistemici e
  checklist DRIVER-aligned informativa e non certificante.
- Riconciliazione documentata tra PRD v1 e v3, checklist dei primi passi umani e template
  di revisione esterna.
- Specifica pubblica autosufficiente, registry machine-readable dei riferimenti R01-R06,
  README operativo, policy di sicurezza/supporto e documentazione open source.
- Gate negativi della distribuzione contro cache, dati locali, `.env` e chiavi private;
  smoke test pulito e offline di wheel e sdist.
- Contratto CLI coerente: lingua limitata a `it|en`, errori workspace sintetici e
  acknowledgement obbligatorio per domini non validati.

### Known release blockers

- Il requisito delle 30–60 fixture canoniche complete e revisionate non è soddisfatto
  dalla sola matrice sintetica del test harness.
- La classificazione v3 delle 32 regole è implementata ma non ancora revisionata da
  biostatistico e wet-lab reviewer indipendenti.
- Dieci Experiment Bundle reali o pubblici con autorizzazione/licenza verificata non sono
  ancora disponibili.
- Gold pilot con doppia annotazione e IAA non disponibile.
- Regole e definizioni non ancora approvate da biostatistico e wet-lab reviewer indipendenti.
- Revisione esterna v0.1 e risultati CI cross-platform su una revisione candidata non sono
  ancora documentati.
- Baseline few-shot, modelli ML, calibrazione appresa ed external validation non sono stati
  eseguiti.
- Nessuna release scientifica o dichiarazione di conformità è autorizzata da questa baseline.
