# Dataset assessment and acquisition policy

## Current decision

The normative target is **PRD v9**; the implemented root contract is **PRD v7**.
Public corpora are auxiliary evidence only and cannot close the Reality Gate.

The current local corpus root is `/Volumes/FLASH128/N-Truth-Datasets/`. Acquisition
and normalization have produced integrity-audited artifacts, but there are no
training-ready files or records under
`/Volumes/FLASH128/N-Truth-Datasets/training_ready/`; structural directories may
remain. Every processed public record is model-ineligible.

The authoritative sources and canonical final destinations are:

- `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/training-readiness.final.json`;
- `/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/quality/`;
- `/Volumes/FLASH128/N-Truth-Datasets/manifests/datasets.json`;
- `packages/ntruth/data/manifests/public_sources.lock.json`;
- `/Volumes/FLASH128/N-Truth-Datasets/manifests/checksums/merkle_manifest.json`;
- [source-portfolio-small-model-v1.md](training/source-portfolio-small-model-v1.md).

The final readiness, doctor, refresh/resume and Merkle artifacts must be regenerated
after the latest quality-report and SourceData task-corpus hardening. Their paths are
stable, but this document does not treat the pre-hardening bytes or checksums at those
paths as final evidence.

Pre-final readiness, doctor, licence-summary, Merkle and report snapshots are
historical and superseded. Statements like `AUXILIARY_READY` in them do not override
the canonical dataset manifest, bundled public lock, per-record eligibility, source
portfolio or root Reality Gate.

## Acquired source decisions

| Source | Observed corpus | Current decision | Blocking boundary |
|---|---:|---|---|
| [SourceData](https://huggingface.co/datasets/EMBO/SourceData) | 75,163 aligned NER/roles records | **Keep processed; model use blocked** | no reliable paper identity in the pinned export, conservative cross-split grouping, asset-level licence scope pending |
| [PreClinIE](https://github.com/Ineichen-Group/Preclinical_IE_Dataset) | 725 papers / 1,450 sections | **Priority auxiliary candidate; model use blocked** | publication-text rights and canonical mapping pending; rigor mentions do not establish allocation, unit or independent n |
| [MeasEval](https://github.com/harperco/MeasEval) | 448 paragraphs | **Keep processed; model use blocked** | licence scope and missing annotations; any derived independent split remains engineering-only until approved |
| [CRAFT](https://github.com/lhunter-lab/CRAFT) | 97 PMC OA articles | **Keep processed; model use blocked** | all records require review; annotation licence does not replace per-article text terms; coreference is not experimental hierarchy |

All four are `SILVER_AUXILIARY`, even where the native upstream tier is human-curated
gold. None may label `experimental_unit`, `independent_n`, `independently_assigned`,
`allocation_level`, `application_level` or `determinability_state`.

The detailed source portfolio, including TAC 2018 SRIE, ARRIVE, OBI, BioCause,
BioRED, SciREX, EBM-NLP, SciFact and risk-of-bias resources, is versioned in
[source-portfolio-small-model-v1.md](training/source-portfolio-small-model-v1.md).

## Admission criteria

Before an asset enters a validated snapshot, its manifest must contain:

- canonical source and immutable revision;
- retrieval timestamp, byte size and SHA-256;
- document, publication family and section identity;
- asset-level licence evidence and granular permitted uses;
- privacy, embargo, revocation and attribution status;
- raw-to-derived transform and parent checksum;
- native annotation tier and N-Truth authority tier;
- annotation method, confidence, review and adjudication state;
- leakage groups spanning versions, supplements, datasets and transformations;
- schema/registry version and adapter version.

Missing or `unknown` values fail closed. A public URL, “open access” label or
repository licence does not establish permission to train on embedded publication
text.

## Acquisition and normalization

Raw bytes are immutable. Downloads use pinned archive hashes, safe extraction and
transactional swaps. Repair is plan/apply with quarantine rather than destructive
cleanup. Normalization preserves original text or a resolvable immutable parent and
records every transformation.

Quality-report and SourceData task-corpus hardening invalidated the earlier Merkle
fingerprint. A new final refresh/resume must regenerate
`/Volumes/FLASH128/N-Truth-Datasets/manifests/checksums/merkle_manifest.json` and the
bounded evidence files `final-refresh.log`, `final-refresh.result.txt`,
`final-resume.log` and `final-resume.result.txt` under the readiness report directory.
Only the fingerprint in that regenerated manifest may be cited; this document does
not predict it. A successful final integrity run would prove integrity of included
artifacts, not scientific validity, licence closure or training readiness.

## Quality policy

Every processed corpus is audited for:

- schema and required-value violations;
- invalid UTF-8/JSON, empty content and offset mismatches;
- duplicate IDs, payloads and normalized content;
- group/content leakage across splits;
- token/label and task/payload alignment;
- missing annotations and review-required records;
- HTML, citation, OCR, encoding and language candidates;
- label and length distributions;
- training/evaluation eligibility counts.

Heuristic artifact and near-duplicate detections are candidates for review, not
semantic truth. A quality report can pass integrity while model use remains blocked.

## Split and leakage policy

Split assignment follows the strongest available family identity:

```text
DOI → PMCID → PMID → upstream source identity
```

Article versions, abstracts, Methods, captions, supplements, linked datasets,
laboratory series, mirrors and transformations stay together. If identity is missing,
the record remains ineligible; a row index cannot establish independence.

Upstream splits are provenance. They are not automatically N-Truth splits. Derived
group-safe splits can demonstrate engineering isolation but require explicit schema,
licence and governance approval before model use.

Test and external challenge content must be physically separated from the trainer.
The training view contains only train and validation, but it is not an executable ML
input until a private runner consumes only verified anonymous/unlinked inherited
read-only file descriptors. Protected evaluation additionally requires a separate
custodian-controlled one-time protocol.

## Storage and publication policy

Raw corpora, processed data, training views, vault content, models, adapters,
checkpoints and predictions remain outside Git. Only code, schemas, small fixtures,
configurations and non-sensitive documentation are versioned.

No artifact is published merely because it has a checksum or open-source code around
it. Distribution requires a separate per-asset review of text, annotations, model
weights, metrics and privacy.

## Readiness effect

Acquisition completeness and local data quality do not justify fine-tuning while:

- the PRD v9 registry is not canonical;
- no sufficient N-Truth GOLD real anchor exists;
- licence and protected-split predicates are not canonically true;
- baselines and H/A/H+A evaluation have not been executed;
- the selected base model has not won a frozen tournament.
- the anonymous/unlinked inherited read-only FD runner does not exist, so all ML
  operations remain fail-closed.

The current decision is therefore **NOT READY**, not “ready with public silver data.”
