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
