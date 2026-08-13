# Workstream C — ModernBERT task corpora v1

> **DOCUMENTO STORICO / SUPERSEDED (2026-08-13).** Branch, commit, stage, Merkle,
> `training_ready` e blocker MeasEval riportati nel piano originale non descrivono lo
> stato corrente e non sono evidenza di readiness. Questo piano non autorizza baseline
> o smoke. Tokenizzazione, training, prediction, metriche/calibrazione,
> resume/checkpoint ed export restano bloccati dal requisito
> `anonymous_unlinked_inherited_fd_runner`; il doctor resta `ready_to_train=false`.
> L'unica decisione operativa corrente è
> [TRAINING-READINESS-small-model-20260813.md](../training/TRAINING-READINESS-small-model-20260813.md).

**Original status (historical):** C0–C1 IMPLEMENTED AND LOCALLY VERIFIED
**Current training decision:** `NOT_READY`
**Original branch:** `feat/modernbert-task-corpora-v1` (PR #3)
**Original prerequisite:** Workstream B merged to `main` (PR #2, merge `ff8cd89`)
**Data root:** `/Volumes/FLASH128/N-Truth-Datasets` (NO_CORPUS in git)

## Goal

Transform acquired public datasets into **deterministic, leakage-aware, task-specific corpora** for **ModernBERT auxiliary extraction baselines**.

This is **not**:

- end-to-end N-Truth training;
- scientific validation;
- Granite graph training;
- promotion of public annotations to N-Truth gold.

## Historical holds from the original plan

```
MODERNBERT_AUXILIARY_BASELINES: HOLD_PENDING_CORPORA
SCIENTIFIC_VALIDATION: NOT_STARTED
NTRUTH_END_TO_END_TRAINING: HOLD
GRANITE_GRAPH_TRAINING: HOLD
TRAINING_PROGRAM: HOLD_PENDING_REAL_ANCHOR
GRANITE_DEFAULT_PROMOTION: HOLD
SOURCE_DATA_TRAINING_USE: BLOCKED
SOURCE_DATA_EVALUATION_USE: PENDING_LICENCE_DECISION
SYNTHETIC_AUGMENTATION: HOLD
```

Only after corpus/licence closure, the anonymous/unlinked inherited read-only FD runner,
an applicable canonical authorization envelope v1, current readiness gates and the
future non-executable baseline protocol have all been satisfied may a new decision
consider setting:

```
MODERNBERT_AUXILIARY_BASELINES: GO
```

---

## 1. Historical repository snapshot (superseded)

The table below records the original Workstream B snapshot only. None of its values
may be used to verify the current external data root.

| Item | Value |
|------|--------|
| main tip | `ff8cd89` Merge PR #2 |
| pipeline package | `packages/ntruth/data/**` |
| external root | `NTRUTH_DATA_ROOT=/Volumes/FLASH128/N-Truth-Datasets` |
| Merkle (historical, retired) | Superseded; use the newly generated canonical manifest referenced by current readiness evidence |
| Sources on stick | SourceData, PreClinIE, MeasEval, CRAFT (SILVER_AUXILIARY) |
| MeasEval (historical state) | Old `BLOCKED_BY_UPSTREAM_GROUP_OVERLAP` label; not the current split/readiness result |
| SourceData multitask (historical location) | Old `training_ready/sourcedata_multitask/` path retired; it conveyed no training authorization |

**Do not** concatenate the four datasets into one generic corpus.

---

## 2. Proposed architecture (historical)

```
NTRUTH_DATA_ROOT/
  raw/                          # immutable (Workstream B)
  processed/                    # common envelopes (Workstream B)
  task_corpora/                 # NEW — task-specific normalized JSONL
    routing/
    entity_roles/
    quantities/
    relations/
    coreference/
    method_indicators/
  task_manifests/               # NEW — stats, splits, data cards, exclusions
  baselines/                    # NEW later — B0 non-neural only in this WS
    b0/
  reports/
    workstream_c/
```

### Package layout (code)

```
packages/ntruth/task_corpora/
  __init__.py
  config.py                 # paths, seeds, task registry
  schemas.py                # TaskRecord + task payloads
  authority.py              # supervision_source, authority_level, allowed/forbidden uses
  adapters/
    sourcedata_entity_roles.py
    measeval_quantities.py
    craft_coreference.py
    preclinie_methods.py
    routing.py              # section routing from structure + PreClinIE segments
  splits.py                 # leakage-aware group assignment reuse
  validate.py               # offsets, token/label length, fail-closed
  stats.py
  cards.py                  # dataset card generators
  cli.py                    # uv run python -m ntruth.task_corpora ...
```

### Canonical task record (minimum fields)

```yaml
record_id: string
task_type: routing | entity_roles | quantities | relations | coreference | method_indicators
source:
  dataset: SourceData | PreClinIE | MeasEval | CRAFT | SYNTHETIC
  version: string
  commit: string
  document_id: string
  segment_id: string
text: string                  # or tokens[] with offsets
labels: ...                   # task-specific payload
supervision_source: HUMAN_PUBLIC | STRUCTURED_METADATA | WEAK_RULE | SYNTHETIC
authority_level: AUXILIARY | CANDIDATE | NTRUTH_GOLD
allowed_uses: [encoder_pretraining, token_classification, span_classification, ...]
forbidden_uses: [experimental_unit_gold, independent_n_gold, pseudoreplication_verdict_gold, ...]
licence_status: LICENSE_SCOPE_VERIFIED | LICENSE_REVIEW_REQUIRED | ...
leakage_group: string         # paper/publication/PMCID/family
split: train | validation | test
training_eligible: bool
evaluation_eligible: bool
requires_review: bool
transform_lineage:
  adapter: string
  transform_version: string
  parent_checksum: sha256
checksum: sha256
```

### JSONL framing contract (normative)

```text
JSONL framing contract:
- records are separated exclusively by ASCII LF, byte 0x0A;
- CRLF may be normalised at ingestion boundaries if explicitly documented;
- Unicode line and paragraph separators, including U+2028 and U+2029, are
  preserved as record content;
- generic splitlines()-style parsing is prohibited for canonical JSONL;
- content digests are computed by one shared implementation
  (records_content_sha256 in packages/ntruth/task_corpora/io_util.py).
```

Code readers must use LF-only physical line iteration
(`iter_jsonl_physical_lines` / `str.split("\n")`), never `str.splitlines()`.

### Granular use decision (normative)

Every snapshot licence file must declare, without inference:

```yaml
use_decision:
  adapter_build_allowed: true | false
  local_format_validation_allowed: true | false
  development_allowed: true | false | unknown
  training_allowed: true | false
  evaluation_allowed: true | false | unknown
  benchmark_metrics_publication_allowed: true | false | unknown
  derived_records_redistribution_allowed: true | false
  model_weights_redistribution_allowed: true | false
```

`unknown` and incompatible values **fail closed** for the relevant capability.
B0 iterative development on a corpus requires `development_allowed=true`,
not merely `training_allowed=false` with silent validation-set peeking.

### Leakage audit field

Build manifests must report:

```text
groups_crossing_splits: <int>
```

Acceptance for a clean upstream-split corpus requires `groups_crossing_splits = 0`
(unless a later written policy documents and quarantines exceptions).

### Task families → sources

| Task family | Primary sources | Notes |
|-------------|-----------------|-------|
| A. Document/section routing | PreClinIE segments; CRAFT article structure; optional synthetic | Labels METHODS, FIGURE_CAPTION, STATISTICAL_METHODS, RESULTS, OTHER, EXPERIMENT_BLOCK? |
| B. Entity & experimental roles | SourceData NER + ROLES_MULTI | Never auto-map to EU / allocation / independence |
| C. Quantities & quantifiers | MeasEval (+ synthetic minimal pairs) | Exclude train∩test overlapping groups from any training-eligible set |
| D. Relations / coreference | CRAFT | Linguistic mechanism only; not N-Truth “these cultures → donors” gold |
| E. Methodological indicators | PreClinIE | Textual evidence only; random allocation phrase ≠ proof of allocation level |

---

## 3. Exact files to create or modify

### Create

- `packages/ntruth/task_corpora/**` (as above)
- `tests/unit/task_corpora/**`
- `tests/integration/task_corpora/**`
- `docs/plans/modernbert-task-corpora-v1.md` (this file)
- `docs/scientific/real-anchor-protocol-v0.1.md`
- `docs/audits/modernbert-task-corpora-v1/` (readiness report, later)
- `scripts/build_task_corpora.sh` (optional thin wrapper)

### Modify (minimal)

- `pyproject.toml` — optional console script entry if needed
- `packages/ntruth/data/config.py` — only if sharing path helpers (prefer import, not fork)

### Never commit

- `task_corpora/**` data
- model weights, HF caches, full text dumps

---

## 4. Implementation stages

### Stage C0 — scaffolding — **VERIFIED (local + CI)**

- Package skeleton, schemas, authority enums, CLI `status` / `build` / `validate` / `stats`
- Unit tests for schema invariants and fail-closed validators
- LF-only JSONL contract + shared `records_content_sha256`

### Stage C1 — SourceData entity_roles adapter — **VERIFIED (local + CI)**

- Consume processed SourceData multitask snapshot
- Emit token-classification task records (`AUXILIARY`)
- Preserve upstream splits; leakage_group = document_id
- Stats + manifest + leakage audit; synthetic_fraction = 0.0

### Stage C2 — PreClinIE routing + method_indicators (next branch)

- Branch design: `feat/preclinie-routing-method-indicators-v1`
- Labels remain AUTHOR_ASSERTION / REPORTED_METHOD_INDICATOR
- **Not** CONFIRMED_ALLOCATION / CONFIRMED_RANDOMIZATION / experimental-unit gold

### Stage C3 — CRAFT auxiliary coreference + explicit relations

- Linguistic mechanism only

### Stage C4 — MeasEval quantities (historical plan; superseded)

- Span/relation payload → quantity task records
- The original plan required `BLOCKED_BY_UPSTREAM_GROUP_OVERLAP` and
  `training_eligible=false` for overlapping groups. That exact blocker is historical;
  consult current manifests/readiness for the family-safe split and model-use status.
- Preserve trial isolation
- Five missing-TSV stems remain non-eligible / requires_review

### (Historical note)

PreClinIE was previously sketched after MeasEval; approved order is
C2 PreClinIE → C3 CRAFT → C4 MeasEval → licence closure → B0 → ModernBERT GO.

### Stage C5 — manifests, cards, B0 hooks (partially done for C0–C1)

- Per-task split manifests, class histograms, exclusion reports, leakage audit
- Data cards with licence_status and granular use_decision
- Smoke commands; storage estimates under FLASH128
- **No ModernBERT training** in this stage

### Stage C6 — Workstream C readiness report

- Acceptance matrix (C0–C1 draft: `docs/task_corpora/workstream-c-c0-c1-readiness.md`)
- What is GO vs HOLD for `MODERNBERT_AUXILIARY_BASELINES`
---

## 5. Tests and acceptance criteria

### Unit

- schema round-trip
- fail-closed token/label length
- fail-closed invalid offsets
- no silent truncation
- authority_level never NTRUTH_GOLD for public adapters
- forbidden_uses always include experimental_unit_gold / independent_n_gold / verdict_gold
- MeasEval overlap groups training_eligible=false
- trial never mixed into train

### Integration

- dry-run on real stick root
- resume idempotent for task_corpora writers
- NO_CORPUS: git status clean of data paths
- ruff + mypy + pytest green

### Acceptance (corpora ready)

1. All six task families have at least one adapter producing non-empty train (where licensed/allowed) or explicit empty-with-reason.
2. Data-use matrix committed as JSON.
3. Leakage audit per task: zero group multi-split; the historical MeasEval exception
   and `training_ready` wording are superseded and cannot authorize model use.
4. Storage estimate < free space − 8 GB reserve.
5. Report `WORKSTREAM_C_CORPORA: READY_FOR_B0` or `BLOCKED` with reason.

### Explicit non-acceptance

- Training ModernBERT weights
- Using public labels as N-Truth EU / n / verdict gold
- Auto-resolving MeasEval overlap without human policy

---

## 6. Decisions and open items

### Resolved for C0–C1

1. **Synthetic contribution for C0–C1: 0%.**
   Future synthetic use must be **task-specific**, benchmarked against a frozen real
   development set and approved through a separate mixture-search decision.
   **No global synthetic percentage is authorised** (including any former “≤10% train” draft).
2. **JSONL LF-only framing** — see contract above; U+2028/U+2029 are content.
3. **Initial routing inventory** — METHODS, STATISTICAL_METHODS, FIGURE_CAPTION, RESULTS, OTHER, UNKNOWN
   (FIGURE_CAPTION only when a source actually supports it).
4. **Lazic** — EXTERNAL_CHALLENGE_CANDIDATE; training_eligible=false by default.
5. **SourceData training** — blocked (`training_allowed=false`, `development_allowed=false`).

### Still requiring user / legal approval

1. **Historical MeasEval overlap options (superseded):**
   `REMOVE_OVERLAPPING_GROUPS_FROM_TRAIN` | `CREATE_NTRUTH_GROUP_SAFE_SPLIT` |
   `FORMAT_SMOKE_ONLY` | `EXCLUDE_FROM_MODEL_TRAINING`. These are not a current
   pending-decision register.
2. **License scope closure** for SourceData / PreClinIE: at least
   `development_allowed`, `evaluation_allowed`, `benchmark_metrics_publication_allowed`,
   and redistribution flags — currently SourceData evaluation is `unknown` (fail closed).
3. **Real-anchor volume** — confirm 30–50 cases and double-review capacity (wet-lab + biostat).
4. **ModernBERT checkpoint choice** — deferred until corpora + B0 + resource benchmarks.

---

## 7. Command sketch (future implementation)

```bash
export NTRUTH_DATA_ROOT=/Volumes/FLASH128/N-Truth-Datasets

uv run python -m ntruth.task_corpora status --root "$NTRUTH_DATA_ROOT"
uv run python -m ntruth.task_corpora dry-run --task entity_roles --root "$NTRUTH_DATA_ROOT"
uv run python -m ntruth.task_corpora build --all --root "$NTRUTH_DATA_ROOT" --resume
uv run python -m ntruth.task_corpora validate --all --root "$NTRUTH_DATA_ROOT"
```

---

## 8. Relationship to scientific sequence

```
Workstream B (done) → Workstream C task corpora → B0 + ModernBERT auxiliary baselines
  → real anchor 30–50 → hybrid benchmarks → only then Granite graph / end-to-end
```
