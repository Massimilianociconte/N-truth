# C2 design only — PreClinIE → routing + method_indicators (PRD v7 aligned)

**Status:** DESIGN_ONLY — not implemented
**Namespace:** contributes to **LEGACY_WS_C** engineering; may feed **V7_WS_C** silver once audited
**Proposed branch:** `feat/preclinie-routing-method-indicators-v1`
**Authority:** `AUXILIARY` only (cross-domain relative to bootstrap **in vitro** profile)
**Training:** fail-closed until licence use decision grants development/training
**Reality Gate:** engineering adapter ≠ scientific validation

## Allowed task semantics (PRD v7)

```text
ROUTING
REPORTED_METHOD_INDICATOR
EVIDENCE_SPAN_CANDIDATE
```

### Routing labels

```text
METHODS
STATISTICAL_METHODS
RESULTS
OTHER
UNKNOWN
```

Do **not** invent `FIGURE_CAPTION` unless upstream PreClinIE structure supports it
consistently and machine-checkably.

### Method / assertion semantics

A reported statement such as “animals were randomly allocated” is at most:

```text
AUTHOR_ASSERTION
REPORTED_METHOD_INDICATOR
EVIDENCE_SPAN_CANDIDATE
```

It is **not** automatically:

```text
confirmed assignment mechanism
confirmed randomisation unit
allocation_gold
experimental_unit_gold
biological_source independence
comparability proof
no-interference proof
interference_gold
estimand_gold
pseudoreplication_verdict_gold
```

## Cross-domain note (PRD §14.4)

PreClinIE is **cross-domain** relative to the initial in vitro Bootstrap Core profile.
It remains AUXILIARY unless a later **profile-specific** protocol assigns another role.
It cannot validate N-Truth v1.0-A in vitro by itself.

## Forbidden inferences

- experimental unit identity as gold
- allocation level / randomisation unit as confirmed fact
- biological independence / no-interference as proven
- estimand or exchangeability as AI labels

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

## Proposed files (future implementation)

```text
packages/ntruth/task_corpora/adapters/preclinie_routing.py
packages/ntruth/task_corpora/adapters/preclinie_method_indicators.py
packages/ntruth/task_corpora/label_maps/preclinie_routing.json
packages/ntruth/task_corpora/label_maps/preclinie_method_indicators.json
packages/ntruth/task_corpora/license_decisions/preclinie.json
tests/unit/task_corpora/test_preclinie_*.py
docs/task_corpora/preclinie-*-label-map.md
```

External outputs only under `NTRUTH_DATA_ROOT/task_corpora/{routing,method_indicators}/preclinie/`.

## Acceptance sketch (future)

- LF-only JSONL + shared `records_content_sha256`
- `groups_crossing_splits` audited
- synthetic_fraction = 0.0 until mixture-search approval
- NO_CORPUS in git
- dual-run idempotence
- tests: AUTHOR_ASSERTION never maps to experimental_unit_gold
