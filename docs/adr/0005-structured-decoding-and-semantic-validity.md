# ADR-0005 — Structured decoding non equivale a validità semantica

**Stato:** accepted<br>
**Data:** 2026-08-01<br>
**Revisione:** a ogni modifica dei contratti staged o del verifier

## Contesto

Grammar-constrained decoding può impedire alcune sequenze sintatticamente invalide, ma
non prova che entità, relazioni, conteggi o evidenze ricostruiscano l'esperimento. Dire
“JSON valido” per “grafo corretto” nasconderebbe il principale rischio scientifico.

## Alternative

- parsing libero con riparazione automatica;
- JSON mode;
- grammar-constrained decoding;
- generazione schema-guided;
- output libero rifiutato e retry bounded.

## Benchmark richiesto

Oltre al syntax/schema-valid rate, ogni backend misura separatamente:

1. JSON Schema;
2. integrità referenziale;
3. compatibilità dei tipi;
4. invarianti del grafo;
5. consistenza temporale;
6. consistenza numerica;
7. supporto nelle evidenze;
8. rilevamento delle contraddizioni;
9. conferma umana dei decisive fields.

I falsi semanticamente plausibili ma errati devono essere challenge cases dedicati.

## Decisione e motivazione

La grammatica, quando disponibile, è un controllo soltanto sintattico. I modelli
Pydantic/JSON Schema verificano forma e parte dell'integrità referenziale;
`validate_candidate_graph_pair` lega coordinate e contenuto alle fonti; hard verifier,
semantic verifier condizionale e human confirmation coprono confini distinti. Nessuno
di questi livelli può essere omesso perché il precedente è passato.

Nei report si usano quindi termini separati: `syntax_valid`, `schema_valid`,
`referentially_valid`, `hard_verified`, `semantically_reviewed` e
`human_confirmed`. “Ricostruzione corretta” è riservato all'esito valutato contro gold.

## Limiti e conseguenze

Il semantic verifier operativo non è ancora addestrato o validato. Il passaggio dello
schema attuale è una proprietà software, non una metrica scientifica. Le riparazioni
automatiche non possono inventare fatti mancanti né essere escluse dal conteggio degli
errori del modello.
