# Contratto parser/verifier v6

## Stato

Il package `ntruth.parser_ai` definisce contratti Pydantic versionati per gli
artefatti del futuro Train A. Non include pesi, non esegue chiamate di rete e non
attiva un parser AI nel flusso standard. La presenza degli schema e della pipeline
MLX locale non equivale a un modello addestrato, calibrato o scientificamente
validato.

La baseline Train D resta deterministica e usa il verificatore hard. I dieci modelli
di fase descritti qui stabiliscono il confine che un backend Train A dovra rispettare;
non tutti sono ancora orchestrati come un'unica esecuzione AI end-to-end.

## Le dieci fasi

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

## Envelope comune

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

## CandidateGraphSet: candidate-only

`CandidateGraphSet` puo contenere:

- blocchi sperimentali ed evidence span;
- nodi e archi candidati;
- fattori, endpoint, contrasti ed estimandi candidati;
- count con quantificatore e scope;
- indipendenza operativa candidata ed eventi procedurali;
- alternative, missing facts e copertura dei chunk.

Non contiene `verdict` ne `determinability`. I modelli sono `extra=forbid`, quindi un
backend v6 non puo aggiungere tali campi. Determinabilita, unita sperimentale, valore
pubblicabile di `n`, alert e conseguenze del ruleset sono derivazioni deterministiche
successive.

Non esiste intenzionalmente una promozione automatica da `CandidateGraphSet.alternatives`
al contratto core `PlausibleGraphSet`. Le alternative del parser contengono riferimenti
a nodi e archi candidati, ma non dimostrano da sole compatibilita scientifica, conseguenze
scope-aware o una domanda discriminante auditabile. La materializzazione core richiede
almeno due grafi distinti validati dall'hard verifier, conseguenze evidence-linked, una
`Question` decisiva e provenance non-`model`; soltanto quel record puo autorizzare lo
stato `MULTIPLE_PLAUSIBLE_GRAPHS`. Un futuro adapter dovra quindi essere una fase
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

## Contratto legacy v2

`ParserAIInput` e `ParserAIOutput` con `contract_version = 2.0.0` restano disponibili
come superficie di compatibilita. Separano documenti, tabelle, metadata e codice
statistico `never_execute`, ma l'output storico include anche una valutazione di
`determinability`.

Quella forma non e autoritativa per nuovi backend o nuovo gold v6. Le nuove
integrazioni devono produrre gli stage dedicati e mantenere `CandidateGraphSet`
candidate-only. Un payload legacy non va reinterpretato silenziosamente come staged:
serve un adapter esplicito e versionato.

## Verificatore hard e verificatore semantico

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

## Determinabilita e output

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

## Parser Gold e Derivation Gold

I due livelli devono restare separati per attribuire correttamente gli errori:

| Artefatto | Mapping | Contenuto | Stato nel repository |
|---|---|---|---|
| Parser Gold | documenti -> grafo | Evidence span, fatti e relazioni adjudicati in un `CandidateGraphSet` candidate-only | Contratto `GoldParserTarget` implementato; corpus reale non ancora raccolto |
| Derivation Gold | grafo confermato -> conseguenze | Determinabilita, EU/n per scope, rule result, domande e proof trace attesi | Protocollo/artifact distinto ancora da popolare e approvare con esperti |

`GoldParserTarget` richiede almeno due submission sorgenti, una comparison per ogni
submission, rationale e ruoli di adjudication, `status=complete` e provenance con
autorita `adjudication`. Il tipo impedisce di chiamare gold una singola proposta del
modello; non prova che esista gia un corpus adjudicato.

Fixture sintetiche, expected output di test e smoke training non sono gold umano. Non
devono alimentare metriche scientifiche, calibrazione o claim di baseline reale.

## Gate Train A

Nessun training scientifico e dichiarato completato. Prima di selezionare o
ottimizzare un modello servono almeno Core Profile e ruleset revisionati, Derivation
Gold confermato, Parser Gold autorizzato, split per bundle/laboratorio, validation e
test congelati, baseline vincolata allo schema e protocolli di calibrazione/external
challenge. I componenti MLX presenti servono a rendere riproducibile il lavoro futuro,
non a superare questi gate.

Vedere [Core Profile D0](core-profile-d0.md) e
[architettura](architettura.md).
