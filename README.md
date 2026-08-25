# N-Truth

[![CI](https://github.com/Massimilianociconte/N-truth/actions/workflows/ci.yml/badge.svg)](https://github.com/Massimilianociconte/N-truth/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Scientific status: NOT STARTED](https://img.shields.io/badge/scientific_validation-NOT_STARTED-red.svg)](docs/status-snapshot.md)

N-Truth is local-first, human-in-the-loop research software for reconstructing
biological experimental designs as typed, evidence-linked graphs and deriving
query-scoped scientific claims through an inspectable deterministic theory lane.

The current programme is **N-Truth PRD v9.0**: five canonical Contract Packages
(`contracts/cp-sci|epi|data|eval|run.yaml`), a versioned evaluator/schema
registry pin (the evaluator artifact pins are engineering identity pins, never
scientific review evidence), Reality Gate fail-closed readiness dimensions, the
preregistered human/AI team evaluation protocol (H / A / H+A), and the
confidence / calibration / OOD machinery. The engineering substrate carries
v8-named kernel contracts extended with v9 sidecar semantics; PRD v7 remains
historical behind explicit `DEPRECATED_V7_ADAPTER` surfaces only.

> **Repository status (2026-08-25, baseline `integration/prd-v9-unified`):**
> `IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`. Scientific validation is **NOT_STARTED**,
> training execution is **HOLD_PENDING_REAL_ANCHOR**, gold data are **not yet
> annotated**, no custodied External Challenge corpus exists, and the
> driver→ARRIVE crosswalk snapshot still has its content hash pending first pin.
> Green CI proves software contracts only — never accuracy, human agreement or
> external validity.

## Scientific boundary

N-Truth separates facts from theory, theory from implementation rules, and every
scientific output from design approval:

```text
documents / wizard
    -> parser candidates only
    -> progressive deterministic verifier
    -> validated facts, events and canonical counts
    -> versioned Derivation Theory + FactorRole/ContrastType gates
    -> query-scoped DerivedClaimSet under SupportProfile
    -> Theory-conformant Rulebook implementation
    -> neutral ReportBundle with sentence/claim-level provenance
```

Core invariants:

- `DETERMINATE` does **not** mean "good design"; determinability and
  `DesignAdequacyEvaluation` are independent axes.
- biological-source independence is not assignment independence and biological-source
  count is not experimental-unit count.
- assignment unit, application unit, effective exposure unit, analytical unit and
  measurement process are distinct.
- interference can change exposure/estimand support without automatically renaming or
  elevating the experimental unit.
- scenario completeness is bounded by a declared, versioned assumption set:
  `EXHAUSTIVE_WITHIN_PROFILE` is no longer a writable claim (registry pin 0.1.2).
- scientific silence is not explicit absence: scientific values use six-state
  `KnowledgeState` wrappers rather than bare `null` or empty collections.
- every claim and count is scoped to an `InferentialQuery` and a versioned profile.
- model confidence is task-calibrated or explicitly `UNQUALIFIED`; OOD/profile shift
  triggers abstention (ADR-0016).
- the parser never predicts `n`, EU, determinability, adequacy or final rule verdicts.
- the statistical strategy module is `HANDOFF_ONLY`; no test or model is recommended.
- derived claims cannot be patched directly. A challenge changes reviewed facts/theory
  inputs and triggers re-derivation; challenge item-level feedback is prohibited while
  a version is ACTIVE (ADR-0017).

## What exists today (verified in-tree)

Verified by listing the repository at this commit — implemented and
engineering-tested components only. None of this is scientific validation.

| Area | In-tree modules |
|---|---|
| Core semantic kernel & schemas | `packages/ntruth/schemas/` (`kernel`, `knowledge`, `factor_role`, `material_lineage`, `count_registry`, `coverage` v9 assumption-set semantics), packaged asset `prd-v8-kernel-schemas-8.0.0.json` |
| Derivation theory & rules | `packages/ntruth/derivation_theory/`, `packages/ntruth/rules/`, `theories/ntruth-derivation-theory-0.1.0.json`, `theories/reviewed-evaluator-registry-0.1.2.json` |
| Graph & verifier | `packages/ntruth/graph/`, `packages/ntruth/verifier/`, deterministic pipeline (`pipeline.py`, `pipeline_v8.py`) |
| Extraction & ingest | `packages/ntruth/parsers/`, `extract/`, `ingest/` (MIME-aware, quarantine, safety), `ocr/` adapter contract |
| Prospective planning | `packages/ntruth/quick_design/` (v8 guided builder + `v9.py` FactorRole/ContrastType-first session), `prospective/`, `design/` |
| Reporting | `packages/ntruth/reporting/` (JSON/YAML/HTML, `safe_methods.py` per Appendix AN, privacy, RO-Crate) |
| Confidence / calibration / OOD | `packages/ntruth/confidence/` (`ConfidenceRecord`, risk–coverage, OOD states), `calibration/abstention.py`, `complexity/tiers.py` (canonical C0–C4) |
| Team evaluation protocol | `packages/ntruth/team_evaluation/` (preregistered H/A/H+A models), `docs/team-evaluation-protocol-v0.1.md` |
| Governance & data use | `packages/ntruth/governance/` (challenge lifecycle, `data_use.py` grants, lineage, contamination, repository policy) |
| Model boundary | `packages/ntruth/model_backends/` (qualification records, registry), `training/` (HOLD-gated MLX lane) |
| Reality Gate | `packages/ntruth/reality_gate/v8.py`: six readiness dimensions, typed blockers, current decision HOLD |
| Contract Packages | `contracts/cp-sci.yaml`, `cp-epi.yaml`, `cp-data.yaml`, `cp-eval.yaml`, `cp-run.yaml` + `scripts/check_contract_packages.py` |
| Sample sheet | `packages/ntruth/sample_sheet/` (generation/validation CLI) |
| Release & verification tooling | `scripts/check_prd_v8_contracts.py`, `check_normative_examples.py`, `check_repository_policy.py`, `check_distribution.py`, `smoke_release.py`, `generate_sbom.py`, `verify_clean_checkout.sh` |
| Desktop UI | `apps/desktop/` guided non-JSON v8 builder (engineering-tested on synthetic fixtures only) |

The machine-readable component map is
[docs/architecture/prd-v8-current-to-target.yaml](docs/architecture/prd-v8-current-to-target.yaml);
the requirement-by-requirement disposition is the
[final PRD v8 migration matrix](docs/audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md)
with the append-only [Scientific Review Register](docs/audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md).

## Explicit blockers

No blocker is closed by passing software tests alone. Open items include:

- incompatible `SupportGrade`/`DerivedClaim`/profile-coverage spellings registered as
  `SRR-V8-*` entries (see the Scientific Review Register);
- external Theory Reference Set, Real Anchor, Derivation Gold, reference stability and
  residual evidence are absent (`SRR-V8-021`, `SRR-V8-022`);
- **gold data not yet annotated**: no adjudicated Derivation Gold set exists;
- training execution is `HOLD_PENDING_REAL_ANCHOR` — no authorized run has happened;
- no custodied External Challenge round exists (lifecycle contracts are implemented,
  custody is empty);
- driver→ARRIVE crosswalk snapshot content hash is pending first custodian pin;
- partial graph scoring, universal few-cluster thresholds and report aggregation
  precedence remain review-blocked and fail-closed.

Current architecture decisions are recorded in
[docs/adr/](docs/adr/README.md) (ADR-0013 … ADR-0018: package split, cloud policy,
calibration policy, challenge feedback, UI defaults).

## Installation

Requirements: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and Node/pnpm only
for the desktop UI.

```bash
git clone https://github.com/Massimilianociconte/N-truth.git
cd N-truth
uv sync --extra dev --extra api --locked
uv run ntruth version
```

`uv.lock` is authoritative. Do not replace a locked command with an unconstrained
`pip install` when reproducing a result or release gate.

The deterministic core has no network requirement. The optional MLX lane is restricted
to Apple Silicon and is not authorized to download a model or train as part of normal
setup.

## Usage

The primary local workflow is the guided desktop form (Quick Design wizard). For
automation and expert inspection, the CLI accepts one strict submission JSON
document — an explicit raw-author-asserted surface, not evidence of guided
confirmation:

```bash
uv run ntruth quick-design run ./quick-design.json --out ./ntruth-out
uv run ntruth reality-gate          # canonical gate status (currently HOLD)
uv run ntruth analyze-v7 ./methods.md --out ./ntruth-v7-out \
  --acknowledge-unvalidated-domain  # DEPRECATED_V7_ADAPTER, historical only
```

### Local API and desktop

```bash
pnpm --dir apps/desktop install --frozen-lockfile
pnpm --dir apps/desktop build
uv run ntruth-api
```

Open `http://127.0.0.1:8765/app/`. The server is loopback-only and unauthenticated;
never expose it on a LAN or the Internet. Cloud use is prohibited without an explicit
funded/university grant (ADR-0015); nothing phones home.

## Validation

Clean-checkout gates (CI runs these; `scripts/verify_clean_checkout.sh` re-verifies
them from an ephemeral detached worktree of HEAD):

```bash
uv lock --check
uv run pytest -m invariant --disable-warnings
uv run pytest -m "not performance" --disable-warnings
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run python scripts/check_prd_v8_contracts.py        # schemas/architecture truth
uv run python scripts/check_contract_packages.py       # CP manifests (PRD v9 §20.2)
uv run python scripts/check_normative_examples.py      # normative fences (PRD v9 §26.5)
uv run python scripts/check_repository_policy.py
uv build && uv run python scripts/check_distribution.py
uv run python scripts/smoke_release.py                 # add --include-ml on Apple Silicon
uv run python scripts/generate_sbom.py --check sbom.cdx.json

bash scripts/verify_clean_checkout.sh                  # PRD v9 §26.10 / NFR-06 verifier
```

At this committed baseline there is no standalone RTM checker script: requirement
traceability lives in
[docs/audits/prd-v8-full-migration/REQUIREMENT_TRACEABILITY_MATRIX.md](docs/audits/prd-v8-full-migration/REQUIREMENT_TRACEABILITY_MATRIX.md)
and is reviewed through the audits, not mechanized yet.

The PRD example registry deliberately preserves Appendices A, AF and AG as
expected-negative fixtures. Green CI must never silently "repair" those authoritative
source examples. A green suite demonstrates the tested software contracts; it does not
demonstrate accuracy on real documents, human agreement or external validity.

Latest clean-checkout verdict: [docs/clean-checkout-report-2026-08-25.md](docs/clean-checkout-report-2026-08-25.md).

## Data, privacy and repository safety

- No raw corpus, private dataset, model weight, secret, credential or external
  challenge payload belongs in Git.
- `TEST` and `EXTERNAL_CHALLENGE` are never training- or model-selection-eligible.
- Repository policy is a bounded detection gate, not an attestation of privacy,
  licensing or absence of contamination.
- Sharing and redistribution remain independently fail-closed.

## Documentation

- [Status snapshot](docs/status-snapshot.md)
- [Clean-checkout report 2026-08-25](docs/clean-checkout-report-2026-08-25.md)
- [Architecture decisions (ADR index)](docs/adr/README.md)
- [Architecture and invariants](docs/architettura.md)
- [Repository structure](docs/repository-structure.md)
- [Team evaluation protocol](docs/team-evaluation-protocol-v0.1.md)
- [PRD v8 data/training/evaluation boundary](docs/prd-v8-data-training-evaluation-boundary.md)
- [Final PRD v8 implementation matrix](docs/audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md)
- [Scientific Review Register](docs/audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md)
- [Contribution guide](CONTRIBUTING.md)
- [Governance](GOVERNANCE.md)
- [Release procedure](docs/releasing.md)
- [Security policy](SECURITY.md)

Historical audit artifacts (PRD v7 alignment, v3/v6 operational drafts) remain under
[docs/audits/](docs/audits/) and the documentation map
([docs/README.md](docs/README.md)); they are records, not current-status descriptions.

## License and citation

Software is licensed under [Apache-2.0](LICENSE). Input documents, datasets and model
artifacts retain their own licenses and permissions; the software license never grants
rights over them. Citation metadata is in [CITATION.cff](CITATION.cff).
