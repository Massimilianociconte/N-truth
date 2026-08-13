# Migrazione architetturale Granite — configurazione corrente con esecuzione bloccata

**Data:** 2026-08-02  
**ADR:** [0010](adr/0010-granite-4.1-3b-migration.md)

> **Nota di stato (2026-08-13).** Questo report conserva la decisione architetturale
> del 2 agosto, ma i precedenti claim di qualifica runtime sono superseded. La fonte
> corrente è [TRAINING-READINESS-small-model-20260813.md](training/TRAINING-READINESS-small-model-20260813.md)
> insieme alla [specifica MLX fail-closed](mlx-training-pipeline.md). Il target
> normativo corrente è PRD v9; il contratto root implementato resta PRD v7 e la
> conformità v9 è bloccata in attesa del registry canonico v9.

## Verdetto di stato

> **Granite resta un profilo tecnico provvisorio, non scientificamente selezionato; il
> profilo corrente non è stato qualificato ed ogni operazione ML è bloccata.**

### Stato machine-readable corrente

| Campo | Valore corrente | Significato |
|---|---|---|
| `status` | **`configuration_defined_execution_blocked`** | Configurazione definita, non capability operativa |
| `selection_role` | **`provisional_primary_train_a`** | Primary tecnico provvisorio |
| `scientifically_selected` | **`false`** | Nessun confronto baseline decisivo eseguito |
| `runtime_qualification_status` | **`NOT_RUN_CURRENT_PROFILE`** | Nessuno smoke Granite corrente |
| `scientific_validation_status` | **`NOT_STARTED`** | Nessun gold/external challenge |
| `synthetic_train_only` | **`true`** | Non abilita training sintetico nello stato corrente |
| `execution_blocker` | **`anonymous_unlinked_inherited_fd_runner`** | Runner FD non implementato |

`ntruth-ml check` deve restituire sempre `ready_to_train=false`. Nessuna qualifica di
artefatti o profili storici si trasferisce al profilo corrente, ad adapter, GGUF,
BF16, revisioni o template differenti.

**Requisito per una futura qualifica positiva:** ogni stato positivo dovrà essere
legato a un fingerprint esatto
(`model_id`, `model_revision`, `weights_sha256`, `adapter_sha256`,
`tokenizer_revision`, `chat_template_hash`, `quantization`, `backend`,
`backend_version`, `schema_version`, `task_profile`, `domain_profile`).
BF16/Transformers ≠ GGUF Q4 ≠ adapter successivo ≠ altro chat template.

Il vocabolario seguente documenta la proposta storica di qualification registry;
non descrive un registry implementato nel checkout corrente:

| Campo | Valori |
|---|---|
| `runtime_qualification_status` | `UNVERIFIED` · `PARTIALLY_VERIFIED` · `VERIFIED` · `FAILED` · `STALE` |
| `scientific_validation_status` | `NOT_STARTED` · `PILOT_VALIDATED` · `EXTERNAL_VALIDATED` · `FAILED` · `INVALIDATED` |

`STALE` / `INVALIDATED` quando il fingerprint corrente diverge da `qualified_artifact`
(pesi, adapter, quantizzazione, tokenizer/template, schema, task, protocollo, ruleset
rilevante, runtime materialmente diverso).

**Gate corrente:** tokenizzazione, training/smoke, prediction, metriche/calibrazione,
resume/checkpoint ed export falliscono chiusi. Prima di qualunque qualifica runtime
serve un runner privato che consumi esclusivamente file descriptor read-only
anonimi/unlinked ereditati. Per il training sostanziale servirà inoltre un canonical
authorization envelope v1 legato esattamente a view, seal, profilo, modello/revisione,
source snapshot e seed; un bare Reality Gate non è sufficiente.

**Proposta storica non implementata:** il report del 2 agosto descriveva un
`models/registry/` con ledger SQLite append-only, mirror JSON ed evidence
content-addressed. Questi percorsi e meccanismi non esistono nel checkout corrente e
non sono una fonte di autorità. Prima di riproporli serve una nuova decisione coerente
con il registry canonico PRD v9 e con l'attuale authorization envelope v1.

**Stato ufficiale:**

> **La configurazione Granite esiste, ma l'esecuzione è bloccata; il profilo corrente
> non è qualificato e il modello non è scientificamente selezionato.**

| Ambito | Stato |
|---|---|
| Profilo Granite, default esplicito della CLI MLX, documentazione e test fail-closed | **Presenti nel checkout** |
| Backend provider-agnostic, model registry/ledger e script dedicati `scripts/models/` | **Non implementati** |
| Qualificazione operativa del profilo corrente | **`NOT_RUN_CURRENT_PROFILE`** |
| Qualificazione scientifica (gold, B5 vs B6, external challenge) | **`NOT_STARTED`** |

Non confondere “migrazione del codice” con “modello scientificamente qualificabile”.

