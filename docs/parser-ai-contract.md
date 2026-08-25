# Contratto parser AI

Questo documento copre tre superfici distinte del package `ntruth.parser_ai`, che
non include pesi e non effettua chiamate di rete:

1. il **contratto canonico PRD v8** (`ParserCandidateOutput` / `GoldParserTarget`),
   descritto in
   [prd-v8-data-training-evaluation-boundary.md](prd-v8-data-training-evaluation-boundary.md);
2. la **superficie staged** a dieci fasi, ancora presente nel codice come confine
   ingegneristico candidate-only;
3. il **contratto legacy v2/PRD v3**, conservato solo per compatibilita.

> **HISTORICAL_NON_NORMATIVE.** Le sezioni sul contratto v2/PRD v3 non sono una guida
> corrente. Il parser canonico PRD v8 è `ParserCandidateOutput`, non include
> `determinability`, e il target supervisionato è `GoldParserTarget`. Vedere
> [prd-v8-data-training-evaluation-boundary.md](prd-v8-data-training-evaluation-boundary.md).

## Superficie staged: le dieci fasi

Il package definisce contratti Pydantic versionati per gli artefatti del parser a
stadi. La presenza degli schema e della pipeline MLX locale non equivale a un modello
addestrato, calibrato o scientificamente validato. I dieci modelli di fase stabiliscono
il confine che un backend deve rispettare; non tutti sono orchestrati come un'unica
esecuzione AI end-to-end.

La versione corrente del contratto staged e `1.0.0`.

| Ordine | `stage` | Modello Pydantic | Responsabilita dell'artefatto |
|---:|---|---|---|
| 1 | `document_route` | `DocumentRouteResult` | Route per file, parser, MIME, lingua e supporto |
| 2 | `evidence_extraction` | `EvidenceExtractionResult` | Evidence span e copertura dei chunk |
| 3 | `entity_count` | `EntityCountResult` | Entita e count candidati con quantificatore/scope |
| 4 | `procedural_event` | `ProceduralEventResult` | Eventi procedurali, soggetti e ordine relativo |
| 5 | `candidate_graph_set` | `CandidateGraphSet` | Fatti del grafo candidato, alternative e missing facts |
| 6 | `verifier` | `VerifierResult` | Check hard obbligatori e, solo se invocati, check semantici |
| 7 | `human_revision_patch` | `HumanRevisionPatch` | Patch JSON umana/adjudicata con checksum base e rationale |
| 8 | `rule_result` | `RuleResult` | Applicazioni deterministiche del ruleset e riferimenti ai fatti derivati |
| 9 | `question_record` | `QuestionRecord` | Domanda discriminante con almeno due scenari |
| 10 | `report_bundle` | `ReportBundle` | Manifest degli artefatti di report e relativi checksum |

### Envelope comune

Ogni sottoclasse di `ParserStageResult` contiene:

- `schema_version` e `result_id`;
- `stage`, fissato dal tipo concreto;
- `status`: `complete`, `partial` o `failed`;
- `provenance` tipizzata;
- tuple `errors` e `warnings` tipizzate.

Gli stati hanno invarianti eseguibili:

- `complete` non ammette errori;
- `partial` richiede almeno un errore o warning;
- `failed` richiede almeno un errore;
- `provenance.stage` deve coincidere con `stage`;
- gli ID di errori, warning e record interni devono essere univoci dove previsto.

`StageProvenance` registra `stage_run_id`, autorita (`deterministic`, `model`, `user`
o `adjudication`), producer/versione, artifact ID e checksum di input, risultati
genitori e, quando disponibili, ruolo dell'attore e timestamp. I checksum dichiarati
sono SHA-256 lowercase.

Per un output `authority=model`, questi campi non sono autorevoli perché provengono
dal testo generato. `validate_candidate_graph_pair()` li sostituisce sempre con una
provenance host-owned: checksum e artifact ID derivati dal `ParserAIInput`, producer e
versione canonici, ID di stage content-addressed, nessun parent umano, ruolo o
timestamp. Anche `source_result_ids` viene azzerato. La proiezione del Parser Gold
rimuove prima ogni lineage di submission/adjudication, così il target non insegna al
modello identità o autorità umane.

