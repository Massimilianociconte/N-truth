# Protocollo baseline ed evaluation del modello piccolo v1

**Stato:** preregistration draft; non eseguito
**Target normativo:** PRD v9
**Contratto root implementato:** PRD v7
**Execution gate:** HOLD; nessuna baseline ML è eseguibile finché mancano il runner anonymous/unlinked inherited read-only FD, l'authorization envelope applicabile e gli altri gate descritti qui

## 1. Domanda decisionale

Il protocollo deve rispondere, prima del fine-tuning:

> Un modello locale piccolo, con output strutturato e comportamento fail-closed, aggiunge valore misurabile rispetto a regole, prompting e retrieval senza degradare validità scientifica, calibrazione o indipendenza del test?

La training loss non è un endpoint. Il fine-tuning è giustificato solo da un miglioramento preregistrato su validation indipendente e poi confermato una sola volta su test sigillato, rispetto alle baseline non addestrate e al human-only workflow.

## 2. Autorità semantica e unità di valutazione

PRD v9 è l'obiettivo normativo; PRD v7 resta il contratto implementato nel root. Finché il registry v9 non è canonico:

- nessun benchmark può dichiarare v9 schema conformance;
- le classi nuove o modificate non vengono ricostruite localmente per analogia;
- parser e modelli emettono candidate structure, non Derivation Gold;
- public corpora restano `SILVER_AUXILIARY` e non sono reference standard del grafo N-Truth;
- `ObservedEvidenceScope` deve restare separato da `TargetPopulationClaim`, e una menzione di contrasto non prova `ContrastSupportClaim`.

L'unità primaria è l'**Experiment Bundle** completo. La valutazione sentence-level è ammessa solo per task ausiliari e non sostituisce graph-level/end-to-end evaluation.

## 3. Freeze prima di qualsiasi test

Prima di aprire test o external challenge devono essere versionati e firmati:

1. registry PRD v9, schema, parser contract, Rulebook e annotation guideline;
2. task definition, decisive fields e mapping policy;
3. corpus snapshot, hash, source/license manifest e schema version;
4. train/validation/test/external group manifest;
5. baseline prompts, retrieval index, constrained decoder e post-processing;
6. candidate model revisions, tokenizer revisions e quantization provenance;
7. seed set, model-selection rule e massimo numero di run;
8. metriche, confidence intervals, multiplicity policy e success/stop criteria;
9. failure taxonomy e protocollo qualitativo;
10. custode indipendente di test ed external challenge.

Ogni modifica successiva all'apertura è una deviazione versionata. Non si riscrive il protocollo retroattivamente.

## 4. Split e custodia anti-leakage

### 4.1 Group key

Lo split è un **blind group split** assegnato per famiglia indivisibile, con chiave
DOI → PMCID → PMID → upstream source ID. Appartengono allo stesso gruppo:

- articolo, preprint, versioni, errata e correzioni;
- abstract, Methods, caption, tabelle e supplementi;
- repository, accessioni, sample sheet e dataset collegati;
- stessa serie di laboratorio o protocollo, quando identificabile;
- traduzioni, paraphrase, augmentation e synthetic transformations dello stesso grafo;
- record duplicati o semanticamente equivalenti provenienti da corpus diversi.

La deduplicazione avviene prima dello split. Un group ID mancante rende il record non eleggibile.

### 4.2 Partizioni

| Partizione | Uso | Accesso durante sviluppo |
|---|---|---|
| Train | eventuale fit di adapter/classifier, synthetic controllato | team ML |
| Validation | prompt, HPO, checkpoint e threshold selection entro budget preregistrato | team ML |
| Test | stima finale interna una sola volta | evaluation custodian |
| External challenge | domini/lab/tecniche/stili unseen; validazione di generalizzazione | custode esterno o indipendente |

Test ed external devono essere sigillati in percorsi che training, retrieval, synthetic generation, prompt tuning e error analysis non possano leggere. Il loader di training non deve enumerarli. Hash commitment e conteggi minimi possono essere pubblici senza esporre contenuto o label.

Se un test viene aperto per debugging, diventa development data e deve essere sostituito prima della valutazione finale.

### 4.3 Contamination audit

Il report deve distinguere:

- **intra-corpus leakage:** gruppo presente in più split;
- **cross-corpus leakage:** stesso paper/testo/claim in fonti diverse;
- **transformation leakage:** derivati della stessa famiglia separati;
- **pretraining contamination:** benchmark pubblico plausibilmente visto dal base model;
- **procedural leakage:** label, schema hint o decision rule inclusi nel prompt/testo;
- **human leakage:** annotatore o custode coinvolto nella model selection del proprio test.

