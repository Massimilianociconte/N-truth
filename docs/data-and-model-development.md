# Dati, annotazione e sviluppo del modello

## Stato verificabile al 13 agosto 2026

Il target normativo corrente è **PRD v9**. Il contratto implementato nel root è
**PRD v7**; la conformance v9 resta
`BLOCKED_PENDING_CANONICAL_REGISTRY`. Questa differenza è un gate, non una
formalità documentale: adapter e trainer non devono inventare classi v9 mancanti.

La pipeline pubblica di acquisizione, normalizzazione, audit e manifest è operativa,
ma non esiste ancora uno snapshot N-Truth autorizzato al training. Tutti i record dei
quattro corpus pubblici sono `training_eligible=false` ed
`evaluation_eligible=false`. Sotto
`/Volumes/FLASH128/N-Truth-Datasets/training_ready/` non esistono file o record
training-ready; possono restare directory strutturali senza contenuto eleggibile. Gli
artefatti legacy sono stati messi in quarantena.

I tree raw da archivi pubblici usano marker
`ntruth.authenticated-raw-marker.v1`, legati al source lock e a un commitment
`ntruth.raw-tree-commitment.v1`. Marker legacy o tree modificati non autorizzano il
resume: la pipeline re-estrae dall'archivio pinned e riscrive il marker autenticato.

La decisione corrente, materializzata nell'artefatto machine-readable finale, è:

- destinazione canonica
  `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/training-readiness.final.json`;
- `overall=NOT_READY`;
- `substantive_training_allowed=false`;
- `scientific_validation=NOT_STARTED`;
- `data_readiness=BLOCKED`.

Il profilo Granite ha stato `configuration_defined_execution_blocked`, ruolo
`provisional_primary_train_a`, `runtime_qualification_status=NOT_RUN_CURRENT_PROFILE`
e `scientifically_selected=false`. Il modello locale non è presente e nessuna
baseline reale è stata eseguita. La decisione completa è in
[TRAINING-READINESS-small-model-20260813.md](training/TRAINING-READINESS-small-model-20260813.md).

## Architettura degli artefatti

La pipeline conserva quattro livelli distinti:

```text
raw immutabile
→ processed canonical acquisition envelope
→ validated task-specific snapshot
→ training view autorizzata e priva di split protetti
```

La root esterna corrente è `/Volumes/FLASH128/N-Truth-Datasets/`:

```text
raw/                 # snapshot upstream immutabili
downloads/           # archivi pinned
processed/           # envelope normalizzati, non training-ready
task_corpora/         # adapter ausiliari con manifest e lineage
training_ready/       # nessun file/record eleggibile finché il gate non apre
quarantine/           # artefatti legacy o non conformi
manifests/            # lock, Merkle, licenze e report
```

Modelli, adapter e run restano sotto `models/local/`, `models/runs/` e
`models/exports/`, ignorati da Git. Il modello non va collocato sul volume dei dati se
ciò spezza i path e i checksum fissati dal profilo.

## Corpus pubblici

I corpus pubblici sono **SILVER_AUXILIARY**, anche quando l'annotazione upstream è
descritta come human-curated gold. Tale attributo non li promuove a N-Truth GOLD.

| Corpus | Artefatto di audit | Stato model use |
|---|---|---|
| SourceData | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/quality/sourcedata.json` | bloccato: identità documentale incompleta, group leakage conservativo e license scope non chiuso |
| PreClinIE | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/quality/preclinie.json` | bloccato: diritti del testo e adapter canonico non approvati; indicatori di rigore non sono verdict N-Truth |
| MeasEval | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/quality/measeval.json` | bloccato: license scope e annotazioni mancanti; gli split vengono derivati solo per isolamento ingegneristico |
| CRAFT | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/quality/craft.json` | bloccato: tutti i 97 record richiedono review e il testo segue licenza PMC per articolo |

Le decisioni fonte-per-fonte sono in
[source-portfolio-small-model-v1.md](training/source-portfolio-small-model-v1.md).

Il corpus ausiliario SourceData già adattato è materializzato in
`/Volumes/FLASH128/N-Truth-Datasets/task_corpora/entity_roles/sourcedata/v2.0.3/`.
Il relativo `manifest.json` dichiara esplicitamente
`model_use_status=BLOCKED`, `data_readiness=BLOCKED`,
`ntruth_partition_approved=false` e
`reality_gate_satisfied_by_public_corpora=false`.

## Provenance e tier

Per ogni asset sono obbligatori source/revision, SHA-256, retrieval, documento e
sezione, parent checksum, trasformazione, schema, tier, decisione di licenza e
leakage group. Le autorizzazioni restano granulari:

```text
inspect != annotate != develop != train != evaluate != publish != redistribute
```

Un campo mancante o `unknown` fallisce chiuso. `NativeAnnotationTier` descrive
l'annotazione upstream; l'autorità N-Truth è espressa separatamente da
`AuthorityLevel` e `SupervisionSource`.

- GOLD: soltanto `NTRUTH_GOLD` con review indipendente, adjudication, provenance e
  rights completi;
- SILVER: `AUXILIARY`, con target scientifici vietati;
- WEAK: `WEAK_RULE`, regola e confidence versionate;
- SYNTHETIC: lineage del generatore e uso train/stress soltanto;
- CANDIDATE: quarantena o review-required, mai promozione implicita.