La tassonomia minima degli errori comprende:

- `UNSUPPORTED_FORMAT`;
- `CHUNK_COVERAGE_INCOMPLETE`;
- `MISSING_REQUIRED_EVIDENCE`;
- `AMBIGUOUS_COREFERENCE`;
- `CONFLICTING_SOURCES`;
- `INVALID_COUNT_INVARIANT`;
- `UNSUPPORTED_DESIGN_PROFILE`;
- `VERIFIER_DISAGREEMENT`.

I warning distinguono inoltre input degradato, fallback e informazione non riportata.
Un backend non deve comprimere un errore strutturato in testo libero o ometterlo per
presentare lo stage come completo.

Ogni classe puo esportare il proprio JSON Schema con il metodo Pydantic
`model_json_schema()`. La funzione storica `parser_ai_json_schemas()` restituisce
soltanto la coppia legacy `ParserAIInput`/`ParserAIOutput`, non l'insieme dei dieci
schema staged.

### CandidateGraphSet: candidate-only

`CandidateGraphSet` puo contenere:

- blocchi sperimentali ed evidence span;
- nodi e archi candidati;
- fattori, endpoint, contrasti ed estimandi candidati;
- count con quantificatore e scope;
- indipendenza operativa candidata ed eventi procedurali;
- alternative, missing facts e copertura dei chunk.

Non contiene `verdict` ne `determinability`. I modelli sono `extra=forbid`, quindi un
backend non puo aggiungere tali campi. Determinabilita, unita sperimentale, valore
pubblicabile di `n`, alert e conseguenze del ruleset sono derivazioni deterministiche
successive.

Non esiste intenzionalmente una promozione automatica da `CandidateGraphSet.alternatives`
al contratto core `PlausibleGraphSet`. Le alternative del parser contengono riferimenti
a nodi e archi candidati, ma non dimostrano da sole compatibilita scientifica, conseguenze
scope-aware o una domanda discriminante auditabile. La materializzazione core richiede
almeno due grafi distinti validati dall'hard verifier, conseguenze evidence-linked, una
`Question` decisiva e provenance non-`model`; soltanto quel record puo autorizzare lo
stato `MULTIPLE_PLAUSIBLE_GRAPHS`. Un adapter deve quindi essere una fase
esplicita di verifica/conferma, non una conversione di schema.

Il contratto staged applica invarianti referenziali esplicite, ma non sostituisce il
verificatore hard. Gli ID sono univoci entro la rispettiva collezione; ogni candidate
fact deve puntare a evidence span presenti; i riferimenti a block e gli ID richiamati
da edge, contrast, estimand, count, independence, event e alternative devono esistere.
Gli endpoint di un edge e i factor/endpoint/contrast di un estimand devono inoltre
appartenere allo stesso Experiment Block del record che li usa. Nel confronto con
`ParserAIInput`, `validate_candidate_graph_pair()` verifica file, coordinate, celle,
artefatti di codice e l'eventuale `section_id` rispetto al documento sorgente.

Ogni `ChunkCoverageRecord` deve classificare tutti gli indici tra `0` e
`total_chunks - 1` come `processed` oppure `failed`, senza buchi o sovrapposizioni.
Un grafo `complete` deve coprire esattamente tutti i file del `ParserAIInput` e non può
avere chunk falliti; uno stato incompleto deve riportare
`CHUNK_COVERAGE_INCOMPLETE` come issue tipizzata.

Compatibilita scientifica dei tipi, timeline, evidence anchor richiesti e altre
invarianti di release restano responsabilita del verificatore hard e
dell'orchestrazione, non del solo JSON Schema. Una confidence resta attributo del fatto
candidato e non diventa probabilita di una conseguenza deterministica.

### Verificatore hard e verificatore semantico

Il verificatore hard e sempre attivo nel runtime deterministico. Controlla almeno:

1. integrita referenziale e invarianti del grafo;
2. coerenza dell'indipendenza operativa;
3. scope e lifecycle dei conteggi;
4. matrice `DeterminabilityState -> output`.

