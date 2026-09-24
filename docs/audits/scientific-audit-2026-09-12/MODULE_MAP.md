# Inventario strutturale N-Truth — 12 settembre 2026

Inventario automatico dei file visibili a `rg`, non attestazione di revisione semantica riga per riga. Sono esclusi dati privati e directory runtime.

HEAD: `57b74436cdcec2a5288059226f2c87b2c85079de`.

| Radice | File |
|---|---:|
| `.env.example` | 1 |
| `.github` | 5 |
| `.gitignore` | 1 |
| `.python-version` | 1 |
| `.superpowers` | 7 |
| `CHANGELOG.md` | 1 |
| `CITATION.cff` | 1 |
| `CODE_OF_CONDUCT.md` | 1 |
| `CONTRIBUTING.md` | 1 |
| `GOVERNANCE.md` | 1 |
| `LICENSE` | 1 |
| `README.md` | 1 |
| `SECURITY.md` | 1 |
| `SUPPORT.md` | 1 |
| `apps` | 48 |
| `benchmarks` | 32 |
| `contracts` | 6 |
| `data` | 10 |
| `data_manifests` | 2 |
| `docs` | 129 |
| `models` | 15 |
| `ontology` | 2 |
| `packages` | 276 |
| `prd` | 2 |
| `pyproject.toml` | 1 |
| `rulesets` | 4 |
| `sbom.cdx.json` | 1 |
| `scripts` | 32 |
| `tests` | 260 |
| `theories` | 3 |
| `uv.lock` | 1 |

## Package Python: tutti i moduli

