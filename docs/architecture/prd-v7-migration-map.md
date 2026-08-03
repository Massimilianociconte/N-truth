# PRD v7 Root Migration Map

**Document ID:** MIG-PRDV7-ROOT-001 · **Date:** 2026-08-03
**Scope:** how the clean-checkout codebase migrates from the v3/v6.1-era contracts to PRD
v7.0 contracts without destroying valid v6.1 engineering.

## 1. Module layout for v7 contracts

New packages (all deterministic, no ML, no network):

```text
packages/ntruth/
  schemas/
    bootstrap_core.py     # Bootstrap Core record v7 (§8.2A, App. X.1)
    causal_context.py     # Causal Design Context (§2.4, App. Y)
    authority.py          # AuthorityType, ConfirmationEvent, ConflictRecord (§0.4, §8.6)
    counts.py             # v7 canonical count kinds + alias migration (§7.9, §15.10)
    determinability_v7.py # 7-state DeterminabilityState + permitted outputs (§10.2, App. M)
    relations.py          # canonical relation registry v0.2.1 + aliases (§8.5)
  reality_gate/
    predicates.py         # tri-state/quad-state predicates (§0.7)
    gate.py               # dimension evaluation + fail-closed composition
    report.py             # machine-readable result + human blocker report
  abstention/
    condition_record.py   # ConditionRecord bilingual (§10.8)
    value_of_abstention.py# 11-element contract (§6.4, §23.2)
  quick_design/
    session.py            # simple_cell_culture vertical slice (§6.1)
    templates.py          # Methods draft, ID convention, sample sheet
    export.py             # biostatistician export + plan freeze
  mvt_a/
    stage_schema.py       # candidate-only stage schema + forbidden finals
    verifier.py           # hard verifier hook
    revision.py           # human revision patch, burden, false-certainty
    benchmark.py          # benchmark manifest contract
  cross_domain/
    roles.py              # profile-relative data role policy (§14.4, §16.7)
  complexity/
    tiers.py              # SIMPLE/MODERATE/COMPLEX/OUT_OF_PROFILE + burden metrics
```

## 2. Migration policy

1. **Additive first.** v7 types live in new modules; legacy v3/v6.1 types remain importable
   and keep their tests. Nothing is deleted in this migration.
2. **Explicit alias tables.** Every renamed enum value or relation gets a documented alias
   (`relations.ALIASES`, `counts.COUNT_KIND_ALIASES`, determinability state map). Input
   accepts legacy spellings; canonical output uses v7 spelling.
3. **No silent semantic promotion.** Parser output stays candidate-only; v7 types never
   accept a model-derived `independent_n` or final determinability.
4. **Fail-closed gates.** Reality Gate predicates default to UNKNOWN, and UNKNOWN blocks.
5. **Versioned schemas.** Each v7 contract carries a literal schema version string and a
   `schema_version` field so records can be migrated forward deterministically.

## 3. Determinability migration (v3 → v7)

| v3 state (`schemas/core.py`) | v7 state (§10.2) | Migration |
|------------------------------|------------------|-----------|
| `DETERMINATE` | `DETERMINATE` | direct |
| `MULTIPLE_PLAUSIBLE_GRAPHS` | `MULTIPLE_PLAUSIBLE_GRAPHS` | direct |
| `INDETERMINATE` | `INSUFFICIENT_INFORMATION` | alias; records keep readable history |
| `CONFLICTING_INFORMATION` | `CONFLICTING_INFORMATION` | direct |
| — | `CONDITIONALLY_DETERMINATE` | new (v3 expressed this via ConditionalScenario) |
| — | `INVALID_GRAPH` | new |
| — | `OUT_OF_SCOPE` | new |

Permitted-output table (App. M) is enforced by `determinability_v7.allowed_outputs`.

## 4. Relation registry migration (v0.1.0 → v0.2.1)

Added: `acquired_from`, `observed_in`, `aggregated_to`, `exposed_with`,
`may_interfere_with`, `supports`/`contradicts` evidence relations (already present as
`SUPPORTS`/`CONTRADICTS`; re-registered with evidence semantics).
Aliases: legacy `aggregated_by` remains accepted on input; canonical direction documented.

## 5. Count kind migration

Canonical v7 kinds: `declared_n`, `planned_n`, `allocated_n`, `treated_n`, `observed_n`,
`excluded_n`, `n_analyzed`, `observational_n`, `analytical_n`, `independent_n`,
`experimental_unit_count_candidate`, `experimental_unit_count`, `biological_source_count`,
`effective_n` (diagnostic-only).
Alias: `analysed` → `analyzed` (see ERRATA E-10). `effective_n` is emitted only in a
diagnostic section and can never repair design replication (statistical-washing ban).

## 6. Workstream naming migration

See [docs/audits/prd-v7-root-alignment/LEGACY_WORKSTREAM_MAPPING.md](../audits/prd-v7-root-alignment/LEGACY_WORKSTREAM_MAPPING.md).

## 7. Documentation truth sync

After code/tests exist, Phase 13 updates README/status docs to:
- name PRD v7.0 as the current specification (v6.1 historical);
- report Reality Gate state by dimension;
- remove claims backed only by uncommitted local artifacts;
- record reference PDF checksums without committing the PDFs.


## Reference PDF checksums (not committed unless policy allows)

- PRD v7.0 SHA-256: `00b544f04796f73f75e859c4cbff0ba4193a314661d50d5258d4bc9b0a13369f`
- Qwen assessment v1.0 SHA-256: `6dab65698d5e098b41e766f956118890958c4bfd3676442b62ee974a82820efc`

PDFs live under the main project `prd/` tree and are not required inside this clean
worktree to run contracts or tests.
