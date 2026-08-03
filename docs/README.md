# N-Truth documentation map

Start here. Prefer machine-readable gates in `models/registry/` over informal prose when statuses conflict.  
Public scientific posture: **candidate software**, not a certified biostatistics product.

## Status first

| Doc | Use |
|-----|-----|
| [status-snapshot.md](status-snapshot.md) | Verified gates (runtime, training HOLD, annotation draft) |
| [training/DECISION-hold-pending-real-anchor.md](training/DECISION-hold-pending-real-anchor.md) | Why substantive LoRA is HOLD |
| [system-card-v0.1.md](system-card-v0.1.md) | Intended use, forbidden uses, residual risks |
| [public-specification-v0.1.md](public-specification-v0.1.md) | Normative software / candidate scientific contract |

## Architecture and science

| Doc | Use |
|-----|-----|
| [architettura.md](architettura.md) | Dual train (D deterministic / A AI contracts) |
| [parser-ai-contract.md](parser-ai-contract.md) | Candidate-only AI boundary |
| [scrivere-regole.md](scrivere-regole.md) | Authoring rules |
| [scientific-references.md](scientific-references.md) | Versioned sources for the rulebook |
| [absolute-claims-register-v6.1.md](absolute-claims-register-v6.1.md) | Banned absolute slogans |

## Models, runtime, decoding

| Doc | Use |
|-----|-----|
| [granite-migration-report.md](granite-migration-report.md) | Granite migration + qualification posture |
| [adr/0010-granite-4.1-3b-migration.md](adr/0010-granite-4.1-3b-migration.md) | ADR migration |
| [adr/0011-constrained-decoding-outlines-mlx.md](adr/0011-constrained-decoding-outlines-mlx.md) | Outlines + MLX (form ≠ science) |
| [adr/0012-p0-lora-approved.md](adr/0012-p0-lora-approved.md) | P0 LoRA **protocol** approval (not science) |
| [mlx-training-pipeline.md](mlx-training-pipeline.md) | Local MLX tooling commands |
| [model-multiplatform-runtime.md](model-multiplatform-runtime.md) | Multiplatform plans (**not all shipped**) |
| [../models/cards/README.md](../models/cards/README.md) | Local model card summary |

## Data, annotation, training

| Doc | Use |
|-----|-----|
| [annotation-reality-check-p0-v0.1.md](annotation-reality-check-p0-v0.1.md) | Reality-check protocol (draft) |
| [annotation-guideline-v0.1.md](annotation-guideline-v0.1.md) | Broader annotation draft |
| [training/human-anchored-calibration-plan.md](training/human-anchored-calibration-plan.md) | Path to real anchor |
| [training/p0-alpha-training-data-specification.md](training/p0-alpha-training-data-specification.md) | Synthetic P0-alpha TDS |
| [data-and-model-development.md](data-and-model-development.md) | Data/model programme |
| [data-card-v0.1.md](data-card-v0.1.md) | Data card draft |
| [../data/annotations/reality-check/README.md](../data/annotations/reality-check/README.md) | Reality-check tree |

## Validation and operations

| Doc | Use |
|-----|-----|
| [validation-protocol-draft.md](validation-protocol-draft.md) | Future validation protocol (draft) |
| [troubleshooting.md](troubleshooting.md) | Operator troubleshooting |
| [repository-structure.md](repository-structure.md) | Repo map |
| [adr/README.md](adr/README.md) | All ADRs |

## Community (repository root)

- [../README.md](../README.md) — product entry  
- [../CONTRIBUTING.md](../CONTRIBUTING.md) — contribution gates  
- [../SECURITY.md](../SECURITY.md) — security disclosure  
- [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)  
- [../SUPPORT.md](../SUPPORT.md)  
- [../CHANGELOG.md](../CHANGELOG.md)  
- [../CITATION.cff](../CITATION.cff)  

## Claim hygiene (short)

Use: *implemented*, *engineering-verified*, *evaluated on a frozen development set*, *not yet evaluated on independent real gold*, *scientific validation has not started*.

Avoid: *scientifically validated AI*, *production-ready*, *the model calculates n*, *the model detects pseudoreplication* as product truth, *verified model* without naming the verification type.
