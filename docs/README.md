# N-Truth documentation map — PRD v8.0

The binding specification is **N-Truth PRD v8.0**. Repository status is
`IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`; scientific validation, training and External
Challenge use remain HOLD.

## Start with current truth

| Document | Purpose |
|---|---|
| [status-snapshot.md](status-snapshot.md) | Clean-checkout engineering/scientific status |
| [architettura.md](architettura.md) | Current v8 layers and invariants |
| [architecture/prd-v8-current-to-target.yaml](architecture/prd-v8-current-to-target.yaml) | Machine-readable implementation map |
| [audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md](audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md) | Final requirement-by-requirement implementation status |
| [audits/prd-v8-full-migration/REQUIREMENT_TRACEABILITY_MATRIX.md](audits/prd-v8-full-migration/REQUIREMENT_TRACEABILITY_MATRIX.md) | Immutable Phase 1 clean-checkout baseline |
| [audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md](audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md) | Append-only scientific blockers |
| [audits/prd-v8-full-migration/SOURCE_RECONCILIATION.md](audits/prd-v8-full-migration/SOURCE_RECONCILIATION.md) | PDF/Markdown authority reconciliation |
| [adr/0013-prd-v8-scientific-contract-migration.md](adr/0013-prd-v8-scientific-contract-migration.md) | Migration decision and safety boundary |

## Contracts and operations

| Document | Purpose |
|---|---|
| [public-specification-v0.1.md](public-specification-v0.1.md) | Historical public baseline, explicitly superseded by v8 |
| [prd-v8-data-training-evaluation-boundary.md](prd-v8-data-training-evaluation-boundary.md) | Current candidate-only parser, protected split, HOLD training and evaluation contract |
| [releasing.md](releasing.md) | Software release gates |
| [troubleshooting.md](troubleshooting.md) | Operator troubleshooting |
| [repository-structure.md](repository-structure.md) | Repository layout |

## Governance and data safety

| Document | Purpose |
|---|---|
| [../GOVERNANCE.md](../GOVERNANCE.md) | Current PRD v8 decision authority and separation of duties |
| [privacy-dpia-screening.md](privacy-dpia-screening.md) | Privacy screening draft |

## Historical records

- [audits/prd-v7-root-alignment/](audits/prd-v7-root-alignment/) — immutable PRD v7
  audit artifacts;
- [architecture/prd-v7-migration-map.md](architecture/prd-v7-migration-map.md) —
  historical migration map;
- [prd-v3-reconciliation.md](prd-v3-reconciliation.md) — historical reconciliation.
- [parser-ai-contract.md](parser-ai-contract.md),
  [mlx-training-pipeline.md](mlx-training-pipeline.md),
  [data-and-model-development.md](data-and-model-development.md) and
  [validation-protocol-draft.md](validation-protocol-draft.md) — v2/v3 operational
  drafts retained as `HISTORICAL_NON_NORMATIVE` records.
- [system-card-v0.1.md](system-card-v0.1.md),
  [governance-workflow.md](governance-workflow.md),
  [governance/external-engagement-policy.md](governance/external-engagement-policy.md),
  [data-management-plan-draft.md](data-management-plan-draft.md) and
  [training/DECISION-hold-pending-real-anchor.md](training/DECISION-hold-pending-real-anchor.md)
  — pre-v8 status/governance drafts; current authority is `GOVERNANCE.md`, the status
  snapshot and the v8 data/training/evaluation boundary.

Historical documents are context, not current v8 implementation evidence. Any v7
runtime use must be explicitly marked `DEPRECATED_V7_ADAPTER`.

## Repository root

- [README.md](../README.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [GOVERNANCE.md](../GOVERNANCE.md)
- [SECURITY.md](../SECURITY.md)
- [SUPPORT.md](../SUPPORT.md)
- [CHANGELOG.md](../CHANGELOG.md)
- [CITATION.cff](../CITATION.cff)

## Claim hygiene

Use “implemented”, “engineering-tested”, “fail-closed” and “HOLD with explicit
blockers”. Do not use “scientifically validated”, “production-ready”, “gold”,
“DRIVER-compliant” or “authorized to train” without the exact independently reviewed
evidence required by the Reality Gate.
