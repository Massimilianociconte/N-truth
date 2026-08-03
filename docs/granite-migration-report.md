# Migrazione architetturale a IBM Granite 4.1 3B completata — validazione runtime e scientifica in corso

**Data:** 2026-08-02  
**ADR:** [0010](adr/0010-granite-4.1-3b-migration.md)

## Verdetto di stato

> **Migrazione architetturale e configurativa a IBM Granite 4.1 3B completata; validazione runtime multipiattaforma, benchmark scientifici e fine-tuning ancora aperti.**

### Stati machine-readable (`models/registry/default.json` → `qualification`)

**Fonte di verità:** il registry (e il ledger SQLite delle transizioni), non questo report.  
Aggiornato in documentazione al 2026-08-02 per allineamento al registry.

| Campo | Valore attuale (verificato) | Significato |
|---|---|---|
| `migration_status` | **`ARCHITECTURE_MIGRATED`** | Codice/config/default backend migrati |
| `runtime_qualification_status` | **`PARTIALLY_VERIFIED`** | Solo per l’artefatto MLX community 4-bit con fingerprint registrato (non multipiattaforma, non `VERIFIED`) |
| `scientific_validation_status` | **`NOT_STARTED`** | Nessun gold/external challenge |
| `qualified_artifact` | **popolato** (fingerprint bound) | Pesi `mlx-community/granite-4.1-3b-4bit`, revision `b1b476b5…`, weights SHA-256 `cff9d052…` |

`PARTIALLY_VERIFIED` ≠ scientificamente validato. La qualifica **non** si trasferisce ad adapter, GGUF, BF16, altre revisioni o template.

**Binding obbligatorio:** ogni stato positivo è legato a un fingerprint esatto
(`model_id`, `model_revision`, `weights_sha256`, `adapter_sha256`,
`tokenizer_revision`, `chat_template_hash`, `quantization`, `backend`,
`backend_version`, `schema_version`, `task_profile`, `domain_profile`).
BF16/Transformers ≠ GGUF Q4 ≠ adapter successivo ≠ altro chat template.

| Campo | Valori |
|---|---|
| `runtime_qualification_status` | `UNVERIFIED` · `PARTIALLY_VERIFIED` · `VERIFIED` · `FAILED` · `STALE` |
| `scientific_validation_status` | `NOT_STARTED` · `PILOT_VALIDATED` · `EXTERNAL_VALIDATED` · `FAILED` · `INVALIDATED` |

`STALE` / `INVALIDATED` quando il fingerprint corrente diverge da `qualified_artifact`
(pesi, adapter, quantizzazione, tokenizer/template, schema, task, protocollo, ruleset
rilevante, runtime materialmente diverso).

**Gate (blocca i claim, non la ricerca):**

| Stato runtime | Consentito |
|---|---|
| `UNVERIFIED` | sviluppo, smoke, benchmark esplorativi |
| `PARTIALLY_VERIFIED` | pilot interni, calibration study |
| `VERIFIED` | external validation |
| `VERIFIED` + `EXTERNAL_VALIDATED` | release scientificamente supportata nel dominio dichiarato |

```python
evaluate_claim_gate("internal_pilot")
# {"allowed": False, "reason": "RUNTIME_UNVERIFIED",
#  "required_next_state": "PARTIALLY_VERIFIED", ...}

can_run_exploratory_benchmarks()  # True se non FAILED
can_run_internal_pilot()  # da PARTIALLY_VERIFIED
can_run_external_validation()  # solo VERIFIED
is_scientifically_releasable()  # VERIFIED + EXTERNAL_VALIDATED
evaluate_qualification_against_artifact(current_artifact={...})
canonical_fingerprint_hash(artifact)  # SHA-256 payload canonico
append_qualification_transition(...)  # log append-only auditabile
```

**Prossimo stato runtime:** `PARTIALLY_VERIFIED` richiede (senza real gold/FT):
pesi verificati, E2E inference, chat/stop, structured output, smoke candidate-only,
benchmark M5 24 GB iniziale, load/unload/resource manager senza errori critici,
fingerprint registrato.

**Persistenza append-only (ledger SQLite, tamper-evident locale):**
`models/registry/qualification_ledger.sqlite3` — trigger vietano `UPDATE`/`DELETE`;
`new_sequence == max+1` in `BEGIN IMMEDIATE`; hash chaining; evidence CA sotto
`qualification_evidence/`. Bootstrap con riga **GENESIS**, hash del JSON sorgente,
schema version; **no reseed** se `initialized=1` e catena vuota.

