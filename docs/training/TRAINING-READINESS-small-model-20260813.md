# Training readiness — modello piccolo — 2026-08-13

## Decisione

> **Non esistono ancora dati, schema, baseline ed evaluation sufficientemente
> autorizzati e indipendenti da giustificare il fine-tuning locale sostanziale.**

```yaml
normative_target: PRD_V9
implemented_root_contract: PRD_V7
v9_schema_conformance: BLOCKED_PENDING_CANONICAL_REGISTRY
substantive_training_allowed: false
scientific_readiness: FAIL
dataset_readiness: FAIL
schema_readiness: FAIL
evaluation_readiness: FAIL
infrastructure_readiness: PARTIAL
apple_silicon_feasibility: PASS
reproducibility: FAIL
overall: NOT_READY
```

Questa decisione sostituisce
[DECISION-hold-pending-real-anchor.md](DECISION-hold-pending-real-anchor.md). Il
documento precedente resta storico: la sua nomenclatura P0 non apre né sostituisce il
Reality Gate corrente.

## Base di evidenza

La valutazione usa evidenze locali osservabili e mantiene separati tre piani:

1. **integrità ingegneristica:** file, parser, manifest, hash e test;
2. **autorizzazione:** licenze, review, split e Reality Gate;
3. **validità scientifica:** gold reale, baseline, human ceiling ed external challenge.

Un PASS nel primo piano non viene promosso agli altri due.

Artefatti principali:

| Evidenza | Percorso | Significato limitato |
|---|---|---|
| Readiness machine-readable | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/training-readiness.final.json` | proiezione finale `NOT_READY`, exit code atteso `2`, `substantive_training_allowed=false` |
| Doctor Granite finale | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/granite-doctor.final.json` | `model_present=false`, `ready_to_train=false`, exit code atteso `2` e blocker FD |
| Canonical Merkle manifest | `/Volumes/FLASH128/N-Truth-Datasets/manifests/checksums/merkle_manifest.json` | root `68651452c3387e36c5358064fc89e7c2579838af54a6b3674783975b3a279b55`, 14.865 file; prova soltanto integrità dei file inclusi |
| Final refresh/resume/verify | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/final-refresh.log`, `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/final-resume.log` e `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/final-verify.log` | exit code `0`; resume con stesso Merkle, download e pin byte-identici e pin non riscritto |
| Corpus audit finale | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/corpus-audit.final.json` | 77.158 envelope validi, zero training/evaluation eligible e zero file `training_ready` |
| Quality reports | `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/quality/` | schema, leakage, artefatti, distribuzioni ed eligibility |
| Canonical dataset manifest | `/Volumes/FLASH128/N-Truth-Datasets/manifests/datasets.json` | stato, source ref, split, eligibility e blocker per corpus |
| Bundled public lock | `packages/ntruth/data/manifests/public_sources.lock.json` | URL, revisioni e hash fissati; non autorizzazione d'uso |
| Source portfolio | [source-portfolio-small-model-v1.md](source-portfolio-small-model-v1.md) | decisioni licenza/task/corpus con limiti espliciti |
| SourceData task manifest | `/Volumes/FLASH128/N-Truth-Datasets/task_corpora/entity_roles/sourcedata/v2.0.3/manifest.json` | corpus ausiliario costruito, `model_use_status=BLOCKED` |

La rigenerazione finale migra i marker raw legacy al contratto
`ntruth.authenticated-raw-marker.v1`: ogni marker lega dataset, source ref, hash
dell'archivio e commitment deterministico `ntruth.raw-tree-commitment.v1` del tree
estratto. Un marker precedente o un tree modificato non viene accettato in resume e
impone re-estrazione fail-closed dall'archivio pinned.

La proiezione ha checksum
`3e29872307c9867a5b33557c5bd98135346a9fd5868d2e4a0016723a43e46b8b`.
Il Reality Gate root incluso nell'artefatto ha checksum
`624fb7cacc9e70653b17ea9ce7936562945647873f52c049a48034de43022741`.

## Scientific readiness — FAIL

**Evidenze**

- il Reality Gate riporta `scientific_validation=NOT_STARTED`;
- non esiste un real anchor N-Truth sufficiente e approvato;
- non esistono human ceiling, feasibility pilot indipendente o external challenge
  eseguiti;
- i corpus pubblici annotano task adiacenti e non costituiscono truth per Experiment
  Graph, experimental unit, independent n o validità causale.

**Blocker**

`SCIENTIFIC_VALIDATION_NOT_COMPLETE`. Richiede lavoro umano/scientifico: registry e
guideline congelati, annotazione indipendente, agreement pre-adjudication,
adjudication, protocollo preregistrato e valutazione esterna.

## Dataset readiness — FAIL

**Evidenze**