Non potendo dimostrare l'assenza dal pretraining, i benchmark pubblici misurano task transfer, non generalizzazione scientifica primaria.

## 5. Reference standard e condizioni H/A/H+A

La reference è N-Truth GOLD: annotazione umana indipendente sui campi decisivi, agreement misurato prima dell'adjudication, adjudication tracciata, provenance e rights clearance. Un record SILVER/WEAK/SYNTHETIC non entra nel denominatore gold primario.

Ogni bundle della valutazione principale è eseguito nelle tre condizioni preregistrate:

| Condizione | Procedura | Cosa misura |
|---|---|---|
| **H — Human-only** | reviewer usa materiali e UI senza output AI | human ceiling operativo, tempo, errori e astensione umana |
| **A — AI-only** | pipeline congelata senza correzione umana | capacità autonoma, false certainty, calibrazione e validità strutturale |
| **H+A — Human with AI assistance** | reviewer cieco alla reference può accettare, modificare o rifiutare candidate + evidence | qualità post-review, correction burden, automation bias e utilità reale |

L'ordine delle condizioni è randomizzato o controbilanciato per evitare learning/carry-over; lo stesso reviewer non vede lo stesso bundle in più condizioni senza washout e disegno appropriato. L'adjudicator non partecipa alla prediction review.

Endpoint H+A obbligatori:

- correttezza post-review del grafo e dei campi decisivi;
- tempo attivo e tempo totale;
- numero di decisive corrections, span corrections e rejected suggestions;
- false certainty accettata, errori nuovi introdotti dall'assistenza e casi di automation bias;
- tasso di astensione/clarification appropriata;
- delta rispetto a H con intervallo di confidenza, non solo media aggregata.

## 6. Baseline ladder

Tutte le baseline usano lo stesso snapshot autorizzato e lo stesso schema contract.

### B0 — Rules-only

- Rulebook e deterministic engine senza LLM;
- 100% sulle fixture canoniche approvate e zero regressioni come release gate;
- report separato di coverage: “nessuna regola applicabile” non è un errore se il caso è indeterminato;
- prova minima contro shortcut con counterexample e exception fixture per regola.

### B1 — Base zero-shot

- modello base senza adapter;
- singolo prompt versionato, constrained decoding e identico evidence budget;
- temperatura e decoding congelati;
- nessun esempio del benchmark nel prompt.

### B2 — Base few-shot

- esempi selezionati soltanto da train/development;
- nessun paper, laboratorio, transformation family o semantic duplicate condiviso con il caso valutato;
- numero e policy di selezione degli esempi congelati;
- confronto con B1 a parità di context budget.

### B3 — Retrieval/context enrichment

- retrieval solo da fonti autorizzate: Rulebook, registry, ontology crosswalk e train/development evidence;
- indice e document hashes congelati;
- nessuna indicizzazione di test/external o relative annotazioni;
- ablation `no retrieval`, `Rulebook only`, `evidence only` e combinazione;
- misurare retrieval recall@k, citation/evidence precision e unsupported-output rate.

### B4 — ModernBERT specialist