| Modulo | Righe | Responsabilità dichiarata |
|---|---:|---|
| [packages/ntruth/__init__.py](../../../packages/ntruth/__init__.py) | 21 | N-Truth: ricostruzione verificabile di unita sperimentali e n indipendente. |
| [packages/ntruth/abstention/__init__.py](../../../packages/ntruth/abstention/__init__.py) | 23 | Contratti v7 di determinabilita condizionata e astensione utile (PRD v7 §10.8, §23.2). |
| [packages/ntruth/abstention/condition_record.py](../../../packages/ntruth/abstention/condition_record.py) | 70 | ConditionRecord bilingue per output condizionali (PRD v7 §10.8). |
| [packages/ntruth/abstention/value_of_abstention.py](../../../packages/ntruth/abstention/value_of_abstention.py) | 71 | Value-of-Abstention contract (PRD v7 §6.4, §23.2, FR-060…FR-065). |
| [packages/ntruth/api/__init__.py](../../../packages/ntruth/api/__init__.py) | 5 | FastAPI locale opzionale (installare l'extra ``ntruth[api]``). |
| [packages/ntruth/api/app.py](../../../packages/ntruth/api/app.py) | 1429 | API locale con lo stesso caso d'uso della CLI (PRD FR-029). |
| [packages/ntruth/api/main.py](../../../packages/ntruth/api/main.py) | 16 | Entrypoint ``ntruth-api`` vincolato al loopback locale. |
| [packages/ntruth/api/session_journal.py](../../../packages/ntruth/api/session_journal.py) | 123 | Durable journal for analysis sessions (resume-after-restart). |
| [packages/ntruth/api/sessions.py](../../../packages/ntruth/api/sessions.py) | 244 | Sessioni locali per correzione, ricalcolo e download controllato. |
| [packages/ntruth/application.py](../../../packages/ntruth/application.py) | 404 | Caso d'uso condiviso da CLI e API per garantire parity (PRD FR-029). |
| [packages/ntruth/artifacts.py](../../../packages/ntruth/artifacts.py) | 95 | Pubblicazione atomica di directory di artefatti append-only. |
| [packages/ntruth/calibration/__init__.py](../../../packages/ntruth/calibration/__init__.py) | 17 | Calibrazione, completezza e astensione (PRD 11.1). |
| [packages/ntruth/calibration/abstention.py](../../../packages/ntruth/calibration/abstention.py) | 138 | Astensione e completezza informativa (PRD 8.7, NFR-05, FR-022). |
| [packages/ntruth/capabilities.py](../../../packages/ntruth/capabilities.py) | 350 | Capability boundary scientifico per i profili di N-Truth. |
| [packages/ntruth/cli/__init__.py](../../../packages/ntruth/cli/__init__.py) | 5 | Interfaccia a riga di comando e automazione locale (PRD 11.1). |
| [packages/ntruth/cli/main.py](../../../packages/ntruth/cli/main.py) | 803 | CLI locale di N-Truth (PRD FR-029: CLI e API oltre alla GUI). |
| [packages/ntruth/complexity/__init__.py](../../../packages/ntruth/complexity/__init__.py) | 25 | Complexity tiers and burden tracking (PRD v7 §15). |
| [packages/ntruth/complexity/tiers.py](../../../packages/ntruth/complexity/tiers.py) | 117 | Complexity and Schema Burden Gate structures. |
| [packages/ntruth/confidence/__init__.py](../../../packages/ntruth/confidence/__init__.py) | 61 | Confidence, calibrazione e OOD per output AI candidati (PRD v9 §9.7, §12.8, §12.9). |
| [packages/ntruth/confidence/records.py](../../../packages/ntruth/confidence/records.py) | 492 | ConfidenceRecord, metriche di calibrazione e stato OOD (PRD v9 §9.7, §12.8, §12.9). |
| [packages/ntruth/conformance/__init__.py](../../../packages/ntruth/conformance/__init__.py) | 35 | PRD v8 Theory-to-Rulebook conformance gate. |
| [packages/ntruth/conformance/examples.py](../../../packages/ntruth/conformance/examples.py) | 251 | Checksum-verified PRD v8 source-example conformance registry. |
| [packages/ntruth/conformance/external_references.py](../../../packages/ntruth/conformance/external_references.py) | 74 | Freeze meccanismo per risorse di riferimento esterne (SRR-V8-021, lato codice). |
| [packages/ntruth/conformance/harness.py](../../../packages/ntruth/conformance/harness.py) | 538 | Cross-asset conformance checks; this module is not a derivation runtime. |
| [packages/ntruth/corrections/__init__.py](../../../packages/ntruth/corrections/__init__.py) | 73 | Correzioni human-in-the-loop, audit append-only ed export candidate. |
| [packages/ntruth/corrections/engine.py](../../../packages/ntruth/corrections/engine.py) | 841 | Motore di correzioni deterministico, append-only e senza dipendenze ML. |
| [packages/ntruth/corrections/export.py](../../../packages/ntruth/corrections/export.py) | 118 | Export separato delle correzioni come candidate annotations (FR-030). |
| [packages/ntruth/corrections/json_patch.py](../../../packages/ntruth/corrections/json_patch.py) | 309 | Applicatore atomico RFC 6902 con JSON Pointer RFC 6901. |
| [packages/ntruth/corrections/recalculate.py](../../../packages/ntruth/corrections/recalculate.py) | 568 | Ricalcolo rules-only dopo una correzione umana (PRD FR-026). |
| [packages/ntruth/corrections/v8.py](../../../packages/ntruth/corrections/v8.py) | 198 | PRD v8 correction boundary: facts may be corrected, derived claims may not. |
| [packages/ntruth/cross_domain/__init__.py](../../../packages/ntruth/cross_domain/__init__.py) | 17 | Cross-domain role policy (PRD v7 §14, §18). |
| [packages/ntruth/cross_domain/roles.py](../../../packages/ntruth/cross_domain/roles.py) | 163 | Profile-relative data roles with fail-closed defaults. |
| [packages/ntruth/data/__init__.py](../../../packages/ntruth/data/__init__.py) | 5 | N-Truth dataset acquisition, validation, alignment, and preparation pipeline. |
| [packages/ntruth/data/acquire.py](../../../packages/ntruth/data/acquire.py) | 296 | CLI orchestrator for N-Truth dataset acquisition, verification, alignment, repair, and lock resolution. |
| [packages/ntruth/data/alignment.py](../../../packages/ntruth/data/alignment.py) | 112 | SourceData NER ↔ ROLES_MULTI join key alignment, token verification, and audit report generation. |
| [packages/ntruth/data/config.py](../../../packages/ntruth/data/config.py) | 81 | Configuration constants, paths, and environment settings for N-Truth dataset acquisition. |
| [packages/ntruth/data/datasets/__init__.py](../../../packages/ntruth/data/datasets/__init__.py) | 3 | Dataset specific acquisition and preparation handlers. |
| [packages/ntruth/data/datasets/craft.py](../../../packages/ntruth/data/datasets/craft.py) | 405 | Handler for CRAFT v5.0.2 with pinned 67/30 Shared Task partition. |
| [packages/ntruth/data/datasets/measeval.py](../../../packages/ntruth/data/datasets/measeval.py) | 322 | Handler for MeasEval dataset handling text/txt structure, trial isolation, and review-required missing TSVs. |
| [packages/ntruth/data/datasets/preclinie.py](../../../packages/ntruth/data/datasets/preclinie.py) | 196 | Handler for PreClinIE dataset with paper-level group-stratified splitting. |
| [packages/ntruth/data/datasets/sourcedata.py](../../../packages/ntruth/data/datasets/sourcedata.py) | 230 | Handler for SourceData-NLP v2.0.3 using lockfile validation and config alignment. |
| [packages/ntruth/data/fs.py](../../../packages/ntruth/data/fs.py) | 247 | Filesystem utilities for exFAT resilience, security, AppleDouble filtering, and Merkle manifests. |
| [packages/ntruth/data/manifests.py](../../../packages/ntruth/data/manifests.py) | 91 | Manifests generation for dataset inventory, files registry, splits, licenses, and Merkle roots. |
| [packages/ntruth/data/schemas.py](../../../packages/ntruth/data/schemas.py) | 183 | Strongly-typed Pydantic schemas, discriminated unions, and validation invariants for N-Truth data. |
| [packages/ntruth/data/splits.py](../../../packages/ntruth/data/splits.py) | 167 | Group-stratified multilabel splitting, deterministic tie-breakers, and anti-leakage invariants. |
| [packages/ntruth/derivation_theory/__init__.py](../../../packages/ntruth/derivation_theory/__init__.py) | 81 | Version-isolated PRD v8 Derivation Theory contracts and assets. |
| [packages/ntruth/derivation_theory/contracts.py](../../../packages/ntruth/derivation_theory/contracts.py) | 424 | Strict PRD v8 contracts separating Derivation Theory from its Rulebook. |
| [packages/ntruth/derivation_theory/loader.py](../../../packages/ntruth/derivation_theory/loader.py) | 141 | Checksum-verifying loaders for isolated PRD v8 theory/conformance assets. |
| [packages/ntruth/derivation_theory/runtime.py](../../../packages/ntruth/derivation_theory/runtime.py) | 1308 | Clause-ID PRD v8 runtime gated by one complete conformance bundle. |
| [packages/ntruth/design/__init__.py](../../../packages/ntruth/design/__init__.py) | 63 | Design compiler local-first: specifica, elicitazione e handoff neutro. |
| [packages/ntruth/design/compiler.py](../../../packages/ntruth/design/compiler.py) | 520 | Compiler conservativo dal design IR a un analysis handoff neutro. |
| [packages/ntruth/design/elicit.py](../../../packages/ntruth/design/elicit.py) | 216 | Elicitazione deterministica delle informazioni mancanti nel design IR. |
| [packages/ntruth/design/io.py](../../../packages/ntruth/design/io.py) | 74 | Import/export deterministico del DesignSpecification e del JSON Schema. |
| [packages/ntruth/design/schema.py](../../../packages/ntruth/design/schema.py) | 432 | Contratto formale e neutro del disegno sperimentale. |
| [packages/ntruth/evaluation_v8/__init__.py](../../../packages/ntruth/evaluation_v8/__init__.py) | 201 | Public PRD v8 evaluation contracts. |
| [packages/ntruth/evaluation_v8/cluster.py](../../../packages/ntruth/evaluation_v8/cluster.py) | 1385 | Deterministic cluster-aware precision interfaces for PRD v8 §24.9. |
| [packages/ntruth/evaluation_v8/models.py](../../../packages/ntruth/evaluation_v8/models.py) | 1236 | Fail-closed PRD v8 contracts for end-to-end and residual evaluation. |
| [packages/ntruth/evaluation_v8/scoring.py](../../../packages/ntruth/evaluation_v8/scoring.py) | 1691 | Deterministic report-level scoring for the PRD v8 evaluation boundary. |
| [packages/ntruth/extract/__init__.py](../../../packages/ntruth/extract/__init__.py) | 100 | Estrazione: NER baseline, n statements, coreference e relazioni (PRD 11.1). |
| [packages/ntruth/extract/blocks.py](../../../packages/ntruth/extract/blocks.py) | 239 | Conservative structural segmentation into ExperimentBlock documents (PRD 12.1). |
| [packages/ntruth/extract/coreference.py](../../../packages/ntruth/extract/coreference.py) | 96 | Conservative deterministic intra-document coreference baseline (FR-011). |
| [packages/ntruth/extract/facts.py](../../../packages/ntruth/extract/facts.py) | 293 | Candidate facts prodotti dall'estrazione. |
| [packages/ntruth/extract/lexicon.py](../../../packages/ntruth/extract/lexicon.py) | 318 | Lessico delle entita sperimentali (baseline rules/regex, PRD 13.2). |
| [packages/ntruth/extract/numbers.py](../../../packages/ntruth/extract/numbers.py) | 203 | Riconoscimento di numeri e menzioni di n (PRD FR-010, FR-013). |
| [packages/ntruth/extract/table_extract.py](../../../packages/ntruth/extract/table_extract.py) | 632 | Estrazione dal sample sheet (PRD FR-005, 11.2). |
| [packages/ntruth/extract/text_extract.py](../../../packages/ntruth/extract/text_extract.py) | 1075 | Estrazione baseline da testo (PRD 13.2: baseline obbligatoria e fallback). |
| [packages/ntruth/facsimile/__init__.py](../../../packages/ntruth/facsimile/__init__.py) | 17 | Contratti record-to-view per i futuri facsimile N-Truth. |
| [packages/ntruth/facsimile/schema.py](../../../packages/ntruth/facsimile/schema.py) | 131 | Projection schema for automated record-to-facsimile invariant gates. |
| [packages/ntruth/governance/__init__.py](../../../packages/ntruth/governance/__init__.py) | 85 | Gate dati, lineage e privacy locali di N-Truth. |
| [packages/ntruth/governance/challenge_lifecycle.py](../../../packages/ntruth/governance/challenge_lifecycle.py) | 210 | PRD v9 Appendix AG.1 external challenge lifecycle state machine. |
| [packages/ntruth/governance/contamination.py](../../../packages/ntruth/governance/contamination.py) | 922 | PRD v8 External Challenge contamination and custody contracts. |
| [packages/ntruth/governance/data_use.py](../../../packages/ntruth/governance/data_use.py) | 137 | Granular data-use grants (PRD v9 section 14.8 and Appendix E). |
| [packages/ntruth/governance/lineage.py](../../../packages/ntruth/governance/lineage.py) | 430 | Snapshot corpus e lineage riproducibile senza avviare alcun training. |
| [packages/ntruth/governance/models.py](../../../packages/ntruth/governance/models.py) | 117 | Contratti locali di consenso, licenza e autorizzazione (PRD v3 15, 18.5, 26). |
| [packages/ntruth/governance/policy.py](../../../packages/ntruth/governance/policy.py) | 103 | Gate centralizzato per ogni azione sui dati; nessun default permissivo. |
| [packages/ntruth/governance/prd_matrix.py](../../../packages/ntruth/governance/prd_matrix.py) | 144 | Parse the final PRD implementation matrix and pin v9 disposition. |
| [packages/ntruth/governance/privacy.py](../../../packages/ntruth/governance/privacy.py) | 241 | Scanner locale stand-off di identificatori e copie redatte (PRD v3 26). |
| [packages/ntruth/governance/repository_policy.py](../../../packages/ntruth/governance/repository_policy.py) | 835 | Bounded PRD v8 policy scan over an explicit tracked-tree path set. |
| [packages/ntruth/governance/repository_truth.py](../../../packages/ntruth/governance/repository_truth.py) | 402 | Machine-readable current-to-target architecture truth for PRD v8. |
| [packages/ntruth/governance/templates.py](../../../packages/ntruth/governance/templates.py) | 30 | Template fail-closed derivati dallo scope reale di una revisione. |
| [packages/ntruth/graph/__init__.py](../../../packages/ntruth/graph/__init__.py) | 7 | Grafo tipizzato: merge delle fonti, conflitti e risoluzione delle unita. |
| [packages/ntruth/graph/builder.py](../../../packages/ntruth/graph/builder.py) | 1796 | Graph builder deterministico (PRD 11.3). |
| [packages/ntruth/graph/determinability.py](../../../packages/ntruth/graph/determinability.py) | 137 | Derivazione deterministica della tabella ``DeterminabilityState`` v6. |
| [packages/ntruth/graph/determinability_v7.py](../../../packages/ntruth/graph/determinability_v7.py) | 77 | Derivazione v7 del DeterminabilityState (PRD v7 §10.2, §18.6). |
| [packages/ntruth/graph/equality_v8.py](../../../packages/ntruth/graph/equality_v8.py) | 429 | Exact identifier-invariant PRD v8 graph equality; partial scoring is blocked. |
| [packages/ntruth/graph/index.py](../../../packages/ntruth/graph/index.py) | 355 | Indice interrogabile del grafo: chiusura di annidamento, conteggi e livelli. |
| [packages/ntruth/graph/units.py](../../../packages/ntruth/graph/units.py) | 937 | Risoluzione delle unita e dei tre n (PRD 7.1, 12.2). |
| [packages/ntruth/graph/validation.py](../../../packages/ntruth/graph/validation.py) | 1080 | Validazione strutturale del grafo e degli ``ExperimentBlock``. |
| [packages/ntruth/ingest/__init__.py](../../../packages/ntruth/ingest/__init__.py) | 33 | Ingestione sicura: import, checksum, MIME, manifest e sandbox (PRD 11.1). |
| [packages/ntruth/ingest/project.py](../../../packages/ntruth/ingest/project.py) | 613 | Progetto locale: ID stabile, copia delle fonti, checksum e manifest (PRD FR-001, FR-007). |
| [packages/ntruth/ingest/safety.py](../../../packages/ntruth/ingest/safety.py) | 580 | Limiti e controlli su input ostili (PRD NFR-13). |
| [packages/ntruth/migrations/__init__.py](../../../packages/ntruth/migrations/__init__.py) | 29 | Explicit, audited compatibility adapters into PRD v8 contracts. |
| [packages/ntruth/migrations/v7_to_v8.py](../../../packages/ntruth/migrations/v7_to_v8.py) | 553 | Fail-closed adapters from deprecated v7 values to v8 kernel contracts. |
| [packages/ntruth/model_backends/__init__.py](../../../packages/ntruth/model_backends/__init__.py) | 53 | Backend modello Train A — cluster 1 (Granite sperimentale, non default). |
| [packages/ntruth/model_backends/base.py](../../../packages/ntruth/model_backends/base.py) | 191 | Interfaccia astratta provider-agnostic per i backend modello Train A. |
| [packages/ntruth/model_backends/constants.py](../../../packages/ntruth/model_backends/constants.py) | 39 | Costanti tecniche del backend (nessuno stato di qualificazione). |
| [packages/ntruth/model_backends/constrained.py](../../../packages/ntruth/model_backends/constrained.py) | 139 | Adapter constrained decoding provider-agnostic (Outlines / MLX-LM). |
| [packages/ntruth/model_backends/errors.py](../../../packages/ntruth/model_backends/errors.py) | 33 | Errori e tipi minimi del backend (senza runtime_resources). |
| [packages/ntruth/model_backends/factory.py](../../../packages/ntruth/model_backends/factory.py) | 110 | Factory backend — default Granite (ADR-0010), legacy Qwen solo con opt-in. |
| [packages/ntruth/model_backends/granite.py](../../../packages/ntruth/model_backends/granite.py) | 364 | Backend sperimentale IBM Granite 4.1 3B Instruct via MLX-LM. |
| [packages/ntruth/model_backends/legacy/__init__.py](../../../packages/ntruth/model_backends/legacy/__init__.py) | 3 |  |
| [packages/ntruth/model_backends/legacy/qwen_backend.py](../../../packages/ntruth/model_backends/legacy/qwen_backend.py) | 177 | Backend Qwen — percorso default esistente fino alla promozione Granite (cluster 2+). |
| [packages/ntruth/model_backends/profile.py](../../../packages/ntruth/model_backends/profile.py) | 65 | Caricamento e validazione della config tecnica Granite (senza stato operativo). |
| [packages/ntruth/model_backends/qualification.py](../../../packages/ntruth/model_backends/qualification.py) | 283 | ModelQualificationRecord e ledger append-only (PRD v9 §12.6, §25.10, Appendice T). |
| [packages/ntruth/model_backends/qualification_ledger.py](../../../packages/ntruth/model_backends/qualification_ledger.py) | 698 | Ledger append-only delle transizioni di qualificazione Train A. |
| [packages/ntruth/model_backends/registry.py](../../../packages/ntruth/model_backends/registry.py) | 915 | Registry centrale dei modelli Train A (single source of truth per model ID). |
| [packages/ntruth/model_backends/stage_schemas.py](../../../packages/ntruth/model_backends/stage_schemas.py) | 194 | Schemi stage-level per structured decoding B4 (forma, non scienza). |
| [packages/ntruth/mvt_a/__init__.py](../../../packages/ntruth/mvt_a/__init__.py) | 69 | Minimum Viable Train A contracts only (PRD v7 §4.2, Workstream B). |
| [packages/ntruth/mvt_a/benchmark.py](../../../packages/ntruth/mvt_a/benchmark.py) | 61 | Benchmark manifest for a future MVT-A run (PRD v7 §4.2). |
| [packages/ntruth/mvt_a/revision.py](../../../packages/ntruth/mvt_a/revision.py) | 71 | Human revision patch and burden metrics for MVT-A (PRD v7 §4.2, §15). |
| [packages/ntruth/mvt_a/stage_schema.py](../../../packages/ntruth/mvt_a/stage_schema.py) | 402 | MVT-A stage schema: candidate-only parser outputs (PRD v8 §13.6). |
| [packages/ntruth/mvt_a/verifier.py](../../../packages/ntruth/mvt_a/verifier.py) | 215 | Hard verifier hook for MVT-A candidate bundles (PRD v8 §13.6). |
| [packages/ntruth/ocr/__init__.py](../../../packages/ntruth/ocr/__init__.py) | 101 | Contratto opzionale per adattatori OCR con provenance (PRD v9 roadmap). |
| [packages/ntruth/parser_ai/__init__.py](../../../packages/ntruth/parser_ai/__init__.py) | 167 | Contratto stabile del parser AI; nessun modello o rete inclusi. |
| [packages/ntruth/parser_ai/adapter.py](../../../packages/ntruth/parser_ai/adapter.py) | 156 | Adapter sostituibile del parser AI; nessun backend concreto e incluso. |
| [packages/ntruth/parser_ai/contract.py](../../../packages/ntruth/parser_ai/contract.py) | 1386 | Contratto JSON candidate-only e backend-agnostic del parser AI (PRD v8 §13). |
| [packages/ntruth/parser_ai/stages.py](../../../packages/ntruth/parser_ai/stages.py) | 977 | Contratti di fase versionati per la pipeline parser/verifier del PRD v6. |
| [packages/ntruth/parsers/__init__.py](../../../packages/ntruth/parsers/__init__.py) | 30 | Parser: JATS/DOCX/PDF/CSV/XLSX/TXT -> Document IR con span e celle (PRD 11.1). |
| [packages/ntruth/parsers/base.py](../../../packages/ntruth/parsers/base.py) | 101 | Contratto comune dei parser: da byte a blocchi con coordinate. |
| [packages/ntruth/parsers/code.py](../../../packages/ntruth/parsers/code.py) | 117 | Import non esecutivo di script statistici R/Python (PRD v3 FR-005). |
| [packages/ntruth/parsers/docx.py](../../../packages/ntruth/parsers/docx.py) | 83 | Parser DOCX (PRD FR-003). Round-trip verificato dalle fixture. |
| [packages/ntruth/parsers/jats.py](../../../packages/ntruth/parsers/jats.py) | 148 | Parser JATS/XML preservando struttura, tabelle e legends (PRD FR-002). |
| [packages/ntruth/parsers/pdf.py](../../../packages/ntruth/parsers/pdf.py) | 235 | Parser PDF testuale con estrazione tabelle (PRD FR-004, audit 2026-09-05). |
| [packages/ntruth/parsers/registry.py](../../../packages/ntruth/parsers/registry.py) | 353 | Assemblaggio del Document IR: dai file del progetto a sezioni, paragrafi e tabelle. |
| [packages/ntruth/parsers/sections.py](../../../packages/ntruth/parsers/sections.py) | 146 | Classificazione deterministica delle sezioni (PRD FR-008). |
| [packages/ntruth/parsers/tabular.py](../../../packages/ntruth/parsers/tabular.py) | 228 | Parser CSV/TSV/XLSX per sample sheet (PRD FR-005). |
| [packages/ntruth/parsers/text.py](../../../packages/ntruth/parsers/text.py) | 97 | Parser TXT e Markdown (PRD FR-003). |
| [packages/ntruth/pipeline.py](../../../packages/ntruth/pipeline.py) | 710 | Orchestrazione locale: progetto -> Document IR -> grafo -> regole -> report. |
| [packages/ntruth/pipeline_v8.py](../../../packages/ntruth/pipeline_v8.py) | 166 | Thin bundle-gated orchestration for the deterministic PRD v8 lane. |
| [packages/ntruth/prospective/__init__.py](../../../packages/ntruth/prospective/__init__.py) | 69 | Compiler prospettico, deterministico e locale per il Core Profile D0. |
| [packages/ntruth/prospective/compiler.py](../../../packages/ntruth/prospective/compiler.py) | 2182 | Compiler prospettico D0: input umano -> blocco canonico verificato. |
| [packages/ntruth/prospective/plan_execution.py](../../../packages/ntruth/prospective/plan_execution.py) | 251 | Provenance prospettica separata tra piano, esecuzione e gold adjudicato. |
| [packages/ntruth/prospective/schema.py](../../../packages/ntruth/prospective/schema.py) | 490 | Contratti di ingresso/uscita del compiler prospettico Core Profile D0. |
| [packages/ntruth/prospective/sessions.py](../../../packages/ntruth/prospective/sessions.py) | 77 | Sessioni effimere e memory-bounded per gli artefatti prospettici D0. |
| [packages/ntruth/quick_design/__init__.py](../../../packages/ntruth/quick_design/__init__.py) | 106 | PRD v8 Quick Design service plus explicitly qualified v7 compatibility adapters. |
| [packages/ntruth/quick_design/export.py](../../../packages/ntruth/quick_design/export.py) | 90 | Export and plan freeze for Quick Design Session (PRD v7 §6.1). |
| [packages/ntruth/quick_design/guided.py](../../../packages/ntruth/quick_design/guided.py) | 2069 | Deterministic guided-input builder for the canonical PRD v8 Quick Design lane. |
| [packages/ntruth/quick_design/session.py](../../../packages/ntruth/quick_design/session.py) | 385 | Quick Design Session service for simple_cell_culture (PRD v7 §6.1). |
| [packages/ntruth/quick_design/templates.py](../../../packages/ntruth/quick_design/templates.py) | 80 | Artefatti deterministici della Quick Design Session (PRD v7 §6.1). |
| [packages/ntruth/quick_design/v8.py](../../../packages/ntruth/quick_design/v8.py) | 342 | Prospective Quick Design orchestration over the verified PRD v8 pipeline. |
| [packages/ntruth/quick_design/v9.py](../../../packages/ntruth/quick_design/v9.py) | 395 | PRD v9 Quick Design session: FactorRole and ContrastType before later steps. |
| [packages/ntruth/quick_design/v9_bundle.py](../../../packages/ntruth/quick_design/v9_bundle.py) | 189 | PRD v9 §6.1 step 7/9: bundle integrato della Quick Design session. |
| [packages/ntruth/reality_gate/__init__.py](../../../packages/ntruth/reality_gate/__init__.py) | 93 | Canonical PRD v8/v9 Reality Gate; historical behavior lives in ``.v7``. |
| [packages/ntruth/reality_gate/gate.py](../../../packages/ntruth/reality_gate/gate.py) | 269 | Composizione fail-closed del Reality Gate (PRD v7 §0.7, §25.6). |
| [packages/ntruth/reality_gate/predicates.py](../../../packages/ntruth/reality_gate/predicates.py) | 96 | Predicati del Reality Gate (PRD v7 §0.7). |
| [packages/ntruth/reality_gate/report.py](../../../packages/ntruth/reality_gate/report.py) | 31 | Report del Reality Gate: esito machine-readable e blocker report umano. |
| [packages/ntruth/reality_gate/v7.py](../../../packages/ntruth/reality_gate/v7.py) | 73 | Explicit compatibility namespace for the historical PRD v7 Reality Gate. |
| [packages/ntruth/reality_gate/v8.py](../../../packages/ntruth/reality_gate/v8.py) | 955 | Authoritative PRD v8 Reality Gate data contracts. |
| [packages/ntruth/reality_gate/v9.py](../../../packages/ntruth/reality_gate/v9.py) | 493 | PRD v9 §0.8 Reality Gate composed over the pinned PRD v8 gate. |
| [packages/ntruth/release/__init__.py](../../../packages/ntruth/release/__init__.py) | 5 | Utility installabili per costruzione e verifica degli artefatti di release. |
| [packages/ntruth/release/sbom.py](../../../packages/ntruth/release/sbom.py) | 205 | Generazione deterministica dell'SBOM CycloneDX dai lockfile uv e pnpm. |
| [packages/ntruth/reporting/__init__.py](../../../packages/ntruth/reporting/__init__.py) | 389 | Rendering del report: JSON come fonte di verita, HTML come vista (PRD 11.1). |
| [packages/ntruth/reporting/html_report.py](../../../packages/ntruth/reporting/html_report.py) | 647 | Report HTML stampabile e navigabile (PRD 20, FR-024, FR-027). |
| [packages/ntruth/reporting/json_report.py](../../../packages/ntruth/reporting/json_report.py) | 112 | Export JSON e graph.json (PRD FR-015, FR-027). |
| [packages/ntruth/reporting/positive.py](../../../packages/ntruth/reporting/positive.py) | 587 | Output positivo prudente del compilatore di disegni (PRD v6, sez. 20). |
| [packages/ntruth/reporting/privacy.py](../../../packages/ntruth/reporting/privacy.py) | 254 | Audit privacy locale e readiness di distribuzione, senza mutare le fonti. |
| [packages/ntruth/reporting/ro_crate.py](../../../packages/ntruth/reporting/ro_crate.py) | 206 | Export RO-Crate 1.3 / JSON-LD deterministico (PRD FR-028, FR-034). |
| [packages/ntruth/reporting/safe_methods.py](../../../packages/ntruth/reporting/safe_methods.py) | 373 | PRD v9 Safe Methods Generation Contract. |
| [packages/ntruth/reporting/v8.py](../../../packages/ntruth/reporting/v8.py) | 358 | Validated neutral renderers for the canonical PRD v8 ReportBundle. |
| [packages/ntruth/rules/__init__.py](../../../packages/ntruth/rules/__init__.py) | 27 | Rules engine deterministico e domande (PRD 11.1). |
| [packages/ntruth/rules/engine.py](../../../packages/ntruth/rules/engine.py) | 531 | Rules engine deterministico (PRD 8, FR-018, FR-019, FR-022). |
| [packages/ntruth/rules/loader.py](../../../packages/ntruth/rules/loader.py) | 64 | Caricamento dei ruleset versionati da disco (PRD FR-018, FR-034). |
| [packages/ntruth/rules/predicates.py](../../../packages/ntruth/rules/predicates.py) | 473 | Predicati valutabili sul grafo (PRD 8.1). |
| [packages/ntruth/rules/v8_engine.py](../../../packages/ntruth/rules/v8_engine.py) | 87 | Pinned open-world adequacy evaluation after claim verification. |
| [packages/ntruth/runtime_resources/__init__.py](../../../packages/ntruth/runtime_resources/__init__.py) | 77 | Runtime resource management backend-agnostic per N-Truth Train A. |
| [packages/ntruth/runtime_resources/budget_io.py](../../../packages/ntruth/runtime_resources/budget_io.py) | 59 | Serializzazione fail-closed del budget runtime misurato. |
| [packages/ntruth/runtime_resources/chunking.py](../../../packages/ntruth/runtime_resources/chunking.py) | 103 | Chunking gerarchico section-first con coordinate riproducibili. |
| [packages/ntruth/runtime_resources/manager.py](../../../packages/ntruth/runtime_resources/manager.py) | 487 | Resource manager sequenziale, cache-bounded e backend-agnostic. |
| [packages/ntruth/runtime_resources/profiles.py](../../../packages/ntruth/runtime_resources/profiles.py) | 68 | Profili runtime modificabili; nessuno incorpora un claim di memoria. |
| [packages/ntruth/runtime_resources/schema.py](../../../packages/ntruth/runtime_resources/schema.py) | 253 | Contratti misurabili per il runtime sequenziale dei componenti Train A. |
| [packages/ntruth/runtime_tree.py](../../../packages/ntruth/runtime_tree.py) | 212 | Exact runtime-tree reconstruction for public PRD v8 execution boundaries. |
| [packages/ntruth/sample_sheet/__init__.py](../../../packages/ntruth/sample_sheet/__init__.py) | 43 | SampleSheetSpec v6: schema, validazione e I/O CSV. |
| [packages/ntruth/sample_sheet/io.py](../../../packages/ntruth/sample_sheet/io.py) | 535 | I/O CSV sicuro e riproducibile per :mod:`ntruth.sample_sheet`. |
| [packages/ntruth/sample_sheet/schema.py](../../../packages/ntruth/sample_sheet/schema.py) | 229 | Contratto canonico del sample sheet iniziale (PRD v6, Appendice O). |
| [packages/ntruth/sample_sheet/v9_schema.py](../../../packages/ntruth/sample_sheet/v9_schema.py) | 411 | SampleSheetSpec iniziale v9 (PRD v9, Appendice O). |
| [packages/ntruth/schemas/__init__.py](../../../packages/ntruth/schemas/__init__.py) | 541 | Contratti dati di N-Truth. Tutto il resto del sistema dipende solo da qui. |
| [packages/ntruth/schemas/adequacy.py](../../../packages/ntruth/schemas/adequacy.py) | 61 | Epistemic design-adequacy evaluations kept orthogonal to determinability. |
| [packages/ntruth/schemas/authority.py](../../../packages/ntruth/schemas/authority.py) | 222 | Shared authority vocabulary plus explicitly historical PRD v7 records. |
| [packages/ntruth/schemas/block_boundary.py](../../../packages/ntruth/schemas/block_boundary.py) | 563 | Experiment Block boundary records for PRD v8 §8.6. |
| [packages/ntruth/schemas/bootstrap_core.py](../../../packages/ntruth/schemas/bootstrap_core.py) | 121 | Bootstrap Core v7: required-or-unknown (PRD v7 §8.2A, App. X.1). |
| [packages/ntruth/schemas/causal_context.py](../../../packages/ntruth/schemas/causal_context.py) | 252 | Causal Design Context: strato descrittivo, non motore causale (PRD v7 §2.4, App. Y). |
| [packages/ntruth/schemas/claims.py](../../../packages/ntruth/schemas/claims.py) | 213 | Claim-specific deterministic output foundations for PRD v8. |
| [packages/ntruth/schemas/contrast_support.py](../../../packages/ntruth/schemas/contrast_support.py) | 111 | PRD v9 ContrastSupport / ExposurePartition / assignment-anchored EU claims. |
| [packages/ntruth/schemas/core.py](../../../packages/ntruth/schemas/core.py) | 212 | Tipi base condivisi: identita deterministica, evidenza e provenance. |
| [packages/ntruth/schemas/coreference.py](../../../packages/ntruth/schemas/coreference.py) | 39 | Explicit mention and intra-document coreference contracts (PRD FR-011). |
| [packages/ntruth/schemas/count_registry.py](../../../packages/ntruth/schemas/count_registry.py) | 397 | PRD v8 Canonical Count Registry. |
| [packages/ntruth/schemas/counts.py](../../../packages/ntruth/schemas/counts.py) | 185 | Conteggi scope-aware e semantica canonica dei conteggi (PRD v7 §7.9, §15.10). |
| [packages/ntruth/schemas/coverage.py](../../../packages/ntruth/schemas/coverage.py) | 202 | Structured PRD v8 profile and scenario coverage contracts. |
| [packages/ntruth/schemas/determinability_v7.py](../../../packages/ntruth/schemas/determinability_v7.py) | 104 | DeterminabilityState v7: sette stati normativi e output ammessi (PRD v7 §10.2, App. M). |
| [packages/ntruth/schemas/document.py](../../../packages/ntruth/schemas/document.py) | 248 | Document IR: rappresentazione immutabile e con coordinate delle fonti. |
| [packages/ntruth/schemas/events.py](../../../packages/ntruth/schemas/events.py) | 190 | PRD v8 event nodes and event-referenced temporal relations. |
| [packages/ntruth/schemas/evidence_levels.py](../../../packages/ntruth/schemas/evidence_levels.py) | 58 | Evidence support levels v7 (PRD v7 §9.5). |
| [packages/ntruth/schemas/execution.py](../../../packages/ntruth/schemas/execution.py) | 70 | Content-addressed execution pins for the deterministic PRD v8 lane. |
| [packages/ntruth/schemas/experiment.py](../../../packages/ntruth/schemas/experiment.py) | 1827 | ExperimentBlock e contratti dati (PRD 12). |
| [packages/ntruth/schemas/factor_role.py](../../../packages/ntruth/schemas/factor_role.py) | 242 | PRD v9 FactorRole / ContrastType eligibility gate. |
| [packages/ntruth/schemas/graph.py](../../../packages/ntruth/schemas/graph.py) | 310 | Nodi e relazioni tipizzati dell'Experiment Graph (PRD 7.2 e 7.3). |
| [packages/ntruth/schemas/graph_v8.py](../../../packages/ntruth/schemas/graph_v8.py) | 169 | Version-isolated PRD v8 Experiment Graph vocabulary and structural model. |
| [packages/ntruth/schemas/inferential_query.py](../../../packages/ntruth/schemas/inferential_query.py) | 44 | InferentialQuery: ogni conclusione e associata a un oggetto versionato (PRD v7 §7.8). |
| [packages/ntruth/schemas/kernel.py](../../../packages/ntruth/schemas/kernel.py) | 179 | Profile-invariant foundations for the PRD v8 Core Semantic Kernel. |
| [packages/ntruth/schemas/knowledge.py](../../../packages/ntruth/schemas/knowledge.py) | 1699 | Normative PRD v8 KnowledgeState and open-world value wrapper. |
| [packages/ntruth/schemas/manifest.py](../../../packages/ntruth/schemas/manifest.py) | 327 | Manifest di progetto e di licenza (PRD 14.5, FR-001, FR-007, FR-032). |
| [packages/ntruth/schemas/material_lineage.py](../../../packages/ntruth/schemas/material_lineage.py) | 273 | PRD v9 MaterialLineage typed events and count-identity invariants. |
| [packages/ntruth/schemas/prospective.py](../../../packages/ntruth/schemas/prospective.py) | 1234 | Immutable prospective plan and executed-design records for PRD v8. |
| [packages/ntruth/schemas/query.py](../../../packages/ntruth/schemas/query.py) | 69 | PRD v8 inferential-query contract. |
| [packages/ntruth/schemas/relations.py](../../../packages/ntruth/schemas/relations.py) | 105 | Registro canonico delle relazioni v7 (PRD v7 §8.5) con alias di migrazione. |
| [packages/ntruth/schemas/report.py](../../../packages/ntruth/schemas/report.py) | 312 | Report: sintesi, limiti, alert, fonti ed export (PRD 20, FR-027). |
| [packages/ntruth/schemas/report_bundle.py](../../../packages/ntruth/schemas/report_bundle.py) | 1572 | Neutral, content-addressed PRD v8 ReportBundle contract. |
| [packages/ntruth/schemas/report_resolution.py](../../../packages/ntruth/schemas/report_resolution.py) | 110 | Versioned and fail-closed PRD v8 report-resolution policy contract. |
| [packages/ntruth/schemas/rules.py](../../../packages/ntruth/schemas/rules.py) | 198 | Regole versionate (PRD 8.1). |
| [packages/ntruth/schemas/schema_snapshot.py](../../../packages/ntruth/schemas/schema_snapshot.py) | 69 | Checksum-verified packaged JSON Schema snapshot for the PRD v8 kernel. |
| [packages/ntruth/schemas/support.py](../../../packages/ntruth/schemas/support.py) | 442 | Orthogonal source, authority, evidence and support contracts for PRD v8. |
| [packages/ntruth/schemas/support_profile.py](../../../packages/ntruth/schemas/support_profile.py) | 260 | PRD v9 multidimensional SupportProfile. |
| [packages/ntruth/schemas/v9_registry.py](../../../packages/ntruth/schemas/v9_registry.py) | 166 | PRD v9 Canonical Schema Registry. |
| [packages/ntruth/scientific/__init__.py](../../../packages/ntruth/scientific/__init__.py) | 29 | PRD v9 scientific sidecar contracts that are not the v8 binding kernel. |
| [packages/ntruth/scientific/assignment_anchor.py](../../../packages/ntruth/scientific/assignment_anchor.py) | 76 | Assignment-anchored EU identity and contrast-support evaluation (PRD v9 B02/M06). |
| [packages/ntruth/scientific/design_matrix.py](../../../packages/ntruth/scientific/design_matrix.py) | 162 | PRD v9 §11.2: design matrix, aliasing perfetto e variazione intra-blocco. |
| [packages/ntruth/scientific/v9_gates.py](../../../packages/ntruth/scientific/v9_gates.py) | 124 | Combined PRD v9 fail-closed gate: role, assignment, contrast support. |
| [packages/ntruth/storage/__init__.py](../../../packages/ntruth/storage/__init__.py) | 43 | Persistenza applicativa locale SQLite e blob content-addressed. |
| [packages/ntruth/storage/blobs.py](../../../packages/ntruth/storage/blobs.py) | 197 | Blob store locale content-addressed, atomico e senza operazioni di rete. |
| [packages/ntruth/storage/database.py](../../../packages/ntruth/storage/database.py) | 721 | Database applicativo SQLite locale per progetti, revisioni e audit N-Truth. |
| [packages/ntruth/storage/migrations.py](../../../packages/ntruth/storage/migrations.py) | 249 | Migrazioni SQLite idempotenti e verificabili per la persistenza locale v6. |
| [packages/ntruth/task_corpora/__init__.py](../../../packages/ntruth/task_corpora/__init__.py) | 5 | Deterministic task-corpora builders for N-Truth auxiliary baselines (Workstream C). |
| [packages/ntruth/task_corpora/__main__.py](../../../packages/ntruth/task_corpora/__main__.py) | 8 | python -m ntruth.task_corpora |
| [packages/ntruth/task_corpora/adapters/__init__.py](../../../packages/ntruth/task_corpora/adapters/__init__.py) | 1 | Source-specific task adapters. |
| [packages/ntruth/task_corpora/adapters/sourcedata_entity_roles.py](../../../packages/ntruth/task_corpora/adapters/sourcedata_entity_roles.py) | 455 | SourceData-NLP multitask → canonical entity_roles task corpus. |
| [packages/ntruth/task_corpora/authority.py](../../../packages/ntruth/task_corpora/authority.py) | 46 | Supervision, authority, licence, and use-policy enums. |
| [packages/ntruth/task_corpora/cli.py](../../../packages/ntruth/task_corpora/cli.py) | 205 | CLI for task corpora build / validate / stats. |
| [packages/ntruth/task_corpora/config.py](../../../packages/ntruth/task_corpora/config.py) | 84 | Paths, seeds, and constants for task corpora. |
| [packages/ntruth/task_corpora/io_util.py](../../../packages/ntruth/task_corpora/io_util.py) | 65 | Idempotent JSONL / JSON writers reusing data.fs atomic helpers. |
| [packages/ntruth/task_corpora/license_loader.py](../../../packages/ntruth/task_corpora/license_loader.py) | 58 | Load machine-readable licence / training-use decisions. |
| [packages/ntruth/task_corpora/provenance_join.py](../../../packages/ntruth/task_corpora/provenance_join.py) | 142 | C1.1 provenance join utilities (investigation-only). |
| [packages/ntruth/task_corpora/readiness.py](../../../packages/ntruth/task_corpora/readiness.py) | 233 | Dataset readiness projection onto canonical PRD-v7 Reality Gate contracts. |
| [packages/ntruth/task_corpora/schemas.py](../../../packages/ntruth/task_corpora/schemas.py) | 200 | Canonical task-record schemas for Workstream C corpora. |
| [packages/ntruth/task_corpora/validate.py](../../../packages/ntruth/task_corpora/validate.py) | 69 | Fail-closed validators for task records and BIO sequences. |
| [packages/ntruth/team_evaluation/__init__.py](../../../packages/ntruth/team_evaluation/__init__.py) | 79 | Preregistered H/A/H+A team evaluation protocol contracts (PRD v9). |
| [packages/ntruth/team_evaluation/models.py](../../../packages/ntruth/team_evaluation/models.py) | 654 | Preregistered H/A/H+A team evaluation contracts (PRD v9 §18.9, §24.2-24.7, Appendix AM). |
| [packages/ntruth/training/__init__.py](../../../packages/ntruth/training/__init__.py) | 53 | Preparazione deterministica di dataset; nessun training viene avviato qui. |
| [packages/ntruth/training/calibration.py](../../../packages/ntruth/training/calibration.py) | 214 | Calibrazione locale delle confidence del parser AI. |
| [packages/ntruth/training/candidate_conformance.py](../../../packages/ntruth/training/candidate_conformance.py) | 295 | Metriche di conformità strutturale per ``CandidateGraphSet`` (non scientifiche). |
| [packages/ntruth/training/cli.py](../../../packages/ntruth/training/cli.py) | 391 | CLI separata per la corsia MLX locale e opzionale. |
| [packages/ntruth/training/custody.py](../../../packages/ntruth/training/custody.py) | 36 | Task-5 custody dependency pins; authority remains owned by Task 7. |
| [packages/ntruth/training/dedup.py](../../../packages/ntruth/training/dedup.py) | 324 | Deduplica esatta e near-duplicate conservativa dei record supervisionati. |
| [packages/ntruth/training/fewshot_p0_fixtures.py](../../../packages/ntruth/training/fewshot_p0_fixtures.py) | 1303 | Fixture canoniche P0 per baseline few-shot Granite (CandidateGraphSet v6). |
| [packages/ntruth/training/gold.py](../../../packages/ntruth/training/gold.py) | 139 | Target parser adjudicati, distinti dagli output candidati del modello. |
| [packages/ntruth/training/manifest.py](../../../packages/ntruth/training/manifest.py) | 151 | Costruzione e serializzazione del manifest content-addressed del dataset. |
| [packages/ntruth/training/metrics.py](../../../packages/ntruth/training/metrics.py) | 501 | Metriche strutturate per il contratto Parser AI v2. |
| [packages/ntruth/training/metrics_v6.py](../../../packages/ntruth/training/metrics_v6.py) | 455 | Metriche candidate-only per il contratto parser ``CandidateGraphSet`` v6. |
| [packages/ntruth/training/mlx_component.py](../../../packages/ntruth/training/mlx_component.py) | 189 | Adapter MLX che implementa ``RuntimeComponent`` (ADR-0003: in training/, non nel core). |
| [packages/ntruth/training/mlx_dataset.py](../../../packages/ntruth/training/mlx_dataset.py) | 295 | Adattamento del dataset governato al formato chat JSONL di MLX-LM. |
| [packages/ntruth/training/mlx_fd_entrypoint.py](../../../packages/ntruth/training/mlx_fd_entrypoint.py) | 203 | Child-only MLX entrypoint that consumes inherited anonymous JSONL files. |
| [packages/ntruth/training/mlx_inference.py](../../../packages/ntruth/training/mlx_inference.py) | 1703 | Tokenizzazione, generazione, scoring ed export locale degli adapter MLX. |
| [packages/ntruth/training/mlx_resource_bridge.py](../../../packages/ntruth/training/mlx_resource_bridge.py) | 271 | Ponte MLX ↔ RuntimeResourceManager (adapter in training/, ADR-0003). |
| [packages/ntruth/training/mlx_runtime.py](../../../packages/ntruth/training/mlx_runtime.py) | 2265 | Runtime locale e riproducibile per MLX-LM su Apple Silicon. |
| [packages/ntruth/training/p0_synthetic.py](../../../packages/ntruth/training/p0_synthetic.py) | 1166 | Factory sintetica graph-first per snapshot P0-alpha (esperimento, non scienza). |
| [packages/ntruth/training/preparation.py](../../../packages/ntruth/training/preparation.py) | 247 | Pipeline deterministica: valida, normalizza, deduplica, separa e manifesta. |
| [packages/ntruth/training/protected_evaluation.py](../../../packages/ntruth/training/protected_evaluation.py) | 267 | Custodial TEST/EXTERNAL_CHALLENGE snapshot contract (PRD v8 sections 24-25). |
| [packages/ntruth/training/records.py](../../../packages/ntruth/training/records.py) | 1042 | Contratti deterministici per preparare dataset supervisionati N-Truth. |
| [packages/ntruth/training/runtime_benchmark.py](../../../packages/ntruth/training/runtime_benchmark.py) | 527 | Benchmark runtime misurato su hardware reale (ADR-0003, PRD Appendice T). |
| [packages/ntruth/training/runtime_env.py](../../../packages/ntruth/training/runtime_env.py) | 108 | Fingerprint dell'ambiente runtime per il resource manager (adapter training). |
| [packages/ntruth/training/semantic_stage_scorer.py](../../../packages/ntruth/training/semantic_stage_scorer.py) | 1053 | Scoring semantico stage-level B4 (development only). |
| [packages/ntruth/training/splits.py](../../../packages/ntruth/training/splits.py) | 432 | Split deterministici group-aware per impedire leakage tra record correlati. |
| [packages/ntruth/transparency.py](../../../packages/ntruth/transparency.py) | 72 | Trasparenza sul dominio e preflight conservativo (PRD NFR-14). |
| [packages/ntruth/verifier/__init__.py](../../../packages/ntruth/verifier/__init__.py) | 71 | Hard, semantic and policy verification of scientific outputs (PRD v6/v8/v9). |
| [packages/ntruth/verifier/hard.py](../../../packages/ntruth/verifier/hard.py) | 176 | Hard verifier sempre attivo, separato dal parser e dalle regole semantiche. |
| [packages/ntruth/verifier/output_policy.py](../../../packages/ntruth/verifier/output_policy.py) | 400 | Matrice normativa ``DeterminabilityState -> output``. |
| [packages/ntruth/verifier/semantic.py](../../../packages/ntruth/verifier/semantic.py) | 697 | Semantic verifier runtime indipendente dagli invarianti hard (ADR-0005/0006). |
| [packages/ntruth/verifier/v8.py](../../../packages/ntruth/verifier/v8.py) | 637 | Fail-closed progressive verifier for PRD v8 inputs, pins and claims. |
| [packages/ntruth/verifier/validation_stack.py](../../../packages/ntruth/verifier/validation_stack.py) | 445 | Stack di validazione a strati: la sintassi non equivale alla ricostruzione. |
