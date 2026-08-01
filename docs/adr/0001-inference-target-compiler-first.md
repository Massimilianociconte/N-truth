# ADR-0001 — Target inferenziale esplicito e compiler-first

**Stato:** accepted for development; amended by PRD v3<br>
**Data:** 2026-07-31
**Gate scientifico:** revisione biostatistica ancora richiesta

## Contesto

Il PRD definisce già N-Truth come compilatore semantico e afferma che l'entità-intervento
replicata deve corrispondere alla domanda scientifica. Il contratto software originario,
tuttavia, rappresentava soltanto fattore, contrasto, endpoint e livello di assegnazione: non
aveva un oggetto computabile per domanda, claim e popolazione di inferenza.

La conseguenza è importante. Gerarchia e assegnazione possono sostenere una **candidate
allocation unit** e un **candidate independent n** per uno scope; non bastano a stabilire se
quello scope sostenga la popolazione o il claim desiderato.

## Decisione

1. Il prodotto primario è il compilatore deterministico di un `DesignSpecification` formale.
2. Ogni inferenza destinata a sostenere un claim usa un `InferenceTarget` esplicito con domanda,
   popolazione, fattori, contrasti, endpoint, unità biologica target, evidenza e stato.
3. Il PRD v3 aggiunge un `Estimand` distinto con endpoint, misura dell'effetto, popolazione/unità
   target, livello di generalizzazione, fattori ed eventuale tempo/condizione.
4. Allocazione indipendente e applicazione fisica del fattore sono campi separati; l'alias legacy
   `assignment_level` corrisponde soltanto all'allocazione.
5. Un target estratto automaticamente resta candidato. Soltanto `user_confirmed` può arrivare
   allo stato strutturalmente `supported`; questo stato non certifica validità scientifica.
6. Se target, estimando, allocazione o riferimenti sono incompleti, il compiler produce
   elicitazione e si astiene. Non completa campi mancanti con euristiche.
7. Il parser di documenti e un eventuale LLM locale sono ingressi opzionali verso lo stesso
   schema, mai il motore scientifico e mai una sorgente che sovrascrive fatti confermati.
8. L'export `analysis_handoff` elenca nesting, cluster, allocazione, applicazione,
   repeated measures, endpoint e assunzioni aperte. Il core non seleziona test, non
   genera formule eseguibili e non esegue power analysis.

## Evidenza e limiti della decisione

- Lazic et al. riportano 22% di replicazione corretta, 46% di pseudoreplicazione e 32% di
  informazione insufficiente in uno specifico campione di 200 studi animali parent-offspring.
  Queste percentuali motivano l'astensione, ma non sono un ceiling universale per ogni dominio.
- ARRIVE definisce l'unità sperimentale rispetto all'allocazione indipendente e richiede n esatto
  per gruppo/analisi. Supporta uno scope esplicito, non un n globale.
- L'ICH E9(R1) mostra perché domanda, popolazione, trattamento, variabile e summary measure
  debbano essere distinti. Il PRD v3 rende vincolante un profilo preclinico minimo di estimando;
  non importa automaticamente l'intero framework clinico.
- L'NC3Rs EDA dimostra il valore di un design IR machine-readable con critique deterministica,
  ma il suo perimetro pubblico è quello degli esperimenti animali. N-Truth mantiene come
  differenziale candidato l'ingresso da documenti/sample sheet e i disegni in vitro; tale
  differenziale dovrà essere verificato con una revisione più ampia del prior art.

## Alternative respinte

- **“LLM sostituisce NER con l'1% dello sforzo”**: nessun benchmark N-Truth lo dimostra.
  Rules-only, encoder, LLM locale e ibrido saranno confrontati sullo stesso gold blinded.
- **Soglia IAA unica come kill-switch**: i 30 casi sono un calibration set fuori dal test;
  il feasibility pilot v3 è 150–250 bundle. Vanno riportati accordo per variabile,
  intervalli, prevalenza, confusioni e cause del disaccordo; la decisione non dipende
  da un solo coefficiente arbitrario.
- **Formula mixed-model automatica**: gerarchia e target non identificano da soli distribuzione,
  random slopes, correlazioni, codifica dei contrasti o struttura residua. L'eventuale plugin
  statistico sarà separato e validato da un biostatistico.

## Fonti primarie

- Lazic SE, Clarke-Williams CJ, Munafò MR (2018), *What exactly is N in cell culture and animal
  experiments?*, PLOS Biology, DOI 10.1371/journal.pbio.2005282.
- ARRIVE Guidelines 2.0, item 1b e sample size item 2.
- ICH E9(R1), *Estimands and Sensitivity Analysis in Clinical Trials*.
- NC3Rs Experimental Design Assistant, descrizione e pubblicazione metodologica.

## Conseguenze operative

- Il resolver resta un calcolatore di candidati scope-specific; il compiler aggiunge i gate per
  target-popolazione, estimando e allocazione senza fondere il livello di applicazione.
- UI e API devono mostrare il target e le domande di elicitazione prima di presentare l'output
  come handoff pronto.
- Gold e annotation guideline devono annotare separatamente fatti osservati, target inferenziale
  e conferma umana.
