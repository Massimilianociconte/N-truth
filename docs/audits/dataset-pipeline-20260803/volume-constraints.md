# Volume constraints — FLASH128 N-Truth-Datasets

generated_at: 2026-08-03T13:44:26Z

## Status

- **volume_status:** `VERIFIED_WITH_FAT32_LIMITATION`
- **filesystem_tested:** `FAT32`
- **exfat_tested_in_this_run:** `false`
- **max_single_file_bytes:** `4294967295` (4 GiB − 1)

## Observations

- Mount point: `/Volumes/FLASH128` (external USB)
- Volume UUID: `29DEE471-44F6-3B26-9A09-BBCC4A4D7D7C`
- Dataset root: `/Volumes/FLASH128/N-Truth-Datasets` (sole N-Truth data root on volume)
- Max observed canonical file: **1784087121** bytes
  (`downloads/preclinie-….zip` ≈ 1.78 GiB)
- Files near/over 4 GiB limit: **none**

## Future migration recommendation (do not apply in this run)

Do **not** reformat or rename FLASH128 in place. If a future corpus requires a single file ≥ 4 GiB:

1. Provision a new volume as **exFAT** or **APFS**.
2. Dual-write with checksum verification (archive SHA-256 + Merkle).
3. Switch `NTRUTH_DATA_ROOT` only after dual verification.
4. Retain the FAT32 stick as offline backup until migration is proven.

## FAT32 implications for the pipeline

- Atomic `os.replace` on the same volume remains valid.
- AppleDouble `._*` / `.DS_Store` are filtered from Merkle via `is_ignorable_metadata`.
- No single canonical file currently approaches the 4 GiB barrier.
