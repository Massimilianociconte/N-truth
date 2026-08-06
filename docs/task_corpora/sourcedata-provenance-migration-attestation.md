# SourceData provenance sidecar migration — attestation (2026-08-06)

Migration: SOURCEDATA DETERMINISTIC PROVENANCE SIDECAR V1
Classification: PARTIAL_DETERMINISTIC (not full recovery)
Base main SHA: fe089eff42c16e3fa55606be340c85df57c5442b (PR #8 merged)
Branch: feat/sourcedata-provenance-sidecar-v1
Paths below are relative to EXTERNAL_DATASETS_ROOT (external dataset volume);
no private absolute paths are recorded in-repo.

## Canonical inputs (pre-migration, unchanged post-migration)

- records_sha256 (canonical, sorted LF-join semantics):
  562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10
- counts: train 60,266 / validation 8,201 / test 6,696 / excluded 0 / total 75,163
- raw roles_multi inputs (verified before build):
  train c2ac812846265686502469208dae435a5dc5279d6149940409f3b4566764c925;
  validation d2e98f0e71905e18cc4dbe208646113ddb4b869cf06d53af628156f6e1493715;
  test f7fbee9acd7e7f52ed92944d3d719c83164ba75e18218841d3dc764956c21a75
- leakage_audit.json: byte-identical before/after
- all canonical record JSONL files: byte-identical before/after (mtime unchanged)

## Upstream provenance asset

- official source: huggingface.co/datasets/EMBO/SourceData (EMBO)
- asset: xml/source_data_xml_v2.0.3.tar.gz
- archive SHA-256: 71f9899211efef62bc523275bbff7ba3e37ec8b4d1fc21405b58f4b68e93ba60
- archive bytes: 98,703,239
- resolvable official reference (re-verified 2026-08-06):
  upstream main 04333ae21badc91671a537e875bbca61b62f87e3
- historical acquisition revision b457c14041b61c56f671c6f966b4324f682855b7:
  UNRESOLVABLE upstream; preserved as historical provenance only; historical
  lock record untouched; no claim of Git-history restoration
- licence: LICENSE_REVIEW_REQUIRED / PENDING_LICENSE_SCOPE_CLOSURE

## Sidecar

- path: task_corpora/entity_roles/sourcedata/v2.0.3/provenance/sourcedata_provenance_map.jsonl
- rows: 75,163 (one per canonical record); duplicate keys: 0;
  missing canonical records: 0; extra sidecar rows: 0
- bytes: 60,799,460
- SHA-256: d452c49c31d8ecc2c1496971f6b8cfff67701402dc7db03266a613649ba95e07
  (dry-run build, post-write re-hash, and independent validation all agree)
- schema_version: 0.1.0; matching_algorithm_version: 0.1.0
- tiers: TIER_1_PANEL_UNIQUE 70,158 / TIER_2_ARTICLE_ONLY 3,914 /
  RECORD_FALLBACK 1,091 (exact reproduction of the audited C1.1 counts)
- fallback reasons: UNMATCHED_NO_EVIDENCE 1,091
  (train 916 / validation 97 / test 78); zero multi-DOI, zero short-segment,
  zero invalid-DOI rejections observed, matching the investigation counters
- whole-figure upstream units (175 records; no sd-panel upstream): kept in
  TIER_1_PANEL_UNIQUE with figure_id set and panel_id null; no panel invented
- write semantics: sibling temporary file, fsync, atomic rename, post-rename
  re-hash; no temporary file remains

## Deterministic dual-build

Two independent builds in separate staging directories: byte-for-byte
identical content, row ordering, SHA-256, tier counts and key coverage.
Canonical files are never written by the builder.

## Metadata changes (external)

- manifest.json: additive provenance_sidecar block; manifest_version
  0.2.2 → 0.3.0; manifest SHA-256 before 5b537b9f5884bc29370ea57ba581595856a49650ace59d1d2acdd4697c38002f,
  after 6174f9b508fde36c1f63645526d9586474b89efe718c33ebd2b1d278935c4494;
  records_sha256 and record_counts unchanged; embedded_document_id_present
  remains 0 (the sidecar does not replace embedded provenance)
- additive lock entry: manifests/sources/sourcedata_provenance_asset_lock_v1.json
  (SHA-256 d4c5c1e8eb790577a4bd45d248a910d187f5ba875d14f9650eafda6ec8098b5f);
  historical lock in manifests/datasets.json untouched

## Leakage limitations

- matched_subset_articles_crossing_existing_splits: 0 — diagnostic over the
  74,072 deterministically matched records only, explicitly excluding the
  1,091 RECORD_FALLBACK records
- paper_level_leakage_claim_allowed: false (global claim stays fail-closed)
- document_level_leakage: UNVERIFIED
- leakage_group_granularity: RECORD_LEVEL_FALLBACK (unchanged)

## Holds retained

DATA_READINESS BLOCKED; SCIENTIFIC_VALIDATION NOT_STARTED;
SOURCE_DATA_DEVELOPMENT_USE BLOCKED; SOURCE_DATA_TRAINING_USE BLOCKED;
SOURCE_DATA_EVALUATION_USE PENDING_LICENCE_DECISION; READY_FOR_B0_GO BLOCKED;
MODERNBERT_TRAINING HOLD; GRANITE_PROMOTION HOLD.
No sidecar result constitutes real gold or a real anchor.

## Explicit non-actions performed as none

No canonical JSONL rewrite; no label/content change; no record moved between
partitions; no fuzzy provenance; no invented identifiers; no eligibility
change; no licence decision; no paper-level leakage claim; no other dataset
workstream started; no PR merge.
