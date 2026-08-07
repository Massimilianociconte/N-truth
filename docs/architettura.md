# Architettura v6

## Due train coordinati

N-Truth separa il valore deterministico dal rischio di ricerca del parser AI.

| Train | Responsabilita | Stato conservativo |
|---|---|---|
| Train D | Ingest locale D0, schema, grafo, regole, determinabilita, hard verifier, correzioni e report | Implementazione software disponibile; revisione scientifica ed external validation non completate |
| Train A | Parser a stadi, corpus, training, calibrazione e validazione esterna | Contratti e tooling preparatorio disponibili; nessun modello N-Truth addestrato/validato |

La visione completa richiede entrambi i train e revisione umana. Train A propone fatti
candidati; non sostituisce il compilatore deterministico o il verificatore hard.

## Flusso Train D corrente

```text
file locali
  -> safety gate e release profile
  -> progetto: manifest + copie sorgente + blob SHA-256 + SQLite
  -> Document IR con coordinate
  -> segmentazione in ExperimentBlock
  -> estrazione deterministica
  -> candidate graph
  -> preflight hard degli invarianti
       -> se invalido: INVALID_GRAPH, stop regole, report dell'errore
       -> se valido: resolver di unita + evidence floor + rules engine
  -> compilatore del disegno + DeterminabilityState
  -> output policy
  -> hard verifier finale
  -> report ed export versionati
```

Una correzione umana viene applicata come patch append-only a una revisione nota; il
blocco corretto viene ricalcolato senza reinterpretare o modificare la fonte. Undo e
redo cambiano la revisione attiva mantenendo intatta la storia.

Nel runtime API corrente il registro di sessione e memory-bounded. Le revisioni di
report e gli audit di correzione vengono pubblicati su file in modo atomico, ma non va
dedotta da questo una sessione collaborativa persistente o ripristinabile dopo il
riavvio del processo.

Il `SampleSheetSpec` v6 ha generatore e validatore CLI dedicati. La validazione
canonica va eseguita prima dell'analisi generale del CSV; non e ancora un gate
automatico per ogni CSV importato.

## Flusso contrattuale Train A

```text
DocumentRouteResult
  -> EvidenceExtractionResult / EntityCountResult / ProceduralEventResult
  -> CandidateGraphSet (senza verdict e determinability)
  -> hard verifier sempre / semantic verifier solo se invocato
  -> HumanRevisionPatch
  -> grafo validato o scenario esplicitamente condizionale
  -> RuleResult / QuestionRecord
  -> ReportBundle
```

Questa e una separazione di responsabilita normativa. Gli schema staged esistono, ma
non rappresentano ancora un parser AI addestrato ne un'orchestrazione scientificamente
validata di tutte le fasi.

## Moduli

| Package | Responsabilita |
|---|---|
| `ntruth.schemas` | Document IR, manifest, Experiment Graph, conteggi, regole e report |
| `ntruth.ingest` | Progetto locale, manifest, checksum, profilo input e controlli di sicurezza |
| `ntruth.storage` | SQLite locale, migrazioni, revisioni/audit e blob store content-addressed |
| `ntruth.parsers` | Byte -> testo, sezioni, tabelle e code artifact con coordinate; codice `never_execute` |
| `ntruth.sample_sheet` | Schema v6, generazione, validazione e I/O CSV sicuro |
| `ntruth.prospective` | Compiler D0 e contratti separati planned/executed con deviazioni tipizzate |
| `ntruth.extract` | Segmentazione e baseline deterministica di candidate fact |
| `ntruth.parser_ai` | Contratti staged v6, compatibilita v2 e validazione; nessun peso incluso |
| `ntruth.runtime_resources` | Profili benchmark-derived, scheduling sequenziale, chunking, cache, fallback e telemetria |
| `ntruth.graph` | Costruzione, validazione, unita per scope e determinabilita |
| `ntruth.verifier` | Verifica hard e matrice normativa degli output |
| `ntruth.rules` | Ruleset versionati, predicati ed esecuzione con trace |
| `ntruth.design` | Target/estimando, elicitazione e compilation del disegno |
| `ntruth.corrections` | JSON Patch validate, ledger, undo/redo, audit e ricalcolo |
| `ntruth.reporting` | Output positivo, JSON/YAML/HTML, graph e metadati di export |
| `ntruth.governance` | Autorizzazioni, privacy, lineage, snapshot e split anti-leakage |
| `ntruth.training` | Gold target contract, preparazione e tooling MLX futuro |
| `ntruth.api` | API locale loopback e sessioni bounded |
| `ntruth.cli` | Comandi locali e messaggi di errore espliciti |
| `ntruth.pipeline` | Orchestrazione deterministica Train D |

## Persistenza locale

Ogni progetto creato dalla pipeline contiene:

