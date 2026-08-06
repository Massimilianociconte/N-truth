# BioImage Archive / REMBI metadata pilot (Phase D) — 2026-08-06

**Mode:** metadata-first, network research only. **No images, TIFF stacks, OME-Zarr payloads, ZIPs or segmentation assets were downloaded.**
**Companion documents:** `dataset-portfolio-status-2026-08-06.md`, `data_manifests/bioimage-rembi-candidates.yaml`, `public-dataset-adapter-backlog.md`.

## 1. Pilot framing (EMBL-EBI — informational only)

EMBL-EBI BioImage Archive staff provided an **informational-only** response: no bespoke curation
capacity exists; the archive search is likely useful; submissions use REMBI; studies may be CC0 or
CC BY 4.0. This is **not** a partnership, endorsement, or blanket permission covering every
accession, and it does not imply EMBL-EBI supports or validates N-Truth. Official archive policy
controls; **every accession's licence was verified individually from its authoritative study
JSON**, and the classification below fails closed (anything not explicitly CC0 / CC BY 4.0 would
be `LICENCE_BLOCKED`).

New direct BioImage Archive submissions typically use CC0 / CC BY 4.0; imported/brokered
accessions may carry other licences. All 40 candidates carry the `S-BIAD` prefix (direct BioImage
Archive submissions) and no imported/brokered provenance indicators were found in their metadata —
but licence was still checked per accession, never inferred from the prefix.

## 2. Confirmed endpoint set (official BioStudies REST, live-verified 2026-08-06)

The BioImage Archive lives in the BioStudies **BioImages** collection. The `/biostudies/help#API`
page is a JS-rendered app and exposes no static API text; endpoints below were confirmed by live
probing against official `ebi.ac.uk` interfaces only.

| Purpose | Confirmed endpoint | Status |
|---|---|---|
| Search | `GET https://www.ebi.ac.uk/biostudies/api/v1/search?query={q}&collection=BioImages&pageSize=&page=&sortBy=release_date&sortOrder=descending` | 200 OK, JSON `{totalHits, hits[...]}` |
| Study retrieval (PageTab/REMBI JSON) | `GET https://www.ebi.ac.uk/biostudies/api/v1/studies/{accession}` | 200 OK |
| File list (DataTables-style) | `GET https://www.ebi.ac.uk/biostudies/api/v1/files/{accession}?start={n}&length=1000` | 200 OK; `recordsFiltered` = total file count; rows carry `path`, `Size` |
| Not valid | `/api/v1/studies/search?...`, `/studies/{acc}/filelist`, `/studies/{acc}/files` | 404 |

Politeness: concurrency = 1 (cap ≤ 2), ~0.6–1 s sleeps between requests, exponential backoff on
429/timeout (implemented; not triggered), small page sizes (search ≤ 50, file list ≤ 1000,
file-list enumeration capped at 3,000 rows per accession).

## 3. Query log summary

12 queries against `collection=BioImages`, sorted by release date descending, up to 2 pages × 50 each.

| Query | totalHits | Unique cumulative |
|---|---|---|
| high content screening | 465 | 100 |
| high content imaging | 1,062 | 167 |
| cell culture | 1,014 | 192 |
| cell line imaging | 1,072 | 192 |
| fluorescence microscopy cell | 1,070 | 197 |
| confocal cell imaging | 1,078 | 197 |
| in vitro imaging | 1,047 | 197 |
| live cell imaging | 1,072 | 197 |
| microscopy screen | 1,061 | 197 |
| U2OS | 57 | 248 |
| HeLa | 80 | 307 |
| cell segmentation | 1,046 | 308 |

**308 unique accessions** surfaced. Pre-screen on search-index snippets identified 39 with an
explicit CC0 / CC BY 4.0 statement; 1 further accession (`S-BIAD2193`, CC0, in-profile) was
discovered during endpoint verification. **40 candidates** entered detailed analysis (study JSON +
file list) — inside the 20–50 target, with no padding from licence-unverified or out-of-profile
accessions.

## 4. Selection criteria

