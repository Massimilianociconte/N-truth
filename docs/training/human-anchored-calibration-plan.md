# Human-Anchored Calibration Plan (pre–substantive P0 LoRA)

**Stato:** ACTIVE priority  
**Gate:** `training_execution_gate: HOLD_PENDING_REAL_ANCHOR`  
**Data:** 2026-08-02

## Perché

P0-alpha sintetico (graph-first) è internamente coerente ma **non ancorato** al
linguaggio reale dei Methods. Un LoRA completo su 2 000 sintetici rischia di
misurare “quanto il modello impara il generatore”, non N-Truth.

Riferimenti di metodo (letteratura, non claim N-Truth):

- SynthIE: testo generato da output strutturato è utile per IE (EMNLP 2023).
- Low-resource: pochi esempi umani di qualità spostano le prestazioni più di
  grandi quantità di solo sintetico.
- Model collapse: conservare dati umani originali e lineage.

## Obiettivi minimi

| Set | Quantità | Uso |
|-----|----------|-----|
| Reality check | **10–20** blocchi reali (Methods/caption/sheet) | Schema/guideline non solo immaginati |
| Calibration pilot | **30–50** Experiment Block | Accordo, tempi, determinability, renderer quality |
| Unlabeled Methods | centinaia (target) | Calibrazione lessicale del renderer (non gold) |
| Held-out real eval | piccolo, separato | Mai in train, mai nei 39 B4 DEV |

I 39 casi `B4_CONSTRAINED_DEV` restano **sintetici/fixture di sviluppo**: non
sostituiscono il real gold.

## Cosa annotare (P0 only)

- evidence spans
- entities + types
- counts (quantifier, value/bounds, unit/scope)
- factor + levels + endpoint (espliciti)
- relazioni esplicite `nested_in` / `derived_from`

**Non** annotare ancora per il pilot P0: allocation implicita, independence,
coreference decisiva, estimand, n_independent, verdetti.

## Processi

1. Doppio review (o single + adjudication) sui campi decisivi.
2. Guideline versionata; inter-annotator agreement sul pilot.
3. Licenze/autorizzazioni per ogni sorgente (CC0/CC BY, lab MoU, ecc.).
4. Split: train real (futuro) ≠ calibration ≠ held-out ≠ B4 DEV ≠ External Challenge.

## Sequenza (HOLD → GO sostanziale)

1. Congelare P0-alpha come `SYN_G1_UNANCHORED` *(fatto)*.
2. Engineering smoke only (tubatura MLX) *(fatto, non qualità modello)*.
3. **Guideline reality-check P0 + Real Experiment Bundle** *(fatto, bozza)*.
4. **Trial interno 3–5 casi** (reali/pubblici, **non gold**) — *prossimo*.
5. Correggere categorie ambigue / tempi / campi onerosi.
6. Audit multi-agente read-only del progetto (sessione dedicata).
7. Integrare finding → **freeze guideline**.
8. Reality check formale **10–20**.
9. Audit umano ≥50 sintetici (può parallellarsi dopo freeze).
10. Calibration pilot **30–50** Experiment Block.
11. Development set reale + **P0-beta** ancorato.
12. Confrontare synthetic-only / real-only / hybrid.
13. Solo allora LoRA P0 **sostanziale** (`READY_FOR_ANCHORED_P0_EXPERIMENT`).

Artefatti annotazione:

- `docs/annotation-reality-check-p0-v0.1.md`
- `data/annotations/reality-check/`

## Decisione corrente

```text
HOLD sul training P0 completo
GO  su preparazione + smoke ingegneristico + real-data anchor
```

## Stati

```yaml
migration_status: ARCHITECTURE_MIGRATED
runtime_qualification_status: PARTIALLY_VERIFIED
scientific_validation_status: NOT_STARTED
training_program_status: P0_LORA_APPROVED
training_execution_gate: HOLD_PENDING_REAL_ANCHOR
engineering_smoke_training_allowed: true
substantive_p0_training_allowed: false
current_synthetic_snapshot_status: SYN_G1_UNANCHORED
```
