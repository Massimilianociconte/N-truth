# SourceData provenance sidecar migration v2 attestation (schema 0.2.0 correction)

Status: EXTERNAL_METADATA_CORRECTED (v2 attestation; v1 attestation immutable)
Date: 2026-08-06
Branch: `feat/sourcedata-provenance-sidecar-v1` (PR #9, open, unmerged)
Supersedes: the schema 0.1.0 sidecar attested in
`sourcedata-provenance-migration-attestation.md` (v1). The v1 attestation and
the external v1 attestation
(`reports/workstream_c/sourcedata_provenance_sidecar_migration_2026-08-06.md`)
are NOT overwritten; this document records the correction.

## Why this correction exists (C1.1 erratum)

The 0.1.0 sidecar classified 175 authoritative whole-figure XML units (no
`sd-panel` child upstream) inside `TIER_1_PANEL_UNIQUE`. That is not panel
provenance. Schema 0.2.0 separates them into `TIER_1_FIGURE_UNIQUE`
(`figure_id` set, `panel_id` null; no panel identifier is invented). See
`c1.1-sourcedata-document-provenance-investigation-erratum-2026-08-06.md`.
The combined unique-unit population (70,158) and every coverage figure are
unchanged.

## Corrected tier counts (audited)

| Tier | Rows |
|---|---|
| TIER_1_PANEL_UNIQUE | 69,983 |
| TIER_1_FIGURE_UNIQUE | 175 |
| TIER_2_ARTICLE_ONLY | 3,914 |
| RECORD_FALLBACK | 1,091 |
| total | 75,163 |

Diagnostic over the matched subset only (RECORD_FALLBACK excluded):
`matched_subset_records: 74,072`; `matched_subset_articles: 3,508`;
`matched_subset_articles_crossing_existing_splits: 0`;
`fallback_records_excluded_from_diagnostic: 1,091`.

## Artifact hashes

Sidecar (`provenance/sourcedata_provenance_map.jsonl`, 62,622,635 bytes):

- superseded (schema 0.1.0): `d452c49c31d8ecc2c1496971f6b8cfff67701402dc7db03266a613649ba95e07`
- current (schema 0.2.0): `7cfba6f9f1a49ee5434c60a8510a7e6702e16849666b081323eee9a1894a041a`
- supersession reason: panel and figure provenance granularities separated

External `manifest.json` (`manifest_version` stays 0.3.0):

- before: `6174f9b508fde36c1f63645526d9586474b89efe718c33ebd2b1d278935c4494`
- after: `31d4fb939e086726b95b20f998e52756dad4153b62965d02b00f7125176e2ee6`
- the `provenance_sidecar` block is now the strict 16-field
  `ProvenanceSidecarManifest` payload (`schema_version`/`algorithm_version`
  0.2.0); contextual keys dropped from the block are preserved in the
  provenance asset lock and in this attestation.

Provenance asset lock (`manifests/sources/sourcedata_provenance_asset_lock_v1.json`):

- before: `d4c5c1e8eb790577a4bd45d248a910d187f5ba875d14f9650eafda6ec8098b5f`
- after: `7a4ff95d16fc33613971d90c5f2d9c5797db0722c3edd18d3b0ab6c6fea4d6c9`
- `related_sidecar` now records schema/algorithm 0.2.0, the corrected sha and
  the full supersession record.

Canonical inputs unchanged:

- `records_sha256`: `562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10` (unchanged)
- canonical per-partition JSONL hashes and the leakage audit file verified
  byte-identical by build preflight before any external write
- upstream XML archive sha: `71f9899211efef62bc523275bbff7ba3e37ec8b4d1fc21405b58f4b68e93ba60`

## Build guarantees applied before the external write

- dual build in two clean directories, byte-identical sidecar output;
- independent post-write validator returned `problems: []` with the corrected
  tier counts;
- atomic replacement gated on the superseded sidecar sha (`d452c49c…`);
- hardened archive extraction (hash gate before unpack, staging directory,
  quotas, hostile-member rejection, atomic publish).

## Leakage posture (fail-closed, unchanged)

- `paper_level_leakage_claim_allowed: false`
- `global_paper_level_leakage_claim_allowed: false`
- `document_level_leakage: UNVERIFIED`
- `leakage_group_granularity: RECORD_LEVEL_FALLBACK`
- the matched-subset diagnostic explicitly excludes the 1,091 RECORD_FALLBACK
  records; `groups_crossing_splits=0` is not paper-level isolation.

## Licence and readiness holds (unchanged)

- `licence_status: PENDING_LICENSE_SCOPE_CLOSURE`,
  `licence_review_status: LICENSE_REVIEW_REQUIRED`
- `data_readiness: BLOCKED`, `model_use_status: BLOCKED`,
  `scientific_validation: NOT_STARTED`, `training_eligible: false`
  (`substantive_training_allowed: false`)
- no model-use permission is promoted by this correction.

## Historical reference

Acquisition revision `b457c14041b61c56f671c6f966b4324f682855b7` is currently
unresolvable as of 2026-08-06 and remains historical provenance only
(`restores_historical_git_history: false`).
