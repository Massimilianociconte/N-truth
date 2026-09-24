# Requirements Traceability Matrix v0.1 (PRD v9, Appendix AP / FR-091)

Status: `v0.1` baseline covering **FR-001..FR-015** (PRD §21.1 Scientific
foundation) and **NFR-01..NFR-10** (PRD §22). This is the first slice of the
FR-091 "traceability coverage report": it does not yet cover all 91 functional
requirements; subsequent increments extend coverage row by row with the same
schema and checker.

Machine-readable source of truth: [`data/rtm-v0.1.csv`](../../data/rtm-v0.1.csv)
Validated by: [`scripts/check_rtm.py`](../../scripts/check_rtm.py)

## Columns (Appendix AP template + evidence note)

| Column | Semantics |
|---|---|
| `requirement_id` | `FR-###` or `NFR-##` exactly as numbered in PRD v9 §21/§22. |
| `source_prd_section` | PRD section number the requirement is defined in. |
| `schema_or_api` | Real repository path of the schema/API implementing the requirement, or the explicit marker `MISSING_EXPLICIT`. |
| `component` | Logical component owning the implementation (aligned with the current-to-target map). |
| `test` | Semicolon-separated real test paths, or `NONE_WITH_RATIONALE`. |
| `metric_gate` | The metric or gate that decides whether the requirement holds; never a prose aspiration. |
| `owner_role` | Role-style owner (`semantic-lead`, `security-engineer`, ...), never a personal name. |
| `status` | `PLANNED`, `PARTIAL` or `IMPLEMENTED`. |
| `evidence_note` | Free-text justification, gaps and cross-references. |

## Checker contract

`uv run python scripts/check_rtm.py` exits non-zero and prints JSON diagnostics
when any of the following fails:

- header is exactly the nine columns above;
- every field of every row is non-empty;
- requirement ids are well-formed and unique;
- `source_prd_section` is numeric (e.g. `21.1`, `22`);
- `status` is one of `PLANNED|PARTIAL|IMPLEMENTED`;
- `owner_role` is role-style (`^[a-z0-9][a-z0-9-]*$`);
- `schema_or_api` paths exist in the repository unless `MISSING_EXPLICIT`;
- `test` paths exist in the repository unless `NONE_WITH_RATIONALE`
  (the marker cannot be mixed with real paths);
- `IMPLEMENTED` rows must cite at least one existing test path.

Every normative requirement carries either at least one test or an explicit
rationale for why it is not automatically testable, per Appendix AP.

## Baseline snapshot (2026-08-26)

- 25 requirements tracked (15 FR + 10 NFR).
- 15 `IMPLEMENTED`, 7 `PARTIAL`, 3 `PLANNED`.
- Deliberate honest gaps: `ObservedEvidenceScope`/`TargetPopulationClaim`
  schemas (FR-009), parser resource quotas/quarantine (NFR-08) and a
  partial-success/no-silent-truncation contract (NFR-09) are `PLANNED` with
  `MISSING_EXPLICIT` markers rather than being presented as done.

## Expansion plan

1. Extend to FR-020..FR-027 (workflow), FR-030..FR-038 (ingestion),
   FR-040..FR-049 (parser AI) in the next increment.
2. Wire `scripts/check_rtm.py` into CI alongside
   `scripts/check_contract_packages.py`.
3. When the Reality Gate flag
   `requirements_traceability_complete_for_release_scope` (PRD §0.8) is
   evaluated, this matrix plus its checker output is the referenced evidence.
