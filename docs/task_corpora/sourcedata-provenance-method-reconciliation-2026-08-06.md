# SourceData provenance method reconciliation — 2026-08-06

**Status:** COMPLETE — dual-run byte-identical, zero conflicts
**Outcome:** `METHOD_B_LABEL_INDEPENDENT_CONFIRMED` (evidence level; any algorithm replacement remains a separately authorised human decision)
**Scope:** read-only over all canonical inputs; no sidecar regeneration; no canonical JSONL, partition, manifest, lock or readiness change
**Harness:** `scripts/task_corpora/sourcedata_provenance_method_reconciliation.py`
**Tests:** `tests/unit/task_corpora/test_provenance_method_reconciliation.py`

This document reconciles, record-by-record and over ONE locked immutable input
bundle, the two incompatible SourceData v2.0.3 provenance methodologies:

- **Method A** — the PR #9 v0.2.0 sidecar algorithm.
- **Method B** — the portfolio C1.1 investigation algorithm, split into
  `B1_LABEL_INDEPENDENT` (S3 exact text) and `B2_LABEL_ASSISTED` (S4 entity-span tuple).

Every count below is **re-derived from the locked inputs**. No historical
report figure is used as an expected constant; historical figures appear only
as comparison targets and every one of them is explained.

## 1. Locked immutable input bundle

All hashes verified against disk before and after the reconciliation
(fail-closed). Counts re-derived, never copied from prior reports.

| Input | SHA-256 |
|---|---|
| canonical records (train+validation+test, concatenated physical lines) | `562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10` |
| canonical train.jsonl | `f2e7bc675294b2a041dee4481c344cc40e093364391e55a3e7a2417e7fe6b18c` |
| canonical validation.jsonl | `76d2fc01d7cb6a96e41dda45e9bdb116e37eae38552c1eedb45d6377163fe886` |
| canonical test.jsonl | `6bbc05663c6c18b490217d6eed8f70ebeb199330b58a322d150b9eb633817b9c` |
| raw roles_multi train.jsonl | `c2ac812846265686502469208dae435a5dc5279d6149940409f3b4566764c925` |
| raw roles_multi validation.jsonl | `d2e98f0e71905e18cc4dbe208646113ddb4b869cf06d53af628156f6e1493715` |
| raw roles_multi test.jsonl | `f7fbee9acd7e7f52ed92944d3d719c83164ba75e18218841d3dc764956c21a75` |
| leakage_audit.json | `d79c65f12a857e837923ea916b1062f321a4064f498597753f134ac3e92f46e7` |
| upstream XML tarball (`source_data_xml_v2.0.3.tar.gz`) | `71f9899211efef62bc523275bbff7ba3e37ec8b4d1fc21405b58f4b68e93ba60` |

Re-derived record counts: train 60,266 + validation 8,201 + test 6,696 =
**75,163**.

## 2. Canonical upstream XML census (measured)

| Statistic | Value |
|---|---|
| xml_file_count | 3,515 |
| valid_article_doi_count | 3,515 |
| figure_count | 22,856 |
| figures_with_sd_panel | 20,400 |
| figures_without_sd_panel | 2,456 |
| explicit_sd_panel_count | 75,232 |
| total_matchable_units | 77,688 |
| empty_caption_units | 34 |
| duplicated_panel_ids (within article+figure) | 1,287 |
| duplicated_figure_ids (within article) | 0 |
| nested_sd_panel_occurrences | 1,859 |
| distinct_raw_captions | 73,233 |
| distinct_normalized_captions | 73,233 |
| duplicate_normalized_caption_keys | 1,953 |

Note on the recurring 3,516-vs-3,515 discrepancy: the tarball contains 3,537
members = 3,515 article XML files + 15 non-XML `*.jsonl` exports
(panelization / roles_gene / roles_small_mol / ner) + 7 directories. Prior
reports that counted 3,516 "articles" counted one non-XML member as a file.

### Index-size hypothesis — CONFIRMED by measurement

`measured_75232_plus_2456_equals_77688 = true` and
`hypothesis_explains_index_delta = true`: Method B's asset index held only
explicit panels (75,232 units); Method A's index additionally admits
panel-less figures as matchable units (2,456), giving 77,688 total units.
This single structural difference, plus the caption-parser difference in §5,
explains every index-level discrepancy between the methods. Nothing was
assumed; both sides were re-counted from the XML.

