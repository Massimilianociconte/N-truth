# ADR-0012 — Approvazione esperimento LoRA P0 (non validazione scientifica)

**Stato:** accettato  
**Data:** 2026-08-02

## Contesto

Baseline B4:

- constrained decoding → schema stage ~100% (condizione C);
- semantic F1 medio ~0.17 su 39 casi DEVELOPMENT;
- failure mode: missed/hallucinated evidence, wrong entity/count, unsupported relations.

## Decisione

1. Autorizzare **solo** `training_program_status: P0_LORA_APPROVED`.
2. **Non** modificare:
   - `runtime_qualification_status` (resta `PARTIALLY_VERIFIED`);
   - `scientific_validation_status` (resta `NOT_STARTED`).
3. Primo adapter `p0-alpha` su task:
   - TASK_EVIDENCE, TASK_ENTITY_COUNT, TASK_FACTOR_ENDPOINT, TASK_EXPLICIT_RELATIONS.
4. Dataset: sintetico graph-first P0-alpha; i 39 casi restano DEV immutabili.
5. Inferenza: Outlines obbligatorio; LoRA impara il contenuto.

## Conseguenze

- Il fine-tuning è un **synthetic pre-adaptation experiment**.
- Promozione scientifica richiede real gold + External Challenge.
- Confronto obbligatorio pre/post su B4_CONSTRAINED_DEV con scorer 1.0.0.

## Emendamento (stesso giorno): HOLD esecuzione sostanziale

Decisione successiva: **non** eseguire il LoRA P0 completo su P0-alpha finché
manca un real-data anchor (PRD calibration pilot, SYNTHETIC_HEAVY con real gold).

```yaml
training_execution_gate: HOLD_PENDING_REAL_ANCHOR
engineering_smoke_training_allowed: true
substantive_p0_training_allowed: false
current_synthetic_snapshot_status: SYN_G1_UNANCHORED
```

Autorizzato solo smoke tubatura (`ENGINEERING_SMOKE_ONLY`), non promozione adapter.

## Riferimenti

- TDS: `docs/training/p0-alpha-training-data-specification.md`
- Semantic report: `benchmarks/fewshot_p0/constrained/SEMANTIC_C_REPORT.md`
- ADR-0010, ADR-0011
