# Desktop application

La UI React/Vite è servita dall'API FastAPI esclusivamente su loopback in `/app/`. Offre
import da percorso locale, navigazione per `ExperimentBlock`, grafo, evidenza sincronizzata,
elicitazione e conferma del target inferenziale, correzioni append-only con undo/redo, ricalcolo
e download degli export registrati nella sessione. La conferma del target passa dalla stessa
traccia di audit delle altre correzioni e non viene promossa automaticamente a gold.

## Sviluppo

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Il dev server inoltra `/v1` a `127.0.0.1:8765`. Il build di produzione viene incluso nel wheel:

```bash
pnpm test
pnpm build
```

La schermata iniziale usa soltanto dati sintetici marcati come demo; non rappresenta un risultato
scientifico. Un wrapper Tauri firmato/notarizzato resta un deliverable separato: la web UI locale
non prova packaging, firma, notarizzazione o release macOS.