**Policy ledger-first:** SQLite e l’unica fonte autorevole; il mirror JSON e
sempre rigenerabile; un crash dopo COMMIT SQLite non annulla la transizione;
al load un mirror incoerente viene ricostruito. Non e tamper-proof (filesystem
completo): per release esterne ancorare l’ultimo `transition_hash` (tag firmato /
checksum / Ed25519).

**Locking:** il lock di processo protegge solo i writer che usano questa
implementazione; la protezione tra processi deriva da `BEGIN IMMEDIATE` e dai
vincoli SQLite. Usare il ledger su **filesystem locale affidabile** — evitare
DB SQLite su NFS, cartelle cloud-sync o storage con locking incerto.

**Stato ufficiale:**

> **Il codice è migrato a Granite. Il runtime Granite non è ancora qualificato e il modello non è ancora scientificamente validato come modello definitivo di N-Truth.**

| Ambito | Stato |
|---|---|
| Codice, interfacce, registry, default, docs, ADR, test strutturali | **Completato** (`ARCHITECTURE_MIGRATED`) |
| Qualificazione operativa (pesi locali, E2E, budget M5 su Granite, CI OS) | **`UNVERIFIED`** |
| Qualificazione scientifica (gold, B5 vs B6, external challenge) | **`NOT_STARTED`** |

Non confondere “migrazione del codice” con “modello scientificamente qualificabile”.

### Ordine corretto delle attività successive

1. Scaricare e verificare i pesi canonici.  
2. Eseguire un’inferenza reale con il backend Transformers.  
3. Verificare chat template, stop token e structured output.  
4. Eseguire il benchmark sul Mac M5 con 24 GB.  
5. Confrontare MLX e GGUF sullo stesso piccolo set.  
6. Attivare CI Windows e Linux.  
7. Eseguire la baseline few-shot su casi N-Truth.  
8. Solo dopo preparare LoRA/QLoRA e confronto B5/B6.  
9. Validare sul real gold.  
10. Eseguire l’External Challenge prima di qualunque claim scientifico.

## COMPLETATO

- backend provider-agnostic (`ModelBackend`);
- Granite come default (`ibm-granite/granite-4.1-3b`);
- Qwen rimosso dal percorso implicito (`models/configs/legacy/`);
- registry e configurazioni (`models/registry/default.json`, `.env.example`);
- profilo LoRA/QLoRA iniziale verificato su moduli Granite;
- script di acquisizione e verifica checksum MLX community;
- documentazione, ADR-0010 e test strutturali.

## DA VALIDARE

- inferenza end-to-end con pesi locali;
- chat template e stop conditions su tutti i backend;
- benchmark M5 24 GB **con Granite** (il budget M5 esistente è storico Qwen);
- conversione e parità GGUF/MLX;
- runtime Windows (llama.cpp/GGUF) e Linux (llama.cpp, Transformers, vLLM);
- fine-tuning reale;
- confronto B5 (cascata) vs monolitico Granite;
- metriche scientifiche sul real gold;
- external challenge.

## 1. Riferimenti Qwen individuati (audit)

