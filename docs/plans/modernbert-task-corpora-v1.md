# Workstream C — ModernBERT task corpora v1 (design)

**Status:** DESIGN_ONLY — no training authorized  
**Branch:** `feat/modernbert-task-corpora-v1`  
**Prerequisite:** Workstream B merged to `main` (PR #2, merge `ff8cd89`)  
**Data root:** `/Volumes/FLASH128/N-Truth-Datasets` (NO_CORPUS in git)

## Goal

Transform acquired public datasets into **deterministic, leakage-aware, task-specific corpora** for **ModernBERT auxiliary extraction baselines**.

This is **not**:

- end-to-end N-Truth training;
- scientific validation;
- Granite graph training;
- promotion of public annotations to N-Truth gold.

## Holds (unchanged)

```
MODERNBERT_AUXILIARY_BASELINES: HOLD_PENDING_CORPORA
SCIENTIFIC_VALIDATION: NOT_STARTED
NTRUTH_END_TO_END_TRAINING: HOLD
GRANITE_GRAPH_TRAINING: HOLD
TRAINING_PROGRAM: HOLD_PENDING_REAL_ANCHOR
GRANITE_DEFAULT_PROMOTION: HOLD
```

After corpora + B0 non-neural baselines + smoke tests pass, a separate approval may set:

```
MODERNBERT_AUXILIARY_BASELINES: GO
```

---

## 1. Repository findings (post–Workstream B)

| Item | Value |
|------|--------|
| main tip | `ff8cd89` Merge PR #2 |
| pipeline package | `packages/ntruth/data/**` |
| external root | `NTRUTH_DATA_ROOT=/Volumes/FLASH128/N-Truth-Datasets` |
| Merkle (post sign-off) | `5aec5f862168a0f38b29fcd71f29eb4d6d9dd072dda1a3c4c3786f4e7d8c7e40` |
| Sources on stick | SourceData, PreClinIE, MeasEval, CRAFT (SILVER_AUXILIARY) |
| MeasEval training_ready | BLOCKED_BY_UPSTREAM_GROUP_OVERLAP |
| SourceData multitask | present under `training_ready/sourcedata_multitask/` (auxiliary) |

**Do not** concatenate the four datasets into one generic corpus.

---

## 2. Proposed architecture

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

### Stage C0 — scaffolding

- Package skeleton, schemas, authority enums, CLI `status` / `dry-run`
- Unit tests for schema invariants and fail-closed validators

### Stage C1 — SourceData entity_roles adapter

- Consume processed or raw SourceData with existing alignment guarantees
- Emit token-classification task records
- Preserve upstream splits; group by document/panel family
- Stats + card

### Stage C2 — MeasEval quantities adapter

- Span/relation payload → quantity task records
- **Enforce** BLOCKED_BY_UPSTREAM_GROUP_OVERLAP: training_eligible=false for any group in train∩test overlap unless human policy later
- Preserve trial isolation
- Five missing-TSV stems remain non-eligible / requires_review

### Stage C3 — PreClinIE method_indicators + routing

- Publication-level grouping (reuse seed 20260803 logic)
- Method indicator multi-label / token tags from existing annotations
- Routing labels from segment type (abstract/methods/…) with explicit authority AUXILIARY

### Stage C4 — CRAFT coreference / relations

- Official 67/30 + N-Truth 60/7 derivation already documented
- Coreference chains as AUXILIARY only

### Stage C5 — manifests, cards, B0 hooks

- Per-task split manifests, class histograms, exclusion reports
- Data cards with licence_status and forbidden_uses
- Smoke commands; storage estimates under FLASH128 FAT32 limit
- **No ModernBERT training** in this stage

### Stage C6 — Workstream C readiness report

- Acceptance matrix
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
3. Leakage audit per task: zero group multi-split (except documented MeasEval upstream overlap which is excluded from training_ready).
4. Storage estimate < free space − 8 GB reserve.
5. Report `WORKSTREAM_C_CORPORA: READY_FOR_B0` or `BLOCKED` with reason.

### Explicit non-acceptance

- Training ModernBERT weights
- Using public labels as N-Truth EU / n / verdict gold
- Auto-resolving MeasEval overlap without human policy

---

## 6. Unresolved decisions (user approval required)

1. **MeasEval overlap policy** (still PENDING_HUMAN_DECISION):  
   REMOVE_OVERLAPPING_GROUPS_FROM_TRAIN | CREATE_NTRUTH_GROUP_SAFE_SPLIT | FORMAT_SMOKE_ONLY | EXCLUDE_FROM_MODEL_TRAINING
2. **License scope closure** for SourceData / PreClinIE training permission before any encoder fine-tune.
3. **Routing label inventory** — final closed set of section labels.
4. **Synthetic budget** — max synthetic fraction per task (proposal: ≤10% train, 0% test).
5. **Real-anchor volume** — confirm 30–50 cases and double-review capacity.
6. **Lazic data** — confirm EXTERNAL_CHALLENGE default; no train without written policy.
7. **ModernBERT checkpoint choice** — deferred until corpora READY_FOR_B0 (not this PR).

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