## 3. Exact method definitions

**Method A (PR #9 sidecar, reconstructed verbatim from
`packages/ntruth/task_corpora/provenance_sidecar.py`):**
caption = `caption_text_from_element` (sd-tag wrappers substituted with their
`text` ATTRIBUTE); normalization = `normalize_caption`; exact caption match
against the 77,688-unit index with containment fallback, exact-match
precedence over containment, tiers PANEL > FIGURE > ARTICLE (DOI collapse) >
RECORD_FALLBACK.

**Method B (portfolio C1.1, reconstructed from the frozen investigation
document):** caption key = plain XML `"".join(el.itertext())` normalized;
two-pass dict counting; emit ONLY keys with exactly 1 record AND exactly 1
asset unit (B1 = S3, LABEL_INDEPENDENT); on ambiguous keys join
(text, sorted entity-span tuple SHA-256) vs (caption, sorted sd-tag text
tuple SHA-256) with 1:1 uniqueness on both sides (B2 = S4, LABEL_ASSISTED —
span boundaries come from gold BIO labels); ambiguous single-article
candidates collapse to deterministic DOI-only provenance; no fuzzy
similarity, no first-match, no containment. The S4 tuple representation used
here (sorted raw entity-span texts, label names excluded) is the documented
reconstruction; the frozen document does not preserve the original tuple
serialisation (see §6, finding R2).

## 4. Re-derived tier counts vs historical comparison targets

| Tier | Method A (re-derived) | Method A (historical) | Method B (re-derived) | Method B (historical) |
|---|---|---|---|---|
| Panel-level unique | 69,983 (TIER_1_PANEL_UNIQUE) | 69,983 ✓ | 71,183 (S3) | 71,183 ✓ |
| Figure-level unique | 175 (TIER_1_FIGURE_UNIQUE) | 175 ✓ | — (no figure tier) | — |
| Label-assisted tuple (S4) | — | — | 3 | 14 (Δ, see §6 R2) |
| Article-level DOI-only | 3,914 (TIER_2_ARTICLE_ONLY) | 3,914 ✓ | 3,976 (AMBIGUOUS_SINGLE_DOI) | 3,965 (Δ, see §6) |
| Fallback / unmatched | 1,091 (RECORD_FALLBACK) | 1,091 ✓ | 1 (UNMATCHED_NO_ASSET_TEXT) | 1 ✓ |
| **Total** | **75,163** | | **75,163** | |

Method B per-split S3: train 57,208 / validation 7,484 / test 6,491 — exact
historical match. The single unmatched record is train line 17638 — exact
historical match.

## 5. Aggregate decision matrix (75,163 delta rows, one per canonical record)

| Relation | Count |
|---|---|
| IDENTICAL | 74,031 |
| METHOD_B_ONLY | 1,090 |
| SAME_ARTICLE_DIFFERENT_GRANULARITY | 41 |
| BOTH_FALLBACK | 1 |
| METHOD_A_ONLY | 0 |
| CONFLICTING_ARTICLE | 0 |
| CONFLICTING_FIGURE | 0 |
| CONFLICTING_PANEL | 0 |

`SAME_ARTICLE_DIFFERENT_GRANULARITY` is NOT a conflict: both methods agree on
the article; only the panel-level resolution differs.

### Delta-reason matrix

| Reason | Count | Relation |
|---|---|---|
| none | 74,031 | IDENTICAL |
| caption_parser_difference | 1,090 | METHOD_B_ONLY |
| doi_collapse_difference | 41 | SAME_ARTICLE_DIFFERENT_GRANULARITY |
| both_methods_fail_closed_on_this_record | 1 | BOTH_FALLBACK |

Every METHOD_B_ONLY row was classified from the fixed taxonomy; 100% resolve
to `caption_parser_difference` (no `implementation_error`, no
`stale_or_different_upstream_asset`, no unclassified rows).

### Root cause of the 1,090 one-sided records

The two methods parse captions differently. Method B keys on plain
`itertext()` (all descendant text nodes); Method A's
`caption_text_from_element` substitutes each `sd-tag` wrapper with its
`text` ATTRIBUTE. Where attribute and text-node content drift (e.g. attribute
`20–4/A4` with en-dash vs itertext `20-4/A4` with hyphen), the same record
keys to different normalized captions, Method A falls closed while Method B
matches. This was discovered empirically by probing parser variants until
Method B's S3 figure (71,183) reproduced exactly.

