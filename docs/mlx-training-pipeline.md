# Pipeline locale MLX/Metal — specifica bloccata

## Stato corrente

Questa guida descrive il contratto futuro per un fine-tuning locale su Apple Silicon.
**Non è una procedura eseguibile.** Il runtime corrente fallisce chiuso per ogni
operazione ML che potrebbe leggere dati dopo la validazione:

- tokenizzazione, incluso lo smoke;
- training sostanziale e training smoke;
- ripresa, checkpoint ed early stopping;
- prediction validation, test o external;
- produzione o verifica di metriche;
- calibrazione;
- export dell'adapter.

Il blocker canonico del codice è:

```text
operazione MLX bloccata: isolamento post-validazione non FD-safe;
serve un runner privato che consumi esclusivamente file descriptor read-only
anonimi/unlinked ereditati
```

Il blocco resta attivo anche se hardware, runtime, modello, dataset e autorizzazione
fossero validi. `ntruth-ml check` restituisce sempre `ready_to_train=false` e include
il blocker FD in `execution_blockers`. `operational_prerequisites_passed=true`, se mai
osservato, significherebbe soltanto che i prerequisiti tecnici non-FD passano; non
autorizzerebbe l'esecuzione.

Il profilo corrente registra esattamente:

- `status=configuration_defined_execution_blocked`;
- `runtime_qualification_status=NOT_RUN_CURRENT_PROFILE`;
- `synthetic_train_only=true`;
- blocker `anonymous_unlinked_inherited_fd_runner`.

Questi valori non descrivono uno smoke Granite eseguito: nessuna qualifica runtime del
profilo corrente è stata effettuata.

La decisione scientifica resta
[NOT READY](training/TRAINING-READINESS-small-model-20260813.md): PRD v9 è il target
normativo, il root implementa PRD v7, il registry v9 non è canonico, i corpus pubblici
sono model-ineligible, le baseline non sono state eseguite e il modello locale è
assente.

## Operazioni ammesse oggi

Sono ammesse soltanto ispezione, diagnostica e test software che non avviano MLX su
dataset o fixture:

```bash
uv run ntruth-ml readiness
uv run ntruth-ml check \
  --profile models/configs/granite-4.1-3b-mlx-qlora.json \
  --repo "$(pwd)"
```

Entrambi possono terminare con codice `2`; nello stato corrente è il risultato
corretto. Non trasformare l'output, non rimuovere `execution_blockers` e non usare un
wrapper che ignori l'exit code.

La preparazione e il freeze dei dati possono essere verificati come trasformazioni di
governance separate, ma non rendono eseguibili tokenizzazione, training o evaluation.
Il download o la verifica dei pesi, se autorizzati per una necessità ingegneristica
distinta, non aprono il gate ML e non costituiscono selezione del modello.

## Perché la training view non basta

Il custody snapshot schema `2.0.0` contiene train, validation, test, external e la
lineage completa. `freeze-training-view` può materializzare una root isolata con:

```text
training-view/
├── train.jsonl
├── valid.jsonl
├── training-records.jsonl
├── training-view-manifest.json
└── protected-split-seal.json
```

Manifest e seal usano schema `1.0.0`. La view rifiuta file extra, symlink, split
protetti e relazioni antenato/discendente col custody. Questi controlli impediscono
molti errori, ma un path verificato può ancora essere sostituito o mutato prima che un
processo MLX lo riapra. Validare un pathname e poi passare quel pathname a un altro
loader non lega i byte validati ai byte effettivamente consumati.

Per questo motivo la sola training view non autorizza alcuna lettura ML. Il confine
richiesto è il file descriptor già aperto sugli stessi byte verificati.

## Runner FD richiesto

Prima di riabilitare qualunque operazione ML deve esistere un runner privato che:

1. apre e valida soltanto file regolari, senza seguire symlink;
2. lega checksum, dimensione, record ID e manifest ai byte effettivamente aperti;
3. copia o materializza i byte approvati in file descriptor read-only
   anonimi/unlinked;
4. eredita nel processo ML soltanto quei descriptor e non i path sorgente;
5. costruisce dataset e tokenizer input esclusivamente dai descriptor ereditati;
6. impedisce al child di enumerare o riaprire custody, training view e protected vault;
7. espone soltanto train/validation all'operazione autorizzata;
8. mantiene output, log e checkpoint fuori dalla root dati;
9. chiude e invalida i descriptor dopo l'uso;
10. prova con test avversariali che sostituzioni, mutation race, symlink e path reopen
    non cambino i byte consumati.

