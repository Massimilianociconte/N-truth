# Benchmark runtime (Runtime Resource Budget)

Questa cartella ospita **artefatti di budget misurati** per
`ntruth.runtime_resources.RuntimeResourceBudget` e template di struttura.

## Eseguire un benchmark reale (M5 24 GB)

Sul Mac target, con modello locale e `uv sync --extra ml`:

```bash
# Protocollo completo (3 profili × 3 replicate generate + stage CPU)
uv run ntruth-ml benchmark-resources \
  --out benchmarks/runtime \
  --repo .

# Smoke ridotto (non usare per release)
uv run ntruth-ml benchmark-resources --quick --out /tmp/ntruth-bench-quick
```

Output tipici:

- `m5-pro-24g-<timestamp>-<digest>.budget.json` — `RuntimeResourceBudget` fail-closed
- `m5-pro-24g-<timestamp>-<digest>.protocol.json` — osservazioni grezze, load meta, note

Il fingerprint deve coincidere con `probe_runtime_environment("mlx-lm", <version>)`
(es. `Mac17,9`, `25769803776` byte, `macOS 26.x`, `mlx-lm 0.31.x`).

Stage misurati:

| Stage | Contenuto |
|---|---|
| `mlx_generate` | generate MLX per profilo (prompt size e max tokens distinti) |
| `rules_engine` | pipeline deterministica su fixture scientifica |
| `hard_verifier` | `verify_block` |
| `semantic_verifier` | `verify_semantic` (algorithmic_v1) |

## Non è evidenza di release scientifica

- Un budget misurato prova **solo** envelope di risorse su quella macchina/runtime.
- **Non** valida accuratezza del modello, gold, External Challenge o claim scientifici.
- Il file `template-budget.schema.example.json` resta **sintetico**
  (`TEMPLATE-NOT-MEASURED`) e non va usato operativamente.
- Cambiare modello, quantizzazione, OS major o `mlx-lm` **invalida** il budget:
  ripetere il protocollo.

## Template

Vedi `template-budget.schema.example.json`.
