# Runtime Resource Budget v6.1

**Stato:** contratto di benchmark e runtime + **artifact misurato** su MacBook Pro
Apple M5 Pro (`Mac17,9`) 24 GB. I valori di RAM/context restano validi solo per lo
stesso fingerprint `(machine, memory, OS, runtime, version)` e non sono requisiti
scientifici di accuratezza del modello.

Il contratto backend-agnostic è in `packages/ntruth/runtime_resources/`. Il ponte
MLX è in `packages/ntruth/training/mlx_resource_bridge.py`. I budget misurati stanno
in `benchmarks/runtime/` (`latest.budget.json` punta all'ultimo protocollo).

## Principi

- I componenti AI vengono eseguiti sequenzialmente per default.
- Ogni modello dichiara lifecycle `load -> warmup -> run -> release`; il rilascio deve
  eliminare i riferimenti e richiedere lo svuotamento della cache del backend quando
  disponibile.
- Il router produce chunk gerarchici per bundle, Experiment Block, sezione e span.
- Nessuna troncatura è silenziosa: coverage, token scartati e motivo vengono registrati.
- Grammar-constrained decoding riguarda la sintassi; non elimina hard verifier,
  semantic checks o revisione umana.
- I budget sono generati da un benchmark versionato e non da stime teoriche fissate
  nel codice.

## Profili operativi

| Profilo | Obiettivo | Scheduling | Context e cache | Fallback |
|---|---|---|---|---|
| `LOW_MEMORY` | Evitare pressure e swap su host occupato | Un componente residente, batch minimo, unload aggressivo | Finestra massima risultata stabile nel benchmark LOW_MEMORY; cache LRU piccola a byte | CPU per stage compatibili; astensione se il fallback viola latenza o qualità minima |
| `BALANCED` | Default interattivo dopo benchmark | Sequenziale con prefetch solo di artefatti non-model | Finestra e batch scelti sul miglior compromesso qualità/latency/peak | Retry una volta in LOW_MEMORY, poi partial result |
| `QUALITY` | Massima qualità entro il limite locale misurato | Sequenziale; challenger più costoso ammesso solo se benchmarkato | Context più ampio e cache maggiore, senza superare il safety floor | Degrado a BALANCED esplicito; mai fallback silenzioso |

I file di profilo memorizzano valori misurati (`budget_bytes`, `context_tokens`,
`batch_size`, `cache_bytes`, `swap_delta_limit_bytes`) insieme a hardware fingerprint,
runtime, versione, data e benchmark ID. Un profilo senza artifact misurato è
`UNVERIFIED` e non può sostenere claim di release.

## Calcolo del budget

Per ogni profilo il benchmark misura:

1. memoria e swap a riposo dopo una finestra di stabilizzazione;
2. picco durante load e warmup;
3. picco per stage, batch e context candidate;
4. memoria dopo release e cache clear;
5. delta di swap e memory-pressure state;
6. latenza p50/p95, token input/output e throughput;
7. cache hit/miss/eviction e spazio locale temporaneo.

Il `runtime_budget_bytes` è il massimo picco osservato nella configurazione accettata,
con safety reserve derivata dal benchmark concorrente e non da una percentuale
universale. Un incremento di context, batch, modello, quantizzazione o runtime invalida
il profilo finché il benchmark non viene ripetuto.

## Budget per stage

| Stage | Modello residente ammesso | Metriche obbligatorie | Condizione di rilascio |
|---|---|---|---|
| Routing/segmentazione | encoder, small LM o regole secondo baseline | latency, peak, input token, coverage | document map e coverage persistiti |
| Evidence/entity/count | un solo estrattore o modello multi-task | peak, token, truncation, output count | artefatto schema-valid persistito |
| Relation/event/coreference | componente specializzato o LM | peak, context, cache, evidence coverage | candidate relations persistite |
| Candidate graph assembly | modello o algoritmo, mai rules verdict | peak, alternatives, invalid outputs | graph candidate e error model persistiti |
| Semantic verification | processo/modello indipendente quando attivato | trigger, peak, latency, disagreement | verifier result persistito |
| Rules engine | nessun modello richiesto | latency, rule count, proof size | output deterministico verificato |

## Chunking, context e cache

- L'unità primaria è l'Experiment Block; si conserva un registry globale di entity e
  evidence per risolvere riferimenti cross-chunk.
- Il context limit è configurabile per stage e profilo. Il runtime rifiuta valori oltre
  il massimo benchmarkato.
- Overlap e retrieval devono produrre un coverage report; una perdita decisiva porta a
  `partial`, domanda o astensione.
- La cache usa LRU byte-aware con chiave composta da hash dell'input, stage, schema,
  modello/runtime e config. L'eviction non elimina artefatti canonici o audit.
- Model cache, artifact cache e tokenizer cache hanno budget separati.

## Telemetria locale del bundle

Ogni run registra senza contenuto scientifico grezzo:

```yaml
bundle_id: pseudonymous-or-local
profile: LOW_MEMORY|BALANCED|QUALITY
benchmark_id: required
stage_metrics:
  - stage: document_route
    latency_ms: measured
    peak_memory_bytes: measured
    swap_delta_bytes: measured
    input_tokens: measured
    output_tokens: measured
    cache_hits: measured
    cache_evictions: measured
    fallback: none|cpu|lower_profile|abstain
```

I log devono restare locali, disattivabili e privi di Methods, evidence span, nomi file
sensibili o identificatori personali.

## Benchmark di selezione

Per ciascuna alternativa architetturale si eseguono almeno cold start, warm run,
long-context, multi-document bundle, worst supported topology e background-load run.
Il report confronta qualità, astensione, review time, latency, peak memory, swap e
failure rate. Non vengono congelati backbone, numero di parametri, quantizzazione o
framework prima di questi risultati.