- [`answerdotai/ModernBERT-base`](https://huggingface.co/answerdotai/ModernBERT-base) come baseline encoder per routing, span/entity/relation extraction ausiliaria;
- non produce da solo l'Experiment Graph e non compete come generatore end-to-end;
- confronto con regole/CRF o linear head quando appropriato;
- task-specific macro-F1 e calibration; nessun mapping dalle label pubbliche ai target proibiti.

### B5 — Generative local tournament

Valutare senza proclamare un vincitore anticipato:

1. [`ibm-granite/granite-4.1-3b`](https://huggingface.co/ibm-granite/granite-4.1-3b) — primary provvisorio;
2. [`Qwen/Qwen3-4B-Instruct-2507`](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) — challenger structured-output/multilingual;
3. [`microsoft/Phi-4-mini-instruct`](https://huggingface.co/microsoft/Phi-4-mini-instruct) — challenger compatto.

Per ciascuno: zero-shot, few-shot e retrieval con stesso protocollo; revision/tokenizer/license fissati; modello quantizzato distinto dal source model; output constrained dallo stesso schema. La selezione avviene su validation senza test peek, considerando qualità, calibrazione, latenza, memoria e stabilità, non popolarità.

### B6 — Fine-tuned candidate, solo dopo il gate

Una eventuale 4-bit [MLX-LM](https://github.com/ml-explore/mlx-lm) QLoRA/LoRA è confrontata con B0–B5. Il suo vantaggio deve sopravvivere:

- almeno tre seed se la varianza è materialmente rilevante;
- ablation dell'adapter;
- controllo di regression per classe/domain;
- valutazione H/A/H+A;
- test sigillato ed external challenge.

Se B2/B3 raggiunge il criterio di non-inferiorità rispetto al fine-tuning con costo accettabile, non si addestra o non si promuove l'adapter.

## 7. Metriche primarie e secondarie

### 7.1 Structured output

- schema-valid rate prima di repair;
- schema-valid rate dopo repair, riportato separatamente;
- exact match canonico per record/campo;
- valid reference rate per node/edge/span;
- forbidden-field hallucination rate;
- abstention/indeterminate correctness.

Un repair che cambia la semantica è una correzione del sistema, non un output valido al primo tentativo.

### 7.2 Span, entity e relation

- precision, recall e F1 strict e relaxed per span;
- micro-F1 e macro-F1 per classi;
- relation F1 con argomenti e direzione corretti;
- evidence-support precision/recall;
- performance per lunghezza, sezione, formato e lingua.

### 7.3 Experiment Graph e campi scientifici

- node/edge precision, recall e F1;
- graph exact match e graph edit distance predefinita;
- macro-F1 e confusion matrix separate per `allocation_level`, `application_level`, `FactorRole`, `ContrastType`, `ContrastSupportClaim` e determinability categories quando il registry v9 le rende canoniche;
- exact match per `experimental_unit`, biological source count, independent unit count e conditional n solo sui casi determinabili;
- non-assignment rate sui casi insufficienti;
- errori distinti per ObservedEvidenceScope e TargetPopulationClaim;
- precision/recall per `DESIGN_REPLICATION`, `ANALYTICAL_DEPENDENCE` e `INFERENCE_SCOPE`.

Non aggregare campi semanticamente diversi in un solo “accuracy”. Un alert analitico non sostituisce un errore di design replication.

### 7.4 Calibrazione e selettività

Per probabilità o confidence score congelati:

- Brier score;
- expected calibration error con binning preregistrato;
- reliability diagram;
- negative log-likelihood se definita;
- risk-coverage curve, selective accuracy e AURC;
- accuracy/F1 a copertura fissata;
- calibration per classe, dominio e determinability state.

Se il modello non espone probabilità comparabili, usare conformal/selective score o margin definito prima del test; non inventare confidence da testo libero.

### 7.5 OOD e robustness

- domini: cell culture, in vivo, imaging, omics, pooling/repeated measures e combinazioni;
- formati: Methods, caption, table, supplementary, OCR-noisy e section-missing;
- perturbazioni controllate: conteggi cambiati, unità sostituite, negazione, ordine di frasi, distractor citations, abbreviazioni e parafrasi;
- linguistic shift e terminologia di laboratorio;
- unseen laboratory/corresponding-author, tecnica e source family nell'external challenge;
- detection/abstention OOD oltre alla task accuracy.

Le perturbazioni mantengono una semantic-preservation label revisionata; gli adversarial examples che cambiano la risposta corretta sono nuove fixture, non robustness paraphrases.

### 7.6 Utilità umana

- correction time e total review time;
- post-review exactness e graph correctness;
- decisive corrections per bundle;
- rejected/accepted suggestion precision;
- clarification usefulness;
- reviewer workload e disagreement;
- errori ad alta severità separati da errori cosmetici.

## 8. Failure taxonomy obbligatoria

Ogni errore può avere più tag, ma un primary failure è adjudicato:

1. source acquisition/OCR/encoding;
2. section routing o context omission;
3. span/entity boundary;
4. relation/coreference;
5. factor/contrast role confusion;
6. allocation vs application confusion;
7. unit-of-analysis vs experimental-unit confusion;
8. biological vs technical replicate confusion;
9. unsupported causal inference;
10. evidence-scope vs population-claim confusion;
11. missed ambiguity o false certainty;
12. schema/reference/serialization failure;
13. retrieval miss o irrelevant retrieval;
14. label leakage/shortcut;
15. OOD/domain/language failure;
16. human correction/automation-bias failure.

Il report include frequenza, severità, classe, dominio, split, modello e correzione necessaria, con esempi redatti secondo licenza/privacy.

## 9. Analisi statistica

- intervalli di confidenza cluster-aware per Experiment Bundle/family;
- confronti paired sullo stesso bundle quando il disegno lo consente;
- macro metriche primarie per class imbalance, più micro metriche di supporto;
- bootstrap o modello gerarchico preregistrato, mai bootstrap ingenuo per sentence quando il cluster è paper/lab;
- correzione per confronti multipli o gerarchia di endpoint congelata;
- missingness ed esclusioni riportate per sistema e classe;
- nessuna sostituzione dei missing con errori o negativi senza regola gold esplicita;
- effect size e intervalli, non solo p-value.

Le soglie numeriche di successo non vengono inventate in questo draft: devono essere congelate con biostatistico, wet-lab lead ed evaluation custodian dopo pilot di fattibilità e prima del test.

## 10. Criterio per giustificare il fine-tuning

Il fine-tuning può essere proposto solo se tutti i prerequisiti sono veri:

```yaml
normative_registry_v9_frozen: true
root_reality_gate_allows_substantive_training: true
gold_reference_and_human_agreement_available: true
licence_and_privacy_scope_verified: true
group_splits_frozen_and_audited: true
test_and_external_sealed: true
baseline_ladder_completed_on_validation: true
primary_metric_and_non_inferiority_margins_preregistered: true
local_runtime_reproducible: true
```

Poi l'adapter deve:

- migliorare il primary validation endpoint rispetto alla migliore baseline non fine-tuned oltre la soglia preregistrata;
- non peggiorare false-certainty, critical-error, OOD e calibration oltre i margini ammessi;
- offrire vantaggio H+A in qualità o burden rispetto a H e alla migliore baseline;
- rispettare memoria, latenza e sostenibilità locali;
- confermare il risultato sul test sigillato senza ulteriore tuning.

Se manca una di queste condizioni, la decisione resta **NO TRAINING**. Un miglioramento della training loss, di un benchmark pubblico o di una sola classe frequente non apre il gate.

## 11. Apple Silicon e riproducibilità

Il torneo è progettato per MacBook Pro M5 Pro con 24 GB di memoria unificata. La fattibilità ingegneristica non equivale a training readiness.

Per ogni run registrare:

- Git commit e worktree state;
- dataset snapshot ID, manifest hash e schema version;
- model/source revision, MLX conversion revision, tokenizer e chat template;
- precision/quantization, LoRA modules/rank/alpha/dropout;
- context length, batch size, gradient accumulation/checkpointing;
- optimizer, learning rate schedule, warmup, epochs/iterations e stopping rule;
- seed, software lock, macOS/MLX versions e hardware;
- peak unified memory, wall time, thermals se disponibili e checkpoint hashes;
- validation metrics, selected checkpoint e tutte le deviazioni.

Nello stato corrente non è ammesso alcun engineering smoke: tokenizzazione, training, prediction, metriche, calibrazione, checkpoint e resume falliscono chiuso finché MLX non consuma esclusivamente descriptor read-only anonimi/unlinked ereditati. Solo dopo quel runner e una nuova review potrà essere autorizzato un smoke minimale sacrificabile; il suo eventuale esito non selezionerà il modello e non produrrà evidenza scientifica.

## 12. Reporting minimo

Il report finale contiene:

1. diagramma del flusso e versioni congelate;
2. dataset card, tier/provenance, license matrix e leakage audit;
3. distribuzioni per label, dominio, lingua, formato e determinability;
4. H, A e H+A con uncertainty intervals;
5. baseline ladder completa, incluso risultato negativo;
6. per-class/confusion matrix e calibration/risk-coverage;
7. structured-output validity prima/dopo repair;
8. OOD, external challenge e failure taxonomy;
9. compute/memory/cost e reproducibility bundle;
10. decisione `FINE_TUNING_JUSTIFIED: YES | NO | INCONCLUSIVE` con blocker.

Nessun claim di validazione scientifica deriva dal solo protocollo, da test software locali, dallo smoke training o da public auxiliary corpora.

## 13. Stato corrente del protocollo

Questo documento definisce un protocollo futuro; non afferma che sia eseguibile o sia stato eseguito. In particolare restano aperti:

- registry e conformance PRD v9;
- real anchor e reference GOLD sufficiente;
- agreement umano e approval del protocollo;
- license scope per tutti gli asset;
- split protetti e custodia test/external;
- baseline reali e soglie statistiche preregistrate;
- confronto H/A/H+A;
- selezione del modello su evidenza;
- runner anonymous/unlinked inherited read-only FD e relativo security review.

Fino alla loro chiusura, ogni risultato è engineering o development evidence e il training sostanziale resta bloccato.