Se il preflight trova una violazione bloccante, il blocco diventa `INVALID_GRAPH`, le
regole non vengono eseguite e il problema resta nel report. Dopo la derivazione della
determinabilita, la output policy sopprime valori non autorizzati e il verificatore
hard controlla nuovamente il blocco.

Nel contratto staged, un `VerifierResult` non fallito deve includere almeno un hard
check. `hard_verifier_passed` deve coincidere con gli esiti dei check hard;
`semantic_verifier_invoked` e vero soltanto quando sono presenti check semantici; gli
insiemi di grafi accettati e rifiutati devono essere disgiunti.

Il verificatore semantico e una capacita condizionale del contratto, non un runtime
scientificamente validato oggi. Quando verra implementato potra rilevare discrepanze
semantiche o chiedere revisione, ma non potra annullare un'invariante hard o
autorizzare un output vietato.

### Determinabilita e output

I sette stati canonici sono:

| Stato | Output numerico autorizzato |
|---|---|
| `DETERMINATE` | Singola unita sperimentale e singolo `independent_n` |
| `CONDITIONALLY_DETERMINATE` | Valori soltanto dentro rami espliciti |
| `MULTIPLE_PLAUSIBLE_GRAPHS` | Nessun valore unico; conservare le alternative |
| `INSUFFICIENT_INFORMATION` | Nessun valore unico; reporting gap e domanda |
| `CONFLICTING_INFORMATION` | Nessun valore unico; conservare il conflitto |
| `INVALID_GRAPH` | Errori e patch richiesta; nessun verdetto scientifico |
| `OUT_OF_SCOPE` | Solo riepilogo strutturale; nessun claim di release |

La confidence del parser e l'esito di un verificatore semantico non possono
autorizzare un singolo `n` in uno stato che lo vieta.

### Parser Gold e Derivation Gold

I due livelli devono restare separati per attribuire correttamente gli errori:

| Artefatto | Mapping | Contenuto | Stato nel repository |
|---|---|---|---|
| Parser Gold | documenti -> grafo | Evidence span, fatti e relazioni adjudicati in un `CandidateGraphSet` candidate-only | Contratto `GoldParserTarget` implementato; corpus reale non raccolto |
| Derivation Gold | grafo confermato -> conseguenze | Determinabilita, EU/n per scope, rule result, domande e proof trace attesi | Protocollo/artifact distinto non popolato e non approvato con esperti |

`GoldParserTarget` richiede almeno due submission sorgenti, una comparison per ogni
submission, rationale e ruoli di adjudication, `status=complete` e provenance con
autorita `adjudication`. Il tipo impedisce di chiamare gold una singola proposta del
modello; non prova che esista gia un corpus adjudicato.

Fixture sintetiche, expected output di test e smoke training non sono gold umano. Non
devono alimentare metriche scientifiche, calibrazione o claim di baseline reale.

### Gate di training

Nessun training scientifico e dichiarato completato. Prima di selezionare o
ottimizzare un modello servono almeno ruleset e profili revisionati, Derivation
Gold confermato, Parser Gold autorizzato, split per bundle/laboratorio, validation e
test congelati, baseline vincolata allo schema e protocolli di calibrazione/external
challenge. I componenti MLX presenti servono a rendere riproducibile il lavoro futuro,
non a superare questi gate; nel repository v8 la decisione corrente e `HOLD` e la
Reality Gate non autorizza l'accesso ai dati protetti.

## Contratto legacy v2 (PRD v3)

Questa sezione descrive il confine stabile previsto dal PRD scientifico v3,
sezione 13. La corsia opzionale `ntruth.training` usa questi stessi modelli Pydantic per
preparazione, QLoRA e inferenza MLX locale; la CLI/API/UI deterministica non la attiva
automaticamente.

### Input

`ParserAIInput` usa `contract_version = 2.0.0` e separa esplicitamente:

- `documents`: testo e sezioni con file ID, checksum e coordinate;
- `tables`: celle normalizzate collegate a file e table ID;
- `metadata`: soli valori JSON scalari;
- `statistical_code`: artefatti R/Python/R Markdown importati in modalità
  `never_execute`;
