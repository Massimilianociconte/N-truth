# Training Data Specification — P0-alpha

**Stato:** APPROVED_FOR_EXPERIMENT (non per claim scientifici)  
**Snapshot target:** `p0-alpha`  
**Decisione a monte:** `GO_LORA_P0` (semantic B4 C, F1≈0.17 su DEV)  
**Data:** 2026-08-02

## Stati ufficiali (immutati da questo documento)

```yaml
migration_status: ARCHITECTURE_MIGRATED
runtime_qualification_status: PARTIALLY_VERIFIED
scientific_validation_status: NOT_STARTED
training_program_status: P0_LORA_APPROVED   # protocollo progettato
training_execution_gate: HOLD_PENDING_REAL_ANCHOR
engineering_smoke_training_allowed: true
substantive_p0_training_allowed: false
current_synthetic_snapshot_status: SYN_G1_UNANCHORED
```

`P0_LORA_APPROVED` significa che il **protocollo** è progettato, non che i dati
siano sufficienti. Il training P0 **completo** resta in HOLD finché non esiste un
real-data anchor (vedi `human-anchored-calibration-plan.md`).

È autorizzato solo un **engineering smoke** sacrificabile (`ENGINEERING_SMOKE_ONLY`).

## Obiettivo

Migliorare la **semantica P0** rispetto alla baseline B4 condizione C
(zero-shot + constrained), mantenendo:

- structured decoding (Outlines) in inferenza;
- candidate-only (no n / verdict / RuleResult);
- separazione dal rules engine;
- i **39 casi** B4 esclusivamente come DEV congelato.

## Task in scope

| Task tag | Target schema stage | Contenuto |
|----------|---------------------|-----------|
| `TASK_EVIDENCE` | `EvidenceExtractionStage` | span di evidenza |
| `TASK_ENTITY_COUNT` | `EntityCountStage` | entità + conteggi |
| `TASK_FACTOR_ENDPOINT` | mini factor/endpoint (nel grafo minimale o stage dedicato) | fattori, livelli, endpoint |
| `TASK_EXPLICIT_RELATIONS` | `CandidateRelationStage` | nested_in / derived_from espliciti |

## Out of scope (primo adapter)

- allocation implicita, independently_assigned
- decisive coreference, alternative graph complessi
- estimand / inference target
- `CandidateGraphSet` completo come target di training
- n_independent, pseudoreplication verdict, RuleResult, test statistico

## Composizione snapshot P0-alpha (sperimentale)

| Sorgente | Target quantitativo | Grado | Uso |
|----------|--------------------:|-------|-----|
| Sintetico graph-first | 1 500–3 000 | SYN-G0/G1 | TRAIN + VAL |
| Counterfactual / negative | ~20% del sintetico | SYN-G0 | TRAIN |
| Silver auditato | 0–300 | se disponibile | TRAIN opzionale |
| Real gold | 0–50 | se disponibile | TRAIN/VAL separato |
| B4 39 casi | 39 | DEV | **solo evaluation** |

Miscela **sintetica iniziale** (non definitiva PRD):

- 70% graph-first positivo
- 20% counterfactual / perturbed / negative
- 10% empty-legitimate / distractor

La miscela definitiva richiederà confronti real-only / synthetic-only / hybrid sul
development reale quando esisterà gold reale sufficiente.

## Flusso graph-first obbligatorio

```text
canonical graph (structured)
  → observation mask (fatti visibili)
  → renderer (Methods-like text)
  → stage target (JSON schema stage)
  → validator (schema + candidate-only + referential)
  → family split
```

Ogni record conserva:

- `family_id`, `leakage_group`
- `graph_hash`, seed, renderer version
- `perturbation_manifest`
- `task`, `schema_version`
- `source_type` = `synthetic_graph_first` | `silver` | `real_gold`
- `training_eligible`, `evaluation_eligible`
- `generator_inaccessible` per DEV B4

## Split

```text
TRAIN_P0          training_eligible=true
VALIDATION_P0     evaluation only (synthetic holdout families)
B4_CONSTRAINED_DEV  39 casi: training_eligible=false, immutable
TEST_REAL_PLACEHOLDER  vuoto, inaccessibile
```

Regole anti-leakage:

1. Nessuna `family_id` attraversa gli split.
2. Nessuna parafrasi dello stesso grafo in train e val.
3. I 39 DEV non sono demo, non sono parafrasati, non entrano nel generator come seed testuale.
4. Similarity gate: rifiutare train se Jaccard/shingle troppo vicino a un testo DEV.
5. Il generator non riceve predizioni C né il file DEV come corpus.

## Quality gate pre-training

Il lotto fallisce se:

- schema validity &lt; 100% sui target
- candidate-only &lt; 100%
- relazioni dangling o evidence orfane
- split contamination family/DEV
- dedupe fallita (exact hash)
- report diversità assente

Audit umano: almeno 50 esempi stratificati (KEEP/REVISE/QUARANTINE) prima di
chiamare un lotto “training-approved” G2. P0-alpha può partire come G0/G1
**synthetic pre-adaptation experiment** se l’audit non è ancora completo, con
etichetta esplicita.

## Training (curriculum)

| Fase | Contenuto |
|------|-----------|
| A | evidence, entity/count, factor/endpoint |
| B | explicit relations |
| C | multi-task mix + replay |

Inferenza: **Outlines** resta obbligatorio; LoRA impara il contenuto.

Adapter unico `p0-alpha` con metriche per task.

## Successo vs baseline C (DEV 39)

Misurare pre/post con scorer v1.0.0:

- evidence / entity / count / relation F1
- hallucinated entity, unsupported relation
- empty-output rate
- schema + candidate-only invariati
- bootstrap CI 95%

Decisioni post-training:  
`PROMOTE_P0_ADAPTER_FOR_B5_EVALUATION` | `REVISE_DATA_MIX` | `REVISE_TRAINING` | `CHANGE_MODEL_OR_ARCHITECTURE`

**Mai** aggiornare `scientific_validation_status` da questo esperimento.

## Artefatti attesi

- Dataset Card + manifest + checksum
- LoRA config + adapter + logs + resource report
- Evaluation pre/post + failure taxonomy delta
- ADR + changelog + rollback

## Formulazione ufficiale

> Il programma training P0 è approvato come esperimento.  
> Granite resta PARTIALLY_VERIFIED sul fingerprint MLX.  
> Nessuna validazione scientifica finché non esisterà real gold indipendente e External Challenge.
