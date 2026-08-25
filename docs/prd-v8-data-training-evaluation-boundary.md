# PRD v8 data, training and evaluation boundary

This is the current repository-level contract. It describes engineering controls, not
data readiness, training authorization or scientific validation. Current state is
**HOLD**: no real anchor, Derivation Gold, independent reference result or qualifying
External Challenge authority is present in the clean checkout.

## Parser and supervised target

The canonical parser output is `ParserCandidateOutput`. It contains candidate facts
and structured block-boundary candidates only. It cannot emit experimental-unit
identity, independent `n`, determinability, adequacy, pseudoreplication or a final rule
result.

A supervised target is `GoldParserTarget`, not the historical v2 output shape. It pins
exactly two independent candidate submissions, their comparison, the
adjudication/provenance record and the selected candidate-only target. A single model
output, a synthetic fixture or an AI critique is never gold.

## Split membership and use policy

Dataset membership and allowed use are separate fields. The canonical protected
memberships are `TEST` and `EXTERNAL_CHALLENGE`; both are always:

- `training_eligible = false`;
- `model_selection_eligible = false`;
- unavailable to ordinary training/tokenization/staging consumers;
- bound to source manifests, family/document lineage and content checksums.

`EXTERNAL_CHALLENGE` additionally requires independent custody, contamination,
access-ledger and authority evidence. Its current use decision is unconditional HOLD.
No legacy `EXTERNAL` value is promoted automatically.

## Training boundary

The MLX implementation is optional engineering tooling. `run_training` consumes only a
canonical Reality Gate v8 resolution and reconciles its complete immutable pin tuple
before snapshot, record, profile, model, staging or subprocess access. A self-issued
JSON document, checksum, local flag or historical Task 5 proposal cannot authorize a
run. The current Gate has unresolved reference/data/evaluation dimensions, so no
substantive training command is authorized by this document.

## Evaluation boundary

Evaluation contracts cover ReportBundle snapshots, query/claim/axis denominators,
evidence/proof matching, abstention, false-certainty, blind residual review, reference
stability and cluster-aware precision conformance. These interfaces remain HOLD and
`scientific_use_permitted = false` without independently reviewed reference and
authority artifacts. No threshold, benchmark result, human ceiling or gold score is
included in this repository.

## Historical documents

The v2/v3 parser, MLX and preregistration documents are retained as history and marked
`HISTORICAL_NON_NORMATIVE`. They are not current instructions and must not be used to
construct v8 targets, eligibility decisions or validation claims. Current operational
truth is the [status snapshot](status-snapshot.md), the
[Scientific Review Register](audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md),
[GOVERNANCE.md](../GOVERNANCE.md) and the canonical schemas/code referenced above.
