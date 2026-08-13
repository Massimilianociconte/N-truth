# Portafoglio fonti per il modello piccolo v1

**Stato:** specifica decisionale; non autorizza training, valutazione o redistribuzione
**Data di ricognizione:** 2026-08-13
**Target normativo:** PRD v9
**Contratto root implementato:** PRD v7
**Decisione globale:** corpus pubblici utilizzabili solo come `SILVER_AUXILIARY`, previa autorizzazione granulare; nessuno soddisfa il Reality Gate o diventa N-Truth GOLD

## 1. Scopo e confini

Il portafoglio serve a scegliere dati per task ausiliari che migliorino la comprensione del testo scientifico senza sostituire il futuro corpus N-Truth GOLD. In particolare:

- una label pubblica come `randomization`, `control`, `cause` o `quantity` non è automaticamente una label N-Truth;
- nessun corpus pubblico qui censito può determinare da solo `experimental_unit`, `independent_n`, `independently_assigned`, `allocation_level`, `application_level` o `determinability_state`;
- la menzione di randomizzazione non prova il livello di allocazione; la presenza di animali, pozzetti o misure non prova indipendenza;
- le annotazioni native restano distinte dall'autorità N-Truth: `HUMAN_CURATED_*` descrive la produzione upstream, mentre l'uso N-Truth resta `SILVER_AUXILIARY`;
- una fonte priva di licenza o autorizzazione granulare verificata può essere ispezionata localmente solo se consentito, ma non può essere promossa a train, evaluation o redistribuzione;
- PRD v9 è il target normativo. Il root implementa PRD v7 e non possiede ancora il registry canonico v9; nessun adapter locale deve inventare `FactorRole`, `ContrastType`, `ContrastSupportClaim`, `ObservedEvidenceScope` o `TargetPopulationClaim`.

## 2. Provenance e regole comuni

Ogni asset ammesso deve essere identificabile almeno da repository o DOI, revisione immutabile, hash SHA-256, data di acquisizione, documento/famiglia, sezione, testo originale o riferimento risolvibile, trasformazione, tier nativo, tier N-Truth, decisione di licenza e schema version. Le trasformazioni non cancellano mai il parent checksum.

La chiave di gruppo globale segue, in ordine: DOI normalizzato, PMCID, PMID, identificativo upstream. Preprint, articolo, correzione, supplementi, dataset collegati, mirror e tutte le trasformazioni di una stessa famiglia restano nello stesso leakage group. Se l'identità del paper è ignota, il record resta non eleggibile; non si simula l'indipendenza con un ID di riga.

Le autorizzazioni sono separate:

```text
inspect != annotate != develop != train != evaluate != publish metrics != redistribute
```

Un valore mancante o `unknown` fallisce chiuso. Gli split upstream sono preservati come provenance, non accettati automaticamente come split N-Truth.

La tassonomia operativa richiesta non introduce un nuovo enum parallelo. Viene rappresentata con i contratti root già esistenti:

| Tier concettuale | Rappresentazione canonica corrente | Vincolo |
|---|---|---|
| GOLD | `AuthorityLevel.NTRUTH_GOLD` e record supervisionato conforme ai requisiti di review | mai emesso da adapter pubblico; seconda review, adjudication, provenance e rights obbligatori |
| SILVER | `AuthorityLevel.AUXILIARY`, con `SupervisionSource.HUMAN_PUBLIC` o `STRUCTURED_METADATA` | task ausiliari soltanto; target scientifici vietati esplicitamente |
| WEAK | `SupervisionSource.WEAK_RULE` con authority non GOLD | regola/versione/confidence e audit separati; mai promozione implicita |
| SYNTHETIC | `SupervisionSource.SYNTHETIC` | train/stress soltanto dopo il gate; vietato nei public adapter C0-C1 |
| UNVERIFIED / CANDIDATE | `AuthorityLevel.CANDIDATE` o record non eleggibile/review-required | quarantena finché schema, lineage, licenza e revisione non sono completi |

