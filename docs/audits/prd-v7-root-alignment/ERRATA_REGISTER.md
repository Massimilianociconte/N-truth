# PRD v7.0 Errata Register — Root Alignment

**Register ID:** ERRATA-PRDV7-ROOT-001
**Created:** 2026-08-03
**Worktree:** clean checkout of `origin/main` at `0dcef3e54ca908d491726c4b7dfe810aa754549a`
(branch `feat/prd-v7-root-alignment`)
**Authoritative PRD:** `prd/N-Truth_PRD_scientifico_completo_v7.0.pdf`
SHA-256 `00b544f04796f73f75e859c4cbff0ba4193a314661d50d5258d4bc9b0a13369f`
**Verified assessment:** `prd/N-Truth_Qwen_review_assessment_v1.0.pdf`
SHA-256 `6dab65698d5e098b41e766f956118890958c4bfd3676442b62ee974a82820efc`
Both hashes verified on 2026-08-03 before any alignment work.

## Scope and rules of this register

This register records internal inconsistencies found while reconciling PRD v7.0 against the
clean-checkout repository. Per the alignment mandate, scientific contradictions are NOT
silently resolved: each item is classified, the safest fail-closed engineering behaviour is
implemented, and items requiring scientific review are recorded as open blockers.

Classifications used:

- `DOCUMENT_EDITORIAL_FIX` — wording/formatting; no behavioural impact.
- `ENGINEERING_CLARIFICATION` — implementable without scientific judgement.
- `SCIENTIFIC_REVIEW_REQUIRED` — needs a biostatistician / wet-lab / methodology reviewer.
- `PROVISIONAL_THRESHOLD` — numeric value explicitly provisional until pilot data exist.
- `BACKWARD_COMPATIBILITY_DECISION` — requires a migration decision for existing records.

---

## E-01 — Feasibility volume: §18.4 (100–150) vs Appendix D.2 (150–250)

- **Observation.** §18.4 and §32.5 state the feasibility stage uses 100–150 real cases.
  Appendix D.2 ("Feasibility pilot") states 150–250 cases.
- **Classification.** `SCIENTIFIC_REVIEW_REQUIRED` + `PROVISIONAL_THRESHOLD`.
- **Engineering decision (fail-closed).** No case-count threshold is hard-coded anywhere in
  the clean checkout. Feasibility gating treats the required volume as an explicit,
  versioned protocol parameter with status `UNRESOLVED`; any gate evaluation that would need
  the volume returns `UNKNOWN` and therefore blocks (fail-closed) until a reviewer fixes one
  canonical value in a protocol amendment.
- **Open blocker.** `BLK-SCIENTIFIC-001`: biostatistician must choose the canonical
  feasibility volume (or a rule for reconciling the two ranges) before feasibility opens.

## E-02 — Reality-check volume: §18.2 (1–3) vs §14.5 / §32.1 (3–5)

- **Observation.** §18.2 requires "almeno 1–3 fonti reali/pubbliche" for the reality-check
  pilot; §14.5 and §32.1 say "3–5 reality-check cases".
- **Classification.** `SCIENTIFIC_REVIEW_REQUIRED` + `PROVISIONAL_THRESHOLD`.
- **Engineering decision (fail-closed).** The Reality Gate predicate
  `schema_stable_on_real_cases` cannot be satisfied by a count rule; it requires recorded,
  hash-identified real cases with a completed second review. Until then it stays `FALSE` or
  `UNKNOWN`, both of which block. No numeric cutoff is encoded.
- **Open blocker.** `BLK-SCIENTIFIC-002`: canonical reality-check case count.

## E-03 — §10.6 fixed 50% ruleset-coverage redirect vs PROVISIONAL-threshold rule

- **Observation.** §10.6 says that if more than 50% of real cases are OUT_OF_SCOPE or
  indeterminate for lack of patterns, the rulebook must be expanded or the domain narrowed.
  §18.7 and the assessment say thresholds must be preregistered after the pilot and that
  values like 0.60/70% are provisional examples.
