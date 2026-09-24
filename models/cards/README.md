# Model cards locali

## Primario provvisorio (Train A)

**MiniCPM5-2B** — `openbmb/MiniCPM5-2B`

- Licenza: Apache-2.0  
- Model card: https://huggingface.co/openbmb/MiniCPM5-2B  
- Architettura: `LlamaForCausalLM` standard (nessun kernel custom)  
- Ruolo: **modello principale provvisorio** del Train A (ADR-0019)  
- Stato: `scientifically_selected=false`  
- Registry qualification (machine-readable, **artifact-bound**; source: `models/registry/default.json`):  
  - `migration_status: ARCHITECTURE_MIGRATED`  
  - `runtime_qualification_status: UNVERIFIED` (pesi mai acquisiti su host)  
  - `scientific_validation_status: NOT_STARTED`  
  - `qualified_artifact`: null finché `qualify_minicpm_runtime.py` non passa  
  - Una validazione non si trasferisce tra artefatti diversi (`STALE` / `INVALIDATED`).  
- Official status: *code migrated; runtime UNVERIFIED; model not scientifically validated as definitive N-Truth.*  
- Formulazione normativa:

> MiniCPM5-2B è il modello principale provvisorio del Train A.
> La sua adozione definitiva rimane subordinata ai benchmark N-Truth sui task
> decisivi, al confronto con il braccio legacy Granite e la cascata B5, e alla
> validazione su dati reali indipendenti.

Distribuzioni:

| Artefatto | ID |
|---|---|
| Canonical safetensors | `openbmb/MiniCPM5-2B` @ `12a3808a…` |
| MLX 4-bit (bootstrap macOS) | `openbmb/MiniCPM5-2B-MLX` @ `8a9ad753…` (**ufficiale vendor**, non community) |
| GGUF ufficiale | `openbmb/MiniCPM5-2B-GGUF` |
| Base (ablation) | `openbmb/MiniCPM5-2B-Base` |
| Ablation 1B (+ MLX ufficiale) | `openbmb/MiniCPM5-1B` / `openbmb/MiniCPM5-1B-MLX` |

Profilo runtime/training: `models/configs/minicpm5-2b-mlx-qlora.json`  
Report: `docs/minicpm-migration-report.md`  
Registry: `models/registry/default.json`

Il modello produce **solo candidate facts** (evidence, entità, relazioni, grafi
candidati, alternative, missing facts, domande). Non emette n finale, verdetti di
pseudoreplicazione, test statistico o giudizio sul paper. Thinking mode sempre
disabilitato (`enable_thinking=false`): trace di ragionamento romperebbero il
parsing JSON.

## Legacy (disabilitato come default)

**Granite 4.1 3B Instruct** (`ibm-granite/granite-4.1-3b`, ADR-0010) è retrocesso
a braccio di confronto storico (ADR-0019): profili in `models/configs/legacy/`,
opt-in `allow_legacy=True` oppure `NTRUTH_ALLOW_LEGACY_GRANITE=1`. Il suo
fingerprint PARTIALLY_VERIFIED resta valido solo per quell'artefatto.

Qwen3-4B Instruct 2507 resta in `models/configs/legacy/` solo per riferimento
storico. Non è caricato dai default CLI/test/CI.