- `data_readiness=BLOCKED` nel Reality Gate;
- sotto `/Volumes/FLASH128/N-Truth-Datasets/training_ready/` non esistono file o
  record training-ready; possono restare directory strutturali;
- SourceData: 75.163 record validi, ma 75.163 con valori identitari obbligatori vuoti,
  un leakage group conservativo cross-split e zero record model-eligible;
- PreClinIE: 1.450 record validi, zero model-eligible; i derivati restano bloccati per
  rights e mapping semantico;
- MeasEval: 448 record, 20 annotazioni mancanti, zero model-eligible; l'isolamento
  document-family è un requisito ingegneristico ma non risolve licenza o task fit;
- CRAFT: 97 record validi, tutti review-required e zero model-eligible;
- il manifest SourceData task-specific dichiara
  `data_readiness=BLOCKED`, `model_use_status=BLOCKED`,
  `ntruth_partition_approved=false` e
  `reality_gate_satisfied_by_public_corpora=false`.

**Blocker**

`ROOT_DATA_READINESS_BLOCKED`. Servono N-Truth GOLD reale, licence scope verificato,
split protetti, second review e decisive-field review. Non si risolve aumentando il
volume SILVER.

## Schema readiness — FAIL

**Evidenze**

- PRD v9 è il target normativo;
- il root implementa PRD v7;
- `v9_schema_conformance=BLOCKED_PENDING_CANONICAL_REGISTRY`;
- i predicate root `schema_stable_on_real_cases` e `no_blocking_schema_gaps` non sono
  entrambi veri;
- FactorRole, contrast semantics e distinzione tra observed evidence scope e target
  population claim non possono essere retrofittati localmente senza registry.

**Blocker**

`V9_CANONICAL_REGISTRY_PENDING` più `ROOT_SCHEMA_PREDICATES_BLOCKED`. Serve una
decisione centrale di governance/scientifica e una migrazione testata; un adapter
training-specific non può fungere da schema canonico.

## Evaluation readiness — FAIL

**Evidenze**

- `real_baseline_executed=UNKNOWN` nel Reality Gate;
- nessuna baseline rules-only, zero-shot, few-shot, retrieval o no-adapter è stata
  eseguita sul reference set reale;
- Granite, Qwen e Phi non sono stati confrontati su validation congelata;
- ModernBERT non è stato valutato come specialist baseline;
- non esiste confronto H, A e H+A;
- non sono disponibili per-class metrics, calibration, risk-coverage, OOD o failure
  taxonomy su N-Truth GOLD.

**Blocker**

`REAL_BASELINE_NOT_EXECUTED`. Il protocollo da preregistrare è in
[baseline-evaluation-protocol-v1.md](baseline-evaluation-protocol-v1.md). La training
loss o lo smoke runtime non sostituiscono le baseline.

## Infrastructure readiness — PARTIAL

**Evidenze positive, solo di configurazione/diagnostica**

- Apple Silicon `arm64`, 24 GiB e spazio pianificato superano i check del doctor;
- MLX-LM `0.31.3` è installato e coincide col profilo;
- esiste un profilo versionato
  `models/configs/granite-4.1-3b-mlx-qlora.json` con LoRA su base 4-bit, batch 1,
  gradient accumulation 8, checkpointing, context massimo operativo 1.024 e budget
  di picco MLX-LM 18 GiB;
- il profilo dichiara `configuration_defined_execution_blocked`,
  `runtime_qualification_status=NOT_RUN_CURRENT_PROFILE` e
  `synthetic_train_only=true`;
- il futuro training sostanziale richiede un authorization envelope canonico v1,
  non un bare Reality Gate, legato esattamente a view, seal, profilo, modello/revisione,
  source snapshot e seed;
- la CLI materializza una training view cieca allowlist-only (manifest/seal `1.0.0`)
  separata dal custody `2.0.0`.

**Limiti**

- `models/local/granite-4.1-3b-4bit/` è assente;
- il doctor riporta `model_present=false` e `ready_to_train=false`;
- Granite è `provisional_primary_train_a`, `scientifically_selected=false` e
  `NOT_RUN_CURRENT_PROFILE` nel profilo;
- manca un runner privato che consegni a MLX esclusivamente file descriptor read-only
  anonimi/unlinked ereditati;
- tokenizzazione, training sostanziale/smoke, prediction, metriche, calibrazione,
  resume/checkpoint ed export falliscono chiuso;
- il doctor deve riportare sempre `ready_to_train=false` e include il blocker FD in
  `execution_blockers`; la proiezione readiness espone lo stesso codice sia in
  `infrastructure.blockers` sia in `overall_blockers`;
