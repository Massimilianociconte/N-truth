# Synthetic Task Use Matrix v6.1

**Stato:** specifica normativa per la progettazione degli esperimenti; le bande
indicate sono ipotesi iniziali da confrontare sul development reale, non quote di
produzione, soglie di release o prove di generalizzazione.

## Regole di interpretazione

- Le percentuali descrivono la composizione task-specifica degli esempi di training
  dopo deduplica e raggruppamento per famiglia. Non si applicano a validation, TEST o
  External Challenge.
- Il limite superiore sintetico è una banda sperimentale, non un obiettivo da
  raggiungere. La miscela viene scelta mediante confronto real-only, synthetic-only e
  hybrid sullo stesso development reale congelato.
- `real gold minimo` significa esempi umani autorizzati e double-reviewed o
  adjudicated sui campi decisivi. Silver e synthetic non soddisfano questo minimo.
- Ogni task conserva validation reale. TEST ed External Challenge sono sempre 100%
  reali, training-ineligible e inaccessibili al generator.
- Il sintetico può migliorare copertura, counterfactual e deliberate practice; non
  dimostra realismo linguistico, trasferimento tra laboratori o generalizzazione.

## Bande iniziali per classe d'uso

| Classe | Synthetic nel training task-specifico | Real gold minimo | Uso |
|---|---:|---:|---|
| `SYNTHETIC_HEAVY` | 50-80% | almeno 20% | Strutture esplicite, tassonomie chiuse, conteggi e perturbazioni controllabili. |
| `HYBRID` | 20-60% | almeno 40% | Relazioni o eventi simulabili, ma sensibili allo stile e alla documentazione reale. |
| `REAL_HEAVY` | 0-30% | almeno 70% | Inferenze decisive, implicite o dipendenti da conoscenza procedurale e biologica. |
| `REAL_ONLY_EVALUATION` | 0% | 100% | Test finale, External Challenge, metriche e claim di release. |

Le bande possono essere ristrette verso il reale, ma non ampliate oltre il massimo
senza protocol amendment, audit di shortcut e nuova mixture search. Un task con meno
del real gold minimo resta research-only anche se le metriche sintetiche sono elevate.

## Matrice P0/P1/P2

| Livello | Task | Classe | Ruolo sintetico ammesso | Vincolo reale e valutazione |
|---|---|---|---|---|
| P0 | Section routing e Methods/Caption detection | `SYNTHETIC_HEAVY` | Template, documenti negativi, ordine delle sezioni, rumore e missing sections. | Development e test reali per stile editoriale, lingua e source shift. |
| P0 | Entity extraction | `SYNTHETIC_HEAVY` | Copertura lessicale controllata, rare entity, spelling e minimal pairs. | Real gold necessario per boundary, sinonimia e distribuzione autentica. |
| P0 | Count e quantifier extraction | `SYNTHETIC_HEAVY` | EXACT/RANGE/BOUND/UNKNOWN, unità, tabelle e counterfactual numerici. | Test reale obbligatorio per layout, omissioni e numeri impliciti. |
| P0 | Relazioni esplicite `nested_in`/`derived_from` | `SYNTHETIC_HEAVY` | Grafi noti, frasi esplicite, inversioni e negative examples. | Real gold per variazione linguistica e cross-sentence relations. |
| P0 | Factor, levels ed endpoint espliciti | `SYNTHETIC_HEAVY` | Combinazioni controllate e anti-shortcut su nomi/ordine. | Valutazione reale per nomenclatura di dominio. |
| P0 | Allocation/application esplicite | `HYBRID` | Eventi espliciti, minimal pair allocate/apply e confondimenti controllati. | Almeno 40% real gold; scoring separato allocation/application. |
| P0 | Contradiction detection di base | `HYBRID` | Conflitti generati con provenance nota e singola mutazione. | Conflitti sottili e multi-fonte valutati soltanto su casi reali. |
| P1 | Annidamento cross-documento | `HYBRID` | Omissioni, ID alias, caption/sample-sheet merge e artifact dropout. | Development reale multi-artefatto obbligatorio. |
| P1 | Procedural events e ordine temporale | `HYBRID` | Timeline graph-first, perturbazioni split/pool/treatment e casi impossibili. | Real gold per omissioni, ordine implicito e protocolli autentici. |
| P1 | Alternative graph semplici | `HYBRID` | Ambiguità controllate e domande discriminanti note. | Scenario-set accuracy e usefulness misurate su casi reali. |
| P1 | Decisive coreference | `REAL_HEAVY` | Counterfactual, distractor e deliberate practice sugli errori reali. | Almeno 70% real gold; evaluation reale separata per antecedente decisivo. |
| P1 | Allocation implicita | `REAL_HEAVY` | Solo augmentation da grafi revisionati e perturbazioni minimali. | Nessun claim senza real gold, human ceiling e review time. |
| P1 | Indipendenza biologica/operativa | `REAL_HEAVY` | Negative examples e scenari condizionali; mai label automatica da parole chiave. | Conferma wet-lab e biostatistica; synthetic non chiude il predicate. |
| P1 | Contraddizioni sottili | `REAL_HEAVY` | Deliberate practice su tassonomia di errori reali senza copiare TEST. | Valutazione esclusivamente su conflitti reali custoditi. |
| P1 | Imaging Core | `HYBRID` | Metadata, gerarchie e missingness controllati; immagini sintetiche solo per task autorizzati. | Validazione reale per pipeline, unità e correlazioni da acquisizione. |
| P2 | Estimand e inference target impliciti | `REAL_HEAVY` | Parafrasi e controfattuali supervisionati; output candidato o astensione. | Gold metodologico reale e human confirmation obbligatori. |
| P2 | Split-plot e multifattore complesso | `REAL_HEAVY` | Rare topology e invariant stress test. | Valutazione reale per ogni profilo supportato. |
| P2 | Question generation free-form | `HYBRID` | Diversificazione controllata da scenari e answer keys. | Utility, ridondanza e output-changing misurati da esperti su casi reali. |
| P2 | Multi-graph calibration e OOD | `REAL_HEAVY` | Synthetic solo per stress/ablation e coverage nota. | Calibration, risk-coverage e threshold selezionati su validation reale. |
| Tutti | External Challenge e metriche di release | `REAL_ONLY_EVALUATION` | Vietato. | 100% reale, unseen, custodito, preregistrato e training-ineligible. |

## Promotion e stop rules

Un task può avanzare solo se:

1. la baseline real-only è stata eseguita sul medesimo snapshot;
2. la miscela hybrid migliora decisive metric o riduce il tempo di revisione;
3. calibrazione e critical-error rate non peggiorano;
4. non emerge shortcut sensitivity verso template, renderer o generator family;
5. gli intervalli bootstrap e la prevalenza delle classi sono riportati;
6. il miglioramento persiste su almeno un set reale non usato nella mixture search.

Se synthetic-only supera hybrid sul development ma non sul real holdout, il lotto è
classificato come shortcut-prone e viene ristretto, rigenerato o escluso.
