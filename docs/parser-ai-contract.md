# Contratto parser AI v2.0.0

Questo documento descrive il confine stabile previsto dal PRD scientifico v3,
sezione 13. Il package `ntruth.parser_ai` non include un modello, non esegue
training e non effettua chiamate di rete. Un backend sostituibile può operare
soltanto attraverso `ParserAIAdapter` e i modelli Pydantic qui descritti.

## Input

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

## Output

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

## Invarianti

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

## JSON Schema e versionamento

`parser_ai_json_schemas()` restituisce gli schemi JSON di input e output per
constrained decoding e validazione esterna. Una modifica incompatibile richiede
una nuova versione del contratto e un adapter esplicito; non va reinterpretato
silenziosamente un payload `1.0.0`. La versione `2.0.0` e intenzionalmente
incompatibile con il precedente schema incompleto: un backend deve emettere i
campi canonici v3.

La pipeline applicativa, la persistenza separata di estrazione/correzione/grafo
confermato e la scelta del backend restano punti di integrazione distinti. La
presenza di questo package non equivale all'attivazione di un parser AI.
