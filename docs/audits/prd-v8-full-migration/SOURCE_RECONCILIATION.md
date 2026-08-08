# PRD v8.0 source reconciliation

**Audit ID:** `PRDV8-SOURCE-20260808`  
**Date:** 2026-08-08  
**Authoritative base:** `origin/main@fe089eff42c16e3fa55606be340c85df57c5442b`

## Sources inspected in full

| Source | SHA-256 | Size | Result |
|---|---|---:|---|
| `prd/N-Truth_PRD_scientifico_completo_v8.0.pdf` | `95a759ceaf91f6b9395bb1952667a72c31c8ba4fd78ba1bac6f94969d76d3db8` | 3,866,380 bytes | Authoritative PRD, 164 pages, text-based, no OCR-required pages |
| `prd/N-Truth_PRD_scientifico_completo_v8.0.md` | `8410c9d792fed7219baefc2d109404b4016a0cb7b33439325990d5d39ae8ad6d` | 232,074 bytes | Full source plus Appendix AE migration map; normatively equivalent except the rendering issue below |

The PDF was classified with PDF Inspector and converted to compact Markdown with page
markers before review. The source PDF was not modified. Figures and layout-dependent pages
13, 15, 18, 37, 58 and 60 were also inspected visually.

## Reconciliation result

The Markdown and the extractable PDF text contain the same normative PRD v8 contract.
Differences are line wrapping, table reflow, code-fence formatting and headings joined to the
preceding line, with one material PDF-rendering loss:

- Appendix K, action T06, PDF page 131 is truncated after `parse (1` because the unescaped
  pipe in `(1|donor/culture)` is treated as a table delimiter. The Markdown source preserves
  the complete action: parse the expression into donor and donor:culture grouping terms.

For T06 only, the intact Markdown source is the usable reading of the intended normative
text. This is a rendering correction, not a new scientific rule.

## Authority rule used for migration

1. The full PRD v8 text is authoritative.
2. Appendix AE is a migration map, not an independent authority.
3. Existing README, schemas, tests and historical audit artifacts are implementation
   evidence only and cannot override the PRD.
4. Internal contradictions that cannot be resolved from the PRD are fail-closed and entered
   in `SCIENTIFIC_REVIEW_REGISTER.md`; no inferred scientific mapping is silently adopted.
5. Historical v7 artifacts remain immutable. Compatibility is provided only through explicit,
   versioned input adapters or read-only projections.

## Clean-checkout truth

The audited implementation is the isolated worktree
`/Users/massimilianociconte/Documents/N-truth/.worktrees/prd-v8-full-20260808`, branch
`codex/prd-v8-full-migration-20260808`, at
`fe089eff42c16e3fa55606be340c85df57c5442b`. The historical worktree
`.worktrees/prd-v8-migration` is dirty and divergent and was used only as read-only reference;
none of its uncommitted state is accepted as current implementation evidence.
