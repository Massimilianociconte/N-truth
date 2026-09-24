# B4 semantic score — condizione C (DEV)

**Scorer:** `1.0.0`  
**benchmark_role:** `B4_CONSTRAINED_DEV`  
**split_role:** `DEVELOPMENT` (n=39)  
**Predizioni:** zero-shot + constrained (Outlines); 13 graph rows recuperate a full text (stessi hparams) perché `raw_preview` era cap a 800 char.

```yaml
migration_status: ARCHITECTURE_MIGRATED
runtime_qualification_status: PARTIALLY_VERIFIED
scientific_validation_status: NOT_STARTED
```

> Non è validazione scientifica né test finale. I 39 casi sono DEVELOPMENT e guideranno LoRA/prompt — **non trainare su di essi**.  
> ALL-CASE e COMPLETE coincidono qui (schema 100%, trunc≈0 su C).

## Primary F1 (bootstrap 95% CI)

| Stage | ALL-CASE mean [low, high] | COMPLETE mean [low, high] | empty% ALL |
|-------|---------------------------:|---------------------------:|-----------:|
| evidence_extraction | 0.128 [0.026, 0.231] (n=39) | 0.128 [0.026, 0.231] (n=39) | 7.7% |
| entity_count | 0.103 [0.026, 0.205] (n=39) | 0.103 [0.026, 0.205] (n=39) | 28.2% |
| candidate_relations | 0.325 [0.179, 0.470] (n=39) | 0.325 [0.188, 0.470] (n=39) | 33.3% |
| candidate_graph_minimal | 0.124 [0.043, 0.218] (n=39) | 0.124 [0.038, 0.218] (n=39) | 5.1% |

## Failure taxonomy (top)

### evidence_extraction
- `MISSED_EVIDENCE`: 34
- `HALLUCINATED_EVIDENCE`: 34
- `CORRECT_SCHEMA_WRONG_CONTENT`: 32
- `WRONG_ENTITY_BOUNDARY`: 25
- `OVER_EXTRACTION`: 1
- `EMPTY_OUTPUT_BIAS`: 1

### entity_count
- `HALLUCINATED_EVIDENCE`: 38
- `MISSED_EVIDENCE`: 29
- `WRONG_ENTITY_TYPE`: 28
- `WRONG_COUNT_VALUE`: 14
- `WRONG_QUANTIFIER`: 14
- `WRONG_COUNT_SCOPE`: 14

### candidate_relations
- `UNSUPPORTED_RELATION`: 46
- `OVER_EXTRACTION`: 21
- `MISSING_REQUIRED_RELATION`: 7
- `EMPTY_OUTPUT_BIAS`: 2
- `UNDER_EXTRACTION`: 2
- `WRONG_RELATION_TYPE`: 1

### candidate_graph_minimal
- `CORRECT_SCHEMA_WRONG_CONTENT`: 36
- `MISSING_REQUIRED_RELATION`: 7
- `EMPTY_OUTPUT_BIAS`: 2
- `UNDER_EXTRACTION`: 2

## A vs C (diagnostico, non superiority claim)

- **evidence_extraction**: comparable_A_json=39, mean_f1_A≈0.07692307692307693, mean_f1_C=0.1282051282051282, empty_A=0.07692307692307693, empty_C=0.07692307692307693
- **entity_count**: comparable_A_json=39, mean_f1_A≈0.2564102564102564, mean_f1_C=0.10256410256410256, empty_A=1.0, empty_C=0.28205128205128205
- **candidate_relations**: comparable_A_json=39, mean_f1_A≈0.07692307692307693, mean_f1_C=0.3247863247863248, empty_A=0.07692307692307693, empty_C=0.3333333333333333
- **candidate_graph_minimal**: comparable_A_json=19, mean_f1_A≈0.3157894736842105, mean_f1_C=0.13157894736842105, empty_A=0.42105263157894735, empty_C=0.0

## Decisione

**`GO_LORA_P0`**

Schema stabile (C), semantica insufficiente, errori concentrati in task supervisionabili (evidence/entity/count/relations). Primo adapter P0 giustificato; i 39 casi restano DEV, non train.

Reasons:
- evidence_extraction: primary_f1_all_case=0.128 < 0.35
- evidence_extraction: top_failures=['MISSED_EVIDENCE', 'HALLUCINATED_EVIDENCE', 'CORRECT_SCHEMA_WRONG_CONTENT']
- entity_count: primary_f1_all_case=0.103 < 0.35
- entity_count: top_failures=['HALLUCINATED_EVIDENCE', 'MISSED_EVIDENCE', 'WRONG_ENTITY_TYPE']
- candidate_relations: primary_f1_all_case=0.325 < 0.35
- candidate_relations: top_failures=['UNSUPPORTED_RELATION', 'OVER_EXTRACTION', 'MISSING_REQUIRED_RELATION']
- candidate_graph_minimal: primary_f1_all_case=0.124 < 0.35
- candidate_graph_minimal: top_failures=['CORRECT_SCHEMA_WRONG_CONTENT', 'MISSING_REQUIRED_RELATION', 'EMPTY_OUTPUT_BIAS']

I 39 casi restano DEVELOPMENT / B4_CONSTRAINED_DEV; non usare per training né come test finale.

Scope primo adapter:
- `TASK_EVIDENCE`
- `TASK_ENTITY_COUNT`
- `TASK_FACTOR_ENDPOINT`
- `TASK_EXPLICIT_RELATIONS`

