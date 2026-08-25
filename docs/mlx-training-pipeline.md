# Pipeline locale MLX/Metal

> **HISTORICAL_NON_NORMATIVE.** Gli esempi `ParserAIOutput` v2, le vecchie eligibility
> e i comandi in questo documento non costituiscono il contratto PRD v8 né
> autorizzazione al training. La corsia corrente usa `ParserCandidateOutput` dentro
> `GoldParserTarget`, protegge TEST/EXTERNAL_CHALLENGE e resta HOLD. Vedere
> [prd-v8-data-training-evaluation-boundary.md](prd-v8-data-training-evaluation-boundary.md).

Questa guida descrive la corsia opzionale e riproducibile per preparare i dati,
eseguire un fine-tuning LoRA su base quantizzata, valutare e calibrare il parser AI
di N-Truth su Apple Silicon. I comandi sono operativi; **il training scientifico sui
dati reali resta bloccato** finché non sono soddisfatti tutti i gate elencati in
[Gate prima del training reale](#gate-prima-del-training-reale).

Il modello produce soltanto candidate fact conformi a `CandidateGraphSet` v1.0.0.
`ParserAIOutput` v2.0.0 rimane un contratto legacy e non è accettato dalla corsia di
training v6. Il modello non decide il valore di `n`, non seleziona test o formule statistiche, non
scrive nel grafo confermato e non sostituisce la revisione umana. Le regole
deterministiche e il workflow di correzione restano l'autorità applicativa.

## Stato e perimetro

La pipeline implementata comprende:

- validazione dell'hardware, della memoria, dello spazio e delle versioni;
- download esplicito di uno snapshot di modello fissato a una revisione;
- manifest di provenienza e verifica SHA-256 di ogni file del modello;
- validazione, normalizzazione, deduplica e split group-aware dei record supervisionati;
- conversione nel formato chat JSONL accettato da MLX-LM;
- controllo reale delle lunghezze con il tokenizer locale;
- QLoRA a fasi, checkpoint, ripresa, validation loss ed early stopping;
- generazione locale, validazione Pydantic fail-closed e metriche strutturate;
- temperature scaling e soglia di astensione stimate soltanto sulla validation;
- snapshot e run state schema v2 verificati contro contenuto, split e checkpoint;
- export con lineage obbligatoria di metriche finali e calibrazione, senza pesi base
  né dati di training.

La corsia ML è separata dal core deterministico. Una normale installazione N-Truth e
la CI Linux non importano MLX. I file locali prodotti dalla pipeline sono ignorati da
Git e non devono essere pubblicati.

## Profilo bootstrap locale, non requisito normativo

I valori seguenti descrivono il runner smoke/QLoRA attualmente versionato. Non sono il
Runtime Resource Budget della v6.1 e non dimostrano che questa configurazione sia la
migliore architettura. Prima di un training o di un claim di fattibilita, il
`RuntimeResourceManager` deve caricare un profilo misurato sul Mac target e produrre
telemetria per stage secondo
[runtime-resource-budget-v6.1.md](runtime-resource-budget-v6.1.md).

| Voce | Precondizione del runner bootstrap corrente |
|---|---|
| Sistema | macOS su Apple Silicon (`Darwin`, `arm64`) |
| Acceleratore | GPU Apple tramite Metal, gestita da MLX |
| Memoria unificata | almeno 24 GiB |
| Python | 3.12 o successivo, come dichiarato in `pyproject.toml` |
| Runtime ML | `mlx-lm[train]==0.31.3` |
| Gestore ambiente | `uv`, usando il lockfile del repository |
| Spazio libero | guardrail bootstrap: 50 GiB dopo il download, da ricalcolare prima del run |
| Workspace N-Truth | envelope bootstrap storico: 40 GiB, non budget universale |
| Memoria riportata da MLX-LM | guardrail bootstrap storico: 18 GB, non peak di sistema |

Il profilo iniziale e destinato al MacBook Pro Apple M5 Pro con 24 GB di memoria
unificata; i test software del doctor non equivalgono a un benchmark completo del
modello su quella macchina. Il doctor blocca Intel Mac, host non macOS, memoria inferiore,
runtime diverso da quello fissato o spazio insufficiente. Il core N-Truth continua a
essere utilizzabile sugli altri sistemi, ma questa corsia di training non è supportata
su CUDA, Linux o Intel.

Riferimenti ufficiali:

- [MLX di Apple](https://github.com/ml-explore/mlx);
- [installazione MLX](https://ml-explore.github.io/mlx/build/html/install.html);
- [MLX-LM](https://github.com/ml-explore/mlx-lm);
- [guida LoRA di MLX-LM](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md).

## Modello primario provvisorio (Train A)

**Stato:** migrazione architetturale/configurativa completata; validazione runtime
e scientifica **in corso** (vedi [granite-migration-report.md](granite-migration-report.md)).

IBM Granite 4.1 3B Instruct è il modello principale **provvisorio** del Train A.
La sua adozione definitiva rimane subordinata ai benchmark N-Truth sui task
decisivi, al confronto con la cascata B5 e alla validazione su dati reali
indipendenti.

Checkpoint canonico Instruct: [`ibm-granite/granite-4.1-3b`](https://huggingface.co/ibm-granite/granite-4.1-3b)
(Apache-2.0). Su macOS il bootstrap usa una **conversione MLX della community**
(non artefatto ufficiale IBM):
[`mlx-community/granite-4.1-3b-4bit`](https://huggingface.co/mlx-community/granite-4.1-3b-4bit).

| Proprietà | Valore verificabile |
|---|---|
| Repository canonico Instruct | [`ibm-granite/granite-4.1-3b`](https://huggingface.co/ibm-granite/granite-4.1-3b) |
| Revisione canonica osservata | `c0650403e44e78ec0262dab1c90914c65b196c4e` |
| Repository MLX 4-bit | [`mlx-community/granite-4.1-3b-4bit`](https://huggingface.co/mlx-community/granite-4.1-3b-4bit) (**community conversion**) |
| Revisione MLX fissata | `b1b476b5a17c46b7d6cd663b4a8ed44b66720aef` |
| Parametri | 3,402,836,480 (~3.40B) |
| **Configured maximum context** | **131 072 token** (config modello; non capacità host-validata) |
| Quantizzazione MLX bootstrap | 4 bit (community) |
| Pesi `model.safetensors` MLX | 2,127,162,429 byte |
| SHA-256 pesi MLX | `cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d` |
| GGUF ufficiale | [`ibm-granite/granite-4.1-3b-GGUF`](https://huggingface.co/ibm-granite/granite-4.1-3b-GGUF) |
| Base (ablation only) | [`ibm-granite/granite-4.1-3b-base`](https://huggingface.co/ibm-granite/granite-4.1-3b-base) |
| Licenza | Apache-2.0 |
| Profilo | [`models/configs/granite-4.1-3b-mlx-qlora.json`](../models/configs/granite-4.1-3b-mlx-qlora.json) |
| Path locale MLX | `models/local/granite-4.1-3b-4bit/` |
| Interfaccia | `ntruth.model_backends.GraniteBackend` (`ModelBackend`) |
| LoRA targets | verificati su architettura/state dict Granite (non ereditati da Qwen) |

Acquisizione:

```bash
uv run python scripts/models/acquire_granite.py --confirm-license-and-download
# oppure
uv run ntruth-ml download-model --confirm-license-and-download
```

### Altri candidati (non default)

| Candidato | Ruolo |
|---|---|
| Granite 4.1 3B Base | ablation experimental only |
| Cascata encoder + small LLM (B5) | baseline preferita ADR-0002 da confrontare |
| Qwen3-4B (legacy) | disabilitato; profilo in `models/configs/legacy/` |

Le stime QLoRA sono envelope storici ingegneristici, non benchmark sul Mac M5 Pro e
non criteri di esclusione per una classe dimensionale. Il 4B e stato configurato come
smoke candidate riproducibile per collaudare la pipeline; modello, backend,
quantizzazione e architettura finale restano decisioni ADR aperte. Questo non dimostra
una qualita migliore. Il benchmark ufficiale
[MLX-LM](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/BENCHMARKS.md) mostra
anche che la quantizzazione può ridurre qualità: il 4-bit deve quindi essere confrontato
con baseline e human ceiling sul futuro validation set. Qualunque challenger puo
essere acquisito solo dopo un confronto preregistrato che giustifichi licenza,
download, memoria, storage, qualita e rischio OOM; i challenger elencati non sono
stati scaricati in questa fase.

## Budget di archiviazione

Questa stima bootstrap riserva 35.5 GiB simultanei entro il suo envelope storico di
40 GiB. Non costituisce un budget v6.1 benchmark-derived. Per mantenere il guardrail
bootstrap di 50 GiB, il piano completo richiede almeno 85.5 GiB
liberi prima dell'allocazione; il solo gate di download richiede invece circa 52.2 GiB
liberi. È quindi compatibile con i circa 94-96 GiB osservati su questa macchina, ma non
con qualsiasi computer che abbia genericamente meno di 100 GiB. Sono stime
conservative: vanno ricontrollate prima di ogni acquisizione o run.

| Componente | GiB riservati |
|---|---:|
| Download raw selezionati | 2.0 |
| Documenti estratti e normalizzati | 3.0 |
| JSONL preparati e report token | 4.0 |
| Modello base quantizzato | 2.2 |
| Cache del download del modello | 2.2 |
| Ambiente Python ML e cache | 3.0 |
| Adapter e checkpoint conservati | 4.0 |
| Export locale o eventuale copia fused opzionale | 8.1 |
| Metriche, log e output degli esperimenti | 2.0 |
| Margine temporaneo | 5.0 |
| **Picco pianificato** | **35.5** |

Non rientrano nel piano e non devono essere scaricati automaticamente: 45.6 GB di
linked reads CAMISIM, 9.9 GB di linked files Chelicerata, l'archivio bulk PLOS, immagini
microscopiche raw e lo snapshot OpenAlex. La selezione dei dati è documentata in
[dataset-assessment.md](dataset-assessment.md).

Controllare sempre lo spazio reale dalla root del repository:

```bash
df -h .
du -sh .venv local-data models/local models/runs models/exports 2>/dev/null
```

Il doctor bootstrap richiede che, sottratto il download atteso, rimangano almeno 50
GiB liberi. Non avviare un download se l'envelope bootstrap aggiornato supera 40 GiB
o se tale pavimento non e rispettato. Per training/release questi valori devono essere
sostituiti da un profilo misurato e versionato del Runtime Resource Manager.

## Installazione

Dalla root di un checkout pulito:

```bash
uv sync --extra dev --extra api --extra ml --locked
uv run python -c "import importlib.metadata as m; print(m.version('mlx-lm'))"
uv run ntruth-ml --help
```

La prima riga installa core, API, corsia ML e strumenti di test. Deve essere
stampata la versione `0.31.3`. Per una macchina che deve soltanto eseguire la pipeline,
senza lint e test, è sufficiente:

```bash
uv sync --extra ml --locked
```

Non sono richieste variabili d'ambiente o un file `.env` per il modello pubblico
selezionato. Il download usa `local-data/cache/huggingface/`; il training imposta
internamente `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`,
`HF_HUB_DISABLE_TELEMETRY=1` e non accede alla rete. Non inserire token Hugging Face,
credenziali o path privati in file versionati.

Per rendere leggibili i comandi successivi, in zsh o bash:

```bash
NTRUTH_REPO="$(pwd)"
NTRUTH_PROFILE="$NTRUTH_REPO/models/configs/granite-4.1-3b-mlx-qlora.json"
```

## Doctor, download e verifica del modello

Eseguire il doctor prima del download:

```bash
uv run ntruth-ml check --profile "$NTRUTH_PROFILE" --repo "$NTRUTH_REPO"
```

Prima che il modello esista, il comando stampa comunque il report JSON ma termina con
codice `2`, perché `ready_to_train=false`. È un risultato atteso se
`ready_to_download=true` e tutti i gate salvo `model_present` sono `true`. Dopo aver
letto la licenza e verificato il budget, il download richiede una conferma esplicita:

```bash
uv run ntruth-ml download-model \
  --confirm-license-and-download \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

Il downloader:

1. ripete i gate hardware e disco;
2. scarica solo la revisione fissata;
3. salva il modello sotto `models/local/` e la cache sotto `local-data/cache/`;
4. acquisisce la licenza della revisione base come `BASE_MODEL_LICENSE`;
5. genera `model-provenance.json` con path, byte e SHA-256 di ogni file.

Non sovrascrive una directory non vuota senza provenance. Verificare ogni volta prima
del training:

```bash
uv run ntruth-ml verify-model \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"

shasum -a 256 \
  models/local/granite-4.1-3b-4bit/model.safetensors
```

Il primo comando deve restituire `"valid": true` e `"problems": []`; il secondo deve
coincidere con lo SHA-256 riportato nella tabella del modello. Infine il doctor deve
restituire `ready_to_train=true`:

```bash
uv run ntruth-ml check --profile "$NTRUTH_PROFILE" --repo "$NTRUTH_REPO"
```

## Contratto dei dati sorgente

L'input di `prepare` è un file JSONL UTF-8 con un oggetto `SupervisedRecord` v1.0.0
per riga. Il contratto completo è in
[`packages/ntruth/training/records.py`](../packages/ntruth/training/records.py); input e
output del parser sono in
[`packages/ntruth/parser_ai/contract.py`](../packages/ntruth/parser_ai/contract.py),
[`packages/ntruth/parser_ai/stages.py`](../packages/ntruth/parser_ai/stages.py) e
[`packages/ntruth/training/gold.py`](../packages/ntruth/training/gold.py).

Ogni record deve contenere almeno:

- `record_id` univoco, `task="parser_candidate_graph_v6"`, lingua e dominio;
- `input_text`, cioè la serializzazione JSON di un `ParserAIInput` v2.0.0;
- `target`, cioè un `GoldParserTarget` v1.0.0 completo e schema-valid, con
  `adjudicated_graph` candidate-only e autorità `adjudication`;
- checksum e identità della fonte, asset e governance;
- versione della guideline e ruoli/revisioni umane;
- licenza o autorizzazione esplicita;
- stato `adjudicated`, `adjudication_id` coerente col target e
  `training_eligible=true`.

Il profilo MLX dichiara separatamente `task=parser_candidate_graph_v6`,
`parser_input_contract_version=2.0.0`, `candidate_graph_contract_version=1.0.0` e
`gold_target_contract_version=1.0.0`. Il vecchio campo generico
`data.contract_version` è rifiutato perché confonde il contratto di input legacy con
il target staged v6.

Struttura schematica di una riga:

```json
{
  "schema_version": "1.0.0",
  "record_id": "paper-family-001-block-01",
  "task": "parser_candidate_graph_v6",
  "language": "it",
  "domain": "experimental_biology",
  "input_text": "{\"contract_version\":\"2.0.0\",\"documents\":[],\"tables\":[],\"metadata\":{},\"statistical_code\":[],\"domain_hint\":\"experimental_biology\",\"language\":\"it\"}",
  "target": {
    "schema_version": "1.0.0",
    "target_id": "gold-paper-family-001-block-01",
    "source_record_id": "paper-family-001-block-01",
    "guideline_version": "6.0",
    "adjudication_id": "adj-paper-family-001-block-01",
    "adjudication_rationale": "Le due annotazioni cieche sono state riconciliate.",
    "adjudicator_roles": ["wet-lab", "biostatistician"],
    "source_submission_ids": ["submission-a", "submission-b"],
    "comparisons": [
      {
        "submission_id": "submission-a",
        "reviewer_role": "wet-lab",
        "changed_paths": [],
        "summary": "Nessuna differenza residua dopo adjudication."
      },
      {
        "submission_id": "submission-b",
        "reviewer_role": "biostatistician",
        "changed_paths": [],
        "summary": "Nessuna differenza residua dopo adjudication."
      }
    ],
    "adjudicated_graph": {
      "schema_version": "1.0.0",
      "result_id": "adj-result-paper-family-001-block-01",
      "stage": "candidate_graph_set",
      "status": "complete",
      "provenance": {
        "stage_run_id": "adj-stage-paper-family-001-block-01",
        "stage": "candidate_graph_set",
        "authority": "adjudication",
        "producer": "ntruth-human-adjudication",
        "producer_version": "6.0",
        "input_artifact_ids": [],
        "input_checksums": {},
        "parent_result_ids": [],
        "actor_role": "wet-lab+biostatistician",
        "started_at": null,
        "completed_at": null
      },
      "errors": [],
      "warnings": [],
      "graph_set_id": "adj-graph-paper-family-001-block-01",
      "source_result_ids": [],
      "experiment_blocks": [],
      "evidence_spans": [],
      "candidate_nodes": [],
      "candidate_edges": [],
      "factors": [],
      "endpoints": [],
      "contrasts": [],
      "candidate_estimands": [],
      "counts": [],
      "operational_independence": [],
      "procedural_events": [],
      "alternatives": [],
      "missing_facts": [],
      "chunk_coverage": []
    }
  },
  "provenance": {
    "source_id": "source-001",
    "source_asset_id": "asset-001",
    "source_sha256": "<64 caratteri esadecimali>",
    "governance_hash": "<64 caratteri esadecimali>",
    "publication_id": "doi-or-family-id",
    "project_id": "project-001",
    "bundle_id": "bundle-001",
    "laboratory_id": "laboratory-001",
    "corresponding_author_id": "author-group-001",
    "license_or_authorization_id": "local-license-record-001",
    "guideline_version": "6.0",
    "reviewer_count": 2,
    "reviewer_roles": ["wet-lab", "biostatistician"],
    "adjudication_id": "adj-paper-family-001-block-01",
    "synthetic": false
  },
  "annotation_status": "adjudicated",
  "training_eligible": true,
  "requested_split": null,
  "metadata": {}
}
```

I placeholder dei checksum nell'esempio devono essere sostituiti con SHA-256 reali.
Un record `adjudicated` richiede anche `adjudication_id`. Per il task canonico v6,
`double_reviewed` da solo non basta: le due submission devono essere riconciliate o
confermate esplicitamente nel `GoldParserTarget`. I record sintetici possono entrare
soltanto nel train, ma la factory/lineage sintetica v6 non è ancora implementata e non
va simulata con un falso gold umano. Candidate e record con una sola revisione vengono
esclusi e non possono essere resi eleggibili modificando soltanto un flag.
Durante l'export MLX, il wrapper `GoldParserTarget` rimane nel manifest privato e il
solo `adjudicated_graph` viene proiettato in `CandidateGraphSet` con
`provenance.authority="model"`: al modello non viene insegnato a dichiararsi reviewer
o adjudicator. `determinability` e `verdict` sono rifiutati dallo schema.

## Preparazione, deduplica e split

Conservare il file approvato in un path privato sotto `local-data/` e usare una nuova
directory di output:

```bash
NTRUTH_SOURCE="$NTRUTH_REPO/local-data/annotations/approved/gold-supervised-v1.jsonl"
NTRUTH_DATA="$NTRUTH_REPO/local-data/prepared/candidate-graph-v6-gold-v1"

uv run ntruth-ml prepare "$NTRUTH_SOURCE" \
  --out "$NTRUTH_DATA" \
  --seed ntruth-dataset-v1 \
  --train-ratio 0.8 \
  --validation-ratio 0.1 \
  --test-ratio 0.1 \
  --near-duplicate-threshold 0.92
```

`prepare` applica, in ordine:

1. validazione Pydantic di ogni riga e dei gate di eleggibilità;
2. normalizzazione Unicode NFKC e whitespace per il confronto, senza mutare la fonte;
3. JSON canonico del target e fingerprint SHA-256;
4. rifiuto di ID duplicati e target incompatibili per lo stesso input;
5. deduplica esatta e near-duplicate con Jaccard su shingle di cinque token; la
   rimozione near richiede target compatibili, mentre ogni match testuale sopra soglia
   collega i record nello stesso leakage group anche con target diversi;
6. componenti di leakage e split deterministico per intero gruppo;
7. conversione in chat `system`/`user`/`assistant` e manifest content-addressed.

I gruppi di leakage sono connessi da `source_id`, `source_asset_id`, `source_sha256`,
`publication_id`, `project_id`, `bundle_id`, `laboratory_id` e
`corresponding_author_id`. Un articolo, le sue revisioni, supplementi, sample sheet,
codice e mirror devono pertanto condividere le stesse identità di provenance.
`requested_split="external"` è ammesso per il set esterno custodito; i record correlati
non possono richiedere split incompatibili.

La directory risultante contiene:

```text
candidate-graph-v6-gold-v1/
├── train.jsonl
├── valid.jsonl
├── test.jsonl
├── external.jsonl
├── dataset-manifest.source.json
├── prepared-records.jsonl
├── preparation-report.json
└── snapshot-manifest.json
```

`train`, `valid` e `test` devono essere non vuoti per il trainer. `external` può essere
vuoto durante lo sviluppo, ma deve restare indipendente per la validazione esterna.
Controllare `preparation-report.json`, ogni decisione di deduplica e i conteggi prima
di approvare lo snapshot. Non spostare singoli record a mano dopo la preparazione:
correggere le identità sorgente o la policy, creare un nuovo snapshot e congelarne gli
hash. Il gate schema v2 non si fida dei soli booleani nel manifest: verifica checksum e
dimensioni di tutti i file, identità e record del manifest sorgente, decisioni di
deduplica, approvazioni per-record, conteggi/ID degli split e ricostruzione esatta dei
messaggi chat. File alterati, symlink o snapshot ricomposti a mano vengono rifiutati.

## Tokenizzazione e gate di lunghezza

La pipeline non salva una seconda copia tokenizzata. Applica il chat template del
modello locale, disabilita la modalità thinking quando supportata e registra le
lunghezze reali:

```bash
uv run ntruth-ml tokenize "$NTRUTH_DATA" \
  --out "$NTRUTH_DATA/token-report.json" \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

Il limite iniziale è 1,024 token. Il report contiene minimo, mediana, p95, massimo e
numero di record oltre soglia per ogni split. Il comando termina con codice `2` se un
record eccede il limite. Non accettare troncamenti silenziosi: segmentare correttamente
gli experiment block a monte oppure creare e revisionare un nuovo profilo, quindi
rigenerare e ricongelare lo snapshot.

## Configurazione QLoRA

Il trainer carica la base 4-bit e ottimizza soltanto adapter LoRA: nel profilo questo
percorso è dichiarato QLoRA. Non dequantizza né modifica i pesi base.

| Parametro | Valore iniziale |
|---|---:|
| Layer adattati | ultimi 8 |
| Proiezioni LoRA | `self_attn.q_proj`, `self_attn.v_proj` |
| Rank / scale / dropout | 8 / 16.0 / 0.05 |
| Batch fisico | 1 |
| Gradient accumulation | 8 |
| Batch effettivo | 8 |
| Ottimizzatore | AdamW |
| Learning rate | `1e-5` |
| Prompt masking | attivo |
| Gradient checkpointing | attivo |
| Lunghezza massima | 1,024 token |
| Iterazioni per fase | 100 |
| Fasi massime | 20 |
| Validation batches | tutti (`-1`) |
| Early stopping | patience 3, miglioramento minimo 0.001 sulla validation loss |
| Checkpoint di fase conservati | ultimi 3, oltre alla copia `best` |
| Seed preregistrati | 13, 37, 101 |

Questa configurazione privilegia il margine di memoria e la riproducibilità. Qualsiasi
variante è un nuovo esperimento: usare un nuovo file profilo, documentare il razionale,
ricontrollare spazio e token e non cambiare parametri durante l'osservazione del test.

## Training, checkpoint e ripresa

Avviare un singolo seed in una directory nuova:

```bash
NTRUTH_RUN="$NTRUTH_REPO/models/runs/candidate-graph-v6-gold-v1-seed13"

uv run ntruth-ml train "$NTRUTH_DATA" \
  --out "$NTRUTH_RUN" \
  --seed 13 \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

Prima di addestrare, il comando verifica doctor, modello, manifest, split non vuoti,
`training_approved=true`, `leakage_check_passed=true` e seed. Il training procede in
fasi di 100 iterazioni. Dopo ogni fase:

1. salva l'adapter in `checkpoints/phase-NNNN/`;
2. valuta l'intero validation split;
3. registra validation loss, durata e picco memoria riportato da MLX-LM;
4. copia il miglior adapter in `best/`;
5. aggiorna atomicamente `run-state.json`;
6. arresta dopo tre fasi senza miglioramento di almeno 0.001 o oltre la soglia di
   memoria configurata.

Ogni fase è un'invocazione MLX-LM separata: riprende i pesi dell'adapter precedente,
ma inizializza nuovamente optimizer e scheduler. Il controller offre checkpoint ed
early stopping riproducibili a confine di fase; non è bit-equivalente a un singolo run
monolitico con stato optimizer continuo. Questo compromesso deve rimanere dichiarato
nelle comparazioni.

I file principali del run sono:

```text
models/runs/<run>/
├── best/
├── checkpoints/
├── configs/
├── _validation-as-test/
├── run-state.json
├── train.log
└── validation.log
```

`_validation-as-test` è una copia tecnica usata perché MLX-LM espone la loss finale
tramite l'interfaccia `test`; contiene esclusivamente la validation, non il test
scientifico. Il test congelato non viene letto dal controller di training.

Se il processo viene interrotto dopo almeno una fase completa, riprendere lo stesso
run:

```bash
uv run ntruth-ml train "$NTRUTH_DATA" \
  --out "$NTRUTH_RUN" \
  --seed 13 \
  --resume \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

La ripresa è rifiutata se sono cambiati profilo, snapshot dati, `uv.lock` o il
fingerprint dei package `training`/`parser_ai`, oppure se manca il checkpoint
dell'ultima fase completa. Non promette una ripresa a metà fase. Il seed effettivo di
ogni fase è `seed + phase - 1` e viene registrato insieme alla configurazione generata.

Dopo il congelamento del protocollo, eseguire e riportare tutti i seed preregistrati,
senza scegliere quello che appare migliore sul test:

```bash
for NTRUTH_SEED in 13 37 101; do
  uv run ntruth-ml train "$NTRUTH_DATA" \
    --out "$NTRUTH_REPO/models/runs/candidate-graph-v6-gold-v1-seed-$NTRUTH_SEED" \
    --seed "$NTRUTH_SEED" \
    --profile "$NTRUTH_PROFILE" \
    --repo "$NTRUTH_REPO"
done
```

## Predizione schema-valid e metriche

Valutare prima la validation usando l'adapter `best`:

```bash
NTRUTH_VALIDATION_EVAL="$NTRUTH_REPO/local-data/evaluation/candidate-graph-v6-gold-v1-validation-seed13"

uv run ntruth-ml predict "$NTRUTH_DATA/valid.jsonl" \
  --adapter "$NTRUTH_RUN/best" \
  --out "$NTRUTH_VALIDATION_EVAL" \
  --split validation \
  --retry-invalid-once \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

La generazione usa temperatura zero, al massimo 1,024 token, il chat template
non-thinking e, per impostazione predefinita, un solo retry se l'output non è valido.
MLX-LM non applica qui una grammatica JSON vincolante. La robustezza è quindi
fail-closed:

1. viene accettato soltanto JSON puro o un unico code fence JSON;
2. testo dopo il payload viene rifiutato;
3. il payload deve validare integralmente `CandidateGraphSet` v1.0.0 con Pydantic e
   dichiarare `provenance.authority="model"`;
4. file, offset, testo, tabelle, celle e code span devono coincidere col
   `ParserAIInput`, e la copertura chunk deve essere esaustiva e file-bound, tramite
   `validate_candidate_graph_pair()`;
5. provenance e lineage dichiarate dal modello vengono sostituite dall'host; non viene
   eseguita alcuna riparazione dei fatti scientifici;
6. dopo il retry, un output invalido vale zero per precision, recall e F1 ed è contato
   esplicitamente.

L'output locale contiene:

- `predictions.jsonl`: gold, output grezzo, prediction validata, tentativi ed errore;
- `metrics.json`: schema-valid rate, exact-contract-match rate, metriche per categoria,
  macro-category F1, micro precision/recall/F1 e conteggio invalidi;
- `confidence-observations.jsonl`: confidence esclusivamente di evidence e candidate
  fact, con esito rispetto al gold, usate per calibrazione.

Le metriche confrontano fatti strutturati per experiment block, evidence span, nodi,
edge, fattori, endpoint, contrasti, estimand, count, indipendenza operativa, eventi,
alternative, missing fact e copertura chunk. La determinability non è una label né
una metrica del parser: viene valutata separatamente sul Derivation Gold del motore
deterministico.

Le firme dei candidate fact includono i link agli evidence span normalizzati: scambiare
le evidenze tra due fatti lascia corretta l'inventario degli span, ma rende errati i
fatti collegati e le relative confidence observations.

Le metriche del parser devono essere riportate per lingua,
dominio e categoria oltre all'aggregato quando il corpus reale lo consente. La loss di
training non sostituisce queste metriche né la revisione degli esperti. Quando un
report viene riusato per calibrazione o export, la pipeline rilegge il gold manifestato
e le prediction, rivalida gli output grezzi e ricalcola score per-record, aggregati e
confidence observations: aggiornare soltanto hash o conteggi non rende valido un
artefatto modificato.

## Calibrazione e astensione

Calibrare esclusivamente le confidence prodotte sulla validation congelata:

```bash
NTRUTH_CALIBRATION="$NTRUTH_REPO/local-data/evaluation/candidate-graph-v6-gold-v1-calibration-seed13.json"

uv run ntruth-ml calibrate \
  "$NTRUTH_VALIDATION_EVAL/confidence-observations.jsonl" \
  --out "$NTRUTH_CALIBRATION" \
  --fit-split validation \
  --maximum-risk 0.10 \
  --minimum-coverage-count 10
```

Il comando richiede almeno due osservazioni e sia esiti corretti sia errati. Stima
deterministicamente una temperatura positiva, confronta negative log-likelihood,
Brier score ed ECE prima/dopo e seleziona sulla validation la massima copertura che
rispetta il rischio empirico richiesto. Il report dichiara sempre
`test_used_for_fit=false`. Prima del fit, la CLI richiede il `metrics.json` adiacente,
verifica che l'artefatto derivi esattamente da `valid.jsonl`, ricontrolla snapshot, run,
adapter, SHA-256 e numero delle confidence; copiare o rinominare il solo JSONL non può
trasformare prediction test in validation. Prima dell'export, temperatura, metriche di
calibrazione e soglia risk-coverage vengono ricalcolate deterministicamente dalle
osservazioni originarie: modificare il report a mano invalida il bundle.

Le confidence sono campi prodotti dal parser, non probabilità token-level dimostrate
ben calibrate. La calibrazione va quindi validata sul corpus reale e documentata nella
Model/System Card. La CLI corrente produce il report di calibrazione, ma non riscrive
automaticamente le prediction del test con la temperatura: l'applicazione operativa
della temperatura e della soglia resta un gate di integrazione.

Dopo aver congelato adapter, prompt, contratto, temperatura, soglia e protocollo,
aprire il test una sola volta:

```bash
NTRUTH_TEST_EVAL="$NTRUTH_REPO/local-data/evaluation/candidate-graph-v6-gold-v1-test-seed13"

uv run ntruth-ml predict "$NTRUTH_DATA/test.jsonl" \
  --adapter "$NTRUTH_RUN/best" \
  --out "$NTRUTH_TEST_EVAL" \
  --split test \
  --retry-invalid-once \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

La stessa procedura si applica a `external.jsonl` con `--split external`, soltanto
durante la validazione indipendente e senza riaprire la model selection.

## Export dell'adapter

Creare un bundle in una directory nuova:

```bash
NTRUTH_EXPORT="$NTRUTH_REPO/models/exports/candidate-graph-v6-gold-v1-seed13"

uv run ntruth-ml export-adapter "$NTRUTH_RUN" \
  --dataset-manifest "$NTRUTH_DATA/snapshot-manifest.json" \
  --metrics "$NTRUTH_TEST_EVAL/metrics.json" \
  --calibration "$NTRUTH_CALIBRATION" \
  --out "$NTRUTH_EXPORT" \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

L'export contiene adapter, configurazione, profilo, run state, manifest del dataset e i
report obbligatori di metriche e calibrazione. Le metriche finali devono provenire dal
`test` dello snapshot di training oppure da uno snapshot `external` indipendente ma
valutato con lo stesso run e adapter; la calibrazione deve provenire dalla validation
dello snapshot di training. `export-manifest.json` registra byte, SHA-256 e lineage di
run, adapter, training snapshot, evaluation snapshot e calibrazione, e dichiara
`contains_base_weights=false` e `contains_training_data=false`.
Per `external`, il run-state deve ancorare il path dello snapshot di training. Prima
della valutazione e nuovamente durante la verifica dell'export, la pipeline ricalcola
l'integrità di entrambi gli snapshot e rifiuta collisioni di record, fingerprint,
provenance/leakage group e near-duplicate lessicali (Jaccard su 5-shingle, soglia
conservativa 0,92). Il report di disgiunzione entra nella lineage delle metriche e
dell'export; un run storico senza path verificabile fallisce in modo chiuso.
Questo non rende automaticamente pubblicabile il bundle: servono review scientifica,
Model Card, valutazione delle licenze e autorizzazione di rilascio. Il flusso standard
non produce né richiede un modello fused.

## Smoke test runtime riproducibile

La modalità smoke crea otto esempi sintetici tecnici, separati 4/2/2. È l'unico modo
in cui un manifest non approvato può entrare nel trainer, richiede il flag esplicito e
limita l'esecuzione a una fase di due iterazioni con gradient accumulation 1.

Su una directory nuova:

```bash
NTRUTH_SMOKE_DATA="$NTRUTH_REPO/local-data/smoke/mlx-runtime-v1"
NTRUTH_SMOKE_RUN="$NTRUTH_REPO/local-data/smoke/run-granite-4.1-3b-v1"

uv run ntruth-ml make-smoke-data --out "$NTRUTH_SMOKE_DATA"
uv run ntruth-ml tokenize "$NTRUTH_SMOKE_DATA" \
  --out "$NTRUTH_REPO/local-data/smoke/token-report-v1.json" \
  --profile "$NTRUTH_PROFILE" --repo "$NTRUTH_REPO"
uv run ntruth-ml train "$NTRUTH_SMOKE_DATA" \
  --out "$NTRUTH_SMOKE_RUN" \
  --seed 13 \
  --runtime-smoke-only \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

Evidenza locale osservata il 1 agosto 2026 su Apple M5 Pro, 24 GB, MLX-LM 0.31.3:

| Misura | Risultato |
|---|---:|
| Esempi sintetici | 8, con split 4 train / 2 validation / 2 test |
| Token massimi | 341 su limite 1,024; 0 oltre soglia |
| Iterazioni | 2 |
| Parametri addestrabili riportati | 0.655M / 4,022.468M, pari a 0.016% |
| Durata training | 6.620 s al primo run; 2.624 s a cache calda |
| Durata validation finale | 1.368 s al primo run; 1.490 s a cache calda |
| Durata complessiva misurata | 7.988 s al primo run; 4.113 s a cache calda |
| Picco memoria riportato da MLX-LM | 3.174 GB |
| Validation loss tecnica finale | 4.203 |

Questi numeri verificano caricamento del modello, Metal, backward pass, salvataggio,
controller a fasi e validation. **Non verificano una ripresa realmente interrotta e
non misurano accuratezza, qualità scientifica,
prestazioni sul corpus reale né il picco di un run completo.** Il manifest smoke
dichiara `training_approved=false`, `leakage_check_passed=false`,
`runtime_smoke_only=true` e `scientific_metrics_allowed=false`.

La verifica fisica schema v2 del 1 agosto 2026 ha tokenizzato 8/8 esempi entro il limite,
completato due iterazioni con picco MLX-LM di 3,174 GB e validation loss 4,203, quindi
prodotto 0 output schema-valid su 2 esempi sintetici. È un risultato atteso per un
adapter tecnico non addestrato e dimostra che il parser fallisce in modo esplicito; non
deve essere usato come baseline scientifica o corretto manualmente per sembrare valido.
Il successivo tentativo di calibrazione è stato rifiutato perché lo snapshot era smoke.

## Verifica del codice

La suite mirata non scarica modelli e verifica budget, contratti, scoring degli output
invalidi, snapshot/run schema v2, calibrazione validation-only, lineage di evaluation ed
export MLX e isolamento dello smoke:

```bash
uv run pytest \
  tests/unit/test_mlx_training_pipeline.py \
  tests/unit/test_mlx_snapshot_integrity.py \
  tests/unit/test_mlx_evaluation_lineage.py \
  tests/unit/test_training_dedup_split_integrity.py
```

Prima di congelare un run o preparare un rilascio, eseguire anche:

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run pytest
```

`run-state.json` schema v2 registra automaticamente Python, piattaforma, architettura,
versioni N-Truth/MLX/Transformers, SHA-256 del lockfile, fingerprint dei sorgenti,
commit Git, presenza di modifiche tracciate, identità dello snapshot e checksum
dell'adapter `best`. Ripresa, inferenza ed export rifiutano il vecchio schema v1 e
artefatti il cui contenuto non coincide con questa lineage. Conservare inoltre con ogni
esperimento, in area locale privata:

- commit Git del codice e hash del profilo;
- `model-provenance.json` e revisione del modello;
- `snapshot-manifest.json`, report di preparazione e token report;
- `run-state.json`, configurazioni di fase e log;
- metriche, calibrazione, seed e motivazione di ogni deviazione;
- hardware, versione macOS, Python, MLX-LM e spazio libero osservati.

## Gate prima del training reale

Il profilo dichiara il training reale bloccato finché non risultano tutti veri:

- pilot gold approvato;
- manifest di licenza/autorizzazione completi per ogni asset;
- privacy review completata;
- split train/validation/test/external congelati;
- snapshot del dataset hashato.

Inoltre il protocollo di progetto richiede revisione esperta, almeno 20 design reali
stabili, 30–60 fixture canoniche e 30 casi di calibrazione annotati in doppio prima di
considerare il fine-tuning scientifico. Vedere
[first-human-steps-checklist.md](first-human-steps-checklist.md),
[data-and-model-development.md](data-and-model-development.md) e
[validation-protocol-draft.md](validation-protocol-draft.md).

Il codice applica i gate immediatamente verificabili (`training_approved`, leakage,
snapshot, modello, hardware); non può attestare da solo che approvazione scientifica,
consenso, licenza o privacy review siano sostanzialmente corretti.

## Limiti attuali

- Non esiste ancora un gold corpus sufficiente per stimare qualità o generalizzazione.
- Il modello base è generalista e non è stato validato per la ricostruzione delle unità
  sperimentali di N-Truth.
- La generazione JSON non usa constrained decoding grammaticale; schema e integrità
  referenziale sono controllati dopo la generazione, con un solo retry.
- Il limite di 1,024 token richiede segmentazione affidabile degli experiment block e
  non autorizza il troncamento di evidenze.
- La deduplica near-duplicate è lessicale e conservativa; non sostituisce una review di
  contaminazione semantica o la ricerca manuale di versioni/mirror.
- Il guardrail bootstrap di 18 GB usa il picco stampato da MLX-LM, non l'intera
  memoria osservata da macOS e non e un requisito v6.1. Prima di un run reale va
  sostituito da un profilo benchmark-derived con memoria, swap e cache per stage.
- Early stopping usa validation loss. Le metriche strutturate e la valutazione umana
  devono guidare la selezione finale secondo un protocollo congelato.
- Il phased training riprende i pesi LoRA ma non lo stato dell'optimizer; una futura
  integrazione nativa dell'early stopping in MLX-LM potrebbe cambiare la traiettoria.
- L'aggregatore CLI non stratifica automaticamente le metriche per lingua o dominio;
  i report stratificati devono essere prodotti da subset congelati e dichiarati.
- Temperature scaling opera sulle confidence dichiarate nel JSON e il suo report non
  viene ancora applicato automaticamente all'inferenza del test o dell'applicazione.
- L'export standard contiene soltanto adapter e provenance; integrazione desktop,
  applicazione della soglia di astensione e packaging di un runtime finale restano
  gate separati.
- Nessuna evidenza smoke autorizza download massivi, training reale, rilascio del
  modello o claim scientifici.

## Troubleshooting

| Sintomo | Controllo e correzione sicura |
|---|---|
| `check` termina con 2 prima del download | Leggere il JSON: è atteso se l'unico gate falso è `model_present`; non ignorare errori di piattaforma, memoria o disco. |
| Versione MLX-LM errata | Eseguire `uv sync --extra ml --locked` e ricontrollare; non aggiornare MLX-LM fuori dal lockfile durante uno studio. |
| Spazio insufficiente | Ridurre il sottoinsieme locale o archiviare artefatti autorizzati; non abbassare il pavimento di 50 GiB senza un nuovo budget revisionato. |
| Directory di output non vuota | Usare un nuovo ID/versione. Non sovrascrivere snapshot, run, prediction o export esistenti. |
| Modello con checksum errato | Mettere in quarantena la directory locale, conservare il report d'errore e riscaricare la revisione fissata dopo verifica; non usare i pesi corrotti. |
| `training_approved` o leakage gate falso | Correggere approvazioni e provenance alla fonte, quindi rigenerare lo snapshot. Non modificare il manifest a mano. |
| Split vuoto | Aumentare il corpus o correggere il piano group-aware; non duplicare record per riempire uno split. |
| Token oltre 1,024 | Correggere la segmentazione degli experiment block o revisionare formalmente un nuovo profilo; non troncare in silenzio. |
| Errore di ripresa per hash cambiato | Il run appartiene al vecchio profilo/snapshot. Creare un nuovo run invece di forzare la ripresa. |
| Snapshot o run schema v1 rifiutato | Rigenerare lo snapshot dai `SupervisedRecord` approvati e avviare un nuovo run schema v2. Non modificare o migrare a mano manifest e run state. |
| Arresto oltre la soglia memoria | Conservare `run-state.json` e i log, interrompere l'esperimento e progettare una variante più piccola prima di riprovare. |
| Output JSON invalido | Ispezionare `predictions.jsonl` e contarlo come invalido. Non ripararlo per il calcolo delle metriche. |
| Calibrazione rifiutata | Conservare `confidence-observations.jsonl` col suo `metrics.json`; devono provenire da `valid.jsonl` dello stesso snapshot/run/adapter e avere hash/conteggio coerenti. Servono inoltre almeno due osservazioni e sia esempi corretti sia errati. |
| Export rifiutato per lineage | Usare adapter `best`, manifest di training, calibrazione validation e metriche finali test/external prodotti dallo stesso run. Non copiare o rinominare artefatti tra run. |
| Training tenta la rete | Il controller imposta la modalità offline. Verificare che il modello fissato sia completo e valido invece di riabilitare download durante il run. |

Tutti i dataset, documenti sorgente, annotation file, cache, pesi, adapter, checkpoint,
prediction raw e output di lavoro devono restare in percorsi ignorati (`local-data/`,
`data/raw/`, `data/processed/`, `models/local/`, `models/runs/`, `models/checkpoints/` o
`models/exports/`) e non devono essere aggiunti a Git senza autorizzazione esplicita e
una verifica di distribuzione separata.
