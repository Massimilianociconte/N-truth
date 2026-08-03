# N-Truth Public Specification v0.1


> **Specification authority note (2026-08-03):** The current binding product & scientific
> requirements document is **PRD v7.0**. This public specification v0.1 remains a public
> summary and may lag the private PRD. Where this document says “seven” determinability
> states, the clean-checkout implementation exposes the legacy four-state v3 enum plus the
> additive PRD v7 eight-state `DeterminabilityStateV7`. No scientific validation is claimed.

**Status:** normative software baseline, candidate scientific specification<br>
**Version:** 0.1.0<br>
**Date:** 1 August 2026<br>
**Scope:** Train D deterministic v0.1-D and contracts required before Train A

This document is the self-contained, redistributable specification for the public
repository. `MUST`, `MUST NOT`, `SHOULD` and `MAY` are normative. Scientific rules,
thresholds and taxonomies remain candidates until the external reviews listed in
section 10 are complete.

The private PRD v6 used during reconciliation is retained locally and is not
distributed by default. Implementations and contributions MUST rely on this public
specification, the versioned schemas and executable tests, not on access to that file.

## 1. Purpose and boundaries

N-Truth reconstructs a biological experimental design from Methods, captions, sample
sheets, metadata and statistical code. It represents the reconstruction as a typed,
versioned graph and applies deterministic, inspectable rules to derive experimental
units, dependencies, inference scope, conditional values of `n`, missing information
and questions for a human reviewer.

The product has three intended modes:

1. prospective design support before data collection;
2. retrospective review of a study or manuscript;
3. human annotation and adjudication for a future parser corpus.

N-Truth MUST NOT present its output as statistical certification, proof of research
integrity, legal/privacy clearance, DRIVER/NC3Rs conformity, or a substitute for a
biostatistician and domain expert. It MUST NOT accuse authors or papers. It MUST
surface uncertainty and permit correction.

## 2. Scientific contract

### 2.1 Three distinct assessments

Every alert MUST belong to exactly one class:

| Class | Question answered |
|---|---|
| `DESIGN_REPLICATION` | Is the factor replicated across independently allocable units, or confounded with one source, culture, plate, batch or day? |
| `ANALYTICAL_DEPENDENCE` | Are correlated observations represented in the analysis, or treated as independent? |
| `INFERENCE_SCOPE` | Does the claim remain within the population and hierarchy actually replicated? |

A hierarchical model MAY address analytical dependence. It MUST NOT be represented as
creating biological replication that the design does not contain.

### 2.2 Factor-relative experimental units and operational independence

The experimental unit is relative to a factor and contrast. `allocation_level` is
necessary but MUST NOT be treated as sufficient evidence of independence. A paper or
experiment bundle MUST NOT receive one global experimental-unit label when allocation
differs by factor. The system MUST preserve:

- `allocation_level`: the level at which factor levels can be assigned independently;
- `application_level`: the level at which a procedure is physically performed;
- `independently_assigned`: required tri-state `TRUE`, `FALSE` or `UNKNOWN`;
- `independence_mechanism`: required when the tri-state is `TRUE`;
- `independence_evidence_ids`: evidence dedicated to the operational-independence
  premise; allocation evidence MUST NOT be reused implicitly as proof;
- randomization unit, shared environment, confounding, source preparation,
  allocation event and timing when available;
- observational/measurement levels below the allocation level;
- nesting, crossing, pairing, blocking, pooling, repeated measures and batch structure.

Legacy `assignment_level`, when imported, maps to allocation and MUST NOT silently
replace application.

### 2.3 Target and estimand

An `InferenceTarget` formalizes the scientific question, claim and population. An
`Estimand` formalizes the target effect. A minimally usable estimand MUST include:

- endpoint;
- effect measure;
- target population or unit;
- generalization level;
- factor identifiers;
- time point or condition when required by the contrast.

N-Truth MAY list candidate analytical strategies. It MUST NOT automatically choose a
statistical test, formula or power analysis as ground truth.

### 2.4 Counts, lifecycle and determinability

