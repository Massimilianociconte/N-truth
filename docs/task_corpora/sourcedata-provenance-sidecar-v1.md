# SourceData v2.0.3 deterministic provenance sidecar (v1)

Status: GENERATED_AND_VERIFIED (external sidecar; canonical records untouched)
Classification: PARTIAL_DETERMINISTIC — not full provenance recovery.
Branch: `feat/sourcedata-provenance-sidecar-v1` (base: PR #8 merged main).

## What this is

One provenance row per canonical SourceData `entity_roles` task record
(75,163 rows), joining each record's original segment text to the official
SourceData XML v2.0.3 caption corpus using the fail-closed tier rules merged
in the C1.1 investigation (PR #8). The sidecar is an **external, additive**
mapping: canonical TaskRecord JSONL, partitions, labels, manifests' record
hashes and the leakage audit are never rewritten.

## Key contract

Primary join key: the canonical `record_id`, verified deterministic, non-null,
unique across all 75,163 records and stable across repeated builds. Every row
also carries the composite context (`dataset_id`, `dataset_version`,
`partition`, `source_row_index`) and `exact_source_text_sha256` computed from
the **original UTF-8 text** of the raw `roles_multi` export — never from the
normalized join key, and never a bare row number alone.

Canonical row `k` of a partition joins to raw `roles_multi` row `k` (verified:
equal line counts per partition; `source_record_id` row-index alignment
confirmed for all 75,163 records before the migration).

## Schema (v0.1.0)

Fields: `schema_version`, `dataset_id`, `dataset_version`, `task_corpus`,
`partition`, `source_row_index`, `canonical_record_id`,
`exact_source_text_sha256`, `provenance_tier`, `match_basis`, `article_doi`,
`figure_id`, `panel_id`, `ambiguity_reason`, `upstream_asset_sha256`,
`upstream_reference`, `matching_algorithm_version`.

Tiers (canonical vocabulary, no competing enums):

- `TIER_1_PANEL_UNIQUE` — deterministic exact unique-unit assignment.
  `match_basis`: `deterministic exact unique-panel assignment`.
  DOI required and well-formed; official `panel_id` when the authoritative
  XML path carries `sd-panel` units; for whole-figure units (no `sd-panel`
  upstream) `figure_id` is carried and `panel_id` stays `null` — no panel
  identifier is invented.
- `TIER_2_ARTICLE_ONLY` — DOI required; `panel_id` always `null`;
  `match_basis` ∈ {`EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL`,
  `CONTAINMENT_SINGLE_ARTICLE`}. Never serialized as panel provenance.
- `RECORD_FALLBACK` — all upstream identifiers `null`; `ambiguity_reason`
  required.

## Matching rules (inherited from the merged C1.1 implementation)

Exact deterministic matches are evaluated before containment; containment can
never override an exact-tier decision or rejection. No fuzzy similarity, no
first-match behaviour; malformed/missing DOIs are rejected; captions under
multiple DOIs remain unassigned; multi-article containment remains fallback;
normalization is whitespace-only and preserves case, punctuation, symbols,
biological identifiers and meaningful Unicode distinctions.

Algorithm version: `0.1.0`. Determinism contract: repeated builds are
byte-identical (dual-build verification is mandatory before any external
write; partition order, then physical row order; canonical JSON serialization).

## Results (audited counts reproduced exactly)

| Tier | Rows |
|---|---|
| TIER_1_PANEL_UNIQUE | 70,158 |
| TIER_2_ARTICLE_ONLY | 3,914 |
| RECORD_FALLBACK | 1,091 |
| total | 75,163 |

All 1,091 fallback records have `ambiguity_reason=UNMATCHED_NO_EVIDENCE`
(train 916 / validation 97 / test 78), identical to the C1.1 investigation's
`unmatched_no_containment` population.

## Leakage claims (fail-closed)

Permitted diagnostic only: `matched_subset_articles_crossing_existing_splits:
0` over the 74,072 deterministically matched records, **explicitly excluding**
the 1,091 RECORD_FALLBACK rows. Global claims remain false:
`paper_level_leakage_claim_allowed=false`, `document_level_leakage=UNVERIFIED`,
`leakage_group_granularity=RECORD_LEVEL_FALLBACK`.

## Licence and readiness holds

`LICENSE_REVIEW_REQUIRED` / `PENDING_LICENSE_SCOPE_CLOSURE` unchanged;
development and training use remain BLOCKED; evaluation pending the licence
decision. No model-use permission is promoted by this migration.

## Upstream provenance asset

Official XML v2.0.3 archive stored hash-verified under the external
`provenance/` directory (not committed to Git). Historical acquisition
revision `b457c140…` remains UNRESOLVABLE and is preserved as historical
provenance only; the new lock entry pins both the content SHA-256 and a
currently resolvable official reference, and does not claim restoration of the
historical Git history.

## Components

- `packages/ntruth/task_corpora/provenance_sidecar.py` — schema, builder,
  fail-closed validation.
- `scripts/task_corpora/sourcedata_sidecar_extract.py` — archive hash check,
  XML extraction, upstream caption index.
- `scripts/task_corpora/sourcedata_sidecar_build.py` — preflight, dual-build,
  comparison, validation, optional atomic write.
- `scripts/task_corpora/sourcedata_sidecar_validate.py` — independent
  post-write validation.
- `BuildManifest.provenance_sidecar` — additive manifest block
  (`manifest_version` 0.2.2 → 0.3.0; backward compatible).
