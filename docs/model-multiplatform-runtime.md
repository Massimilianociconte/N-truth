# Runtime multipiattaforma Train A (MiniCPM)

**Stato migrazione:** architettura e default MiniCPM5-2B completati (ADR-0019);
acquisizione pesi e validazione runtime multipiattaforma **da svolgere**
(non dichiarare E2E OS come chiuso).

| Piattaforma | Backend preferito | Note |
|---|---|---|
| macOS Apple Silicon | MLX-LM 4-bit **ufficiale vendor** | Distribuzione `openbmb/MiniCPM5-2B-MLX`; alternativa llama.cpp Metal + GGUF ufficiale |
| Windows | llama.cpp + GGUF | CPU; CUDA se disponibile; Vulkan opzionale. **vLLM non è runtime core Windows** (nessun supporto ufficiale nativo) |
| Linux | llama.cpp e/o Transformers | vLLM per installazioni **server** Linux; CUDA/ROCm/CPU secondo hardware |

## CI target (separati)

```text
• CI Windows: llama.cpp/GGUF, CPU e GPU dove disponibile
• CI Linux: llama.cpp, Transformers e vLLM
```

Configurazione centrale (non duplicare model ID):

```bash
export NTRUTH_MODEL_PROVIDER=minicpm
export NTRUTH_MODEL_ID=openbmb/MiniCPM5-2B
export NTRUTH_MODEL_PROFILE=BALANCED
export NTRUTH_MODEL_QUANTIZATION=auto
export NTRUTH_STRUCTURED_OUTPUT=true
export NTRUTH_ML_PROFILE=models/configs/minicpm5-2b-mlx-qlora.json
# Legacy Granite solo opt-in esplicito:
# export NTRUTH_ALLOW_LEGACY_GRANITE=1
# Legacy Qwen solo opt-in esplicito:
# export NTRUTH_ALLOW_LEGACY_QWEN=1
```

## Context window

**Configured maximum context: 131 072 token** (config del checkpoint).  
La finestra pratica dipende da backend, quantizzazione, KV cache, RAM, batch e
latency. N-Truth usa **chunking gerarchico**; non caricare 131K per ogni bundle.

## Resource manager

Registra backend, modello, quantizzazione, token, load/warmup, latency, peak RAM,
swap, cache e unload. I budget devono essere **misurati su MiniCPM** (i budget M5
attuali su Qwen/Granite restano storici).

## Structured output

Post-generazione lo stack distingue sintassi JSON, schema, integrità referenziale,
tipi, invarianti grafo, coerenza temporale/numerica, evidence support, conflitti e
conferma umana. **JSON valido ≠ ricostruzione corretta.**
