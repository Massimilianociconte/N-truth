# Changelog PRD v6.1

**Data:** 1 agosto 2026  
**Baseline:** PRD v6.0, checksum registrato in `prd/README.md`  
**Tipo:** revisione minor execution-critical; obiettivo scientifico invariato

## Added

- Synthetic Task Use Matrix P0/P1/P2 con bande synthetic/real gold, real-only
  evaluation e promotion/stop rules.
- Runtime Resource Manager con profili LOW_MEMORY, BALANCED e QUALITY, lifecycle dei
  modelli, chunking, context caps, cache byte-aware, fallback e telemetria locale.
- Runtime Resource Budget derivato da benchmark sul MacBook Pro Apple M5 24 GB.
- Confronto architetturale A-E comprendente cascata, monolite chunked, encoder
  multi-task, modello N-Truth e challenger quantizzato sequenziale.
- Stack esplicito di validazione sintattica, strutturale, numerica, temporale,
  evidence-grounded, contraddittoria e umana.
- Lean Governance Matrix a quattro livelli e attivazione progressiva di Resource Gate,
  STOP Authority e validation committee.
- Registro occurrence-aware delle affermazioni assolute e delle sostituzioni.
- Soglie di release marcate `PROVISIONAL` fino al pilot e al protocollo approvato.
- Invariant-test contract per split, leakage, count semantics, inference scope,
  allocation validity e AUTHOR_ASSERTION.
- Prospective Gold con record separati planned/executed e deviazioni tipizzate.
- Copertura ADR minima per modello, backend, quantizzazione, structured decoding,
  verifier, database e linguaggio del rules engine.

## Changed

- La cascata specialistica è baseline preferita, non architettura obbligatoria.
- Nomi, dimensioni, framework e quantizzazioni sono challenger configurabili e non
  decisioni scientifiche prima del benchmark.
- Il target `peak RAM <=20 GB` non è più un requisito universale: il limite operativo
  proviene da benchmark versionato e hardware fingerprint.
- Il vantaggio prospettico è formulato come riduzione dell'ambiguità e osservabilità
  delle deviazioni, non eliminazione dell'incertezza.
- Il determinismo del ruleset è separato dalla scelta del modello statistico e dei
  gradi di libertà.
- Gli encoder sono descritti come non-generativi, ma fallibili su extraction e
  relation tasks.
- Il gold prospettico distingue esplicitamente piano, eseguito, sostituzioni,
  esclusioni, pooling, campioni persi, cambi di trattamento e sample sheet finale.
- La governance dei primi 90 giorni è ridotta agli artefatti necessari al bootstrap;
  i gate più onerosi scattano quando aumenta il rischio.

## Clarified

- Un JSON grammar-valid non è un grafo scientificamente corretto.
- `biological_source_count` ed `experimental_unit_count` sono tipi distinti; la loro
  distinzione non implica disuguaglianza numerica in ogni caso.
- `inference_scope` e `validity_of_allocation` sono dimensioni distinte.
- `split=TRAIN` vieta `evaluation_only=true`, ma non vieta a priori usi multipli
  autorizzati che vengono poi separati dal manifest e dal leakage policy.
- Synthetic, silver, real gold e authority level restano assi indipendenti.

## Removed or superseded

- Intervalli di dimensione modello come prescrizione normativa.
- Budget RAM teorico fisso come release proof.
- Qualunque interpretazione della cascata come obbligo architetturale.
- Qualunque uso di `JSON valido` come sinonimo di ricostruzione corretta.
- Qualunque soglia F1/IAA/degradation presentata come definitiva prima del pilot.

Le formulazioni citate dall'audit ma non presenti letteralmente nella v6.0 sono
registrate come chiarimenti preventivi, non come cancellazioni fittizie.

## Companion implementation

- `ntruth.runtime_resources` implementa profili, fingerprint, budget osservati,
  scheduling sequenziale, context cap, CPU fallback, cache LRU e telemetria.
- `ntruth.prospective.plan_execution` conserva piano, esecuzione, deviazioni e sample
  sheet finale senza sovrascrittura retroattiva.
- `ntruth.facsimile` e gli eligibility validator esprimono gli invarianti richiesti
  come contratti eseguibili.
- La fixture `tests/fixtures/v6/facsimile_split_counterfactuals.json`, i test dedicati
  e il marker CI `invariant` coprono casi positivi, negativi e controfattuali.
- Gli ADR 0002-0009 registrano decisioni aperte, provvisorie o benchmark-gated.

## Limiti espliciti della revisione

- Restano assenti gold reale, modello fine-tuned scientificamente selezionato e
  External Challenge eseguito.
- Il backend **modello** del semantic verifier (`model_provisional`) non è ancora
  configurato: serve lineage indipendente + benchmark; fino ad allora il runtime
  usa `algorithmic_v1`.

## Implementazione codice successiva alla revisione documentale

- `ntruth.runtime_resources.budget_io` + `ntruth.training.mlx_resource_bridge`
  collegano opzionalmente MLX a `RuntimeResourceManager` (fail-closed su budget
  e fingerprint; path legacy invariato se il budget non è fornito).
- Benchmark reale M5 Pro 24 GB: `ntruth-ml benchmark-resources` e artifact in
  `benchmarks/runtime/m5-pro-24g-*.budget.json` (fingerprint `Mac17,9`, mlx-lm).
- Persistenza append-only `plan_execution_records` (migrazione SQLite v4), API
  `POST/GET /v1/prospective/plan-execution` e promozione gold, pannello desktop
  piano vs esecuzione allineato a `ProspectivePlanExecutionRecord`.
- `ntruth.verifier.validation_stack` formalizza che JSON/sintassi validi non
  equivalgono a ricostruzione scientifica accettabile.
- `ntruth.verifier.semantic` (`algorithmic_v1`) eseguito in pipeline; non override
  hard-invalid. Vedi `docs/semantic-verifier-runtime.md`.
