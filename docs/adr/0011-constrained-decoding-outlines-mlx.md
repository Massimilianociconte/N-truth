# ADR-0011 — Constrained decoding backend (Outlines + MLX-LM)

**Stato:** accettato  
**Data:** 2026-08-02  
**Contesto:** baseline B4 few-shot/zero-shot su Granite MLX 4-bit

## Contesto

La baseline B4 ha mostrato:

- zero-shot: ~100% JSON, ~0% schema `CandidateGraphSet`;
- few-shot: JSON extractable in calo e schema ~5%;
- candidate-only: 100%;
- micro-F1 semantico ≈ 0.

Serve separare **sintassi/schema** da **semantica** prima di qualsiasi LoRA.

## Decisione

1. **Adapter provider-agnostic** `OutlinesMlxAdapter` in `model_backends/constrained.py`.
2. Integrazione **Outlines** (`outlines.from_mlxlm`) sul modello MLX già caricato da `GraniteBackend`.
3. `GenerationRequest` esteso con `constrained`, `output_schema`, `SamplingConfig`.
4. **Nessun fallback silenzioso**: status espliciti
   `CONSTRAINED_SUPPORTED | CONSTRAINED_UNAVAILABLE | CONSTRAINT_COMPILATION_FAILED | GENERATION_INCOMPLETE | FREE_DECODE | GENERATION_OK`.
5. **Schemi a stadi** (non il grafo monolitico all’inizio):
   - `EvidenceExtractionStage`
   - `EntityCountStage`
   - `CandidateRelationStage`
   - `MinimalCandidateGraphStage`
6. Dipendenza opzionale: `outlines` nell’extra `ml` (Apple Silicon).

## Alternative considerate

| Opzione | Pro | Contro | Esito |
|---|---|---|---|
| Solo post-hoc JSON validate | Semplice | Non alza schema-valid rate | Insufficiente |
| outlines-core manual logits | Controllo fine | Più codice fragile | Non come default |
| vLLM guided decoding | Maturo | Non path macOS core N-Truth | Deferito Linux |
| Grammar GGML/llama.cpp | Cross-platform | Backend diverso da MLX bootstrap | Futuro multiplatform |

## Conseguenze

- La sintassi può avvicinarsi al 100% **senza** claim scientifici.
- `parser_ai` **non** importa Outlines; solo il backend Granite.
- `runtime_qualification_status` resta `PARTIALLY_VERIFIED` finché non si completa il protocollo multi-replica VERIFIED.
- `scientific_validation_status` resta `NOT_STARTED`.
- Se schema stage ≥95% ma F1 semantico resta basso → **allora** LoRA P0 è motivato.

## Budget token

`mlx_lm.generate` ha default **256** `max_tokens`. I benchmark devono registrare esplicitamente:

```text
max_tokens ≥ p95(gold_output_tokens) × 1.5
```

e non ereditare il default library/server.

## Riferimenti

- Outlines MLX: https://dottxt-ai.github.io/outlines/latest/features/models/mlxlm/
- mlx-lm SERVER default max_tokens: documentazione mlx-lm
- N-Truth ADR-0005 (structured decoding gate)
- N-Truth ADR-0010 (Granite migration)