- **Licence verification is authoritative, not snippet-based.** Every candidate's `License`
  attribute + URL was read from `/studies/{accession}`. Result: all 40 carry explicit CC0
  (publicdomain/zero/1.0) or CC BY 4.0 (licenses/by/4.0/legalcode). Zero `LICENCE_BLOCKED`, zero
  unverifiable licences in the final set — licence-unverified hits were never promoted (fail-closed).
- **Ambiguities noted.** (a) `S-BIAD679` declares `CC0` by name but its licence URL qualifier is
  empty in the study JSON — treated as valid CC0 (the name is explicit) but **flagged for
  re-verification before any sampling**. (b) Most accessions expose only the archive DOI
  (`10.6019/S-BIAD…`); genuine paper DOIs exist only for a minority. Missing publication linkage
  is recorded as a missing decisive field, not a licence issue. (c) No identifiable
  clinical/patient data indicators found in any candidate metadata; `S-BIAD3467` (tonsil
  organoid) touches primary human tissue and was excluded as OUT_OF_PROFILE regardless.
- **REMBI coverage.** All candidates use BioImages templates (v4/v5, REMBI-derived) with
  Biosample / Specimen / Image acquisition sections; Image analysis sections and Study Components
  with file lists are common.
- **Size discipline.** Totals and largest-file sizes were computed from authoritative file lists.
  Anything > 20 GB, or with any file ≥ 4 GiB (FAT32 limit), or > ~100k files, cannot justify an
  image sample within the 500 MiB pilot budget.

## 5. Per-accession table (all 40 candidates)

Column codes — BS/SP/AQ/AN: Biosample / Specimen / Image acquisition / Image analysis metadata
present (Y/N). File list `*`: declared bytes sampled from a 3,000-row cap (`sampled_partial=true`).
Missing flags: PUB = associated-publication DOI/PMID missing; ANA = image-analysis metadata
section absent; FL = complete file-list not enumerated in pilot.