| Area | Path / nota |
|---|---|
| Config default | era `models/configs/qwen3-4b-instruct-2507-mlx-qlora.json` → **legacy/** |
| CLI default | `packages/ntruth/training/cli.py` DEFAULT_PROFILE → Granite |
| Packaging | `pyproject.toml` hatch force-include → profilo Granite |
| Chat thinking | flag `enable_thinking` Qwen-specifici **rimossi** |
| LoRA keys | moduli verificati su architettura Granite (non ereditati implicitamente da Qwen) |
| Docs / tests / scripts | aggiornati ai default Granite |
| Artifacts locali Qwen | storici (`models/local/Qwen…`, smoke, budget protocol) |

## 2. Dati del modello (accuratezza)

| Campo | Valore | Nota |
|---|---|---|
| Instruct (default) | `ibm-granite/granite-4.1-3b` | post-trained; **nessun** repo `-instruct` su HF |
| Base | `ibm-granite/granite-4.1-3b-base` | solo ablation |
| Licenza | Apache-2.0 | |
| Parametri | 3 402 836 480 | |
| **Configured maximum context** | **131 072 token** | limite da `config.json`; **non** capacità già validata sul Mac M5 |
| GGUF ufficiale | `ibm-granite/granite-4.1-3b-GGUF` | es. Q4_K_M ~2.1 GB |
| MLX 4-bit | `mlx-community/granite-4.1-3b-4bit` | **conversione community MLX-LM, non artefatto ufficiale IBM** |

### Manifest MLX community (checksum verificato in streaming)

| Campo | Valore |
|---|---|
| repository | `mlx-community/granite-4.1-3b-4bit` |
| revisione | `b1b476b5a17c46b7d6cd663b4a8ed44b66720aef` |
| file | `model.safetensors` |
| dimensione | 2 127 162 429 byte |
| SHA-256 | `cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d` |
| conversione | MLX-LM (community); non firmata IBM |
| mlx-lm (dev profile) | 0.31.3 (runtime pin del progetto) |

## 3. Context 131K

Scrivere sempre:

> **Configured maximum context: 131 072 token**

La finestra **utilizzabile** dipende da backend, quantizzazione, KV cache, RAM, batch e latency budget. N-Truth deve continuare a usare **chunking gerarchico**; non caricare 131K per ogni bundle.

## 4. Target LoRA

Moduli coerenti con lo state dictionary Granite:

```text
self_attn.q_proj, self_attn.k_proj, self_attn.v_proj, self_attn.o_proj
mlp.gate_proj, mlp.up_proj, mlp.down_proj
```

Formulazione corretta:

> I target LoRA sono stati verificati direttamente sull’architettura e sullo state dictionary di Granite, anziché ereditati implicitamente dalla precedente configurazione Qwen.

(Nomi di proiezione simili a Qwen non equivalgono a “copiati da Qwen”.)

Prima del training lo script deve stampare moduli selezionati, parametri addestrabili, % trainabili e moduli mancanti (vedi profilo + future training hooks).

## 5. Runtime multipiattaforma (separazione Windows / Linux)

| OS | Percorsi supportati |
|---|---|
| **Windows** | llama.cpp + GGUF; CPU; CUDA se disponibile; Vulkan opzionale. **Non** vLLM nativo come runtime core. |
| **Linux** | llama.cpp; Transformers; vLLM (server); CUDA/ROCm/CPU. |
| **macOS** | MLX-LM (community quant) o llama.cpp Metal + GGUF. |

## 6. Legacy Qwen (opt-in esplicito)

| Scenario | Comportamento |
|---|---|
| Default / senza opt-in | Granite; Qwen **mai** selezionato implicitamente |
| `NTRUTH_MODEL_PROVIDER=legacy_qwen` senza opt-in | **errore** |
| `allow_legacy=True` **o** `NTRUTH_ALLOW_LEGACY_QWEN=1` | opt-in esplicito; caricamento legacy ammesso |
| Fallback silenzioso da config generica a Qwen | **vietato** |

## 7. Candidate-only (allineamento PRD)

```text
Granite → evidence, candidate facts, candidate graph, missing facts
rules engine + human → EU, n condizionale, limiti inferenziali
```

Rinforzi:

- schema parser senza verdetto/`n` finale pubblicabile;
- tipi distinti CandidateGraphSet vs RuleResult;
- confini di import (parser_ai ↛ rules; rules/graph ↛ parser_ai);
- CI / test strutturali.

## 8. Deliverable codice

| # | Deliverable | Dove |
|---|---|---|
| Backend | `packages/ntruth/model_backends/` | |
| Profilo | `models/configs/granite-4.1-3b-mlx-qlora.json` | |
| Registry | `models/registry/default.json` | |
| Acquisizione | `scripts/models/acquire_granite.py` | |
| ADR | `docs/adr/0010-granite-4.1-3b-migration.md` | |
| Conversione | `docs/model-granite-conversion.md` | |
| Multipiattaforma | `docs/model-multiplatform-runtime.md` | |

## 9. Rollback

1. Checkout pre-migrazione, oppure  
2. Opt-in esplicito legacy (non default CLI): profilo in `models/configs/legacy/` + `NTRUTH_ALLOW_LEGACY_QWEN=1` / `allow_legacy=True`.  
3. Nuovo ADR se Qwen tornasse default.

## Formulazione normativa

> IBM Granite 4.1 3B Instruct è il modello principale **provvisorio** del Train A. La sua adozione definitiva rimane subordinata ai benchmark N-Truth sui task decisivi, al confronto con la cascata B5 e alla validazione su dati reali indipendenti.
