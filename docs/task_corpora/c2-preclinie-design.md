# C2 design only — PreClinIE → routing + method_indicators

**Status:** DESIGN_ONLY — do not implement until PR #3 is closed
**Proposed branch:** `feat/preclinie-routing-method-indicators-v1`
**Authority:** `AUXILIARY` only
**Training:** fail-closed until licence use decision grants development/training

## Scope

| Task | Source | Notes |
|------|--------|-------|
| `routing` | PreClinIE segments / structure | Section-level labels |
| `method_indicators` | PreClinIE method statements | Textual evidence spans |

### Routing labels (initial)

```text
METHODS
STATISTICAL_METHODS
RESULTS
OTHER
UNKNOWN
```

Do **not** invent `FIGURE_CAPTION` from PreClinIE unless the source structure
actually distinguishes captions in a consistent, machine-checkable way.

### Method indicators semantics

```text
AUTHOR_ASSERTION / REPORTED_METHOD_INDICATOR
≠
CONFIRMED_ALLOCATION / CONFIRMED_RANDOMIZATION
≠
experimental_unit_gold / independent_n_gold / biological_independence_gold
```

Example: “animals were randomly allocated” may yield a reported-method evidence
span. It must **not** auto-assert which entity was randomized or that the
procedure occurred as described.

## Forbidden inferences

- experimental unit identity
- allocation level
- biological independence
- pseudoreplication verdict gold

## Licence

Same machine-readable decision shape as SourceData. PreClinIE snapshot must have:

```yaml
adapter_build_allowed: ...
local_format_validation_allowed: ...
development_allowed: false | true | unknown
training_allowed: false
evaluation_allowed: unknown | ...
```

Unknown permissions fail closed. No model download or training in C2.

## Acceptance sketch (future)

- LF-only JSONL + shared `records_content_sha256`
- `groups_crossing_splits` audited
- synthetic_fraction = 0.0 until mixture-search approval
- NO_CORPUS in git
- dual-run idempotence