| Accession | Title | Released | Licence | Template | Organism / source | BS | SP | AQ | AN | Components | File list | Files | Declared size | Largest file | N-Truth relevance | Missing (flags) | Class |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S-BIAD1094 | EUbOPEN Wave1 compounds Cell Painting Images | 2024-03-29 | CC BY 4.0 | v4 | Homo sapiens (human) / Bone sarcoma cell line | Y | Y | Y | N | 1 | yes | 105 | 2.36 TB | 23.76 GB | excluded | ANA | TOO_LARGE |
| S-BIAD1259 | An automated high-content screening and assay platform for the analysis of sphe… | 2024-07-04 | CC0 | v4 | Homo sapiens (human) / HeLa Kyoto cultured cells | Y | Y | Y | N | 6 | yes* | 137,936 | 13.10 GB | 7.1 MB | excluded | PUB+ANA+FL | TOO_LARGE |
| S-BIAD1319 | Compressed phenotypic screening empowers scalable biological discovery | 2024-08-15 | CC BY 4.0 | v4 | Homo sapiens (human) / U2OS human cell lines | Y | Y | Y | Y | 6 | yes* | 386,248 | 673.90 GB | 23.17 GB | excluded | PUB+FL | TOO_LARGE |
| S-BIAD1738 | Characterizing protein sequence determinants of nuclear condensates by high-thr… | 2025-03-26 | CC0 | v4 | Homo sapiens (human) / HeLa or U2OS cells expressing fluore… | Y | Y | Y | N | 1 | yes* | 31,906 | 9.02 TB | 1.33 TB | excluded | ANA+FL | TOO_LARGE |
| S-BIAD2076 | spaCR: Spatial phenotype analysis of CRISPR-Cas9 screens. | 2025-06-14 | CC BY 4.0 | v4 | Homo sapiens (human) / Toxoplasma gondii | Y | Y | Y | N | 1 | yes* | 98,288 | 23.86 GB | 8.0 MB | excluded | PUB+ANA+FL | TOO_LARGE |
| S-BIAD2124 | PARP7 is a proteotoxic stress sensor which labels proteins for autophagic degra… | 2025-08-01 | CC BY 4.0 | v5 | Homo sapiens (human) / HeLa cells treated with proteotoxic … | Y | Y | Y | N | 1 | yes | 249 | 1.73 GB | 14.8 MB | Imaging Profile | PUB+ANA | IMAGE_SAMPLE_CANDIDATE |
| S-BIAD2135 | Spatial phenotype analysis of CRISPR-Cas9 screens | 2025-07-04 | CC BY 4.0 | v4 | Homo sapiens (human) / Toxoplasma gondii | Y | Y | Y | N | 1 | yes* | 159,718 | 23.88 GB | 8.0 MB | excluded | PUB+ANA+FL | TOO_LARGE |
| S-BIAD2192 | Fluorescent protein and peptide tags alter condensate formation and dynamics in… | 2025-07-25 | CC BY 4.0 | v5 | Homo sapiens (human) / HelaK, Hela Gromeier, In vitro conde… | Y | Y | Y | N | 1 | yes* | 8,165 | 26.16 GB | 227.1 MB | schema/provenance mapping reference | PUB+ANA+FL | METADATA_CANDIDATE |
| S-BIAD2193 | Identification of cell types by cell morphology analysis | 2025-07-22 | CC0 | v5 | Homo sapiens (human) / Different cell lines | Y | Y | Y | N | 1 | yes | 549 | 2.02 GB | 3.7 MB | Imaging Profile | PUB+ANA | IMAGE_SAMPLE_CANDIDATE |
| S-BIAD2261 | HIT-MAP: A Scalable Approach to Multimodal Mapping of Subcellular Organization | 2026-06-04 | CC BY 4.0 | v5 | Homo sapiens (human) / HEK293 cells are a human cell line d… | Y | Y | Y | N | 1 | yes | 640 | 4.94 GB | 19.1 MB | Imaging Profile | PUB+ANA | SMALL_FILELIST_CANDIDATE |
| S-BIAD2262 | EUbOPEN compounds Cell Painting Images and profiles | 2025-10-10 | CC BY 4.0 | v5 | Homo sapiens (human) / Bone sarcoma cell line | Y | Y | Y | Y | 1 | yes | 213 | 1.86 TB | 29.67 GB | excluded | PUB | TOO_LARGE |
| S-BIAD2357 | pan-ASLM: a high-resolution and large field-of-view light sheet microscope for … | 2025-10-25 | CC BY 4.0 | v5 | Homo sapiens (human) / HeLa cell line expanded using pan-Ex… | Y | Y | Y | N | 1 | yes | 16 | 571.62 GB | 121.57 GB | excluded | ANA | OUT_OF_PROFILE |
| S-BIAD2379 | Data supporting Figures 3-6 from "Central infusion of prostaglandin E2 reveals … | 2026-06-30 | CC BY 4.0 | v5 | Mus musculus (mouse) / Adult mouse | Y | Y | Y | Y | 1 | yes* | 176,190 | 319.00 GB | 83.34 GB | excluded | FL | OUT_OF_PROFILE |
| S-BIAD2466 | Pulsed-electron illumination does not reduce beam damage for imaging biological… | 2025-12-05 | CC BY 4.0 | v5 | Virus / Purple membrane, Tobacco Mosaic Virus | Y | Y | Y | Y | 4 | yes | 2,351 | 869.09 GB | 3.36 GB | excluded | — | OUT_OF_PROFILE |
| S-BIAD2499 | microglia synapses engulfment analysis 24h after TIA | 2026-07-31 | CC0 | v5 | Mus musculus (mouse) / somatosensory cortex | Y | Y | Y | Y | 1 | yes | 20 | 7.01 GB | 424.1 MB | excluded | PUB | OUT_OF_PROFILE |
| S-BIAD2500 | microglia morphology analsis after ATP brain injection | 2026-07-31 | CC0 | v5 | Mus musculus (mouse) / somatosensory cortex | Y | Y | Y | N | 1 | yes | 49 | 14.76 GB | 369.5 MB | excluded | PUB+ANA | OUT_OF_PROFILE |
| S-BIAD2501 | glutamatergic synapses analysis after ATP injection in mouse brain | 2026-07-31 | CC0 | v5 | Mus musculus (mouse) / somatosensory cortex | Y | Y | Y | N | 1 | yes | 50 | 152.0 MB | 3.2 MB | excluded | PUB+ANA | OUT_OF_PROFILE |
| S-BIAD2502 | Analysis of microglia morphology 24 hours after a TIA in control animals and an… | 2026-07-31 | CC0 | v5 | Mus musculus (mouse) / somatosensary cortex | Y | Y | Y | N | 1 | yes | 28 | 9.87 GB | 426.1 MB | excluded | PUB+ANA | OUT_OF_PROFILE |
| S-BIAD2504 | glutamatergic synapses anaysis 24 hours after a TIA in control animals and anim… | 2026-07-31 | CC0 | v5 | Mus musculus (mouse) / somatosensory cortex | Y | Y | Y | N | 1 | yes | 52 | 53.6 MB | 1.0 MB | excluded | PUB+ANA | OUT_OF_PROFILE |
| S-BIAD2733 | Endocytosed lipids induce cell aggregation via filopodia retraction in a close … | 2026-03-07 | CC0 | v5 | Capsasora owczarzaki / Capsaspora cell line | Y | Y | Y | Y | 1 | yes | 3 | 4.50 GB | 2.88 GB | Imaging Profile | — | SMALL_FILELIST_CANDIDATE |
| S-BIAD2827 | Synthetic protein binders reveal a cryptic regulatory pocket on Aurora A for se… | 2026-02-06 | CC0 | v5 | Homo sapiens (human) / HeLa cells, homo sapiens. | Y | Y | Y | N | 1 | yes | 57 | 10.97 GB | 3.51 GB | Imaging Profile | PUB+ANA | SMALL_FILELIST_CANDIDATE |
| S-BIAD2914 | Automated analysis of zebrafish vascular networks using the VISTA-Z pipeline | 2026-02-08 | CC0 | v5 | Danio rerio (zebrafish) / Zebrafish embryos between 3 and 5… | Y | Y | Y | Y | 1 | yes | 2,160 | 403.91 GB | 470.0 MB | excluded | PUB | OUT_OF_PROFILE |
| S-BIAD2942 | Quantitative nanoscale imaging shows peptide–MHC I complexes are monomeric and … | 2026-05-05 | CC0 | v5 | Homo sapiens / HAP1 cells | Y | Y | Y | Y | 4 | yes | 12 | 1.12 TB | 704.55 GB | excluded | PUB | TOO_LARGE |
| S-BIAD3018 | VPS26A Retromer Complex and SNX27 Mediate Stress-Induced Golgi Bypass of Membra… | 2026-03-11 | CC BY 4.0 | v5 | Homo sapiens (human) / HeLa Cell lines | Y | Y | Y | N | 1 | yes | 160 | 691.2 MB | 11.1 MB | Imaging Profile | PUB+ANA | IMAGE_SAMPLE_CANDIDATE |
| S-BIAD3037 | Anagrelide remodels the PDE3A–SLFN12 interactome to associate with translation … | 2026-03-09 | CC BY 4.0 | v5 | Homo sapiens (human) / SA-4 and HeLa cells | Y | Y | Y | Y | 1 | yes | 2 | 5.85 GB | 5.36 GB | excluded | PUB | TOO_LARGE |
| S-BIAD3134 | 2-photon imaging raw data from striatal populations through GRIN lens | 2026-06-12 | CC BY 4.0 | v5 | Mus musculus (mouse) / Mouse striatum | Y | Y | Y | N | 2 | yes* | 3,142 | 293.78 GB | 5.75 GB | excluded | ANA+FL | OUT_OF_PROFILE |
| S-BIAD3135 | Holographic stimulation of neuronal ensembles in striatum | 2026-06-12 | CC BY 4.0 | v5 | Mus musculus (mouse) / Mouse striatum | Y | Y | Y | N | 1 | yes* | 4,225,816 | 44.74 GB | 6.14 GB | excluded | ANA+FL | OUT_OF_PROFILE |
| S-BIAD3162 | Nucleophagy removes cytotoxic trapped PARP1 | 2026-03-28 | CC0 | v5 | Homo sapiens (human) / CAL51 cells | Y | Y | Y | N | 13 | yes* | 6,509 | 31.09 GB | 380.1 MB | schema/provenance mapping reference | PUB+ANA+FL | METADATA_CANDIDATE |
| S-BIAD3296 | oc3_project18 : Detection and Analysis of Nuclear Pore Complexes by DNA PAINT | 2026-07-14 | CC BY 4.0 | v5 | Homo sapiens / HK-Nup107-GFP cell line (purchased from Cyti… | Y | Y | Y | Y | 1 | yes | 4 | 334.9 MB | 167.4 MB | Imaging Profile | PUB | IMAGE_SAMPLE_CANDIDATE |
| S-BIAD3316 | Mapping in-cell protein contact sites reveals hijacking of paraspeckles during … | 2026-05-18 | CC BY 4.0 | v5 | Homo sapiens / A549, Calu-3, HBEpCs, HeLa, MEFs and HEK293T… | Y | Y | Y | N | 1 | yes | 26 | 263.72 GB | 69.61 GB | excluded | PUB+ANA | TOO_LARGE |
| S-BIAD3320 | Lipid droplets promote the aberrant liquid-liquid phase separation of alpha-syn… | 2026-06-19 | CC BY 4.0 | v5 | Homo sapiens / M17D cell line | Y | Y | Y | Y | 16 | yes* | 5,317 | 17.29 GB | 108.7 MB | Imaging Profile | FL | SMALL_FILELIST_CANDIDATE |
| S-BIAD3370 | Imaging data for in situ sequencing of hiPSC-derived cardiomyocytes and endothe… | 2026-05-14 | CC BY 4.0 | v5 | Homo sapiens / cell culture | Y | Y | Y | N | 1 | yes | 1 | 122.95 GB | 122.95 GB | excluded | PUB+ANA | TOO_LARGE |
| S-BIAD3460 | 2D Time-Lapse Multispectral and Bright-Field Imaging of iPSCs and iNeurons duri… | 2026-07-20 | CC BY 4.0 | v5 | Homo sapiens (human) / KOLF2.1J wild-type (KOLF2.1 wt) huma… | Y | Y | Y | N | 1 | yes | 360 | 588.44 GB | 2.51 GB | excluded | PUB+ANA | TOO_LARGE |
| S-BIAD3467 | A tonsil organoid model reveals Epstein-Barr virus infected germinal center B c… | 2026-05-31 | CC BY 4.0 | v5 | Homo sapiens / Human tonsil FFPE section | Y | Y | Y | Y | 1 | yes | 5 | 2.78 GB | 780.2 MB | excluded | PUB | OUT_OF_PROFILE |
| S-BIAD3613 | Plant cells at the organ surface use mechanical cues to activate a specific gro… | 2026-07-15 | CC0 | v5 | Arabidopsis thaliana (thale cress) / Arabidopsis thaliana r… | Y | Y | Y | N | 1 | yes | 41 | 21.01 GB | 15.53 GB | excluded | PUB+ANA | OUT_OF_PROFILE |
| S-BIAD3647 | CDK8 remodels tumor microenvironment to resist KRASG12D inhibitors and daraxonr… | 2026-06-24 | CC0 | v5 | Homo sapiens (human) / PDXs | Y | Y | Y | N | 10 | yes* | 8,569 | 16.38 GB | 1.02 GB | excluded | PUB+ANA+FL | OUT_OF_PROFILE |
| S-BIAD3676 | An annotated timelapse imaging dataset on dormancy exit dynamics of Escherichia… | 2026-07-07 | CC BY 4.0 | v5 | Escherichia coli str. K-12 substr. MG1655 / Escherichia col… | Y | Y | Y | Y | 1 | yes | 4 | 342.55 GB | 316.79 GB | excluded | PUB | TOO_LARGE |
| S-BIAD3759 | The CCCH-type zinc-finger PfMD3 promotes translation for malaria parasite trans… | 2026-07-09 | CC0 | v5 | Plasmodium falciparum RO-33 / In vitro cultured human red b… | Y | Y | Y | Y | 1 | yes | 52 | 3.3 MB | 189,068 B | excluded | PUB | OUT_OF_PROFILE |
| S-BIAD3811 | CD24 drives evolutionarily conserved innate immune evasion in colorectal cancer… | 2026-07-20 | CC BY 4.0 | v5 | Danio rerio (zebrafish) / SW620 human colorectal cancer xen… | Y | Y | Y | Y | 1 | yes | 10 | 57.4 MB | 18.6 MB | excluded | PUB | OUT_OF_PROFILE |
| S-BIAD679 | The order of sequential exposure of U2OS cells to gamma and alpha radiation inf… | 2023-04-25 | CC0 | v4 | Homo sapiens (human) / Human Bone Osteosarcoma Epithelial C… | Y | Y | Y | N | 1 | yes | 57 | 10.13 GB | 184.4 MB | Imaging Profile | PUB+ANA | SMALL_FILELIST_CANDIDATE |

### 5.1 Supplementary per-accession fields

The five fields below are reported per accession exactly as captured from the authoritative
study JSON / file-list samples. Values that could not be sourced from captured metadata are
written as `not captured`; nothing is invented.

- **Possible N-Truth fields** — identical for all 40 accessions (single shared set):
  `biosample->organism/cell_line`, `specimen->sample_preparation`,
  `acquisition->instrument/method/parameters`, `analysis->protocols`,
  `study_component->file_list & associations (biosample/specimen/acquisition linkage)`,
  `plate/well mapping (where present in file paths)`.
- Raw / derived counts are file-list-sample classifications (row-level path/size heuristics),
  not full-corpus tallies; for the 12 `sampled_partial=true` accessions they cover only the
  sampled rows.

| Accession | Publication identifiers | Study type | Direct / imported submission | Raw / derived (file-list sample) |
|---|---|---|---|---|
| S-BIAD1094 | doi:10.5281/zenodo.10894237 | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD1259 | archive DOI only (10.6019/S-BIAD1259) | Study | direct (S-BIAD) | raw 3000 / derived/tabular 0 (files sampled) |
| S-BIAD1319 | archive DOI only (10.6019/S-BIAD1319) | Study | direct (S-BIAD) | raw 2965 / derived/tabular 0 (files sampled) |
| S-BIAD1738 | doi:10.1038/s41592-025-02726-y | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD2076 | archive DOI only (10.6019/S-BIAD2076) | Study | direct (S-BIAD) | raw 3000 / derived/tabular 0 (files sampled) |
| S-BIAD2124 | archive DOI only (10.6019/S-BIAD2124) | Study | direct (S-BIAD) | raw 218 / derived/tabular 28 (files sampled) |
| S-BIAD2135 | archive DOI only (10.6019/S-BIAD2135) | Study | direct (S-BIAD) | raw 3000 / derived/tabular 0 (files sampled) |
| S-BIAD2192 | archive DOI only (10.6019/S-BIAD2192) | Study | direct (S-BIAD) | raw 1215 / derived/tabular 32 (files sampled) |
| S-BIAD2193 | archive DOI only (10.6019/S-BIAD2193) | Study | direct (S-BIAD) | raw 546 / derived/tabular 3 (files sampled) |
| S-BIAD2261 | archive DOI only (10.6019/S-BIAD2261) | Study | direct (S-BIAD) | raw 256 / derived/tabular 380 (files sampled) |
| S-BIAD2262 | archive DOI only (10.6019/S-BIAD2262) | Study | direct (S-BIAD) | raw 0 / derived/tabular 142 (files sampled) |
| S-BIAD2357 | doi:10.1038/s41467-020-17523-8; doi:10.1101/2022.04.04.486901; doi:10.1101/2025.07.28.667278; doi:10.1101/2025.08.06.668765 | Study | direct (S-BIAD) | raw 16 / derived/tabular 0 (files sampled) |
| S-BIAD2379 | doi:10.1101/2025.04.28.651028 | Study | direct (S-BIAD) | raw 72 / derived/tabular 1430 (files sampled) |
| S-BIAD2466 | doi:10.1101/2025.07.29.667395; doi:10.1101/2025.07.29.667395v1 | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD2499 | archive DOI only (10.6019/S-BIAD2499) | Study | direct (S-BIAD) | raw 20 / derived/tabular 0 (files sampled) |
| S-BIAD2500 | archive DOI only (10.6019/S-BIAD2500) | Study | direct (S-BIAD) | raw 48 / derived/tabular 0 (files sampled) |
| S-BIAD2501 | archive DOI only (10.6019/S-BIAD2501) | Study | direct (S-BIAD) | raw 48 / derived/tabular 0 (files sampled) |
| S-BIAD2502 | archive DOI only (10.6019/S-BIAD2502) | Study | direct (S-BIAD) | raw 28 / derived/tabular 0 (files sampled) |
| S-BIAD2504 | archive DOI only (10.6019/S-BIAD2504) | Study | direct (S-BIAD) | raw 51 / derived/tabular 0 (files sampled) |
| S-BIAD2733 | doi:10.1101/2024.05.14.593945v1 | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD2827 | archive DOI only (10.6019/S-BIAD2827) | Study | direct (S-BIAD) | raw 57 / derived/tabular 0 (files sampled) |
| S-BIAD2914 | archive DOI only (10.6019/S-BIAD2914) | Study | direct (S-BIAD) | raw 2160 / derived/tabular 0 (files sampled) |
| S-BIAD2942 | archive DOI only (10.6019/S-BIAD2942) | Study | direct (S-BIAD) | raw 0 / derived/tabular 8 (files sampled) |
| S-BIAD3018 | archive DOI only (10.6019/S-BIAD3018) | Study | direct (S-BIAD) | raw 160 / derived/tabular 0 (files sampled) |
| S-BIAD3037 | archive DOI only (10.6019/S-BIAD3037) | Study | direct (S-BIAD) | raw 1 / derived/tabular 0 (files sampled) |
| S-BIAD3134 | doi:10.64898/2025.12.03.692128 | Study | direct (S-BIAD) | raw 82 / derived/tabular 2623 (files sampled) |
| S-BIAD3135 | doi:10.64898/2025.12.03.692128 | Study | direct (S-BIAD) | raw 2788 / derived/tabular 171 (files sampled) |
| S-BIAD3162 | archive DOI only (10.6019/S-BIAD3162) | Study | direct (S-BIAD) | raw 2484 / derived/tabular 464 (files sampled) |
| S-BIAD3296 | archive DOI only (10.6019/S-BIAD3296) | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD3316 | Title: Snapshot of in-cell protein contact sites reveals new host factors and hijacking o… | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD3320 | doi:10.1126/sciadv.ads7627 | Study | direct (S-BIAD) | raw 2777 / derived/tabular 185 (files sampled) |
| S-BIAD3370 | archive DOI only (10.6019/S-BIAD3370) | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD3460 | archive DOI only (10.6019/S-BIAD3460) | Study | direct (S-BIAD) | raw 360 / derived/tabular 0 (files sampled) |
| S-BIAD3467 | archive DOI only (10.6019/S-BIAD3467) | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD3613 | archive DOI only (10.6019/S-BIAD3613) | Study | direct (S-BIAD) | raw 28 / derived/tabular 12 (files sampled) |
| S-BIAD3647 | archive DOI only (10.6019/S-BIAD3647) | Study | direct (S-BIAD) | raw 1417 / derived/tabular 299 (files sampled) |
| S-BIAD3676 | archive DOI only (10.6019/S-BIAD3676) | Study | direct (S-BIAD) | raw 1 / derived/tabular 0 (files sampled) |
| S-BIAD3759 | archive DOI only (10.6019/S-BIAD3759) | Study | direct (S-BIAD) | raw 52 / derived/tabular 0 (files sampled) |
| S-BIAD3811 | Title: CD24 drives evolutionarily conserved innate immune evasion in colorectal cancer re… | Study | direct (S-BIAD) | raw 0 / derived/tabular 0 (files sampled) |
| S-BIAD679 | archive DOI only (10.6019/S-BIAD679) | Study | direct (S-BIAD) | raw 57 / derived/tabular 0 (files sampled) |

## 6. Recommendation-class distribution

| Class | Count |
|---|---|
| IMAGE_SAMPLE_CANDIDATE | 4 |
| SMALL_FILELIST_CANDIDATE | 5 |
| METADATA_CANDIDATE | 2 |
| TOO_LARGE | 13 |
| OUT_OF_PROFILE | 16 |
| LICENCE_BLOCKED | 0 |
| INSUFFICIENT_METADATA | 0 |

## 7. Budget and downloads

- Total downloaded: **16,973,278 bytes (≈ 16.2 MiB)** across 135 ledger entries — search
  responses, study JSON, file-list pages, endpoint probes. Budget cap 500 MiB: **respected by > 30×**.
- Every ledger entry carries URL, saved path, byte count and SHA-256 (operation scratch ledger).
- **No images were downloaded.** Metadata resides in operation scratch space only; nothing
  metadata-blob-shaped is committed to the repository.
- `S-BIAD679` licence flag: CC0 by name, empty licence URL qualifier — needs re-verification
  before any later sampling (see §4).

## 8. Top recommendations for a LATER, separately authorised image-sample pilot

**Images were NOT downloaded in this operation.** The four below are ranked candidates only; any
sampling requires separate authorisation and per-accession licence re-check at download time
(licences can change on revision).

| Rank | Accession | Licence | Declared size | Files | Justification |
|---|---|---|---|---|---|
| 1 | **S-BIAD3296** — Detection and analysis of nuclear pore complexes by DNA-PAINT (HK-Nup107-GFP human cell line) | CC BY 4.0 | ~0.33 GB | 4 | Smallest; full REMBI including analysis section; largest file 167 MB |
| 2 | **S-BIAD3018** — VPS26A/SNX27 Golgi bypass, HeLa immuno-cytochemistry | CC BY 4.0 | ~0.7 GB | 160 | Small, uniform TIFF set; largest file 11 MB |
| 3 | **S-BIAD2124** — PARP7 proteotoxic stress, HeLa | CC BY 4.0 | ~1.7 GB | 249 | Raw TIFFs + derived tabular files; clean biosample → acquisition chain |
| 4 | **S-BIAD2193** — Cell-type morphology classification, multiple human cell lines | CC0 | ~2.0 GB | 549 | CC0; archive DOI only (10.6019/S-BIAD2193); no associated publication in metadata; largest file 3.7 MB |

Combined declared size ≈ 4.7 GB; a ≤ 500 MiB subset (e.g. smallest files from ranks 1–2 plus a
few files from ranks 3–4) would fit the budget with room for provenance documentation.

Secondary tier (SMALL_FILELIST_CANDIDATE): `S-BIAD2261` (HIT-MAP), `S-BIAD2827` (HeLa mitosis;
largest file 3.5 GB < 4 GiB), `S-BIAD679` (U2OS radiation; CC0; v4 template; licence flag),
`S-BIAD3320` (M17D; rich 16-specimen REMBI), `S-BIAD2733` (Capsaspora cell line, CC0 —
unicellular culture, borderline profile).

## 9. Caveats for downstream use

1. `total_declared_bytes` is authoritative where the full file list was fetched (**28
   accessions**); for **12** accessions it is a 3,000-row sample flagged
   `sampled_partial=true`: S-BIAD1259, S-BIAD1319, S-BIAD1738, S-BIAD2076, S-BIAD2135,
   S-BIAD2192, S-BIAD2379, S-BIAD3134, S-BIAD3135, S-BIAD3162, S-BIAD3320, S-BIAD3647.
   These sampled accessions are TOO_LARGE / OUT_OF_PROFILE / METADATA_CANDIDATE **except
   S-BIAD3320, which is SMALL_FILELIST_CANDIDATE** — its declared size is therefore a
   partial-sample estimate, not an authoritative total.
2. Recommendation classes encode the pilot budget (500 MiB) and the 4 GiB FAT32 limit; re-run
   classification if caps change.
3. Any later image-sample pilot requires separate authorisation and per-accession licence
   re-check at download time.
4. N-Truth relevance is Imaging Profile only. No automatic well = experimental-unit inference;
   no gold role is claimed for any accession.
