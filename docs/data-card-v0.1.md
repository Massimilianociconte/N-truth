# N-Truth Data Card v0.1

**Stato:** nessun corpus N-Truth approvato, congelato o training-ready

**Target normativo:** PRD v9

**Contratto root implementato:** PRD v7

## Contenuto versionato

Il repository contiene fixture e contratti per test software, non un corpus
scientifico N-Truth. Gli asset di regressione e gli scenari sintetici non sono
Experiment Bundle reali, non costituiscono human gold e non misurano accuratezza.

L'inventario delle fixture storiche è in
`data/manifests/fixture-catalog-v3.json`. Il numero di fixture o il pass dei test non
soddisfa il Reality Gate.

## Dati esterni osservati

La root locale `/Volumes/FLASH128/N-Truth-Datasets/` contiene snapshot raw e derivati
di SourceData, PreClinIE, MeasEval e CRAFT. Questi dati non sono distribuiti dal
repository.

| Corpus | Record processati | Autorità N-Truth | Training | Evaluation |
|---|---:|---|---|---|
| SourceData | 75.163 multitask | `SILVER_AUXILIARY` | 0 eleggibili | 0 eleggibili |
| PreClinIE | 1.450 sezioni | `SILVER_AUXILIARY` | 0 eleggibili | 0 eleggibili |
| MeasEval | 448 paragrafi | `SILVER_AUXILIARY` | 0 eleggibili | 0 eleggibili |
| CRAFT | 97 articoli | `SILVER_AUXILIARY` | 0 eleggibili | 0 eleggibili |

I conteggi derivano dai report in
`/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/quality/`. Descrivono la
materializzazione osservata, non sufficienza, rappresentatività o qualità scientifica.
`NativeAnnotationTier.HUMAN_CURATED_GOLD` indica soltanto annotazione gold nel task
upstream; non equivale a `AuthorityLevel.NTRUTH_GOLD`.

Sotto `/Volumes/FLASH128/N-Truth-Datasets/training_ready/` non esistono file o record
training-ready; possono restare directory strutturali senza contenuto eleggibile. I
derivati legacy SourceData sono conservati sotto
`/Volumes/FLASH128/N-Truth-Datasets/quarantine/training_ready/` e non possono essere
usati come input.

## Architettura canonica

```text
source asset + immutable hash
→ raw snapshot
→ processed acquisition envelope
→ validated canonical/task snapshot
→ authorized train/validation view
```

Un futuro training export dovrà essere derivato e riproducibile; non sarà la fonte
primaria. Il custody snapshot completo conserva test/external e una training view
fisicamente separata espone soltanto train/validation. Nessuna view è oggi leggibile
da MLX: manca il runner anonymous/unlinked inherited read-only FD. Il protected vault
resta sotto custodia indipendente.

## Tier e usi

| Tier | Uso consentito | Vincolo |
|---|---|---|
| N-Truth GOLD | futuro training/evaluation secondo split | review indipendente, adjudication, provenance, rights e registry v9 |
| SILVER | task ausiliari autorizzati | nessun target epistemico o scientific verdict automatico |
| WEAK | sviluppo controllato | regola, versione, confidence e audit separati |
| SYNTHETIC | futuro train/stress soltanto | generator lineage, deduplica e human calibration; il profilo corrente impone `synthetic_train_only=true` |
| CANDIDATE | quarantena/review | mai promozione tramite solo flag |

Ogni capability è autorizzata separatamente: analisi locale non implica training,
evaluation, pubblicazione di metriche o redistribuzione.

## Gold futuro

Il futuro corpus N-Truth deve includere Experiment Bundle reali, evidence span,
Experiment Graph, fattori, contrasti, endpoint, gerarchie, allocation/application,
determinability, alternative e clarification question secondo il registry canonico.

Prima della raccolta sostanziale servono schema e guideline PRD v9 congelati. I casi
decisivi devono essere doppiamente annotati, l'agreement misurato prima
dell'adjudication e il test custodito fuori dal workflow di sviluppo.

## Split e contamination

Train, validation, test ed external vengono separati per famiglia di articolo,
versioni, supplementi, dataset, laboratorio e transformation family. La deduplica
esatta, near e semantic-family precede lo split. Synthetic e tutte le sue parafrasi
restano train-only.

Benchmark pubblici plausibilmente presenti nel pretraining non sono test primari di
generalizzazione scientifica. Un test aperto per debugging diventa development data.

## Provenance e licenze

Ogni asset richiede source URL/ID, revisione, SHA-256, document/section identity,
original text o riferimento risolvibile, trasformazione, annotation method,
confidence, tier, licenza, timestamp e schema version. Annotazioni, testo e
supplementi possono avere termini diversi.

Licenza assente, scope ambiguo, revoca, privacy non risolta o identity incompleta
falliscono chiuso. Non è attribuita una licenza globale ai corpus futuri.

## Stato di readiness

La destinazione canonica della proiezione machine-readable finale è
`/Volumes/FLASH128/N-Truth-Datasets/manifests/reports/readiness-20260813/training-readiness.final.json`.
Il file deve essere rigenerato dopo l'hardening; la decisione da preservare finché i
blocker non cambiano è:

```text
scientific FAIL
dataset FAIL
schema FAIL
evaluation FAIL
infrastructure PARTIAL
apple_silicon_feasibility PASS
reproducibility FAIL
overall NOT_READY
```

Non sono disponibili baseline reali, human ceiling, H/A/H+A, performance per classe o
OOD. Tokenizzazione, training/smoke, prediction, metriche, calibrazione, resume,
checkpoint ed export sono bloccati dal confine FD; nessuno di questi risultati viene
stimato o sostituito con conteggi dei corpus pubblici.
