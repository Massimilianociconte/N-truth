# N-Truth dataset portfolio status — 2026-08-06

| Field | Value |
|---|---|
| Date | 2026-08-06 |
| Branch | `chore/dataset-portfolio-completion-bia-metadata-v1` |
| Base SHA | `8afe8e0e35adfcae023316d58346685638c91f18` (origin/main, verified after fetch) |
| Operation class | DOCUMENTATION_ONLY — status consolidation, Phase E classification, metadata-pilot reporting. No data mutation, no downloads, no model operation. |

## Immutable references

| Reference | Value |
|---|---|
| SourceData entity_roles `records_sha256` | `562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10` (counts 60,266 / 8,201 / 6,696; `groups_crossing_splits` 0) |
| Canonical Merkle root | `5aec5f862168a0f38b29fcd71f29eb4d6d9dd072dda1a3c4c3786f4e7d8c7e40` (byte-identical across two verify passes) |
| SourceData pin | v2.0.3, HF rev `b457c14041b61c56f671c6f966b4324f682855b7` (dead upstream — see C1.1 investigation) |
| PreClinIE pin | `f38df55a28505a77d30eefb5b867bbfdcc9baf25` |
| MeasEval pin | `1fa738b6bc9b72c84c88a80344ca3ab39a310a44` |
| CRAFT pin | `v5.0.2` |
| Archive SHA-256 (PreClinIE) | `3aa37a6d801d8475093c94b3d44c709d08ed0c1a60a920e230f60208f2b4d5e7` |
| Archive SHA-256 (MeasEval) | `c53b28506befad2edf6da7f9782c7711c6f955d34322425a60d3743f05d8fd57` |
| Archive SHA-256 (CRAFT) | `56677e5110f81303642f49ec21dce9d55e38c95cef1162212514d8b2c73077f2` |
| entity_roles manifest SHA-256 (Gate-0 pin, v0.2.2) | `5b537b9f5884bc29370ea57ba581595856a49650ace59d1d2acdd4697c38002f` (see post-operation note below) |
| SourceData XML asset LFS SHA-256 | `71f9899211efef62bc523275bbff7ba3e37ec8b4d1fc21405b58f4b68e93ba60` (join asset; see C1.1 investigation) |

Dataset root is the conventional pinned root `DEFAULT_DATASET_ROOT` from `packages/ntruth/data/config.py`.