`planned_n`, `allocated_n`, `treated_n`, `observed_n`, `excluded_n`, `analysed_n`,
`declared_n`, `observational_n`, `analytical_n`, `independent_n` and
`biological_source_count` are different quantities. They MUST remain scoped by unit,
group/level, factor/contrast, endpoint, timepoint, lifecycle and condition.
`effective_n` is an optional diagnostic and MUST remain outside the primary count table.
The system MUST NOT fill a missing independent count with a declared or observational
count.

Every count MUST retain one quantifier: `EXACT`, `LOWER_BOUND`, `UPPER_BOUND`,
`APPROXIMATE`, `RANGE`, `UNKNOWN` or `NOT_REPORTED`. Silence MUST NOT become zero and
bounds MUST NOT become exact values. Exclusions MUST retain unit, phase, prespecification,
endpoint, group, decision role, evidence and count impact.

`independent_n` MAY be scalar only in `DETERMINATE`. The seven exhaustive states are:
`DETERMINATE`, `CONDITIONALLY_DETERMINATE`, `MULTIPLE_PLAUSIBLE_GRAPHS`,
`INSUFFICIENT_INFORMATION`, `CONFLICTING_INFORMATION`, `INVALID_GRAPH` and
`OUT_OF_SCOPE`. A conditional state MAY expose numeric values only within explicit
branches. All other non-determinate states MUST suppress a unique experimental unit
and `independent_n`. `AUTHOR_ASSERTION` alone MUST NOT close determinability.

### 2.5 Evidence and provenance

Evidence MUST distinguish at least:

- `STRUCTURAL_FACT`;
- `AUTHOR_ASSERTION`;
- `SAMPLE_METADATA`;
- `STATISTICAL_CODE`;
- `USER_CONFIRMATION`;
- `MODEL_INFERENCE`;
- `DERIVED_FACT`;
- `CONFLICTING_EVIDENCE`.

Phrases such as “independent experiments” are author assertions unless corroborated by
structural, tabular, user-confirmed or adjudicated evidence. Statistical code is
read-only silver evidence of declared clustering; it does not prove allocation or
randomization. Confidence belongs to candidate facts, not to deterministic rule
consequences.

## 3. Product strategy

### Train D - deterministic foundation

Train D MUST provide local ingest, typed graph construction, human correction,
deterministic rules, traceable output and data-governance gates. It MUST remain useful
without a model and MUST be the reference implementation used to verify future parser
outputs.

### Train A - AI parser and corpus

Train A will segment experimental blocks and propose evidence spans, entities,
relations, allocation/application and operational-independence candidates, procedural
events, alternatives and missing facts through stable stage contracts. Parser outputs
are candidates. Final determinability, alerts and deterministic consequences MUST
remain outside the model contract.

No scientific training or model selection MAY begin until Core Profile, Derivation
Gold, baseline, data, schema-stability and scientific-review gates in section 10 are
satisfied. A bounded, synthetic-only
runtime smoke MAY exercise loading, backpropagation and checkpoint code when its
manifest forbids scientific metrics and no result is treated as a baseline.

## 4. Architecture and trust boundaries

```text
Experiment Bundle or prospective wizard
  -> DocumentRouteResult
  -> EvidenceExtractionResult / EntityCountResult / ProceduralEventResult
  -> CandidateGraphSet
  -> hard verifier (always) / semantic verifier (only when triggered)
  -> HumanRevisionPatch
  -> validated or explicitly conditional graph
  -> RuleResult / QuestionRecord
  -> ReportBundle and versioned exports
```

The rules engine reads a validated graph, not raw prose. Imported R, Python and R
Markdown files MUST be treated as text and MUST NEVER be executed. The baseline API
is single-user, unauthenticated and loopback-only; it MUST NOT be bound to `0.0.0.0`,
placed behind a reverse proxy or exposed to a LAN/Internet.

Every stage envelope MUST expose schema version, provenance, typed errors/warnings and
`complete`, `partial` or `failed`. A parser stage MUST NOT emit a rules-engine verdict.
Parser Gold and Derivation Gold MUST remain distinct.

Corrections and exports MUST be append-only revisions. A new correction MUST NOT
rewrite the source or an earlier export. Every output MUST identify applicable schema,
ruleset, ontology, parser contract and software versions.

## 5. Functional requirements

The IDs below are stable public identifiers.

