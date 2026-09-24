# Struttura del repository

Questa mappa descrive il checkout software post-merge, che contiene sia i moduli del
core deterministico pre-v8 sia i contratti v8/v9. I dati locali reali non fanno parte
del repository e devono vivere in `local-data/`, ignorata da Git.

## Mappa principale

| Percorso | Responsabilità |
|---|---|
| `packages/ntruth/` | package Python, CLI, API, pipeline e contratti |
| `packages/ntruth/schemas/` | contratti strict v8/v9 (kernel, grafo, eventi, count registry, report) e schemi del core pre-v8 |
| `packages/ntruth/ingest/` | progetti, release profile, checksum e safety gate |
| `packages/ntruth/storage/` | SQLite, migrazioni e blob store SHA-256 immutabile |
| `packages/ntruth/parsers/` | parser TXT/Markdown, JATS, DOCX, PDF, CSV/XLSX e codice read-only |
| `packages/ntruth/sample_sheet/` | `SampleSheetSpec` v6, generator, validator e I/O CSV |
| `packages/ntruth/prospective/` | compiler D0 e contratti separati planned/executed |
| `packages/ntruth/extract/` | segmentazione e baseline di estrazione deterministica |
| `packages/ntruth/graph/` | costruzione, validazione, unità per scope, determinabilità, determinability v7 ed equality v8 |
| `packages/ntruth/verifier/` | hard verifier, output policy e verifier v8 |
| `packages/ntruth/rules/` | ruleset versionati, predicati e rules engine (incluso `v8_engine`) |
| `packages/ntruth/design/` | design specification, elicitazione e analysis handoff strutturale |
| `packages/ntruth/corrections/` | patch append-only, undo/redo, audit, ricalcolo e correzioni v8 |
| `packages/ntruth/reporting/` | JSON, YAML, HTML, JSON-LD/RO-Crate, output positivo e reporting v8/safe methods |
| `packages/ntruth/governance/` | licenze, consenso, lineage, privacy, split anti-leakage, contamination e policy/repository truth v8 |
| `packages/ntruth/parser_ai/` | contratto JSON del parser candidato (staged + legacy v2); nessun backend attivato dal prodotto standard |
| `packages/ntruth/runtime_resources/` | profili benchmark-derived, scheduling sequenziale, chunking, cache, fallback e telemetria |
| `packages/ntruth/training/` | preparazione governata, split anti-leakage, MLX QLoRA, metriche, calibrazione, custody ed export |
| `packages/ntruth/api/` | API locale loopback; include il journal durevole opt-in delle sessioni (`session_journal.py`) |
| `packages/ntruth/cli/` | CLI `ntruth` |
| `packages/ntruth/release/` | controlli, SBOM e metadati di distribuzione |
| `packages/ntruth/conformance/` | harness, fixture e registry degli esempi PRD v8 |
| `packages/ntruth/derivation_theory/` | loader e runtime della Derivation Theory versionata |
| `packages/ntruth/data/` | acquisizione, allineamento, manifest e split governati di dataset pubblici candidati |
| `packages/ntruth/task_corpora/` | contratti, CLI e validazione dei corpora task (C0/C1) |
| `packages/ntruth/evaluation_v8/` | scoring report-level, cluster-aware e modelli di valutazione v8 |
| `packages/ntruth/reality_gate/` | Reality Gate fail-closed v7/v8 con predicati e report |
| `packages/ntruth/quick_design/` | builder guidato/raw v8/v9 ed export |
| `packages/ntruth/mvt_a/` | revisione, verifica e benchmark a stadi del percorso MVT-A |
| `packages/ntruth/scientific/` | assignment anchor e gate scientifici v9 |
| `packages/ntruth/migrations/` | migrazioni tipizzate v7 -> v8 |
| `packages/ntruth/abstention/` | condition record e valore dell'astensione |
| `packages/ntruth/complexity/` | tier di complessità sperimentale |
| `packages/ntruth/cross_domain/` | ruoli cross-domain |
| `packages/ntruth/ocr/` | contratto adattatori OCR opzionali con provenance obbligatoria (nessun engine incluso) |
| `packages/ntruth/calibration/`, `packages/ntruth/facsimile/`, `packages/ntruth/model_backends/` | supporto a calibrazione, revisione facsimile e backend modello locali |
| `apps/desktop/` | UI React/Vite servita localmente dall'API; include il selettore visivo degli span (`SpanLocator.tsx`) |
| `rulesets/` | ruleset JSON versionati, incluso `ntruth-v8-core-0.1.0.json` |
| `theories/` | Derivation Theory, evaluator registry e profile closure versionati |
| `ontology/` | vocabolario/ontologia versionata |
| `benchmarks/` | benchmark registrati e report baseline (es. fewshot P0 B4) |
| `tests/` | unit, integration, golden, regression, security, property, performance e fixture sintetiche |
| `data/manifests/` | soli inventari pubblicabili; nessun dato reale |
| `data/splits/` | documentazione e futuri snapshot di split approvati |
| `data_manifests/` | inventari pubblicabili delle fonti esterne candidate |
| `models/configs/` | profili versionati; quello MLX fissa modello, runtime, memoria, training e storage |
| `models/cards/` | gate e card dei modelli; nessun peso incluso |
| `prd/` | PRD privato/istruttorio locale (`prd/N-Truth_PRD_scientifico_completo_v8.0.md`); non è automaticamente distribuibile |
| `scripts/` | gate contrattuali (`check_prd_v8_contracts.py`), policy repository, SBOM, distribuzione, smoke e utility task_corpora |
| `docs/` | architettura, governance, guideline, protocolli, audit, ADR e mappe v8 |
| `.github/` | CI e template di collaborazione |

## Flusso delle dipendenze

`DocumentIR` è il confine dell'ingestione. Il rules engine legge esclusivamente il
grafo validato e non il testo grezzo. Le correzioni producono nuove revisioni; non
riscrivono le fonti né gli export precedenti. La UI usa gli stessi casi d'uso della CLI
e dell'API.

Parser Gold misura documenti -> grafo; Derivation Gold misura grafo confermato ->
conseguenze. La distinzione impedisce di attribuire al modello un errore del motore o
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

- `workspace/`: progetti locali riapribili;
- `local-data/`: fonti, metadati privati, annotazioni e split candidati;
- `data/raw/`, `data/external/`, `data/processed/`: eventuali layout legacy locali;
- `models/local/`, `models/cache/`: snapshot base e cache locali;
- `models/checkpoints/`, `models/runs/`, `models/adapters/`, `models/exports/`: pesi,
  adapter, log ed export locali;
- `ntruth-out/`, `dist/`, `apps/desktop/dist/`: artefatti ricostruibili.

Prima di un commit verificare sempre:

```sh
git status --short
git check-ignore -v --no-index local-data/ workspace/ models/local/ models/checkpoints/
```

Non aggiungere eccezioni a `.gitignore` per pubblicare dati o pesi senza una decisione
esplicita su licenza, privacy, provenienza e dimensione.

Vedere [architettura](architettura.md), [Core Profile D0](core-profile-d0.md),
[SampleSheetSpec v6](sample-sheet-v6.md),
[contratto parser AI](parser-ai-contract.md) e la
[mappa current-to-target v8](architecture/prd-v8-current-to-target.yaml).