**Post-operation note (SourceData entity_roles manifest):** the manifest SHA-256 pinned above (`5b537b9f…`, manifest v0.2.2, pinned by PR #7) is the Gate-0 fact of THIS operation. After this operation's Gate 0 and verification passes, a separately authorised concurrent operation (branch `feat/sourcedata-provenance-sidecar-v1`, commit `2d4a6d4`) performed an additive provenance-sidecar migration bumping the manifest v0.2.2 → v0.3.0 (new SHA-256 `6174f9b508fde36c1f63645526d9586474b89efe718c33ebd2b1d278935c4494`), adding `provenance/source_data_xml_v2.0.3.tar.gz` (SHA-256 `71f9899211efef62bc523275bbff7ba3e37ec8b4d1fc21405b58f4b68e93ba60`) and `provenance/sourcedata_provenance_map.jsonl` (SHA-256 `d452c49c31d8ecc2c1496971f6b8cfff67701402dc7db03266a613649ba95e07`). Canonical records were untouched by that migration (`records_sha256 `562b6ac933c13f05a0ea536696857e7e11dd5a324503d1fe930d26149d071b10` re-validated after it). This portfolio operation itself performed no canonical JSONL or manifest writes.

## Storage report (before-state, 2026-08-06)

| Item | Value |
|---|---|
| Mounted path | `/Volumes/FLASH128` |
| Filesystem | FAT32 (4 GiB single-file limit) |
| Capacity / used / free | 49 GiB / 7.6 GiB / 42 GiB (asserted ≥ 10 GiB — PASS) |
| Total used by N-Truth-Datasets | 7,176,192 KiB ≈ 6.84 GiB |
| Top-level sizes | raw 3.6 G · processed 94 M · downloads 1.8 G · training_ready 257 M · task_corpora 329 M · cache 734 M |
| Largest existing file | `downloads/preclinie-f38df55a….zip` — 1,784,087,121 B (≈1.66 GiB « 4 GiB FAT32 limit) |
| Largest proposed new file | **none** — all four corpora VERIFIED_PRESENT; no downloads required |

Per-dataset sizes (raw / processed / task corpus):

| Dataset | raw | processed | task corpus |
|---|---|---|---|
| sourcedata v2.0.3 | 252,512 KiB (14 files) | 928 KiB (14 files) | entity_roles 336,576 KiB |
| preclinie `f38df55a…` | 2,779,712 KiB (6,454 files) | 88,608 KiB (18 files) | n/a |
| measeval `1fa738b…` | 170,176 KiB (5,272 files) | 1,728 KiB (12 files) | n/a |
| craft v5.0.2 | 603,040 KiB (6,231 files) | 4,480 KiB (9 files) | n/a |

Cache: 751,296 KiB total (pip/huggingface/git). `training_ready/sourcedata_multitask`: 263,168 KiB.

Cache attribution was attempted: pip/HuggingFace/git caches store transformed artefacts without per-dataset keys, so per-dataset cache attribution is not possible; the shared cache total above is reported instead.

## Phase A preflight table

Classification vocabulary (seven status classes):

```text
VERIFIED_PRESENT | PRESENT_BUT_UNVERIFIED | INCOMPLETE | CORRUPT | MISSING | VERSION_MISMATCH | LICENCE_REVIEW_REQUIRED
```

| Field | SourceData | PreClinIE | MeasEval | CRAFT |
|---|---|---|---|---|
| dataset_id | sourcedata | preclinie | measeval | craft |
| expected version/revision | v2.0.3 (HF rev `b457c14041b61c56f671c6f966b4324f682855b7`) | `f38df55a28505a77d30eefb5b867bbfdcc9baf25` | `1fa738b6bc9b72c84c88a80344ca3ab39a310a44` | v5.0.2 |
| actual version/revision | v2.0.3 (`b457c140…`) | `f38df55a…` | `1fa738b6…` | v5.0.2 |
| acquisition status | ACQUIRED (HF files pinned in datasets.json/lock) | ACQUIRED (archive + `.ntruth_complete.json`) | ACQUIRED (archive + `.ntruth_complete.json`) | ACQUIRED (archive + `.ntruth_complete.json`) |
| raw status | PRESENT (6/6 JSONL) | PRESENT (6,454 files) | PRESENT (5,272 files incl. `data/trial`) | PRESENT (6,231 files) |
| processed status | PRESENT (14 files) | PRESENT (18 files) | PRESENT (12 files incl. `trial/records.jsonl`) | PRESENT (9 files) |
| manifest status | datasets.json + splits.json + lock OK | datasets.json + splits.json OK | datasets.json + splits.json OK (`training_ready_status=BLOCKED_BY_UPSTREAM_GROUP_OVERLAP`) | datasets.json + splits.json OK |
| verification status | VERIFIED (6/6 raw SHA + 4/4 task-corpus SHA) | VERIFIED (archive SHA + Merkle) | VERIFIED (archive SHA + Merkle) | VERIFIED (archive SHA + Merkle) |
| raw bytes | 252,512 KiB (~247 MiB) | 2,779,712 KiB (~2.65 GiB) | 170,176 KiB (~166 MiB) | 603,040 KiB (~589 MiB) |
| processed bytes | 928 KiB | 88,608 KiB (~87 MiB) | 1,728 KiB | 4,480 KiB |
| cache bytes | shared volume cache (751,296 KiB total; not attributable per dataset) | same | same | same |
| record count | 75,163 (60,266 / 8,201 / 6,696) | 1,450 (1,160 / 146 / 144) | 448 (218 / 30 / 135 / trial 65) | 97 (60 / 7 / 30) |
| file count | raw 14 / processed 14 | raw 6,454 / processed 18 | raw 5,272 / processed 12 | raw 6,231 / processed 9 |
| largest file | `raw/sourcedata/v2.0.3/ner/train.jsonl` 104,663,617 B | `processed/preclinie/…/train/records.jsonl` 45,054,765 B (raw largest 36,349,822 B) | `processed/measeval/…/train/records.jsonl` 594,233 B | `raw/craft/v5.0.2/…/NCBITaxon+extensions.obo.zip` 21,284,123 B |
| SHA-256 / Merkle state | raw 6/6 pinned SHA PASS; task corpus 4/4 PASS; Merkle root `5aec5f86…8c7e40` PASS | archive SHA PASS; Merkle PASS | archive SHA PASS; Merkle PASS | archive SHA PASS; Merkle PASS |
| licence state | CC-BY-4.0 claimed on HF card; `LICENCE_REVIEW_REQUIRED` (model_training `PENDING_SCOPE_FILE_PROOF`) | MIT repo LICENSE verified; annotation/PDF-text scope unclear → `LICENCE_REVIEW_REQUIRED` | NO LICENSE file upstream; README cites CC-BY (ScienceDirect/OA-STM) → `LICENCE_REVIEW_REQUIRED`; training `BLOCKED_BY_POLICY_AND_LICENSE` | CC-BY-3.0 annotations; `LICENSE_SCOPE_VERIFIED` |
| development permission | local processing yes; training pending licence scope closure | local processing yes for repo snapshot; training pending scope confirmation | local use only pending review | allowed as SILVER_AUXILIARY with attribution |
| training permission | PENDING_SCOPE_FILE_PROOF | PENDING_SCOPE_CONFIRMATION | blocked by policy + licence + upstream group overlap | SILVER_AUXILIARY allowed with attribution |
| evaluation permission | yes (licence-scoped) | yes (licence-scoped) | local use only pending review | yes |
| task adapter status | `sourcedata_entity_roles` VERIFIED (`records_sha256 562b6ac9…`; 60,266/8,201/6,696; groups_crossing_splits 0) | none (silver auxiliary) | none (silver auxiliary) | none (silver auxiliary) |
| scientific role | HUMAN_CURATED_GOLD reality-gate reference corpus (reality_gate_ref commit `f2faace47178`, status BLOCKED upstream of this operation); `engineering_readiness VERIFIED_FOR_C0_C1` | SILVER_AUXILIARY gold-annotated preclinical corpus | SILVER_AUXILIARY gold-annotated measurement corpus (train/test group overlap is upstream) | SILVER_AUXILIARY gold-annotated biomedical corpus |
| blockers | licence scope closure (non-data) | licence scope confirmation for publication text (non-data) | licence review + upstream train/test group overlap (data complete; NOT training-ready by policy) | none |
| **classification** | **VERIFIED_PRESENT** (+ licence note) | **VERIFIED_PRESENT** (+ licence note) | **VERIFIED_PRESENT** (+ `LICENCE_REVIEW_REQUIRED` note) | **VERIFIED_PRESENT** |

Notes:

- **MeasEval `data/trial` stale-log note.** `data/trial` EXISTS locally (ann/brat/tsv/txt) and exists inside the pinned upstream archive. The 2026-08-03 log line `ERROR: MeasEval split lacks text/tsv directories: …/data/trial` is STALE: it was written before extraction completion and before later processing; `processed/measeval/…/trial/records.jsonl` exists with 65 records. No action required.
- **`dataset_files.sha256` known gap.** `manifests/checksums/dataset_files.sha256` does not exist (legacy-tool artifact). Noted per plan; not treated as CORRUPT; not created.
- **MeasEval overlap policy.** `training_ready_status = BLOCKED_BY_UPSTREAM_GROUP_OVERLAP` — the upstream train/test overlap must NOT be fixed by moving records; role stays SILVER_AUXILIARY.

## Phase B result — NO_COMPLETION_REQUIRED

Phase A classified all four corpora VERIFIED_PRESENT. Per the approved plan, nothing was downloaded, no repair plan was generated. Idempotence was proven by two full verification passes:

| Pass | Command | Merkle root | `merkle_manifest.json` vs snapshot |
|---|---|---|---|
| 1 (Phase A step 7) | `uv run python -m ntruth.data.acquire verify` | `5aec5f862168a0f38b29fcd71f29eb4d6d9dd072dda1a3c4c3786f4e7d8c7e40` | byte-identical (diff exit 0) |
| 2 (Phase B) | same | `5aec5f862168a0f38b29fcd71f29eb4d6d9dd072dda1a3c4c3786f4e7d8c7e40` | byte-identical (diff exit 0) |

Both roots equal each other and equal the canonical pin. No restore was needed; the only sanctioned write (the idempotent Merkle rewrite) produced a byte-identical file.

## Phase E classification — external candidate sources (no downloads performed)

All items below were classified from documentation and official-interface review only. No content was downloaded in this operation.

| Source | Classification | Notes |
|---|---|---|
| PMC Open Access subset | FUTURE_PROFILE | Possible OA Methods/caption source. Official interfaces identified at documentation level only: PMC Open Access Subset web service / FTP, and Europe PMC REST API. Licensing filters must apply at acquisition time; nothing acquired. |
| ISA / BioStudies / SDRF | FUTURE_PROFILE | Metadata/provenance ecosystem standards — record schemas and exchange formats, not one downloadable corpus. Relevant as schema-alignment references (see BioImage/REMBI pilot). |
| OME / OMERO | FUTURE_PROFILE | Imaging metadata/interoperability mapping implications for the Imaging Profile (OME data model, OME-Zarr, OMERO object model). No corpus to acquire. |
| Cell Painting (Cell Painting Gallery / JUMP-CP) | FUTURE_PROFILE | Future auxiliary plate-mapping/scalability source. Candidate public datasets (Cell Painting Gallery, JUMP-CP consortium) are TB-scale — far beyond current volume headroom and pilot budgets. Classified FUTURE_PROFILE; no download, no sampling. |
| Lazic in vivo pseudoreplication data | ROLE_DECISION_PENDING / NOT_RECEIVED | No access, no download, no label inspection. Profile-relative role decision required before any label access (PRD v7 §14.4). |
| NC3Rs ARRIVE compliance checker dataset | ANNOUNCED_NOT_RELEASED | Not released; no download attempted; AUXILIARY_CANDIDATE only; NC3Rs is not a partner or endorser. |

## Full portfolio matrix

Pipeline-state vocabulary (strictly distinguished): `ACQUIRED → PROCESSED → TASK_ADAPTER_READY → MODEL_USE_ELIGIBLE → SCIENTIFIC_GOLD`. **None of the public corpora is SCIENTIFIC_GOLD or MODEL_USE_ELIGIBLE; all remain SILVER_AUXILIARY at best.**

| Dataset / source | Source type | Local presence | Current bytes | Official version | Licence | Permitted uses | Target task | Profile | Adapter | Provenance quality | Leakage-group quality | Role | Download decision | Reason | Next operation | Blocker | Est. additional storage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SourceData v2.0.3 | public silver corpus (Hugging Face) | ACQUIRED + PROCESSED + TASK_ADAPTER_READY | raw 252,512 KiB + processed 928 KiB + task corpus 336,576 KiB | v2.0.3 (pin `b457c140…`, dead upstream) | CC-BY-4.0 claimed; LICENCE_REVIEW_REQUIRED | local processing; dev/training fail-closed; evaluation pending licence | biomedical_entity_extraction, assay_extraction, experimental_role_tagging, caption_parsing | Bootstrap in vitro (engineering reference) | `sourcedata_entity_roles` VERIFIED | RECORD_LEVEL_FALLBACK; C1.1 = RECOVERABLE_PARTIAL_DETERMINISTIC (not implemented) | groups_crossing_splits 0 at RECORD granularity; document-level UNVERIFIED | Reality-Gate reference corpus; AUXILIARY for token tasks — not model-use gold | ALREADY_ACQUIRED | byte-verified against pins; 13/13 streaming SHA checks PASS | C1.1 migration (separately authorised future task) + licence scope closure | licence scope closure (non-data); HF pin dead upstream | 0 |
| PreClinIE `f38df55a…` | public silver corpus (GitHub archive) | ACQUIRED + PROCESSED | raw 2,779,712 KiB + processed 88,608 KiB | `f38df55a…` | MIT repo LICENSE; publication-text scope unclear → LICENCE_REVIEW_REQUIRED | local processing; dev/training fail-closed | ROUTING, REPORTED_METHOD_INDICATOR, EVIDENCE_SPAN_CANDIDATE (C2, DESIGN_ONLY) | cross-domain vs in vitro bootstrap | none | upstream publication linkage; no document join audited | split files present; group audit pending adapter | SILVER_AUXILIARY — never experimental_unit/allocation/independent_n gold | ALREADY_ACQUIRED | archive SHA + Merkle PASS | C2 adapter implementation (future PR) | licence scope confirmation (non-data) | 0 |
| MeasEval `1fa738b…` | public silver corpus (GitHub archive) | ACQUIRED + PROCESSED | raw 170,176 KiB + processed 1,728 KiB | `1fa738b…` | NO LICENSE file upstream → LICENCE_REVIEW_REQUIRED; training BLOCKED_BY_POLICY_AND_LICENSE | local use only pending review | quantity_extraction, unit_extraction, measurement_context_extraction, measurement_relation_extraction | measurement metadata auxiliary | none | upstream article grouping known; train/test overlap upstream | BLOCKED_BY_UPSTREAM_GROUP_OVERLAP — must not be fixed by moving records | SILVER_AUXILIARY | ALREADY_ACQUIRED | archive SHA + Merkle PASS; `data/trial` present | upstream train/test overlap resolution design + licence review (future) | licence + upstream group overlap (policy) | 0 |
| CRAFT v5.0.2 | public silver corpus (GitHub archive) | ACQUIRED + PROCESSED | raw 603,040 KiB + processed 4,480 KiB | v5.0.2 | CC-BY-3.0 annotations; LICENSE_SCOPE_VERIFIED | allowed as SILVER_AUXILIARY with attribution | ontology_concept_extraction, biomedical_coreference, syntactic_auxiliary_training | biomedical NLP auxiliary | none | upstream full-text linkage (CRAFT native) | upstream splits retained | SILVER_AUXILIARY | ALREADY_ACQUIRED | archive SHA + Merkle PASS; licence scope verified | adapter backlog design (future PR) | none | 0 |
| BioImage Archive / REMBI pilot (40 accessions) | public imaging archive (EMBL-EBI BioStudies BioImages collection) | metadata-only (study JSON + file lists, held outside the repo) | 16,973,278 bytes metadata retrieved (≤500 MiB cap respected by >30×); 0 bytes committed | BioImages.v4/v5 REMBI templates | per-accession verified: CC0 or CC BY 4.0 (fail-closed; S-BIAD679 flagged) | metadata research only; no image use yet | biosample/specimen/acquisition/analysis metadata mapping (Imaging Profile) | Imaging Profile only | none | archive DOI + REMBI structure per accession | no model-use partitions exist | SILVER_AUXILIARY candidate at best; no gold inference (no automatic well=EU) | METADATA_ONLY_NOW (executed); top 4 SELECTIVE_SAMPLE_LATER under separate authorisation | endpoints live-verified; licences verified per accession from authoritative study JSON | separately authorised image-sample pilot if approved | none for metadata; image sampling needs authorisation + per-accession licence re-check | ≤500 MiB if an image-sample pilot is later approved |
| PMC Open Access subset | public OA literature corpus | none | 0 | rolling OA subset | PMC OA licence terms per article; filtering required | none granted | possible OA Methods/caption source (undecided) | undecided | none | n/a | n/a | undecided — no role assigned | FUTURE_PROFILE | official interfaces identified only (PMC OA Subset web service/FTP; Europe PMC REST); no acquisition | documentation-level feasibility only | licence filtering + scope decision | not estimated (large) |
| ISA / BioStudies / SDRF | metadata ecosystem standards | none | 0 | ISA-Tab / BioStudies schema / SDRF | open specification documents | schema alignment reference | record-schema alignment (metadata structure) | Imaging/metadata profiles | none | n/a | n/a | standards reference — not a corpus | DO_NOT_DOWNLOAD | record schemas, not one downloadable corpus | schema mapping notes if Imaging Profile work proceeds | none | 0 |
| OME / OMERO | imaging metadata standards / platform | none | 0 | OME data model, OME-Zarr, OMERO | open specifications | interoperability mapping reference | imaging metadata/interoperability mapping implications | Imaging Profile | none | n/a | n/a | standards reference — not a corpus | DO_NOT_DOWNLOAD | interoperability mapping implications only; no corpus to acquire | mapping review if Imaging Profile proceeds | none | 0 |
| Cell Painting Gallery / JUMP-CP | public imaging consortia datasets | none | 0 | public releases (TB-scale) | per-accession licences (varies) | none granted | future auxiliary plate-mapping/scalability source | undecided (imaging) | none | n/a | n/a | undecided — FUTURE_PROFILE; no well=EU inference | FUTURE_PROFILE | TB-scale sizes exceed volume headroom and pilot budgets | future profiling only if storage and authorisation change | storage capacity | terabytes (not approvable now) |
| Lazic in vivo pseudoreplication data | private offered dataset | none | 0 | n/a | UNKNOWN | none — no access occurred | undecided (pseudoreplication/experimental structure) | future Animal Profile (profile-relative) | none | n/a | n/a | ROLE_DECISION_PENDING — never training-eligible until decided | NOT_RECEIVED | offered in principle; details pending | await schema/case-counts/licence; written role decision before any label access | role decision + access conditions | unknown |
| NC3Rs ARRIVE checker dataset | announced unreleased dataset | none | 0 | not released | UNKNOWN | none | reporting/evidence extraction candidates only | preclinical reporting auxiliary | none | n/a | n/a | AUXILIARY_CANDIDATE; forbidden defaults enforced | NOT_AVAILABLE | announced, not released; no download attempted | await release; then inspect schema + licence | release pending | unknown |

## States that must remain (verbatim)

```text
DATA_READINESS: BLOCKED
SCIENTIFIC_VALIDATION: NOT_STARTED
SOURCE_DATA_DEVELOPMENT_USE: BLOCKED
SOURCE_DATA_TRAINING_USE: BLOCKED
SOURCE_DATA_EVALUATION_USE: PENDING_LICENCE_DECISION
READY_FOR_B0_GO: BLOCKED
C2_PRECLINIE: DESIGN_ONLY
MODERNBERT_TRAINING: HOLD
GRANITE_PROMOTION: HOLD
SUBSTANTIVE_TRAINING: HOLD_PENDING_REAL_ANCHOR
```

No public corpus becomes real gold. Silver/public corpora do not satisfy the Reality Gate, do not provide experimental_unit / independent_n / allocation gold, and do not unblock B0.

## C1.1 status

**C1.1 SourceData document provenance: RECOVERABLE_PARTIAL_DETERMINISTIC.** The locked HF pin `b457c14041b61c56f671c6f966b4324f682855b7` is dead upstream (`Invalid rev id`; absent from all 208 commits of `main`), but all v2.0.3 join assets are byte-identical between the v2.0.3-era commit `9edc4cca…` and HEAD `04333ae2…`; 71,197/75,163 records receive unique PANEL provenance, 3,965 ARTICLE-level (DOI-only), 1 unmatched. Full evidence and the proposal-only migration plan: `docs/task_corpora/c1.1-sourcedata-document-provenance-investigation.md`. No canonical JSONL or manifest was modified by that investigation.

## Non-actions declaration

- No bulk image download (BioImage pilot was metadata-only; 16,973,278 bytes of API responses total).
- No model operation of any kind (no download, training, fine-tuning, promotion).
- No B0 baseline execution.
- No Lazic data access, label inspection, or ingestion.
- No scientific validation activity.
- No merge, no push.
- No redownload of any VERIFIED_PRESENT data.
