# Storage estimate — Workstream C0–C1

**Root:** `/Volumes/FLASH128/N-Truth-Datasets`  
**Measured:** 2026-08-03 (after SourceData entity_roles build)

## Current footprint

| Path | Size (approx.) |
|------|----------------|
| `task_corpora/` (total) | **298 MiB** |
| `…/entity_roles/sourcedata/v2.0.3/train.jsonl` | 239 MiB |
| `…/validation.jsonl` | 33 MiB |
| `…/test.jsonl` | 26 MiB |
| manifests / stats / logs | &lt; 1 MiB |

Records: 60 266 train + 8 201 validation + 6 696 test = **75 163** JSONL lines.

Average ~4.0 KiB/record (canonical metadata + dual BIO channels).

## Projection (order-of-magnitude, not a commitment)

| Future corpus (not built) | Assumed records | Rough size |
|---------------------------|-----------------|------------|
| Quantities / MeasEval-class | ~10⁴–10⁵ | 50–400 MiB |
| Relations / coref | ~10⁴–10⁵ | 50–400 MiB |
| Routing labels | ~10⁴–10⁵ | 20–200 MiB |
| Method indicators | ~10³–10⁴ | 5–50 MiB |
| **C0–C1 only (now)** | 7.5×10⁴ | **~0.3 GiB** |
| Full multi-task (speculative) | — | **1–3 GiB** JSONL |

Models, checkpoints, and training caches are **out of scope** and must not land under `task_corpora/`.

## Policy

- All generated corpora stay on the external data volume.
- Git holds only code, schemas, label maps, license decisions, and docs.
- Synthetic fraction for C0–C1: **0%** (no synthetic storage).
