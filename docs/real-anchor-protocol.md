# Real Anchor Protocol v0.1-draft

**Stato:** bozza preregistrabile, **non approvata, non eseguita**. Non modifica
alcun gate: il training primario resta `HOLD_PENDING_REAL_ANCHOR` e la
validazione scientifica resta `NOT_STARTED` finché i gate canonici
(`packages/ntruth/reality_gate/v8.py`, Contract Packages, team-evaluation
freeze con quattro attestazioni) non sono soddisfatti con evidenza reale.
Vedi `docs/status-snapshot.md`, `docs/derivation-gold-protocol.md`,
`docs/annotation-guideline-v0.1.md`.

## 1. Definizione

Il **Real Anchor** è il minimo corpus reale annotato da esperti che ancora
l'intero programma N-Truth al mondo reale. Senza di esso, ogni numero su
sintetico (incluso p0-alpha) resta diagnostica ingegneristica e non può
sostenere claim scientifici, confronti SOTA o promozioni di qualifica.

## 2. Composizione minima

1. **Sorgenti reali protette** con manifest indipendente (provenienza, licenza,
   versione/revisione, hash), registrate in custodia (`data_use` /
   External Challenge lifecycle). Niente identità reviewer nei record.
2. **Parser Gold pilota**: ExperimentBlock con evidence span, unità
   (biologica / sperimentale / osservazionale / analitica), fattori, livelli,
   gruppi, endpoint, conteggi con lifecycle, relazioni e coreference —
   secondo `docs/annotation-guideline-v0.1.md` congelata.
3. **Derivation Gold pilota**: casi con grafo confermato e soli output attesi
   deterministici (determinabilità, unità sperimentale, `independent_n` per
   fattore/contrasto/scope, rule result, proof trace, astensioni) — secondo
   `docs/derivation-gold-protocol.md`.

## 3. Doppia annotazione e adjudication

- Doppia annotazione indipendente obbligatoria per: unità sperimentale,
  repliche bio vs tecniche, assignment/allocation level, determinabilità,
  `independent_n` per contrasto/scope, astensioni.
- Single-review ammesso solo per: metadati bibliografici, span tipografici
  non controversi,alikvotature puramente descrittive — mai per verdict.
- Adjudication da biostatistico con verbale; conflitti conservati nel record
  (mai schiacciati a maggioranza silenziosa); casi ambigui e non
  determinabili restano classi esplicite, non esclusioni post-hoc.
- IAA preregistrata prima del pilot: accordo su unità ExperimentBlock con
  metrica per classificazione gerarchica + span overlap; soglie di
  accettazione fissate prima di misurare, mai adattate per far passare il set.

## 4. Split senza leakage (train / dev / test)

- Split per **gruppo/autore/dataset/studio**: mai blocchi dello stesso
  paper, studio longitudinale o versioni multiple dello stesso paper su lati
  diversi dello split.
- Il test resta intatto e cieco: nessun training, tuning, prompt engineering
  o selezione modello su di esso; DEV guida LoRA/prompt, TEST si apre una
  sola volta per la valutazione registrata.
- Tutto il futuro sintetico generato dallo stesso template condivide il
  leakage-group del seme/famiglia: mai usato come prova di generalizzazione
  reale (solo smoke di formato, coverage, stress, counterfactual).

## 5. Soglie di sufficienza (da ratificare, non da improvvisare)

| Fase | Ingresso minimo |
|---|---|
| Apertura training reale | Real Anchor congelato + guideline/schema congelati + IAA misurata sopra soglia preregistrata + gate TRAIN risolto con evidenza |
| Pilot interno / calibrazione | + team-evaluation freeze con quattro attestazioni + metrica semantica (F1/prec/rec su gold, mai JSON/schema-rate) con CI bootstrap |
| Validazione AI | + eval cieca su TEST + robustness (seed) + calibrazione/temperatura su validation + analisi errori con tassonomia |
| Validazione esterna | + corpus External Challenge custodito + protocollo pubblicato + ladder percorsa senza salti fino a `VERIFIED` |
| First scientific release | + `VERIFIED+EXTERNAL_VALIDATED`, mai prima |

## 6. Cosa questo protocollo NON autorizza

- Nessun training sostanziale su p0-alpha o altri sintetici.
- Nessuna promozione `PARTIALLY_VERIFIED` → `VERIFIED` senza ladder completa.
- Nessuna lettura di 100% JSON/schema come successo semantico.
- Nessun confronto o claim SOTA.
- Nessuna qualifica di confidence/OOD senza dati pilota.

## 7. Prossimo passo concreto

Congelare guideline v0.1 → v1.0 con owner (annotation lead, wet-lab
reviewer, adjudicator biostatistico), preregistrare IAA e split, raccogliere
il primo pacchetto di blocchi reali sotto custodia — e solo allora chiedere
la riapertura del gate TRAIN con evidenza, mai con promesse.
