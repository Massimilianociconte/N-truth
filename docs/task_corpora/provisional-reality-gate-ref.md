# Dataset Reality Gate projection (root-aligned)

**PRD:** v7.0 §0.7
**Root owner:** `packages/ntruth/reality_gate/` (merged PR #6 @ `f2faace…`)
**Dataset role:** project facts only; never claim full gate satisfaction from engineering alone

## Canonical root contract

Import / reference:

```text
packages/ntruth/reality_gate/     GatePurpose, GateValue, DataReadiness,
                                  ScientificValidation, evaluate_reality_gate
packages/ntruth/task_corpora/readiness.py
                                  DatasetReadinessProjection
                                  project_sourcedata_c0_c1()
```

Do **not** re-implement scientific validation in task_corpora.

## Normative conditions (PRD)

Substantive training and scientific AI claims remain blocked until **all** relevant
conditions hold. Public corpora, structured decoding, engineering smoke or SYN-G1
do **not** satisfy the Reality Gate.

Dataset projection fields for C0–C1 SourceData:

| Field | Value |
|-------|-------|
| `engineering_component_status` | `VERIFIED_FOR_C0_C1` |
| `engineering_readiness` (root enum map) | `PARTIAL_OR_VERIFIED_BY_COMPONENT` |
| `data_readiness` | `BLOCKED` |
| `scientific_validation` | `NOT_STARTED` |
| `reality_gate_status` | `BLOCKED` |
| `real_anchor_available` | `FALSE` |
| `substantive_training_allowed` | `false` |
| `ai_claims_allowed` | `false` |
| `reality_gate_satisfied_by_public_corpora` | `false` |
| `reality_gate_satisfied_by_silver_adapter` | `false` |

`reality_gate_ref` on new manifests:

```text
reality_gate@main:f2faace47178
```

Deprecated alias (historical manifests only):

```text
prd_v7_section_0.7_provisional_dataset_manifest
```

## Serialization impact

`DatasetReadinessProjection` is written into **BuildManifest / leakage_audit /
stats** metadata only. It does **not** change TaskRecord JSONL lines or
`records_sha256` of the SourceData entity_roles corpus.
