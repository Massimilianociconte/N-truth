# REPORT B — DATASET PIPELINE FINAL AUDIT (2026-08-03)

generated_at: 2026-08-03T13:44:26Z
workstream: B only
candidate_commit: `fix/dataset-acquisition-pipeline` @ readiness-gates commit (see `git log -1 --oneline`) (`fix/dataset-acquisition-pipeline`)
data_root: `/Volumes/FLASH128/N-Truth-Datasets`

## Final status

```
DATASET_PIPELINE: REPAIRED_AND_VERIFIED

SOURCE_DATA: VERIFIED_AUXILIARY
PRECLINIE: VERIFIED_AUXILIARY
MEASEVAL: ACQUIRED_AND_PROCESSED_NOT_TRAINING_READY
CRAFT: VERIFIED
VOLUME: VERIFIED_WITH_FAT32_LIMITATION

TRAINING_PROGRAM: HOLD_PENDING_REAL_ANCHOR
SCIENTIFIC_VALIDATION: NOT_STARTED
CLUSTER_3B: HOLD
GRANITE_DEFAULT_PROMOTION: HOLD
PUSH: NOT_PERFORMED
MERGE: NOT_PERFORMED
```

## 1. Volume

| Field | Value |
|-------|-------|
| mount | `/Volumes/FLASH128` |
| UUID | `29DEE471-44F6-3B26-9A09-BBCC4A4D7D7C` |
| filesystem | FAT32 |
| free (approx) | ~42.5–43 GiB available |
| root | `N-Truth-Datasets` only data root |
| volume_status | `VERIFIED_WITH_FAT32_LIMITATION` |
| max_single_file_bytes | 4294967295 |
| max_observed_file | 1784087121 |
| near/over limit | none |

## 2. Merkle / idempotency

| Field | Value |
|-------|-------|
| merkle_root | `e1fac7112991f9369d783f2b18e677b68a994693dbd907c71af42caf1db4de7d` |
| algorithm | SHA-256 of sorted `relpath:file_sha256` lines |
| included | raw, processed, training_ready, manifests/splits.json, manifests/datasets.json |
| excluded | cache, downloads, logs, tools, reports, licenses, AppleDouble |
| second `all --resume` | **idempotent=true** |
| network_download_count | 0 |
| raw/processed/training_ready/manifests modified | 0 |

Evidence: `manifests/reports/idempotency_final.json`

## 3. CRAFT

- Tag **v5.0.2**, archive sha256 `56677e5110f81303642f49ec21dce9d55e38c95cef1162212514d8b2c73077f2`
- LICENSE CC-BY-3.0 file-verified on stick
- **upstream_split:** 67 development / 30 evaluation (official identifier files)
- **ntruth_split:** 60 train / 7 validation / 30 test — N-Truth derivation of the 67, **not** official three-way
- PMCID overlap: **0**
- source_status: **VERIFIED**

## 4. MeasEval

- Commit `1fa738b6bc9b72c84c88a80344ca3ab39a310a44`
- status: **ACQUIRED_AND_PROCESSED_NOT_TRAINING_READY**
- training_ready_status: **BLOCKED_BY_UPSTREAM_GROUP_OVERLAP**
- train∩test publication groups: **45**; train∩validation: **0**
- trial isolated (training_eligible=false, evaluation_eligible=false)
- five TXT-without-TSV stems all `missing_annotation_file` / non-eligible / requires_review=true
- **not** under `training_ready/`
- license: **LICENSE_REVIEW_REQUIRED** (no LICENSE file on stick)

## 5. SourceData

| Layer | train | validation | test |
|-------|------:|-----------:|-----:|
| upstream_raw NER | 60266 | 8201 | 6696 |
| upstream_raw ROLES_MULTI | 60266 | 8201 | 6696 |
| alignment matched | 60266 | 8201 | 6696 |
| derived_multitask | 60266 | 8201 | 6696 |

- revision lock: `b457c14041b61c56f671c6f966b4324f682855b7` version 2.0.3
- lock file SHA-256: all match
- join key implemented: positional line index + identical words (`panel_id` absent in locked JSONL)
- unmatched / token mismatches: 0
- derived multitask is **not** labeled “upstream split”
- license SPDX claim CC-BY-4.0 with **LICENSE_REVIEW_REQUIRED** (no local LICENSE file)

## 6. PreClinIE

- Commit `f38df55a28505a77d30eefb5b867bbfdcc9baf25`
- LICENSE **MIT** file-verified (`manifests/licenses/preclinie_LICENSE`)
- splits 1160 / 146 / 144; group leakage **0**
- SILVER_AUXILIARY; forbidden N-Truth targets listed in envelopes

## 7. License table (summary)

See `source-and-license-summary.json`. Inconclusive entries carry `LICENSE_REVIEW_REQUIRED` (SourceData local file, MeasEval packaging).

## 8. Tests

Clean detached checkout of closing commit: **37 passed** (`tests/unit/data` + `tests/integration/data/test_acquire_cli.py`). No raw/processed/cache/corpus blobs in commit tree. `git diff --check` clean after whitespace fix.

## 9. Non-goals respected

- No Cluster 3A changes
- No re-download without mismatch
- No format/rename of stick
- No push/merge
- No training / Granite promotion / Cluster 3B
