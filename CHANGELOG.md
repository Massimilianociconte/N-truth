# Changelog

Tutte le modifiche rilevanti sono registrate in questo file. Il progetto segue
[Semantic Versioning](https://semver.org/) per codice, schema, grafo, parser, ruleset e
ontologia; queste versioni possono avanzare indipendentemente.

## [Unreleased]

### Documentation

- Full documentation refresh (2026-08-02): verified status snapshot
  (`docs/status-snapshot.md`), documentation map (`docs/README.md`), README/system
  card/model card/migration report/ADR-0010 aligned to registry
  (`PARTIALLY_VERIFIED` artifact-bound; science `NOT_STARTED`; training HOLD;
  annotation protocol draft; human second packet ready, not complete).
- ADR index lists 0011 (Outlines) and 0012 (P0 LoRA protocol + HOLD).
- Public specification FR-018: determinability derived via rules/output policy, not
  free-form model classification.
- Scientific claim hygiene: candidate-only AI; dry-run ≠ real data; AI review ≠ human
  IAA; synthetic P0 ≠ gold; engineering smoke ≠ trained product model.

### Added

- Constrained decoding adapter **Outlines + MLX-LM** (`model_backends/constrained.py`)
  with explicit status codes (no silent free-decode fallback).
- Stage-level decoding schemas (evidence / entity_count / relations / minimal graph)
  and B4 matrix A/B/C/D runner (`scripts/models/run_b4_constrained_matrix.py`).
- ADR-0011 (Outlines/MLX constrained decoding choice).
- B4 reports: free vs constrained on 39 frozen eval cases
  (`benchmarks/fewshot_p0/constrained/`).
- Semantic stage scorer `1.0.0` + report C (DEV): bootstrap CI, failure
  taxonomy, decisione `GO_LORA_P0` (i 39 casi restano DEVELOPMENT, non train/test).
- Training program **P0_LORA_APPROVED** (sperimentale): TDS P0-alpha, factory
  sintetica graph-first, snapshot `data/training/p0-alpha/`, config LoRA
  `granite-4.1-3b-p0-lora.json`, ADR-0012. Non modifica scientific validation.
- **HOLD_PENDING_REAL_ANCHOR**: snapshot P0-alpha congelato `SYN_G1_UNANCHORED`;
  substantive LoRA bloccato; smoke ingegneristico autorizzato; piano calibration
  umano in `docs/training/human-anchored-calibration-plan.md`.
- Reality-check P0: guideline `annotation-reality-check-p0-v0.1`, schema/template
  Real Experiment Bundle, pilot-internal 3–5, validator; formal 10–20 ancora vuoto.
- Pilot constraints: sources immutabili+hash, second review cieca, triade
  UNKNOWN/NOT_REPORTED/NOT_APPLICABLE, no train auto, batteria eterogenea 3–5,
  gate esplicito verso 10–20, versioning guideline senza rewrite retroattivo.

### Changed

- `GenerationRequest` / `GenerationResult`: optional `output_schema`, `constrained`,
  explicit `max_tokens` diagnostics (EOS / truncation / mlx default 256).
- **Train A default model (architectural migration):** IBM Granite 4.1 3B Instruct
  (`ibm-granite/granite-4.1-3b`) replaces Qwen3-4B on all default paths. **Runtime
  multipiattaforma, benchmark scientifici e fine-tuning restano aperti** (vedi
  `docs/granite-migration-report.md`).
- Qwen profile moved to `models/configs/legacy/`; caricamento solo con opt-in
  esplicito (`allow_legacy=True` o `NTRUTH_ALLOW_LEGACY_QWEN=1`).
- Provider-agnostic `ModelBackend` / `GraniteBackend`; registry e `NTRUTH_MODEL_*`.
- MLX bootstrap descritto come **conversione community** (`mlx-community/...`);
  **configured maximum context 131072** (non host-validato); LoRA targets verificati
  su state dict Granite.
- ADR-0010 e report di migrazione allineati al verdetto di stato.
- Registry `qualification` (schema **1.3.0**): fingerprint canonico SHA-256,
  gate con reason code, coerenza schema, prerequisiti `PARTIALLY_VERIFIED`.
- Ledger SQLite append-only e **tamper-evident** delle transizioni
  (`qualification_ledger.sqlite3`): trigger anti UPDATE/DELETE, monotonia
  `sequence=max+1` in `BEGIN IMMEDIATE`, GENESIS + anti-reseed, hash chaining,
  evidence content-addressed; policy ledger-first (JSON mirror rigenerabile).

### Added

- Revisione PRD v6.1 con Synthetic Task Use Matrix, Runtime Resource Budget, Lean
  Governance Matrix, registro delle affermazioni assolute, response matrix e
  changelog occurrence-aware; scopo AI finale e validazione reale restano invariati.
- Runtime Resource Manager backend-agnostic con profili `LOW_MEMORY`, `BALANCED` e
  `QUALITY`, fingerprint del benchmark, load/unload sequenziale, context cap, CPU
  fallback, cache LRU e telemetria bundle/stage.
- Bridge opzionale MLX → Resource Manager (`mlx_resource_bridge`, `budget_io`,
  `runtime_env`) e template di budget non misurato in `benchmarks/runtime/`.
- Protocollo `ntruth-ml benchmark-resources` e budget reale M5 Pro 24 GB
  (`benchmarks/runtime/m5-pro-24g-*.budget.json`, stage `mlx_generate` /
  `rules_engine` / `hard_verifier` / `semantic_verifier`).
- Semantic verifier runtime `algorithmic_v1` (`ntruth.verifier.semantic`), wired
  in pipeline; backend modello fail-closed finché non c’è lineage indipendente.
- Persistenza SQLite append-only `plan_execution_records` (migrazione v4), API
  `/v1/prospective/plan-execution` e pannello desktop piano vs esecuzione.
- `ValidationStackReport` che separa esplicitamente sintassi/JSON da accettabilità
  scientifica (schema, referential, hard verifier, human confirmation).
- Contratto prospettico che conserva separatamente piano, esecuzione, sample sheet
  finale, deviazioni, sostituzioni, esclusioni, pooling, campioni persi e cambi di
  trattamento, con promotion gold fail-closed.
- ADR 0002-0009 per architettura, backend/resource manager, quantizzazione,
  structured decoding, verifier, storage, rules language e piano/esecuzione.
- Invarianti CI positivi, negativi e controfattuali per split/eligibility, leakage,
  count semantics, inference scope, allocation validity e `AUTHOR_ASSERTION`.
- Draft v6 operational documents for independence, Derivation Gold, graph-first
  synthetic generation and record-to-facsimile review. They define gates without
  claiming that expert review, governed datasets or the renderer already exist.
- Provenance completa delle correzioni: gli eventi `apply`, `undo` e `redo`
  conservano ruolo privacy-safe, timestamp con fuso e metadati inclusi nell'ID
  verificabile; i locator EvidenceSpan corretti vengono confrontati con il Document IR
  immutabile.
- Separazione evidence-aware nel report fra fatti osservati, asserzioni degli autori,
  conferme utente, inferenze e ipotesi; l'HTML rende entrambi i rami condizionali e le
  interpretazioni trattenute dei conflitti.
- Separazione fra registro sorgente e vista positiva: i `CountRecord` restano
  auditabili, mentre un `INDEPENDENT_N` numerico e soppresso dalla vista pubblicabile
  fuori da `DETERMINATE` e il relativo ID viene registrato.
- Riconciliazione completa con il PRD v6: Train D/Train A, micro-dominio D0,
  matrice dei sette `DeterminabilityState` e separazione esplicita tra supporto
  software e validazione scientifica.
- Core Profile `d0_core` predefinito per TXT, Markdown e CSV semplice; i parser
  complessi restano opt-in `extended_experimental` e fuori dai claim D0.
- Contratto di indipendenza operativa tri-state con meccanismo obbligatorio quando
  `TRUE`; allocation e ID restano candidati e non provano da soli l'unita
  sperimentale.
- `CountRecord`, lifecycle completo, quantificatori, scope con reason code per i
  null, `ExclusionRecord` ed `effective_n` esclusivamente diagnostico.
- Hard verifier sempre attivo, output policy per i sette stati e dieci stage envelope
  del futuro parser con esiti `complete`, `partial` e `failed`.
- Ruleset `ntruth-core@0.2.0`; le modifiche semantiche a `GEN-001` e `GEN-002`
  avanzano entrambe a `1.1.0`, mentre l'asset storico `0.1.0` resta immutato e
  caricabile per riproducibilita.
- `SampleSheetSpec` v6, CLI di generazione/validazione, ingest MIME-aware e blocco di
  macro, XML con DTD/entity, traversal, symlink e codice eseguibile.
- Persistenza locale SQLite e blob store content-addressed con migrazioni,
  transazioni, revisioni/audit append-only, deduplica e tamper detection.
- Checksum v6 dell'intero `ProjectManifest`, verifica prima di qualsiasi backfill e
  migrazione esplicita dei soli manifest legacy riconoscibili dopo verifica sorgenti.
- Eligibility distinte per training, evaluation e release; `TEST` ed
  `EXTERNAL_CHALLENGE` non sono mai training-eligible e i gruppi anti-leakage
  includono famiglie articolo/dataset/lab/facility/synthetic/counterfactual.
- Workspace prospettico D0 nella UI con wizard, sample sheet, conteggi lifecycle,
  evidence/proof view e canvas esteso dietro opt-in post-v0.1-D.
- Compiler prospettico D0 canonico con API locale, hard verifier, capability gate,
  audit/checksum di sessione, limiti fail-closed e collegamento end-to-end dal wizard;
  i controlli client restano marcati come preview non autorevole.
- Il SampleSheet del wizard rende osservabili per riga anche giornata, operatore
  pseudonimizzato e incubatore, cosi il gate di confondimento non dipende da JSON
  preparato a mano.
- Il confine di ingestione rifiuta output o workspace annidati in una directory
  sorgente, impedendo che copie di run precedenti vengano reingerite dopo la modifica
  o rimozione dei file originali.
- Documentazione operativa v6 per Core Profile, sample sheet, designazione dei dati,
  bootstrap 10-20, calibration 30-50 e feasibility 100-150.
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
- Contratto parser AI v2.0.0 conservato come superficie legacy esplicita; i nuovi
  backend usano i dieci contratti staged v6 e `CandidateGraphSet` candidate-only.
- Contratti fail-closed per autorizzazioni, licenze, snapshot corpus, gruppi anti-leakage,
  lineage e scansione privacy stand-off.
- `privacy-scan.json`, `share-readiness.json`, endpoint e comando CLI per valutare
  esplicitamente `share`/`redistribute`; il gate non esegue trasferimenti e non inferisce
  diritti dai documenti.
- Dieci JSON Schema staged v6 e schema input inclusi negli export/RO-Crate; lo schema
  output v2 storico è rinominato `parser-ai-output-legacy-v2.schema.json`. La crate attribuisce
  Apache-2.0 al software ma non inferisce o sostituisce licenze e diritti del dataset/input.
- Percorso positivo bilingue con Methods statement, tabella di `n`, livelli epistemici e
  checklist DRIVER-aligned informativa e non certificante.
- Riconciliazione documentata tra PRD v1 e v3, checklist dei primi passi umani e template
  di revisione esterna.
- Specifica pubblica autosufficiente, registry machine-readable dei riferimenti R01-R06,
  README operativo, policy di sicurezza/supporto e documentazione open source.
- Gate negativi della distribuzione contro cache, dati locali, `.env` e chiavi private;
  smoke test isolato di wheel e sdist con dipendenze vincolate dal lockfile e modalità
  offline opzionale.
- Contratto CLI coerente: lingua limitata a `it|en`, errori workspace sintetici e
  acknowledgement obbligatorio per domini non validati.
- Pipeline deterministica per supervision records: gate di licenza/review, normalizzazione,
  deduplica esatta/near, conflitti di label, leakage group transitivi, split group-aware,
  synthetic train-only e manifest content-addressed.
- Corsia opzionale `ntruth-ml` per Apple Silicon con profilo Granite 4.1 3B MLX 4-bit
  (ex bootstrap Qwen rimosso dai default),
  doctor e budget disco, download esplicito, verifica checksum, token audit, QLoRA,
  checkpoint/ripresa, early stopping a fasi e logging dell'ambiente.
- Training e generazione v6 vincolati a `GoldParserTarget` adjudicato e
  `CandidateGraphSet` con autorità model; task legacy, determinability e verdict sono
  rifiutati. Un solo retry, metriche candidate-only, temperature scaling
  validation-only, risk-coverage ed export dell'adapter restano fail-closed.
- Valutazione pubblicabile delle fonti dati, budget complessivo da 35,5 GiB e guida
  riproducibile della pipeline MLX; dati, modello e artefatti di lavoro restano ignorati.
- Snapshot e run state MLX schema v2 con verifica content-addressed dei record, deduplica,
  approvazioni, split e checkpoint; i link near-duplicate anti-leakage ignorano il
  target e i conflitti di split sono fail-closed.
- Lineage obbligatoria per prediction, calibrazione ed export: binding tra nome file e
  split, ricostruzione di score/metriche/confidence, ricalcolo della calibrazione e
  blocco di adapter o snapshot estranei.

### Known release blockers

- Il requisito delle 30–60 fixture canoniche complete e revisionate non è soddisfatto
  dalla sola matrice sintetica del test harness.
- La classificazione delle 32 regole, mantenuta nel PRD v6, è implementata ma non
  ancora revisionata da
  biostatistico e wet-lab reviewer indipendenti.
- Dieci Experiment Bundle reali o pubblici con autorizzazione/licenza verificata non sono
  ancora disponibili.
- Gold pilot con doppia annotazione e IAA non disponibile.
- Regole e definizioni non ancora approvate da biostatistico e wet-lab reviewer indipendenti.
- Revisione esterna v0.1 e risultati CI cross-platform su una revisione candidata non sono
  ancora documentati.
- Baseline few-shot su casi reali, fine-tuning scientifico, calibrazione appresa ed
  external validation non sono stati eseguiti; lo smoke MLX sintetico non li sostituisce.
- Nessuna release scientifica o dichiarazione di conformità è autorizzata da questa baseline.