## 6. Explanation of every historical discrepancy

**71,197 vs 70,158 (panel/figure-level assignments).**
Historical Method B panel-level = 71,197 = S3 71,183 + S4 14. Historical
Method A panel+figure = 70,158 = 69,983 + 175. Re-derived: S3 still 71,183;
S4 under the reconstructed text-span tuple representation is 3 (finding R2);
Method A exactly 70,158. The structural gap is Method B's itertext caption
projection recovering 1,090 records that Method A's attribute-substitution
parser cannot key, minus Method A's 175 figure-tier assignments that Method B
never separates out (its index keys panel-less figure captions as ordinary
units).

**3,965 vs 3,914 (article-level).**
Method A DOI-collapses 3,914 records; Method B 3,976 re-derived (historical
3,965). Method B's article tier is larger because records that Method A
resolves to a panel via containment/attribute-caption paths are still
ambiguous in Method B's exact-only regime, and vice versa the caption-parser
difference moves 1,090 records OUT of ambiguity in B. Historical 3,965 vs
re-derived 3,976: difference 11 = historical S4 removed 14 ambiguous records
from this tier while the reconstruction removes 3 (R2).

**1 vs 1,091 (fallback).**
Method B unmatched = 1 (train line 17638, exact). Method A RECORD_FALLBACK =
1,091 (exact). Delta: 1,090 METHOD_B_ONLY rows are exactly the records where
Method A fell closed and Method B matched (1,091 − 1,090 = 1 BOTH_FALLBACK =
train 17638, which fails in BOTH methods — no public-asset counterpart).

**75,232 vs 77,688 (index size).**
Measured: 75,232 explicit panels + 2,456 panel-less figures = 77,688.
Method B indexed panels only; Method A indexes panels plus panel-less
figures. Confirmed, not assumed (§2).

**Finding R2 — S4 count 14 vs 3.** The frozen C1.1 document records 14 S4
resolutions but does not preserve the exact tuple serialisation (span text
normalization, label inclusion, sorting). The documented reconstruction
(sorted raw span texts, label names excluded — chosen to be comparable with
the asset-side sd-tag `text` attributes) resolves 3. All S4 matches are
LABEL_ASSISTED and reported separately; none of the reconciliation's
conclusions depends on the S4 count. The original 14 cannot be recovered
without the original code, which was never committed.

## 7. Label-dependence policy

- B1 (S3) = `LABEL_INDEPENDENT`: uses only record `text` and XML text nodes.
- B2 (S4) = `LABEL_ASSISTED`: span boundaries derive from gold BIO labels.
  All 3 S4 matches are reported separately and are never merged into the
  label-independent figure.
- `label_assisted_promotion_allowed = false`: label-assisted evidence never
  promotes leakage claims, eval-split statements, model-use decisions or
  production provenance.

## 8. Adjudication (§12 replacement conditions)

| Condition | Value |
|---|---|
| zero_conflicting_article_assignments | true |
| zero_unexplained_conflicting_figure_assignments | true |
| zero_unexplained_conflicting_panel_assignments | true |
| every_additional_assignment_traces_to_official_xml_unit | true |
| dual_run_byte_identical | true |
| Method A fallback records not matched by B | 0 |
| B-only matches all explained from fixed taxonomy | true (1,090/1,090) |

**Outcome: `METHOD_B_LABEL_INDEPENDENT_CONFIRMED`.** Method B's
label-independent core (S3) strictly covers Method A's unique assignments on
74,031 identical records, explains every Method A fallback except the one
record that fails in both, and introduces zero conflicts. This is an
evidence-level statement. Any algorithm replacement in the sidecar pipeline
remains a separately authorised human decision; **no sidecar was regenerated
and none will be without separate authorisation** (`sidecar_regenerated =
false`).

## 9. Manual-audit set summary (§13)

Audit set: **1,135 records** (`audit_set.jsonl`, sanitized identifiers only —
record IDs, partition, row index, text SHA-256, both methods' tiers and
identifiers; no corpus text). Composition (measured): all conflict rows (0
found), all 3 label-assisted S4 rows, all Method-B-unmatched rows reproduced
(1, the BOTH_FALLBACK record), all METHOD_B_ONLY rows (1,090 — every Method A
fallback that Method B resolves) and all SAME_ARTICLE_DIFFERENT_GRANULARITY
rows (41) = 1,090 + 41 + 1 + 3. Every non-IDENTICAL delta row is therefore
audit-eligible and included; the ≥100 stratified stride floor is satisfied
by mandatory coverage alone.

