# N-Truth

[![CI](https://github.com/Massimilianociconte/N-truth/actions/workflows/ci.yml/badge.svg)](https://github.com/Massimilianociconte/N-truth/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Scientific status: candidate](https://img.shields.io/badge/scientific_status-candidate-orange.svg)](docs/system-card-v0.1.md)

N-Truth is a local-first, human-in-the-loop platform for reconstructing biological
experimental designs. It turns Methods, captions, sample sheets, metadata and
statistical code into a typed, versioned graph, then applies inspectable deterministic
rules to expose experimental units, dependencies, inference scope, conditional values
of `n`, missing information and decisive questions.

> N-Truth is research software in alpha status. It does not certify statistical
> validity, reproducibility, research integrity, privacy compliance or adherence to
> DRIVER/NC3Rs. It does not replace a biostatistician or domain expert. No N-Truth AI
> model, gold corpus or externally validated performance claim exists yet.

Repository: [github.com/Massimilianociconte/N-truth](https://github.com/Massimilianociconte/N-truth)<br>
Issues: [bug reports and feature requests](https://github.com/Massimilianociconte/N-truth/issues)<br>
Security: [private reporting policy](SECURITY.md)

## What N-Truth does

- safely imports TXT/Markdown, JATS/XML, DOCX, text-based PDF, CSV/XLSX and R/Python/R
  Markdown;
- never executes imported statistical code;
- segments multiple experimental blocks instead of assigning one label to a paper;
- keeps allocation level, application level and observation level distinct;
- represents factors, contrasts, endpoints, targets, estimands, pairing, blocking,
  pooling, nesting, repeated measures and declared clustering;
- distinguishes declared, allocated, analyzed, observational and independent counts;
- abstains or emits explicit scenarios when a decisive fact is unknown;
- separates design replication, analytical dependence and inference scope;
- supports evidence-linked human corrections, append-only revisions, undo/redo and
  candidate-annotation export;
- exports JSON, YAML, HTML, graph JSON, JSON-LD/RO-Crate and machine-readable schemas;
- scans locally for privacy indicators and denies sharing/redistribution by default.

It does **not** currently perform OCR, train or run an AI parser, choose a definitive
statistical test, upload files, or grant rights to use third-party data.

## Scientific model

Every rule answers exactly one of three questions:

| Class | Meaning |
|---|---|
| `DESIGN_REPLICATION` | Is the factor replicated across independently allocable units? |
| `ANALYTICAL_DEPENDENCE` | Does the analysis represent correlation between observations? |
| `INFERENCE_SCOPE` | Does the claim stay within the population and hierarchy actually replicated? |

An experimental unit is always relative to a factor and contrast. A hierarchical model
can represent dependence but cannot create missing biological replication. Author
phrases such as “independent experiments” remain assertions unless structural,
tabular, adjudicated or user-confirmed evidence supports them. When independence is
not established, `n_independent` remains `null` or is represented through conditional
scenarios.

The public normative contract is [N-Truth Public Specification v0.1](docs/public-specification-v0.1.md).
The scientific sources cited by the 32 rules are resolvable in the
[versioned reference registry](docs/scientific-references.md). Rules and their current
10/17/5 class mapping remain candidates pending external wet-lab and biostatistical
review.

## Current status

| Area | Available now | Still required |
|---|---|---|
| Deterministic core | Safe ingest, graph, 32 rules, conditional `n`, positive output | Expert review and 30-60 canonical fixtures |
| Human workflow | Evidence view, editable graph, corrections, revisions, audit, undo/redo | Formal user study and adjudication workflow on real data |
| Interfaces | CLI, loopback FastAPI, React UI | Authentication/multi-user mode is intentionally absent |
| Data governance | Per-asset contracts, privacy scan, lineage and fail-closed distribution gate | Signed authorizations, DPIA where needed and approved corpus manifests |
| Parser AI | Stable input/output JSON contract and validators | Backend, evaluated baseline, calibration and OOD detection |
| Training | Policy, placeholder configs and model/data/system cards | Gold data, frozen splits, trainer, model weights and measured metrics |
| Validation | Synthetic executable tests and challenge fixtures | Double annotation, IAA/human ceiling and independent external validation |

The repository contains 12 synthetic scientific regressions and 128 executable rule
scenarios (positive, negative, ambiguous and exception for each rule). These verify
software contracts; they are not an adjudicated corpus.

## Architecture

```mermaid
flowchart LR
    A["Experiment Bundle<br/>documents + tables + code"] --> B["Safe local ingest<br/>Document IR"]
    B --> C["Deterministic extraction<br/>future AI candidates"]
    C --> D["Typed graph<br/>evidence + alternatives"]
    D --> E["Human review<br/>append-only corrections"]
    E --> F["Validated graph"]
    F --> G["Deterministic compiler<br/>32 versioned rules"]
    G --> H["Report + questions<br/>JSON/YAML/HTML/RO-Crate"]
```

The rules engine reads the validated graph, never raw prose. Candidate parser facts are
untrusted until schema, reference, coordinate and evidence-span validation succeeds.
The CLI, API and UI call the same application layer. See
[architecture and invariants](docs/architettura.md) and the
[repository map](docs/repository-structure.md).

## Requirements

### Core

- macOS (Apple Silicon) or Linux x86-64;
- Python 3.12 or newer;
- [`uv`](https://docs.astral.sh/uv/) with the committed `uv.lock`.

### API/UI and development

- Node.js 20.19 or newer;
- pnpm 11.9.0, as declared in `apps/desktop/package.json`.

No database, cloud account, API key or GPU is required for the deterministic baseline.
There is no PyPI release yet; install from this checkout or from a verified local wheel.

## Installation

Clone the official repository and enter it:

```bash
git clone https://github.com/Massimilianociconte/N-truth.git
cd N-truth
```

Install only the deterministic core:

```bash
uv sync --locked
```

Add the local API:

```bash
uv sync --extra api --locked
```

Set up a contributor environment:

```bash
uv sync --extra dev --extra api --locked
pnpm --dir apps/desktop install --frozen-lockfile
```

`uv.lock` is authoritative. Do not replace a locked command with an unconstrained
`pip install` when reproducing a result or release gate.

## 60-second CLI quickstart

Inspect the software and bundled rules:

```bash
uv run ntruth version
uv run ntruth rules list
uv run ntruth rules show MIC-004
```

Analyze a public synthetic fixture:

```bash
uv run ntruth analyze \
  tests/scientific_fixtures/uc02_preparations/methods.md \
  --out ./ntruth-out \
  --lang it \
  --domain quantitative_microscopy \
  --acknowledge-unvalidated-domain
```

The acknowledgement confirms only that the domain warning was read. It does not
validate the domain or accept a scientific conclusion.

Each run receives an isolated directory:

```text
ntruth-out/runs/<run-id>/
├── project/                 # copied local source and project manifest
└── revisions/0000/
    ├── report.json
    ├── report.yaml
    ├── report.html
    ├── graph.json
    ├── design-specification.json
    ├── design-compilation.json
    ├── parser-ai-input.schema.json
    ├── parser-ai-output.schema.json
    ├── privacy-scan.json
    ├── share-readiness.json
    └── ro-crate-metadata.json
```

Open `report.html` locally. Verify a reusable project before further work:

```bash
uv run ntruth verify ./ntruth-out/runs/<run-id>/project
```

Use `--project /absolute/path/to/project` only when intentionally appending to an
existing local workspace. Without it, runs are isolated and previous output is not
overwritten.

## Local API and UI

Build the bundled UI and start the loopback server:

```bash
pnpm --dir apps/desktop install --frozen-lockfile
pnpm --dir apps/desktop build
uv run ntruth-api
```

Then open:

- application: `http://127.0.0.1:8765/app/`
- OpenAPI documentation: `http://127.0.0.1:8765/docs`
- health check: `http://127.0.0.1:8765/v1/health`

```bash
curl --fail http://127.0.0.1:8765/v1/health
```

The API is unauthenticated, single-user and intentionally hard-coded to
`127.0.0.1:8765`. It accepts local paths and holds at most 16 recent editing sessions
in memory; restarting it clears those sessions, while append-only run artifacts remain
on disk. Never bind it to `0.0.0.0`, expose it to a LAN/Internet, or place it behind a
reverse proxy.

For UI development, run the API and, in a second terminal:

```bash
pnpm --dir apps/desktop dev
```

Open `http://127.0.0.1:5173/app/`; Vite proxies API requests to the loopback server.

## Configuration

The core reads one optional environment variable:

| Variable | Required | Meaning |
|---|---|---|
| `NTRUTH_RULESETS` | No | One or more external ruleset directories, separated by the operating-system path separator (`:` on supported macOS/Linux). External paths take precedence over bundled rules. |

Example:

```bash
export NTRUTH_RULESETS="/absolute/path/to/reviewed-rulesets"
uv run ntruth rules list
```

N-Truth does not load `.env` automatically. `.env.example` is documentation only; do
not put tokens, passwords or private-data paths in it. The deterministic application
requires no credentials.

## Supported input and safety behavior

| Input | Support and limits |
|---|---|
| TXT/Markdown | Local text and headings |
| JATS/XML | Sections, references and evidence coordinates |
| DOCX | Text/tables from safe, bounded archives; macros are not executed |
| PDF | Extractable text only; no OCR in the baseline |
| CSV/XLSX | Sheets, types and formulas; formulas are data, never instructions |
| R/Python/R Markdown | Read-only extraction; `never_execute` policy |

Corrupt, oversized, traversal-bearing, macro-bearing or unsupported inputs fail
explicitly. Formula injection, prompt injection and imported code are treated as
untrusted content. See [Security Policy](SECURITY.md).

## Human correction workflow

1. Run an analysis and open the local evidence/graph view.
2. Select an experiment block and inspect the evidence for the candidate fact.
3. Confirm, reject or apply a constrained patch with rationale and reviewer role.
4. Review the diff and the recalculated deterministic output.
5. Use undo/redo when needed; every action remains in the audit trail.
6. Export candidate annotations only after reviewing evidence and alternatives.

Corrections create new revision directories. They never mutate source files or promote
an annotation to gold. Candidate exports remain `training_eligible=false` until an
independent reviewer and adjudicator explicitly promote them.

## Data governance and distribution checks

Every analysis writes `privacy-scan.json` and `share-readiness.json`; sharing and
redistribution are denied by default. To evaluate a specific revision:

```bash
uv run python scripts/create_governance_template.py \
  ./ntruth-out/runs/<run-id>/revisions/<revision> \
  --out /absolute/private/path/governance.pending.json

uv run ntruth distribution-check \
  ./ntruth-out/runs/<run-id>/revisions/<revision> \
  --governance /absolute/private/path/governance.reviewed.json \
  --action share \
  --privacy-policy acknowledged \
  --acknowledgement-reference local://privacy-review/<review-id>
```

The governance file must contain records whose asset IDs and SHA-256 values exactly
match `share-readiness.json`, plus immutable evidence of authorization and any required
per-asset license manifest. `blocked` always denies distribution. `acknowledged`
requires an explicit review reference. `redacted_copy` requires a complete redaction
manifest and exact derivative content for every finding.

The command performs a local fail-closed evaluation only: it never copies, uploads or
shares a file. Start from the scope-bound procedure in the
[governance workflow](docs/governance-workflow.md), then see
[data governance](docs/data-governance-v3.md),
[data-sharing checklist](docs/data-sharing-agreement-checklist.md) and
[privacy/DPIA screening](docs/privacy-dpia-screening.md).

## Data collection, annotation and model development

Real or downloaded data must live in `local-data/`, which is ignored by Git. The
expected local layout is:

```text
local-data/
├── raw/incoming/
├── metadata/assets/
├── metadata/sources/
├── annotations/pending/
├── train/
├── validation/
├── test/
├── external/
└── quarantine/
```

An acquired file stays immutable in `raw/incoming` with split `unassigned`. Promotion
requires asset-level license evidence, provenance, SHA-256, privacy review,
deduplication and a whole-bundle leakage group. Article, revisions/preprint,
supplements, sample sheet, code, repository accessions and mirrors must remain in one
split. Synthetic/template data may enter training only; validation, test and external
sets are frozen before optimization.

There is intentionally no training command and no `ml` installation extra in this
release. Training begins only after expert review, 20 stable real designs, 30-60
canonical fixtures, 30 double-annotated calibration cases, a frozen pilot protocol,
approved rights and bundle/laboratory-aware splits. See
[data and model development](docs/data-and-model-development.md), the
[Data Card](docs/data-card-v0.1.md), [Model Card gates](models/cards/README.md) and the
[validation protocol draft](docs/validation-protocol-draft.md).

Never commit or publish `local-data/`, `data/raw/`, real annotations, checkpoint files,
model runs or source documents without explicit authorization.

## Development and test commands

From a contributor installation:

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run pytest
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build
uv run python scripts/generate_sbom.py --check sbom.cdx.json
uv build
uv run python scripts/check_distribution.py
uv run python scripts/smoke_release.py
```

The release smoke test installs the wheel and rebuilds/installs the source distribution
in separate clean environments, then checks the CLI, bundled rules and local API health
contract. A green suite demonstrates the tested software contracts; it does not
demonstrate accuracy on real documents, human agreement or external validity.

See [Contributing](CONTRIBUTING.md), the [release procedure](docs/releasing.md) and
[Code of Conduct](CODE_OF_CONDUCT.md).

## Troubleshooting

- **Domain acknowledgement required:** rerun with
  `--acknowledge-unvalidated-domain` only after reading the warning.
- **Ruleset not found:** run `uv run ntruth rules list` and verify
  `NTRUTH_RULESETS`; N-Truth does not auto-load `.env`.
- **PDF produces no content:** the baseline does not perform OCR; use a separately
  reviewed OCR workflow and retain the original.
- **UI is missing/stale:** rebuild it with `pnpm --dir apps/desktop build` before
  starting `ntruth-api`.
- **Port 8765 is occupied:** inspect the exact listener with
  `lsof -nP -iTCP:8765 -sTCP:LISTEN`; do not use broad `pkill` commands.
- **Distribution denied:** this is the safe default; inspect checksums, permission,
  license and privacy records rather than bypassing the gate.

Full guidance: [Troubleshooting](docs/troubleshooting.md) and [Support](SUPPORT.md).

## Current limitations and roadmap

Release-blocking scientific work still requires people and data:

- independent wet-lab and biostatistical review of definitions and all principal rules;
- 30-60 complete canonical, referenced and reviewed fixtures;
- authorized real Experiment Bundles and a double-annotated pilot;
- IAA, adjudication, determinability rate and human-ceiling estimates;
- evaluated constrained parser baseline, calibration, abstention and OOD detection;
- external validation on unseen laboratories/techniques and a crossover user study.

Engineering roadmap items include a governed corpus snapshot builder, active learning
after evaluation-set freeze, optional OCR adapters with provenance, persistent/multi-user
deployment with authentication, and a trained parser only after the published gates.
See [PRD v3 reconciliation](docs/prd-v3-reconciliation.md) and the
[first human steps checklist](docs/first-human-steps-checklist.md).

## Documentation index

- [Public Specification v0.1](docs/public-specification-v0.1.md)
- [Architecture and invariants](docs/architettura.md)
- [Repository structure](docs/repository-structure.md)
- [Scientific references](docs/scientific-references.md)
- [Annotation Guideline draft](docs/annotation-guideline-v0.1.md)
- [Design Specification](docs/design-specification-v0.1.md)
- [Parser AI contract](docs/parser-ai-contract.md)
- [Data governance](docs/data-governance-v3.md)
- [Governance and distribution workflow](docs/governance-workflow.md)
- [Data/model development](docs/data-and-model-development.md)
- [Data Management Plan draft](docs/data-management-plan-draft.md)
- [Validation protocol draft](docs/validation-protocol-draft.md)
- [System Card](docs/system-card-v0.1.md) and [Data Card](docs/data-card-v0.1.md)
- [Release procedure](docs/releasing.md) and [Troubleshooting](docs/troubleshooting.md)

## Contributing, citation and license

Contributions are welcome through issues and pull requests. Scientific changes must
include executable edge cases and must not be called approved before external review.
Read [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and
[SECURITY.md](SECURITY.md) first.

Citation metadata is available in [CITATION.cff](CITATION.cff). Until a tagged release
or archival DOI exists, cite the exact Git commit in addition to the project title and
repository URL.

Original code, documentation, rulesets, ontology and synthetic fixtures in this
repository are licensed under [Apache License 2.0](LICENSE), unless a file explicitly
states otherwise. This license does not extend to imported papers, datasets,
laboratory material, restricted annotations or model weights.

N-Truth is an independent project. It is not an NC3Rs product, does not reproduce the
DRIVER resource and must not imply endorsement or certification.
