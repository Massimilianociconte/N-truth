# ADR-0003 — Backend aperto e Runtime Resource Manager misurato

**Stato:** resource manager accepted for instrumentation; backend benchmark-gated<br>
**Data:** 2026-08-01<br>
**Revisione:** dopo benchmark ripetuti sul MacBook Pro M5 Pro da 24 GB

## Contesto

Una pipeline che può caricare encoder, LLM e verifier senza una politica di residenza
esplicita rischia picchi di memoria, swap e latenza non osservati. Valori derivati dalla
dimensione nominale dei modelli non rappresentano un budget operativo.

## Alternative

- MLX/Metal come backend locale iniziale;
- altro backend Apple Silicon compatibile con i contratti;
- CPU per stage supportati o fallback controllato;
- esecuzione esterna solo dopo governance e Resource Gate dedicati.

Il resource manager è backend-agnostic: ogni componente implementa `run` e `close` e
viene creato da una factory associata al device. Nessun ADR congela oggi il backend del
modello finale.

## Benchmark richiesto

Per profilo e stage si registrano almeno macchina, memoria unificata, sistema operativo,
runtime/versione, input/output token, latenza, picco RAM aggiuntivo e variazione swap.
Servono ripetizioni su bundle piccoli, mediani, grandi, avversariali e sotto carico
concorrente controllato. Il budget viene derivato dai massimi osservati: un eventuale
margine deve essere a sua volta misurato, non aggiunto come percentuale universale. Una
misura di un'altra macchina o profilo non è riutilizzabile silenziosamente.

## Decisione e motivazione

Il package `ntruth.runtime_resources` definisce:

- profili `LOW_MEMORY`, `BALANCED`, `QUALITY` come politiche configurabili, senza
  stime RAM incorporate;
- chunking section-first e finestre sovrapposte con limite di context window;
- stage rigorosamente sequenziali;
- load/unload esplicito, cache LRU bounded ed eviction con `close()`;
- fallback CPU solo se abilitato e se il load sul device preferito fallisce prima
  dell'esecuzione;
- budget costruibili soltanto da osservazioni benchmark-bound;
- metriche di latenza, token, picco RAM e swap per stage e bundle;
- failure chiusa quando context, budget o misurabilità richiesta non sono rispettati.

MLX/Metal resta il primo backend da misurare sul computer target, non una dipendenza del
core né una scelta scientifica definitiva.

## Limiti e conseguenze

Il probe standard campiona ai confini dei chunk; il picco del processo usa la misura
del sistema operativo, mentre lo swap disponibile è system-wide e non attribuibile con
certezza a un singolo processo. I benchmark di release dovranno usare anche strumenti
Apple/MLX più granulari e riportarne versione e metodo. I valori di context window dei
profili sono punti di partenza configurabili: solo il budget misurato ne autorizza
l'uso su un dato stage.