- **Classification.** `PROVISIONAL_THRESHOLD` + `SCIENTIFIC_REVIEW_REQUIRED`.
- **Engineering decision (fail-closed).** The 50% figure is NOT implemented as a gate.
  Coverage measurement is implemented as reporting (percentages per state on real cases);
  the redirect/kill decision remains a human, preregistered protocol decision. The disputed
  50% rule is never hard-coded without explicit provisional status.
- **Open blocker.** `BLK-SCIENTIFIC-003`: preregistered redirect thresholds after pilot.

## E-04 — §15.3 fixed minimum of 50 synthetic realisations per cycle vs risk-based audit sizes

- **Observation.** §15.3 requires "almeno 50 realizzazioni stratificate" per synthetic cycle
  while §17.4/§18 leave audit sizes to measurement and risk.
- **Classification.** `PROVISIONAL_THRESHOLD`.
- **Engineering decision.** Synthetic promotion gates in the clean checkout do not consume a
  fixed 50-item constant; audit size is a per-cycle manifest field. Until a cycle manifest
  with an audited sample exists, synthetic lots remain non-promotable (`SYN_G*_UNANCHORED`
  semantics preserved from the v6.1 engineering line).
- **Open blocker.** none (engineering is fail-closed by default); reviewer confirmation of
  the 50-realisation minimum is recorded as a documentation question only.

## E-05 — Appendix F sequencing B0–B5 vs reality-first ordering (§4.2) and MVT-A

- **Observation.** Appendix F step 5 says "Eseguire baseline B0–B5" before the calibration
  pilot (step 6), while §4.2 orders reality-check → wizard → Minimum Viable Train A →
  calibration, and §12.3 defines MVT-A as B0/B4 only.
- **Classification.** `ENGINEERING_CLARIFICATION` + `DOCUMENT_EDITORIAL_FIX`.
- **Engineering decision.** The repository follows §4.2/§12.3: the contract implemented for
  MVT-A is B0/B4-or-encoder with hard verifier and human review. Appendix F is treated as a
  historical 90-day plan whose B0–B5 line predates the MVT-A narrowing; it is documented as
  superseded in the migration map, not acted upon.
- **Open blocker.** none.

## E-06 — Legacy "Core Profile" terminology vs "Bootstrap Core"

- **Observation.** Appendices D.1 and F.1 still say "Core Profile"; the v7 normative term is
  "Bootstrap Core" (§0.2, §8.2, Appendix X). Historical repo docs (`docs/core-profile-d0.md`
  in the dirty worktree; `public-specification-v0.1.md` in the clean checkout) use "Core
  Profile".
- **Classification.** `DOCUMENT_EDITORIAL_FIX` + `BACKWARD_COMPATIBILITY_DECISION`.
- **Engineering decision.** v7 code uses `bootstrap_core`. Legacy "Core Profile" documents
  keep their names (historical), and the migration map records
  `Core Profile (legacy) ≡ Bootstrap Core (v7)` for the micro-domain. No silent rename of
  historical files.
- **Open blocker.** none.

## E-07 — Appendix B "classify determinability" vs normative derive-then-review (§18.6)

- **Observation.** Appendix B step 9 says annotators "classificare determinabilità", while
  §18.6 requires determinability to be DERIVED from the normative table and then reviewed,
  never freely chosen.
- **Classification.** `ENGINEERING_CLARIFICATION`.
- **Engineering decision.** Implemented per §18.6: the v7 derivation function computes the
  state from graph facts; annotation UI/exports may record a reviewer's agreement or
  correction of the DERIVED state as an authority event, never a free choice. Appendix B is
  flagged as editorially superseded on this point.
- **Open blocker.** none.

## E-08 — Appendix N field matrix vs complete Bootstrap Core (§8.2) and four independences

