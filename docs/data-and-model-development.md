# Dati, annotazione e sviluppo del modello

## Stato verificabile

Il repository contiene una pipeline riproducibile per preparare annotazioni autorizzate,
eseguire QLoRA locale con MLX, valutare output strutturati, calibrare le confidence ed
esportare un adapter. Non esistono ancora un corpus gold N-Truth, un modello N-Truth
scientificamente addestrato o metriche su dati reali. Il runtime smoke sintetico verifica
soltanto che il percorso tecnico funzioni.

La configurazione iniziale è
`models/configs/qwen3-4b-instruct-2507-mlx-qlora.json`; la guida operativa completa è
[mlx-training-pipeline.md](mlx-training-pipeline.md). Le fonti pubbliche e le decisioni
di acquisizione sono riepilogate in [dataset-assessment.md](dataset-assessment.md).

## Layout locale

I dati reali o scaricati devono restare in `local-data/`, ignorata integralmente da Git:

```text
local-data/
├── raw/incoming/          # byte originali, immutabili
├── metadata/assets/       # URL, licenza, checksum, retrieval e review
├── metadata/sources/      # due diligence delle fonti
├── annotations/
│   ├── pending/
│   ├── double-reviewed/
│   └── adjudicated/
├── prepared/<snapshot>/   # manifest e chat JSONL content-addressed
├── evaluation/<run>/      # prediction, metriche e calibrazione
├── cache/                 # cache di download locale
├── train/                 # layout legacy; preferire manifest sotto prepared
├── validation/
├── test/
├── external/
└── quarantine/            # licenza, privacy o integrità non risolte
```

Modelli, adapter e run restano rispettivamente in `models/local/`, `models/runs/` e
`models/exports/`, anch'esse ignorate. Gli split contengono riferimenti e manifest; le
sorgenti raw non vanno duplicate fisicamente.

## Gate di acquisizione

Per ogni asset registrare almeno:

- URL primario e responsabile;
- versione/data di recupero e checksum SHA-256;
- licenza per singolo asset e URL della prova;
- attribuzione e usi separati (`analyze`, `annotate`, `train`, `share`, `redistribute`);
- eventuali restrizioni commerciali, privacy, embargo o revoca;
- famiglia articolo/preprint, laboratorio, dataset e supplementi collegati;
- stato `pending`, `approved_tier_a` o `rejected`.

L'acquisizione automatizzata iniziale deve limitarsi a `CC0-1.0` e `CC-BY-4.0` con
prova per singolo asset. “Open access”, accesso gratuito o presenza in un repository
pubblico non bastano. CC BY-NC, CC BY-ND, licenze custom e licenza assente richiedono
review scritta e non entrano automaticamente nel corpus.

## Contratto supervisionato e preparazione

`ntruth.training.SupervisedRecord` è il confine prima della preparazione. Ogni record
contiene:

- `record_id`, task, lingua, dominio, `ParserAIInput` e target `ParserAIOutput`;
- source/asset ID e SHA-256;
- governance hash e prova di licenza o autorizzazione;
- versione della guideline, numero/ruolo dei reviewer e adjudication ID;
- stato annotativo, consenso esplicito al training e split eventualmente fissato;
- publication/project/bundle, laboratorio e corresponding-author ID per costruire i
  leakage group.

Un record `candidate` o `single_reviewed` non può essere `training_eligible`. Lo stato
`double_reviewed` richiede almeno due reviewer; `adjudicated` richiede anche un ID di
adjudication. Il comando `prepare` applica in ordine:

1. validazione Pydantic e dei gate di eleggibilità;
2. normalizzazione Unicode/whitespace e serializzazione canonica del target;
3. fingerprint SHA-256 e deduplica esatta;
4. deduplica near conservativa tramite shingle: rimozione soltanto con target
   compatibile e match diretto, ma grouping anti-leakage indipendente dal target e
   transitivo sull'intera componente;
5. errore fatale se input equivalenti hanno label incompatibili;
6. unione transitiva dei gruppi per pubblicazione, progetto, bundle, sorgente e asset;
7. split deterministico group-aware con seed registrato;
8. vincolo synthetic-only-train e rispetto degli split `external` fissati;
9. manifest, report decisionale e snapshot content-addressed.

Esempio:

```bash
uv run ntruth-ml prepare /absolute/private/approved-records.jsonl \
  --out local-data/prepared/corpus-v1 \
  --seed ntruth-dataset-v1 \
  --train-ratio 0.8 \
  --validation-ratio 0.1 \
  --test-ratio 0.1 \
  --near-duplicate-threshold 0.92
```

