# Auxiliary training lane — status report 2026-08-28

> **SCOPE: LOCAL_AUXILIARY_ENGINEERING_ONLY (D1).** Questa lane vive in
> `~/Documents/N-truth-training-lane/` (fuori dal repository) e consuma solo
> l'export locale `LSC-SOURCEDATA-20260825` (SourceData v2.0.3) più corpora
> pubblici esterni licenziati. **Nessun numero di questa lane è citabile come
> validazione N-Truth, né autorizza il training primario**, che resta
> `HOLD_PENDING_REAL_ANCHOR` in [status-snapshot.md](status-snapshot.md).
> Il valore dichiarato è: pipeline di training ausiliaria collaudata, baseline
> ingegneristiche misurate, e terreno di prova per il giorno in cui il gold
> sarà disponibile.

## 1. Cosa è cambiato dal 27 agosto 2026

### Trainer ausiliario v4.1 (`train_tokencls_v4.py`)
- warm-start da checkpoint precedenti, LLRD, label smoothing, EMA pesi,
  FGM opzionale, token-mask opzionale, accumulo gradienti, LR floor.
- **Long-run safe**: checkpoint per epoca (`best.pt` + `ckpt_epochNNN.pt`),
  `trainer_state.pt` con ottimizzatore/scheduler/EMA per resume anti-crash
  (`--resume`), `--eval-only` per valutazioni senza training,
  `--rdrop` (R-Drop, spento di default), preflight `verify_lane.sh`.
- Encoder utilizzati: `answerdotai/ModernBERT-base`, `bert-base-uncased`,
  e (ratificati in sessione 2026-08-27, registro `RATIFICA-pesi-esterni-v4bio.md`)
  `almanach/ModernBERT-bio-base` e `thomas-sounack/BioClinical-ModernBERT-base`
  — usati SOLO come inizializzazione locale di specialisti ausiliari.

### Risultati misurati (test micro-F1, export locale v2.0.3)
| Configurazione | entity | roles |
|---|---|---|
| v3 baseline (warm-start, 3 ep) | 0.8184 | 0.7946 |
| bio-base fresh specialist | 0.8176 | 0.7936 |
| entity L384 (warm continuation, 6 ep) | 0.8207 | — |
| **ensemble intersezione (2 modelli, official units)** | **0.8222** | 0.7886* |

\* roles: l'ensemble vince nel protocollo span (+1,3pp) ma in unità ufficiali
resta sotto il baseline v3 per effetto della finestra comune di valutazione;
è un limite documentato, non un claim di vittoria.

Note metodologiche:
- l'ensemble è valutato con `ensemble_eval.py` (allineamento a livello di
  parola, protocollo finestra-comune); i token-F1 dei singoli modelli
  ricalcolati riproducono al quarto decimale i valori ufficiali (controllo di
  regressione della pipeline di valutazione).
- le configurazioni sono tra loro confrontabili; **nessuna** è confrontabile
  come evidenza scientifica N-Truth.

### Dati esterni (staging, non ancora merged nel training)
Tutto in `FLASH128:N-Truth-Datasets/external_corpora/20260827/` con
`PROVENANCE.md`, `RATIFICA-mapping-v21.md` (registro R) e
`leakage_screen_v1.json`:

- 16 corpora BioNER (pack MTL-Bioinformatics-2016) armonizzati allo schema
  v2.0.3 (`harmonize_externals.py`); mappature draft ratificate dal
  proprietario in sessione 2026-08-27.
- SciCap: 451.320 caption testuali deduplicate (10.829 bio-like) — pool
  UNLABELED per MLM adattivo/self-training.
- Biomed-Enriched: 6 shard parquet (~7 GB) per continued-pretraining locale.
- EBM-PICO: loader BigBIO scaricato (proxy debole per i ruoli).
- `screen_leakage.py` (k=8 shingle fingerprint vs 74k record locali):
  205 righe BioNER e 474 caption SciCap bloccate.
- **v2.1.0 costruito** (`build_v21.py`): train 236.121 righe
  (59.350 SourceData + 176.771 esterne; −205 bloccate), validation/test
  copiati byte-identici. Politica: esterni SOLO nel train.

