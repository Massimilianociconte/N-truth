# Runtime multipiattaforma Train A (Granite)

**Stato migrazione:** architettura e default Granite completati; validazione
runtime multipiattaforma **in corso** (non dichiarare E2E OS come chiuso).

| Piattaforma | Backend preferito | Note |
|---|---|---|
| macOS Apple Silicon | MLX-LM 4-bit **community** | Conversione `mlx-community`, non artefatto ufficiale IBM; alternativa llama.cpp Metal + GGUF ufficiale |
| Windows | llama.cpp + GGUF | CPU; CUDA se disponibile; Vulkan opzionale. **vLLM non è runtime core Windows** (nessun supporto ufficiale nativo) |
| Linux | llama.cpp e/o Transformers | vLLM per installazioni **server** Linux; CUDA/ROCm/CPU secondo hardware |

## CI target (separati)

```text
• CI Windows: llama.cpp/GGUF, CPU e GPU dove disponibile
• CI Linux: llama.cpp, Transformers e vLLM
```

Configurazione centrale (non duplicare model ID):

```bash
export NTRUTH_MODEL_PROVIDER=granite
export NTRUTH_MODEL_ID=ibm-granite/granite-4.1-3b
export NTRUTH_MODEL_PROFILE=BALANCED
export NTRUTH_MODEL_QUANTIZATION=auto
export NTRUTH_STRUCTURED_OUTPUT=true
export NTRUTH_ML_PROFILE=models/configs/granite-4.1-3b-mlx-qlora.json
# Legacy Qwen solo opt-in esplicito:
# export NTRUTH_ALLOW_LEGACY_QWEN=1
```

## Context window

**Configured maximum context: 131 072 token** (config del checkpoint).  
La finestra pratica dipende da backend, quantizzazione, KV cache, RAM, batch e
latency. N-Truth usa **chunking gerarchico**; non caricare 131K per ogni bundle.

## Resource manager

Registra backend, modello, quantizzazione, token, load/warmup, latency, peak RAM,
swap, cache e unload. I budget devono essere **misurati su Granite** (i budget M5
attuali su Qwen restano storici).

## Structured output

Post-generazione lo stack distingue sintassi JSON, schema, integrità referenziale,
tipi, invarianti grafo, coerenza temporale/numerica, evidence support, conflitti e
conferma umana. **JSON valido ≠ ricostruzione corretta.**