La scelta tecnica concreta deve essere compatibile con macOS e MLX-LM e va revisionata
separatamente. Un temporary path privato, un file copiato ma ancora nominato o un
directory FD non soddisfano da soli il requisito. Nessun flag CLI, authorization o
checksum del path può sostituire questo runner.

## Matrice di disponibilità

| Operazione | Stato corrente | Condizione minima futura |
|---|---|---|
| `readiness` | diagnostica eseguibile | nessuna; resta fail-closed |
| `check` | diagnostica eseguibile, sempre `ready_to_train=false` | runner FD implementato e verificato prima di cambiare il valore |
| `prepare` / `freeze-training-view` | trasformazione dati, non ML readiness | review dei relativi artefatti |
| `tokenize` | **BLOCCATA** | tokenizer alimentato solo da FD anonimi/unlinked verificati |
| `train` | **BLOCCATA** | runner FD + readiness scientifica + authorization envelope v1 |
| `train --runtime-smoke-only` | **BLOCCATA** | stesso runner FD; nessuna eccezione smoke |
| `train --resume` | **BLOCCATA** | runner FD e protocollo resume nuovamente progettato/testato |
| `predict --split validation` | **BLOCCATA** | runner FD e lineage validation verificata |
| test/external prediction | **BLOCCATA** | runner FD + permit monouso + ledger + attestation |
| metriche/calibrazione | **BLOCCATA** | lettura FD-safe degli artefatti e lineage verificabile |
| `export-adapter` | **BLOCCATA** | protected evaluation attestata e bundle verificato end-to-end |

La presenza dei comandi nell'help della CLI documenta l'interfaccia e il comportamento
fail-closed, non una capability operativa.

## Authorization envelope v1

Il training sostanziale futuro non accetterà un `RealityGateResult` nudo. Richiederà
un envelope canonico, schema `1.0.0`, con esattamente:

```json
{
  "schema_version": "1.0.0",
  "artifact_type": "ntruth-training-authorization-envelope",
  "gate": {
    "checksum": "<checksum canonico RealityGateResult>",
    "purpose": "SUBSTANTIVE_TRAINING"
  },
  "binding": {
    "training_view_id": "<id content-addressed>",
    "training_view_sha256": "<sha256>",
    "protected_split_seal_sha256": "<sha256>",
    "profile_sha256": "<sha256>",
    "model_repository": "<repository MLX fissato>",
    "model_revision": "<revisione immutabile>",
    "source_snapshot_sha256": "<fingerprint sorgenti codice/lock del run>",
    "seed": 13
  },
  "checksum": "<checksum canonico dell'envelope>"
}
```

Il blocco `gate` reale deve essere il `RealityGateResult` machine-readable completo,
non l'estratto illustrativo sopra. Deve avere:

- `purpose=SUBSTANTIVE_TRAINING`;
- `substantive_training_allowed=true`;
- data readiness `READY`;
- nessun blocker;
- proiezione normativa PRD v9 complessivamente `READY`.

Il binding deve contenere **esattamente** gli otto campi mostrati. Campo mancante,
campo extra, checksum non canonico, seed diverso, modello/revisione diversa, view/seal
diversi, profilo diverso o source snapshot diverso fanno fallire il comando. Un bare
Reality Gate viene rifiutato esplicitamente.

Questo envelope è necessario ma non sufficiente: anche un envelope perfetto incontra
oggi il blocker FD. Non crearne uno manualmente per provare ad aprire il training.

## Profilo tecnico provvisorio

Il profilo versionato è
[`models/configs/granite-4.1-3b-mlx-qlora.json`](../models/configs/granite-4.1-3b-mlx-qlora.json).
Granite è un **primary tecnico provvisorio**, non una selezione scientifica.

