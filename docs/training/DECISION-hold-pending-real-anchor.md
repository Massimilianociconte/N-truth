# Decisione: HOLD training P0 sostanziale

**Data:** 2026-08-02  
**Aggiornamento strategico:** 2026-08-02 (post first real-source trial + AI diagnostic comparison)

**Verdetto operativo:**

```text
HOLD sul training P0 sostanziale (LoRA vero)
GO  su protocollo, dati reali, track deterministico, runtime, partnership, audit
```

Non si ferma l’intero progetto: si sospende solo **insegnare al modello** finché non è chiaro e affidabile **che cosa** vogliamo insegnargli.

## Stati machine-readable

```yaml
migration_status: ARCHITECTURE_MIGRATED
runtime_qualification_status: PARTIALLY_VERIFIED
scientific_validation_status: NOT_STARTED
training_program_status: P0_LORA_APPROVED
training_execution_gate: HOLD_PENDING_REAL_ANCHOR
engineering_smoke_training_allowed: true
substantive_p0_training_allowed: false
current_synthetic_snapshot_status: SYN_G1_UNANCHORED
annotation_protocol_status: REALITY_CHECK_PROTOCOL_DRAFT
real_anchor_status: NOT_STARTED
```

## Colli di bottiglia e sequenza corretta

Il collo di bottiglia non è “più epoch su sintetico”, ma **testi sperimentali reali con annotazioni umane affidabili**.

I casi reali **non** entrano subito nel LoRA: prima correggono schema, guideline e generatore sintetico.

```text
persone e dati reali
→ protocollo stabile
→ synthetic factory ancorata
→ training ibrido
→ valutazione indipendente
```

### 1. Chiudere il trial umano attuale (`reb-20260802-003`)

```text
seconda annotazione umana cieca
→ freeze
→ confronto human–human
→ eventuale adjudication
```

- Packet: `HUMAN_SECOND_REVIEW_PACKET_READY` (finché il revisore non avvia).
- Non modificare la guideline sulla base del solo confronto primary–AI.
- Una review umana completa **non** rende da sola il bundle real anchor / gold.

### 2. Guideline v0.2 (bozza, non definitiva)

Dopo confronto umano, candidati minimi:

- `allocation` vs `application`
- dichiarazione di replica vs meccanismo documentato
- conteggi biologici vs tecnici
- plate come contenitore
- `nested_in` / `derived_from` / `observed_in`
- dual cell line / dual endpoint
- campi che restano `UNKNOWN` / `NOT_REPORTED`

### 3. Almeno un altro caso reale

Preferibilmente diverso dal primo (es. coltura primaria, imaging, Methods+caption, gerarchie meno esplicite). Serve a testare se le correzioni v0.2 sono generali.

### 4. Raccolta formale

```text
3–5 trial reali
→ guideline sufficientemente stabile
→ formal 10–20 (reality check strutturato)
→ calibration pilot ~30–50 Experiment Block (nucleo per primo LoRA sostanziale)
```

Nota: 30–50 sono **Experiment Block**, non necessariamente 50 paper; un articolo può contribuire più block se separati correttamente.

## Split prima del training

I dati reali **non** vanno tutti in train:

```text
real-anchor train
real development
real test   # escluso da train, HPO, prompt, correzione generator, checkpoint selection
```

External Challenge futuro: insieme indipendente ulteriore.

## Disegno di training (quando il gate si apre)

Ibrido, non “solo pochi reali” e non “solo 2000 synth”:

```text
sintetici graph-first
+ piccolo nucleo reale annotato
+ structured decoding
```

Confrontare almeno:

1. Granite base + constrained decoding  
2. LoRA synthetic-only  
3. LoRA real-only ridotto  
4. LoRA synthetic + real anchor  

Il reale serve anche a ricalibrare il sintetico → P0-beta ancorato.

## Gate prima del LoRA sostanziale

```yaml
human_second_review_completed: true          # sul pilot decisivo, non solo AI
guideline_frozen_for_pilot: true
blocking_schema_gaps: 0
real_experiment_blocks_reviewed: "circa 30–50"
decisive_fields_double_reviewed: true
train_dev_test_split_frozen: true
synthetic_factory_human_calibrated: true
training_execution_gate: READY_FOR_ANCHORED_P0_EXPERIMENT
```

A quel punto:

```yaml
# da
training_execution_gate: HOLD_PENDING_REAL_ANCHOR
# a
training_execution_gate: READY_FOR_ANCHORED_P0_EXPERIMENT
```

**senza** ancora cambiare:

```yaml
scientific_validation_status: NOT_STARTED
```

## Binari paralleli (GO mentre si aspettano annotatori)

| Binario | Contenuto | Dipende da LoRA? |
|---------|-----------|------------------|
| **Dati e protocollo** | human second, v0.2 draft, altri trial reali, partnership | no |
| **Audit multi-agente** | read-only full repo (coda; sessione dedicata) | no |
| **Track deterministico** | rules, proof trace, DeterminabilityState, fixture, test negativi | no |
| **Runtime qualification** | verso `VERIFIED`: multi-replica, memory, recovery, budget M5 | no |
| **Collaborazioni** | wet-lab second annotator, biostat, lab partner, licenze | no |
| **LoRA sostanziale** | **HOLD** | sì — gated |

Engineering smoke già completato resta sacrificabile; non è qualità scientifica.

## Formulazione ufficiale

> Il protocollo LoRA P0 è progettato (`P0_LORA_APPROVED`) ma l’esecuzione  
> sostanziale è in **HOLD** in attesa di real-data anchor e split congelati.  
> Non si ferma N-Truth: si ferma solo l’addestramento sostanziale.  
> Prima del training, i casi reali devono stabilizzare protocollo, schema e factory.  
> Il prossimo aggiornamento utile sul trial 003 è il **freeze della second review umana**.  
> Priorità: **persone e dati reali → protocollo → synthetic ancorato → ibrido → eval indipendente**.