### Ordine futuro dopo la rimozione verificata del blocker FD

1. Implementare e verificare il runner FD anonimo/unlinked inherited read-only.
2. Chiudere gate scientifici, dati, schema, evaluation e riproducibilità.
3. Fissare modello/revisione e authorization envelope v1 canonico.
4. Solo allora eseguire le baseline no-adapter secondo protocollo.
5. Se giustificato dalle baseline, qualificare il runtime Granite sul Mac target.
6. Solo dopo valutare un minimal training run e il confronto B5/B6.
7. Validare sul real gold ed eseguire l'External Challenge prima di claim scientifici.

## PRESENTE NEL CHECKOUT CORRENTE

- profilo Granite come default esplicito della CLI `ntruth-ml`;
- profilo Qwen sotto `models/configs/legacy/`, selezionabile solo passando
  esplicitamente `--profile`;
- configurazione LoRA/QLoRA provvisoria con target modules dichiarati nel profilo;
- comandi `ntruth-ml download-model` e `ntruth-ml verify-model` integrati nel runtime;
- readiness PRD v9-target, authorization envelope v1 e blocco fail-closed delle
  operazioni ML-consuming;
- documentazione, ADR-0010 e test strutturali.

Non sono presenti `ModelBackend` / `GraniteBackend`, `models/registry/`, il ledger
SQLite, `scripts/models/acquire_granite.py` o un meccanismo `allow_legacy` via API o
variabile d'ambiente.

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
| CLI default | `packages/ntruth/training/cli.py` `DEFAULT_PROFILE` → Granite |
| Packaging | `pyproject.toml` hatch force-include → profilo Granite |
| Chat thinking | flag `enable_thinking` Qwen-specifici **rimossi** |
| LoRA keys | target configurati per Granite; verifica sul checkpoint esatto ancora richiesta |
| Docs / test | profilo Granite documentato e coperto dai gate fail-closed |
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

### Metadati attesi fissati nel profilo

I valori seguenti sono pin configurativi. Non attestano che i pesi siano presenti o
che il checksum sia stato verificato nel checkout corrente; tale evidenza può essere
prodotta solo da una verifica corrente del modello locale.

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

Formulazione corretta allo stato corrente:

> I target LoRA sono configurati per le proiezioni dichiarate da Granite e dovranno
> essere verificati sul checkpoint esatto prima di qualunque training autorizzato;
> non sono ereditati implicitamente dalla precedente configurazione Qwen.

(Nomi di proiezione simili a Qwen non equivalgono a “copiati da Qwen”.)

Prima del training lo script deve stampare moduli selezionati, parametri addestrabili, % trainabili e moduli mancanti (vedi profilo + future training hooks).

## 5. Alternative runtime multipiattaforma (non implementate o qualificate qui)

| OS | Percorsi architetturali da validare |
|---|---|
| **Windows** | llama.cpp + GGUF; CPU; CUDA se disponibile; Vulkan opzionale. **Non** vLLM nativo come runtime core. |
| **Linux** | llama.cpp; Transformers; vLLM (server); CUDA/ROCm/CPU. |
| **macOS** | MLX-LM (community quant) come profilo corrente; llama.cpp Metal + GGUF resta alternativa da qualificare. |

## 6. Legacy Qwen (opt-in esplicito)

| Scenario | Comportamento |
|---|---|
| Default / senza opt-in | Granite; Qwen **mai** selezionato implicitamente |
| `--profile models/configs/legacy/qwen3-4b-instruct-2507-mlx-qlora.json` | unico opt-in reale; si applicano gli stessi gate fail-closed |
| `allow_legacy=True` o `NTRUTH_ALLOW_LEGACY_QWEN=1` | non implementati; non costituiscono opt-in |
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

## 8. Deliverable del checkout corrente

| # | Deliverable | Dove |
|---|---|---|
| Profilo | `models/configs/granite-4.1-3b-mlx-qlora.json` | |
| Runtime/CLI fail-closed | `packages/ntruth/training/mlx_runtime.py`, `packages/ntruth/training/cli.py` | |
| Readiness | `packages/ntruth/training/readiness.py` | |
| ADR | `docs/adr/0010-granite-4.1-3b-migration.md` | |

Backend provider-agnostic, registry/ledger e script dedicati di acquisizione restano
proposte storiche, non deliverable implementati.

## 9. Rollback

1. Checkout pre-migrazione, oppure  
2. Opt-in esplicito legacy (non default CLI): passare
   `--profile models/configs/legacy/qwen3-4b-instruct-2507-mlx-qlora.json`.
3. Nuovo ADR se Qwen tornasse default.

## Formulazione normativa

> IBM Granite 4.1 3B Instruct è il modello principale **provvisorio** del Train A. La sua adozione definitiva rimane subordinata ai benchmark N-Truth sui task decisivi, al confronto con la cascata B5 e alla validazione su dati reali indipendenti.
