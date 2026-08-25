# Canonical JSONL framing contract (Workstream C)

**Normative.** Applies to all task corpora under `NTRUTH_DATA_ROOT/task_corpora/`.

```text
JSONL framing contract:
- records are separated exclusively by ASCII LF, byte 0x0A;
- CRLF may be normalised at ingestion boundaries if explicitly documented;
- Unicode line and paragraph separators, including U+2028 and U+2029, are
  preserved as record content;
- generic splitlines()-style parsing is prohibited for canonical JSONL;
- content digests are computed by one shared implementation.
```

## Implementation

| Concern | Module |
|---------|--------|
| Physical line iterator | `ntruth.task_corpora.io_util.iter_jsonl_physical_lines` |
| Content digest | `ntruth.task_corpora.io_util.records_content_sha256` |
| Writers | `ntruth.task_corpora.io_util.write_jsonl_records` (rejects raw CR/LF inside a record body) |

## Regression (SourceData)

Scientific tokens may embed U+2028 (e.g. “Student's” + U+2028 + “t-test”).
`str.splitlines()` inflates train line counts (60266 → 60318) and breaks
`records_sha256`. Unit tests under `tests/unit/task_corpora/` lock the contract.
