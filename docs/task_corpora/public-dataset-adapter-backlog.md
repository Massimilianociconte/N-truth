# Public dataset adapter backlog — documentation only

**Status:** BACKLOG / DESIGN_NOTES ONLY — no implementation in this operation
**Date:** 2026-08-06 · Branch `chore/dataset-portfolio-completion-bia-metadata-v1`
**Companion documents:** `dataset-portfolio-status-2026-08-06.md`, `c2-preclinie-design.md`, `c1.1-sourcedata-document-provenance-plan.md`.

Each item below is scoped to a **separate future PR**. Nothing here is implemented, built, or
trained. All model-use permissions remain fail-closed.

## Governing constraints (apply to every item)

- **Forbidden targets** (`FORBIDDEN_NTRUTH_TARGETS` in `packages/ntruth/data/config.py`):
  `independent_n`, `experimental_unit`, `independently_assigned`, `allocation_level`,
  `application_level`, `determinability_state`. No public auxiliary dataset may ever serve these.
- **Reference implementation pattern:** the sole implemented adapter
  `packages/ntruth/task_corpora/adapters/sourcedata_entity_roles.py`. Any future adapter must
  follow the same contract: LF-only JSONL, `records_sha256` content hash, split counts,
  `groups_crossing_splits` audit, `leakage_group_granularity` reporting, dual-run idempotence,
  NO_CORPUS-in-git, licence decision file with fail-closed unknowns.
- **Authority ceiling:** every corpus below stays SILVER_AUXILIARY at best. None is
  SCIENTIFIC_GOLD; none becomes MODEL_USE_ELIGIBLE without a written licence use decision.

## 1. C2 — PreClinIE routing + method indicators

- **Tasks:** `ROUTING`, `REPORTED_METHOD_INDICATOR`, `EVIDENCE_SPAN_CANDIDATE` (per
  `c2-preclinie-design.md`; routing labels `METHODS / STATISTICAL_METHODS / RESULTS / OTHER / UNKNOWN`).
- **Hard limits:** no experimental-unit gold, no allocation gold, no independent-n gold, no
  independence inference. A reported statement ("animals were randomly allocated") is at most an
  AUTHOR_ASSERTION / REPORTED_METHOD_INDICATOR / EVIDENCE_SPAN_CANDIDATE.
- **Preconditions:** licence scope confirmation for publication text (`LICENCE_REVIEW_REQUIRED`);
  cross-domain note — PreClinIE is cross-domain relative to the bootstrap in vitro profile and
  cannot validate N-Truth v1.0-A in vitro by itself.
- **Proposed files (future PR):** adapters `preclinie_routing.py` / `preclinie_method_indicators.py`,
  label maps, licence decision JSON, unit tests asserting AUTHOR_ASSERTION never maps to any
  forbidden target.

## 2. CRAFT — coreference and full-text structure

- **Tasks:** `ontology_concept_extraction`, `biomedical_coreference`,
  `syntactic_auxiliary_training` (per `DATASET_TASK_POLICIES`); candidate evidence linking against
  CRAFT's native full-text structure.
- **Hard limits:** no experimental-unit gold, no independent-n gold; CRAFT annotations are
  CC-BY-3.0 (`LICENSE_SCOPE_VERIFIED`) and remain SILVER_AUXILIARY with attribution.
- **Notes:** CRAFT ships its own document structure (full-text XML + concept annotation), so
  provenance quality is stronger than SourceData's RECORD_LEVEL_FALLBACK; the adapter must still
  audit `groups_crossing_splits` at document granularity before any model-use discussion.
- **Preconditions:** none data-side (VERIFIED_PRESENT, licence scope verified); adapter design
  review + separate PR only.

## 3. MeasEval — quantities, units, measured-property relations

- **Tasks:** `quantity_extraction`, `unit_extraction`, `measurement_context_extraction`,
  `measurement_relation_extraction` (per `DATASET_TASK_POLICIES`).
- **Precondition (blocking):** **upstream train/test article overlap must be resolved before any
  model-use partition.** The overlap is upstream; it must NOT be fixed by moving records. Until a
  documented, separately authorised partition decision exists, `training_ready_status` remains
  `BLOCKED_BY_UPSTREAM_GROUP_OVERLAP`.
- **Licence:** no LICENSE file upstream → `LICENCE_REVIEW_REQUIRED`; training
  `BLOCKED_BY_POLICY_AND_LICENSE`. Local use only pending review.
- **Hard limits:** no forbidden targets; measurement annotations do not assert experimental
  structure.

## 4. BioImage Archive / REMBI — imaging metadata mapping

- **Scope:** biosample / specimen / image-acquisition / image-analysis metadata mapping from
  REMBI-structured BioImages studies (see `bioimage-rembi-metadata-pilot.md` and
  `data_manifests/bioimage-rembi-candidates.yaml`).
- **Profile:** Imaging Profile only.
- **Hard limits:** no automatic well = experimental-unit inference; no gold role for any
  accession; licence re-verified per accession at any later sampling time (S-BIAD679 flagged).
- **Preconditions:** metadata-only pilot is complete; any image sampling requires separate
  authorisation and its own budget/licence review.

## Acceptance sketch (every future adapter PR)

```text
- LF-only JSONL + shared records_content_sha256
- groups_crossing_splits audited at the strongest justified granularity
- leakage_group_granularity explicitly reported
- synthetic_fraction = 0.0 until mixture-search approval
- NO_CORPUS in git
- dual-run idempotence proven
- licence decision file present; unknown permissions fail closed
- tests: no label ever maps to a FORBIDDEN_NTRUTH_TARGET
```
