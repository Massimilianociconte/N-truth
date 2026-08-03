# REPORT A — CLUSTER 3A Structured Decoding (final review)

**Stato sign-off:** `APPROVED`
**Data review:** 2026-08-03
**Branch:** `feat/structured-decoding-cluster3a`
**Commit candidato:** `64a160b`
**Base:** `fac3249` (ancestor verificato)

## Preflight

| Campo | Valore |
|---|---|
| Worktree | `.worktrees/cluster3a` |
| HEAD review | `64a160b` clean |
| Diff | 10 file, +2032/−24 vs fac3249 |
| Outlines (uv.lock) | **1.3.2** (extra `ml`, Darwin arm64) |
| mlx-lm | 0.31.3 |
| Registry/chain | **byte-identical** (vedi `file-hashes.json`) |
| Factory default | `legacy_qwen` |
| Runtime qualification | `PARTIALLY_VERIFIED` (invariato) |
| Scientific validation | `NOT_STARTED` (invariato) |
| scientifically_releasable | `false` |

## Contract review

`StructuredDecodeResult` espone: status, parsed, raw_output, schema_valid, truncated,
fallback_used, diagnostics, schema_name/version/status, backend/version, max_tokens,
terminated_by_eos/stop (None se non osservabili).

Stage 0.1.0 EXPERIMENTAL, `extra=forbid`, candidate-only:

- EvidenceExtractionResult
- EntityCountResult
- FactorEndpointResult
- CandidateRelationSet

Campi vietati bloccati (n / n_independent / verdict / RuleResult / determinability / …).

## Defect search

Nessun difetto di **codice** confermato:

- nessun import circolare
- nessun fallback free silenzioso
- validazione post-generazione obbligatoria sul path constrained
- normalizzazione allowlist-only
- nessun coupling B4/P0/training nel codice
- nessun tocco a registry/chain/default provider

Nit documentali (whitespace ADR / EOF test) corretti nel follow-up documentale.

## Partials interrotti

Vedi `interrupted-files-inventory.json`. Tutti i partial del main dirty tree sono stati
**DISCARDED_REWRITTEN** (non copiati alla cieca); SHA originari registrati.

## Test (detached clean @ 64a160b)

| Suite | Collected | Passed | Duration |
|---|---:|---:|---:|
| Cluster 3A constrained | 32 | 32 | ~1.43 s |
| Cluster 1 granite | 12 | 12 | ~0.53 s |
| Cluster 2 registry | 21 | 21 | ~0.62 s |
| tests/unit completa | 521 | 521 | ~2.36 s |

Comandi:

```text
uv run pytest tests/unit/test_constrained_decoding.py -q --tb=no
uv run pytest tests/unit/test_granite_backend_cluster1.py -q --tb=no
uv run pytest tests/unit/test_registry_cluster2.py tests/unit/test_registry_authority_and_verify.py -q --tb=no
uv run pytest tests/unit -q --tb=no
git diff --check fac3249..64a160b
```

Invarianti scriptate: free FREE_DECODE; structured fail-closed CONSTRAINED_UNAVAILABLE senza Outlines;
import senza Outlines eager; validation post-gen; registry byte-identical.

## Smoke reale

`ENGINEERING_INTEGRATION_SMOKE` su pesi locali
`/Users/massimilianociconte/Documents/N-truth/models/local/granite-4.1-3b-4bit`

| Campo | Valore |
|---|---|
| Status | `PASS_ENGINEERING_SYNTAX_ONLY` |
| Load | ~1040 ms |
| Generate constrained | ~2912 ms, `GENERATION_OK` |
| schema_valid | true |
| fallback_used | false |
| Unload | sì |
| Registry post-smoke | invariato |
| Claim | **solo sintassi**; nessuna transition di qualifica |

## Limiti residui

- Schemi EXPERIMENTAL 0.1.0 — non normativi scientifici
- Structured decoding ≠ verità / accuracy semantica
- PARTIALLY_VERIFIED non esteso al decoding profile
- MinimalCandidateGraphResult rinviato
- Factory default resta legacy_qwen; Granite non default
- Cluster 3B non aperto; no push/merge

## Commit

- Feature: `64a160b feat(model): add fail-closed structured decoding for Granite MLX`
- Documentary follow-ups: audit pack under `docs/audits/cluster3a-structured-decoding-20260803/`
- Branch tip at sign-off: `git rev-parse HEAD` on `feat/structured-decoding-cluster3a` (descendant of `64a160b`)

Log `fac3249..HEAD` at pack update (parent of this commit if dirty):

```
3cbb457 docs(audit): record final Cluster 3A tip in review pack
e92e5cc docs(audit): normalize Cluster 3A report trailing whitespace
4ceb5ae docs(audit): persist Cluster 3A structured decoding review pack
64a160b feat(model): add fail-closed structured decoding for Granite MLX
```

## Sign-off

**CLUSTER_3A_REVIEW: APPROVED**
