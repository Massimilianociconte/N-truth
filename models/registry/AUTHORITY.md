# Qualification authority model (cluster 2)

Three artifacts, **one hierarchy**. None may be edited independently without
fail-closed verification.

```yaml
operational_qualification_ledger:
  format: SQLite
  path: models/registry/qualification_ledger.sqlite3
  role: append-only local event ledger for new transitions on a developer host
  git_tracked: false
  authority: operational_during_local_append_only

published_qualification_snapshot:
  format: canonical JSONL hash chain
  path: models/registry/qualification_chain.jsonl
  companion: models/registry/qualification_chain.manifest.json
  evidence: models/registry/public_evidence/
  role: repository-verifiable signed-off export of the qualification history
  git_tracked: true
  authority: published_source_of_truth_for_clones

registry_mirror:
  file: models/registry/default.json
  role: current derived state (factory_default_provider, provisional primary, statuses)
  note: "default registry record — not 'default model'"
  git_tracked: true
  authority: derived_view_must_match_published_snapshot
```

## Rules

1. **Published checkout:** `qualification_chain.jsonl` (+ evidence + tip manifest)
   is the **only** authority for the claim `PARTIALLY_VERIFIED` in Git.
2. **Local append:** optional SQLite may record new events while producing a new
   published export; until export is reviewed and committed, the Git claim does
   not change.
3. **`default.json`:** mirror of current derived state. Must not disagree with
   the published chain tip (verified by `load_registry` / `verify_public_chain`).
4. **Never** call both SQLite and JSONL “source of truth” without this split.
5. **Scientific validation** is independent and remains `NOT_STARTED` unless a
   separate, reviewed scientific process advances it.

## Factory default vs provisional primary

```yaml
factory_default_provider: legacy_qwen          # operational factory default
provisional_primary_model_id: ibm-granite/...  # architectural intent only
```

`default.json` means **default registry record**, not “Granite is the default backend”.
