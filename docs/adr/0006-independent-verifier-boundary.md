# ADR-0006 — Verifier separato dal generatore e autorità deterministica

**Stato:** accepted for development<br>
**Data:** 2026-08-01<br>
**Revisione:** prima di promuovere un semantic verifier nel runtime scientifico

## Contesto

Un unico modello che genera e approva il proprio grafo può ripetere lo stesso errore
con alta confidenza. D'altro canto, un secondo modello non può sostituire invarianti
deterministici o conferma umana.

## Alternative

- self-verification dello stesso modello;
- hard verifier soltanto;
- hard verifier più semantic verifier indipendente su tutti i campi;
- hard verifier sempre e semantic verifier indipendente attivato sui campi decisivi;
- revisione umana senza verifier automatico.

## Benchmark richiesto

Misurare trigger rate, agreement/disagreement col generatore, errori critici corretti,
falsi blocchi, latenza, RAM e riduzione o aumento del tempo di revisione. Il confronto
usa decisive fields, contraddizioni e challenge reali, non solo JSON malformati.

## Decisione e motivazione

L'hard verifier è sempre attivo e conserva l'autorità sugli invarianti. Il semantic
verifier è indipendente dal generatore per modello, prompt o training lineage quando
controlla allocation/application, decisive coreference, conflitti o grafi che cambiano
EU/n. Può bloccare o chiedere revisione; non può rendere valido un grafo hard-invalid,
chiudere un missing fact o autorizzare output vietati dalla determinabilità.

## Limiti e conseguenze

Il repository contiene hard verifier sempre attivo e un **semantic verifier runtime
algoritmico** (`ntruth.verifier.semantic`, backend `algorithmic_v1`) indipendente dai
pesi del generator. Un backend modello (`model_provisional`) resta fail-closed finché
non esiste lineage indipendente + benchmark + budget stage. Se nessun candidato
modello supera costo e qualità, hard + semantic algoritmico + human review restano
la baseline onesta. Vedi `docs/semantic-verifier-runtime.md`.
