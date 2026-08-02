# Clean-checkout documentation verification

**Verdict date:** 2026-08-02  
**Method:** detached git worktree at `ef39fb4` (parent `4cfee299`), zero local dirty files.  
**Worktree path (ephemeral):** `/tmp/ntruth-clean-docs-verify-ef39fb4`  
**Purpose:** decide whether GitHub-facing docs describe the **publishable repository** or a **local unreproducible state**.

## Gate checklist

| Gate | Result |
|------|--------|
| `commit_contains_docs_only` (`ef39fb4`) | **true** (11 paths: README, CHANGELOG, docs/*, models/cards) |
| `no_secrets_or_personal_paths` in docs commit | **true** (spot-checked) |
| `no_model_weights` in docs commit | **true** |
| `no_frozen_annotations` in docs commit | **true** |
| `no_ledger_changes` in docs commit | **true** |
| `clean_checkout_docs_consistent` | **false** — **BLOCKER** |
| `documented_implementation_is_committed` | **false** — **BLOCKER** |
| `documentation_commands_verified` (core CLI) | **partial true** (deterministic core works) |
| `documentation_commands_verified` (Train A / Granite / B4 / P0 / annotation) | **false** |

```yaml
PUSH_TO_REMOTE: CONDITIONAL_FAIL   # clean_checkout_docs_consistent=false
MERGE_TO_MAIN: HOLD
DOCUMENTATION_CONTENT: APPROVED_AS_LOCAL_DESCRIPTION_ONLY
```

## What a clean clone actually contains

At `ef39fb4` / `4cfee299`:

| Area | In clean Git? | Notes |
|------|---------------|--------|
| Deterministic Train D (CLI, rules, analyze, fixtures) | **yes** | `ntruth version`, `rules list`, analyze fixture **PASS** |
| ML profile default | **Qwen3-4B config only** | `ntruth-ml check` resolves `models/configs/qwen3-4b-instruct-2507-mlx-qlora.json` |
| `packages/ntruth/model_backends/` (GraniteBackend, Outlines) | **no** | directory absent |
| `models/registry/default.json` | **no** | absent (untracked in working tree) |
| `models/registry/training_program.json` | **no** | absent |
| Granite MLX configs | **no** | only ModernBERT + Qwen configs tracked |
| B4 / fewshot_p0 / semantic-C | **no** | `benchmarks/` has README + rules-only only |
| P0-alpha 2000/300 | **no** | `data/training/p0-alpha` absent |
| Reality-check schema / pilot 003 | **no** | `data/annotations/*/` gitignored; not in tree |
| ADR-0011, ADR-0012 | **no** | untracked on disk; index in clean docs **links to missing files** |
| `docs/annotation-reality-check-p0-v0.1.md` | **no** | untracked |
| `scripts/models/*` | **no** | untracked |
| Qualification ledger | **no** (and should not ship as mutable claim without policy) | local only |

## README / status-snapshot claims that are **not** reproducible from Git

These statements appear in committed docs (`ef39fb4`) but **cannot** be verified from a clean checkout of that commit:

1. `runtime_qualification_status=PARTIALLY_VERIFIED` with registered MLX community fingerprint  
2. Source of truth `models/registry/default.json` / `training_program.json`  
3. Granite as provisional primary Train A **in code/config defaults**  
4. Outlines constrained decoding package path  
5. B4 39 cases, condition C F1 ≈ 0.17, `GO_LORA_P0`  
6. P0-alpha 2000/300 `SYN_G1_UNANCHORED`  
7. `HOLD_PENDING_REAL_ANCHOR` as machine-readable gate file  
8. Reality-check protocol tree, trial `HUMAN_SECOND_REVIEW_PACKET_READY`, Behrens pilot  
9. ADR-0011 / ADR-0012 bodies (only titles referenced from ADR README)  
10. Engineering smoke run path as repository evidence  

**Scientific honesty of the prose is fine for a local workstation description.**  
**As a description of the GitHub tip, it is currently over-claiming implementation presence.**

## Commands verified on clean checkout

| Command | Result |
|---------|--------|
| `uv sync --locked` | PASS |
| `uv run ntruth version` | PASS (`N-Truth 0.1.0 · schema 0.2.0`) |
| `uv run ntruth rules list` | PASS (32 rules) |
| `uv run ntruth analyze` synthetic fixture | PASS |
| `uv run ntruth-ml check` | PASS but **Qwen profile**, not Granite registry story |
| Paths for GraniteBackend / Outlines / B4 / P0 / annotation validator | **FAIL** (missing) |

## Dirty working tree (local only) — clusters that docs describe

From the developer workspace (~219 porcelain lines at verification time), **untracked** high-signal clusters include:

```text
packages/ntruth/model_backends/
models/registry/
models/configs/granite-4.1-3b-*.json
models/ntruth-granite-3b/
benchmarks/fewshot_p0/
scripts/models/
docs/adr/0011-*.md
docs/adr/0012-*.md
docs/annotation-reality-check-p0-v0.1.md
docs/training/p0-alpha-training-data-specification.md
tests/unit/test_model_backends.py
tests/unit/test_constrained_decoding.py
tests/unit/test_qualification_ledger.py
…
```

Plus large sets of **modified** tracked files (package, desktop, CI, etc.) not part of `ef39fb4`.

## Contradiction: Granite config status

In the **local** tree (not clean Git):

- Registry: `PARTIALLY_VERIFIED` + populated `qualified_artifact`  
- `models/configs/granite-4.1-3b-mlx-qlora.json`: may still say `UNVERIFIED` / null artifact  

**Policy for publication:** registry is canonical for qualification claims; config file must either mirror registry, declare itself a non-authoritative template, or be omitted from public docs until committed with a single-source-of-truth note.

## Annotation / `.gitignore`

```gitignore
data/annotations/*/
```

Effect: reality-check protocol materials under `data/annotations/reality-check/` are **not** published by default.  
**Decision required before any public claim** about pilot bundles:

- publish **schema + templates + protocol docs** only (whitelist paths), keep submissions local; or  
- keep entire tree private and **remove pilot/trial status tables from public README** until a public subset exists.

Do **not** force-add freezes, sources, or primary/second submissions without license/privacy review.

## Required sequence before push/merge

```text
1. Inventory local dirty clusters (implementation vs experiments vs secrets)
2. Technical commits (separate, reviewable):
   - model_backends + tests
   - registry schema + default.json (no weights, no sqlite ledger secrets)
   - granite configs with SoT note
   - B4 benchmarks (no private data)
   - p0-alpha synthetic snapshot if intended public
   - scripts/models
   - ADR 0011/0012 + annotation-reality-check doc
   - optional: whitelist reality-check schema/templates only
3. Test those commits on a clean worktree
4. Rebase/cherry-pick ef39fb4 (or rewrite docs) onto the versioned implementation tip
5. Re-run THIS clean-checkout verification → must pass
6. Conditional push of docs/implementation branches
7. Review → merge only when clean_checkout_docs_consistent=true
```

## Scientific gates (unchanged; not affected by this verification)

```yaml
scientific_validation_status: NOT_STARTED
training_execution_gate: HOLD_PENDING_REAL_ANCHOR   # local machine-readable only today
real_anchor_status: NOT_STARTED
trial_status: HUMAN_SECOND_REVIEW_PACKET_READY      # local only; not in clean Git
```

Documentation refresh is **not** a scientific gate. Human second-review trial continues independently and must not be blocked by this publication HOLD—except that **public GitHub text must not claim the trial is in-repo until artifacts are intentionally versioned**.

## Bottom line

| Question | Answer |
|----------|--------|
| Is the scientific tone of `ef39fb4` careful enough? | **Yes** (candidate-only, NOT_STARTED, HOLD language) |
| Does `ef39fb4` describe a clean GitHub checkout? | **No** |
| Push as official N-Truth status? | **Not yet** |
| Merge to `main`? | **HOLD** |

```text
DOCUMENTATION_CONTENT: APPROVED (as local/workstation narrative)
PUBLISHABLE_GITHUB_DOCS: FAIL_CLEAN_CHECKOUT
PUSH_TO_REMOTE: CONDITIONAL_FAIL
MERGE_TO_MAIN: HOLD
```
