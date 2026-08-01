# Struttura del repository

Questa mappa descrive il checkout software. I dati locali reali non fanno parte del
repository e devono vivere in `local-data/`, ignorata da Git.

| Percorso | Responsabilità |
|---|---|
| `packages/ntruth/` | package Python, CLI, API, pipeline e contratti |
| `packages/ntruth/parsers/` | parser TXT/Markdown, JATS, DOCX, PDF, CSV/XLSX e codice read-only |
| `packages/ntruth/graph/` | costruzione, validazione, unità e determinabilità del grafo |
| `packages/ntruth/rules/` | caricamento ed esecuzione deterministica delle regole |
| `packages/ntruth/design/` | design specification, elicitazione e analysis handoff strutturale |
| `packages/ntruth/corrections/` | patch append-only, undo/redo, audit e ricalcolo |
| `packages/ntruth/governance/` | licenze, consenso, lineage, privacy e gate fail-closed |
| `packages/ntruth/parser_ai/` | contratto JSON del futuro parser AI; nessun backend attivo |
| `packages/ntruth/reporting/` | JSON, YAML, HTML, JSON-LD/RO-Crate e output positivo |
| `apps/desktop/` | UI React/Vite servita localmente dall'API |
| `rulesets/` | ruleset JSON versionati e revisionabili senza retraining |
| `ontology/` | vocabolario/ontologia versionata |
| `tests/` | unit, integration, security, property, performance e fixture sintetiche |
| `data/manifests/` | soli inventari pubblicabili; nessun dato reale |
| `data/splits/` | documentazione e futuri snapshot di split approvati |
| `models/configs/` | configurazioni dichiarative; non avviano training |
| `models/cards/` | gate e card dei futuri modelli |
| `scripts/` | benchmark, SBOM e controlli di distribuzione |
| `docs/` | architettura, governance, guideline, protocollo e ADR |
| `.github/` | CI e template di collaborazione |

## Flusso delle dipendenze

`DocumentIR` è il confine dell'ingestione. Il rules engine legge esclusivamente il
grafo validato e non il testo grezzo. Le correzioni producono nuove revisioni; non
riscrivono le fonti né gli export precedenti. La UI usa gli stessi casi d'uso della CLI
e dell'API.

## Directory non versionate

- `workspace/`: progetti locali riapribili;
- `local-data/`: fonti, metadati privati, annotazioni e split candidati;
- `data/raw/`, `data/external/`, `data/processed/`: eventuali layout legacy locali;
- `models/checkpoints/`, `models/runs/`: pesi e log;
- `dist/`, `apps/desktop/dist/`: artefatti ricostruibili.

Prima di un commit verificare sempre `git status --short` e `git check-ignore` sui
percorsi dati attesi.