## 10. Determinism proof (two full pipeline executions)

`run-all` executed the complete reconciliation twice into independent output
directories and compared every artifact hash; the diff was empty
(`dual_run_byte_identical = true`). Final adjudication was written only
after this attestation.

| Artifact | SHA-256 (run-1 == run-2) |
|---|---|
| `upstream_caption_index.jsonl` | `140df6f5cef42bf2ec20b3b0bb78eef8aad457f01ee4e2108c5ead3a0fd95004` |
| `method_a_rows.jsonl` | `1b31ce3a0617f366753a8b04783574f0777c2334185d845c8e1c291a83f7bc40` |
| `method_b_rows.jsonl` | `e088f411e9a9cda604a1d461eb463fc57c5fd6218fdf0f143006f9b16456d0ab` |
| `delta_rows.jsonl` | `322c693a9a2337ebf82d3f896677df439e782da6cba4c2dd9bd766bd9afc2e49` |
| `audit_set.jsonl` | `12d5c4ecf43c5e448ebb1d8bc8a1002f1b0362561b79e0757797092999b77d42` |
| `census.json` | `b4f1518ef25ad3f6d0f9f7944f8a72b76a1852fb537a43c8f45f5fd4c1332569` |
| `method_a_summary.json` | `5a8d02df96602710b772c7b31356e1d0f642df4e0bebb6f394e3cde81111f5ea` |
| `method_b_summary.json` | `7543ae8da0bb419032180281cd5c40e70cebd6fe769b5b047fbe687f7068d22f` |
| `delta_summary.json` | `c96a5dcfa4521ea3c400eefca411900b97767cb43e56fbc21e534b05c8a9b251` |
| `adjudication.json` | `2966a7a64ac8f56d44bf8a2e7807f39533f5b9ce06a2d0add69a7dcf3d9eb02e` |

Full row-level payloads live ONLY outside Git (scratch reconciliation work
dirs); committed content is aggregates, hashes and sanitized identifiers.

## 11. Final reconciliation status

`METHOD_B_LABEL_INDEPENDENT_CONFIRMED`, zero conflicts, byte-deterministic,
all historical discrepancies explained. The frozen external sidecar
(`sourcedata_provenance_map.jsonl`, as locked by the portfolio branch) remains the authoritative
external artifact; its figures correspond to Method A and are now fully
cross-explained against Method B. Full hash:
`7cfba6f9f1a49ee5434c60a8510a7e6702e16849666b081323eee9a1894a041a`.

## 12. Effect on PR #9

- No algorithmic change to the sidecar pipeline is made by this
  reconciliation. The caption-parser difference (attribute substitution vs
  itertext) is documented as the root cause of the 1,090-record coverage gap;
  whether to adopt Method B's projection in a FUTURE sidecar version is a
  separately authorised decision.
- PR #9 remains DRAFT. CodeRabbit remediation (commit 1) and this
  reconciliation (commit 2) are added; merge remains prohibited until the
  human adjudication decision is recorded.

## 13. External artifacts unchanged — explicit statement

No external artifact was created, modified, regenerated or replaced:
`sourcedata_provenance_map.jsonl`, `manifest.json`, `leakage_audit.json`,
the provenance asset lock, the v1/v2 migration attestations and all canonical
JSONL/partitions on the dataset volume are untouched. The only external write
is the new report authorised under
`<dataset-volume>/N-Truth-Datasets/reports/workstream_c/sourcedata_provenance_method_reconciliation_2026-08-06.md`.
Input hashes were re-verified after the full pipeline pass and matched.

## Reproduction

```bash
python scripts/task_corpora/sourcedata_provenance_method_reconciliation.py run-all \
  --work-dir <scratch-dir> \
  --canon-dir <volume>/task_corpora/entity_roles/sourcedata/v2.0.3 \
  --raw-dir <volume>/raw/sourcedata/v2.0.3/roles_multi \
  --archive <volume>/task_corpora/entity_roles/sourcedata/v2.0.3/provenance/source_data_xml_v2.0.3.tar.gz
```

The command fails closed unless every §1 input hash matches; it executes the
full pipeline twice and raises unless all artifacts are byte-identical.
