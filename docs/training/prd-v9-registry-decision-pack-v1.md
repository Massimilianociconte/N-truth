# PRD v9 registry decision pack v1

**Status:** PENDING_HUMAN_SCIENTIFIC_APPROVAL  
**Does not approve itself.**  
**Does not freeze GOLD.**  
**Does not set `normative_registry_v9_frozen=true`.**  
**Implemented root contract remains PRD v7.**  
**Normative target:** PRD v9 (9 August 2026)

Machine-readable draft: `packages/ntruth/schemas/registry_v9_draft.json`  
Checker: `ntruth.schemas.registry_v9`

This pack exists so a human scientific owner can approve or reject a single
canonical registry. Public and auxiliary adapters must not invent the v9 labels
listed here.

## 1. Single canonical registry

PRD v9 §0.4 requires one registry for all of the following topics, verbatim:

- enum
- field name
- claim type
- error code
- count kind
- status

Rules:

- each token is defined once;
- text, JSON Schema, Pydantic, fixtures and docs must be generated or checked
  against the draft;
- a deprecated alias is readable only through a v7 adapter and must not be
  written into a v9 record;
- this draft is **not** frozen; `status=PENDING_HUMAN_SCIENTIFIC_APPROVAL`.

Authority hierarchy (PRD v9 §0.4), unchanged:

1. Canonical Schema Registry (pending)
2. Derivation Theory
3. Contract Packages and profile
4. Rulebook
5. normative examples
6. informative text and historical snapshots

## 2. Labels

Draft enums (names only; not live root fields):

| Token | Values |
|---|---|
| FactorRole | ASSIGNED_INTERVENTION, OBSERVATIONAL_EXPOSURE, INTRINSIC_ATTRIBUTE, BLOCKING_FACTOR, BATCH_NUISANCE, REPEATED_MEASURE_INDEX, MEASUREMENT_CONDITION, UNKNOWN |
| ContrastType | ASSIGNED_INTERVENTION_EFFECT, OBSERVATIONAL_ASSOCIATION, INTRINSIC_ATTRIBUTE_COMPARISON, WITHIN_UNIT_REPEATED_CONTRAST, NUISANCE_OR_BATCH_COMPARISON, DESCRIPTIVE_ONLY, UNKNOWN |
| KnowledgeState | PRESENT, ABSENT_EXPLICIT, NOT_REPORTED, UNKNOWN, NOT_APPLICABLE, CONFLICTING |
| DeterminabilityState | v7 seven-state contract retained |
| CountKind | implemented v7 count registry; aliases read-only |

Public adapters (SourceData entity roles and any future auxiliary adapter) may
emit only their source BIO / task labels. They **must not** emit `FactorRole`,
`ContrastType`, `ContrastSupportClaim`, `ObservedEvidenceScope`, or
`TargetPopulationClaim` as canonical N-Truth labels.

## 3. Stati ambigui / indeterminati

The following states remain first-class. Silence is not absence. A missing
decisive predicate is `INSUFFICIENT_INFORMATION` or `INDETERMINATE`, never a
guess:

- INSUFFICIENT_INFORMATION
- INDETERMINATE
- UNKNOWN
- NOT_REPORTED
- NOT_APPLICABLE
- CONFLICTING_INFORMATION
- MULTIPLE_PLAUSIBLE_GRAPHS
- OUT_OF_SCOPE

`TargetPopulationClaim` defaults to `NOT_ASSESSED`. An observed mention of a
population is not a target-population claim.

## 4. Rulebook

The Rulebook stays the executable conformance layer under Derivation Theory.
This pack does **not** freeze, rewrite, or locally invent Rulebook clauses.
Until human approval, derived EU / independent-n / adequacy claims remain
blocked for public corpora.

## 5. Annotation guideline

CP-DATA requires an approved annotation guideline before Parser Gold or
Derivation Gold. This pack records that the guideline is
`PENDING_HUMAN_SCIENTIFIC_APPROVAL`. GOLD-pilot machinery can record dual
annotation; it cannot declare GOLD.

## 6. Verifiable migration PRD v7 → v9

| v7 | v9 draft | Mode |
|---|---|---|
| `Determinability.INDETERMINATE` | `INSUFFICIENT_INFORMATION` | explicit alias (already in `determinability_v7`) |
| other v7 determinability states | same v7 token | identity |
| `CountKind` aliases (`n_analysed`, …) | canonical `CountKind` | read-only alias |
| `Factor.kind` (treatment/genotype/…) | `FactorRole` | **no silent mapping** |
| `Contrast` without type | `ContrastType` | **no silent mapping** |
| missing ObservedEvidenceScope / ContrastSupportClaim | unmigrated decisive field | fail-closed, not invented |

`ntruth.schemas.registry_v9.migrate_v7_record` is the checkable function.
A v7 record is accepted as a *migration input* only when ambiguous states stay
expressible and no adapter-invented v9 label is present. It is never rewritten
into a frozen v9 GOLD record by this function.

## 7. Experiment Graph: decisive vs candidate inference

Including the five named v9 terms:

| Field | Authority | Meaning |
|---|---|---|
| FactorRole | **decisive** | required before any EU / count derivation; human-approved |
| ContrastType | **decisive** | required before derivation; compatibility gated by FactorRole |
| ContrastSupportClaim | **decisive** | support of the contrast in the recorded design; a mention ≠ claim |
| ObservedEvidenceScope | **decisive** | descriptive scope of what was actually observed |
| TargetPopulationClaim | **candidate inference** | optional external-population claim; default NOT_ASSESSED; never inferred from observed scope |
| ExperimentalUnitClaim / AssignmentUnit / InferentialQuery / MaterialLineage | **decisive** | assignment-anchored; interference does not rename the EU |
| AdequacyAssessment / SupportProfile / parser `experimental_unit_count` | **candidate inference** | not canonical N-Truth labels from public adapters |

## 8. What this pack does not do

- It does not approve the registry.
- It does not set `normative_registry_v9_frozen=true`.
- It does not write `AuthorityLevel.NTRUTH_GOLD`.
- It does not let public adapters invent the five v9 labels.
- It does not open training, baselines, or model download.
