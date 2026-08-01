# Procedura di release software

Questa procedura produce artefatti software; non chiude i gate scientifici.

## Preflight

```bash
git status --short
uv lock --check
pnpm --dir apps/desktop install --frozen-lockfile
uv sync --extra dev --extra api --locked
```

Verificare versioni coerenti in `pyproject.toml`, `packages/ntruth/__init__.py`,
`CITATION.cff`, changelog e card. Le versioni di schema, parser, ruleset e ontologia
possono avanzare indipendentemente.

## Gate riproducibili

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run pytest
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build
uv run python scripts/generate_sbom.py --check sbom.cdx.json
uv build
uv run python scripts/check_distribution.py
uv run python scripts/smoke_release.py
uv run ntruth-ml --help
```

`pnpm build` deve precedere `uv build`, perché il wheel include gli asset UI. Ispezionare
la wheel prima del tag. `check_distribution.py` rifiuta cache, dati locali, `.env` e
materiale di chiave; `smoke_release.py` installa separatamente wheel e sdist in ambienti
temporanei puliti, vincola le dipendenze a `uv.lock` e verifica CLI, ruleset e
`/v1/health`. Usa `--offline` soltanto quando una wheel cache completa è disponibile;
un ambiente già sincronizzato non equivale a una wheelhouse offline.

`sbom.cdx.json` è dichiaratamente un inventario completo dei due lockfile di sviluppo:
include dipendenze opzionali/dev e tool UI, quindi non va descritto come SBOM minimale
del solo runtime installato.

Su macOS arm64 la CI e il gate locale installano inoltre wheel e sdist con `[api,ml]`
in ambienti puliti, senza scaricare il modello:

```bash
uv run python scripts/smoke_release.py --include-ml
```

Questo verifica la risoluzione bloccata di MLX-LM 0.31.3, l'import del runtime, la CLI
e il profilo incorporato. Lo smoke QLoRA con pesi locali resta un gate hardware
separato e non deve essere eseguito automaticamente in CI.

La release non scarica modelli. Verificare che `models/local/`, `models/runs/`,
`models/exports/` e `local-data/` siano ignorati, che nessun `*.safetensors` sia
tracciato e che wheel/sdist contengano soltanto il profilo JSON e il codice della corsia
ML opzionale.

## Pubblicazione

- aggiornare `CHANGELOG.md` senza presentare target come risultati;
- creare un commit firmato se la configurazione locale lo consente;
- usare push fast-forward, mai `--force` sul branch protetto;
- attendere CI macOS/Linux;
- pubblicare checksum e SBOM insieme agli artefatti;
- non allegare corpus, annotazioni, checkpoint o documenti sorgente.

Una release può essere marcata “software alpha”. Le diciture “scientificamente
validata”, “gold”, “DRIVER-compliant” o equivalenti richiedono le evidenze esterne
elencate nel protocollo di validazione.