- nessun run sul profilo Granite corrente è stato eseguito;
- il primary non ha battuto Qwen/Phi su evaluation congelata;
- protected test/external, permit monouso, ledger append-only, attestation verificabile
  ed export finale restano intenzionalmente bloccati.

**Blocker**

`MODEL_SELECTION_BENCHMARK_PENDING`, blocker
`anonymous_unlinked_inherited_fd_runner` e protected evaluation assente. Il download
del modello non risolve nessuno di questi gate.

## Apple Silicon feasibility — PASS

**Evidenze**

- target osservato: Apple Silicon `arm64`, 24 GiB di memoria unificata;
- il doctor passa piattaforma, memoria, runtime e headroom disco;
- un adapter training 4-bit su candidati 3B–4B è tecnicamente realistico con batch 1,
  accumulation e checkpointing;
- il profilo riserva 35,3 GiB entro un cap di workspace di 40 GiB.

Questo PASS significa soltanto **fattibilità tecnica pianificata**. Non autorizza
training, non seleziona Granite e non dimostra sostenibilità di un run completo.

## Reproducibility — FAIL

**Evidenze positive**

- revisioni e hash di archivi/dataset sono registrati;
- manifest, log e result file finali hanno nomi canonici; il Merkle osservato è
  `68651452c3387e36c5358064fc89e7c2579838af54a6b3674783975b3a279b55`
  su 14.865 file e il resume non ha riscritto il pin;
- seed, profilo e model revision hanno contratti versionati;
- authorization envelope e binding hanno un contratto v1 fail-closed.

**Perché resta FAIL**

- `protected_split_frozen=UNKNOWN`;
- `licence_scope_verified=UNKNOWN`;
- non esiste uno snapshot training autorizzato;
- non esiste il runner FD e quindi non viene creato un run-state corrente;
- resume e checkpoint sono indisponibili;
- test/external non sono ancora un protected evaluation bundle congelato e affidato a
  custodia indipendente;
- schema v9, baseline protocol e model selection non sono frozen.

**Blocker**

`FROZEN_REPRODUCIBLE_SNAPSHOT_NOT_AUTHORIZED`. La riproducibilità tecnica di file non
compensa l'assenza di autorizzazione e indipendenza scientifica.

## Scelta del modello

Non esiste ancora un modello vincitore.

| Modello | Ruolo corrente | Decisione |
|---|---|---|
| `ibm-granite/granite-4.1-3b` | primary provvisorio | profilo tecnico disponibile; non scaricato e non selezionato scientificamente |
| `Qwen/Qwen3-4B-Instruct-2507` | challenger | mantenere nel torneo no-adapter |
| `microsoft/Phi-4-mini-instruct` | challenger | mantenere nel torneo no-adapter |
| `answerdotai/ModernBERT-base` | specialist baseline | extraction/routing soltanto, non Experiment Graph generator |

La scelta finale richiede qualità strutturata, calibrazione, OOD, H+A, memoria,
latenza, tokenizer/lingua e licenza sul medesimo validation set congelato.

## Decisione sul training e sullo smoke

**Training sostanziale:** vietato.

**Nuovo smoke training:** non eseguibile. Non esiste un'eccezione al blocker FD;
`runtime-smoke-only` fallisce chiuso e non produce run-state, checkpoint, loss o
metriche. Un futuro smoke minimale potrà essere la prima esecuzione soltanto dopo il
runner anonymous/unlinked inherited read-only FD e una nuova autorizzazione.

## Sequenza per riaprire la decisione

1. Congelare registry, schema, Rulebook e guideline PRD v9.
2. Chiudere licenze/DUA e provenance per gli asset effettivamente necessari.
3. Produrre real anchor e pilot GOLD con review indipendente/adjudication.
4. Congelare train/validation e un protected vault test/external con custode.
5. Materializzare la training view cieca e provarne la non-lettura degli split
   protetti.
6. Implementare e revisionare il runner anonymous/unlinked inherited read-only FD.
7. Eseguire rules, zero-shot, few-shot, retrieval e ModernBERT soltanto tramite il
   runner verificato.
8. Confrontare Granite, Qwen e Phi no-adapter su validation.
9. Preregistrare soglie, H/A/H+A e criteri di stop.
10. Creare l'authorization envelope v1 per un singolo run e rivalutare la readiness.

## Blocker non automatizzabili

- scelta e approvazione scientifica del registry v9;
- annotatori indipendenti, adjudicator e agreement;
- data-steward review per licenze/privacy;
- custodia umana di test/external e autorizzazione one-time;
- security review del runner FD e integrazione MLX/tokenizer senza path reopen;
- soglie di successo definite con biostatistico e wet-lab lead;
- decisione finale sul valore scientifico del fine-tuning rispetto a prompting/RAG.

Fino alla loro chiusura, l'esito resta **NOT READY**.
