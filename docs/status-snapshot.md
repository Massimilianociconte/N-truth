# N-Truth — verified project status snapshot (clean checkout)

**Document role:** human-readable status of the **clean checkout** (`origin/main` lineage
and approved integration branches).
**Does not claim** scientific validation, gold corpora, NC3Rs/DRIVER endorsement, or
model promotion.
**Current specification:** PRD v7.0 (scientific). v6.1 remains historical.
**Verified (root-alignment branch work):** 2026-08-03.
**Scientific validation:** **`NOT_STARTED`**.

## Capability ladder (do not collapse)

| Level | Meaning for N-Truth today |
|-------|---------------------------|
| Designed | PRD / ADRs / protocols describe the target |
| Implemented | Code paths exist in the clean checkout |
| Tested | Automated software tests exercise contracts |
| Runtime-verified | Artifact-bound host qualification for a **registered fingerprint** |
| Evaluated on development | Development-only eval artefacts — not final test, not train |
| Validated on real gold | Independent real annotated gold — **not available** |
| Scientifically validated | External challenge / approved protocols — **`NOT_STARTED`** |
| Production-ready | **Not claimed** |

## Reality Gate (PRD v7 §0.7) — three independent dimensions

Clean-checkout expected top-level state (fail-closed; UNKNOWN blocks):

| Dimension | Status | Notes |
|-----------|--------|-------|
| `engineering_readiness` | `PARTIAL_OR_VERIFIED_BY_COMPONENT` | Contracts and unit tests present; real-case schema stability unmeasured |
| `data_readiness` | **`BLOCKED`** | No real anchor, licence scope incomplete (BLK-DATA-001), no protected split frozen |
| `scientific_validation` | **`NOT_STARTED`** | No independent external challenge closed |
| Substantive training | **`HOLD_PENDING_REAL_ANCHOR`** | ModernBERT / Granite promotion remain **HOLD** |
| AI claims | **not allowed** | Public corpora, SYN-G1 and engineering smoke do not satisfy real-anchor predicates |

Machine-readable implementation: `packages/ntruth/reality_gate/`.
Appendix AA is **non-normative**; do not treat it as implementation truth without
repository verification.

## Clean-checkout drift warnings

The following artefacts are **absent** from a clean checkout of `origin/main` and must
**not** be cited as repository contents:

- `models/registry/default.json`
- `models/registry/training_program.json`
- `models/ntruth-granite-3b/`
- FLASH128-only datasets and private trees

Historical documentation that references those paths describes **local or uncommitted**
worktrees, not clean-checkout truth. Granite/MLX runtime claims that exist only on
unmerged local branches are **not** promoted by this document.

## Determinability contracts

| Contract | Clean-checkout status |
|----------|------------------------|
| Legacy `Determinability` in `schemas/core.py` | **4 states** (v3 compatibility) |
| PRD v7 `DeterminabilityStateV7` | **8 states** in `schemas/determinability_v7.py` (additive) |
| Permitted/forbidden outputs (App. M) | Implemented as tables + tests |
| Derive-then-review | `graph/determinability_v7.derive_determinability_v7` (conservative) |

README and older docs that said “seven states” while only the v3 enum existed were
**documentation drift**; v7 adds the full normative enum without rewriting v3 reports.

## Neuro-symbolic architecture (normative)

```text
experimental documents
  → AI parser (candidate facts only)
  → candidate evidence / entities / relations / graphs
  → human review or confirmation when required
  → Experiment Graph
  → deterministic rules engine
  → conditional derivations + rule/premise trace
```

The model **must not** emit final: independent `n`, scientific/pseudoreplication
verdicts, free-form `RuleResult`, or final `DeterminabilityState`.

## PRD v7 root contracts present in this checkout

| Area | Module(s) | Status |
|------|-----------|--------|
| Bootstrap Core | `schemas/bootstrap_core.py` | Implemented (additive) |
| Causal Design Context + 4 independences | `schemas/causal_context.py` | Implemented (descriptive; no causal engine) |
| Authority / conflict | `schemas/authority.py` | Implemented (append-only) |
| Counts + aliases | `schemas/counts.py` | Implemented |
| Relations registry 0.2.0 | `schemas/relations.py` | Implemented (`acquired_from` etc.) |
| ConditionRecord / Value of Abstention | `abstention/` | Implemented |
| Reality Gate | `reality_gate/` | Implemented (fail-closed) |
| Quick Design (`simple_cell_culture`) | `quick_design/` + CLI | Vertical slice (no large UI) |
| MVT-A contracts only | `mvt_a/` | Contracts/harness only — **no train/download** |
| Cross-domain roles | `cross_domain/` | Implemented (fail-closed) |
| Complexity / burden | `complexity/` | Structures only; no hard-coded IAA/hours |

## What this snapshot does **not** claim

- Production readiness or scientific validation
- Gold N-Truth corpus or externally validated performance
- That Granite or ModernBERT is trained, promoted or scientifically ready
- That synthetic data satisfies real-anchor or scientific-validation predicates
- NC3Rs / DRIVER endorsement or formal partnership
- Resolution of open scientific errata (BLK-SCIENTIFIC-001…004)

## Authority order

1. PRD v7.0 normative requirements (after internal-consistency / errata review)
2. Verified assessment (explanatory only)
3. Approved scientific rules / ADRs
4. Clean-checkout code and tests
5. Historical documentation
6. Local or uncommitted claims

Audit artefacts: [docs/audits/prd-v7-root-alignment/](audits/prd-v7-root-alignment/).
