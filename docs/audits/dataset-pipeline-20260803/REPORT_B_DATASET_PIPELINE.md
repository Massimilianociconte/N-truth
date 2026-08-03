# REPORT B — DATASET PIPELINE SIGN-OFF (2026-08-03)

generated_at: 2026-08-03T14:22:06Z
branch: `fix/dataset-acquisition-pipeline`
base_commit: `f3a04dd` (readiness gates)
workstream: B only (Cluster 3A not modified)

## WORKSTREAM_B_REVIEW: APPROVED_WITH_CLARIFICATIONS

```
DATASET_PIPELINE: REPAIRED_AND_VERIFIED

SOURCE_DATA:
  acquisition: VERIFIED
  processing: VERIFIED
  data_tier: SILVER_AUXILIARY
  training_readiness: PENDING_LICENSE_SCOPE_CLOSURE

PRECLINIE:
  acquisition: VERIFIED
  processing: VERIFIED
  data_tier: SILVER_AUXILIARY
  training_readiness: PENDING_LICENSE_SCOPE_CONFIRMATION

MEASEVAL:
  acquisition: VERIFIED
  processing: VERIFIED
  data_tier: SILVER_AUXILIARY
  training_readiness: BLOCKED_BY_UPSTREAM_GROUP_OVERLAP

CRAFT:
  acquisition: VERIFIED
  processing: VERIFIED
  data_tier: SILVER_AUXILIARY
  training_readiness: AUXILIARY_READY

VOLUME: VERIFIED_WITH_FAT32_LIMITATION

TRAINING_PROGRAM: HOLD_PENDING_REAL_ANCHOR
SCIENTIFIC_VALIDATION: NOT_STARTED
CLUSTER_3B: HOLD
GRANITE_DEFAULT_PROMOTION: HOLD
PUSH: NOT_PERFORMED
MERGE: NOT_PERFORMED
```

None of the four datasets is real anchor / Parser Gold / Derivation Gold / External Challenge / scientific validation set.

## Volume

| Field | Value |
|-------|-------|
| mount | `/Volumes/FLASH128` |
| UUID | `29DEE471-44F6-3B26-9A09-BBCC4A4D7D7C` |
| filesystem | FAT32 |
| free | ~42.5 GiB available |
| max_single_file_bytes | 4294967295 |
| largest_current_file_bytes | 1784087121 |
| largest file | `downloads/preclinie-f38df55a28505a77d30eefb5b867bbfdcc9baf25.zip` |
| near/over 4 GiB limit | none |
| future migration | FUTURE_STORAGE_MIGRATION_RECOMMENDED_BEFORE_LARGE_CHECKPOINTS (not applied) |

## Merkle lineage

| Root | Value |
|------|-------|
| previous (post-MeasEval-fix idempotent) | `0ab7db467c91310394854f7cc93c1d57d014674f22a2b18e2776e74b83180db4` |
| intermediate (post readiness gates f3a04dd era) | `e1fac7112991f9369d783f2b18e677b68a994693dbd907c71af42caf1db4de7d` |
| **current** | `6f5bcc4551365df0c6153e1545e8f9aa85f3eb7f13b3adcabdfec4afd85305d0` |

**Why it changed**

1. **0ab7 → e1fac:** canonical `manifests/datasets.json` gained CRAFT `upstream_split`/`ntruth_split` and MeasEval `training_ready_status` / `status` (readiness metadata). Raw/processed corpora not the driver.
2. **e1fac → current:** `datasets.json` PreClinIE authority renamed to `NTRUTH_GROUP_STRATIFIED_DERIVATION` + grouping metadata; `training_ready/.../alignment_report.json` gained formal `join_key` object. Again not a raw corpus rewrite; no network download.

See `merkle-lineage.json` for algorithm, inclusions/exclusions, AppleDouble handling.

## Idempotency (this sign-off)

Second `uv run python -m ntruth.data.acquire all --root … --resume` after stabilize:

- network_download_count = 0
- raw/processed/training_ready/canonical manifests/splits modified = 0
- merkle_unchanged = true
- idempotent = true

