# Model cards locali

## Primario provvisorio (Train A)

**IBM Granite 4.1 3B Instruct** — `ibm-granite/granite-4.1-3b`

- Licenza: Apache-2.0  
- Model card: https://huggingface.co/ibm-granite/granite-4.1-3b  
- Ruolo: **modello principale provvisorio** del Train A  
- Stato: `scientifically_selected=false`  
- Registry qualification (machine-readable, **artifact-bound**; source: `models/registry/default.json`):  
  - `migration_status: ARCHITECTURE_MIGRATED`  
  - `runtime_qualification_status: PARTIALLY_VERIFIED` (MLX community 4-bit fingerprint only)  
  - `scientific_validation_status: NOT_STARTED`  
  - `qualified_artifact`: populated for `mlx-community/granite-4.1-3b-4bit` (not null)  
  - A BF16/Transformers validation does **not** transfer to GGUF Q4, adapters, or template changes (`STALE` / `INVALIDATED`).  
- Official status: *code migrated; runtime PARTIALLY_VERIFIED for the registered fingerprint only; model not scientifically validated as definitive N-Truth.*  
- Formulazione normativa:

> IBM Granite 4.1 3B Instruct è il modello principale provvisorio del Train A.
> La sua adozione definitiva rimane subordinata ai benchmark N-Truth sui task
> decisivi, al confronto con la cascata B5 e alla validazione su dati reali
> indipendenti.

Distribuzioni:

| Artefatto | ID |
|---|---|
| Canonical safetensors | `ibm-granite/granite-4.1-3b` |
| MLX 4-bit (bootstrap macOS) | `mlx-community/granite-4.1-3b-4bit` (**community conversion**, not official IBM) |
| GGUF ufficiale | `ibm-granite/granite-4.1-3b-GGUF` |
| Base (ablation) | `ibm-granite/granite-4.1-3b-base` |

Profilo runtime/training: `models/configs/granite-4.1-3b-mlx-qlora.json`  
Registry: `models/registry/default.json`

Il modello produce **solo candidate facts** (evidence, entità, relazioni, grafi
candidati, alternative, missing facts, domande). Non emette n finale, verdetti di
pseudoreplicazione, test statistico o giudizio sul paper.

## Legacy (disabilitato)

Qwen3-4B Instruct 2507 resta in `models/configs/legacy/` solo per riferimento
storico. Non è caricato dai default CLI/test/CI.
