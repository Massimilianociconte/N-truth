# Troubleshooting

## `uv` o Python non disponibili

Verificare:

```bash
python3 --version
uv --version
```

N-Truth richiede Python 3.12 o successivo. Ricreare l'ambiente senza rimuovere dati:

```bash
uv sync --extra dev --extra api --locked
```

## Ruleset non trovato

Controllare le versioni incluse:

```bash
uv run ntruth rules list
```

`NTRUTH_RULESETS` è opzionale e contiene una o più directory separate da `:` su
macOS/Linux. Ha precedenza sui ruleset inclusi:

```bash
export NTRUTH_RULESETS="/percorso/assoluto/rulesets"
uv run ntruth rules list
```

N-Truth non carica automaticamente `.env`; un valore vuoto non va esportato.

## Nessun file utilizzabile

Formati supportati: TXT/Markdown, JATS/XML, DOCX, PDF con testo estraibile, CSV/XLSX,
R, Python e R Markdown. JSON generici, archivi e binari sconosciuti vengono scartati.
Usare un file sorgente preciso invece della cartella se la cartella contiene artefatti
di test o output.

## PDF scansionato o OCR degradato

Il parser PDF non esegue OCR. Un PDF senza testo estraibile deve essere convertito con
una pipeline OCR separata e revisionata; non rinominare un'immagine come PDF e non
trattare l'OCR come fonte gold senza controllo sul documento originale.

## Avviso sul dominio

`quantitative_microscopy` è rappresentato dal ruleset ma non ancora validato su external
set indipendente. L'avviso è previsto. L'acknowledgement conferma soltanto di aver letto
il limite:

```bash
uv run ntruth analyze SOURCE --out ntruth-out \
  --acknowledge-unvalidated-domain
```

## API non raggiungibile o porta occupata

L'API usa esclusivamente `127.0.0.1:8765`:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
uv run ntruth-api
curl --fail http://127.0.0.1:8765/v1/health
```

Se la porta è occupata, identificare il processo esatto prima di terminarlo. Non usare
`pkill` generici. L'host non è configurabile intenzionalmente nella baseline locale.

## UI assente o non aggiornata

Ricostruire gli asset prima di avviare l'API dal checkout:

```bash
pnpm --dir apps/desktop install --frozen-lockfile
pnpm --dir apps/desktop build
uv run ntruth-api
```

Aprire `http://127.0.0.1:8765/app/`. In sviluppo usare `pnpm --dir apps/desktop dev`
e aprire `http://127.0.0.1:5173/app/` mentre l'API è attiva.

## Distribuzione negata

`share_ready=false` e `redistribute_ready=false` sono il default corretto. Il comando
`distribution-check` richiede record, checksum, licenze e policy coerenti; non crea
permessi e non trasferisce file. Consultare [data-governance-v3.md](data-governance-v3.md).

## Una suite verde ma output scientifico dubbio

I test verificano contratti software e fixture sintetiche. Conservare l'output come
candidato, registrare il caso con evidenze e richiedere review scientifica. Non cambiare
una regola solo per far coincidere un singolo paper non adjudicato.

## `ntruth-ml check` termina con exit code 2

Il codice 2 indica che almeno un prerequisito operativo non è pronto, non un crash.
Leggere l'oggetto `checks`:

```bash
uv run ntruth-ml check
```

- `apple_silicon=false`: la corsia MLX è supportata solo su macOS arm64;
- `memory=false`: il profilo iniziale richiede 24 GiB di memoria unificata;
- `disk_download_headroom=false`: liberare spazio senza cancellare dataset o run non
  revisionati; il download deve lasciare almeno 50 GiB liberi;
- `runtime_version=false`: eseguire `uv sync --extra ml --locked`;
- `model_present=false`: eseguire il download esplicito soltanto dopo aver letto la
  licenza e il budget.

```bash
uv run ntruth-ml download-model --confirm-license-and-download
uv run ntruth-ml verify-model
```

Una directory modello parziale priva di `model-provenance.json` viene bloccata per
evitare di sovrascrivere file ambigui. Ispezionarla e conservarla finché non è chiaro
se il download vada ripreso o rifatto.

## Training MLX bloccato

Il training normale richiede `training_approved=true` e
`leakage_check_passed=true` nello snapshot. Non modificare a mano questi campi. Tornare
ai `SupervisedRecord`, completare licenze/review/privacy e rigenerare lo snapshot:

```bash
uv run ntruth-ml prepare /absolute/private/approved-records.jsonl \
  --out local-data/prepared/corpus-v1
```

Se la tokenizzazione restituisce exit code 2, almeno un record supera i 1.024 token del
profilo; segmentare per Experiment Block o preregistrare un nuovo profilo, senza
troncare silenziosamente evidence span e target.

## Out-of-memory, swap o run interrotto

Il profilo iniziale usa batch 1, otto layer LoRA e gradient checkpointing. Prima di
aumentare sequenza, layer o rank, eseguire un pilot breve e verificare il picco nel
`run-state.json`. Il controller interrompe oltre il limite osservato configurato di 18
GiB, ma il sistema operativo può usare memoria addizionale.

Riprendere soltanto la stessa directory, con codice, lockfile, profilo e snapshot
immutati:

```bash
uv run ntruth-ml train local-data/prepared/corpus-v1 \
  --out models/runs/corpus-v1-seed13 --seed 13 --resume
```

Se checksum di dati, sorgenti o lockfile sono cambiati, creare un nuovo run. Non
aggirare il blocco modificando `run-state.json`.

Snapshot e run creati con lo schema v1 non sono accettati da training, inferenza o
export. Rigenerare lo snapshot dai `SupervisedRecord` approvati e avviare un nuovo run
schema v2; non migrare a mano manifest, split o checksum.

## Output del modello non è JSON valido

La corsia MLX non usa un decoder grammar-constrained. `predict` esegue un solo retry di
formato, poi rifiuta l'output. Controllare `predictions.jsonl`,
`invalid_output_count` e `schema_valid_rate`; non riparare automaticamente fatti
scientifici e non escludere gli errori dal denominatore.

La guida completa è [mlx-training-pipeline.md](mlx-training-pipeline.md).

## Calibrazione o export MLX rifiutati

La prediction deve usare il file manifestato corretto: `valid.jsonl` per validation,
`test.jsonl` per test ed `external.jsonl` per external. Il comando non accetta un file
rinominato o uno split dichiarato diverso. Conservare insieme `predictions.jsonl`,
`confidence-observations.jsonl` e `metrics.json`.

L'export richiede obbligatoriamente:

- adapter `best` di un run schema v2 completato;
- manifest dello snapshot di training del run;
- calibrazione calcolata sulla validation dello stesso run;
- metriche finali dal test dello stesso snapshot oppure da external indipendente,
  sempre valutato con lo stesso run e adapter.

Se un checksum o una lineage non coincide, rigenerare l'artefatto dal suo comando
originario. Non correggere JSON, path o hash manualmente.
