# N-Truth documentation map

Start here. The normative target is **PRD v9**; the implemented root contract remains
**PRD v7**, and v9 conformance is blocked pending the canonical registry. For training
status, prefer the fail-closed `ntruth-ml readiness` projection and its referenced
evidence over informal prose. Model profiles are configuration, not authorization;
this checkout has no authoritative `models/registry/`.
Public scientific posture: **candidate software**, not a certified biostatistics product.

## Status first

| Doc | Use |
|-----|-----|
| [training/TRAINING-READINESS-small-model-20260813.md](training/TRAINING-READINESS-small-model-20260813.md) | Current PRD v9-target readiness decision (`NOT_READY`) |
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

## Models, runtime, decoding

| Doc | Use |
|-----|-----|
| [granite-migration-report.md](granite-migration-report.md) | Granite migration + qualification posture |
| [adr/0010-granite-4.1-3b-migration.md](adr/0010-granite-4.1-3b-migration.md) | ADR migration |
| [mlx-training-pipeline.md](mlx-training-pipeline.md) | Local MLX tooling commands |
| [../models/cards/README.md](../models/cards/README.md) | Local model card summary |

## Data, annotation, training

| Doc | Use |
|-----|-----|
| [annotation-guideline-v0.1.md](annotation-guideline-v0.1.md) | Broader annotation draft |
| [training/baseline-evaluation-protocol-v1.md](training/baseline-evaluation-protocol-v1.md) | Baseline and protected evaluation protocol |
| [training/source-portfolio-small-model-v1.md](training/source-portfolio-small-model-v1.md) | Source inclusion/exclusion decisions |
| [data-and-model-development.md](data-and-model-development.md) | Data/model programme |
| [data-card-v0.1.md](data-card-v0.1.md) | Data card draft |

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
