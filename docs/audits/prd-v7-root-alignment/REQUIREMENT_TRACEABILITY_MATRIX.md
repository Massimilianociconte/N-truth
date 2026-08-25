# PRD v7.0 Requirement Traceability Matrix — Clean Checkout

**Matrix ID:** RTM-PRDV7-ROOT-001 · **Date:** 2026-08-03
**Base:** `origin/main` @ `0dcef3e54ca908d491726c4b7dfe810aa754549a` (clean worktree,
branch `feat/prd-v7-root-alignment`). Every status below was confirmed from code and tests
in this checkout, not from README/PRD prose.

Status legend: `IMPLEMENTED` · `PARTIALLY_IMPLEMENTED` · `DOCUMENTED_ONLY` · `PLACEHOLDER` ·
`MISSING` · `SUPERSEDED` · `UNKNOWN`.

| # | v7 contract / requirement | PRD ref | Current files/classes/tests (clean checkout) | Status | Required migration | Sci-review dep | Gate impact |
|---|---------------------------|---------|----------------------------------------------|--------|--------------------|----------------|-------------|
| 1 | Reality Gate (3 dimensions, fail-closed, tri-state predicates) | §0.7, §25.6, NFR-28, Fig. 2 | none (v6.1 gates lived in uncommitted `models/registry/*.json`) | MISSING | new `ntruth/reality_gate/` module + machine-readable result + blocker report + tests | none for mechanics; predicate evidence needs reviewers | blocks substantive training & AI claims |
| 2 | Bootstrap Core record (required-or-unknown) | §8.2A, App. X.1, App. N | `packages/ntruth/schemas/experiment.py` (ExperimentBlock, Factor, Contrast, Endpoint), `design/schema.py` DesignSpecification 0.2 | PARTIALLY_IMPLEMENTED | new `ntruth/schemas/bootstrap_core.py` v7 record; keep v3 IR as ingestion input | BLK-SCIENTIFIC-004 (App. N reconciliation) | v0.1-D |
| 3 | Full Scientific Record | §8.2B, App. X.2 | lifecycle counts (NKind/NScope), Contradiction, UnitAssessment; no authority-event log, no planned/executed diff object | PARTIALLY_IMPLEMENTED | extend with authority events, conflict records, alternatives, analytical provenance fields | none | post-Core |
| 4 | Causal Design Context (descriptive only) | §2.4, §8.2C, App. Y | Estimand, InferenceTarget in `schemas/experiment.py`; no AssignmentMechanism / InterferenceAssessment / ComparabilityBasis | PARTIALLY_IMPLEMENTED | new `ntruth/schemas/causal_context.py`; never emit `exchangeable=true` | biostatistician (spec doc) | before inference-scope outputs |
| 5 | Four independence dimensions (no proxying) | §2.3, §7.12 | DataSufficiency.source_independence; abstention codes; no typed four-dimension object | PARTIALLY_IMPLEMENTED | `IndependenceProfile` with assignment / biological-source / exposure / analytical dimensions, tri-state | none (normative in PRD) | v0.1-D |
| 6 | Authority types (7-value enum) | §0.4 | `ProvenanceKind` (model/user/adjudication/rule/derived/explicit/tabular); task_corpora `AuthorityLevel` | PARTIALLY_IMPLEMENTED | new `AuthorityType` enum + scope/rationale fields | none | before double annotation |
| 7 | ConfirmationEvent (append-only) | §8.4, §8.6, NFR-25 | absent | MISSING | new `ntruth/governance/authority.py` append-only event log | none | before double annotation |
| 8 | ConflictRecord (survives resolution) | §0.3, §8.6, §15.15 | `Contradiction` (status unresolved/resolved_by_user/resolved_by_adjudication) | PARTIALLY_IMPLEMENTED | v7 ConflictRecord with sources, field, authority, rationale, resolution_event; keep Contradiction as legacy alias | none | release blocker if hidden |
| 9 | Evidence support levels (9) | §9.5 | `EvidenceType` 8 kinds (v3 §9.1) | PARTIALLY_IMPLEMENTED | add support-level enum mapping DIRECT/STRUCTURED_DIRECT/AUTHOR_ASSERTED/INFERRED_CANDIDATE/CONFIRMED/ADJUDICATED/CONFLICTING/NOT_REPORTED/UNKNOWN over existing spans | none | v0.2-A |
| 10 | DeterminabilityState (8 states) | §10.2, App. M | `Determinability` 4 states (core.py); README/public-spec claim 7 states | PARTIALLY_IMPLEMENTED | new v7 enum + derivation + permitted-output table; keep legacy enum with migration alias INDETERMINATE→INSUFFICIENT_INFORMATION | biostatistician sign-off on state table | release blocker (n outside states) |
| 11 | ConditionRecord (bilingual, evidence_required, effects) | §10.8 | `ConditionalScenario` (conditional_on, if_confirmed/if_rejected, question, rule_id) | PARTIALLY_IMPLEMENTED | extend to ConditionRecord with it/en human_readable, evidence_required, if_true/if_false effects, primary_question_id | none | v0.1-D |
| 12 | InferentialQuery (versioned, mandatory for conclusions) | §7.8, §8.4 | Estimand + InferenceTarget separate objects | PARTIALLY_IMPLEMENTED | unified `InferentialQuery` object referencing factor/levels/endpoint/estimand/population/level | none | every output |
| 13 | Value-of-Abstention contract (11 elements) | §6.4, §23.2, FR-060…065 | `calibration/abstention.py` AbstentionDecision (7 codes) | PARTIALLY_IMPLEMENTED | `AbstentionReport` implementing the full contract; empty "cannot determine" is invalid | none | product contract |
| 14 | Quick Design Session (simple_cell_culture) | §1.1, §6.1, §5.1 | `design/elicit.py`, `design/compiler.py`, SampleSheetSpec docs; no session service/CLI | MISSING | new `ntruth/quick_design/` domain service + CLI + fixtures + export | none | v0.1-D wedge |
| 15 | MVT-A contracts (stage schema, hard verifier, human patch, burden, benchmark manifest) | §12.3, §13.2, §28.3 | `parser_ai/contract.py` v2.0.0 candidate-only output; no HumanRevisionPatch, burden or benchmark manifest | PARTIALLY_IMPLEMENTED | new `ntruth/mvt_a/` contracts only; no model download/training | none for contracts | Phase 2 gate |
| 16 | Cross-domain role policy (profile-relative) | §14.4, §16.7, NFR-27 | task_corpora authority/license enums; no profile-relative role object | PARTIALLY_IMPLEMENTED | new `ntruth/governance/cross_domain.py` role decision model; Lazic role never assumed | scientific reviewer + data owner | before external labels |
| 17 | Real-anchor acquisition programme | §14.2, App. Z | docs/plans + audit reports only | DOCUMENTED_ONLY | documentation + registry contract; no acquisition code in this PR | data steward | calibration pilot |
| 18 | Complexity tiers (SIMPLE/MODERATE/COMPLEX/OUT_OF_PROFILE) | §17.2 | absent | MISSING | `ntruth/burden/tiers.py` classification + recording | none | feasibility |
| 19 | Schema Burden Gate | §17.4 | absent | MISSING | burden recording structures + report contract (no hard-coded thresholds) | none | pilot |
| 20 | Decisive field/edge definition | §7.13, §24.3 | `Question.decisive` flag only | PARTIALLY_IMPLEMENTED | `is_decisive()` predicate over fields/edges + registry | none | metrics & review |
| 21 | Five executive AI metrics | §24.1 | absent (training/metrics.py is v3 task metrics) | MISSING | metric definitions + recording contract (no threshold constants) | none | MVT-A benchmark |
| 22 | Count semantics & scope-aware counts | §7.9, §15.10 | NScope/NKind/NStatement with group/contrast/endpoint scope; lifecycle counts | IMPLEMENTED (v3 contract) | add v7 kinds (`experimental_unit_count_candidate`, `biological_source_count`, `effective_n` diagnostic separation) + alias migration (`analysed`→`analyzed`) | none | invariants |
| 23 | Canonical relation registry | §8.5 | `RelationType` 44 relations, ontology/ntruth-core-0.1.0.json | PARTIALLY_IMPLEMENTED | add `acquired_from`, `observed_in`, `aggregated_to`, `exposed_with`, `may_interfere_with`, evidence relations; version registry 0.2.0 with alias table | none | schema tests |
| 24 | Candidate-only parser output / no direct n/verdict | §12.7, §12.10, §13.3 | ParserAIOutput `extra=forbid`, DeterminabilityAssessment evidence rule; parser_ai has no verdict fields | IMPLEMENTED | keep; add explicit v7 forbidden-target tests | none | release blocker |
| 25 | Import boundary graph_core/rules ⊬ parser_ai | §20.1 | verified: 0 hits of `parser_ai` in graph/rules packages | IMPLEMENTED | preserve; add CI test | none | architecture |
| 26 | Clean-checkout truth | §26.6, NFR-24 | `docs/documentation-clean-checkout-verification.md` exists; BUT `docs/status-snapshot.md` cites `models/registry/*.json` which are ABSENT from this checkout | PARTIALLY_IMPLEMENTED (drift) | status snapshot must cite repo-committed evidence only; Appendix AA claims re-verified per component | none | publishability |
| 27 | Anti-leakage / family split | §14.7, §15.15 | governance/lineage.py LeakageGroup; task_corpora split invariants | IMPLEMENTED | preserve | none | release blocker |
| 28 | Synthetic grades & promotion gates | §15.3 | training pipeline v3 + docs; no committed SYN gate code in clean checkout | DOCUMENTED_ONLY | keep documented; gates enforced by Reality Gate predicate applicability (E-14) | ML lead + auditor | training |
| 29 | Privacy-by-design local checks | §27.1 | governance/privacy.py scan/redact | IMPLEMENTED | preserve + extend to clarification source refs (opaque refs) | none | exports |
| 30 | NO_CORPUS discipline (no dataset download in repo workflows) | §25.7, task brief | data/ contains manifests + annotations only; corpora outside Git | IMPLEMENTED | preserve + scan | none | hygiene |

## Notes

- Row 26 drift detail: `models/registry/default.json` and `models/registry/training_program.json`
  are referenced by `docs/status-snapshot.md` as sources of truth but do not exist at
  `origin/main`. They exist only in the uncommitted historical worktree. Per clean-checkout
  truth they cannot support public claims until committed through review.
- Appendix AA ("Implementation Status Snapshot", non-normative) verified against this
  checkout: "Granite backend implemented" and "stage-level structured decoding integrated"
  are NOT observable at `origin/main` (they live on unmerged local branches
  `feat/granite-backend-cluster1`, `feat/structured-decoding-cluster3a`). AA is therefore
  treated as unverified for the clean checkout and not repeated as truth.
- v3 `Contradiction.status` values map cleanly onto v7 ConflictRecord resolution states and
  are preserved by migration, not deleted.
