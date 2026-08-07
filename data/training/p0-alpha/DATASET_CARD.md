# Dataset Card — P0-alpha (synthetic pre-adaptation)

**Class:** synthetic pre-adaptation experiment (NOT scientific fine-tuning claim)

## Contents

- Train: 2000 records
- Validation: 300 records
- Source: graph-first synthetic (`p0-graph-first-1.0.0`)
- Tasks: TASK_EVIDENCE, TASK_ENTITY_COUNT, TASK_FACTOR_ENDPOINT, TASK_EXPLICIT_RELATIONS

## Protection

- B4_CONSTRAINED_DEV (39 cases): training_eligible=false, generator inaccessible
- TEST_REAL_PLACEHOLDER: empty

## Statuses

```yaml
training_program_status: P0_LORA_APPROVED
scientific_validation_status: NOT_STARTED
runtime_qualification_status: PARTIALLY_VERIFIED
```

## Quality gate

passed=True errors=0 task_counts={'TASK_EVIDENCE': 577, 'TASK_EXPLICIT_RELATIONS': 583, 'TASK_ENTITY_COUNT': 587, 'TASK_FACTOR_ENDPOINT': 553}

## Use

Train LoRA `p0-alpha` only. Evaluate on B4 DEV and this validation split.
Do not use for External Challenge or scientific release claims.
