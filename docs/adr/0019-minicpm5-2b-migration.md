# ADR-0019 — Migrazione a MiniCPM5-2B come modello Train A primario provvisorio

**Stato:** accepted for development
**Data decisione architetturale:** 2026-09-17
**Revisione scientifica:** dopo Parser Gold, benchmark decisivi N-Truth, e confronto MiniCPM/Granite-legacy/B5

## Contesto

Il Train A richiede un modello generativo centrale per **candidate facts**
(evidence, entità, relazioni, grafi), non verdetti scientifici. IBM Granite 4.1
3B Instruct (ADR-0010) resta valido ma presenta tre frizioni strutturali:

1. **Distribuzione MLX solo community** (`mlx-community/...`, non ufficiale IBM):
   hop di fiducia extra su artefatto non vendor, fingerprint non trasferibile.
2. **Dimensione/costo**: ~3.40B parametri, 2.13 GB in 4-bit; QLoRA più costoso
   su M5 24 GB rispetto a un 2B di pari capacità dichiarata.
3. **Benchmark di categoria**: nella tabella comparativa pubblicata dal vendor
   OpenBMB (stesso harness interno), MiniCPM5-2B (media 53.9) supera
   granite-4.2-3B (media 42.7, modello Granite *più recente* del 4.1-3b) e tutti
   i 4B inclusi (max 51.1). Numeri vendor-side, non verifica indipendente, ma
   segnale sufficiente — insieme ai punti 1–2 — per una migrazione
   architetturale provvisoria con benchmark decisivi N-Truth a seguire.

MiniCPM5-2B (OpenBMB, settembre 2026) è denso 2.52B, Apache-2.0,
architettura `LlamaForCausalLM` standard (nessun kernel custom), context
configurato 131 072, distribuzione MLX 4-bit **ufficiale del vendor**,
GGUF/GPTQ ufficiali, cookbook di fine-tuning (TRL+PEFT, LLaMA-Factory,
ms-swift, unsloth) e chat template con flag `enable_thinking` (N-Truth lo
rende sempre `false`: JSON diretto, niente trace di ragionamento nei
candidate facts). Dettagli e pin in `docs/minicpm-migration-report.md`.

## Decisione

1. **Checkpoint primario provvisorio:** `openbmb/MiniCPM5-2B`
   (2 516 756 480 parametri, Apache-2.0), revisione canonica
   `12a3808a956f869c767195e9266b59c4d21d92e2`.
2. **Distribuzione MLX bootstrap:** `openbmb/MiniCPM5-2B-MLX` (ufficiale vendor,
   4-bit), revisione `8a9ad7539ac86281d0ac2b017ba04a5de53fe9a3`,
   `model.safetensors` 1 416 035 216 byte, SHA-256
   `c207798696a4a454e7ac211b25227625466c693335941cee8904fb922f295cc1`.
3. **Braccio ablation:** `openbmb/MiniCPM5-1B` (+ MLX ufficiale
   `9879b18bf2928355fcdf4287635388a3665a40cb`, 608 026 621 byte,
   SHA-256 `a23e0c5c79944a0b2cc92cb9ab79376b4dce41e2312383727e21ee43fe19cb4f`),
   ruolo `reproducible_bootstrap_candidate`, mai default.
4. **Interfaccia:** `ModelBackend` + nuovo `MiniCPMBackend`; parser/verifier/UI
   non importano librerie vendor (invariato).
5. **Granite 4.1 3B:** retrocesso a **legacy opt-in** (profili in
   `models/configs/legacy/`, opt-in `allow_legacy=True` oppure
   `NTRUTH_ALLOW_LEGACY_GRANITE=1`); resta il braccio di confronto storico per
   head-to-head MiniCPM vs Granite. Non riabilitare come default senza nuovo ADR.
