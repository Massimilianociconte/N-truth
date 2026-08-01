# Architettura e invarianti PRD v3

## Flusso

```text
Experiment Bundle locale
   |
   v
ingest       manifest, checksum, MIME, ruoli file, limiti su input ostili
   |
   v
parsers      JATS/DOCX/PDF/CSV/XLSX/TXT + R/Python read-only -> Document IR
   |
   +--> baseline deterministica ---------------------------+
   |                                                        |
   +--> futuro parser AI vincolato -> candidate fact -------+
                                                            v
                                                      grafi alternativi
                                                            |
                                                            v
                                                conferma/correzione umana
                                                            |
                                                            v
design compiler -> grafo validato -> rules engine -> report positivo/alert/domande
                                                            |
                                                            v
                                      revisioni append-only ed export versionati
```

Il parser AI è centrale per la visione v1.0 ma assente dalla baseline operativa. Il
motore deterministico può essere sviluppato e verificato prima del training senza
ridurre la visione finale alla sola Track A.

## Moduli

| Package | Responsabilità |
|---|---|
| `ntruth.schemas` | Document IR, Experiment Bundle, grafo, fattori, estimandi, regole e report |
| `ntruth.ingest` | progetto locale, checksum, manifest e controlli di sicurezza |
| `ntruth.parsers` | byte → sezioni/tabelle/code artifact con coordinate; codice `never_execute` |
| `ntruth.extract` | baseline deterministica di candidate fact da testo e sample sheet |
| `ntruth.parser_ai` | contratto input/output, JSON Schema, adapter e validazione; nessun modello incluso |
| `ntruth.design` | target/estimando, elicitazione e handoff conservativo |
| `ntruth.graph` | merge delle fonti, alternative, conflitti e unità per scope |
| `ntruth.rules` | predicati e motore su grafo validato con trace |
| `ntruth.reporting` | percorso verde, alert, domande ed export leggibili/machine-readable |
| `ntruth.corrections` | JSON Patch validate, ledger, undo/redo e ricalcolo |
| `ntruth.governance` | autorizzazioni, privacy, snapshot corpus, anti-leakage e lineage |
| `ntruth.api` | API loopback, sessioni bounded, artefatti e UI locale |
| `ntruth.cli` | comandi locali |
| `ntruth.pipeline` | orchestrazione dei passaggi |

## Invarianti scientifici

1. L'unità sperimentale è derivata per fattore e contrasto; non esiste una label
   globale del paper.
2. `allocation_level` e `application_level` sono distinti. Il primo determina il
   candidato EU; il secondo descrive la procedura.
3. L'estimando minimo è separato dal target inferenziale e deve essere esplicito per
   sostenere un handoff completo.
4. `n_declared`, `n_allocated`, `n_analyzed`, `n_observational` e `n_independent` non
   sono alias.
5. Un'incertezza decisiva produce astensione o scenario condizionale con domanda.
6. Replicazione del disegno, dipendenza analitica e portata dell'inferenza generano
   classi di alert separate.
7. Un modello statistico può dichiarare clustering o gestire dipendenza; non crea
   replicazione del disegno.
8. Una dichiarazione dell'autore genera un candidato, non una prova di indipendenza.
9. La confidenza si applica ai fatti candidati; una conseguenza deterministica espone
   regola e premesse, non una probabilità propria.

## Invarianti di tracciabilità

1. Il Document IR conserva coordinate di testo, celle e code span.
2. Ogni candidate fact riferisce evidence span esistenti.
3. Il graph builder conserva alternative e conflitti; non sceglie silenziosamente.
4. Il rules engine legge il grafo validato, non interpreta il testo grezzo.
5. Il renderer non introduce fatti assenti dal JSON.
6. Una correzione crea una patch append-only; non cancella estrazione o revisione
   precedenti.
7. Ogni run e revisione è isolato e pubblicato atomicamente.
8. Gli artefatti restano `not_gold` finché un workflow umano separato non li promuove.

## Codice statistico

Gli script `.R`, `.r`, `.Rmd` e `.py` sono importati come testo e non vengono mai
eseguiti. Pattern come `(1|culture/well)` o grouping in una formula possono creare
`declared_clustering` con evidenza `STATISTICAL_CODE`. Non possono creare
`allocated_to`, `applied_to` o `randomized_at`: descrivono il modello dichiarato, non
il processo fisico di allocazione.

## Contratto parser AI

`ParserAIInput` separa documenti, tabelle, metadata e codice statistico.
`ParserAIOutput` accetta soltanto candidate fact, alternative, determinabilità e
domande. Non contiene un verdetto. La validazione controlla vocabolari, riferimenti,
coordinate, evidenze e versione del contratto prima dell'ingresso nel grafo.

L'esistenza di questo boundary non implica che un backend sia configurato o che siano
disponibili metriche ML.

## Persistenza, revisioni e concorrenza

`execute_analysis` pubblica una revisione iniziale in un run nuovo. Il riuso di un
progetto richiede opt-in esplicito. Le correzioni API vengono serializzate nella
sessione e ogni commit costruisce uno snapshot privato, scrive gli artefatti e lo rende
visibile con un rename atomico.

Checksum e versioni consentono di verificare contenuto, annotazioni e audit. La
licenza del codice non viene trasferita alle fonti incluse in un bundle o in un export.

## Governance e privacy

Gli usi `analyze`, `annotate`, `train`, `share` e `redistribute` sono autorizzazioni
separate. Un record assente, revocato, scaduto o non coerente con il checksum produce
un diniego fail-closed. Gli snapshot del corpus includono gruppi anti-leakage e lineage
di schema/parser/guideline/ontologia.

Lo scanner privacy crea finding stand-off e copie redatte separate. È assistivo. La
pipeline applicativa genera scan e readiness negata per default; API e CLI applicano i
gate immediatamente prima di valutare `share`/`redistribute`. L'esito riguarda gli
artefatti e checksum correnti e non esegue trasferimenti. Una chiamata di basso livello
senza Document IR non scansiona le fonti e non costituisce readiness.

## Limiti della baseline

- Nessun modello AI N-Truth è presente o addestrato.
- Segmentazione, estrazione e coreference rules-only non sono validate su un corpus
  reale.
- PDF senza testo estraibile/OCR degradato richiedono fallimento esplicito o una
  pipeline futura.
- Nessun agreement umano, human ceiling, calibrazione o external challenge è stato
  misurato.
- Le fixture sintetiche verificano contratti software, non validità scientifica.
- L'editor locale non sostituisce il workflow di doppia annotazione e adjudication.
