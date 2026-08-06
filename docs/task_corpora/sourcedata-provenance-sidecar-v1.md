# SourceData v2.0.3 deterministic provenance sidecar (v1 branch, schema 0.2.0)

Status: GENERATED_AND_VERIFIED (external sidecar; canonical records untouched)
Classification: PARTIAL_DETERMINISTIC — not full provenance recovery.
Branch: `feat/sourcedata-provenance-sidecar-v1` (base: PR #8 merged main).
Supersedes the schema 0.1.0 sidecar written earlier on the same branch (see
C1.1 erratum below and the migration attestation for hashes).

## What this is

One provenance row per canonical SourceData `entity_roles` task record
(75,163 rows), joining each record's original segment text to the official
SourceData XML v2.0.3 caption corpus using the fail-closed tier rules merged
in the C1.1 investigation (PR #8). The sidecar is an **external, additive**
mapping: canonical TaskRecord JSONL, partitions, labels, manifests' record
hashes and the leakage audit are never rewritten.

## C1.1 erratum (schema 0.2.0)

The 0.1.0 sidecar classified 175 authoritative whole-figure XML units (no
`sd-panel` child upstream) inside `TIER_1_PANEL_UNIQUE`. That is not panel
provenance. Schema 0.2.0 separates them into `TIER_1_FIGURE_UNIQUE`; the
combined unique-unit population (70,158) and all coverage figures are
unchanged. See
`c1.1-sourcedata-document-provenance-investigation-erratum-2026-08-06.md`.

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

## Schema (v0.2.0, strict)

`SidecarRow` uses `ConfigDict(extra="forbid")`: unknown fields are rejected.
Fields: `schema_version`, `dataset_id`, `dataset_version`, `task_corpus`,
`partition`, `source_row_index`, `canonical_record_id`,
`exact_source_text_sha256`, `provenance_tier`, `granularity`, `match_basis`,
`article_doi`, `figure_id`, `panel_id`, `ambiguity_reason`,
`upstream_asset_sha256`, `upstream_reference`, `matching_algorithm_version`.

Strict gates: `schema_version`/`matching_algorithm_version` pinned to
`0.2.0`; dataset identity literals (`SourceData` / `2.0.3` / `entity_roles`);
partition ∈ {train, validation, test}; `source_row_index >= 0`; non-empty
`canonical_record_id`; both SHA-256 fields lowercase 64-hex; cross-field
validation enforces every tier rule at construction time.

Tiers (canonical vocabulary, no competing enums):

- `TIER_1_PANEL_UNIQUE` (granularity PANEL) — deterministic exact unique-unit
  assignment where the authoritative XML path carries an `sd-panel` element.
  DOI required and well-formed; official `panel_id` required; `figure_id` may
  be present. `match_basis`: `deterministic exact unique-panel assignment`.
- `TIER_1_FIGURE_UNIQUE` (granularity FIGURE) — deterministic exact
  unique-unit assignment to a whole-figure upstream unit (no `sd-panel`
  child). DOI required; `figure_id` required; `panel_id` null — no panel
  identifier is invented. `match_basis`:
  `deterministic exact unique-figure assignment`.
- `TIER_2_ARTICLE_ONLY` (granularity ARTICLE) — DOI required; `figure_id` and
  `panel_id` always null; `match_basis` ∈
  {`EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL`, `CONTAINMENT_SINGLE_ARTICLE`}.
  Never serialized as panel or figure provenance.
- `RECORD_FALLBACK` (granularity RECORD_FALLBACK) — all upstream identifiers
  null; `ambiguity_reason` required.

## Archive extraction hardening

`extract_xml_archive` verifies the archive SHA-256 BEFORE extraction; refuses
stale/populated destinations; rejects absolute paths, traversal, symlinks,
hardlinks, duplicate member names and duplicate output basenames; enforces
configurable maximum file count, per-file size and total decompressed bytes;
stages output in a fresh temporary directory, fsyncs and publishes it with
one atomic rename; removes partial output on any failure.

Non-XML member policy (enforced and tested): the extractor tolerates
verified-benign non-XML file members and directory entries — they are
enumerated and screened exactly like XML members but are NEVER extracted —
while every hostile member class (absolute path, traversal, link, hidden,
non-file, duplicate) aborts the whole extraction fail-closed. Tolerated
members contribute nothing to the output directory or to any downstream
index.

## Typed manifest model

`BuildManifest.provenance_sidecar` is the typed `ProvenanceSidecarManifest`
(`extra="forbid"`): 16 required fields with invariants — tier counts sum to
`rows == 75,163`; `matched_subset_records` equals the matched tiers;
`fallback_records_excluded_from_diagnostic == record_fallback`;
`embedded_document_id_present == 0`;
`global_paper_level_leakage_claim_allowed == false`; SHA-256 fields strictly
validated. Manifests without the block still parse (default
`manifest_version` 0.2.2).

## Matching rules (inherited from the merged C1.1 implementation)

Exact deterministic matches are evaluated before containment; containment can
never override an exact-tier decision or rejection. No fuzzy similarity, no
first-match behaviour; malformed/missing DOIs are rejected; captions under
multiple DOIs remain unassigned; multi-article containment remains fallback;
normalization is whitespace-only and preserves case, punctuation, symbols,
biological identifiers and meaningful Unicode distinctions.

Algorithm version: `0.2.0`. Determinism contract: repeated builds are
byte-identical (dual-build verification is mandatory before any external
write; partition order, then physical row order; canonical JSON serialization).

## Results (audited counts, corrected decomposition)

| Tier | Rows |
|---|---|
| TIER_1_PANEL_UNIQUE | 69,983 |
| TIER_1_FIGURE_UNIQUE | 175 |
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
revision `b457c140…` is currently unresolvable as of 2026-08-06 and is
preserved as historical provenance only; the new lock entry pins both the
content SHA-256 and a currently resolvable official reference, and does not
claim restoration of the historical Git history.

## Components

- `packages/ntruth/task_corpora/provenance_sidecar.py` — strict schema 0.2.0,
  builder, hardened extraction, fail-closed validation.
- `scripts/task_corpora/sourcedata_sidecar_extract.py` — archive hash check,
  XML extraction, upstream caption index.
- `scripts/task_corpora/sourcedata_sidecar_build.py` — preflight (incl.
  per-file canonical JSONL hashes), dual-build, comparison, validation,
  optional atomic write/replace with supersession hash gate.
- `scripts/task_corpora/sourcedata_sidecar_validate.py` — independent
  post-write validation.
- `BuildManifest.provenance_sidecar` — typed `ProvenanceSidecarManifest`
  block (`manifest_version` 0.3.0; backward compatible when absent).
