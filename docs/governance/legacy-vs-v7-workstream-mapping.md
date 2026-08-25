# Legacy vs PRD v7 workstream namespace

**Purpose:** prevent silent reinterpretation of historical audit labels after PRD v7.0.

**Do not rewrite** historical audit documents or Git history. Future text **must** use
an explicit namespace.

## Mapping

| Namespace label | Meaning | Not the same as |
|-----------------|---------|-----------------|
| `LEGACY_WS_B` | Historical “Workstream B”: dataset acquisition pipeline (raw/processed/training_ready, PR #2 era) | V7_WS_B |
| `LEGACY_WS_C` | Historical “Workstream C”: task-corpora / silver engineering (C0–C1, PR #3) | V7_WS_C |
| `V7_WS_A` | PRD v7 Workstream A: scientific foundation and Train D | LEGACY_WS_* |
| `V7_WS_B` | PRD v7 Workstream B: Minimum Viable Train A and parser AI | LEGACY_WS_B |
| `V7_WS_C` | PRD v7 Workstream C: Real Anchor, silver and synthetic | LEGACY_WS_C |
| `V7_WS_D` | PRD v7 Workstream D: governance and adoption | — |

## Contribution without identity

- `LEGACY_WS_B` infrastructure **feeds** silver and public corpus handling that
  later support `V7_WS_C` silver audit, but is not itself Real Anchor acquisition.
- `LEGACY_WS_C` task-corpora scaffolding **feeds** engineering readiness for
  auxiliary baselines that may appear under `V7_WS_B` / `V7_WS_C`, but does not
  complete Minimum Viable Train A or Real Anchor calibration.

## Forbidden reinterpretation

Do not silently treat:

```text
"Workstream B complete"  →  V7_WS_B complete
"Workstream C complete"  →  V7_WS_C complete
"READY_FOR_B0 CANDIDATE" →  Reality Gate open
```

Tests under `tests/unit/task_corpora/test_workstream_namespace.py` lock the
namespace vocabulary for registry and docs invariants.
