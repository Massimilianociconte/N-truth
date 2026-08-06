# ADR-0013 — SourceData provenance: exporter-aligned full-unit hybrid (Method C candidate)

**Status:** accepted (human design decision, 2026-08-06)
**Decision type:** project-level engineering/scientific design decision
**Supersedes:** none (records the outcome of the PR #9 method reconciliation
and exporter-lineage adjudication, 2026-08-06)

## Context

The SourceData v2.0.3 provenance reconciliation (PR #9) compared two
algorithms over one locked immutable input bundle:

- **Method A** — the sidecar v0.2.0 algorithm: caption text projected by
  substituting each `sd-tag` wrapper with its `text` ATTRIBUTE; upstream
  index of PANEL units plus panel-less FIGURE units.
- **Method B** — the portfolio C1.1 investigation algorithm: caption text
  projected by plain `itertext()`; upstream index of explicit panels only.

Two independent adjudications closed the scientific questions:

1. **Exporter lineage** (official `source-data/soda-data` generation code):
   the locked `token_classification` `text` field is, by construction, the
   `cleanup()`-normalized plain-itertext projection of the sd-panel.
   Attributes are never read by the exporter. Outcome:
   `EXPORTER_LINEAGE_SUPPORTS_METHOD_B`.
2. **Method reconciliation** (75,163 canonical records, dual-run
   byte-deterministic): Method B's label-independent core reproduced with
   zero identifier conflicts; every Method A fallback record explained;
   outcome `METHOD_B_LABEL_INDEPENDENT_REPRODUCED_ZERO_IDENTIFIER_CONFLICTS`.

However, Method B's historical implementation indexed only the 75,232
explicit `sd-panel` units, while the measured official XML structural
universe is:

```text
explicit_sd_panels:                     75232
panel_less_figures:                      2456
complete_matchable_structural_units:    77688
```

Method A had correctly indexed all 77,688 units. Adopting historical
Method B as-is would therefore silently drop the panel-less figure units.

## Decision

Record the following statuses and the future production-provenance
candidate architecture.

```text
EXPORTER_TEXT_PROJECTION:
  METHOD_B_ITER_TEXT
  AUTHORITATIVE_FOR_FUTURE_PROVENANCE

PROVENANCE_ALGORITHM_CANDIDATE:
  EXPORTER_ALIGNED_FULL_UNIT_HYBRID
```

Principles of `EXPORTER_ALIGNED_FULL_UNIT_HYBRID`:

```text
text_projection:
  official exporter-aligned itertext

upstream_unit_universe:
  explicit PANEL units
  plus panel-less FIGURE units

structural_granularity:
  PANEL
  FIGURE
  ARTICLE
  RECORD_FALLBACK

matching:
  deterministic
  label-independent
  fail-closed

fuzzy_matching:
  forbidden

first_match:
  forbidden

S4_label_assisted_provenance:
  NON_PRODUCTION

ambiguous provenance:
  retain lower trustworthy granularity or fallback
```

Method A status:

```text
METHOD_A_TEXT_PROJECTION:
  NOT_EXPORTER_AUTHORITATIVE

METHOD_A_STRUCTURAL_UNIT_MODEL:
  RETAINS_VALID_PANEL_AND_FIGURE_DISTINCTION

SIDECAR_V0_2_0:
  FROZEN_HISTORICAL_BASELINE
```

Sidecar v0.2.0 (SHA-256
`7cfba6f9f1a49ee5434c60a8510a7e6702e16849666b081323eee9a1894a041a`) is NOT
corrupt or invalid: it is a deterministic, audited historical baseline whose
text-projection method is no longer preferred for future provenance
reconstruction. Its attestations are never deleted or rewritten.

Method B status:

```text
METHOD_B_TEXT_PROJECTION:
  EXPORTER_LINEAGE_SUPPORTED

METHOD_B_LABEL_INDEPENDENT_RESULTS:
  REPRODUCED_WITH_ZERO_IDENTIFIER_CONFLICTS

METHOD_B_ORIGINAL_UNIT_UNIVERSE:
  INCOMPLETE_FOR_PANELLESS_FIGURE_UNITS

METHOD_B_LABEL_ASSISTED_S4:
  PARTIAL_NOT_HISTORICALLY_REPRODUCIBLE
  NON_PRODUCTION
```

The historical S4 = 14 is NOT described as reproduced. The current
reproducible S4 count is 3; the frozen C1.1 document does not preserve the
original tuple serialisation, so the original 14 cannot be recovered without
the original (never-committed) code.

## Alternatives considered

1. **Adopt historical Method B unchanged** — rejected: correct text
   projection but incomplete unit universe (drops 2,456 panel-less figure
   units).
2. **Keep Method A as final** — rejected: its text projection is not the
   one the official exporter published.
3. **Hybrid (this decision)** — exporter-aligned itertext projection +
   Method A's PANEL/FIGURE structural universe + fail-closed ambiguity;
   keeps every measured property of both methods and discards only what the
   exporter lineage disproved.

## Evidence

- Official-source investigation:
  `docs/task_corpora/sourcedata-exporter-lineage-adjudication-2026-08-06.md`
  (outcome `EXPORTER_LINEAGE_SUPPORTS_METHOD_B`, 7-entry source-record
  table).
- Reconciliation:
  `docs/task_corpora/sourcedata-provenance-method-reconciliation-2026-08-06.md`
  (75,163 delta rows; IDENTICAL 74,026 / METHOD_B_ONLY 1,090 /
  SAME_ARTICLE_DIFFERENT_GRANULARITY 46 / BOTH_FALLBACK 1 / conflicts 0;
  dual-run byte-identical, 24 attested artifacts).
- Adjudication policy 1.0.0, SHA-256
  `e9d09ad6e779953fe510bd4f85392632894b5b1c4869865e718f66868def529b`.

## Limits and consequences

- This ADR does NOT calculate final v0.3 counts and does NOT implement the
  candidate algorithm. A v0.3 sidecar does not exist.
- No sidecar is regenerated; v0.2.0 remains the authoritative external
  artifact until a separately authorised v0.3 build.
- Canonical JSONL (records SHA-256
  `562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10`), the
  external manifest (SHA-256
  `31d4fb939e086726b95b20f998e52756dad4153b62965d02b00f7125176e2ee6`) and
  the sidecar are frozen; no readiness hold is lifted by this decision.
- Label-assisted (S4) evidence remains NON_PRODUCTION and never promotes
  leakage claims, split statements, model-use decisions or production
  provenance.

## Dates

- Decision date: 2026-08-06 (human design decision recorded via PR #9 final
  gate authorisation).
- Revision trigger: a separately authorised "SourceData Provenance v0.3 —
  EXPORTER_ALIGNED_FULL_UNIT_HYBRID" implementation task, whose output must
  pass the same fail-closed adjudication policy before any sidecar
  replacement is considered.
