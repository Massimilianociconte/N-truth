# N-Truth clean-checkout status — PRD v8.0

**Verified scope:** repository engineering contracts, 2026-08-09.
**Binding specification:** **N-Truth PRD v8.0**.
**Repository implementation status:** **`IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`**.
**Scientific validation:** **`NOT_STARTED`**.
**Training and External Challenge:** **`HOLD`**.

This is a clean-checkout status document. It does not convert code, synthetic fixtures,
an AI review, a repository scan or green CI into scientific evidence.
The complete requirement-by-requirement disposition is the
[final PRD v8 implementation matrix](audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md);
the Phase 1 matrix is retained separately as immutable pre-implementation evidence.

## Capability ladder

| Level | Current evidence |
|---|---|
| Designed | PRD v8, ADR-0013 and explicit schemas/contracts |
| Implemented | v8 kernel, theory/runtime, parser boundary, reporting, evaluation and Gate code |
| Engineering-tested | Focused unit/integration/E2E/package tests and desktop build |
| Runtime-verified | Deterministic package/conformance assets only |
| Evaluated on independent real reference | **Not available** |
| Validated on real gold | **Not available** |
| Scientifically validated | **`NOT_STARTED`** |
| Production-ready scientific product | **Not claimed** |

## Reality Gate v8

The canonical gate is `packages/ntruth/reality_gate/v8.py`; the historical v7 gate is
available only through explicitly named `DEPRECATED_V7_ADAPTER` interfaces.

| Dimension | Status | Why |
|---|---|---|
| Kernel/schema conformance | Engineering evidence present | Runtime-derived schemas and strict validation exist |
| Theory/Rulebook conformance | Engineering evidence present | Versioned clause/rule/fixture/code pins are checked |
| Reference stability | **BLOCKED** | No reviewed Theory Reference Set or real stability result (`SRR-V8-021`, `SRR-V8-022`) |
| End-to-end evaluation | **BLOCKED** | Contracts exist; independent real ReportBundle evaluation does not |
| Contamination/custody | **BLOCKED** | Contracts exist; no qualifying external attestation is supplied |
| Data/training authorization | **HOLD** | TEST/EXTERNAL are protected and no authoritative GO decision exists |

The CLI command `uv run ntruth quick-design reality-gate` reports the canonical v8
HOLD. `reality-gate-v7` is historical and visibly deprecated.

## Engineering components

The machine-readable source of component truth is
[architecture/prd-v8-current-to-target.yaml](architecture/prd-v8-current-to-target.yaml).

| Component | Engineering status | Scientific note |
|---|---|---|
| Core Semantic Kernel / KnowledgeState | Implemented | Published schema ambiguities remain registered |
| Derivation Theory / Rulebook closure | Implemented with external blockers | Theory Reference Set and Derivation Gold absent |
| Query-scoped claims / count registry | Implemented with explicit blockers | Count/profile/payload mappings are not guessed |
| Parser candidate-only boundary | Implemented | Model output is never scientific authority |
| Planned/executed ReportBundle | Implemented | Mixed aggregation remains review-gated |
| Statistical module | `HANDOFF_ONLY` | No strategy recommendation or threshold |
| Evaluation/residual/cluster interfaces | Implemented as HOLD contracts | No fabricated benchmark result or gold |
| Contamination/custody | Implemented as fail-closed contracts | No self-issued challenge authorization |
| Reality Gate v8 | Implemented | Current decision remains HOLD |
| Desktop guided v8 builder and ReportBundle consumer | Implemented and engineering-tested | Synthetic fixture only; question ordering remains unreviewed |

## Current blockers

The append-only
[Scientific Review Register](audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md)
is authoritative. It records internal PRD conflicts, missing external evidence and
scientific choices that the implementation must not invent.

Important consequences:

- Appendices A, AF and AG are preserved as expected-negative fixtures.
- Profile predicate closure (`SRR-V8-008`) cannot be asserted from a scalar example.
- partial graph scoring (`SRR-V8-012`) and a universal few-cluster floor
  (`SRR-V8-013`) are unavailable.
- heterogeneous report-resolution precedence (`SRR-V8-014`) is fail-closed.
- unknown interference topology never rewrites EU (`SRR-V8-017`).
- Real Anchor, Derivation Gold, reference stability and residual evidence are absent
  (`SRR-V8-021`, `SRR-V8-022`).
- Quick Design preserves the full question queue, but no packaged Theory asset can
  yet claim a reviewed primary-question/evidence ordering (`SRR-V8-025`).

## Compatibility

PRD v7 contracts are historical. Compatibility is explicit and never the canonical
default:

- CLI: `analyze-v7`, `quick-design run-v7`, `reality-gate-v7`;
- API: `/v7/analyze`, `/v7/quick-design`;
- response marker: `DEPRECATED_V7_ADAPTER`.

Historical audits under [audits/prd-v7-root-alignment/](audits/prd-v7-root-alignment/)
are immutable records, not current implementation evidence.

## Reproducible truth gates

```bash
uv run python scripts/check_prd_v8_contracts.py
uv run python scripts/check_repository_policy.py
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run pytest --disable-warnings
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build
uv build
uv run python scripts/check_distribution.py
uv run python scripts/smoke_release.py
```

`check_repository_policy.py` reports findings over the tracked tree. A clean result is
`NO_FINDING_DETECTED_NOT_AN_ATTESTATION`; it is not proof of privacy, licensing or
absence of contamination.

## Final interpretation

The repository can claim an implemented PRD v8 engineering boundary with explicit
fail-closed blockers. It cannot claim completed scientific conformity, validated
performance, an authorized training run, a safe External Challenge release or
production readiness.
