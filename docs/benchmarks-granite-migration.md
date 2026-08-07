# Benchmark harness — migrazione Granite

## Confronti richiesti (stesso snapshot dati)

| Braccio | Note |
|---|---|
| Qwen3-4B legacy | solo se ancora eseguibile con allow_legacy; non default |
| Granite 4.1 3B zero/few-shot | Instruct canonical o MLX 4-bit |
| Granite + LoRA | solo dopo gold + curriculum task tags |
| Cascata encoder + Granite | ADR-0002 B5 preferred baseline |
| Granite GGUF Q4 / Q5 | Windows/Linux/Metal |

## Metriche

evidence-span F1, entity/count accuracy, decisive-edge F1, allocation/application
accuracy, contradiction detection, procedural-order, scenario-set, appropriate
abstention, calibration, human corrections, time-to-confirmed-graph, latency,
peak RAM, swap, artifact size.

## Gate

### Completati (software / architettura)

- [x] Contratti parser compatibili (CandidateGraphSet invariato)
- [x] Backend provider-agnostic
- [x] Qwen non caricato come default (solo opt-in esplicito)
- [x] Test unitari backend/profilo / confini di package

### Aperti (operativi e scientifici)

- [ ] Inferenza end-to-end con pesi locali
- [ ] Chat template / stop su tutti i backend
- [ ] Resource budget **rimisurato** su Granite sul Mac M5 24 GB
- [ ] Conversione e parità GGUF/MLX
- [ ] CI Windows: llama.cpp/GGUF (CPU/GPU)
- [ ] CI Linux: llama.cpp, Transformers, vLLM
- [ ] Fine-tuning reale
- [ ] Confronto B5 (cascata) vs monolitico Granite
- [ ] Metriche scientifiche su real gold / external challenge

## Comando risorse (dopo download pesi)

```bash
uv run python scripts/models/acquire_granite.py --confirm-license-and-download
uv run ntruth-ml benchmark-resources --out benchmarks/runtime --repo .
```
