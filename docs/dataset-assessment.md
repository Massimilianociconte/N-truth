# Dataset assessment and acquisition policy

This document summarizes the public, repository-safe dataset decisions for N-Truth.
It intentionally excludes local paths, checksums, unpublished review notes, personal
data and the contents of non-versioned datasets.

The detailed per-asset registry remains local and is not part of the open-source
repository. No dataset, annotation corpus, model weight, cache or checkpoint is
distributed with N-Truth.

## Current readiness

The local bootstrap contains eight small source files occupying less than 1 MiB in
total. They cover structured biomedical articles, one article supplement and three
small metadata/sample-sheet files. They are useful for parser fixtures and manual
calibration, but none is currently approved for model training.

Every local asset remains:

- immutable in raw storage;
- unassigned to train, validation or test;
- ineligible for training until license, privacy and annotation gates pass;
- grouped with every article version, supplement and linked repository record.

Public availability and free access do not establish a right to train, redistribute
or publish a derived corpus.

## Admission criteria

Automatic acquisition is limited to a single, versioned asset with machine-readable
evidence of CC0 1.0 or CC BY 4.0. Even then, admission is only a pre-screen. Before an
asset can enter a corpus snapshot, its manifest must record:

- canonical source, responsible organization and immutable identifier;
- exact version, retrieval time and SHA-256;
- asset-level license evidence and required attribution;
- separate permissions for analysis, annotation, training, sharing and redistribution;
- privacy status, restrictions and revocation information;
- work family, laboratory, article, supplement and repository leakage groups;
- preprocessing lineage and raw-to-normalized coordinate mapping;
- annotation, adjudication and split status.

The admission workflow must fail closed when any required fact is missing. The code
enforces the presence and format of governance/license identifiers, reviewer maturity,
training eligibility and split groups; it cannot authenticate the legal or scientific
substance of those records. Human/data-steward approval remains mandatory.

## Official source decisions

