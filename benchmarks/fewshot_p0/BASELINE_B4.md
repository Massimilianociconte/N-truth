# B4 baseline — Granite few-shot / zero-shot (P0)

**Stato:** eseguito. Non è validazione scientifica.  
`scientific_validation_status: NOT_STARTED`  
`runtime_qualification_status: PARTIALLY_VERIFIED` (artefatto MLX 4-bit, fingerprint registrato).

## Artefatto valutato

| Campo | Valore |
|---|---|
| Modello | IBM Granite 4.1 3B Instruct (canonico) |
| Runtime | MLX community 4-bit + mlx-lm |
| Host | MacBook Pro M5 Pro, 24 GB (`Mac17,9`) |
| Suite | `fewshot_p0_v1` |
| Eval | 39 casi |
| Demo few-shot | 3 |
| Report | `results/baseline-latest.json` |

## Suite

- **47 casi totali** (8 demo + 39 eval)
- Sintetiche canoniche + parafrasi realistiche
- Tipi: empty/incomplete, evidence/entity, counts, factor/endpoint, relazioni esplicite, candidate graph, contraddizioni
- Gold = `CandidateGraphSet` candidate-only (niente verdetti / n finale)
- **Non** usata per training del rules engine

Rigenerazione:

```bash
uv run python scripts/models/run_granite_fewshot_baseline.py --materialize-only
uv run python scripts/models/run_granite_fewshot_baseline.py --mode both
```

## Metriche di conformità (contratto, non scienza)

| Metric | zero-shot | few-shot (k=3) |
|---|---:|---:|
| JSON estraibile | **100%** | **51.3%** |
| Schema valido (strict) | **0%** | **5.1%** (2/39) |
| Schema dopo normalize sicura | 0% | 5.1% |
| Candidate-only (no campi vietati) | **100%** | **100%** |
| Forbidden key hits | 0 | 0 |
| Exact contract match | 0% | 0% |
| Micro F1 (fatti vs gold minimo) | 0.0 | ~0.019 |

Interpretazione:

1. **Zero-shot** produce quasi sempre JSON, ma **non** il contratto v6 (`CandidateGraphSet`): inventa layout tipo `candidate_graphs` / `facts` custom.
2. **Few-shot** inizia ad allineare lo *scheletro* (2 casi schema-validi: `ev-ent-02`, `rel-01`), ma spesso **tronca** o deforma JSON (rate estraibile ↓).
3. **Candidate-only policy**: nessun caso ha emesso `determinability` / `verdict` / n finale nei campi intercettati — il gate policy regge.
4. La **correttezza semantica** (F1 su evidence/entity/count/factor/edge) è quasi zero: atteso senza constrained decoding e senza adapter P0.

## Failure mode tipici

| Pattern | Dove | Azione corretta |
|---|---|---|
| Schema inventato (`candidate_graphs`, …) | zero-shot | constrained decoding / few-shot migliore / LoRA |
| `missing_facts` come stringa | zero-shot/few-shot | **non** auto-inventare record; decoding o adapter |
| JSON troncato / non parseable | few-shot (output lungo) | più `max_tokens`, demos più corti, decoding vincolato |
| typo letterali (`candidate_ graph_set`) | few-shot | decoding vincolato |
| Extra fields / tipi sbagliati | few-shot | schema grammar |

**Non fare:** riempire automaticamente fatti scientifici o “riparare” `missing_facts` string → lista di record inventati.  
**Ammesso:** `missing_facts: []` solo se il campo è assente/null e significa “array vuoto”, non “nessuna informazione scientifica mancante”.

## Cosa dimostra / non dimostra

**Dimostra**

- Harness B4 ripetibile su fingerprint PARTIALLY_VERIFIED.
- Policy candidate-only rispettata in baseline grezza.
- Gap di conformità contratto quantificato (sintassi ≠ schema ≠ semantica).

**Non dimostra**

- Stabilità su input lunghi / multi-documento.
- Budget multi-replica → `VERIFIED`.
- Superiorità vs B5/B6.
- Generalizzazione su gold reale.

## Percorso successivo (invariato)

```text
B4 (questa baseline) → stabilizzare schema (constrained / better few-shot)
                     → B5 encoder/router + Granite + verifier
                     → B6 LoRA P0 solo se migliora conformità / F1 decisive / review time
```

Primo LoRA, se giustificato dalle metriche di conformità:

```text
TASK_EVIDENCE | TASK_ENTITY_COUNT | TASK_FACTOR_ENDPOINT
TASK_EXPLICIT_RELATIONS | TASK_CANDIDATE_GRAPH
```

## Comandi

```bash
# Unit test fixture + normalize sicura
uv run pytest tests/unit/test_fewshot_p0_conformance.py -q

# Smoke 6 casi
uv run python scripts/models/run_granite_fewshot_baseline.py --mode both --limit 6

# Full baseline
uv run python scripts/models/run_granite_fewshot_baseline.py --mode both
```