- **Observation.** Appendix N omits several §8.2 Bootstrap Core requirements: source
  preparation, key counts, missing decisive fact, primary question, assignment timing, and
  the interference/exposure and analytical dimensions of independence; it also introduces
  `independence_mechanism: required_if_true` which appears nowhere else.
- **Classification.** `ENGINEERING_CLARIFICATION` + `SCIENTIFIC_REVIEW_REQUIRED`.
- **Engineering decision.** The implemented Bootstrap Core follows §8.2/Appendix X (the
  superset). `independence_mechanism` is kept as an optional extension field
  (`required_if_true` semantics: required when `independently_assigned == TRUE`), documented
  as Appendix-N-derived. The four independence dimensions remain distinct fields; none is
  derived from another.
- **Open blocker.** `BLK-SCIENTIFIC-004`: reviewer sign-off on the Appendix N reconciliation.

## E-09 — `acquired_from` in Appendix A but absent from the formal relation registry (§8.5)

- **Observation.** Appendix A uses `acquired_from` (field → well); §8.5 lists `measured_on`,
  `observed_in` but not `acquired_from`. Tavola 05 corrections (§15.8) explicitly prefer
  "image acquired_from field/well" over "measured_on well".
- **Classification.** `ENGINEERING_CLARIFICATION` + `BACKWARD_COMPATIBILITY_DECISION`.
- **Engineering decision.** `acquired_from` is added to the versioned relation registry
  (v7.0.0) for acquisition provenance (image/file ← field/well/instrument). `measured_on`
  keeps its measurement semantics. An alias/normalization table records legacy spellings so
  existing records are not silently broken.
- **Open blocker.** none.

## E-10 — Canonical spelling: analyzed vs analysed

- **Observation.** §11.5 lifecycle arrow uses "analysed"; §7.9/§15.2/Appendix O use
  `n_analyzed`, `analyzed`. The existing codebase (`NKind.ANALYZED = "analyzed"`) uses
  American spelling.
- **Classification.** `BACKWARD_COMPATIBILITY_DECISION` + `DOCUMENT_EDITORIAL_FIX`.
- **Engineering decision.** Canonical machine spelling is `analyzed` (matches the existing
  code and the majority of PRD field names). `analysed` is accepted as an alias on input and
  mapped to the canonical kind; exports use `analyzed`. Human-facing prose may use either.
- **Open blocker.** none.

## E-11 — Canonical count semantics: experimental_unit_count_candidate vs experimental_unit_count vs independent_n vs biological_source_count

- **Observation.** §7.9 Bootstrap Count Profile lists `experimental_unit_count_candidate`;
  §15.2 records distinguish `experimental_unit_count`; `independent_n` and
  `biological_source_count` appear throughout with distinct semantics (§7.1: biological
  source count is always semantically distinct from experimental unit count even when
  numerically equal).
- **Classification.** `ENGINEERING_CLARIFICATION`.
- **Engineering decision.** Canonical kind set implemented:
  - `experimental_unit_count_candidate` — parser/annotation candidate; never a verdict;
  - `experimental_unit_count` — rule-engine output only, allowed only in `DETERMINATE`;
  - `independent_n` — rule-engine output only, scope-aware, never emitted by the parser;
  - `biological_source_count` — independent kind, never conflated with EU counts.
  Invariants reject records where a parser-origin count carries
  `experimental_unit_count`/`independent_n`.
- **Open blocker.** none.

## E-12 — Terminology: CAUSAL_AWARE vs CAUSAL_SCOPED vs "Causal Scope Layer" vs "Causal Design Context"

- **Observation.** The PRD v7 cover says "CAUSAL-AWARE"; the assessment (§1, §5, §7) says
  "CAUSAL-SCOPED" and "Causal Scope Layer"; the normative term in §0.2/§2.4/§8.2 is "Causal
  Design Context".
- **Classification.** `DOCUMENT_EDITORIAL_FIX`.
- **Engineering decision.** Canonical engineering name: `CausalDesignContext` (v7 §0.2).
  "Causal Scope Layer" is recorded as the assessment's label for the same extension;
  "CAUSAL-AWARE" remains the version tagline. No behavioural difference.