## Contratto supervisionato

`ntruth.training.SupervisedRecord` resta il confine del futuro corpus supervisionato
PRD v7. Un record candidate o single-reviewed non può essere training eligible;
double-reviewed richiede due reviewer e adjudicated richiede un adjudication ID.

Questo contratto non dimostra conformance PRD v9. Prima di materializzare nuovo GOLD
occorre congelare il registry v9 e definire una migrazione esplicita. Parser e LLM
producono candidate structure; non trasformano output modello in Derivation Gold.

## Deduplica e split

La separazione futura avviene per famiglia indivisibile, mai per riga:

- DOI, PMCID, PMID e tutte le versioni/correzioni;
- abstract, Methods, caption, tabelle e supplementi;
- dataset, sample sheet, codice e accessioni collegati;
- laboratorio/corresponding author quando identificabile;
- tutte le trasformazioni e parafrasi della stessa famiglia.

La deduplica esatta, near e semantic-family precede lo split. Un'identità ignota non
viene sostituita con un ID di riga per simulare indipendenza. Test ed external devono
essere custoditi separatamente e non leggibili da training, tokenizzazione,
retrieval, calibration o model selection.

Lo snapshot preparato completo è un **custody snapshot**, non l'input del trainer.
Una training view fisicamente separata può contenere soltanto train e validation,
mentre test/external restano nel protected vault. Anche questa view non è oggi un
input ML eseguibile: manca un runner che consegni a MLX soltanto file descriptor
read-only anonimi/unlinked ereditati, eliminando il path reopen dopo la validazione. I
dettagli sono in
[mlx-training-pipeline.md](mlx-training-pipeline.md).

## Annotazione e gold futuro

Il gate richiede dati reali N-Truth e non può essere soddisfatto dai corpus pubblici.
Servono almeno:

1. registry/schema/Rulebook PRD v9 congelati;
2. real anchor con campi decisivi doppiamente annotati;
3. agreement misurato prima dell'adjudication;
4. adjudication e lineage per ogni caso;
5. licence/privacy scope verificato;
6. split bundle/lab-aware congelati;
7. test ed external affidati a un custode indipendente;
8. protocollo baseline ed H/A/H+A preregistrato.

I casi ambigui restano indeterminati. Menzioni di randomizzazione, numerosità,
repliche o unità non vengono convertite automaticamente in allocation level,
experimental unit o independent n.

## Readiness, runtime e autorizzazione

I soli comandi sicuri nello stato corrente sono diagnostici:

```bash
uv sync --extra dev --extra api --extra ml --locked
uv run ntruth-ml readiness
uv run ntruth-ml check \
  --profile models/configs/granite-4.1-3b-mlx-qlora.json \
  --repo "$(pwd)"
```

`readiness` termina con codice `2` finché lo stato è `NOT_READY`. Il doctor finale ha
destinazione canonica
`/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/granite-doctor.final.json`:
la verifica finale indica MLX-LM `0.31.3`, Apple Silicon e budget disco/memoria
passanti, ma
`model_present=false` e `ready_to_train=false`. Il doctor deve restare
`ready_to_train=false` anche dopo un eventuale download finché manca il runner FD.

Tokenizzazione, training, smoke, prediction, metriche, calibrazione, resume,
checkpoint ed export sono tutti fail-closed. L'autorizzazione futura non è un bare
`RealityGateResult`: è un envelope canonico v1 legato esattamente a training view,
seal, profilo, repository/revisione modello, source snapshot e seed. Anche un envelope
valido non supera il blocker FD.

## Evaluation prima del training

Non sono state eseguite baseline reali. Il protocollo congelabile è in
[baseline-evaluation-protocol-v1.md](training/baseline-evaluation-protocol-v1.md) e
richiede:

- rules-only;
- base zero-shot e few-shot;
- retrieval/context enrichment;
- ModernBERT specialist;
- confronto no-adapter tra Granite, Qwen e Phi;
- condizioni H, A e H+A;
- schema-validity, exact match, precision/recall/F1, macro-F1 per classe,
  calibration, risk-coverage, OOD, failure taxonomy e correction burden.

Il fine-tuning ha senso soltanto se supera la migliore baseline preregistrata senza
peggiorare false certainty, calibrazione, OOD o burden umano. La training loss non è
un endpoint decisionale.

## Riproducibilità e pubblicazione

Ogni futuro run dovrà legare commit, dirty state, dataset/view/seal hash,
registry/schema, model/tokenizer revision, profilo, seed, ambiente, hardware,
authorization envelope, descriptor commitments, checkpoint e metriche. Oggi nessun
run-state o checkpoint corrente viene prodotto. L'hardening dei quality report e del
task corpus SourceData ha invalidato il precedente fingerprint: refresh e resume
finali devono essere rigenerati. Il solo fingerprint da citare sarà quello scritto nel
nuovo `/Volumes/FLASH128/N-Truth-Datasets/manifests/checksums/merkle_manifest.json` e
confermato dai nuovi `final-refresh.log` / `final-resume.log` nella directory
readiness; questo documento non ne anticipa il valore.

Un Merkle valido prova integrità degli artefatti inclusi, non licenza, qualità
scientifica, assenza di contamination o training readiness. Non pubblicare dati,
annotazioni, pesi, adapter, prediction o log senza una distinta review di
distribuzione.
