# ADR-0011 — Structured decoding stage-level (Outlines + MLX-LM)

**Stato:** accettato (Cluster 3A tecnico)
**Data:** 2026-08-03
**Contesto:** backend Granite sperimentale + registry runtime PARTIALLY_VERIFIED

## Contesto

Il backend Granite (Cluster 1) e il registry (Cluster 2) espongono free-decode e
fingerprint runtime, ma non garantiscono output JSON schema-valid per gli stage
del parser AI. Serve **sintassi vincolata** senza confonderla con verità
scientifica, training P0/LoRA, o estensione di `PARTIALLY_VERIFIED`.

## Decisione

1. **Adapter** `OutlinesMlxAdapter` in `model_backends/constrained.py` con
   lazy import di Outlines (`from_mlxlm` + `Generator`).
2. **Errori pubblici** in `errors.py` (`ConstrainedStatus`,
   `ConstrainedDecodingError`); `constrained.py` li importa (niente cicli).
3. **Schemi stage EXPERIMENTAL 0.1.0** (non 1.0.0 normativo):
   - `EvidenceExtractionResult`
   - `EntityCountResult`
   - `FactorEndpointResult`
   - `CandidateRelationSet`
4. **Fail-closed**: se Outlines manca o la generazione/schema fallisce → errore
   esplicito; **nessun** fallback silenzioso a free-decode.
5. **Free generation** invariata quando `constrained=False` e `output_schema` è assente.
6. Dipendenza opzionale: `outlines>=1.0` nell’extra `ml` (solo Darwin arm64).
7. **MinimalCandidateGraphResult** rinviato: non autonomo rispetto al grafo
   canonico e amplierebbe il cluster senza bisogno immediato.

## Stati machine-readable

`CONSTRAINED_SUPPORTED | CONSTRAINED_UNAVAILABLE |
CONSTRAINT_INITIALIZATION_FAILED | CONSTRAINT_COMPILATION_FAILED |
GENERATION_OK | GENERATION_INCOMPLETE | SCHEMA_VALIDATION_FAILED |
INVALID_OUTPUT_SCHEMA | BACKEND_LOAD_FAILED | FREE_DECODE`

## Normalizzazione consentita

- `null → []` solo su allowlist esplicita di array stage
- ordinamento chiavi
- whitespace non semantico
- case enum solo via mapping esatto

## Vietato

- stringa → fatto / evidence / relazione
- invenzione di entità o missing facts
- deduzione allocation / application / indipendenza
- uso del rules engine per “riparare” output AI
- predizione di `n`, `verdict`, `RuleResult`, `determinability`

## Non decisioni di questo ADR

- Nessuna promozione Granite a factory default (resta `legacy_qwen`)
- Nessuna modifica a registry / qualification chain / fingerprint
- Nessuna estensione di `PARTIALLY_VERIFIED` al decoding profile
- Nessun B4 benchmark run, nessun P0/LoRA, nessuna annotazione gold

## Alternative considerate

| Opzione | Pro | Contro | Esito |
|---|---|---|---|
| Solo post-hoc JSON validate | Semplice | Non vincola i token | Insufficiente da solo |
| outlines-core logits manuali | Controllo fine | Più fragile | Non default |
| vLLM guided decoding | Maturo | Non path macOS core | Deferito |
| Grammar llama.cpp | Cross-platform | Backend diverso | Futuro multiplatform |

## Conseguenze

- Core N-Truth resta importabile **senza** Outlines.
- `parser_ai` non importa Outlines; solo il backend Granite (lazy).
- `runtime_qualification_status` e `scientific_validation_status` invariati.
- Structured decoding = **sintassi**, non claim scientifico.

## Riferimenti

- Outlines MLX: https://dottxt-ai.github.io/outlines/latest/features/models/mlxlm/
- N-Truth ADR-0005 (structured decoding gate, ambito più ampio)
- Cluster 1 `741ef47`, Cluster 2 `a98c49c` / `fac3249`
