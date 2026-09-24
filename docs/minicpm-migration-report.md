# Report migrazione MiniCPM5-2B (ADR-0019) — confronto con Granite 4.1 3B

Data: 2026-09-17. Stato: migrazione architetturale/configurativa completata;
validazione runtime e scientifica **da svolgere**. Nessun peso scaricato in
questa fase; nessun training avviato.

## 1. Pin verificati (fonte: Hugging Face Hub API, settembre 2026)

| Artefatto | Valore |
|---|---|
| Canonico primario | `openbmb/MiniCPM5-2B` @ `12a3808a956f869c767195e9266b59c4d21d92e2` |
| MLX 4-bit ufficiale | `openbmb/MiniCPM5-2B-MLX` @ `8a9ad7539ac86281d0ac2b017ba04a5de53fe9a3` |
| Peso MLX | `model.safetensors`, singolo file, 1 416 035 216 byte |
| SHA-256 peso MLX | `c207798696a4a454e7ac211b25227625466c693335941cee8904fb922f295cc1` (LFS oid = SHA-256 del contenuto) |
| Ablation 1B canonico | `openbmb/MiniCPM5-1B` @ `87179e5c1f455ef22e6223592d2d61351b525bfc` |
| Ablation 1B MLX | `openbmb/MiniCPM5-1B-MLX` @ `9879b18bf2928355fcdf4287635388a3665a40cb`, 608 026 621 byte, SHA-256 `a23e0c5c79944a0b2cc92cb9ab79376b4dce41e2312383727e21ee43fe19cb4f` |
| GGUF | `openbmb/MiniCPM5-2B-GGUF` (riferimento nome; pin alla prima acquisizione) |
| Base (ablation) | `openbmb/MiniCPM5-2B-Base` (riferimento nome) |
| Licenza | Apache-2.0 ovunque (canonico, MLX, 1B) |

## 2. Confronto approfondito Granite 4.1 3B Instruct vs MiniCPM5-2B

### 2.1 Identità e governance (parità — nessun impatto su policy)

| Voce | Granite 4.1 3B | MiniCPM5-2B |
|---|---|---|
| Vendor | IBM (USA) | OpenBMB (CN, collab. accademica/industriale) |
| Release | 29 apr 2026 | 7 set 2026 (4 mesi più recente) |
| Licenza | Apache-2.0 | Apache-2.0 ✓ (ADR-0015/GRC invariati) |
| Uso commerciale | Sì | Sì |
| Dati training aperti | No (curatela IBM interna, GRC enterprise) | Sì, famiglia UltraData (Ultra-FineWeb, Code, Math, SFT, RL) |
| Local-first | Sì | Sì (nessun cambio di postura privacy/rete) |

La diversa provenienza geografica del vendor non ha effetti di governance:
pesi locali, licenza permissiva identica, nessuna telemetria (training offline,
`HF_HUB_OFFLINE=1` invariato).

### 2.2 Architettura e dimensione (vantaggio MiniCPM)

| Voce | Granite 4.1 3B | MiniCPM5-2B |
|---|---|---|
| Parametri | 3 402 836 480 (~3.40B) | 2 516 756 480 (~2.52B), **−26%** |
| Architettura | Dense decoder-only proprietario (GQA 40Q/8KV, RoPE, SwiGLU, tied embeddings) | **`LlamaForCausalLM` standard** (GQA 16Q/2KV, 42 layer) |
| Kernel custom | No, ma arch non-standard per MLX | **No, standard**: nessun fork model-code, compatibile con Outlines/vLLM/SGLang/llama.cpp nativi |
| Context configurato | 131 072 | 131 072 (parità; chunking gerarchico resta obbligatorio) |
| Peso MLX 4-bit | 2 127 162 429 byte (community) | 1 416 035 216 byte (ufficiale), **−33%** |
| Thinking mode | Assente | Presente ma **vietato** in N-Truth (`enable_thinking=false` fail-closed) |

Implicazioni QLoRA su M5 24 GB: base più piccola → meno memoria per pesi e
attivazioni, step più veloci, più margine per adapter rank-16 su 8 layer e
batch effettivo 8. Iperparametri LoRA invariati di proposito (comparabilità);
i target (`self_attn.q/k/v/o_proj`, `mlp.gate/up/down_proj`) hanno gli stessi
nomi perché entrambi seguono la convenzione layer Llama.

### 2.3 Distribuzione e fiducia dell'artefatto (vantaggio MiniCPM, strutturale)

| Voce | Granite 4.1 3B | MiniCPM5-2B |
|---|---|---|
| MLX Apple Silicon | **Solo community** (`mlx-community/...`, non IBM) | **Ufficiale vendor** (`openbmb/...-MLX`) |
| GGUF | Ufficiale IBM | Ufficiale OpenBMB |
| Quantizzate | Q4_K_M/Q5_K_M IBM | GPTQ + DSpark draft ufficiali |
| Single-file safetensors MLX | Sì (2.13 GB) | Sì (1.42 GB) |
| Finetune cookbook | Generici (Unsloth et al.) | **Ufficiali**: TRL+PEFT, LLaMA-Factory, ms-swift, unsloth + agent skills |

L'MLX ufficiale elimina un hop di fiducia (conversione community non
verificabile dal vendor) e semplifica il fingerprinting: pesi, revisione e
provenance provengono dallo stesso org del checkpoint canonico.

