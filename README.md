# N-Truth

[![CI](https://github.com/Massimilianociconte/N-truth/actions/workflows/ci.yml/badge.svg)](https://github.com/Massimilianociconte/N-truth/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Scientific status: HOLD](https://img.shields.io/badge/scientific_status-HOLD-orange.svg)](docs/status-snapshot.md)

N-Truth is local-first, human-in-the-loop research software for reconstructing
biological experimental designs as typed, evidence-linked graphs and deriving
query-scoped scientific claims through an inspectable deterministic theory lane.

The binding specification is **N-Truth PRD v8.0**. Appendix AE is a migration map;
the full PRD remains authoritative. PRD v7 is historical and is available only
through explicitly named `DEPRECATED_V7_ADAPTER` surfaces.

> **Current repository status: `IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`.** The v8
> engineering contracts are implemented and tested component by component. This is
> not scientific validation. Data readiness is `BLOCKED`, validation is
> `NOT_STARTED`, training is `HOLD`, and External Challenge use is `HOLD`. No real
> anchor, Derivation Gold, independent reference-stability result, scientific
> performance result or authorization to train is claimed.

## Scientific boundary

N-Truth separates facts from theory, theory from implementation rules, and every
scientific output from design approval:

```text
documents / wizard
    -> parser candidates only
    -> progressive deterministic verifier
    -> validated facts, events and canonical counts
    -> versioned Derivation Theory
    -> query-scoped DerivedClaimSet
    -> Theory-conformant Rulebook implementation
    -> neutral ReportBundle v8
```

Core invariants:

- `DETERMINATE` does **not** mean “good design”; determinability and
  `DesignAdequacyEvaluation` are independent axes.
- biological-source independence is not assignment independence and biological-source
  count is not experimental-unit count.
- assignment unit, application unit, effective exposure unit, analytical unit and
  measurement process are distinct.
- interference can change exposure/estimand support without automatically changing the
  experimental unit.
- timing is event-referenced; global timing shortcuts are legacy input only.
- scientific silence is not explicit absence. Scientific values use six-state
  `KnowledgeState` wrappers rather than ambiguous bare `null` or empty collections.
- every claim and count is scoped to an `InferentialQuery` and a versioned profile.
- the parser never predicts `n`, EU, determinability, adequacy or final rule verdicts.
- the statistical strategy module is `HANDOFF_ONLY`; no test or model is recommended.
- derived claims cannot be patched directly. A challenge changes reviewed facts/theory
  inputs and triggers re-derivation.

## Implemented engineering surface

| Area | Repository implementation | Scientific boundary |
|---|---|---|
| Core Semantic Kernel | Strict v8 schemas, `KnowledgeValue`, evidence/support axes, query-scoped claims | Vocabulary and profile ambiguities remain registered |
| Theory and Rulebook | Seven clause families, immutable assets, packaged conformance fixtures, reviewed code pins | Theory Reference Set and Derivation Gold remain unavailable |
| Deterministic runtime | Bundle-gated derivation, proof verification, exact graph equality, Canonical Count Registry | Partial graph scoring and some positive payload shapes remain review-blocked |
| Prospective/reporting | Immutable planned/executed records, reconciliation, neutral ReportBundle, JSON/YAML/HTML | Mixed-state aggregation remains fail-closed without reviewed policy |
| Parser/training boundary | Candidate-only parser, adjudicated Gold target, protected TEST/EXTERNAL splits, anonymous FD consumption | Training can never proceed while Reality Gate v8 is HOLD |
| Evaluation/governance | Report-level scoring contracts, residual audit, cluster-aware interfaces, contamination/custody records | No real reference/evaluation results are included |
| Reality Gate v8 | Six readiness dimensions, typed blockers, complete pin reconciliation, repository policy | Current authoritative decision is HOLD |
| Desktop | Guided, non-JSON v8 builder; separate axes; NON_EXHAUSTIVE and HANDOFF_ONLY visible | Synthetic fixtures are UI/conformance evidence, never scientific results |

The machine-readable component map is
[docs/architecture/prd-v8-current-to-target.yaml](docs/architecture/prd-v8-current-to-target.yaml).
The reconciled implementation status is in the
[final PRD v8 requirement matrix](docs/audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md);
the original clean-checkout matrix remains an immutable Phase 1 baseline. Open
scientific decisions are in the same
[audit directory](docs/audits/prd-v8-full-migration/).

## Explicit blockers

The append-only
[Scientific Review Register](docs/audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md)
is authoritative. Important open items include:

- incompatible `SupportGrade`, `DerivedClaim`, profile-coverage and published example
  spellings (`SRR-V8-001`–`SRR-V8-008`);
- count-vocabulary closure and graph partial scoring (`SRR-V8-011`, `SRR-V8-012`);
- no universal few-cluster threshold and no inferred report aggregation policy
  (`SRR-V8-013`, `SRR-V8-014`);
- source-class and interference-topology closure (`SRR-V8-015`, `SRR-V8-017`);
- Appendix AG is expected-negative (`SRR-V8-018`);
- external Theory Reference Set, Real Anchor, Derivation Gold, reference stability and
  residual evidence are absent (`SRR-V8-021`, `SRR-V8-022`);
- some positive determinability/challenge payload mappings remain blocked
  (`SRR-V8-023`, `SRR-V8-024`);
- the Quick Design question queue has no reviewed Theory priority/evidence-ordering
  asset, so ordering remains visibly unreviewed (`SRR-V8-025`).

No blocker is closed by passing software tests alone.

## Installation

Requirements: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and Node/pnpm only
for the desktop UI.

```bash
git clone https://github.com/Massimilianociconte/N-truth.git
cd N-truth
uv sync --extra dev --extra api --locked
uv run ntruth version
```

The deterministic core has no network requirement. The optional MLX lane is restricted
to Apple Silicon and is not authorized to download a model or train as part of normal
setup.

## Canonical v8 usage

The primary local workflow is the guided desktop form. It sends a typed draft to
`POST /v8/quick-design/build-submission`, shows the complete review queue and, only
after explicit confirmation, receives the canonical result from that same atomic
request. The user is not required to author or paste JSON.

For automation and expert inspection, the CLI accepts one strict
`QuickDesignV8Submission` JSON document. This is an explicit raw-author-asserted
surface, not evidence of guided confirmation:

```bash
uv run ntruth quick-design run ./quick-design-v8.json --out ./ntruth-out
```

The command writes content-addressed planned-design and ReportBundle v8 artifacts. A
raw legacy document analysis must be selected explicitly:

```bash
uv run ntruth analyze-v7 ./methods.md --out ./ntruth-v7-out \
  --acknowledge-unvalidated-domain
```

That surface emits `DEPRECATED_V7_ADAPTER`; it is not a canonical v8 result.

## Local API and desktop

```bash
pnpm --dir apps/desktop install --frozen-lockfile
pnpm --dir apps/desktop build
uv run ntruth-api
```

Open `http://127.0.0.1:8765/app/`. The server is loopback-only and unauthenticated;
never expose it on a LAN or the Internet.

Canonical routes:

- `POST /v8/quick-design/build-submission` — guided PREVIEW/CONFIRM; CONFIRM emits
  the canonical result atomically and the audit snapshot is not a reusable execution
  capability;
- `POST /v8/quick-design` — strict raw-author-asserted v8 compilation for expert
  automation;
- `POST /v1/analyze` — v8 fail-closed boundary for unsupported raw inputs;
- `POST /v7/analyze` and `POST /v7/quick-design` — explicit historical adapters;
- `GET /v1/health` — local service metadata.

For UI development, run `pnpm --dir apps/desktop dev`; Vite proxies `/v1`, `/v7`
and `/v8` to `127.0.0.1:8765`.

## Validation

Minimum clean-checkout gates:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run pytest --disable-warnings
uv run python scripts/check_prd_v8_contracts.py
uv run python scripts/check_repository_policy.py
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build
uv build
uv run python scripts/check_distribution.py
uv run python scripts/smoke_release.py
```

The PRD example registry deliberately preserves Appendices A, AF and AG as
expected-negative fixtures with exact `SRR-V8-*` diagnostics. Green CI must never
silently “repair” those authoritative source examples.

## Data, privacy and repository safety

- No raw corpus, private dataset, model weight, secret, credential or external
  challenge payload belongs in Git.
- `TEST` and `EXTERNAL_CHALLENGE` are never training- or model-selection-eligible.
- Repository policy is a bounded detection gate, not an attestation of privacy,
  licensing or absence of contamination.
- External data under `/Volumes/FLASH128` is outside this repository and is never
  modified by repository validation.
- Sharing and redistribution remain independently fail-closed.

## Documentation

- [Current clean-checkout status](docs/status-snapshot.md)
- [Architecture and invariants](docs/architettura.md)
- [Current-to-target architecture map](docs/architecture/prd-v8-current-to-target.yaml)
- [PRD v8 source reconciliation](docs/audits/prd-v8-full-migration/SOURCE_RECONCILIATION.md)
- [Final PRD v8 implementation matrix](docs/audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md)
- [Phase 1 clean-checkout matrix](docs/audits/prd-v8-full-migration/REQUIREMENT_TRACEABILITY_MATRIX.md)
- [Scientific Review Register](docs/audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md)
- [Public specification boundary](docs/public-specification-v0.1.md)
- [Contribution guide](CONTRIBUTING.md)
- [Governance](GOVERNANCE.md)
- [Release procedure](docs/releasing.md)
- [Security policy](SECURITY.md)

Historical v7 audit artifacts remain available under
[docs/audits/prd-v7-root-alignment/](docs/audits/prd-v7-root-alignment/) and are not
rewritten as v8 evidence.

## License and citation

Software is licensed under [Apache-2.0](LICENSE). Input documents, datasets and model
artifacts retain their own licenses and permissions; the software license never grants
rights over them. Citation metadata is in [CITATION.cff](CITATION.cff).
