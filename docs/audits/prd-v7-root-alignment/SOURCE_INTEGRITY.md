# Source integrity — PRD v7 root alignment

## Verified PDF hashes (local paths on main project tree)

| Artefact | Path | SHA-256 |
|----------|------|---------|
| PRD v7.0 | `prd/N-Truth_PRD_scientifico_completo_v7.0.pdf` | `00b544f04796f73f75e859c4cbff0ba4193a314661d50d5258d4bc9b0a13369f` |
| Assessment v1.0 | `prd/N-Truth_Qwen_review_assessment_v1.0.pdf` | `6dab65698d5e098b41e766f956118890958c4bfd3676442b62ee974a82820efc` |

PDFs are **not** committed by this branch unless repository policy explicitly allows it.

## Base commits

| Item | Value |
|------|-------|
| `origin/main` at branch creation | `0dcef3e54ca908d491726c4b7dfe810aa754549a` |
| Branch | `feat/prd-v7-root-alignment` |
| Dirty historical branch (do not modify) | `docs/full-documentation-refresh-20260802` |

## Safety boundary

No access to `/Volumes/FLASH128/` or dataset/private trees under it. No training,
model download, Lazic data access, or PR #4 / #5 modification.