### 2.4 Training recipe e capacità dichiarate (segnale, non prova)

Granite 4.1: ~15T token in 5 fasi, SFT ~4.1M sample, RL on-policy GRPO/DAPO;
model-card: MMLU 67.02, IFEval 82.30, GSM8K 86.88, HumanEval 81.71, BFCL v3 60.80.

MiniCPM5-2B: base + mid-training (UltraData tiered), post-training SFT 400B
token deep-thinking + RL critic-based (JustRL II) + **OPD** (distillazione
on-policy da 16 teacher RL, +10.96 reasoning / +6.96 agentic dichiarati).

Head-to-head pubblicato da OpenBMB (stesso harness interno, media su
code/math/IF/knowledge/long-context/tool-use/agent): **MiniCPM5-2B 53.9**,
Qwen3.5-4B 51.1, **granite-4.2-3B 42.7** (modello Granite più recente del
4.1-3b), LFM2.5-2.6B 33.2. Picchi MiniCPM: AIME 2025/2026 86.5, MATH-500 94.6,
SWE-bench Verified 46.4 (vs 36.8 del 4B migliore), τ²-Bench Telecom 97.1.

**Caveat espliciti (non negoziabili):**
- harness vendor-side, nessuna verifica indipendente; gli score Granite-card
  provengono da harness diverso → **i numeri non sono confrontabili tra loro**;
- vietato qualsiasi claim di superiorità scientifica prima dei benchmark
  N-Truth (stessa regola di ADR-0010, ora ADR-0019);
- i benchmark decisivi restano: task staged v6 su Parser Gold futuro,
  calibrazione task-specific (ADR-0016), head-to-head MiniCPM vs Granite-legacy
  vs B5, external challenge.

### 2.5 Rischi specifici MiniCPM e mitigazioni

| Rischio | Mitigazione implementata |
|---|---|
| Thinking mode inietta `<think>` nel JSON | `enable_thinking=False` ovunque (backend, training, predict); TypeError → errore esplicito; gate `qualify_minicpm_runtime.py` con check `no_thinking_trace` |
| Template ChatML diverso dai role-tag Granite | Nome template versionato (`minicpm5_chatml_no_think`); hash pinnato in fingerprint alla prima acquisizione; cambio template invalida il binding (STALE) |
| Modello più recente, meno mileage ecosistemico | Ruolo provvisorio, scienza NOT_STARTED, rollback documentato (ADR-0019 §Rollback) |
| Stop token `<\|im_end|>` non verificati in generazione | Item esplicito in "non dichiarato completo"; smoke/qualify lo misurano |
| Budget memoria/disco ereditati da Granite | Mantenuti come **upper bound conservativi** (il 2B consuma meno); da rimisurare su MiniCPM prima di qualsiasi run reale |

## 3. Cosa è cambiato nel repository

**Nuovo (default MiniCPM):**
- `models/configs/minicpm5-2b-mlx-qlora.json` (primario), `minicpm5-1b-mlx-qlora.json` (ablation)
- `packages/ntruth/model_backends/minicpm.py` (`MiniCPMBackend`), errori `MiniCPMBackendError`
- `scripts/models/acquire_minicpm.py` (`--variant 2b|1b`, `--verify-only`)
- `scripts/models/qualify_minicpm_runtime.py` (10 gate, evidenza in `models/ntruth-minicpm-2b/manifests/`)
- `docs/adr/0019-minicpm5-2b-migration.md`, questo report

**Retrocessi a legacy (opt-in `NTRUTH_ALLOW_LEGACY_GRANITE=1` o `allow_legacy=True`):**
- `models/configs/granite-*.json` → `models/configs/legacy/`
- `GraniteBackend`, `acquire_granite.py`, `qualify_granite_runtime.py` (braccio di confronto storico, invariati)
- Registry: fingerprint Granite PARTIALLY_VERIFIED conservato, valido solo per quell'artefatto

**Registry/ledger:** `default_model_id=openbmb/MiniCPM5-2B`, runtime globale
`UNVERIFIED`, `qualified_artifact=null`, transizione append-only
PARTIALLY_VERIFIED→UNVERIFIED con rationale ADR-0019.

**Training lane ausiliaria** (`Documents/N-truth-training-lane`): **nessuna
modifica**. Verificato via inventario: la lane è encoder-only
(ModernBERT/BioClinical-ModernBERT per NER token-classification) e non referenzia
alcun modello generativo (zero occorrenze granite/qwen/minicpm come modello).
Il Train A generativo vive interamente nel repo N-Truth.

## 4. Prossimi passi ordinati (nessuno avviato)

1. `acquire_minicpm.py --confirm-license-and-download` (decisione owner) + `--verify-only`
2. `qualify_minicpm_runtime.py` → PARTIALLY_VERIFIED per il fingerprint esatto
3. Smoke engineering (`--runtime-smoke-only`) su profilo MiniCPM
4. Micro-benchmark M5 + profilo risorse misurato (sostituisce upper bound ereditati)
5. Head-to-head MiniCPM vs Granite-legacy su fixture sintetiche (exploratory, UNVERIFIED-compatibile)
6. Parser Gold → benchmark decisivi → eventuale promozione scientifica (gate invariati)
