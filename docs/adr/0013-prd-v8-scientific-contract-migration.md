# ADR-0013 — PRD v8 scientific-contract migration

**Status:** accepted for implementation  
**Date:** 2026-08-08  
**Base:** `origin/main@fe089eff42c16e3fa55606be340c85df57c5442b`

## Context

Current main is an engineering-stable v7-era implementation, but the PRD v8 contract changes
the scientific architecture: facts and theory precede claims; determinability is claim-specific;
design adequacy is independent; open-world state is explicit; counts and timing are scoped; and
parser output is candidate-only. A previous divergent v8 worktree is dirty and cannot support
clean-checkout truth.

## Decision

1. The full PRD v8 is authoritative and Appendix AE is used only as a migration map.
2. The migration is implemented from the clean `origin/main` worktree on
   `codex/prd-v8-full-migration-20260808`; no historical dirty worktree is modified.
3. Raw evidence, graph history, human events and audited historical artifacts are immutable.
   v8 outputs are re-derived under explicit theory/rule/profile/support-policy versions.
4. v7 compatibility is input-only or a read-only projection, with a structured migration
   result and deprecation evidence. Incompatible v7 behavior is not retained merely to keep
   old tests green.
5. Scientific rules are sourced by Derivation Theory clauses. Rulebook code declares and is
   tested for conformance; it never becomes theory by implementation accident.
6. Internal PRD ambiguity is represented by `SCIENTIFIC_REVIEW_REQUIRED` and a register entry.
   No unreviewed vocabulary mapping, aggregation precedence or numerical threshold is added.
7. The parser produces candidates only. The deterministic verifier/theory layer owns counts,
   EU, determinability, adequacy and report resolution.
8. Science/data readiness stays blocked. This migration runs no training, model download,
   acquisition or external-volume mutation.

## Consequences

- Existing v7 callers receive explicit migration failures or deprecation warnings where a safe
  semantic mapping is unavailable.
- The report and UI lose positive/green determinability semantics and active statistical
  strategy suggestions.
- Release/training gates become stricter even though the pre-migration suite is green.
- A repository-only completion can be `IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`, not scientific
  validation.

## Evidence and review trigger

The pre-implementation evidence is in
`docs/audits/prd-v8-full-migration/REQUIREMENT_TRACEABILITY_MATRIX.md`. Revisit this ADR only
through a superseding ADR after closure of affected entries in
`SCIENTIFIC_REVIEW_REGISTER.md`; never rewrite this record retroactively.