`NativeAnnotationTier.HUMAN_CURATED_GOLD` descrive soltanto l'autorità dell'annotazione originale del corpus e non equivale a N-Truth GOLD.

## 3. Fonti acquisite: decisione corrente

### 3.1 SourceData

| Campo | Valutazione |
|---|---|
| Fonte primaria | [Dataset card EMBO/SourceData](https://huggingface.co/datasets/EMBO/SourceData), [revisione ufficiale risolvibile fissata](https://huggingface.co/datasets/EMBO/SourceData/tree/04333ae21badc91671a537e875bbca61b62f87e3); il ref storico non più risolvibile resta nel lock come lineage |
| Task nativo | NER/NEL biomedico, assay extraction, ruoli sperimentali in figure caption |
| Granularità | token/pannello; l'export locale fissato non conserva un identificatore paper/panel affidabile per tutti i record |
| Dimensione osservata | 75.163 righe fisiche allineate per ciascuno dei task NER e `ROLES_MULTI`: 60.266 train, 8.201 validation, 6.696 test |
| Qualità | annotazione manuale upstream e label utili per entità/ruoli; non annota gerarchia sperimentale, unità o indipendenza |
| Licenza | dataset card dichiara CC BY 4.0; il pacchetto locale non contiene ancora una prova di licenza asset-level sufficiente a chiudere ogni uso |
| Leakage | assenza di paper identity nell'export locale: isolamento document-level non dimostrabile; tutti gli split devono restare bloccati per model use |
| Contaminazione | possibile sovrapposizione con articoli del futuro anchor e con pretraining del modello; richiede registro DOI/PMCID e confronto con ogni split protetto |
| Decisione | **INCLUSIONE CONDIZIONATA** come corpus ausiliario per entity/role tagging e caption parsing; `training_eligible=false`, `evaluation_eligible=false` finché licenza, paper identity e split non sono chiusi |
| Divieti | nessun mapping automatico verso causalità, experimental unit, allocazione o independent n |

SourceData è prezioso per insegnare la superficie linguistica delle figure, non la semantica epistemica di N-Truth. L'allineamento per riga e token verifica integrità tecnica, non indipendenza scientifica.

### 3.2 PreClinIE

| Campo | Valutazione |
|---|---|
| Fonte primaria | [Repository Ineichen-Group](https://github.com/Ineichen-Group/Preclinical_IE_Dataset), revisione fissata `f38df55a28505a77d30eefb5b867bbfdcc9baf25`, [paper BioNLP 2025](https://aclanthology.org/2025.bionlp-1.8/) |
| Task nativo | estrazione da studi preclinici di indicatori di rigore e caratteristiche come specie, sesso, strain, numerosità, randomizzazione e blinding |
| Granularità | 725 paper, 1.450 sezioni title/abstract o Methods; span/token e categorie document-level |
| Qualità | annotazione umana con subset sovrapposti e procedure di review; agreement variabile per label e task deve essere riportato per classe, non riassunto in un solo valore |
| Licenza | repository con MIT; il file non separa esplicitamente codice, annotazioni e testo degli articoli/PDF inclusi |
| Leakage | split obbligatorio per paper, non per sezione; abstract e Methods dello stesso paper restano uniti |
| Contaminazione | testo estratto da pubblicazioni e PDF: verificare diritti del testo, versioni/mirror, sovrapposizione con anchor, TAC, RoB e pretraining |
| Decisione | **CANDIDATO PRIORITARIO, BLOCCATO PER MODEL USE**; idoneo in prospettiva a routing Methods e indicator extraction dopo rights review, adapter canonico, audit IAA e split paper-level |
| Divieti | `randomization` è evidence mention, non prova `allocation_level`; `animals-number` non è `independent_n`; nessuna label di rigore diventa verdict |

È la fonte pubblica più vicina alla descrizione del design sperimentale, ma proprio questa vicinanza aumenta il rischio di scorciatoie semantiche. Gli esempi ambigui devono restare tali.

### 3.3 MeasEval

| Campo | Valutazione |
|---|---|
| Fonte primaria | [Repository ufficiale](https://github.com/harperco/MeasEval), revisione fissata `1fa738b6bc9b72c84c88a80344ca3ab39a310a44`, [SemEval-2021 Task 8](https://aclanthology.org/2021.semeval-1.38/) |
| Task nativo | quantity, unit, modifier, measured entity/property/qualifier e relazioni |
| Granularità | paragrafi scientifici; 448 file testo osservati nei partition locali, con 20 documenti senza TSV |
| Qualità | task condiviso manualmente annotato; difficoltà e agreement diversi per quantità, qualifier, entità e relazioni richiedono metriche separate |
| Licenza | README rinvia a articoli CC-BY nell'Elsevier OA-STM Corpus, ma il repository non contiene una licenza unica che chiuda annotazioni, testo e usi derivati |
| Leakage | gli split ufficiali train/eval contengono documenti sovrapposti e il trial non è automaticamente indipendente; raggruppare per article ID prima di qualsiasi nuovo split |
| Contaminazione | shared-task pubblico e plausibilmente noto ai modelli base; mai usare come prova principale di generalizzazione |
| Decisione | **QUARANTENA MODEL USE**; utile per validare parser di quantità e relazioni, ma non per train/eval finché license scope, missing annotations e overlap policy non sono chiusi |
| Divieti | una quantità o unità estratta non determina numerosità biologica, experimental unit, denominatore o estimando |

I 20 file testo privi di TSV restano `MISSING_ANNOTATION`/review-required. Non sono esempi negativi.

### 3.4 CRAFT

| Campo | Valutazione |
|---|---|
| Fonte primaria | [Repository CRAFT](https://github.com/lhunter-lab/CRAFT), release `v5.0.2`, [descrizione del corpus](https://pmc.ncbi.nlm.nih.gov/articles/PMC7243923/) |
| Task nativo | concept annotation, ontologie, struttura, coreference biomedica |
| Granularità | 97 articoli PMC Open Access; partition ufficiale 67 development e 30 evaluation, raffinata localmente in 60 train, 7 validation, 30 test |
| Qualità | annotazione specialistica ricca; il parser locale conserva solo catene coreference losslessly rappresentabili e marca le esclusioni |
| Licenza | annotazioni CC BY 3.0 nel `LICENSE.txt`; il testo di ogni articolo resta soggetto alla propria licenza PMC OA |
| Leakage | gruppo PMCID; tutte le viste/annotazioni di un articolo restano insieme; controllare overlap con altri corpora PMC e futuro anchor |
| Contaminazione | benchmark longevo, plausibilmente presente nel pretraining; valutazione solo ausiliaria e mai come test scientifico finale |
| Decisione | **INCLUSIONE CONDIZIONATA** per coreference/ontology auxiliary dopo verifica per-articolo delle licenze e adapter task-specific; non materiale training-ready corrente |
| Divieti | coreference linguistica non prova derivazione biologica, nesting sperimentale, causalità o indipendenza |

Le catene discontinuous o semanticamente non rappresentabili non devono essere troncate: vengono escluse con provenance e reason code.

## 4. Fonte ad alta priorità non ancora acquisita

### TAC 2018 SRIE

| Campo | Valutazione |
|---|---|
| Fonte primaria | [Pagina NIST SRIE](https://tac.nist.gov/2018/SRIE/), [indice dati 2018](https://tac.nist.gov/data/past/2018/SRIE18.html), [overview](https://tac.nist.gov/publications/2018/additional.papers/TAC2018.SRIE.overview.proceedings.pdf) |
| Task nativo | estrazione da Methods/Materials di fattori di study design in esperimenti animali e grouping dei dettagli in concetti |
| Pertinenza | **alta** per information extraction di design; comunque non annota direttamente il grafo epistemico N-Truth |
| Accesso/licenza | l'accesso ai dati TAC storici richiede credenziali; termini di partecipazione, testo PubMed e redistribuzione devono essere verificati prima dell'acquisizione |
| Contaminazione | benchmark pubblico dal 2018; eventuale evaluation deve essere secondaria e documentare possibile esposizione del modello base |
| Decisione | **FUTURE PRIORITY / HOLD**; acquisire solo dopo decisione data-steward firmata, lock immutabile e mapping review umano verso task ausiliari |

TAC SRIE è il miglior candidato pubblico successivo perché lavora sui Methods di esperimenti animali. Non deve essere retrofittato in label v9 non ancora canoniche.

## 5. Fonti normative e ontologiche

| Fonte | Uso ammesso | Uso vietato | Decisione |
|---|---|---|---|
| [ARRIVE 2.0](https://arriveguidelines.org/arrive-guidelines) | guideline, definizioni, coverage checklist, costruzione di test controllati e training degli annotatori | generare automaticamente ground truth dagli item di reporting; equiparare “reported randomisation” a corretta allocazione | **INCLUDERE COME RIFERIMENTO**, mai corpus GOLD automatico |
| [Ontology for Biomedical Investigations](https://github.com/obi-ontology/obi) / [OBO Foundry](https://obofoundry.org/ontology/obi.html) | normalizzazione terminologica e candidate mappings versionati | modificare tassonomia N-Truth per comodità; trattare assiomi ontologici come evidenza del paper | **INCLUDERE COME ONTOLOGY CANDIDATE**, con crosswalk revisionato |

Queste fonti possono informare il Rulebook e il futuro registry v9, ma non autorizzano l'introduzione locale di nuove label.

## 6. Fonti NLP adiacenti: hold, exclude o evaluation-only

| Fonte | Evidenza primaria e dimensione | Valore potenziale | Rischio principale | Decisione v1 |
|---|---|---|---|---|
| [BioCause](https://www.nactem.ac.uk/biocause/) | 19 full text OA, 851 relazioni causali | detection di causal language e cause/effect span | CC BY-NC-SA 3.0 per annotazioni più licenza per-articolo; causal claim linguistico non è validità causale | **HOLD / ROBUSTNESS-ONLY** dopo rights review; vietato come causal gold N-Truth |
| [BioRED](https://pmc.ncbi.nlm.nih.gov/articles/PMC9487702/) | 600 abstract, entity/relation/novelty annotations | document-level NER/RE, distinzione finding/background | articolo CC BY-NC; termini dell'asset vanno verificati; task non sperimentale | **FUTURE AUXILIARY**, bassa priorità rispetto a TAC/PreClinIE |
| [SciREX](https://aclanthology.org/2020.acl-main.670/) | document-level entities, coreference e n-ary relations in articoli ML | struttura document-level e relazioni n-arie | dominio computer science; forte mismatch con biomedicina/design; possibile contamination | **OOD/ARCHITECTURE BENCHMARK**, non train corrente |
| [EBM-NLP](https://github.com/bepnye/EBM-NLP) | 4.993 abstract RCT con P/I/O crowdsourced | PICO extraction e weak-supervision stress | basso agreement span riportato, dominio clinico, crowd labels; licenza/abstract rights da chiudere | **EXCLUDE DAL TRAIN v1**, possibile robustness set separato |
| [SciFact](https://github.com/allenai/scifact) | circa 1,4k claim esperti con evidence/rationale | evidence retrieval e claim verification | claim sintetizzati, dominio ampio, non design; test pubblico/leaderboard contamination | **EVALUATION-ONLY ADIACENTE**, mai N-Truth scientific test principale |
| [RoB preclinico 7.840](https://pmc.ncbi.nlm.nih.gov/articles/PMC9298308/) | full text con cinque label document-level di reporting; review umane | detection di frasi su randomizzazione, blinding, esclusioni | dati aggregati da più progetti, disponibilità e licenze dei full text non dimostrate; split pubblicato casuale, label “reported” | **HOLD LICENCE/ACCESS**; se acquisito, rifare group split e usare solo indicator extraction |
| [RoBBR](https://aclanthology.org/2025.emnlp-main.160/) | oltre 500 studi, task di risk-of-bias judgement e evidence retrieval | benchmark human-in-the-loop e reasoning/evidence | CC BY-NC; dominio prevalentemente clinical review; label RoB non coincide con Experiment Graph | **FUTURE EVAL CANDIDATE**, mai train senza autorizzazione |
| [RobotReviewer unseen set](https://zenodo.org/records/6908146) | 3.324 PDF OA con RoB annotations | challenge esterno per evidence retrieval | licenze PDF per-articolo, Cochrane-derived judgments, rischio di aprire un test “unseen” durante sviluppo | **SEALED EXTERNAL CANDIDATE**; non scaricare finché protocollo e custode non sono congelati |

## 7. Fonti esplicitamente escluse dal knowledge path corrente

Sono escluse dal training sostanziale del modello piccolo:

- dataset con label automatiche o derivate da modelli senza gold umano separabile;
- benchmark il cui testo o annotazioni non hanno una base di uso verificabile;
- corpora clinical/EHR con dati soggetti a DUA o privacy non necessari al micro-dominio;
- dati sintetici generati da un LLM e poi riusati come giudice o fonte di ulteriori generazioni;
- esempi che incorporano la label nella consegna o usano template troppo uniformi;
- training set preconfezionati di causal reasoning che confondono causal language, associazione e validità del design;
- qualunque test set già aperto per prompt/model selection, che diventa development evidence e perde il ruolo di test indipendente.

## 8. Dati sintetici: uso limitato

I dati sintetici sono ammessi solo nel train o nello stress testing e restano `SYNTHETIC`; non diventano `NTRUTH_GOLD`. Ogni famiglia sintetica mantiene graph seed, generator ID/version, prompt hash, transformation family, model/judge provenance e human review status.

Prima dell'ammissione servono:

1. validazione schema e Rulebook;
2. controllo che la label non sia esplicitata nel testo;
3. deduplicazione esatta, near e semantic family-level;
4. adversarial minimal pairs e variazione linguistica;
5. revisione umana sui campi decisivi;
6. limite di quota preregistrato per task/classe;
7. quarantena automatica se giudice e generatore condividono modello o prompt lineage incompatibile.

Non è ammesso synthetic-on-synthetic curriculum senza nuovo anchor umano.

## 9. Ordine operativo raccomandato

1. Congelare registry, schema e Rulebook PRD v9 prima di nuovi mappings semantici.
2. Chiudere per asset le autorizzazioni SourceData, PreClinIE, MeasEval e CRAFT.
3. Recuperare paper identity/lineage affidabile o mantenere non eleggibili i record.
4. Implementare adapter canonici task-specific senza label N-Truth proibite.
5. Valutare accesso/licenza TAC 2018 SRIE come prima nuova fonte.
6. Creare il real anchor N-Truth indipendente e doppiamente revisionato.
7. Deduplicare tutti i candidati contro anchor, development, sealed test ed external challenge prima dello snapshot.
8. Implementare il runner anonymous/unlinked inherited read-only FD; solo dopo eseguire il protocollo baseline e considerare il fine-tuning se Reality Gate root e gate v9 sono aperti.

## 10. Condizione di inclusione nello snapshot

Una fonte può entrare in un validated snapshot solo se esistono contemporaneamente:

- revisione e hash immutabili;
- asset manifest e lineage completi;
- licenza/DUA granulare con `development_allowed` e/o `evaluation_allowed` espliciti;
- schema adapter compatibile con il registry canonico;
- audit di offset, label, missingness, duplicate e artefatti;
- leakage groups non vuoti e split indipendenti;
- confronto con contamination registry dei modelli candidati;
- approvazione del data steward per lo specifico uso.

Il superamento di questo gate produce solo un dataset autorizzato al task dichiarato. Non soddisfa automaticamente scientific readiness, v9 conformance o Reality Gate.