| Source | Intended use | Decision | Reason and restrictions |
|---|---|---|---|
| [PMC Open Access Subset](https://pmc.ncbi.nlm.nih.gov/tools/openftlist/) and [PMC OA AWS service](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/) | Targeted JATS articles, captions, tables and small supplements | **Include selectively** | License is checked per article and version. Presence in PMC is not enough; see [PMC copyright guidance](https://pmc.ncbi.nlm.nih.gov/about/copyright/). |
| [Europe PMC APIs](https://europepmc.org/developers) | Discovery, DOI/PMCID reconciliation and selected OA full text | **Include selectively** | `FREE_FULL_TEXT` is not license evidence. Preserve the license embedded in each article. |
| [PLOS text and data mining](https://plos.org/text-and-data-mining/) | Homogeneous JATS and article-supplement bundles | **Include selectively** | Use DOI-level retrieval, not the full bulk. Verify each component against the [PLOS license policy](https://journals.plos.org/plosone/s/licenses-and-copyright). |
| [eLife article XML](https://github.com/elifesciences/elife-article-xml) | Cell-culture, imaging and version-aware JATS cases | **Include selectively** | Pin the version. Exclude peer-review `sub-article` content from model input and check third-party components. |
| [BioStudies](https://www.ebi.ac.uk/biostudies/help#API) | PageTab metadata, sample sheets and small linked supplements | **Include selectively** | Verify license per record and file; EMBL-EBI's general terms are documented separately in its [licensing guidance](https://www.ebi.ac.uk/licencing). |
| [BioImage Archive](https://www.ebi.ac.uk/bioimage-archive/) | REMBI/file-list metadata and small sample maps | **Metadata only** | Raw multidimensional images are outside the bootstrap storage and modeling scope. Imported studies can retain different licenses. |
| [Image Data Resource](https://idr.openmicroscopy.org/about/download.html) | HCS hierarchy and metadata examples | **Metadata only** | Raw holdings are far beyond local capacity. Check each study's terms using the [IDR FAQ](https://idr.openmicroscopy.org/about/faq/). |
| [Zenodo](https://help.zenodo.org/docs/deposit/describe-records/licenses/) | Small, versioned sample sheets and codebooks | **Include selectively** | Record metadata is not peer review. Verify file checksum, version, privacy and record-level license. Do not download linked FASTQ solely to parse a sample sheet. |
| [Figshare API](https://docs.figshare.com/) | Small experimental metadata tables | **Include selectively** | Require canonical item version, license, codebook and publication relationship. An unresolved article link blocks external-gold use. |
| [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | DOI canonicalization and work-family grouping | **Discovery only** | Metadata does not license publisher abstracts, full text or supplements. |
| [DataCite public data](https://support.datacite.org/docs/datacite-public-data-file) | Dataset DOI/version relationships | **Discovery only** | Record metadata does not determine the rights of deposited files. |
| [OpenAlex](https://help.openalex.org/hc/en-us/articles/28926392245399-How-is-OpenAlex-open) | Work/version and author/laboratory matching | **API only** | The full snapshot is larger than the available local storage and does not license linked content. |
| [PubMed download services](https://pubmed.ncbi.nlm.nih.gov/download/) | PMID/PMCID discovery | **Discovery only** | Many abstracts retain publisher rights and are not accepted automatically as training text. |
| [PubTables-1M](https://github.com/microsoft/table-transformer) | Possible future table-structure pretraining | **Defer** | It is not N-Truth gold, has substantial storage cost and can overlap the same PMC articles used for evaluation. Exact release license and file manifest must be reviewed first. |
| [CRAFT](https://pmc.ncbi.nlm.nih.gov/articles/PMC7243923/) | Possible NER/evidence-span benchmark | **Defer** | Annotation license and every underlying article license must be reconciled; task fit is indirect. |
| [SourceData](https://sourcedata.embo.org/) | Figure/entity relation research | **Defer** | Release, article and linked-file rights require separate review; overlap with target articles must be measured. |
| [University of Bristol “What exactly is N” dataset](https://data.bris.ac.uk/data/dataset/2uad9gecss2r2ksaujt85gj4a) | Meta-scientific comparison | **Exclude from automatic training** | The recorded non-commercial license is outside the automatic Tier A policy and the dataset may contaminate evaluation against a core scientific reference. |
| [PubMedQA](https://huggingface.co/datasets/qiaojin/PubMedQA) | General biomedical question answering | **Defer** | The dataset-card license does not by itself establish sublicensing of underlying PubMed text, and the task is not experimental-design reconstruction. |

Files with CC BY-NC, CC BY-ND, CC BY-SA, custom terms, no license or only a generic
“open access” label are not acquired automatically.

## Transformation requirements

Original files remain byte-for-byte immutable. Training never reads arbitrary raw
files directly; it reads a content-addressed corpus snapshot produced by a documented
pipeline.

### Articles

1. parse JATS/XML with DTD, entity expansion and network access disabled;
2. retain the main article's Methods, captions and tables;
3. exclude references, funding, peer-review sub-articles and author responses unless a
   separately governed task requires them;
4. normalize Unicode and whitespace while retaining a bidirectional offset map;
5. preserve section, table, cell and cross-reference provenance;
6. segment whole experimental blocks rather than independent sentences;
7. produce double annotation and adjudication before supervised training.

### Tables and sample sheets

1. detect the real delimiter and encoding rather than trusting the extension;
2. preserve workbook sheet names, cell coordinates, formulas and cached values;
3. distinguish observation, identifier, declared count, mean, SD, SEM, percentage and
   missing value;
4. normalize into long-form records without overwriting the raw source;
5. do not invent experimental-unit identifiers absent from the file;
6. reconcile group, factor, endpoint and hierarchy with the corresponding article or
   codebook.

### Model examples

The learned target is the candidate parser contract: evidence spans, experiment
blocks, entities, relations, allocation/application levels, alternatives,
determinability and decisive questions. Deterministic alerts and rule consequences
remain outside the model target.

See [Data and model development](./data-and-model-development.md) for the repository's
training gates and local storage layout.

## Split and leakage policy

Splits use content-addressed manifests; source files are not copied into separate
directories.

The indivisible split unit includes:

- DOI/PMCID, preprint, publication, corrections and revisions;
- supplement, sample sheet, code and repository accession;
- mirrors from PMC, Europe PMC, PLOS or a publisher;
- synthetic template and every paraphrase or transformation derived from it.

The implemented preparation uses exact SHA-256/content matching, conservative
near-duplicate fingerprints over the canonical input, and transitive identifiers for
publication/work family, bundle, project, laboratory and corresponding author. A
normalized table fingerprint and DOI/mirror reconciliation remain upstream curation
requirements; omitted identifiers cannot be recovered safely by the split algorithm.

Synthetic examples are train-only. Validation, test and external sets are frozen
before prompt engineering, model selection and calibration. Public articles already
used to design the system are not described as blind external validation.

## Storage policy

The local machine has less than 100 GiB available. Therefore:

- the committed MLX profile requires at least 50 GiB still free after the base-model
  download; 25-30 GiB is only the absolute floor that no archival decision may cross;
- cap raw plus processed data at 15-20 GiB;
- acquire 50-100 targeted JATS articles before considering any bulk source;
- cap each supplement bundle and inspect its manifest before download;
- use APIs for bibliographic metadata rather than full snapshots;
- use BioImage Archive and IDR metadata, not raw images;
- never acquire linked FASTQ when only the sample-sheet structure is needed;
- stop before download if archive, extraction, preprocessing and temporary space
  cannot be budgeted together.

The current strategy prioritizes a small, diverse and expertly annotated corpus over a
large weakly governed collection. Dataset, annotation, model and checkpoint files stay
outside Git unless the project owner later gives explicit authorization for a specific
redistributable artifact.
