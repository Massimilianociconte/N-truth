# PR #3 post-merge attestation

**Does not rewrite** `workstream-c-c0-c1-readiness.md` historical evidence.

## Merge

| Field | Value |
|-------|--------|
| PR | [#3](https://github.com/Massimilianociconte/N-truth/pull/3) |
| Method | **merge commit** (not squash) |
| Merge SHA | `0dcef3e54ca908d491726c4b7dfe810aa754549a` |
| Merged at | `2026-08-03T15:58:26Z` |
| Pre-merge head | `d3d6e3e98a27f37074a4de160702f2e9434a4ecd` |
| Base | `main` @ `ff8cd8963a5afeb3c87744e441c0ce3500bacafc` |
| CI (pre-merge) | deterministic-core + linux-portability green — runs [30829176746](https://github.com/Massimilianociconte/N-truth/actions/runs/30829176746), [30829176628](https://github.com/Massimilianociconte/N-truth/actions/runs/30829176628) |

## Post-merge local verification (clean worktree @ merge SHA)

| Gate | Result |
|------|--------|
| `tests/unit/task_corpora` | PASS |
| full `tests/unit` | PASS |
| ruff / mypy | PASS |
| `git diff --check` | clean |
| NO_CORPUS | PASS (`jsonl` under package = 0) |
| dual rebuild SourceData entity_roles | **IDEMPOTENT** |
| validate | OK |
| U+2028 LF-only contract tests | covered in unit suite |

## Corpus hashes (lineage)

| Stage | records_sha256 | Notes |
|-------|----------------|-------|
| C1 initial | `14638a55e96d7dd458d312774b7b1e93072383eedf5e70147d2991eb4a7b342c` | first C1 content |
| C1 use-decision | `0fe9c1190b10b49b8b2cd60fe32e7718f5041fda58858d79225e9c1831642fe2` | granular licence + eval fail-closed |
| Counts | train 60266 / val 8201 / test 6696 / excl 0 | unchanged across both |

Post-merge dual rebuild reproduced **use-decision** hash before any schema_v0.2 transform bump.

## Explicit status

```text
SOURCE_DATA_DOCUMENT_LEVEL_LEAKAGE: UNVERIFIED
READY_FOR_B0: CANDIDATE
READY_FOR_B0_GO: BLOCKED

partition_origin: UPSTREAM_SOURCEDATA
partition_preserved: true
ntruth_partition_approved: false
model_use_status: BLOCKED

C1_1_SOURCEDATA_DOCUMENT_PROVENANCE: REQUIRED
```

Leakage audit at post-merge:

```text
groups_crossing_splits: 0
leakage_group_granularity: RECORD_LEVEL_FALLBACK
document_id_present: 0
document_id_missing: 75163
unique_leakage_groups: 75163
```

## External attestation copy

Full command log also on the data volume:

`/Volumes/FLASH128/N-Truth-Datasets/reports/workstream_c/pr3_post_merge_attestation.md`
