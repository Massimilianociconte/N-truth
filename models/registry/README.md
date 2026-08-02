# Model registry (cluster 2)

This directory holds the **default registry record** and the **published
qualification snapshot**. It does **not** mean Granite is the factory default
backend.

## Authority hierarchy

See [AUTHORITY.md](AUTHORITY.md). Summary:

| Artifact | Role | Git |
|----------|------|-----|
| `qualification_chain.jsonl` + `public_evidence/` + tip manifest | **Published source of truth** for runtime qualification claims | tracked |
| `default.json` | **Derived mirror** of current statuses + model records | tracked |
| `qualification_ledger.sqlite3` | **Optional local** append-only operational ledger | **not** tracked |

## Fields in `default.json`

```yaml
factory_default_provider: legacy_qwen
provisional_primary_model_id: ibm-granite/granite-4.1-3b
qualification.runtime_qualification_status: PARTIALLY_VERIFIED  # exact fingerprint only
qualification.scientific_validation_status: NOT_STARTED
```

## Operations

### Verify published qualification (no weights, no re-qualification)

```bash
uv run python scripts/models/qualify_granite_runtime.py
# operation: VERIFY_PUBLISHED_QUALIFICATION
```

### Optional local weight integrity check (still not re-qualification)

```bash
uv run python scripts/models/qualify_granite_runtime.py --check-weights
```

### Run local qualification (weights + real backend)

Not part of the default CI path. A future command may produce new evidence and
propose a transition; publishing requires exporting a new JSONL snapshot and
updating the derived `default.json` in a reviewed commit.

## Scientific status

Runtime qualification is **not** scientific validation. Claim gates keep
`scientifically_releasable` false until external validation + runtime VERIFIED.
