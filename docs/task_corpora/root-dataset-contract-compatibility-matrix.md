# Root ↔ dataset contract compatibility matrix

**Baselines**

| Item | SHA |
|------|-----|
| Current main (branch base) | `a2afde309e6f529dcf5437c1b297bfbf130a0d05` |
| PR #6 root contract merge | `f2faace471788bdc4255e42fa88d5868f906e732` |
| Prior dataset checkpoint | `fcce7bc871e08bdbaf89621a5bcb5b48f386715e` |
| SourceData records_sha256 (verified) | `562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10` |

**Pass class:** root-to-dataset compatibility only. No reacquire, rebuild, training, or Lazic access.

## Classification legend

`DOC_ONLY` · `MANIFEST_ONLY` · `VALIDATOR_ONLY` · `SHARED_ENUM_IMPORT` ·
`RECORD_SCHEMA_CHANGE` · `RECORD_CONTENT_CHANGE`

## Matrix

| Concept | Root canonical | Dataset-side | Match | Migration | Class | Serialized records change? |
|---------|----------------|--------------|-------|-----------|-------|----------------------------|
| Engineering readiness | `EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT` | `VERIFIED_FOR_C0_C1` component string + projection map | Naming-only + detail | Project via `DatasetReadinessProjection` | SHARED_ENUM_IMPORT + MANIFEST_ONLY | **no** |
| Data readiness | `DataReadiness.BLOCKED` / `READY` | `data_readiness=BLOCKED` | Exact for current state | Fail-closed projection | SHARED_ENUM_IMPORT | **no** |
| Scientific validation | `ScientificValidation` + evidence | `NOT_STARTED` string | Exact for current state | Never set VALIDATED from silver | SHARED_ENUM_IMPORT | **no** |
| Reality Gate purpose | `GatePurpose` | Previously absent | Missing | Default `MVT_A_EXPLORATORY` in projection | SHARED_ENUM_IMPORT | **no** |
| GateValue | TRUE/FALSE/UNKNOWN/NOT_APPLICABLE | Mostly booleans + provisional strings | Partial | Use `GateValue` in projection fields | SHARED_ENUM_IMPORT | **no** |
| Reality Gate ref | root package | `provisional_dataset_manifest` | Deprecated | `reality_gate@commit:f2faace47178` on new manifests | MANIFEST_ONLY | **no** (manifest only) |
| Auxiliary/silver authority | N/A (profile roles) | `AuthorityLevel.AUXILIARY` | Compatible | Keep task-corpora enum; bans enforced | DOC_ONLY | **no** |
| Cross-domain roles | `DataRole`, `CrossDomainRoleDecision` | YAML `ROLE_DECISION_PENDING` | Parallel docs | Registry keeps pending; tests call root decision for policy | VALIDATOR_ONLY + DOC_ONLY | **no** |
| Training eligibility | Reality Gate + licences | `training_eligible` + `LicenseUseDecision` | Compatible fail-closed | Keep record validators | VALIDATOR_ONLY | **no** |
| Forbidden gold uses | product contract list | `FORBIDDEN_GOLD_USES` | Exact superset check | Assert superset of canonical list | VALIDATOR_ONLY | **no** |
| Annotation authority | `AnnotationAuthority` | free-form roles in YAML | Parallel | GOLD path uses root types in tests | DOC_ONLY | **no** |
| Evidence support level | `EvidenceSupportLevel` | not in TaskRecord body | N/A for silver tokens | No TaskRecord change | DOC_ONLY | **no** |
| Count kinds | `CountKind` | not in entity_roles payload | N/A | No TaskRecord change | DOC_ONLY | **no** |
| Relation registry | `V7Relation` / `CONTAINED_IN` | not in entity_roles payload | N/A | No TaskRecord change | DOC_ONLY | **no** |
| Leakage grouping | design guidance | `leakage_group` + `RECORD_LEVEL_FALLBACK` | Compatible | Explicit `paper_level_leakage_claim_allowed=false` | MANIFEST_ONLY | **no** |
| Split eligibility | protected split predicates | upstream partitions, `ntruth_partition_approved=false` | Compatible | Keep blocked | MANIFEST_ONLY | **no** |
| Licence / use | gate `LICENCE_SCOPE_VERIFIED` | `LicenseUseDecision` granular flags | Compatible fail-closed | Keep loaders | VALIDATOR_ONLY | **no** |
| ROLE_DECISION_PENDING | cross_domain UNDECIDED | Lazic YAML | Compatible | Never training/dev/eval | VALIDATOR_ONLY | **no** |
| MVT-A contracts | `packages/ntruth/mvt_a` | not used in task build | Separate | No coupling to parser/model | DOC_ONLY | **no** |

## Hash impact decision (record vs manifest)

```text
record_schema_change: false
record_content_change: false
manifest_schema_change: true
manifest_content_change: true
rebuild_jsonl_required: false
manifest_refresh_required: true
expected_records_sha256_change: false
```

| Layer | Version / hash | This PR |
|-------|----------------|---------|
| TaskRecord JSONL body | schema/transform **0.2.0** | **unchanged** |
| BuildManifest metadata | **0.2.2** (+ projection fields) | schema + content |
| SourceData `records_sha256` | `562b6ac9…` | **unchanged** |
| FLASH128 `manifest.json` | external checkpoint | **not modified in this PR** |

Rationale: readiness projection and `reality_gate@commit:f2faace47178` land in
BuildManifest / leakage_audit metadata only. TaskRecord JSONL checksum inputs are
unchanged, so **JSONL rebuild is not required**. After merge, a separate
**manifest-only refresh** on the external checkpoint must rewrite metadata,
re-verify JSONL byte-identity and `records_sha256`, and must **not** rewrite JSONL
files.

Full contract pin SHA: `f2faace471788bdc4255e42fa88d5868f906e732`.

If a future change modifies fields inside each JSONL line, reclassify as
`RECORD_CONTENT_CHANGE` and require a separate rebuild authorisation.