| Proprietà | Valore fissato |
|---|---|
| Modello sorgente | [`ibm-granite/granite-4.1-3b`](https://huggingface.co/ibm-granite/granite-4.1-3b) |
| Revisione sorgente | `c0650403e44e78ec0262dab1c90914c65b196c4e` |
| Conversione MLX community | [`mlx-community/granite-4.1-3b-4bit`](https://huggingface.co/mlx-community/granite-4.1-3b-4bit) |
| Revisione MLX | `b1b476b5a17c46b7d6cd663b4a8ed44b66720aef` |
| Parametri sorgente | 3.402.836.480 |
| Quantizzazione | 4 bit |
| Licenza modello | Apache-2.0 |
| Modello locale previsto | `models/local/granite-4.1-3b-4bit/`, assente |
| Context operativo pianificato | 1.024 token |
| Batch / accumulation pianificati | 1 / 8 |
| LoRA rank / scale / dropout | 16 / 32 / 0,05 |
| Layer adattati | ultimi 8 |
| Peak MLX-LM massimo pianificato | 18 GiB |

Le proiezioni LoRA coprono Q/K/V/O attention e gate/up/down MLP. Sono parametri di un
esperimento futuro, non prova di compatibilità runtime. La licenza del modello non
concede diritti sui documenti del dataset.

Alternative da mantenere nel torneo no-adapter:

| Candidato | Ruolo |
|---|---|
| Granite 4.1 3B | primary provvisorio extraction/classification-first |
| Qwen3 4B Instruct 2507 | challenger generativo |
| Phi-4 mini instruct | challenger compatto |
| ModernBERT-base | specialist extraction baseline, non graph generator |

Nessun candidato è stato confrontato sulla validation N-Truth congelata.

## Fattibilità Apple Silicon

Il target resta MacBook Pro M5 Pro, 24 GiB di memoria unificata. Il profilo richiede:

- macOS `arm64` e Metal;
- MLX-LM `0.31.3`;
- almeno 24 GiB di memoria unificata;
- almeno 40 GiB liberi;
- workspace N-Truth massimo pianificato 40 GiB;
- budget simultaneo stimato 35,3 GiB.

Questi controlli sostengono soltanto `apple_silicon_feasibility=PASS`. Non dimostrano
che un run completo sia sostenibile e non cambiano il blocker FD. Il doctor del 13
agosto 2026 aveva già riportato modello assente; il runtime corrente aggiunge inoltre
il blocker di esecuzione e non può mai riportare readiness al training.

Riferimenti ufficiali:

- [MLX](https://github.com/ml-explore/mlx);
- [installazione MLX](https://ml-explore.github.io/mlx/build/html/install.html);
- [MLX-LM](https://github.com/ml-explore/mlx-lm);
- [guida LoRA/QLoRA MLX-LM](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md).

## Dataset e split futuri

Il futuro input supervisionato resta `SupervisedRecord` schema `1.0.0`, con
`ParserAIInput`/`ParserAIOutput` v2, provenance, licenza/autorizzazione, almeno doppia
review e `training_eligible=true`. Questo contratto implementa il confine PRD v7 e non
dimostra conformance PRD v9.

La preparazione deve continuare a:

1. validare schema ed eligibility;
2. normalizzare senza mutare l'originale;
3. deduplicare esatto, near e per famiglia semantica;
4. tenere nello stesso gruppo paper, versioni, supplementi, dataset, laboratorio e
   trasformazioni correlate;
5. separare train/validation da test/external prima di qualsiasi model selection;
6. produrre custody e training view content-addressed.

Tutti i corpus pubblici correnti restano `SILVER_AUXILIARY` e hanno zero record
training/evaluation-eligible. Nessuno di essi può essere usato per provare il runner.

## Operazioni future non eseguibili

I seguenti esempi descrivono soltanto l'interfaccia da rivalidare **dopo**
l'implementazione del runner FD e l'apertura di tutti i gate. Non devono essere
eseguiti nello stato corrente:

```bash
# FUTURE / NON ESEGUIBILE OGGI
uv run ntruth-ml tokenize "$NTRUTH_TRAINING_VIEW" \
  --out "$NTRUTH_TOKEN_REPORT" \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"

# FUTURE / NON ESEGUIBILE OGGI
uv run ntruth-ml train "$NTRUTH_TRAINING_VIEW" \
  --out "$NTRUTH_RUN" \
  --seed 13 \
  --training-authorization "$NTRUTH_AUTHORIZATION_ENVELOPE" \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"

# FUTURE / NON ESEGUIBILE OGGI
uv run ntruth-ml predict "$NTRUTH_TRAINING_VIEW/valid.jsonl" \
  --adapter "$NTRUTH_RUN/best" \
  --out "$NTRUTH_VALIDATION_EVAL" \
  --split validation \
  --profile "$NTRUTH_PROFILE" \
  --repo "$NTRUTH_REPO"
```

Le firme potrebbero cambiare quando il runner sarà implementato. La loro presenza qui
non promette checkpoint, metriche, calibrazione, resume o export.

## Smoke

Non esiste più un'eccezione eseguibile per lo smoke. La presenza dell'interfaccia
`make-smoke-data` nella CLI non è una smoke capability, non autorizza l'invocazione di
MLX e non costituisce evidenza. In ogni caso:

- `tokenize --runtime-smoke-only` fallisce col blocker FD;
- `train --runtime-smoke-only` fallisce col blocker FD;
- prediction e calibrazione smoke falliscono col blocker FD;
- nessun nuovo run-state, checkpoint, loss o metrica smoke viene prodotto.

Eventuali risultati smoke storici appartengono ad architetture precedenti e non
qualificano il runtime corrente. Non vanno ripetuti, confrontati o citati come evidenza
di readiness.

## Prediction, metriche e calibrazione

La validation resta l'unico split concepibile per model selection, ma oggi anche
`predict --split validation` fallisce prima di caricare modello o adapter. Di
conseguenza:

- non vengono generate nuove `predictions.jsonl`;
- non vengono generate o verificate nuove `metrics.json`;
- non vengono generate confidence observations;
- non viene eseguito temperature scaling o risk-coverage fitting;
- la training loss non può essere prodotta né usata come sostituto.

Il protocollo di metriche strutturate, calibrazione, per-class, OOD e H/A/H+A resta
definito in
[baseline-evaluation-protocol-v1.md](training/baseline-evaluation-protocol-v1.md), ma
non è stato eseguito.

## Protected evaluation ed export

Test ed external richiedono, oltre al runner FD:

- vault fisicamente separato;
- permit monouso legato a split, seal, adapter, run, modello, calibration e protocollo;
- Reality Gate e approvazione del custode;
- ledger append-only con reservation prima del primo byte protetto;
- consumo permanente del permit anche su crash;
- attestation e output hash verificabili senza riaprire il gold.

Questa infrastruttura non esiste. L'export finale resta quindi doppiamente bloccato:
nessun run/metric/calibration corrente e nessuna protected attestation. Non assemblare
bundle manuali.

## Run-state, resume e checkpoint

`RUN_SCHEMA_VERSION` è `5.0.0`, ma il percorso corrente non crea un nuovo run-state:
il training si arresta al blocker FD. Il resume viene rifiutato esplicitamente prima
di aprire il dataset o invocare il doctor. Un vecchio run-state non rende disponibile
la ripresa e non va migrato a mano.

Quando il runner esisterà, il contratto di run dovrà registrare almeno:

- authorization envelope e binding completi;
- training view, seal, profilo, modello, source snapshot e seed;
- commit e dirty state;
- ambiente software/hardware;
- descriptor/byte commitments senza path reopen;
- configurazione, checkpoint e metriche prodotte dal futuro runner.

Questo elenco è una specifica futura, non la descrizione di artefatti prodotti oggi.

## Verifica del comportamento fail-closed

La suite mirata non scarica modelli e deve provare il rifiuto delle operazioni ML:

```bash
uv run pytest -q \
  tests/unit/test_mlx_training_pipeline.py \
  tests/unit/test_mlx_snapshot_integrity.py \
  tests/unit/test_mlx_evaluation_lineage.py \
  tests/unit/test_mlx_blind_training_view.py \
  tests/unit/test_mlx_training_authorization.py \
  tests/unit/test_training_readiness_gate.py \
  tests/unit/test_training_dedup_split_integrity.py
```

Test software verdi dimostrano soltanto il blocco e i contratti. Non dimostrano
tokenizzazione, training, prediction, calibrazione, export o qualità scientifica.

## Gate per riaprire l'esecuzione

Prima di rimuovere il blocker FD devono essere veri **tutti** questi punti:

1. runner anonimo/unlinked inherited read-only FD implementato;
2. test avversariali TOCTOU, symlink, mutation e path-reopen verdi;
3. integrazione MLX/tokenizer che consuma soltanto i descriptor approvati;
4. security review indipendente del confine;
5. registry/schema/Rulebook PRD v9 canonici;
6. dataset GOLD, licenze e split protetti approvati;
7. baseline e selezione modello completate;
8. authorization envelope v1 esatto per il singolo run;
9. nuovo smoke minimale esplicitamente autorizzato come prima esecuzione;
10. rivalutazione della readiness e nuova documentazione verificata.

Fino ad allora:

```text
scientific readiness       FAIL
dataset readiness          FAIL
schema readiness           FAIL
evaluation readiness       FAIL
infrastructure readiness   PARTIAL
Apple Silicon feasibility  PASS
reproducibility            FAIL
overall                    NOT READY
```

Tutti i dati, pesi, adapter, run, checkpoint, prediction e output futuri devono
restare fuori Git e richiedono una review di distribuzione distinta.
