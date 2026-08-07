# Struttura del repository

Questa mappa descrive il checkout software. Dati reali, documenti privati, modelli,
cache e checkpoint non fanno parte del repository pubblico.

## Mappa principale

| Percorso | Responsabilita |
|---|---|
| `packages/ntruth/` | Package Python, CLI, API e orchestrazione locale |
| `packages/ntruth/schemas/` | Contratti per documenti, manifest, grafo, conteggi, regole e report |
| `packages/ntruth/ingest/` | Progetti, release profile, checksum e safety gate |
| `packages/ntruth/storage/` | SQLite, migrazioni e blob store SHA-256 immutabile |
| `packages/ntruth/parsers/` | Parser D0 e parser estesi; codice statistico read-only |
| `packages/ntruth/sample_sheet/` | `SampleSheetSpec` v6, generator, validator e I/O CSV |
| `packages/ntruth/prospective/` | Contratto, compiler, piano/esecuzione riconciliati e sessioni effimere del percorso prospettico D0 |
| `packages/ntruth/extract/` | Segmentazione e baseline di estrazione deterministica |
| `packages/ntruth/graph/` | Costruzione, validazione, unit resolver e determinabilita |
| `packages/ntruth/verifier/` | Hard verifier e output policy |
| `packages/ntruth/rules/` | Predicati e rules engine deterministico |
| `packages/ntruth/design/` | Target, estimand e compilation del disegno |
| `packages/ntruth/corrections/` | Patch append-only, undo/redo, audit, export candidate e ricalcolo |
| `packages/ntruth/reporting/` | JSON, YAML, HTML, graph e output positivi |
| `packages/ntruth/governance/` | Licenze, consenso, privacy, lineage e split anti-leakage |
| `packages/ntruth/parser_ai/` | Dieci stage contract v6 e superficie legacy v2; nessun peso |
| `packages/ntruth/runtime_resources/` | Profili benchmark-derived, scheduling sequenziale, chunking, cache, fallback e telemetria |
| `packages/ntruth/training/` | Gold target contract, dataset preparation e tooling MLX locale |
| `packages/ntruth/api/` | API locale loopback |
| `packages/ntruth/cli/` | CLI `ntruth` |
| `packages/ntruth/release/` | Controlli e metadati di distribuzione |
| `apps/desktop/` | Client React/Vite locale; non e un servizio pubblico |
| `rulesets/` | Ruleset JSON versionati e revisionabili senza retraining |
| `ontology/` | Vocabolario/ontologia versionata |
| `tests/` | Unit, integration, security, property, performance e fixture sintetiche |
| `data/manifests/` | Soli inventari pubblicabili; nessun dato reale |
| `data/splits/` | Specifiche e futuri snapshot approvati degli split |
| `models/configs/` | Configurazioni versionate, incluse quelle MLX |
| `models/cards/` | Gate e card; nessun peso incluso |
| `scripts/` | Benchmark, SBOM e controlli di distribuzione |
| `docs/` | Specifica pubblica, architettura, governance, guideline, protocolli e ADR |
| `prd/` | PRD privato/istruttorio locale; non e automaticamente distribuibile |
| `.github/` | CI, policy e template di collaborazione |

## Separazione Train D / Train A

| Superficie | Train D | Train A |
|---|---|---|
| Input | `ingest`, parser D0, `sample_sheet` | Router/parser staged e formati progressivi |
| Rappresentazione | `schemas`, `graph`, `design` | `parser_ai.CandidateGraphSet` candidate-only |
| Decisione | `rules`, `verifier`, output policy | Nessun verdict del modello; riusa il confine Train D |
| Revisione | `corrections`, audit e revisioni | `HumanRevisionPatch`, doppia annotazione e adjudication |
| Dati | Fixture e futuro Derivation Gold | Parser Gold autorizzato, split e lineage |
| ML | Non richiesto | `training` e MLX dopo i gate |

Train D e implementato come fondazione software, ma non e ancora scientificamente
validato. Train A dispone di contratti e strumenti preparatori; non esistono nel
repository pesi N-Truth addestrati o metriche scientifiche su gold reale.

## Flusso delle dipendenze

`DocumentIR` e il confine dell'ingestione. L'estrazione costruisce candidate fact; il
graph builder le collega; il verificatore hard controlla gli invarianti; il rules
engine legge il grafo validato; determinabilita e output policy autorizzano o
sopprimono EU/n; reporting serializza senza introdurre nuovi fatti.

Il futuro parser AI termina a `CandidateGraphSet`. Parser Gold misura
documenti -> grafo; Derivation Gold misura grafo confermato -> conseguenze del
ruleset. La distinzione impedisce di attribuire al modello un errore del motore o
viceversa.

`sample_sheet` e disponibile tramite CLI/schema e viene compilato anche dal wizard
D0 attraverso la API prospettica. Un CSV generico accettato dall'ingest D0 non e
automaticamente un `SampleSheetSpec` valido: eseguire il validator dedicato prima
dell'analisi.

## Layout di un progetto locale

Quando `ntruth analyze` crea o riusa un progetto, il layout persistente e:

```text
workspace/project/
├── manifest.json
├── sources/
│   └── <copie sorgente registrate>
├── blobs/
│   └── sha256/
│       └── ab/
│           └── <digest SHA-256 completo>
└── ntruth.sqlite3
```

- `manifest.json` registra file, checksum, versioni e release profile.
- `sources/` conserva la copia compatibile usata dalla pipeline.
- `blobs/` conserva il contenuto immutabile e deduplicato per SHA-256.
- `ntruth.sqlite3` registra progetti, blob, revisioni, sessioni, run, audit e
  migrazioni.

Revisioni ed eventi di audit sono append-only a livello database. Il blob store non
sovrascrive un digest esistente. `ntruth verify` controlla sia la copia in `sources/`
sia il blob registrato.

## Profili di rilascio

- `d0_core` e il default ufficiale: `.txt`, `.md` e CSV semplice con virgole e righe
  rettangolari.
- `extended_experimental` abilita esplicitamente `.docx`, `.xml`, `.nxml`, `.jats`,
  `.pdf`, `.tsv`, `.xlsx`, `.r`, `.py` e `.rmd` oltre agli input D0.
- Il profilo esteso non implica validazione del parser o del disegno.
- Il release profile e persistito nel manifest; un mismatch in riapertura e
  rifiutato.

## Directory non versionate

- `workspace/`: progetti locali riapribili, SQLite e blob;
- `local-data/`: fonti, metadati privati, annotazioni e split candidati;
- `data/raw/`, `data/external/`, `data/processed/`: layout dati locali o legacy;
- `models/local/`, `models/cache/`: snapshot base e cache;
- `models/checkpoints/`, `models/runs/`, `models/adapters/`, `models/exports/`: pesi,
  adapter, log ed export;
- `ntruth-out/`, `dist/`, `apps/desktop/dist/`: artefatti ricostruibili.

Prima di un commit verificare almeno:

```sh
git status --short
git check-ignore -v --no-index local-data/ workspace/ models/local/ models/checkpoints/
```

Non aggiungere eccezioni a `.gitignore` per pubblicare dati o pesi senza una decisione
esplicita su licenza, privacy, provenienza e dimensione.

Vedere [architettura](architettura.md), [Core Profile D0](core-profile-d0.md),
[SampleSheetSpec v6](sample-sheet-v6.md) e
[contratto parser/verifier](parser-ai-contract.md).
