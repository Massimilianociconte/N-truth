# Real-anchor protocol v0.1

**Status:** DRAFT — not operational gold  
**Purpose:** Define the 30–50 case human calibration anchor required before substantive N-Truth training or scientific validation claims.

## 1. Role of the real anchor

The real anchor is the first **NTruth_GOLD** slice used for:

- schema and UI calibration;
- inter-annotator / second-review measurement on decisive fields;
- gating synthetic and weak-supervision generators away from final test;
- later hybrid evaluation of parser + rules (not for large-scale training alone).

It is **not** interchangeable with:

- SourceData / PreClinIE / MeasEval / CRAFT public annotations (SILVER_AUXILIARY);
- synthetic P0-alpha fixtures;
- B4 developmental sets without human gold.

## 2. Volume and review

| Parameter | Value |
|-----------|--------|
| Target size | 30–50 cases |
| Primary review | Expert 1 full annotation |
| Second review | Expert 2 on **all decisive fields** (minimum); preferably full dual annotation on ≥50% |
| Adjudication | Third expert or documented consensus procedure |
| Agreement metrics | Field-level exact match + span overlap (IoU); report separately per field |

## 3. Decisive fields (must be double-reviewed)

1. factor  
2. contrast  
3. endpoint  
4. hierarchy (nesting of experimental units / observational units)  
5. allocation_level  
6. application_level  
7. independently_assigned  
8. independence_mechanism  
9. experimental_unit  
10. biological_source_count  
11. independent_unit_count  
12. determinability_state  
13. evidence_spans (character offsets into source text/facsimile)  
14. alternative_graph (if non-unique reconstruction)  
15. minimal_clarification_question (when underdetermined)

Optional supporting fields (single review acceptable initially): free-text notes, figure panel IDs, assay names without EU implication.

## 4. Case inclusion criteria

- Real scientific materials (papers, protocols, lab notes) under a **cleared licence** or internal research use agreement.  
- Prefer diversity of: culture systems, animals, pooling, repeated measures, well-level application vs animal allocation.  
- Exclude: cases that only restate public-task labels without hierarchy content.

## 5. Evidence and graphs

Each case must store:

- source document ID + version hash;
- evidence spans with `start`/`end` and medium (`text` | `table` | `figure_caption`);
- primary reconstructed experimental graph (candidate structure, not a verdict alone);
- optional alternative graph when determinability is partial;
- determinability rationale tied to FR-018 boundary (no inventing missing n).

## 6. Anti-leakage

- Anchor cases receive a **family_id** (paper/PMCID/lab series).  
- No family may appear in both anchor-development and external-challenge partitions.  
- Synthetic generators and training loaders **must not** read external-challenge paths.  
- Public auxiliary corpora (Workstream B) must use separate leakage groups and must not reuse anchor family IDs.

## 7. Lazic / external datasets

Default classification:

```
authority_level: EXTERNAL_CHALLENGE_CANDIDATE
training_eligible: false
```

Rules:

1. Prefer schema alignment on a **documented development subset** only after written permission.  
2. Hold out the majority for validation / external challenge.  
3. Do not auto-ingest into training or synthetic seed pools.  
4. Partition and use policy must be a separate signed decision record.

## 8. Licensing and ethics

- Each case records `licence_status` and data-use agreement ID.  
- No case enters NTruth_GOLD without licence clearance.  
- Human subjects / clinical content follows institutional rules (out of scope for this draft).

## 9. Outputs of a completed anchor campaign

- `real_anchor/v0.1/cases/*.json` (external root only)  
- dual-review matrix  
- adjudication log  
- determinability distribution  
- frozen split manifest  
- decision: `REAL_ANCHOR_V0_1: ACCEPTED | REVISE`

## 10. Relationship to ModernBERT baselines

ModernBERT auxiliary task corpora may train in parallel **without** the real anchor, but:

- they cannot claim scientific validation of independent *n*;  
- promotion of any model to default scientific interpreter remains HOLD until real anchor + hybrid benchmarks exist.

## 11. Open decisions

- Annotator pool and training materials  
- Exact dual-review sampling rate if not 100%  
- Tooling: desktop UI vs spreadsheet bootstrap  
- Timeline and ownership  
