# Benchmark locali

Gli artefatti in questa cartella misurano esclusivamente il checkout e la macchina indicati
nel JSON. Le fixture sono sintetiche normative: un esito sotto i budget temporali e di memoria
non dimostra accuratezza, generalizzabilita o rispetto del gate su un corpus MVP reale.

Rigenerazione:

```bash
.venv/bin/python scripts/benchmark.py --out benchmarks/rules-only-local.json
```
