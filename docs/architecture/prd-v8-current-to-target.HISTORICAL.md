# HISTORICAL — PRD v8 current-to-target map

`prd-v8-current-to-target.yaml` is **HISTORICAL** as of the PRD v9 unified
integration tree. The live map is
[`prd-current-to-target.yaml`](./prd-current-to-target.yaml) (v0.2).

The v8 file is kept byte-for-byte unchanged on purpose:

- its root literals (`schema_version`, `map_id`, `base_sha`,
  `target_contract`, `status_semantics`) are pinned by
  `ntruth.governance.repository_truth.validate_current_target_map`, and the
  file is parsed with a strict JSON reader, so neither comments nor new fields
  can be added without failing the v8 repository-truth integration tests;
- it remains the reviewed evidence base for the v8 migration audit
  (see `docs/audits/prd-v8-full-migration/`).

Do not extend or reformat the v8 file. Record all current-state changes in the
v0.2 map instead.