- `domain_hint` e `language`.

`ParserAIInput.from_document_ir()` realizza l'adattamento deterministico dal
Document IR. I file di codice non vengono duplicati in `documents`: questo
impedisce agli estrattori testuali di interpretarli come descrizioni dei
Methods.

### Output

`ParserAIOutput` espone esclusivamente candidate facts:

- `experiment_blocks`, `evidence_spans`, `candidate_nodes` e `candidate_edges`;
- `factors`, `endpoints`, `contrasts` e `candidate_estimands`;
- `determinability`, `alternatives` e `clarification_questions`;
- `model_metadata`, inclusa la versione del contratto.

Non esiste un campo verdetto. I modelli usano `extra=forbid`, perciò un backend
non può aggiungere un verdetto o un fatto fuori contratto.

Ogni fattore candidato mantiene distinti `allocation_level` e
`application_level`, entrambi obbligatori nello schema ma nullable quando la fonte
non li rende determinabili. Un contrasto usa `factor_ids`, `compared_levels` ed
`endpoint_ids`, quindi non comprime un disegno multifattoriale in un solo fattore.
Ogni estimando candidato deve esplicitare endpoint, misura dell'effetto,
popolazione o unita target, livello di generalizzazione e tutti i fattori
coinvolti; tempo e condizione restano opzionali. L'assenza di un campo minimo non
viene colmata dal decoder con una formula o una scelta statistica implicita.

### Invarianti

Ogni candidate fact deve avere almeno un `evidence_id` e una confidence finita
in `[0, 1]`. Il validatore rifiuta ID duplicati o pendenti, edge verso nodi
assenti, riferimenti factor/contrast/endpoint non validi e metadati con una
versione contratto diversa.

La confidence descrive il candidate fact. Un successivo outcome del motore
deterministico espone premesse e `rule_id`, non eredita o inventa una probabilità
separata per la conseguenza.

I tipi di nodo e relazione accettano soltanto i vocabolari `NodeType` e
`RelationType`. Un valore non previsto deve essere rappresentato da `OTHER`
insieme a `original_text`; la stringa originale non diventa automaticamente un
nuovo termine ontologico.

Gli span vengono controllati anche contro l'input tramite
`validate_contract_pair()`: testo, offset, celle, file e code artifact devono
coincidere con la fonte. `run_parser_adapter()` applica sempre questo controllo.

Uno span `STATISTICAL_CODE` può sostenere una dichiarazione candidata di
clustering, ma non una relazione `assigned_to`, `allocated_to`, `randomized_at`
o `applied_to`. Il codice statistico è evidenza silver e non dimostra come sia
avvenuta l'allocazione sperimentale.

### JSON Schema e versionamento

`parser_ai_json_schemas()` restituisce gli schemi JSON di input e output per backend
capaci di constrained decoding e per validazione esterna. MLX-LM non offre qui un
decoder grammar-constrained: `ntruth-ml predict` richiede JSON puro, applica un limite
di token, valida lo schema, tenta una sola correzione di formato e rifiuta l'output
ancora invalido. Una modifica incompatibile richiede
una nuova versione del contratto e un adapter esplicito; non va reinterpretato
silenziosamente un payload `1.0.0`. La versione `2.0.0` e intenzionalmente
incompatibile con il precedente schema incompleto: un backend deve emettere i
campi canonici v3.

Quella forma non e autoritativa per nuovi backend o nuovo gold. Le nuove
integrazioni devono produrre gli stage dedicati e mantenere `CandidateGraphSet`
candidate-only. Un payload legacy non va reinterpretato silenziosamente come staged:
serve un adapter esplicito e versionato.

La pipeline applicativa, la persistenza separata di estrazione/correzione/grafo
confermato e la scelta del backend restano punti di integrazione distinti. La presenza
del package o di un modello base locale non equivale all'attivazione di un parser AI
nel prodotto né a una validazione scientifica.

Vedere [Core Profile D0](core-profile-d0.md),
[architettura](architettura.md) e
[prd-v8-data-training-evaluation-boundary.md](prd-v8-data-training-evaluation-boundary.md).
