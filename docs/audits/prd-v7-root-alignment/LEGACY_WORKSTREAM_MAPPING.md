# Legacy Workstream Mapping (pre-v7 → PRD v7.0)

**Document ID:** WS-MAP-PRDV7-ROOT-001 · **Date:** 2026-08-03

PRD v7.0 §4.1 redefines the four workstreams. The merged history of this repository
(PR #1, #2, #3 and their plans/reports) used earlier workstream labels with DIFFERENT
meanings. Historical reports keep their original labels; this document is the explicit,
version-qualified mapping.

## 1. Mapping table

| Legacy label (historical reports) | Meaning in historical reports | v7 workstream (PRD §4.1) | Notes |
|-----------------------------------|-------------------------------|--------------------------|-------|
| `LEGACY_WS_B_DATASET_ACQUISITION` | "Workstream B" in PR #2, `docs/audits/dataset-pipeline-20260803/`, `REPORT_B_DATASET_PIPELINE.md`: reproducible public-corpus preparation and audit | `V7_WS_C_REAL_ANCHOR_SILVER_SYNTHETIC` (data side) + part of `V7_WS_A_SCIENTIFIC_FOUNDATION` (fixtures) | Dataset acquisition is a data activity in v7 terms, not the parser train line. |
| `LEGACY_WS_C_TASK_CORPORA` | "Workstream C" in PR #3, `docs/plans/modernbert-task-corpora-v1.md`, `docs/task_corpora/`: deterministic task corpora architecture C0–C1, SourceData entity_roles adapter | `V7_WS_C_REAL_ANCHOR_SILVER_SYNTHETIC` (corpus engineering) feeding `V7_WS_B_MINIMUM_VIABLE_TRAIN_A` (baselines B0/B4) | ModernBERT task corpora are auxiliary/silver material for baselines, never real gold. |
| "Workstream A" (v6-era docs, where present) | deterministic foundation | `V7_WS_A_SCIENTIFIC_FOUNDATION` | Name preserved; scope extended by Bootstrap Core / Causal Design Context. |
| (none — governance was embedded) | — | `V7_WS_D_GOVERNANCE_ADOPTION` | v7 names governance/adoption/sustainability explicitly. |

## 2. v7 workstream definitions (for reference)

- `V7_WS_A_SCIENTIFIC_FOUNDATION` — Bootstrap Core, Full Scientific Record, wizard,
  SampleSheetSpec, graph store, Rulebook, DeterminabilityState, Derivation Gold, reports,
  fixtures (Train D).
- `V7_WS_B_MINIMUM_VIABLE_TRAIN_A` — baseline B0/B4, stage contracts, hard verifier,
  staged parser, trained/distilled components, calibration, abstention, external validation
  (Train A).
- `V7_WS_C_REAL_ANCHOR_SILVER_SYNTHETIC` — real-anchor acquisition, calibration/feasibility
  corpus, prospective gold, audited silver, Synthetic Data Factory, anti-shortcut sets,
  mixture reports.
- `V7_WS_D_GOVERNANCE_ADOPTION` — reviewers, LOI, budget, data custody, STOP authority,
  primary-persona usability, co-maintainers, funding.

## 3. Rules of use

1. Historical reports (`REPORT_B_DATASET_PIPELINE.md`, `workstream-c-c0-c1-readiness.md`,
   `modernbert-task-corpora-v1.md`, PR descriptions) are NOT rewritten. When citing them,
   add: *"workstream names in this document predate the PRD v7.0 taxonomy; see
   LEGACY_WORKSTREAM_MAPPING.md."*
2. New documents and code comments use the version-qualified `V7_WS_*` identifiers.
3. No gate or claim may be transferred between legacy and v7 labels without this mapping
   (e.g. legacy "Workstream C done" does not mean v7 Real Anchor work is done — it covers
   only corpus engineering, with real-anchor acquisition still NOT_STARTED).