6. **LoRA target modules:** identici per nome a quelli Granite
   (`self_attn.{q,k,v,o}_proj`, `mlp.{gate,up,down}_proj`) perché MiniCPM5 è
   architettura Llama standard; rank 16 / scale 32 / dropout 0.05, ultimi
   8 layer, invariati per comparabilità.
7. **Thinking sempre disabilitato:** ogni rendering del chat template passa
   `enable_thinking=False`; un tokenizer che rifiuta il flag fallisce
   fail-closed (mai thinking silenzioso).
8. **Registry:** `default_model_id=openbmb/MiniCPM5-2B`, runtime globale
   `UNVERIFIED` (pesi mai acquisiti), `qualified_artifact=null`, scienza
   `NOT_STARTED`. Il fingerprint Granite PARTIALLY_VERIFIED resta valido solo
   per l'artefatto Granite storico.

## Alternative considerate

| Opzione | Esito |
|---|---|
| Restare su Granite 4.1 3B come default | Respinta: MLX solo community, pesi +50%, segnale benchmark sfavorevole |
| MiniCPM5-1B come primario | Respinta: bound inferiore utile solo come ablation |
| MiniCPM4-0.5B / 4.1-8B | Respinte: generazione precedente (0.5B) o fuori budget M5 (8B) |
| Dichiarare MiniCPM scientificamente migliore | **Vietato** prima dei benchmark N-Truth (stessa regola di ADR-0010) |

## Formulazione normativa (PRD/docs)

> MiniCPM5-2B è il modello principale **provvisorio** del Train A.
> La sua adozione definitiva rimane subordinata ai benchmark N-Truth sui task
> decisivi, al confronto con il braccio legacy Granite e la cascata B5, e alla
> validazione su dati reali indipendenti.

## Conseguenze

- Default: `NTRUTH_MODEL_PROVIDER=minicpm`, `NTRUTH_MODEL_ID=openbmb/MiniCPM5-2B`.
- Acquisizione pesi solo esplicita (`acquire_minicpm.py
  --confirm-license-and-download`, anche `--variant 1b`); nessun download in CI/test.
- Training effettivo **bloccato** (stessi gate: gold, split, budget misurato
  su MiniCPM, protocollo).
- Il modello **non** emette n finale, verdetti di pseudoreplicazione, test
  statistico o score di paper (schema + confini di package + policy invariati).
- Budget runtime storici (Qwen, Granite) restano storici; ripetere su MiniCPM.
- Chunking gerarchico resta obbligatorio: non caricare 131K per ogni bundle.

## Cosa questa ADR non dichiara completo

- Inferenza E2E con pesi locali (pesi mai scaricati in questa fase);
- Comportamento `enable_thinking=false` verificato su tokenizer MLX locale;
- Stop token `<|im_end|>` verificati in generazione;
- Benchmark M5 24 GB su MiniCPM;
- Fine-tuning reale;
- Head-to-head MiniCPM vs Granite-legacy vs B5 su gold reale / external challenge;
- CI runtime Windows/Linux.

## Rollback

1. `NTRUTH_MODEL_PROVIDER=granite` + `NTRUTH_ALLOW_LEGACY_GRANITE=1` con profilo
   `models/configs/legacy/granite-4.1-3b-mlx-qlora.json`, oppure
2. Nuovo ADR che ripristina Granite come default.
3. Non riabilitare Qwen come default senza nuovo ADR (resta doppio-legacy).

## Riferimenti

- Model card: https://huggingface.co/openbmb/MiniCPM5-2B
- MLX ufficiale: https://huggingface.co/openbmb/MiniCPM5-2B-MLX
- Tech report: https://arxiv.org/pdf/2506.07900 · UltraData: https://arxiv.org/pdf/2602.09003
- Repo: https://github.com/openbmb/minicpm
- Report: `docs/minicpm-migration-report.md`
- ADR-0002, ADR-0003, ADR-0005, ADR-0006, ADR-0010, ADR-0015, ADR-0016
