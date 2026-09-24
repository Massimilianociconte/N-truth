# ADR-0002 — Architettura del modello scelta mediante benchmark

**Stato:** benchmark-gated; nessun vincitore selezionato<br>
**Data:** 2026-08-01<br>
**Revisione:** dopo Parser Gold/Derivation Gold e prima di congelare la baseline Train A

## Contesto

La visione finale richiede un modello AI specializzato che proponga evidenze, entità,
relazioni e grafi candidati. Una cascata specialistica è una buona ipotesi iniziale per
un host da 24 GB, ma imporla prima delle misure confonderebbe una preferenza
ingegneristica con un risultato sperimentale.

## Alternative

- **A:** encoder + small LLM + verifier indipendente;
- **B:** small LLM monolitico con chunking gerarchico;
- **C:** encoder multi-task;
- **D:** modello N-Truth fine-tuned o distilled;
- **E:** modello quantizzato più grande, caricato ed eseguito sequenzialmente.

Rules-only resta il controllo deterministico, non un sostituto della visione AI.

## Benchmark richiesto

Tutte le alternative ammissibili usano gli stessi split bundle/laboratorio e lo stesso
external challenge congelato. Il protocollo confronta almeno:

- decisive-edge F1;
- accuratezza separata di allocation e application;
- calibrazione, risk-coverage e astensione;
- tempo e numero di correzioni fino al grafo confermato;
- latenza, picco RAM, swap e token per bundle;
- prestazione sull'external challenge.

Devono essere riportati intervalli bootstrap, prevalenze, human ceiling e costo degli
errori critici. Il solo schema-valid rate non seleziona un'architettura.

## Decisione e motivazione

**A è la baseline preferita da tentare per prima, non un obbligo.** B–E restano
candidati equivalenti finché non esistono dati comparabili. Non vengono congelati nomi
di modello, numero di parametri o framework. Vince l'alternativa Pareto-ammissibile che
supera il controllo deterministico e minimizza il carico di revisione rispettando il
budget misurato.

Questa decisione mantiene il modello AI centrale, ma impedisce che la sua forma sia
scelta per intuizione o disponibilità contingente dei pesi.

## Limiti e conseguenze

Il repository non contiene ancora il gold necessario: oggi nessuna alternativa è
scientificamente selezionata. Un candidato bootstrap può collaudare la pipeline, non
produrre metriche di release. L'architettura vincente dovrà comunque emettere candidate
fact, passare hard/semantic verification e lasciare i decisive fields alla conferma
umana.
