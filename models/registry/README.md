# Model registry (cluster 2)

## Public source of truth

| Artifact | Role |
|----------|------|
| `default.json` | Registry schema + qualification summary |
| `qualification_chain.jsonl` | Append-only transition chain with hashes |
| `qualification_chain.manifest.json` | Tip hash + event count |
| `public_evidence/` | Content-addressed evidence blobs |

**Do not** treat a local `qualification_ledger.sqlite3` as the published proof.
SQLite may exist on a developer machine for append operations; the Git checkout
must remain verifiable via the JSONL chain alone.

## Factory default

`factory_default_provider` is **`legacy_qwen`**. Granite is the provisional
architectural primary and may be `PARTIALLY_VERIFIED` for an exact artifact without
being the operational default.

## Scientific status

Always independent from runtime. Published value: `NOT_STARTED`.
