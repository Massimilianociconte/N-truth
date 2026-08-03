# Volume constraints — FLASH128 N-Truth-Datasets

generated_at: 2026-08-03T14:22:06Z

## Status

- **volume_status:** `VERIFIED_WITH_FAT32_LIMITATION`
- **filesystem_tested:** `FAT32`
- **exfat_tested_in_this_run:** `false`
- **max_single_file_bytes:** `4294967295`
- **largest_current_file_bytes:** `1784087121`
- **largest_current_file_path:** `downloads/preclinie-f38df55a28505a77d30eefb5b867bbfdcc9baf25.zip`
- **current_dataset_storage:** `SUPPORTED`
- **future_large_model_or_checkpoint_storage:** `NOT_GUARANTEED`

## Recommendation (future only — not applied)

`FUTURE_STORAGE_MIGRATION_RECOMMENDED_BEFORE_LARGE_CHECKPOINTS`

Do not reformat, rename, or migrate FLASH128 in this workstream. Before multi-GiB model checkpoints, provision a separate exFAT/APFS volume with dual-write checksum verification.