La directory di output deve essere nuova. `train.jsonl`, `valid.jsonl`, `test.jsonl` ed
`external.jsonl` sono in formato chat MLX. Lo snapshot schema v2 conserva anche
`prepared-records.jsonl`, il manifest sorgente e il report decisionale; il validatore
ricostruisce ogni riga chat dai record preparati e verifica byte, checksum, conteggi,
ID univoci, split, approvazioni e identità content-addressed prima del training.

## Separazione degli split e leakage

La separazione avviene per Experiment Bundle, mai per frase o riga. Lo stesso leakage
group non può attraversare split:

- DOI/PMCID e tutte le revisioni;
- preprint e versione pubblicata;
- supplementi, sample sheet, codice e dataset collegati;
- laboratorio/corresponding author quando disponibile;
- template synthetic o trasformazioni dello stesso grafo.

Nel corpus scientifico gli asset synthetic sono ammessi soltanto nel train. La
validation viene congelata prima dell'ottimizzazione ed è usata per early stopping,
model selection e calibrazione; test ed external non vengono usati per questi scopi e
si aprono soltanto dopo il freeze. La fixture tecnica `runtime_smoke_only` è una
eccezione isolata 4/2/2 che non appartiene al corpus e vieta metriche scientifiche.

## Annotazione manuale e condizioni di training

Il percorso umano previsto dal PRD v3 è:

1. almeno 20 disegni reali rappresentabili senza modifiche sostanziali allo schema;
2. 30 calibration cases fuori dal test;
3. doppia annotazione indipendente wet-lab/biostatistica;
4. agreement misurato prima dell'adjudication;
5. protocollo del pilot e split congelati;
6. feasibility pilot di 150-250 bundle con disagreement log;
7. stima di human ceiling e determinability rate per dominio.

Il fine-tuning scientifico resta bloccato finché regole principali, guideline, licenze,
privacy, autorizzazioni e separazione anti-leakage non sono approvate. Le correzioni UI
restano `candidate_annotations` con `training_eligible=false` finché il processo umano
non le promuove.

## Training, valutazione e calibrazione

Sul Mac supportato:

```bash
uv sync --extra dev --extra api --extra ml --locked
uv run ntruth-ml check
uv run ntruth-ml download-model --confirm-license-and-download
uv run ntruth-ml verify-model
uv run ntruth-ml tokenize local-data/prepared/corpus-v1 \
  --out local-data/prepared/corpus-v1/token-report.json
uv run ntruth-ml train local-data/prepared/corpus-v1 \
  --out models/runs/corpus-v1-seed13 --seed 13
```

Il trainer opera offline dopo il download, usa un modello base quantizzato a 4 bit,
LoRA sui proiettori Q/V, batch 1, gradient accumulation e checkpointing. Un controller
esterno esegue fasi da 100 iterazioni, valuta la validation, conserva il best adapter e
interrompe dopo la patience configurata. `--resume` richiede gli stessi checksum di
profilo, snapshot, lockfile e sorgenti della corsia ML.

La generazione richiede JSON puro, applica limite di token, parsing e validazione
`ParserAIOutput`; dopo un solo retry controllato, un output ancora invalido viene
rifiutato e conteggiato come tale. Le metriche includono schema-valid rate, exact
contract match, determinability accuracy/macro F1, precision/recall/F1 per categoria e
micro/macro per candidate facts. Temperature scaling, NLL, Brier, ECE e risk-coverage
usano esclusivamente la validation. Prima di calibrazione o export, il verificatore
ricostruisce gold e prediction dallo snapshot, ricalcola score, aggregati e confidence
observations e rifiuta anche artefatti alterati con checksum aggiornati.

I comandi completi di predict, calibrate, test ed export, insieme ai limiti del phased
training e al budget di memoria/disco, sono in
[mlx-training-pipeline.md](mlx-training-pipeline.md).

## Riproducibilità e pubblicazione

Ogni run registra automaticamente snapshot, seed, profilo, modello, runtime, lockfile,
fingerprint del codice e stato Git. Le versioni di schema/parser/guideline/ontologia e
gli split appartengono al dataset manifest e devono essere conservati insieme al run.
Lo schema v2 del run lega inoltre il checkpoint `best` ai checksum di adapter,
configurazione, snapshot e manifest. `export-adapter` richiede obbligatoriamente
metriche finali da `test` o `external` e una calibrazione ottenuta dalla validation del
medesimo run; ricalcola la calibrazione e verifica tutta la lineage prima di copiare
pesi LoRA, profilo, run state, manifest e report. Non copia pesi base o record di
training.

Non pubblicare dataset, sorgenti, annotazioni reali, modello base, adapter, cache o log
senza autorizzazione esplicita e una nuova verifica dei manifest. Il software corrente
non richiede token per analisi o training. Eventuali credenziali di repository o storage
appartengono a un keychain/secret manager, mai a `.env.example`, manifest, issue, log o
commit.