## SourceData

| Layer | train | validation | test |
|-------|------:|-----------:|-----:|
| upstream_raw NER | 60266 | 8201 | 6696 |
| upstream_raw ROLES_MULTI | 60266 | 8201 | 6696 |
| alignment matched | 60266 | 8201 | 6696 |
| derived_multitask | 60266 | 8201 | 6696 |

Join key (revision-bound, not stable across HF revisions if export order changes):

- source_configuration: `token_classification/v_2.0.3`
- upstream_split: from paired file path
- source_file_or_config: `ner/{split}.jsonl` + `roles_multi/{split}.jsonl`
- source_record_index: 0-based physical line index
- words_sha256: sha256(NUL-joined words); must match at index

Lock revision `b457c14041b61c56f671c6f966b4324f682855b7` — all 6 file SHA-256 match. License: **LICENSE_REVIEW_REQUIRED** (no local LICENSE file; CC-BY-4.0 claimed).

## PreClinIE

- commit `f38df55a28505a77d30eefb5b867bbfdcc9baf25`
- split_authority: **NTRUTH_GROUP_STRATIFIED_DERIVATION** (not official)
- grouping_key: publication_id; seed 20260803; 1160/146/144; leakage 0
- LICENSE MIT file SHA verified on stick; **scope of included publication text vs annotations → LICENSE_REVIEW_REQUIRED / PENDING_LICENSE_SCOPE_CONFIRMATION** for training

## MeasEval

- commit `1fa738b6bc9b72c84c88a80344ca3ab39a310a44`
- training_ready_status: **BLOCKED_BY_UPSTREAM_GROUP_OVERLAP**
- train∩test groups: 45; train∩validation: 0; not in `training_ready/`
- trial isolated; five missing-TSV stems all `missing_annotation_file` / non-eligible / requires_review=true
- future overlap policy: **PENDING_HUMAN_DECISION** (REMOVE_OVERLAPPING_GROUPS_FROM_TRAIN | CREATE_NTRUTH_GROUP_SAFE_SPLIT | FORMAT_SMOKE_ONLY | EXCLUDE_FROM_MODEL_TRAINING)
- license: **LICENSE_REVIEW_REQUIRED**

## CRAFT

- tag v5.0.2; archive sha256 `56677e5110f81303642f49ec21dce9d55e38c95cef1162212514d8b2c73077f2`
- upstream_split: 67 development / 30 evaluation
- ntruth_split: 60 train / 7 validation / 30 test (NTRUTH_DETERMINISTIC_DERIVATION from official id files — **not** official three-way)
- PMCID overlap: 0; test training_eligible=false
- annotations LICENSE **CC-BY-3.0** file-verified → training_readiness **AUXILIARY_READY** (SILVER_AUXILIARY only)

## Licenses — concluded vs pending

| Dataset | review_status | training implication |
|---------|---------------|----------------------|
| SourceData | LICENSE_REVIEW_REQUIRED | PENDING_LICENSE_SCOPE_CLOSURE |
| PreClinIE | LICENSE_REVIEW_REQUIRED | PENDING_LICENSE_SCOPE_CONFIRMATION |
| MeasEval | LICENSE_REVIEW_REQUIRED | also BLOCKED_BY_UPSTREAM_GROUP_OVERLAP |
| CRAFT | LICENSE_SCOPE_VERIFIED (annotations CC-BY-3.0) | AUXILIARY_READY |

## Human decisions still required

1. SourceData: obtain/attach LICENSE file proof for CC-BY-4.0 scope on annotations vs text.
2. PreClinIE: confirm MIT covers annotations and included abstract/Methods text for model training.
3. MeasEval: license scope + choose overlap policy (options listed; not applied).
4. CRAFT article redistribution/training terms beyond annotations if full-text models expand scope.

## Tests (to be filled by clean checkout log)

See closing verification: unit+integration data tests exact counts.

## Discipline

- No push / no merge
- No Cluster 3A / Granite / registry / B4 / P0 / LoRA / annotation trial changes
- No re-download / no format / no rename of stick
