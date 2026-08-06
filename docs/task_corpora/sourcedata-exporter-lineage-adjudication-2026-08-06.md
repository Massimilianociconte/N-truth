# SourceData exporter-lineage adjudication — 2026-08-06

**Status:** COMPLETE — official-source investigation, read-only
**Outcome:** `EXPORTER_LINEAGE_SUPPORTS_METHOD_B`
**Question:** which XML text projection produced the locked v2.0.3
`token_classification` `text` field — the sd-tag `text`-attribute
substitution (Method A) or plain `itertext()` (Method B)?
**Method rule:** the answer is derived ONLY from the official SourceData
generation code, never inferred from match coverage. Coverage measurements
(§5) are corroboration, not evidence.

## 1. Official sources inspected

| Source | Revision | Provenance |
|---|---|---|
| `source-data/soda-data` (GitHub) | `3f57a17741b830c69c59ceb48deeb82de1505ae7` (2023-10-09) | v2.0.3-era exporter |
| `source-data/soda-data` (GitHub) | `85cc1b44c6f3c2293b41dfd8c7d5636771dbc40a` (2024-12-10, master) | parity cross-check |
| `EMBO/SourceData` (Hugging Face) loader `SourceData.py` | `9edc4cca16793a88e4fb9bbb560d7b07eda3bd69` (259 lines) | attested HF revision |
| `EMBO/SourceData` (Hugging Face) loader `SourceData.py` | `04333ae21badc91671a537e875bbca61b62f87e3` (430 lines) | attested HF revision |

The projection logic is IDENTICAL at both soda-data revisions; the attested
SHA-256 inputs of the reconciliation reference the HF revisions (the
`9edc4cca…`/`04333ae…` identifiers are Hugging Face repo commits, not
GitHub commits).

## 2. Source-record table

Every line cites repo, file, function and the verified line number.

| # | File (soda-data @ `3f57a17741b8`) | Function / location | What it establishes | Strength |
|---|---|---|---|---|
| 1 | `sdneo/xml_utils.py` | `generate_panel` (L139), `add_children_of_panels` (L165), attribute transfer (L221-225) | TaggedEntity/SmartNode properties — including `text` — are copied onto `sd-tag` ATTRIBUTES (`tag.attrib[k] = …`). The `text` property therefore exists in the XML only as `sd-tag@text`. | Direct |
| 2 | `dataproc/token_classification.py` | `class DataGeneratorForTokenClassification(XMLEncoder)` (L16-24) | Defaults: `xpath=".//sd-panel"`, `xpath_filter=".//sd-tag"`, `keep_xml=True`, `min_length=32`. | Direct |
| 3 | `dataproc/xml_extract.py` | `XMLExtractor.extract_xml_elements`, `_cleanup` (L400-403) → `utils.cleanup` (`dataproc/utils.py` L55-69) | Serialized sd-panel XML passes through `cleanup()`: `[\r\n\t]`→space, space-run collapse, `[–—‐−]`→`-`, leading `Abstract` stripped. Applied BEFORE text extraction. | Direct |
| 4 | `dataproc/token_classification.py` | `_encode_xml_example` (L238) → `_get_entity_labels` (L281), `inner_text = innertext(xml_element)` at **L284** | The record's `text` field is the element's inner text. | Decisive |
| 5 | `dataproc/utils.py` | `innertext` (L43): `"".join([t for t in xml.itertext()])` | Inner text = concatenated descendant text nodes. ATTRIBUTES ARE NEVER READ. | Decisive |
| 6 | `dataproc/token_classification.py` | `to_jsonl` writers (L220, L533): `json.dumps(..., ensure_ascii=False)` | JSONL written without ASCII escaping (the U+2028/U+2029 physical-line hazard the reconciliation handles explicitly). | Direct |
| 7 | HF `SourceData.py` @ both attested revisions | example generation, `"text": data["text"]` (L224/231/241/248) | The HF loader passes the exported `text` field through UNMODIFIED. | Direct |

## 3. The exporter chain

1. Panel captions are re-serialized as XML with sd-tag markup; entity
   properties land in **attributes** (record 1).
2. `DataGeneratorForTokenClassification` extracts panels keeping the XML,
   filtering to sd-tags (record 2), and the serialized XML is normalized by
   `cleanup()` (record 3).
3. For each example, `text = innertext(panel)` — text nodes only, attributes
   never read (records 4-5).
4. Records are written as JSONL with `ensure_ascii=False` (record 6) and the
   HF loader republishes `text` unchanged (record 7).

Conclusion: the locked `text` field is, by construction, the
`cleanup()`-normalized plain-itertext projection of the sd-panel. The
sd-tag `text` attribute (Method A's projection) is written into the XML but
never contributes to the exported `text` field.

## 4. Outcome and residual caveats

**`EXPORTER_LINEAGE_SUPPORTS_METHOD_B`** — recorded in the final
adjudication (vocabulary fixed by the authorisation; the sidecar was NOT
modified and Method A was NOT declared wrong: its projection is simply not
the one the exporter published).

Residual caveats (honest limits of the investigation):

- `cleanup()` normalizes whitespace, collapses space runs, maps four dash
  characters to `-` and strips a leading "Abstract". Both projections used
  by the reconciliation apply the same normalization before comparison, so
  the residual is bounded and quantified in §5 below.
- The investigation reads the official repository code; it cannot observe
  the historical runtime invocation itself. Parity between the v2.0.3-era
  and master revisions materially reduces this risk.
- No inference was drawn from match coverage anywhere in this section.

## 5. Measured corroboration (projection equivalence, locked bundle)

Measured on the locked bundle (77,688 matchable units vs 73,126 locked
raw texts; full rows outside Git):

| Category | Units |
|---|---|
| projections_identical | 74,048 |
| itertext_matches_exporter | 1,114 |
| attribute_matches_exporter | **0** |
| both_match_distinct_locked_texts | 0 |
| neither_matches_exporter | 2,492 |
| exporter_unavailable_for_unit | 34 |

For all 1,090 METHOD_B_ONLY records: `itertext == locked text` in 1,090/1,090
cases; `attribute != locked text` in 1,090/1,090; `attribute == some OTHER
locked text` in **0** cases (zero identifier conflicts introduced).

The measurement corroborates the official-source conclusion: wherever the
two projections diverge, the exporter text is the itertext projection; the
attribute projection matches the exporter for zero units.

## 6. Consequences

- Adjudication outcome recorded:
  `METHOD_B_LABEL_INDEPENDENT_REPRODUCED_ZERO_IDENTIFIER_CONFLICTS` with
  `exporter_lineage = EXPORTER_LINEAGE_SUPPORTS_METHOD_B`.
- Any adoption of Method B's projection in a future sidecar version remains
  a separately authorised human decision; `sidecar_regenerated = false`.
- The human adjudication dossier (review packet, sanitized identifiers and
  hashes only, no corpus text in Git) lives outside Git under
  `/tmp/ntruth-sourcedata-provenance-final-review/` and references this
  document's evidence for the EXPORTER_PROJECTION_DISAGREEMENT category.