```text
project/
├── manifest.json
├── sources/
│   └── <copie locali registrate>
├── blobs/
│   └── sha256/<prime-2-cifre>/<sha256-completo>
└── ntruth.sqlite3
```

`sources/` e mantenuta per compatibilita e accesso locale. Il blob store e immutabile,
deduplica per contenuto, pubblica atomicamente e verifica digest e dimensione. SQLite
registra progetti, blob, collegamenti progetto-blob, revisioni, sessioni, run, eventi
di audit e migrazioni. Usa foreign key, WAL, `synchronous=FULL`, transazioni e
savepoint; trigger impediscono update/delete di revisioni ed eventi di audit.

L'apertura di un workspace precedente esegue un backfill non distruttivo nel blob
store soltanto quando la copia legacy corrisponde al checksum. Il comando
`ntruth verify` ricontrolla copia sorgente e blob.

SQLite e il backend locale iniziale. PostgreSQL o un graph database non sono
funzionalita collaborative dichiarate come implementate.

## Trust boundary degli input

Il core non apre indiscriminatamente ogni file:

- D0 accetta TXT, Markdown e CSV semplice;
- formati complessi richiedono `extended_experimental`;
- estensione e firma/media type devono essere coerenti;
- symlink, traversal, macro e archivi/input oltre i limiti sono rifiutati;
- JATS/XML non puo contenere `DOCTYPE` o `ENTITY`;
- script statistici sono dati testuali e non vengono mai eseguiti;
- il contenuto di una fonte e sempre dato, mai istruzione per il sistema.

Il profilo e persistito nel manifest. Un workspace non puo essere riaperto con un
profilo differente senza creare un progetto separato.

## Invarianti scientifici

1. L'unita sperimentale e derivata per fattore, contrasto ed endpoint, non per paper.
2. Allocazione, applicazione e indipendenza operativa sono concetti distinti.
3. Un `independent_n` richiede indipendenza operativa confermata e uno scope valido.
4. Conteggi, quantificatori, lifecycle ed esclusioni non vengono compressi in un solo
   `n`.
5. Un'incertezza decisiva produce astensione, alternative o rami condizionali.
6. Replicazione del disegno, dipendenza analitica e portata inferenziale restano tre
   classi separate.
7. Statistical code e author assertion non provano da soli allocazione o
   indipendenza.
8. Solo la matrice di determinabilita autorizza un valore singolo di EU/n.

## Invarianti di provenance e correzione

1. Document IR conserva file, checksum e coordinate di testo/cella/codice.
2. Candidate fact e relazioni puntano a evidenze esistenti.
3. Alternative e conflitti non vengono risolti silenziosamente.
4. Il rules engine non interpreta testo grezzo.
5. Il renderer non introduce fatti assenti dagli artefatti strutturati.
6. Correzioni, revisioni ed audit sono append-only e verificabili per checksum; ogni
   evento registra ruolo dell'attore e timestamp con fuso, senza identita personale.
7. Un artefatto resta `not_gold` fino a doppia annotazione/adjudication prevista dal
   protocollo.
8. Parser Gold e Derivation Gold restano separati.
9. La Evidence View desktop e attualmente consultiva: il backend accetta patch agli
   span solo se coordinate, testo, sezione e cella coincidono con il Document IR
   immutabile; l'editor visuale dei locator appartiene al gate A1.

## Governance e rete

Le autorizzazioni `analyze`, `annotate`, `train`, `share` e `redistribute` sono
separate. Un record mancante, scaduto, revocato o incoerente con il checksum nega
l'azione governata. Lo scanner privacy e assistivo e produce finding stand-off;
`distribution-check` valuta un gate e non trasferisce file.

La API baseline e single-user, senza autenticazione e destinata al loopback. Non deve
essere pubblicata su `0.0.0.0`, reverse proxy, LAN o Internet.

## Limiti correnti

- Nessun modello AI N-Truth addestrato, calibrato o pubblicato e disponibile.
- Segmentazione, estrazione e coreference rules-only non sono validate su un corpus
  reale rappresentativo.
- Il semantic verifier e un contratto opzionale, non un runtime scientificamente
  validato.
- Il Runtime Resource Manager e implementato come confine backend-agnostic ma non e
  ancora collegato al runner MLX, e manca un artifact benchmark reale sul Mac target.
- Il record prospettico planned/executed e validato in memoria ma non e ancora
  persistito in SQLite ne esposto dal wizard/API.
- Il profilo esteso abilita sperimentazione, non supporto stabile.
- Nessun human ceiling, agreement, external challenge o studio utente completato e
  dichiarato.
- Fixture sintetiche e test software verificano implementazione e contratti, non la
  validita scientifica delle conclusioni.

Per i confini operativi vedere [Core Profile D0](core-profile-d0.md),
[SampleSheetSpec v6](sample-sheet-v6.md) e
[contratto parser/verifier](parser-ai-contract.md).
