# ADR-0010 — Migrazione a IBM Granite 4.1 3B Instruct come modello Train A primario

**Stato:** accepted for development  
**Machine-readable (registry `qualification`, schema 1.3.0) — verify in `models/registry/default.json`:**  
`migration_status=ARCHITECTURE_MIGRATED` ·  
`runtime_qualification_status=PARTIALLY_VERIFIED` (artefatto MLX community 4-bit registrato; non multipiattaforma) ·  
`scientific_validation_status=NOT_STARTED` ·  
`qualified_artifact` popolato per fingerprint MLX 4-bit (`weights_sha256=cff9d052…`, revision `b1b476b5…`) ·  
`transition_log` mirror JSON + **ledger SQLite append-only e tamper-evident**
(`qualification_ledger.sqlite3`: no UPDATE/DELETE, `sequence=max+1`, GENESIS
anti-reseed, hash chain, evidence CA; JSON rigenerabile, ledger autorevole).  
Artifact-bound + fingerprint canonico SHA-256; gate con reason code;
transizioni impossibili bloccate (es. `EXTERNAL_VALIDATED` senza runtime
`VERIFIED`; `VERIFIED` senza `qualified_artifact`).  
**Data decisione architetturale:** 2026-08-02  
**Nota doc refresh:** header allineato al registry (era `UNVERIFIED` / `qualified_artifact=null`).  
**Revisione scientifica:** dopo Parser Gold, benchmark decisivi N-Truth, e confronto B5/cascata

## Contesto

Il percorso MLX usava Qwen3-4B Instruct 2507 4-bit come *bootstrap candidate*
riproducibile. La visione N-Truth richiede un modello AI centrale per **candidate
facts** (evidence, entità, relazioni, grafi), non verdetti scientifici. La scelta
di un checkpoint default deve restare:

- local-first e open-source friendly (Apache-2.0);
- compatibile col budget M5 24 GB **dopo** benchmark sul modello scelto;
- disaccoppiata dal rules engine / hard verifier;
- reversibile e confrontabile con la cascata B5.

## Decisione

1. **Checkpoint Instruct primario (provisorio):** `ibm-granite/granite-4.1-3b`  
   (~3.40B, Apache-2.0). **Configured maximum context: 131 072 token** (da
   `config.json`; non una capacità già validata sull’host locale).  
   Nota: non esiste HF `...-3b-instruct`; l’Instruct è il repo senza suffisso.
2. **Distribuzione MLX bootstrap:** `mlx-community/granite-4.1-3b-4bit` —  
   **conversione community tramite MLX-LM, non artefatto ufficiale IBM.**  
   Checksum/file/dimensione/revisione nel profilo e in
   `docs/granite-migration-report.md`.
3. **GGUF ufficiale:** `ibm-granite/granite-4.1-3b-GGUF` (Q4_K_M / Q5_K_M consigliati).
4. **Base** `ibm-granite/granite-4.1-3b-base` solo come **ablation**, non default.
5. **Interfaccia:** `ModelBackend` + `GraniteBackend`; parser/verifier/UI non
   importano librerie vendor.
6. **Qwen:** profilo in `models/configs/legacy/`; **mai** selezionato
   implicitamente. Opt-in solo con `allow_legacy=True` **o**
   `NTRUTH_ALLOW_LEGACY_QWEN=1`.
7. **LoRA target modules:** verificati sull’architettura / state dictionary di
   Granite (non ereditati implicitamente dalla configurazione Qwen precedente):

   `self_attn.{q,k,v,o}_proj`, `mlp.{gate,up,down}_proj`

## Runtime multipiattaforma (decisione)

| OS | Runtime core | Non core |
|---|---|---|
| Windows | llama.cpp + GGUF (CPU; CUDA; Vulkan opzionale) | vLLM nativo non supportato ufficialmente |
| Linux | llama.cpp; Transformers; vLLM server | — |
| macOS | MLX-LM community quant **o** llama.cpp Metal | — |

## Alternative considerate

| Opzione | Esito |
|---|---|
| Restare su Qwen3-4B bootstrap | Respinta come default |
| Solo GGUF llama.cpp | Path Windows/Linux; non unica su macOS |
| Cascata encoder-first (B5) | Baseline preferita ADR-0002 da confrontare; B6 monolitico non default scientifico |
| Dichiarare Granite scientificamente migliore | **Vietato** prima dei benchmark N-Truth |

## Formulazione normativa (PRD/docs)

> IBM Granite 4.1 3B Instruct è il modello principale **provvisorio** del Train A.
> La sua adozione definitiva rimane subordinata ai benchmark N-Truth sui task
> decisivi, al confronto con la cascata B5 e alla validazione su dati reali
> indipendenti.

## Conseguenze

- Default: `NTRUTH_MODEL_PROVIDER=granite`, `NTRUTH_MODEL_ID=ibm-granite/granite-4.1-3b`.
- Training effettivo **bloccato** finché non esistono gold, split, budget
  **misurato su Granite** e protocollo di valutazione.
- Il modello **non** emette n finale, verdetti di pseudoreplicazione, test
  statistico o score di paper (schema + confini di package + policy).
- I budget runtime misurati su Qwen restano **storici**; ripetere su Granite.
- Chunking gerarchico resta obbligatorio: non caricare 131K per ogni bundle.

## Cosa questa ADR non dichiara completo

- Inferenza E2E con pesi locali su tutti i backend;
- Benchmark M5 24 GB su Granite;
- Fine-tuning reale;
- Confronto B5/B6 e metriche su real gold / external challenge;
- CI runtime Windows/Linux.

## Rollback

1. Checkout pre-migrazione, oppure  
2. Opt-in legacy esplicito (non default CLI):  
   profilo `models/configs/legacy/qwen3-4b-instruct-2507-mlx-qlora.json`  
   + `NTRUTH_ALLOW_LEGACY_QWEN=1` e/o `allow_legacy=True`.  
3. Non riabilitare Qwen come default senza nuovo ADR.

## Riferimenti

- Model card: https://huggingface.co/ibm-granite/granite-4.1-3b  
- GGUF: https://huggingface.co/ibm-granite/granite-4.1-3b-GGUF  
- MLX community: https://huggingface.co/mlx-community/granite-4.1-3b-4bit  
- IBM docs: https://www.ibm.com/granite/docs/models/granite4-1  
- ADR-0002, ADR-0003, ADR-0005, ADR-0006  
- Report: `docs/granite-migration-report.md`