### 5.1 D0 inputs and progressive ingest

| ID | Requirement |
|---|---|
| FR-001 | In v0.1-D, create an Experiment Block through the prospective wizard. |
| FR-002 | In v0.1-D, import TXT/Markdown and simple CSV only. |
| FR-003 | Generate and validate the versioned `SampleSheetSpec`. |
| FR-004 | Gate JATS/XML, DOCX, PDF, XLSX and TSV behind an explicit experimental profile until their release stage. |
| FR-005 | Gate R, Python and R Markdown behind the experimental profile and treat them as read-only text. |
| FR-006 | Associate multiple files with one Experiment Bundle. |

### 5.2 Parser contract

| ID | Requirement |
|---|---|
| FR-010 | Segment multiple experimental blocks. |
| FR-011 | Classify evidence spans. |
| FR-012 | Extract entities, counts and units. |
| FR-013 | Extract relations and intra-document coreference. |
| FR-014 | Propose allocation and application levels separately. |
| FR-015 | Extract endpoints, factors, groups and contrasts. |
| FR-016 | Propose an inference target or explicitly declare it absent. |
| FR-017 | Return alternative graphs when evidence supports more than one interpretation. |
| FR-018 | After hard verification (and human confirmation when required), **derive** determinability via the rules/output-policy stack—not as a free-form model classification. Determinability is outside the candidate-only parser contract (see §3). |
| FR-019 | Generate the smallest decisive questions. |

Train D MAY implement conservative deterministic subsets of FR-010 through FR-019.
This does not satisfy the evaluated AI-parser requirement.

### 5.3 Graph and rules

| ID | Requirement |
|---|---|
| FR-020 | Validate schemas, references and graph invariants. |
| FR-021 | Derive an experimental unit per factor/scope. |
| FR-022 | Derive conditional `n` per group and contrast. |
| FR-023 | Keep the three alert classes distinct. |
| FR-024 | Detect perfect confounding and pooling. |
| FR-025 | Represent paired, blocked and repeated-measures designs. |
| FR-026 | Produce an inspectable rule trace. |

### 5.4 Human interaction

| ID | Requirement |
|---|---|
| FR-030 | Present an editable graph. |
| FR-031 | Synchronize claims with source evidence. |
| FR-032 | Allow confirmation, rejection and alternatives. |
| FR-033 | Preserve an append-only audit trail and revision history. |
| FR-034 | Prioritize questions by their impact on determinability. |

### 5.5 Positive output

| ID | Requirement |
|---|---|
| FR-040 | Generate a candidate Methods design statement. |
| FR-041 | Generate an `n` table by endpoint and contrast. |
| FR-042 | Export structured JSON and YAML. |
| FR-043 | Export JSON-LD; RO-Crate MAY extend the baseline mapping. |
| FR-044 | Provide an informative DRIVER-aligned checklist without certification. |
| FR-045 | Distinguish facts, inferences, hypotheses and limitations. |

### 5.6 Data and learning

| ID | Requirement |
|---|---|
| FR-050 | Export stand-off candidate annotations. |
| FR-051 | Prevent training on unauthorized/unreviewed assets. |
| FR-052 | Version content-addressed corpus snapshots and splits. |
| FR-053 | Support active learning only after frozen evaluation sets exist. |
| FR-054 | Record model, dataset, configuration and code lineage. |

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | Local-first processing is the default. |
| NFR-02 | No source data in application logs without explicit opt-in. |
| NFR-03 | Every output is traceable to evidence and versions. |
| NFR-04 | The rules engine is deterministic and reproducible. |
| NFR-05 | Learned confidence, calibration and abstention are evaluated before claims. |
| NFR-06 | The locked project supports Apple Silicon and Linux x86-64. |
| NFR-07 | UI and reports are keyboard-friendly and readable. |
| NFR-08 | Typical deterministic analyses remain interactive locally. |
| NFR-09 | Corrupt/unsupported inputs fail explicitly. |
| NFR-10 | Archive, macro, traversal and decompression risks are bounded; imported code is never executed. |
| NFR-11 | UI/output support Italian and English; initial scientific parsing targets English. |
| NFR-12 | Seeds, versions, checksums and environment are recorded where applicable. |
| NFR-13 | No silent cloud fallback or undeclared transfer. |