### Valutato e scartato per ora
BioImage Archive (EBI): immagini + metadati REMBI, licenze CC0/CC-BY, ma zero
etichette NER/ruoli e prosa di metodo non caption → registrato per l'eventuale
fase multimodale futura, non scaricato.

## 2. Stato della coda di training al 2026-08-28 00:32

La coda notturna `run_sat_night2.sh` è stata **interrotta da spegnimento
manuale del Mac** (overload riferito dal proprietario). Stato:

| Fase | Stato |
|---|---|
| entity L384 | **COMPLETATA** — test 0.8207 (sopra) |
| roles L384 | **INTERRIPTTA** dopo 1 epoca (val 0.824); resumibile con `--resume` da `trainer_state.pt` |
| rdrop entity / rdrop roles | non avviate |
| LARGE (396M, tetto 6 ep) | non avviata |
| lane v2.1.0 multi-corpus | pianificata, richiede coda libera |

Ripresa: solo su comando esplicito del proprietario.

## 3. Cosa NON cambia (confini invariati)

- `Scientific validation: NOT_STARTED` — invariato.
- `Training (primario): HOLD_PENDING_REAL_ANCHOR` — invariato.
- Reality Gate: decisione corrente `HOLD` — invariata.
- Nessun artefatto della lane entra nel repository o nei claim normativi;
  i dataset fisici restano su volume locale esterno, non in Git.

---

## 4. CHIUSURA CAMPAGNA (2026-08-29, ore ~22:40) — decisione proprietario

Tutti i processi di training sono stati **fermati su richiesta del proprietario**
("chiudiamo tutti i processi attivi allo stato migliore attuale"). Stato
congelato con misure finali sul test set (SourceData v2.0.3, micro-F1):

### Entity
| Configurazione | test | nota |
|---|---|---|
| v3 baseline (bert-warm, 3 ep) | 0.8184 | riferimento storico |
| bio-base fresh | 0.8176 | parità con baseline |
| bio-base L384 (warm 6 ep) | 0.8207 | miglior SINGOLO |
| **ensemble intersezione v3+bio** | **0.8222** | **config. di produzione ausiliaria** (solo lane esterna; mai validazione, mai sblocco training — vedi SCOPE sopra) |
| R-Drop (ep4, val 0.8280) | 0.8193 | interrotto: epoche 4-8h su MPS, ROI insufficiente |
| v2.1.0 esterni (3 ep, 236k righe) | 0.8126 | **trasferimento negativo**, archiviato |
| LARGE 396M | n/d | archiviata: ~13h senza completare 1 epoca su MPS |

### Roles
| Configurazione | test |
|---|---|
| v3 baseline | 0.7946 |
| bio-base L384 (resume, 5 ep) | **0.7966** — miglior roles |
| ensemble (protocollo span) | +1,3pp sui soli span; in unità ufficiali 0.7886 (limite finestra, documentato) |
| R-Drop roles | non eseguito (skip, costi/benefici sfavorevoli) |

### Conclusioni di campagna (per il registro)
1. Config ausiliaria di produzione (lane esterna `N-truth-training-lane`,
   assistenza pre-estrazione soltanto — non validazione scientifica,
   non sblocco del training primario):
   **entity = ensemble intersezione
   (v3 + bio-base), test 0.8222; roles = bio-base L384, test 0.7966.**
2. Il tetto del dataset v2.0.3 è raggiunto: modelli molto diversi convergono
   nella stessa fascia; il valore residuo dipende da dati nuovi, non da epoche.
3. Esternal BioNER su SourceData: trasferimento negativo misurato — non insistere.
4. R-Drop/LARGE: tecniche testate, esito documentato, non ripetere su questo hardware.
5. Artefatti di ripresa lasciati a terra (resumibili con `--resume`):
   `runs/sat-entity-d1-v4bio-rdrop/trainer_state.pt` (ep 5 incompleta),
   checkpoints per epoca in ogni run dir.

Nessun claim di validazione scientifica N-Truth deriva da questa campagna;
`Scientific validation: NOT_STARTED` e `Training (primario): HOLD` restano invariati.
