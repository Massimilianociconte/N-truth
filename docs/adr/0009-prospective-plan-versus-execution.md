# ADR-0009 — Piano ed esecuzione prospettici sono artefatti distinti

**Stato:** accepted for contract<br>
**Data:** 2026-08-01<br>
**Revisione:** dopo i primi 10–20 Experiment Bundle prospettici reali

## Contesto

Un sample sheet con il solo lifecycle corrente non ricostruisce sempre il disegno
originario. Sostituzioni, pooling, perdite e cambi di trattamento possono modificare
l'inferenza pur lasciando un inventario finale internamente coerente.

## Alternative

- sovrascrivere il piano con il sample sheet finale;
- conservare soltanto un log testuale libero;
- inferire le deviazioni confrontando versioni non tipizzate;
- conservare snapshot distinti e registri tipizzati piano→esecuzione.

## Evidenza e test richiesti

Il contratto deve rifiutare ID sconosciuti, aggiunte/rimozioni non spiegate,
exclusion non visibili nel final sheet, treatment change incoerenti e design eseguito
diverso senza deviation. Fixture positive e negative coprono ogni classe di evento.
I primi bundle reali misureranno campi mancanti e costo di compilazione del wizard.

## Decisione e motivazione

`ProspectivePlanExecutionRecord` conserva separatamente:

- `planned_design` e `planned_sample_sheet`;
- `executed_design`;
- `deviations`, `substitutions`, `exclusions`, `pooling`, `lost_samples` e
  `treatment_changes`;
- `final_sample_sheet`.

Il record è un candidato auditabile. Solo `ProspectiveGoldRecord`, con almeno due
annotazioni distinte, due ruoli reviewer e adjudication timestamped, può dichiarare
`adjudicated_gold`.

## Limiti e conseguenze

Il compiler D0 e l'API non persistono ancora automaticamente questo record: integrarli
richiede UX, storage e migrazione dedicati. Il contratto non certifica che la deviazione
sia scientificamente accettabile; rende osservabile la differenza tra piano ed
esecuzione affinché regole e persone possano valutarla.
