# Provisional Reality Gate reference (dataset manifests)

**PRD:** v7.0 §0.7
**Owner of full schema:** root-alignment workflow (not this package)
**Dataset role:** record status only; never claim gate satisfaction from engineering alone

## Normative conditions (PRD text)

Substantive training and scientific AI claims remain blocked until **all** relevant
conditions hold (names as in PRD):

```text
schema_stable_on_real_cases
human_second_review_completed
blocking_schema_gaps == 0
real_anchor_available
license_scope_verified
train_dev_test_split_frozen
decisive_fields_reviewed
real_baseline_executed
synthetic_factory_human_calibrated
```

PRD explicit non-satisfaction:

> La presenza di public corpora, structured decoding, engineering smoke o SYN-G1
> NON soddisfa il Reality Gate.

## Dataset manifest fields (provisional)

| Field | C0–C1 SourceData value |
|-------|-------------------------|
| `reality_gate_status` | `BLOCKED` |
| `reality_gate_ref` | `prd_v7_section_0.7_provisional_dataset_manifest` |
| `engineering_readiness` | `VERIFIED_FOR_C0_C1` |
| `data_readiness` | `BLOCKED` |
| `scientific_validation` | `NOT_STARTED` |
| `reality_gate_satisfied_by_public_corpora` | `false` |
| `reality_gate_satisfied_by_silver_adapter` | `false` |

When the root Reality Gate contract lands, migrate these fields to the shared
schema without rewriting historical audit documents.