## 7. Report contract

A complete report SHOULD present, in order:

1. design summary;
2. graph and evidence;
3. factors, allocation and application levels;
4. the derived determinability state, alternatives and prohibited outputs;
5. endpoints, contrasts, inference targets and estimands;
6. lifecycle and semantic counts with scope and quantifier;
7. green path: what is supported and why;
8. alerts grouped by the three classes;
9. decisive open questions and conditional scenarios;
10. candidate analytical considerations;
11. generalization limits;
12. proof trace and component versions.

Severity MUST depend on the type and impact of the problem, evidence certainty,
contrast, correctability, available dependence evidence and confounding. It MUST NOT
be a direct opaque model score.

## 8. Data rights and privacy

Every real asset MUST have a per-version manifest containing its source, immutable
identifier, retrieval time, SHA-256, license evidence, attribution, permitted uses,
privacy status and leakage group. Permissions are granular: `analyze`, `annotate`,
`train`, `share` and `redistribute` are not interchangeable.

Local analysis MUST NOT imply permission to train or distribute. Missing, expired,
revoked or mismatched records MUST fail closed. Redaction produces a separate derived
asset; it MUST NOT mutate the source. Distribution readiness evaluates the current
scope and MUST NOT itself upload, copy or share data.

Training, evaluation and release eligibility are separate booleans. `TEST` and
`EXTERNAL_CHALLENGE` MUST NEVER be training eligible. Splits are assigned by whole
experiment bundle, not by sentence. An indivisible group includes article,
preprint/versions/corrections, supplements, sample sheets, code, repository accessions
and mirrors. Synthetic transformations of one graph remain in a single train-only
group.

## 9. Evaluation

Deterministic rules require 100% pass on approved canonical fixtures; a regression is
a release blocker. Generated scenario coverage does not replace expert-reviewed
fixtures.

Future parser evaluation MUST report evidence-span/entity/relation metrics, graph
metrics, allocation/application performance, determinability, question usefulness,
risk-coverage and abstention. End-to-end evaluation MUST include correction time,
post-review graph correctness, conditional `n`, critical-alert performance, false
alerts and Methods completeness. Results MUST be reported against human agreement and
with uncertainty intervals.

Validation and test sets MUST be frozen before optimization. External validation MUST
include at least a cell-culture laboratory, an imaging core, an uninvolved group and a
public adjacent-domain challenge.

## 10. Release and training gates

The deterministic software can be published as an alpha when its code, tests, package
and documentation gates pass. It MUST still carry the scientific disclaimer.

Training remains blocked until all of the following are documented:

- 10-20 real designs represented in the D0 micro-domain without substantive schema changes;
- principal rules reviewed by a biostatistician and wet-lab expert;
- 30-60 complete canonical fixtures with graph, expected output, exception,
  counterexample, reference and review;
- at least 20 confirmed real/canonical cases in Derivation Gold;
- 30-50 calibration cases with independent annotation on decisive fields and
  pre-adjudication agreement;
- a 100-150-case feasibility protocol with all decisive fields double annotated;
- frozen pilot protocol and redirect criteria;
- asset-level licenses/authorizations and privacy review;
- bundle/laboratory-aware train, validation, test and external splits;
- a constrained baseline that emits schema-valid candidates.

Claims of scientific validation remain blocked until the independent pilot, human
ceiling, external challenge and user study are complete.

The PRD v6 body, roadmap and Definition of Done specify 100-150 feasibility cases;
Appendix D still says 150-250. The public baseline uses 100-150 and records the latter
as an open editorial erratum rather than silently combining the two targets.

## 11. Versioning and change control

Software, schema, ruleset, ontology, parser contract, guideline and corpus snapshots
are versioned separately. An incompatible schema or parser change requires an
explicit migration/adapter and updated examples/tests. A rule change requires four
executable fixture outcomes plus a complete canonical case and named external review
before its status can become approved.

The original documentation, rulesets, ontology and synthetic fixtures in this
repository are covered by the repository Apache-2.0 license unless a file states
otherwise. That license never extends automatically to imported documents, public
datasets, laboratory data, annotations derived from restricted sources or model
weights.
