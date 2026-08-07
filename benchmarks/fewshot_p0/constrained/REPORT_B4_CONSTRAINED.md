# B4 — Matrice free vs constrained (Outlines + MLX)

**Data:** 2026-08-02  
**Artefatto:** Granite 4.1 3B MLX community 4-bit (fingerprint PARTIALLY_VERIFIED)  
**Stati preservati:**

```yaml
migration_status: ARCHITECTURE_MIGRATED
runtime_qualification_status: PARTIALLY_VERIFIED
scientific_validation_status: NOT_STARTED
```

> Granite è eseguibile e parzialmente qualificato per il fingerprint MLX registrato.  
> La capacità di rispettare CandidateGraphSet e svolgere i task P0 non è ancora scientificamente dimostrata.

## Condizioni (39 eval congelati, seed=0, temp=0)

| ID | Prompt | Decoding |
|----|--------|----------|
| A | zero-shot | free |
| B | few-shot k=3 SHORT | free |
| C | zero-shot | **constrained (Outlines)** |
| D | few-shot k=3 SHORT | **constrained (Outlines)** |

`max_tokens` esplicito per stage: `max(256, p95(gold_short)×1.5)` — **non** il default library mlx-lm (256).

## Risultati — schema validity / JSON / truncation

### evidence_extraction (`max_tokens=298`)

| Cond | JSON % | Schema % | Trunc % | Cand-only % |
|------|-------:|---------:|--------:|------------:|
| A free ZS | 100 | **0** | 0 | 100 |
| B free FS | 56.4 | 7.7 | 28.2 | 100 |
| C constr ZS | **100** | **100** | **0** | 100 |
| D constr FS | **100** | **100** | **0** | 100 |

### entity_count (`max_tokens=273`)

| Cond | JSON % | Schema % | Trunc % | Cand-only % |
|------|-------:|---------:|--------:|------------:|
| A | 100 | 0 | 0 | 97.4 |
| B | 89.7 | 0 | 2.6 | 100 |
| C | **100** | **100** | **0** | 100 |
| D | **100** | **100** | **0** | 100 |

### candidate_relations (`max_tokens=256`)

| Cond | JSON % | Schema % | Trunc % | Cand-only % |
|------|-------:|---------:|--------:|------------:|
| A | 100 | 0 | 0 | 100 |
| B | 74.4 | 5.1 | 23.1 | 100 |
| C | **100** | **100** | **0** | 100 |
| D | **100** | **100** | **0** | 100 |

### candidate_graph_minimal (`max_tokens=514`)

| Cond | JSON % | Schema % | Trunc % | Cand-only % |
|------|-------:|---------:|--------:|------------:|
| A | 79.5 | 0 | 23.1 | 100 |
| B | 56.4 | 0 | 41.0 | 100 |
| C | **100** | **100** | **0** | 100 |
| D | 53.8 | 53.8 | **46.2** | 100 |

## Interpretazione

1. **Constrained decoding risolve sintassi e forma** sugli stage P0 piccoli: C e D → **100% schema** su evidence / entity / relations.
2. **Zero-shot free (A)** resta “JSON sì, schema no” — conferma la baseline precedente.
3. **Few-shot free (B)** peggiora JSON/truncation (prompt lungo + budget) senza risolvere lo schema.
4. **Grafo minimale + few-shot constrained (D)** è limitato da **truncation** (budget 514 insufficiente con demos lunghe nel contesto): non è fallimento semantico, è incomplete generation.
5. **Candidate-only** resta ~100% in quasi tutte le celle (1 hit free entity_count).
6. **Semantica P0** (F1 evidence/entity/relation) **non** è dimostrata da questi numeri: schema validity ≠ semantic accuracy.

## Target ingegneristici vs esito

| Target | Evidence / Entity / Relations (C) | Graph minimal (C) | Graph minimal (D) |
|--------|-----------------------------------:|------------------:|------------------:|
| JSON 100% | sì | sì | no (trunc) |
| Schema ≥95% | **100%** | **100%** | 53.8% |
| Candidate-only 100% | sì | sì | sì |
| Truncation &lt;1% | sì | sì | **no** |

→ Sintassi stage-level **stabile** con constrained zero-shot.  
→ Few-shot sul grafo aggregato richiede **più max_tokens** o demos ancora più corti, non LoRA.

## Diagnosi few-shot (perché scende il JSON)

- Input tokens B/D ~ **1.2–1.6k** vs A/C ~ **350–380**
- Demos SHORT ancora serializzano più span/entity del necessario
- Su graph minimal, free e constrained few-shot colpiscono spesso `max_tokens` → JSON non chiuso

**Non** interpretare truncation come errore semantico.

## Artefatti

| Path | Contenuto |
|------|-----------|
| `audit.json` | EOS, default mlx 256, schema compile, demo lengths |
| `matrix-*-latest.json` | righe per condizione |
| `matrix-summary-latest.json` | sintesi multi-stage |
| `packages/ntruth/model_backends/constrained.py` | adapter Outlines |
| `packages/ntruth/model_backends/stage_schemas.py` | schemi stage |
| `docs/adr/0011-constrained-decoding-outlines-mlx.md` | ADR |
| `scripts/models/run_b4_constrained_matrix.py` | runner |

## Decision gate verso LoRA

| Se | Allora |
|----|--------|
| Schema stage C ≥95% e trunc≈0 (già vero) ma F1 semantico basso | **LoRA P0** è giustificato da evidenza |
| Schema instabile | correggere budget/schema/backend prima |
| Solo graph+FS trunca | alzare `max_tokens` o ridurre demos, **non** trainare ancora |

**Prossimo passo utile:** misurare F1 semantico stage-level sulle uscite **C** (constrained zero-shot, già schema-valid), poi decidere LoRA P0.

## Comandi

```bash
uv run python scripts/models/run_b4_constrained_matrix.py --audit-only
uv run python scripts/models/run_b4_constrained_matrix.py --all-stages
uv run pytest tests/unit/test_constrained_decoding.py -q
```