- **Open blocker.** none.

## E-13 — Workstream B/C historical naming vs v7 Workstream definitions (§4.1)

- **Observation.** Merged PRs #2/#3 and repo docs use "Workstream B" = dataset acquisition
  and "Workstream C" = ModernBERT task corpora. PRD v7 §4.1 defines Workstream B = Minimum
  Viable Train A / parser AI and Workstream C = Real Anchor / silver / synthetic.
- **Classification.** `BACKWARD_COMPATIBILITY_DECISION` + `DOCUMENT_EDITORIAL_FIX`.
- **Engineering decision.** Historical reports keep their original labels with a note that
  their names predate the v7 taxonomy. Version-qualified mapping introduced:
  `LEGACY_WS_B_DATASET_ACQUISITION`, `LEGACY_WS_C_TASK_CORPORA` →
  v7 `WS_A/WS_B/WS_C/WS_D`. Future-facing docs use v7 names.
- **Open blocker.** none.

## E-14 — Reality Gate predicate `synthetic_factory_human_calibrated` vs Minimum Viable Train A before synthetic promotion

- **Observation.** §0.7 lists `synthetic_factory_human_calibrated: true` among Reality Gate
  requirements for substantive training, but §14.8 allows SYN-G0/G1 engineering use before a
  real baseline and MVT-A (§12.3) does not require any synthetic data.
- **Classification.** `ENGINEERING_CLARIFICATION`.
- **Engineering decision.** The predicate is marked `NOT_APPLICABLE` for MVT-A and for any
  gate evaluation performed before synthetic promotion is requested. It becomes applicable
  (and must be TRUE) only when a synthetic lot requests training-approved status or when
  substantive fine-tuning is requested. This keeps the gate fail-closed without blocking
  MVT-A contracts.
- **Open blocker.** none.

## E-15 — SourceData/PreClinIE "intended use" language vs unverified/restricted licence permissions

- **Observation.** §16.2–16.3 describe intended uses (NER, auxiliary pretraining, baseline)
  for SourceData-NLP and PreClinIE, while §16.9 and the clean-checkout task-corpora lineage
  record that per-record licence/use decisions are still pending for several datasets
  (e.g. MeasEval not training-ready; granular `use_decision` fields default to fail-closed).
- **Classification.** `ENGINEERING_CLARIFICATION` + `SCIENTIFIC_REVIEW_REQUIRED` (licence
  interpretation is a data-steward decision).
- **Engineering decision (fail-closed).** Intended-use prose is never treated as permission.
  The cross-domain/licence policy requires an explicit `LicenseUseDecision` per dataset and
  per capability; `unknown` fails closed. No SourceData/PreClinIE record is marked
  training-eligible in the clean checkout.
- **Open blocker.** `BLK-DATA-001`: data-steward licence/use decisions for each silver
  candidate dataset (recorded in the dataset handoff document).

---

## Open blocker register (summary)

| ID | Area | Description | Owner | Status |
|----|------|-------------|-------|--------|
| BLK-SCIENTIFIC-001 | Feasibility volume | Canonical case count 100–150 vs 150–250 | Biostatistician | OPEN |
| BLK-SCIENTIFIC-002 | Reality-check volume | Canonical case count 1–3 vs 3–5 | Biostatistician + product owner | OPEN |
| BLK-SCIENTIFIC-003 | Redirect thresholds | Preregistered coverage/redirect thresholds after pilot | Biostatistician | OPEN |
| BLK-SCIENTIFIC-004 | Appendix N reconciliation | Bootstrap Core field matrix sign-off | Wet-lab + biostat reviewer | OPEN |
| BLK-DATA-001 | Licence/use decisions | Per-dataset granular use decisions (SourceData, PreClinIE, CRAFT, MeasEval, Lazic) | Data steward | OPEN |

No item in this register was resolved by inventing a scientific answer. All engineering
behaviour chosen here is the fail-closed option.
