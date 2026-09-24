# Workspace reliability implementation plan

**Goal:** Implement the four improvement areas approved in chat: durable workspace, usable D0 editing, canonical Reality Gate presentation, and engineering checks.

**Architecture:** Keep scientific computations in Python. Extract persistence and UI validation into focused modules; persist input drafts, never promote restored results into canonical evidence. Preserve existing public endpoints and checkpoint compatibility.

**Tech stack:** React 19, TypeScript, Vitest/Testing Library, Python 3.12, pytest, mypy.

**Spec:** User-approved analysis and scope in this session (2026-09-11).

## Constraints
- No new runtime dependencies, network services, training runs or scientific gate changes.
- Preserve Italian/English controls and keyboard accessibility.
- Keep changes in the requested working copy; no commit or publication requested.

## 1. Persistence
- [ ] Add regression tests for immediate pagehide flush, corrupt drafts and unavailable storage.
- [ ] Extract lifecycle autosave hook from App; capture latest committed state, clean up all event listeners and expose save failure.
- [ ] Persist and validate D0 draft, sample rows, step and experiment ID; restore input only; ensure close-project clears state.
- [ ] Verify `npm test -- --reporter=dot` and `npm run build`.

## 2. D0 editing
- [ ] Reproduce ID-edit focus loss, delete/add duplicate identifiers and static source ranges.
- [ ] Extract row helpers and validation presentation into focused D0 modules.
- [ ] Add unique row creation, stable editing identity, dynamic source locators and field-linked actionable errors.
- [ ] Verify D0 regression tests including keyboard focus and adding/removing rows.

## 3. Reality Gate
- [ ] Test malformed ledger rejection and PRESENT-but-unsatisfied values, including strict boolean/integer distinction.
- [ ] Extract request transport and gate response validator from api.ts while preserving its exports.
- [ ] Fix gate card semantics, unloaded/error states and integrate in home.
- [ ] Verify card and API tests, then desktop build.

## 4. Python verification
- [ ] Reproduce mypy errors; use distinct variables for v8 dimensions and v9 predicates.
- [ ] Diagnose slow pytest execution with named test output and stack traces; change code only for demonstrated causes.
- [ ] Verify mypy, lint, formatting, relevant CLI and full Python tests with appropriate timeout.

## 5. Integration
- [ ] Review diffs for lifecycle races, invalid restore data, canonical-state confusion and accessibility.
- [ ] Run desktop suite/build, Python gates and contract/traceability checks.
- [ ] Document actual outcomes and remaining external scientific blockers without converting software checks into scientific validation.
