---
title: "N-TRUTH"
subtitle: "Product & Scientific Requirements Document"
author: "Massimiliano Ciconte - Laureato in Scienze Biologiche (L-13), Università degli Studi di Milano"
date: "6 agosto 2026"
lang: it-IT
---

**Versione:** 8.0 - REALITY-ANCHORED · FORMAL-SEMANTICS · CLAIM-SPECIFIC · AI-PRESERVED  
**Nome del prodotto:** N-Truth, nome provvisorio soggetto a naming review  
**Stato:** specifica scientifica e di prodotto completa; major scientific-contract revision della v7.0 con scopo finale invariato  
**Hardware locale di riferimento:** MacBook Pro con Apple M5 Pro, 24 GB di memoria unificata e SSD da 1 TB  
**Licenza prevista del codice:** Apache-2.0; licenze distinte per documentazione, dati e pesi quando necessario  
**Dominio bootstrap:** esperimenti in vitro semplici con colture cellulari, un fattore primario, due livelli, un endpoint e riferimenti prevalentemente espliciti  
**Principio di release:** nessun claim scientifico supportato senza teoria derivativa versionata, real anchor umano, valutazione end-to-end indipendente e riduzione misurabile del carico di revisione  

> **STATUTO DEL DOCUMENTO** - L'obiettivo finale di N-Truth NON cambia: il sistema completo deve combinare un parser AI specializzato, realmente addestrato e valutato, un Experiment Graph ispezionabile, conferma umana, una Derivation Theory normativa, un motore scientifico deterministico e validazione indipendente su dati reali. La versione 8.0 rafforza il contratto attorno a **Reality Gate**, **Core Semantic Kernel**, **Derivation Theory**, **claim-specific determinability**, **open-world semantics**, **Value of Abstention** ed **end-to-end validation**. Train D non sostituisce Train A; il synthetic non sostituisce il gold reale; un output strutturato non equivale a un'interpretazione scientificamente corretta; `DETERMINATE` non equivale ad approvazione del disegno.

# Nota editoriale sulla revisione 8.0

La revisione 8.0 nasce da una seconda attività di red-team sul PRD v8.0, orientata non alla fattibilità operativa ma alla **solidità epistemica, statistica e formale del nucleo derivativo**. Il report esterno ha individuato correttamente alcune lacune centrali: la teoria di derivazione di unità sperimentale e conteggi indipendenti non era ancora formalizzata separatamente dal Rulebook; `DeterminabilityState` rischiava di essere letto come giudizio sulla qualità del disegno; alcune semantiche open-world erano ambigue; l'interference layer era descritto ma non aveva conseguenze normative sufficientemente esplicite; e la valutazione non definiva ancora in modo completo il target end-to-end consumato dall'utente.

La revisione è stata verificata contro il testo effettivo della v7.0 e contro fonti primarie su unità sperimentale, interference, estimand, agreement annotativo, valutazione gerarchica e benchmark contamination [R01-R02, R35-R46]. Il verdetto consolidato è:

> **Il nucleo architetturale di N-Truth resta valido, ma la v7.0 necessitava di una teoria formale dei claim derivati e di una validazione end-to-end che non si limitasse alla conformità del Rulebook.**

La versione 8.0:

- preserva l'obiettivo finale AI + motore deterministico;
- introduce una **Derivation Theory** normativa e versionata, distinta dal Rulebook eseguibile;
- ridefinisce i campi decisivi in modo controfattuale e claim-specifico, evitando circolarità;
- rende la determinabilità **specifica per claim** e separa obbligatoriamente determinabilità, supporto evidenziale e adeguatezza del disegno;
- distingue assignment unit, application unit, effective exposure unit/cluster, experimental unit, biological-source count, analytical unit e inference scope;
- introduce `DerivedClaim`, `SupportGrade`, `KnowledgeState`, `SensitivityRecord`, `ScenarioCoverage` e `ProfileCoverageStatement`;
- sostituisce la gerarchia lineare delle fonti con un modello ortogonale di source class, authority type ed evidence basis;
- formalizza le conseguenze di interference ed exposure mapping senza trasformare N-Truth in un causal inference engine;
- aggiunge criteri di boundary per Experiment Block e semantica di equivalenza dei grafi;
- introduce un registro canonico dei conteggi e invarianti scope-aware;
- separa il supporto statistico informativo dalle raccomandazioni di analisi, che restano bloccate finché non esiste un reference set validato;
- aggiunge valutazione end-to-end, residual-error audit dopo HITL, precisione cluster-aware e contamination attestation dell'External Challenge;
- sostituisce il concetto di “reference stability” con **reference stability**, perché l'accordo umano non è una prova automatica di verità;
- mantiene il Reality Gate, il Bootstrap Core, la Synthetic Data Factory, il Value of Abstention e il programma di acquisizione del real gold.

Alcune proposte del report sono state accolte con modifica scientifica. In particolare:

- non si richiede che tutte le quattro dimensioni di indipendenza siano risolte per ogni singolo claim: ciascun claim dichiara le proprie precondizioni e le dimensioni non pertinenti devono essere marcate `NOT_APPLICABLE_TO_CLAIM` con rationale;
- l'interference non cambia automaticamente l'unità sperimentale: può modificare l'esposizione realizzata, l'estimand supportato, la portata inferenziale o il livello al quale la separabilità del trattamento è effettiva;
- l'unità sperimentale resta principalmente legata al fattore e al meccanismo di assegnazione; contrasto, endpoint e timepoint rendono specifici i conteggi, le esclusioni, lo scope e i claim, ma non riscrivono arbitrariamente la storia di assegnazione;
- non viene introdotto uno stato separato `DETERMINATE_ON_SELF_REPORT`: la determinabilità resta epistemica, mentre la qualità del supporto è rappresentata da `SupportGrade` e dalla sensibilità alle conferme decisive;
- journal, venue e anno non sono leakage group primari: vengono aggiunti `study_family_id`, `document_lineage_id`, `laboratory_or_facility_group` e un contamination-risk record per il backbone.

Le correzioni non demoliscono componenti già validi. La v8.0 è una **major scientific-contract revision**, non una riscrittura dello scopo.

# Indice

- 0. Controllo del documento e contratto interpretativo
- 1. Sintesi esecutiva
- 2. Problema scientifico e motivazione
- 3. Posizionamento rispetto a DRIVER, ARRIVE, EDA e standard di metadata
- 4. Visione di prodotto e strategia coordinata
- 5. Target, personas e bisogni
- 6. Flussi di utilizzo e casi d'uso
- 7. Definizioni scientifiche vincolanti e Derivation Theory
- 8. Modello formale dell'Experiment Graph
- 9. Modello epistemico, dell'evidenza e open-world semantics
- 10. Motore deterministico e claim-specific determinability
- 11. Supporto statistico: capacità, guardrail e limiti
- 12. Ruolo centrale e architettura del modello AI
- 13. Contratto del parser AI e del verifier
- 14. Strategia dati complessiva
- 15. Synthetic Data Factory e revisione dei facsimile manuali
- 16. Fonti pubbliche, baseline e condizioni d'uso
- 17. N-Truth Experiment Graph Corpus e unit economics
- 18. Annotazione, adjudication e reference stability
- 19. Collaborazione con professori, ricercatori e laboratori
- 20. Architettura software
- 21. Requisiti funzionali
- 22. Requisiti non funzionali
- 23. UX, adozione e report
- 24. Strategia di valutazione end-to-end
- 25. Hardware, context engineering e strategia di training
- 26. Ingegneria, repository e testing
- 27. Privacy, etica, licenze e uso responsabile
- 28. Roadmap completa e stage gate
- 29. Team, governance e sostenibilità
- 30. Rischi e mitigazioni
- 31. KPI e criteri di successo
- 32. Definition of Done
- 33. Istruzioni vincolanti per un agente AI di sviluppo
- 34. Riferimenti essenziali
- Appendice A - Esempio completo di Experiment Bundle v8
- Appendice B - Template di annotazione v8
- Appendice C - Domande minime per dominio
- Appendice D - Pilot di reference stability
- Appendice E - Modulo per contributori di dati
- Appendice F - Prima sequenza operativa
- Appendice G - Matrice delle baseline AI
- Appendice H - Protocollo per question usefulness, burden e residual audit
- Appendice I - Canonical Training Record minimo
- Appendice J - Facsimile Render Manifest
- Appendice K - Review matrix delle dodici tavole
- Appendice L - Correzioni minime prima dell'uso
- Appendice M - Claim-specific Determinability Reference
- Appendice N - Derivation Theory Decision Matrix
- Appendice O - SampleSheetSpec iniziale v8
- Appendice P - Count Registry, event timing ed edge case
- Appendice Q - Resource Gate Checklist
- Appendice R - Confirmation Support, Sensitivity e RuleChallenge
- Appendice S - Synthetic Task Use Matrix v8
- Appendice T - Runtime Resource Budget
- Appendice U - Lean Governance Matrix
- Appendice V - Audit v6.1 preservato
- Appendice W - Matrice di risposta alla review Qwen 3.8 Max
- Appendice X - Bootstrap Core, Core Semantic Kernel e profili
- Appendice Y - Causal, Exposure e Measurement Context Reference
- Appendice Z - Real Anchor Acquisition Portfolio
- Appendice AA - Implementation Status Snapshot, 6 agosto 2026 - non normativo
- Appendice AB - Changelog v7.0 preservato
- Appendice AC - KnowledgeState e open-world semantics
- Appendice AD - Matrice di risposta alla critical review v7.0
- Appendice AE - Migration map v7 -> v8
- Appendice AF - DerivedClaim e ReportBundle contract
- Appendice AG - External Challenge Contamination Attestation
- Appendice AH - Changelog v8.0

# 0. Controllo del documento e contratto interpretativo

## 0.1 Scopo

Questo documento stabilisce in modo prescrittivo:

- il problema scientifico che N-Truth deve risolvere;
- il valore da offrire prima, durante e dopo l'esperimento;
- il Bootstrap Core, il Full Scientific Record, il Core Semantic Kernel e i profili estesi;
- la **Derivation Theory** che definisce i claim scientifici derivabili da un grafo validato;
- la separazione tra teoria scientifica, Rulebook eseguibile e output del software;
- il modello di autorità, supporto evidenziale, conflitto, sensibilità e revisione umana;
- le responsabilità rispettive di parser AI, hard verifier, revisione umana, Derivation Theory e rules engine;
- i dati necessari per fixture, Theory Reference Set, Derivation Gold, Parser Gold, calibration, training ed external validation;
- le condizioni per usare synthetic, silver e dati cross-domain;
- la semantica open-world di campi assenti, sconosciuti, non applicabili o conflittuali;
- le metriche e i gate che precedono ogni claim di release;
- come il progetto deve evolvere senza ridurre il deliverable AI finale.

Il PRD è destinato a collaboratori umani e ad agenti AI. Un agente NON DEVE interpretare il percorso execution-first o il rafforzamento formale come riduzione dello scopo finale: l'analisi automatica mediante componenti AI locali o localmente distribuibili resta un deliverable obbligatorio della visione completa.

## 0.2 Linguaggio normativo e termini aggiunti

| Termine | Significato vincolante |
|---|---|
| **DEVE / DEVONO** | Requisito obbligatorio. |
| **NON DEVE** | Divieto esplicito. |
| **DOVREBBE** | Requisito fortemente raccomandato; la deviazione va motivata. |
| **PUÒ** | Capacità facoltativa. |
| **Bootstrap Core** | Sottoinsieme minimo di campi e relazioni necessario per il micro-dominio iniziale e per il primo pilot umano. |
| **Core Semantic Kernel** | Semantica profilo-invariante: claim, KnowledgeState, authority/evidence, query scope, counts, determinability e provenance. |
| **Full Scientific Record** | Record completo e versionato, inclusi lifecycle counts, alternative, causal/exposure/measurement context, provenance e profili estesi. |
| **Derivation Theory** | Specifica scientifica normativa, indipendente dal codice, che definisce precondizioni e conseguenze dei claim derivati. |
| **Rulebook** | Implementazione eseguibile e versionata della Derivation Theory per un profilo. Non è la fonte della teoria. |
| **DerivedClaim** | Singolo claim versionato per una `InferentialQuery`, con valore, stato di determinabilità, support grade, assunzioni, sensitivity e proof trace. |
| **Claim-specific determinability** | Applicazione di `DeterminabilityState` a un claim specifico; non equivale a qualità del disegno. |
| **Design adequacy finding** | Finding separato su replicazione, confondimento, interference, scope o dipendenza analitica. Non è `DeterminabilityState`. |
| **KnowledgeState** | Stato open-world di un campo: `PRESENT`, `ABSENT_EXPLICIT`, `NOT_REPORTED`, `UNKNOWN`, `NOT_APPLICABLE`, `CONFLICTING`. |
| **SupportGrade** | Qualifica non probabilistica della base evidenziale di un claim o predicato decisivo. |
| **ScenarioCoverage** | Attestazione che un insieme di scenari è `EXHAUSTIVE_WITHIN_PROFILE`, `NON_EXHAUSTIVE` o `UNKNOWN`. |
| **Reality Gate** | Gate che impedisce fine-tuning sostanziale o claim AI quando mancano real anchor, split protetti, licenze, reference stability o revisione umana. |
| **Decisive predicate** | Predicato che, secondo una Derivation Theory versionata, può cambiare valore o stato di un claim specifico in un controfattuale ammissibile. |
| **Theory Reference Set** | Casi e controfattuali expert-reviewed che verificano la teoria indipendentemente dall'implementazione del Rulebook. |
| **Train D** | Linea deterministica: schema, wizard, Derivation Theory, Rulebook, report e artefatti prospettici. |
| **Train A** | Linea AI: parsing assistivo, corpus, training, calibrazione ed external validation. |
| **Minimum Viable Train A** | Baseline reale minima: testo Methods/caption, output strutturato, hard verification, revisione umana e metriche di burden. |
| **Gold reale** | Annotazione umana autorizzata e, sui predicati decisivi, indipendente o adjudicata. |
| **Reference stability** | Stabilità del reference standard misurata con agreement, cross-role review, adjudicator test-retest e gold-uncertainty audit; non è un “reference stability” assoluto. |
| **Synthetic augmentation** | Dati graph-first per training, fixture e stress test; mai real gold o final evaluation. |

## 0.3 Modello di autorità, evidenza e derivazione

La v8.0 abbandona una graduatoria lineare unica. Ogni affermazione deve registrare tre dimensioni ortogonali:

1. **source class** - documento, sample sheet, instrument log, metadata, chiarimento, output del modello;
2. **authority type** - autore, utente, annotatore, domain expert, adjudicator, sistema;
3. **evidence basis** - direct record, structured direct, assertion, inference, confirmation, adjudication.

Regole normative:

- `RULE_DERIVATION` non è una fonte fattuale e non “vince” contro una fonte: trasforma fatti validati in claim derivati;
- un output AI non può prevalere su una dichiarazione esplicita o su un record strutturato;
- una dichiarazione dell'autore resta `AUTHOR_ASSERTION` finché non specifica il meccanismo richiesto;
- un chiarimento dell'autore o dell'utente può risolvere un fatto locale, ma il supporto deve essere qualificato e le fonti incompatibili restano nel `ConflictRecord`;
- una adjudication sceglie un reference interpretation nello scope dichiarato, ma non cancella la storia del disaccordo;
- il planned design e l'executed design devono avere source context separati; un sample sheet pianificato non prevale automaticamente su un record eseguito;
- un esperto che contesta una derivazione non modifica direttamente il `RuleResult`: crea un `RuleChallenge` e, se accolto, una nuova versione della Derivation Theory/Rulebook con re-derivation.

> **PRINCIPIO** - Le fonti descrivono o dichiarano l'esperimento; non sono l'esperimento stesso. N-Truth rende trasparenti evidenza, assunzioni e limiti, ma non può osservare retroattivamente fatti non registrati.

## 0.4 Authority type, evidence basis e support grade

| Campo | Valori minimi | Uso |
|---|---|---|
| `authority_type` | `SYSTEM_INFERENCE`, `USER_CONFIRMATION`, `AUTHOR_CLARIFICATION`, `ANNOTATOR_CONFIRMATION`, `DOMAIN_EXPERT_REVIEW`, `EXPERT_ADJUDICATION`, `RULE_DERIVATION` | Chi ha prodotto o confermato l'elemento. |
| `evidence_basis` | `DIRECT_RECORD`, `STRUCTURED_DIRECT`, `AUTHOR_ASSERTED`, `SELF_REPORT`, `CORROBORATED_CONFIRMATION`, `INFERRED_CANDIDATE`, `ADJUDICATED_REFERENCE` | Su quale base epistemica poggia. |
| `support_grade` | `ADJUDICATED`, `CORROBORATED_DIRECT`, `DIRECT_SINGLE_SOURCE`, `AUTHOR_CLARIFIED`, `SELF_REPORT_ONLY`, `ASSERTION_ONLY`, `MODEL_CANDIDATE`, `CONFLICTED` | Come deve essere mostrato e usato. |

`SupportGrade` NON è una probabilità e non sostituisce la calibration. Un claim può essere `DETERMINATE` ma `SELF_REPORT_ONLY`; in questo caso il report deve mostrare il qualifier e la sensitivity associata.

## 0.5 Documenti derivati obbligatori

| Documento | Momento minimo | Owner minimo |
|---|---|---|
| Bootstrap Core Specification | Prima del reality-check pilot | Product owner + reviewer metodologico |
| Core Semantic Kernel Specification | Prima di qualunque schema profilo-specifico | Biostatistico/metodologo + engineering |
| Derivation Theory v0.x | Prima di derivare EU o conteggi | Biostatistico + wet-lab reviewer |
| Profile Predicate Closure Argument | Prima di dichiarare `DETERMINATE` nel profilo | Biostatistico/metodologo |
| Theory Reference Set Protocol | Prima di validare il Rulebook | Biostatistico + reviewer esterno |
| Rulebook versionato | Prima della v0.1-D | Biostatistico + wet-lab reviewer |
| Claim-specific Determinability Table | Prima della prima regola | Biostatistico + wet-lab reviewer |
| Design Adequacy Finding Registry | Prima dei report scientifici | Biostatistico/metodologo |
| KnowledgeState & Null Semantics Specification | Prima di congelare lo schema | Data lead + engineering |
| Confirmation Support & Sensitivity Policy | Prima della prima human confirmation | Biostatistico + UX/review lead |
| Experiment Block Boundary Policy | Prima del routing multi-block | Domain reviewer + engineering |
| Graph Equality & Scoring Specification | Prima di IAA e benchmark graph-level | Annotation lead + ML lead |
| Count Registry & Invariant Specification | Prima dei lifecycle count | Biostatistico + data engineer |
| Scenario Coverage Protocol | Prima di `MULTIPLE_PLAUSIBLE_GRAPHS` | Rulebook owner + reviewer |
| External Challenge Contamination Protocol | Prima di congelare il challenge | ML lead + custodian |
| End-to-End Validation Protocol | Prima della release AI | Biostatistico + validation lead |
| Measurement Process Context Specification | Prima dell'Imaging Profile | Imaging reviewer + biostatistico |
| Strategy Reference Set | Prima di raccomandare famiglie di analisi | Biostatistico esterno |
| Tutti i documenti obbligatori della v7.0 non sostituiti | Secondo i gate già definiti | Owner già specificati |

## 0.6 Invarianza dello scopo e cambiamenti della versione 8.0

La versione 8.0 NON riduce lo scopo finale. Cambia il contratto scientifico dei claim derivati.

Principali cambiamenti:

- Derivation Theory separata dal Rulebook;
- decisive predicate definito controfattualmente e claim-specifico;
- `DeterminabilityState` applicato ai singoli `DerivedClaim`;
- report-level state distinto dai claim state;
- `DesignAdequacyFinding` obbligatoriamente separato dalla determinabilità;
- support grade e sensitivity per conferme decisive;
- open-world semantics senza bare `null` o liste vuote ambigue;
- interference/exposure con conseguenze normative su esposizione, estimand e scope;
- assignment facts separati dalle proiezioni query-specifiche;
- scenario coverage esplicita;
- end-to-end report scoring e residual-error audit;
- contamination attestation e cluster-aware precision;
- Strategy module in `HANDOFF_ONLY` finché non validato;
- profile-invariant kernel separato dalle estensioni.

## 0.7 Reality Gate v8

Il training sostanziale e i claim scientifici sono bloccati finché non sono veri tutti i requisiti pertinenti:

```yaml
schema_stable_on_real_cases: true
core_semantic_kernel_reviewed: true
derivation_theory_reviewed: true
profile_predicate_closure_reviewed: true
human_second_review_completed: true
blocking_schema_gaps: 0
real_anchor_available: true
license_scope_verified: true
train_dev_test_split_frozen: true
decisive_predicates_reviewed: true
reference_stability_report_available: true
real_baseline_executed: true
synthetic_factory_human_calibrated: true
end_to_end_metric_contract_frozen: true
external_challenge_contamination_protocol_ready: true
```

La presenza di public corpora, structured decoding, engineering smoke, fixture complete o SYN-G1 NON soddisfa il Reality Gate.

# 1. Sintesi esecutiva

N-Truth è una piattaforma open source, local-first e human-in-the-loop per rendere esplicito, ispezionabile e computazionalmente verificabile il disegno sperimentale biologico. Il problema centrale è che il numero di misure - cellule, immagini, campi, sezioni, pozzetti o letture - non coincide automaticamente con il numero di unità alle quali un intervento è stato assegnato in modo indipendente e sulle quali può essere sostenuta l'inferenza.

Il sistema finale riceve una combinazione di:

- piano sperimentale e risposte del ricercatore;
- Methods, caption e paragrafi statistici;
- sample sheet CSV/XLSX;
- metadata REMBI, ISA, OME/OMERO o equivalenti;
- struttura cartelle e convenzioni dei file;
- codice statistico read-only;
- registri di piano, esecuzione e deviazioni.

Il parser AI produce esclusivamente evidence span, entità, conteggi, eventi, relazioni, grafi candidati, alternative, conflitti e missing predicates. Un hard verifier controlla sintassi, schema, integrità referenziale, semantica open-world, supporto delle evidenze e invarianti. I predicati decisivi vengono confermati, corretti o lasciati sconosciuti da una persona. Solo dopo, il Rulebook - implementazione della Derivation Theory - produce un `DerivedClaimSet` specifico per la `InferentialQuery`.

![](ntruth_v8_assets/fig1_neurosymbolic_v8.png){width=96%}

*Figura 1 - Il parser propone; fonti e revisori qualificano i fatti; la Derivation Theory produce claim specifici, non un giudizio globale sul paper.*

## 1.1 Tesi di prodotto

N-Truth deve dimostrare due valori distinti:

1. **valore prospettico immediato** - aiutare a progettare e documentare un esperimento semplice in pochi minuti;
2. **valore AI misurato** - ridurre tempo ed errori nella ricostruzione senza aumentare falsa certezza residua dopo la revisione umana.

La prima feature ad alto valore è la Quick Design Session:

- definizione di unità, fattore, livelli, endpoint e contrasto;
- sample sheet iniziale;
- ID e naming convention;
- bozza Methods;
- una domanda decisiva primaria e, se necessario, domande secondarie ordinate per utilità;
- export per il biostatistico;
- report separato di record completeness e design findings.

Il target iniziale di completamento in meno di 10 minuti è PROVISIONAL e deve essere validato con utenti reali.

## 1.2 Architettura fondamentale

N-Truth non è soltanto un rules engine e non è soltanto un LLM.

- Senza Derivation Theory, il Rulebook rischia di validare soltanto la propria coerenza interna.
- Senza rules engine, i claim non sarebbero testabili e riproducibili.
- Senza AI, la ricostruzione multi-documento non scalerebbe.
- Senza human-in-the-loop, omissioni, assertions e auto-report diventerebbero falsa certezza.
- Senza support grade e sensitivity, una conferma debole apparirebbe identica a una conferma documentata.
- Senza real gold e residual audit, non sarebbe possibile distinguere comprensione, shortcut e conferma umana fallibile.
- Senza un percorso prospettico, molti fatti decisivi resterebbero irrecuperabili.

## 1.3 Obiettivo finale invariato

La visione completa è una piattaforma capace di:

1. assistere la pianificazione;
2. generare sample sheet e record coerenti;
3. conservare piano ed eseguito senza sovrascrittura;
4. leggere documenti e file di laboratorio;
5. ricostruire scenari plausibili e dichiararne la copertura;
6. identificare missing predicates decisivi secondo una teoria versionata;
7. porre domande brevi e operative;
8. produrre un grafo confermato con support grade;
9. applicare regole validate contro un Theory Reference Set;
10. generare claim-specific determinability, proof trace e design adequacy findings separati;
11. produrre report per Methods, analisi e provenance;
12. apprendere da correzioni autorizzate senza contaminare test o external challenge;
13. generalizzare progressivamente a nuovi profili.

## 1.4 Release train e anti-deferral covenant

### Train D - deterministico

Produce Core Semantic Kernel, Bootstrap Core, wizard, sample sheet, Derivation Theory, Rulebook, proof trace, report, Theory Reference Set e Derivation Gold.

### Train A - AI assistiva

Produce parser, baseline, training, calibrazione, astensione, residual audit ed external validation.

### Minimum Viable Train A

Train A NON può essere rinviato in attesa del corpus perfetto. Dopo i primi casi reali deve essere eseguita una baseline minima:

```text
Methods/caption text
-> few-shot or encoder candidate extraction
-> constrained structured output
-> hard verification
-> human review
-> claim-specific scoring
-> time, decisive-error and residual-error measurement
```

Una review trimestrale deve verificare che Train D non stia assorbendo indefinitamente risorse destinate al deliverable AI finale.

### Regola di release

- v1.0-D può essere rilasciata quando il compilatore deterministico è revisionato, utile a utenti esterni e conforme alla Derivation Theory.
- v1.0-A può essere rilasciata soltanto quando il parser supera real challenge, contamination controls, calibration, burden, end-to-end e false-certainty gate.
- B6 diventa default soltanto se supera B5 o riduce sostanzialmente il carico umano senza aumentare residual error.

![](ntruth_v8_assets/fig2_release_gates_v8.png){width=92%}

*Figura 2 - Engineering readiness, data readiness e scientific validation sono stati indipendenti.*

## 1.5 Tre modalità d'uso

| Modalità | Momento | Valore principale |
|---|---|---|
| Prospective design | Prima del wet-lab | Sample sheet, completezza, prevenzione, execution record e prospective gold |
| Assisted reconstruction | Durante analisi/scrittura | Parser, conferma del grafo, domande, claim-specific report e proof trace |
| Retrospective review | Revisione/meta-ricerca | Ricostruzione prudente, scenario coverage, reporting gap e astensione utile |

La modalità prospettica è il percorso di adozione predefinito; il retrospettivo resta importante ma non deve essere il solo wedge.

## 1.6 Regola di interpretazione del report

Ogni report deve mostrare su assi separati:

1. **cosa è derivabile dal record** (`DeterminabilityState` per claim);
2. **quanto è forte la base evidenziale** (`SupportGrade`);
3. **quali limiti possiede il disegno** (`DesignAdequacyFinding`);
4. **quale parte del profilo e della teoria è coperta** (`ProfileCoverageStatement`).

Un claim `DETERMINATE` non certifica un disegno adeguato. Un disegno pseudoreplicato può essere perfettamente determinabile; un record incompleto non dimostra che il disegno sia sbagliato.

# 2. Problema scientifico e motivazione

## 2.1 Perché il valore di n è difficile da interpretare

Molti esperimenti hanno una gerarchia di provenienza:

```text
donatore -> preparazione -> coltura -> piastra -> pozzetto -> campo -> cellula
```

Le osservazioni ai livelli bassi condividono storia biologica, ambiente, intervento, batch e pipeline analitica. Non sono quindi automaticamente indipendenti. L'unità sperimentale non deriva dalla sola gerarchia: dipende dalla variabile manipolata, dal meccanismo di assegnazione, dal timing rispetto a split/pooling, dall'applicazione realizzata e dalla possibilità che unità candidate ricevano esposizioni differenti.

La definizione NC3Rs dell'unità sperimentale come entità sottoposta indipendentemente all'intervento e il framework entity-intervention di Lazic et al. sostengono questo nucleo [R01-R02]. La v8.0 aggiunge una distinzione necessaria: **l'identità dell'unità sperimentale, il numero di fonti biologiche, la dipendenza analitica e la portata inferenziale non sono lo stesso claim**.

## 2.2 Casistica documentata

Lazic, Clarke-Williams e Munafò hanno riportato, nel campione studiato, il 22% di replicazione corretta della coppia entità-intervento, il 46% di pseudoreplicazione e il 32% di informazione insufficiente [R01]. Questi valori non sono una prevalenza universale, ma dimostrano che:

- falsa replicazione e reporting insufficiente sono problemi distinti;
- l'astensione è scientificamente necessaria;
- un parser non può recuperare fatti che la fonte non contiene;
- il prodotto deve offrire valore anche quando EU o conteggi non sono determinabili;
- un output corretto deve distinguere struttura del disegno, supporto del claim e scope della generalizzazione.

## 2.3 Cinque assi da non collassare

La v8.0 vieta di usare il termine `independent` senza qualificatore.

1. **Assignment separability** - i livelli del fattore potevano essere assegnati separatamente alle unità candidate?
2. **Application/exposure separability** - il trattamento è stato applicato e realizzato separatamente oppure condiviso fra unità?
3. **Biological-source diversity** - le unità derivano da fonti o preparazioni biologiche distinte?
4. **Analytical/measurement dependence** - osservazioni, segmentazioni, timepoint o righe del modello sono correlate?
5. **Inferential scope** - a quale popolazione, protocollo o livello è sostenibile generalizzare?

Tre well della stessa coltura possono essere unità di assegnazione per un trattamento locale, avere una sola fonte biologica, condividere ambiente di piastra, produrre molte misure correlate e sostenere soltanto un'inferenza limitata a quella preparazione. Nessun singolo asse deve essere usato come proxy automatico degli altri.

![](ntruth_v8_assets/fig3_derivation_axes_v8.png){width=96%}

*Figura 3 - Gli assi alimentano claim diversi. Non esiste un unico booleano “independent”.*

## 2.4 Causal, exposure e measurement context

N-Truth NON diventa un causal inference engine. Registra però il contesto necessario per non trasformare una descrizione meccanica in una conclusione causale impropria.

Per ogni `InferentialQuery`, quando pertinente, il record include:

```yaml
assignment_context:
  declared_level: well
  mechanism: random|blocked_random|matched|manual|convenience|unknown
  assignment_event_id: EVT-ASSIGN-01
  separability_state: PRESENT|UNKNOWN|CONFLICTING

application_context:
  application_unit: well
  application_event_id: EVT-APPLY-01
  relative_to_event:
    event_id: EVT-SPLIT-02
    relation: AFTER

exposure_context:
  exposure_pathway: direct_dosing|shared_medium|diffusion|co_culture|unknown
  exposure_container: well|plate|bath|cage|device|unknown
  interference_status: no_known_path|possible|documented|unknown
  interference_cluster: plate_01|unknown

source_context:
  preparation_id: culture_batch_01
  biological_source_state: PRESENT|UNKNOWN|CONFLICTING

measurement_context:
  measured_on: segmented_cell
  algorithm_id: segmentation_model_x
  algorithm_version: 1.2.0
  repeated_measure_unit: field
  correlated_error_structure: possible|documented|unknown

inferential_query:
  factor_id: treatment
  contrast_id: vehicle_vs_drug
  endpoint_id: viability
  timepoint_id: T48H
  effect_measure_or_estimand: mean_difference|unknown
  inference_population: cultures_under_protocol_x|unknown
```

I concetti di estimand sono adottati come disciplina di chiarezza, non come claim di conformità ICH [R37]. `comparability_basis` non autorizza un output `exchangeable=true`.

## 2.5 Conseguenze differenziate dei cinque assi

| Asse | Claim che può modificare | Cosa NON modifica automaticamente |
|---|---|---|
| Assignment separability | assignment unit, experimental unit, design replication count | biological-source count, analytical dependence |
| Application/exposure | exposure unit/cluster, realized experimental unit, estimand support | fonte biologica distinta |
| Biological source | source count, inference scope, source-level generalization | experimental-unit count del fattore, se l'assegnazione è davvero separata |
| Analytical/measurement | analysis handoff, grouping, repeated measures, uncertainty | replicazione sperimentale |
| Inferential query | scope, endpoint/timepoint-specific counts, contrast support | storia fattuale di assegnazione |

L'interference può rendere non identificato o diverso l'effetto di interesse senza cambiare automaticamente l'unità di assegnazione. Quando un'esposizione condivisa impedisce alle unità assegnate di ricevere stati di trattamento distinti, il sistema deve elevare l'unità realizzata, emettere un ramo condizionale o dichiarare l'estimand non supportato.

## 2.6 Tre problemi da non confondere

### A. Replicazione del disegno

Il fattore è applicato a più unità assegnabili separatamente o confuso con una singola piastra, coltura, linea, donatore, batch o giornata? Un modello statistico non crea replicazione che il disegno non possiede.

### B. Dipendenza analitica e di misura

Osservazioni correlate sono trattate come indipendenti? Aggregazione, modelli gerarchici, GEE o errori cluster-robust possono gestire dipendenza analitica in condizioni appropriate, ma non riparano una mancata replicazione del disegno. Errori di segmentazione o misurazione correlati devono essere registrati separatamente.

### C. Portata dell'inferenza

A quale popolazione è sostenibile generalizzare? Tre colture assegnate separatamente ma provenienti da un solo donatore possono sostenere un contrasto all'interno di quel contesto, non automaticamente la variabilità fra donatori.

## 2.7 Interference e shared exposure

La letteratura sull'interference mostra che design, exposure mapping ed estimand devono essere distinti [R35-R36, R39]. In N-Truth sono esempi:

- medium bath condiviso;
- diffusione fra well o insert;
- co-culture e conditioned medium;
- cage/litter effects;
- contaminazione o cross-feeding;
- device o chamber condivisi;
- plate-edge e incubator environment.

L'assenza di reporting non equivale a `no_interference`. Gli stati `possible`, `documented` o `unknown` devono avere conseguenze esplicite sul supporto dell'estimand, sullo scope e sulle domande da porre.

## 2.8 Confine epistemico

N-Truth opera su **record dell'esperimento**. Un Methods, un sample sheet o un chiarimento possono essere accurati, incompleti o errati. Perciò ogni output deve dichiarare:

- se descrive piano, esecuzione o dichiarazione retrospettiva;
- quali fonti sono state osservate;
- quali fatti sono self-report;
- quali assunzioni restano aperte;
- quali deviazioni dall'esecuzione potrebbero non essere registrate;
- la copertura nota del profilo e del Rulebook.

La modalità prospettica riduce questo rischio mediante planned/executed reconciliation, ma non lo elimina.

## 2.9 Problema di prodotto

N-Truth deve offrire:

- formalizzazione rapida prima dell'esperimento;
- sample sheet, ID e Methods draft;
- controllo di completezza;
- domande operative;
- evidenze, support grade e provenance;
- scenari con coverage dichiarata;
- limiti inferenziali e design findings separati;
- export per il biostatistico;
- valore esplicito anche nell'astensione.

# 3. Posizionamento rispetto a DRIVER, ARRIVE, EDA e standard di metadata

## 3.1 DRIVER: riferimento ufficiale, non dipendenza unica

DRIVER - Designing and Reporting In Vitro Experiments Responsibly - è stato lanciato ufficialmente dal NC3Rs il 23 luglio 2026 [R03-R04]. Il crosswalk N-Truth deve registrare URL canonico, data di accesso, versione o snapshot disponibile e content hash del materiale effettivamente mappato.

N-Truth deve usare DRIVER come riferimento principale per il dominio in vitro, ma il proprio schema scientifico NON DEVE dipendere esclusivamente da una singola risorsa. Il nucleo resta fondato su definizioni metodologiche consolidate, tra cui unità sperimentale per fattore, assegnazione indipendente, provenienza, contrasto, estimand, interference, dipendenza e portata inferenziale [R01-R02, R15-R16, R35-R39].

La formulazione corretta è:

> **Companion indipendente, open source e machine-actionable, allineato a concetti scientifici e raccomandazioni internazionali, con un crosswalk versionato verso DRIVER.**

N-Truth non deve presentarsi come:

- prodotto ufficiale NC3Rs;
- certificatore di conformità DRIVER;
- riproduzione integrale della risorsa;
- strumento approvato dagli autori.

Qualsiasi riuso sostanziale di materiale NC3Rs deve rispettare le condizioni ufficiali [R05].

## 3.2 Perimetro DRIVER iniziale

| Area DRIVER | v0.1-v1.0 | Futuro |
|---|---|---|
| Experimental unit | Implementazione centrale tramite Derivation Theory | Multi-fattore e multi-dominio |
| Risk of bias | Metadati minimi e alert selezionati | Modulo dedicato |
| Experimental model | Identità, origine, passaggio e provenance | Suitability e quality attributes |
| Experimental procedures | Sequenza, assignment, application ed exposure | Protocol auditing |
| Groups and exclusions | Gruppi, esclusioni, attrition | Audit completo |
| Data availability and presentation | Export e provenance | Packaging FAIR esteso |

## 3.3 ARRIVE, EDA e tassonomia metodologica

ARRIVE ed EDA forniscono definizioni, esempi e criteri utili, soprattutto per esperimenti in vivo. EDA dimostra che un grafo del disegno può sostenere feedback deterministici e che uno studio può avere più unità sperimentali per fattori differenti [R02, R06, R29]. Hurlbert fornisce una tassonomia storica della pseudoreplicazione che può essere usata come descrizione secondaria, senza sostituire i claim e i finding tipizzati di N-Truth [R16].

N-Truth deve differenziarsi tramite:

- dominio in vitro e imaging;
- parsing automatico multi-documento;
- evidence span localizzati;
- claim specifici per `InferentialQuery`;
- distinzione fra assignment unit, source count, exposure cluster e analytical unit;
- provenance dell'analisi delle immagini;
- export aperto;
- modello AI locale.

## 3.4 REMBI, ISA, OME e interoperabilità

REMBI descrive studio, biosample, specimen, acquisizione, immagine e analisi; il BioImage Archive lo adotta come modello di metadata [R07-R08]. ISA fornisce un modello per Investigation, Study e Assay [R09]. OME/OMERO offre rappresentazioni diffuse per dati e metadata di bioimaging.

N-Truth non deve duplicare questi standard. Deve:

- importare identificatori e provenance da REMBI/ISA/OME quando disponibili;
- aggiungere fattore, assignment, application, exposure, contrasto, estimand, unità sperimentale, evidenza e determinabilità;
- distinguere formato di interscambio da modello interno;
- esportare mapping documentati e testati;
- evitare di dichiarare compatibilità completa senza suite di conformità.

## 3.5 Crosswalk versionato e verificabile

Ogni regola collegata a una raccomandazione deve registrare:

- standard e versione/snapshot;
- URL canonico;
- content hash o release identifier;
- item o sezione;
- tipo di relazione: `implements`, `supports`, `requires_user_judgement`, `out_of_scope`;
- eventuale adattamento;
- data dell'ultima revisione;
- responsabile scientifico.

Il crosswalk serve a mantenere credibilità e aggiornabilità senza trasformare N-Truth in una copia di DRIVER. Una modifica upstream non aggiorna automaticamente il Rulebook: genera una review task.

## 3.6 Crosswalk iniziale bounded

Nel bootstrap il crosswalk copre soltanto concetti direttamente utili al Core:

1. experimental unit;
2. randomisation/allocation;
3. replicates e reporting di n;
4. exclusions/attrition;
5. blinding come metadata di rigor, non derivazione di EU;
6. sample-size justification;
7. biological source e provenance;
8. data availability;
9. image/sample metadata minimi;
10. limiti di inferenza;
11. distinzione fra record completeness e design adequacy.

Il mapping esteso è post-Core. N-Truth non deve diventare un hub universale di standard prima che schema, Derivation Theory, workflow reale e validation protocol siano stabili.

# 4. Visione di prodotto e strategia coordinata

## 4.1 Quattro workstream coordinati

### Workstream A - Fondazione scientifica e Train D

Produce Core Semantic Kernel, Bootstrap Core, Full Scientific Record, wizard, SampleSheetSpec, graph store, Derivation Theory, Rulebook, claim-specific determinability, Theory Reference Set, report e fixture.

### Workstream B - Minimum Viable Train A e parser AI

Produce baseline B0/B4, stage contracts, hard verifier, parser a stadi, componenti addestrati o distillati, calibrazione, astensione, end-to-end scoring ed external validation.

### Workstream C - Real Anchor, silver e synthetic augmentation

Produce real-anchor acquisition, calibration/feasibility corpus, prospective gold, silver auditato, Synthetic Data Factory, anti-shortcut set, reference stability e mixture reports.

### Workstream D - Governance, adozione e sostenibilità

Comprende reviewer, LOI, budget, data custody, STOP authority, primary-persona usability, co-maintainer, funding, challenge custodian e contamination attestation.

## 4.2 Reality-first e theory-first ordering

L'ordine operativo non è “costruire tutti i componenti e poi trovare dati”. È:

```text
Core Semantic Kernel
-> Derivation Theory v0.x
-> 3-5 reality-check cases
-> human disagreement and rule-challenge analysis
-> first-value wizard
-> Minimum Viable Train A
-> 30-50 real calibration cases
-> synthetic/hybrid experiments
-> end-to-end feasibility
-> custodial external challenge
```

Engineering può procedere in parallelo, ma non può promuovere stati scientifici. Il Rulebook non può essere dichiarato validato soltanto perché passa fixture generate dalla propria logica.

## 4.3 Versioni target

| Release | Capacità | Dati/AI | Claim consentito |
|---|---|---|---|
| v0.1-D | Quick Design Session, Kernel, Derivation Theory, rules, fixture | Nessun parser obbligatorio | Alpha deterministica, teoria provisional |
| v0.2-A | Methods/caption, P0 facts, structured output | 10-30 real cases + baseline | Assistente; conferma totale; no semantic qualification |
| v0.5-D | Rulebook, sample sheet e Methods revisionati | Theory Reference Set + Derivation Gold esterno | Compilatore pilotabile nel micro-dominio |
| v0.5-A | Parser a stadi e primi componenti | 30-50 real gold + silver/synthetic auditati | Research preview end-to-end |
| v1.0-D | Compilatore stabile | Utenti e laboratorio esterno | Release supportata, non certificante |
| v1.0-A | Parser validato nel micro-dominio | Learning curve + challenge reale con contamination attestation | AI assistiva human-in-the-loop |
| v2.x | Imaging/Animal/advanced profiles | Corpus, theory extension e challenge dedicati | Espansione post-validazione |

## 4.4 AI Capability Levels

| Livello | Capacità | Stato target |
|---|---|---|
| L0 | Schema, wizard, Derivation Theory e rules-only | v0.1-D |
| L1 | Evidence, entità, counts e fattori espliciti | v0.2-A |
| L2 | Relazioni core, allocation/application candidate, conflitti | v0.5-A |
| L3 | Multi-document merge, decisive coreference, alternative calibrate | v1.0-A |

## 4.5 Train A continuity covenant

Ogni trimestre il progetto registra:

- ore dedicate a Train A e Train D;
- baseline AI effettivamente eseguite;
- blocker dati e theory blockers;
- progresso su real anchor;
- stato del reference standard;
- decisione `PROCEED`, `REVISE`, `LIMIT` o `PAUSE`.

Train D può maturare autonomamente, ma non può essere presentato come completamento della visione AI.

## 4.6 Survival pack a dodici mesi

Anche se Train A non supera ancora i gate, devono esistere:

- Core Semantic Kernel e schema citabili;
- Derivation Theory revisionata;
- Rulebook conforme alla teoria;
- Quick Design Session e sample sheet;
- 30-60 fixture/counterfactual;
- Theory Reference Set e Derivation Gold esterno;
- real-anchor acquisition report;
- Minimum Viable Train A benchmark;
- end-to-end metric contract;
- zero overclaim;
- decisione documentata sul prosieguo.

# 5. Target, personas e bisogni

## 5.1 Primary persona bootstrap

**Dottorando, tesista o ricercatore wet-lab che sta pianificando un esperimento semplice di coltura cellulare.**

Bisogni immediati:

- formalizzare fonte biologica, unità, trattamento ed endpoint;
- generare sample sheet e ID coerenti;
- preparare una bozza Methods;
- identificare 1-3 domande che cambiano il disegno;
- preparare un record leggibile dal biostatistico;
- evitare di confondere molte misure con molte repliche.

## 5.2 Secondary persona bootstrap

**Biostatistico o methodological reviewer.**

Vuole ricevere:

- grafo preliminare;
- evidence span e provenance;
- campi decisivi confermati o UNKNOWN;
- alternative e conflitti;
- domanda inferenziale e conteggi distinti;
- proof trace delle derivazioni.

## 5.3 Personas successive

- core facility di imaging/omica;
- technician/data steward;
- autore, reviewer o editor;
- docente di experimental design;
- meta-researcher;
- sviluppatore ELN/LIMS.

Queste personas non devono guidare la UI bootstrap se aumentano il burden della primary persona.

## 5.4 Anti-personas

N-Truth non è progettato per:

- valutazioni disciplinari automatiche;
- ranking pubblico di paper o laboratori;
- certificazioni legali o regolatorie;
- sostituzione del biostatistico;
- inferenze cliniche;
- uso su dati personali senza governance;
- scoring bulk retrospettivo.

# 6. Flussi di utilizzo e casi d'uso

## 6.1 Quick Design Session - wedge primario

1. L'utente seleziona il template `simple_cell_culture`.
2. Definisce fonte/preparazione, unità, fattore, livelli, endpoint, contrasto e population scope iniziale.
3. Registra assignment, application e timing tramite riferimenti a eventi, oppure `UNKNOWN`.
4. Il sistema evidenzia una domanda primaria decisiva secondo la Derivation Theory.
5. Genera sample sheet, ID convention, Methods draft ed export.
6. Mostra separatamente record completeness e design findings.
7. L'utente può congelare il piano.

Target PROVISIONAL:

- tempo mediano inferiore a 10 minuti;
- massimo tre domande presentate inizialmente, senza limitare il numero di scenari scientificamente necessari;
- nessun obbligo di editare JSON/YAML.

## 6.2 Prospective plan-execution reconciliation

Durante e dopo il wet-lab il sistema conserva separatamente:

- planned design;
- executed design;
- deviations;
- substitutions;
- exclusions;
- pooling;
- lost samples;
- treatment changes;
- final sample sheet;
- instrument or execution logs, quando disponibili.

La riconciliazione produce un diff; non riscrive retroattivamente il piano. Controlli strutturali possono segnalare incoerenze fra dichiarazioni e sample sheet, ma non trasformano automaticamente pattern compatibili in prova del meccanismo di assegnazione.

## 6.3 Assisted reconstruction

1. Import Methods/caption e, se disponibili, sample sheet/metadata.
2. Router identifica Experiment Block secondo criteri versionati.
3. Parser produce evidence, entità, counts e relazioni candidate.
4. Hard verifier preserva output validi e segnala errori.
5. Sistema genera alternative, missing predicates e `ScenarioCoverage`.
6. Utente conferma o corregge predicati decisivi; ogni conferma registra support grade.
7. Rulebook produce `DerivedClaimSet`, proof trace e sensitivity record.
8. Report separa determinabilità, adeguatezza e profile coverage.

## 6.4 Retrospective review e Value of Abstention

Quando un claim non è determinabile, il sistema DEVE restituire:

- fatto decisivo mancante;
- evidence presente e assente;
- scenari plausibili;
- stato di esaustività degli scenari;
- conseguenza di ogni scenario;
- domanda primaria operativa;
- reporting gap;
- proposta di Methods/sample-sheet improvement;
- limite di inferenza;
- profile coverage caveat;
- artefatti ancora utilizzabili.

L'astensione senza questi elementi è un fallimento di prodotto, anche se scientificamente prudente.

## 6.5 Flusso di annotazione

1. Acquisizione autorizzata e hash.
2. Primary annotation dei fatti, non del verdict globale.
3. Freeze immutabile.
4. Second review cieca sui predicati decisivi.
5. Field-by-field disagreement classification.
6. Adjudication quando necessaria.
7. RuleChallenge se il disaccordo riguarda la teoria o il Rulebook.
8. Separazione Parser Gold / Theory Reference Set / Derivation Gold.
9. Eligibility, leakage group e split.
10. Blind re-adjudication audit su un campione dei grafi confermati.

## 6.6 Criteri di Experiment Block

Un `ExperimentBlock` è una porzione di studio con una storia coerente di fonti, assignment, application/exposure, endpoint e query inferenziale. Il sistema DEVE separare blocchi quando almeno una delle seguenti condizioni cambia in modo non rappresentabile con query interne:

- meccanismo o unità di assegnazione;
- popolazione/fonte biologica;
- application/exposure pathway;
- endpoint con pipeline e coorte differenti;
- contrasto o gruppo non condivisibile;
- timeline incompatibile;
- source document che descrive un esperimento distinto.

Non deve separare automaticamente blocchi soltanto perché cambiano figure, paragrafi o file. La segmentazione deve produrre `BlockBoundaryEvidence` e `boundary_confidence` candidate-only.

## 6.7 Casi normativi

- UC01: Quick Design Session semplice.
- UC02: sample sheet e ID.
- UC03: piano vs esecuzione.
- UC04: Methods/caption reconstruction.
- UC05: assignment vs application vs exposure.
- UC06: assertion “independent experiments” senza prova.
- UC07: multiple plausible graphs con coverage non esaustiva.
- UC08: interference/shared exposure.
- UC09: biological source count diverso da experimental-unit count.
- UC10: conflicting source and human clarification.
- UC11: endpoint/timepoint-specific counts senza riscrivere l'unità di assegnazione.
- UC12: self-report-only confirmation con sensitivity record.
- UC13: determinable but inadequate design.
- UC14: rule challenge e re-derivation.
- UC15: cross-domain in vivo profile, solo dopo gate dedicato.

# 7. Definizioni scientifiche vincolanti e Derivation Theory

## 7.1 Unità biologica e fonte biologica

Entità biologica da cui deriva materiale o informazione: donatore, animale, litter, linea cellulare, coltura primaria, clone, organoide, tessuto o altro sistema. Non coincide automaticamente con l'unità sperimentale.

`biological_source_count` è sempre distinto semanticamente da `experimental_unit_count`, anche quando i valori numerici coincidono.

## 7.2 Assignment unit, application unit ed experimental unit

### Assignment unit

La più piccola unità alla quale i livelli di un fattore erano assegnabili separatamente nel piano o nell'esecuzione documentata.

### Application unit

L'unità sulla quale l'intervento è stato materialmente applicato.

### Effective exposure unit/cluster

La più piccola unità o cluster per cui l'esposizione realizzata può essere distinta, tenendo conto di ambiente condiviso e pathway documentati.

### Experimental unit per query

Per la `InferentialQuery` attiva, l'unità sperimentale è l'entità sottoposta all'intervento in modo separabile dalle altre unità rilevanti. Nella situazione standard coincide con l'unità di assegnazione. Se il trattamento è applicato prima dello split o un'esposizione condivisa collassa unità nominalmente assegnate, l'unità realizzata può essere più alta o il claim può rimanere condizionale.

La biological-source diversity e la dipendenza analitica NON cambiano automaticamente l'identità dell'unità sperimentale; modificano altri claim.

## 7.3 Unità osservazionale

Entità sulla quale viene effettuata una misura: cellula, immagine, campo, sezione, well, campione, timepoint o altro oggetto osservato.

## 7.4 Unità analitica

Unità che entra come riga, traiettoria o aggregato nel modello statistico, definita per endpoint e pipeline. Può differire dall'unità osservazionale e dall'unità sperimentale.

## 7.5 Replica biologica

Nuova istanza dell'unità biologica o sperimentale pertinente allo specifico claim. Il termine non deve essere usato senza indicare:

- fattore/contrasto;
- fonte biologica;
- unità di assegnazione;
- scope inferenziale.

“Biologica” non è un'etichetta assoluta.

## 7.6 Replica tecnica e sottocampionamento

Ripetizione della misura o sottocampionamento della stessa unità sperimentale. Migliora precisione o descrive variabilità interna; non aumenta automaticamente le unità assegnate separatamente o le fonti biologiche.

## 7.7 Eventi e timing referenziato

Il campo globale `timing_relative_to_split` è deprecato. Ogni relazione temporale deve riferirsi a eventi specifici:

```yaml
relative_timing:
  subject_event_id: EVT-APPLY-01
  reference_event_id: EVT-SPLIT-02
  relation: BEFORE|AFTER|SAME_EVENT|OVERLAPS|UNKNOWN
  evidence_refs: [EV-12]
```

Questo consente pool-then-split, split-then-pool, replating e protocolli multi-evento.

## 7.8 Contrasto, estimand e InferentialQuery

Ogni conclusione è associata a un oggetto versionato:

```yaml
inferential_query:
  id: IQ-001
  profile_id: simple_cell_culture
  factor_id: treatment
  contrast_id: vehicle_vs_drug
  compared_levels: [vehicle, drug_x]
  endpoint_id: viability
  timepoint_id: T48H
  effect_measure_or_estimand: mean_difference|unknown
  inference_population: cultures_under_protocol_x|unknown
  inference_level: culture|well|unknown
```

L'assegnazione è un fatto del disegno e non viene duplicata arbitrariamente per endpoint. I claim di conteggio, coorte analizzata, determinabilità, estimand support e scope sono invece query-specifici.

## 7.9 Canonical Count Registry

La v8.0 usa un unico registro canonico:

- `declared_n`;
- `planned_unit_count`;
- `allocated_unit_count`;
- `treated_unit_count`;
- `observed_unit_count`;
- `excluded_unit_count`;
- `analyzed_unit_count`;
- `observational_measurement_count`;
- `analytical_row_count`;
- `experimental_unit_count`;
- `biological_source_count`;
- `diagnostic_effective_n`.

`independent_n` resta un alias di presentazione deprecato per `experimental_unit_count` nello scope della query. Ogni count è legato a unit type, factor, contrast, group, endpoint, timepoint, lifecycle cohort, quantifier ed evidence.

I lifecycle counts sono confrontabili soltanto quando condividono unit type, coorte e scope. Il numero di cellule osservate non è confrontabile monotonicamente con il numero di well trattati.

## 7.10 Quantificatori e compatibilità

Valori ammessi:

`EXACT`, `LOWER_BOUND`, `UPPER_BOUND`, `APPROXIMATE`, `RANGE`, `UNKNOWN`, `NOT_REPORTED`.

Il parser non converte un limite in valore esatto né silenzio in zero. La compatibilità fra due count dipende da quantifier e intervallo:

- EXACT 5 è compatibile con APPROXIMATE 5, ma non automaticamente con EXACT 6;
- RANGE 4-6 può essere compatibile con EXACT 5;
- LOWER_BOUND 5 non prova EXACT 5;
- `declared_n` ambiguo non viene forzato a un lifecycle count: genera un ambiguity/conflict record.

## 7.11 Attrition, esclusioni e missingness

Ogni esclusione registra fase, criterio, endpoint, gruppo, evidence basis, actor e impatto. `analyzed_unit_count` è endpoint-specifico. `NOT_REPORTED` non equivale a zero esclusioni.

## 7.12 Dimensioni e claim - tabella normativa

| Dimensione | Predicato principale | Claim diretto | Conseguenza se sconosciuta |
|---|---|---|---|
| Assignment | unità e separabilità dell'assegnazione | assignment unit, EU candidate | EU/n conditional o insufficient |
| Application/exposure | applicazione realizzata, exposure pathway, interference | effective exposure unit, estimand support | exposure/estimand claim conditional; EU può restare noto o no |
| Biological source | source lineage e preparation identity | biological-source count, inference scope | source-level scope unknown/limited |
| Analytical/measurement | grouping, repeated measures, algorithm/pipeline | analytical unit, handoff requirements | analysis advice withheld/partial |
| Inferential query | factor, contrast, endpoint, timepoint, estimand, population | scope di tutti i claim | nessun claim finale fuori query |

## 7.13 Decisive predicate - definizione non circolare

Un predicato `p` è decisivo per un claim `C` sotto la Derivation Theory `T` se esistono due record ammissibili `G1` e `G2`, identici salvo il valore di `p`, tali che `T(G1,Q)` e `T(G2,Q)` producono valori o stati diversi per `C`.

Conseguenze:

- la decisività è claim-specifica;
- la decisività è versionata con la teoria, non definita dal comportamento corrente del codice;
- un Rulebook può implementare male un predicato decisivo; il fatto che cambi output non ne prova la correttezza;
- ogni predicato decisivo deve avere almeno un minimal pair controfattuale nel Theory Reference Set.

## 7.14 Derivation Theory - contratto formale

Per un grafo validato `G`, un profilo `P`, una query `Q` e una versione di teoria `T`, N-Truth definisce:

```text
D_T(G, P, Q) -> DerivedClaimSet
```

Il `DerivedClaimSet` contiene almeno:

- assignment unit;
- application unit;
- effective exposure unit/cluster;
- experimental unit;
- experimental-unit count per gruppo/contrasto;
- biological-source count;
- observational e analytical unit/count;
- interference/estimand support;
- inference scope;
- design adequacy findings;
- record/profile coverage.

La teoria è indipendente dal Rulebook. Ogni regola eseguibile deve riferirsi a una clausola della teoria.

## 7.15 Clausole minime di derivazione

### A. Assignment unit

È derivabile quando esistono factor/levels, assignment event o meccanismo equivalente, candidate unit e separability support. Keyword come “independent” o la presenza di well non sono sufficienti.

### B. Experimental unit

È derivabile quando il trattamento rilevante è assegnato e realizzato in modo separabile alla candidate unit. Se application/exposure collassa la separabilità, il sistema eleva l'unità soltanto con evidence sufficiente; altrimenti emette ramo condizionale o informazione insufficiente.

### C. Experimental-unit count

È il numero di istanze distinte dell'EU nello scope del contrasto e del lifecycle pertinente, per gruppo o paired set. Repeated measures, cellule, campi e analytical rows non lo moltiplicano.

### D. Biological-source count

Deriva esclusivamente dalla provenienza confermata. Non modifica automaticamente il count dell'EU, ma qualifica inference scope e source-level generalization.

### E. Interference/estimand support

- `no_known_path` consente soltanto una formulazione prudente: non prova assenza di interference;
- `possible` o `unknown` richiedono caveat, domanda o sensitivity se il claim dipende dalla no-interference assumption;
- `documented` richiede exposure mapping ed estimand appropriato; in assenza, `estimand_support=UNSUPPORTED_OR_UNSPECIFIED`.

### F. Analytical dependence

Genera grouping/repeated-measure/measurement findings e statistical handoff. Non modifica l'EU o il source count.

### G. Inference scope

Deriva da query, source diversity, protocol, external replication, exposure/interference e profile coverage. Non viene inferita dalla sola numerosità.

## 7.16 Claim-specific determinability

`DeterminabilityState` si applica a ogni `DerivedClaim`. Una dimensione può essere:

- richiesta e risolta;
- richiesta e sconosciuta;
- non pertinente al claim, con `NOT_APPLICABLE_TO_CLAIM` e rationale;
- fuori copertura del profilo.

Il report non deve bloccare un claim che non dipende da una dimensione sconosciuta. Esempio: `experimental_unit_count=3 wells` può essere determinabile mentre `biological_source_count` è 1 e `inference_scope` è limitato.

## 7.17 Record completeness e predicate sufficiency assumption

Ogni claim derivato è condizionato da due assunzioni esplicite:

1. il record osservato rappresenta correttamente piano/esecuzione nello scope dichiarato;
2. il profilo contiene un predicate set sufficiente per il tipo di claim.

Ogni profilo deve pubblicare un `ProfilePredicateClosureArgument`: elenco dei predicati noti come necessari, controesempi considerati, limiti e unknown unknowns. La copertura non è mai presentata come completa oltre il profilo.

## 7.18 Determinabilità e adeguatezza sono assi separati

![](ntruth_v8_assets/fig6_determinability_adequacy_v8.png){width=90%}

*Figura 6 - Un record completo non certifica la qualità del disegno; un record incompleto non dimostra un errore di disegno.*

`DesignAdequacyFinding` comprende almeno:

- replication status;
- hard/possible confounding;
- interference/estimand support;
- biological-source scope;
- analytical dependence;
- reporting adequacy.

Nessun KPI deve trattare la percentuale `DETERMINATE` come successo scientifico.

## 7.19 Non-goal espliciti

Nel Bootstrap Core N-Truth NON valuta automaticamente:

- multiplicity e family-wise error;
- selective endpoint reporting;
- publication bias;
- complete risk-of-bias score;
- causal effect identification generale;
- adeguatezza universale di un modello statistico.

Può raccogliere metadata utili a moduli futuri.

# 8. Modello formale dell'Experiment Graph

## 8.1 Natura del grafo

Il modello è un grafo tipizzato, versionato e profile-aware. Rappresenta annidamento, derivazione, splitting, pooling, pairing, blocking, repeated measures, assignment, application, exposure, gruppi, exclusions, pipeline analitiche, measurement process e provenance.

Il grafo conserva fatti e predicati validati. I claim derivati vivono in oggetti separati e riferiscono il grafo e la query che li hanno generati.

## 8.2 Quattro livelli di rappresentazione

### A. Core Semantic Kernel

Definisce semantica profilo-invariante:

- `KnowledgeState`;
- source/authority/evidence basis;
- `InferentialQuery`;
- unit/event/evidence identity;
- `DerivedClaim`;
- claim-specific `DeterminabilityState`;
- count registry;
- conflict, confirmation, sensitivity e provenance;
- profile/rule coverage.

### B. Bootstrap Core

Usato nel primo pilot e nella Quick Design Session. Richiede:

- `experiment_block_id` e boundary evidence;
- source references ed evidence decisive;
- unit types/instances minime;
- `derived_from`/`nested_in` espliciti;
- factor, levels, endpoint e primary contrast;
- assignment unit required-or-UNKNOWN;
- application/exposure required-or-UNKNOWN quando decisivi;
- assignment separability tri-state;
- source preparation required-or-UNKNOWN;
- key counts e quantifier;
- missing decisive predicate;
- primary minimal question;
- claim-specific determinability derivata e revisionata.

### C. Full Scientific Record

Aggiunge lifecycle counts, exclusions, alternative graphs, conflicts, authority events, analytical pipeline, multiple endpoints, planned/executed diff, measurement context, rule challenges e governance.

### D. Profile extensions

Aggiungono vocabolari e predicati per Imaging, Animal, organoids/iPSC, multifactor, longitudinal e altri domini. Non possono modificare silenziosamente la semantica del Core Kernel.

## 8.3 Minimal Annotation Profile

Il profilo annotativo iniziale non coincide con l'intero schema di scambio. Comprende circa 14-20 elementi, da finalizzare con real cases:

1. Experiment Block e boundary evidence;
2. evidence spans;
3. unit types;
4. core relations;
5. factor;
6. levels;
7. endpoint;
8. primary contrast/query;
9. declared/observed/analyzed counts;
10. assignment unit candidate;
11. application/exposure candidate;
12. event timing;
13. source preparation;
14. biological-source count/state;
15. assignment separability;
16. missing decisive predicate;
17. primary question;
18. authority/evidence basis;
19. rationale/confidence;
20. profile coverage.

EU, counts e determinability sono derivati dal Rulebook conforme alla teoria e revisionati; non sono semplici impressioni dell'annotatore.

## 8.4 Nodi minimi

- `ExperimentBlock`;
- `UnitType` e `UnitInstance`;
- `BiologicalSource` e `Preparation`;
- `Factor`, `FactorLevel`, `Contrast`;
- `InferentialQuery`;
- `Endpoint`;
- `AssignmentEvent`, `ApplicationEvent`, `ExposureEvent`, `SplitEvent`, `PoolEvent`;
- `Observation` e `AnalysisAggregate`;
- `MeasurementProcess`;
- `EvidenceSpan`;
- `CountRecord`;
- `ExclusionRecord`;
- `ConflictRecord`;
- `ConfirmationEvent`;
- `QuestionRecord`;
- `ConditionRecord`;
- `RuleChallenge`;
- `DerivedClaim`;
- `SensitivityRecord`;
- `ProfileCoverageStatement`.

## 8.5 Relazioni minime

Core:

- `derived_from`;
- `nested_in`;
- `contained_in`;
- `allocated_to`;
- `applied_to`;
- `exposed_as`;
- `measured_on`;
- `observed_in`;
- `acquired_from`;
- `aggregated_to`;
- `belongs_to_group`;
- `excluded_from`;
- `supports`;
- `contradicts`.

Estensioni:

- `split_from`, `pooled_from`, `paired_with`, `matched_with`, `blocked_by`, `crossed_with`;
- `same_source_as`, `repeated_measure_of`;
- `shares_exposure_with`, `may_interfere_with`;
- `generated_by`, `computed_from`, `segmented_into`.

`contained_in` descrive contenimento fisico; `derived_from` descrive provenance biologica; non sono sinonimi.

## 8.6 Experiment Block boundary record

```yaml
block_boundary:
  block_id: EB-01
  boundary_basis:
    - distinct_assignment_history
    - distinct_source_population
  source_refs: [METHODS-S2, FIG-3]
  status: CONFIRMED|CANDIDATE|CONFLICTING
  rationale: "Treatment and endpoint belong to a distinct allocation history."
```

Un block split o merge deve essere tracciato. Il router AI propone boundary; il verifier e la review umana le confermano.

## 8.7 Authority, conflict e rule-challenge records

```yaml
confirmation_event:
  id: CONF-001
  authority_type: AUTHOR_CLARIFICATION
  evidence_basis: SELF_REPORT
  support_grade: AUTHOR_CLARIFIED
  actor_id: author_01
  scope: assignment_event
  statement: treatment was assigned after splitting
  source_ref: email_2026_08_03

conflict_record:
  id: CONFLICT-001
  field: biological_source_count
  sources: [methods_ev_12, sample_sheet_rowset_4]
  status: unresolved|resolved_with_rationale
  resolution_event:
    knowledge_state: NOT_APPLICABLE
    rationale: conflict remains unresolved

rule_challenge:
  id: RC-001
  derived_claim_id: CLAIM-EU-01
  challenged_clause: DT-EU-04
  challenger_role: DOMAIN_EXPERT_REVIEW
  rationale: "Shared bath invalidates the current realized-exposure clause."
  status: OPEN|ACCEPTED|REJECTED
```

Un `RuleChallenge` non modifica l'output esistente. Una nuova teoria/ruleset produce re-derivation e migration record.

## 8.8 Graph equality e scoring semantics

Per annotation agreement e benchmark, l'uguaglianza dei grafi non dipende dagli ID locali.

- nodi equivalenti: stesso tipo, ruolo e semantic key nello scope;
- edge equivalenti: stesso tipo, endpoint equivalenti, factor/query scope e attributi decisivi;
- provenance ed evidence span sono valutati separatamente;
- alternative graph sets richiedono matching bipartito e coverage status;
- exact graph match, decisive subgraph match e partial typed match sono metriche distinte;
- un grafo con stessa topologia ma supporto evidenziale diverso non è identico a livello di reference record.

La specifica esatta deve essere congelata prima di IAA e Derivation Gold.

## 8.9 Imaging e advanced profiles

Imaging, multifattore, organoidi/iPSC, split-plot e longitudinali complessi sono stage-gated. Il Measurement Process Context del profilo Imaging registra almeno:

- instrument/acquisition ID;
- algorithm e version;
- segmentation/feature pipeline;
- ROI selection policy;
- repeated-measure unit;
- correlated-error assumptions;
- aggregation path;
- outcome-guided selection risk.

Non entrano nel Bootstrap Core salvo campi minimi necessari alla query.

## 8.10 Declared clustering

Il clustering dichiarato dal codice statistico è silver evidence della struttura analitica, non prova di assignment, source independence o EU.

## 8.11 Profile-invariant vs profile-specific semantics

Il Core Semantic Kernel è stabile fra profili. Ogni profilo deve dichiarare:

- vocabolario aggiunto;
- predicati decisivi aggiunti;
- clausole di Derivation Theory aggiunte o ristrette;
- edge case coperti;
- known gaps;
- migration impact;
- challenge set dedicato.

Un profilo non può ridefinire silenziosamente `KnowledgeState`, `DerivedClaim`, count semantics o authority policy.

# 9. Modello epistemico, dell'evidenza e open-world semantics

## 9.1 Tipi di evidence span

| Tipo | Esempio | Autorità epistemica |
|---|---|---|
| `STRUCTURAL_FACT` | Each culture was split into four wells | Può sostenere archi strutturali nello scope del testo |
| `PROCEDURAL_EVENT` | Drug was added after plating | Ordina eventi, non prova automaticamente separabilità |
| `AUTHOR_ASSERTION` | Three independent biological replicates | Assertion candidate, mai prova conclusiva del meccanismo |
| `SAMPLE_METADATA_PLANNED` | Righe del piano | Evidenza del piano, non dell'esecuzione |
| `SAMPLE_METADATA_EXECUTED` | Final sample sheet congelato | Evidenza strutturata dell'eseguito, con limiti di provenienza |
| `INSTRUMENT_OR_EXECUTION_LOG` | run/plate/time metadata | Supporto diretto dell'esecuzione tecnica |
| `IMAGE_METADATA` | plate/well/site/file | Provenance di acquisizione |
| `STATISTICAL_CODE` | random intercept culture/well | Silver clustering evidence |
| `AUTHOR_CLARIFICATION` | risposta extra-documento | Fatto locale con support grade e conflict policy |
| `USER_CONFIRMATION` | risposta sul proprio esperimento | Autorità locale; può essere self-report only |
| `EXPERT_ADJUDICATION` | decisione con rationale | Reference interpretation nello scope |
| `MODEL_INFERENCE` | relazione proposta | Candidate-only |
| `RULE_DERIVATION` | output della regola | Conseguenza, non fonte |
| `CONFLICTING_EVIDENCE` | fonti incompatibili | Blocca claim pertinenti |

## 9.2 Assertions, confirmations e supporto

`AUTHOR_ASSERTION` nel paper e `AUTHOR_CLARIFICATION` successiva sono oggetti differenti. La seconda può aggiungere informazione, ma non modifica retroattivamente il testo pubblicato; il sistema conserva entrambe.

Ogni conferma decisiva registra:

- authority type;
- evidence basis;
- support grade;
- attachment o evidence ref;
- scope;
- actor;
- independence of review;
- sensitivity effect.

Un click dell'utente non diventa automaticamente equivalente a una conferma corroborata.

## 9.3 Sequenza procedurale

Gli eventi vengono ordinati relativamente mediante ID:

```text
thaw -> expand -> split -> assign -> apply -> acquire -> segment -> aggregate
```

L'ordine delle frasi non è assunto come ordine reale. Relazioni temporali incomplete restano `UNKNOWN`.

## 9.4 Provenance

Ogni nodo, arco, count, confirmation, derived claim e rule output è tracciato a:

- documento/versione;
- coordinate e testo originale;
- planned/executed context;
- metodo di estrazione;
- actor;
- timestamp;
- schema, theory, model e ruleset;
- profile e query;
- support grade;
- migration lineage.

## 9.5 KnowledgeState normativo

Ogni campo scientificamente significativo usa:

| Stato | Significato |
|---|---|
| `PRESENT` | Valore o insieme di valori presente con supporto. |
| `ABSENT_EXPLICIT` | La fonte dichiara esplicitamente assenza nello scope. |
| `NOT_REPORTED` | Le fonti osservate tacciono. |
| `UNKNOWN` | Non determinabile dalle fonti o dalle conferme disponibili. |
| `NOT_APPLICABLE` | Il campo non è pertinente al claim/query, con rationale. |
| `CONFLICTING` | Esistono valori incompatibili non risolti. |

Sono vietati bare `null`, stringhe vuote o liste vuote come semantica scientifica autonoma.

Esempio:

```yaml
confounded_with:
  knowledge_state: NOT_REPORTED
  items: []
  source_scope: [methods_01, sample_sheet_01]
```

Una lista vuota è valida soltanto insieme a uno stato esplicito.

## 9.6 Evidence support levels

- `DIRECT_RECORD` - esplicito in un record eseguito o in una fonte primaria;
- `STRUCTURED_DIRECT` - metadato o cella strutturata con provenance;
- `AUTHOR_ASSERTED` - dichiarato ma non operazionalizzato;
- `INFERRED_CANDIDATE` - proposta del modello/annotatore;
- `SELF_REPORTED_CONFIRMATION` - confermato da soggetto autorevole ma non corroborato;
- `CORROBORATED_CONFIRMATION` - conferma supportata da record indipendente;
- `ADJUDICATED_REFERENCE` - reference gold nello scope;
- `CONFLICTING` - fonti incompatibili;
- `NOT_REPORTED`;
- `UNKNOWN`.

## 9.7 SensitivityRecord

Ogni predicato confermato che modifica un claim decisivo deve produrre, quando computabile:

```yaml
sensitivity_record:
  id: SENS-001
  derived_claim_id: CLAIM-N-01
  decisive_predicate_id: PRED-INDEP-01
  current_support_grade: SELF_REPORT_ONLY
  current_value: true
  counterfactual_value: false
  current_output: {experimental_unit_count: 4}
  counterfactual_output: {experimental_unit_count: 1}
  interpretation: "The reported n depends entirely on this confirmation."
```

Non è richiesta una probabilità soggettiva. È richiesta trasparenza sull'impatto di una conferma fallibile.

## 9.8 Source-to-reality boundary

I report devono contenere una nota standard:

> “These claims are derived from the inspected records and confirmations. N-Truth does not independently observe the executed experiment and cannot recover unrecorded deviations.”

Nel prospettico, il sistema deve distinguere `planned`, `executed`, `reconciled` e `unverified retrospective statement`.

# 10. Motore deterministico e claim-specific determinability

## 10.1 Responsabilità

Il motore riceve esclusivamente un grafo validato, un grafo candidato marcato come tale oppure uno scenario condizionale. Deve:

- applicare il Rulebook del profilo attivo;
- dimostrare la conformità di ogni regola a una clausola della Derivation Theory;
- derivare claim specifici per `InferentialQuery` quando le precondizioni sono soddisfatte;
- calcolare conteggi scope-aware;
- separare record completeness, design replication, dipendenza analitica, portata inferenziale e reporting gap;
- produrre scenari e domande quando mancano predicati decisivi;
- dichiarare se gli scenari sono esaustivi entro il profilo;
- rifiutare grafi invalidi o non supportati;
- generare proof trace, theory clause ID, rule ID, precondizioni, support grade e provenance;
- non inventare informazioni né trasformare assertions in fatti.

## 10.2 DerivedClaim contract

Ogni output scientifico è un `DerivedClaim`:

```yaml
derived_claim:
  claim_id: CLAIM-EU-001
  claim_type: EXPERIMENTAL_UNIT
  inferential_query_id: IQ-001
  value:
    unit_type: well
  determinability_state: DETERMINATE
  support_grade: DIRECT_SINGLE_SOURCE
  required_predicates:
    - assignment_unit
    - assignment_separability
    - realized_exposure_separability
  irrelevant_predicates:
    - id: biological_source_independence
      rationale: "Not required to identify the treatment EU; used for inference scope."
  assumptions:
    - record_complete_for_claim
  sensitivity_records: [SENS-001]
  theory_version: derivation-theory-0.1.0
  theory_clauses: [DT-EU-01, DT-EU-04]
  rule_trace: [EU-ALLOC-001]
  profile_coverage: COVERED_WITH_KNOWN_GAPS
```

## 10.3 DeterminabilityState claim-specifico

| Stato | Precondizione | Output ammesso | Output vietato |
|---|---|---|---|
| `DETERMINATE` | Tutti i predicati richiesti per quel claim risolti o formalmente non applicabili | valore, proof, support, sensitivity | interpretazione oltre scope |
| `CONDITIONALLY_DETERMINATE` | Predicati finiti mancanti con rami scientificamente definiti | branch outputs, condition, question | valore unico senza condizione |
| `MULTIPLE_PLAUSIBLE_GRAPHS` | >=2 grafi compatibili | alternative, consequences, coverage | forced choice |
| `INSUFFICIENT_INFORMATION` | Predicato decisivo assente e non inferibile | explicit KnowledgeState, gap, question | guess |
| `CONFLICTING_INFORMATION` | Fonti pertinenti incompatibili | ConflictRecord, retained interpretations | automatic override |
| `INVALID_GRAPH` | Invarianti violate | errori e required patch | scientific claim |
| `OUT_OF_SCOPE` | Topologia o claim non coperto | structural summary, known gaps | verdict/release claim |

Una query può contenere contemporaneamente claim con stati differenti.

## 10.4 ReportResolutionState

Il report aggrega i claim senza perdere granularità:

- `COMPLETE_FOR_REQUESTED_CLAIMS`;
- `PARTIAL_WITH_ACTIONABLE_GAPS`;
- `MULTI_SCENARIO`;
- `CONFLICTED`;
- `INVALID`;
- `OUT_OF_SCOPE`.

Il report summary non sostituisce gli stati dei singoli claim.

## 10.5 Design adequacy separata

Il motore produce finding tipizzati, non un unico giudizio:

- `DESIGN_REPLICATION_SUPPORTED|LIMITED|ABSENT|UNKNOWN`;
- `HARD_CONFOUNDING_DOCUMENTED|POSSIBLE|NOT_IDENTIFIED|UNKNOWN`;
- `INTERFERENCE_DOCUMENTED|POSSIBLE|NO_KNOWN_PATH|UNKNOWN`;
- `SOURCE_SCOPE_SINGLE|MULTIPLE|UNKNOWN`;
- `ANALYTICAL_DEPENDENCE_CLUSTERED|REPEATED|SIMPLE|UNKNOWN`;
- `REPORTING_COMPLETE_FOR_CLAIM|INCOMPLETE|CONFLICTING`.

`DETERMINATE` non è una classe di adeguatezza e non usa visual encoding verde.

## 10.6 Output condizionale leggibile

```json
{
  "claim_type": "EXPERIMENTAL_UNIT_COUNT",
  "determinability_state": "CONDITIONALLY_DETERMINATE",
  "scenario_coverage": "EXHAUSTIVE_WITHIN_PROFILE",
  "branches": [
    {
      "condition": "Cultures were initiated as separable preparations before treatment assignment.",
      "output": {"control": 4, "drug": 4}
    },
    {
      "condition": "Cultures share one preparation or treatment was assigned before separation.",
      "output": {"control": 1, "drug": 1}
    }
  ],
  "primary_question": "Were the cultures separable preparations before treatment assignment?",
  "theory_clause": "DT-EU-04"
}
```

Le condizioni devono essere comprensibili a un biologo; un flag booleano generico non è sufficiente.

## 10.7 ScenarioCoverage

Ogni scenario set registra:

```yaml
scenario_coverage:
  status: EXHAUSTIVE_WITHIN_PROFILE|NON_EXHAUSTIVE|UNKNOWN
  profile_id: simple_cell_culture
  theory_version: derivation-theory-0.1.0
  emitting_clauses: [DT-EU-04, DT-EXP-02]
  omitted_dimensions:
    knowledge_state: ABSENT_EXPLICIT
    items: []
  caveat:
    knowledge_state: NOT_APPLICABLE
```

Il limite UX alle domande si applica all'ordine di presentazione, non alla generazione o conservazione degli scenari. Un set non esaustivo non può essere presentato come spazio completo delle possibilità.

## 10.8 Famiglie di regole iniziali

- unità per fattore e query;
- separabilità dell'assegnazione;
- timing event-referenced;
- application/exposure collapse;
- lifecycle counts e attrition;
- stessa preparazione distribuita in più well;
- batch/plate/day confounding;
- repeated measures semplici;
- pooling e splitting canonici;
- observational vs analytical vs experimental unit;
- source scope e inference scope;
- reporting gap e conflitti;
- count invariants;
- scenario coverage e rule coverage.

Le regole avanzate devono essere aggiunte soltanto con theory clause, fixture, casi reali e revisione esterna.

## 10.9 Theory Reference Set, Derivation Gold e conformance

La validazione è divisa in tre asset:

1. **Theory Reference Set** - casi e counterfactual expert-reviewed che verificano la Derivation Theory senza usare l'output del Rulebook come riferimento;
2. **Implementation Conformance Fixtures** - test che verificano che il Rulebook implementi ogni theory clause;
3. **Derivation Gold** - grafi reali confermati con claim attesi, support grade, design findings e rationale.

Un primo set deve comprendere:

- 30-60 fixture canoniche e falsification fixtures;
- 20-30 casi reali con grafo confermato;
- almeno tre casi reali e un counterfactual per ogni clausola critica, oppure una dichiarazione esplicita di riuso e coverage;
- casi che tentano di falsificare la predicate closure del profilo.

## 10.10 Coverage del theory/ruleset

Devono essere misurati separatamente:

- theory clause coverage;
- implementation conformance;
- profile predicate coverage;
- real-case graph coverage;
- report-level claim coverage;
- `OUT_OF_SCOPE` e known gaps;
- errori del motore a grafo corretto;
- nuovi pattern richiesti.

La percentuale `DETERMINATE` è descrittiva, non un KPI di successo.

## 10.11 Validazione e release blocker

Ogni regola deve avere theory clause, precondizioni, output, eccezioni, fixture positiva/negativa/counterfactual, riferimento, reviewer, data e changelog. Una release è bloccata se:

- una clausola critica non ha reviewer esterno;
- il motore emette count fuori dagli stati consentiti;
- count invariants non sono verificate;
- un bare null/lista vuota produce assenza certa;
- ICC o effective sample size modificano una classe di design replication;
- AUTHOR_ASSERTION chiude la determinabilità;
- self-report decisivo non è qualificato e non ha sensitivity;
- scenario non esaustivo è presentato come completo;
- una formula statistica viene presentata come unica soluzione universale;
- DesignAdequacy e Determinability sono fusi.

## 10.12 ConditionRecord e domanda primaria

Ogni output condizionale deve contenere:

```yaml
condition_record:
  id: COND-001
  predicate: independent_preparations_before_assignment
  claim_ids: [CLAIM-EU-01, CLAIM-N-01]
  human_readable:
    it: "Le colture erano preparazioni separabili prima dell'assegnazione?"
    en: "Were cultures separable preparations before assignment?"
  evidence_required: [preparation_id, assignment_event_id]
  if_true_effect: "EU=culture; count by group"
  if_false_effect: "EU collapses to shared preparation or remains unknown"
  scenario_coverage: EXHAUSTIVE_WITHIN_PROFILE
  primary_question_id: Q-001
```

Una domanda primaria è obbligatoria. Le domande secondarie possono essere conservate oltre il friction budget e mostrate progressivamente.

## 10.13 Interaction con human authority

Il rules engine usa il grafo nello stato corrente e registra authority/evidence basis di ogni precondizione. Una decisione umana che risolve il caso deve essere inclusa nel proof trace con support grade. Un conflitto irrisolto blocca soltanto i claim che dipendono dal conflitto.

Un esperto non può patchare direttamente un claim derivato: usa `RuleChallenge` e re-derivation.

# 11. Supporto statistico: capacità, guardrail e limiti

## 11.1 Statistical handoff come capacità di default

Dal grafo confermato N-Truth può produrre un handoff strutturato:

- unità di assignment/application/exposure dichiarate;
- experimental unit e counts derivati quando consentiti;
- livelli di clustering da considerare;
- repeated-measure unit;
- possibili grouping factors;
- endpoint/cohort/lifecycle counts;
- numero di cluster e bilanciamento;
- hard confounding o pochi cluster;
- measurement process e aggregation path;
- dati mancanti necessari alla consulenza statistica.

L'handoff non è una prescrizione automatica del modello statistico.

## 11.2 Strategy module - stato iniziale HANDOFF_ONLY

Nel Bootstrap Core il sistema NON raccomanda famiglie di analisi come output normativo. Può mostrare requisiti e domande per il biostatistico.

Una futura capacità `CANDIDATE_STRATEGY_FAMILIES` richiede:

- Strategy Reference Set indipendente;
- mapping design-pattern -> famiglie ammissibili e vietate;
- exclusion list per pochi cluster, separazione quasi nulla, endpoint incompatibili o estimand non definito;
- external statistical review;
- metriche di errore e abstention;
- output sempre candidate, mai unica soluzione.

## 11.3 Cosa non può scegliere automaticamente in modo universale

La scelta dipende da:

- distribuzione e scala dell'endpoint;
- link function;
- random slopes;
- struttura temporale;
- eteroschedasticità;
- obiettivo marginale o condizionale;
- numero, bilanciamento e trattamento dei cluster;
- missingness;
- measurement error;
- assunzioni e design specifico.

## 11.4 Divieto di statistical washing

ICC, design effect, effective sample size, mixed models, GEE o cluster-robust errors NON possono:

- creare replicazione sperimentale inesistente;
- cambiare un finding di mancata design replication in classe non problematica;
- ridurre automaticamente la severity di hard confounding o single-batch design;
- sostituire un'unità di randomizzazione mancante;
- trasformare più misure tecniche in fonti biologiche indipendenti.

## 11.5 Pochi cluster e abstention floor

Metodi cluster-robust e bootstrap possono essere inaffidabili con pochi cluster o pochi cluster trattati [R42, R47]. Perciò:

- nessuna soglia universale viene hard-coded senza protocollo specifico;
- il sistema registra numero di cluster, distribuzione per braccio e bilanciamento;
- sotto il guardrail validato per il metodo considerato, strategia ed `effective_n` vengono `WITHHELD_INSUFFICIENT_CLUSTER_SUPPORT`;
- un caveat non sostituisce l'abstention.

## 11.6 ICC, design effect ed effective sample size

Un modulo opzionale può stimare tali quantità soltanto quando:

- sono disponibili dati numerici autorizzati;
- il numero e la struttura dei cluster supportano la procedura;
- endpoint e grouping sono definiti;
- assunzioni e incertezza sono riportate;
- la strategy validation è disponibile.

`diagnostic_effective_n` appare in una sezione diagnostica separata da `experimental_unit_count`.

## 11.7 Attrition e analisi per endpoint

Il sistema mostra almeno:

```text
planned -> allocated -> treated -> observed -> excluded -> analysed
```

per coorte, unit type, gruppo ed endpoint. Non ricostruisce retroattivamente la numerosità pianificata da quella analizzata né interpreta un'esclusione post-outcome come semplice perdita tecnica.

# 12. Ruolo centrale e architettura del modello AI

## 12.1 Perché l'AI resta fondamentale

Il rules engine non rende il prodotto scalabile. L'AI deve ridurre il costo di localizzare fatti, riconciliare ID, estrarre counts, ricostruire eventi, collegare artefatti, proporre alternative e precompilare il grafo.

L'AI è centrale nella visione; la sua adozione come default è evidence-based.

## 12.2 AI Capability Ladder

### P0 - release-gating

- routing Methods/caption;
- evidence typing;
- entità, counts e quantificatori;
- factor, levels, endpoint;
- relazioni esplicite `nested_in`/`derived_from`;
- assignment/application esplicite come candidate;
- provenance e conflict detection di base.

### P1 - assistenza avanzata

- decisive coreference;
- procedural order;
- multi-artifact merge;
- repeated measures;
- alternative graphs e coverage candidate;
- question templates;
- imaging core.

### P2 - research frontier

- estimand implicito;
- multifattore/split-plot;
- free-form question generation;
- OOD e multi-graph calibration;
- nuovi domini.

## 12.3 Minimum Viable Train A

La prima prova AI non richiede la pipeline completa:

1. Methods/caption text;
2. B0 rules e B4 LLM/encoder candidate;
3. stage-level schema vincolato;
4. hard verifier;
5. human review con support grade;
6. claim-specific e report-level metrics;
7. tempo e residual-error audit.

Soltanto se questa baseline riduce burden o chiarisce failure modes si aggiungono router avanzato, normalizer, procedural event extractor, coreference module e semantic verifier model-based.

## 12.4 Pipeline a stadi target

1. routing/segmentazione;
2. Experiment Block boundary candidate;
3. evidence extraction;
4. entity/count normalization;
5. factor/endpoint/query;
6. procedural events;
7. core relations;
8. candidate graph assembly;
9. hard validation;
10. semantic verification mirata;
11. human review;
12. Rulebook e DerivedClaimSet.

Ogni stage produce artefatti versionati e partial success.

## 12.5 Baseline ladder

- B0: regex/dizionari/table parser;
- B1: encoder NER/classifier;
- B2: relation/coreference baseline;
- B3: pipeline modulare;
- B4: LLM locale few-shot con schema vincolato;
- B5: cascata ibrida + verifier;
- B6: modello N-Truth fine-tuned/distilled.

B6 è default solo se batte B5 sui predicati decisivi, calibration, false certainty, residual error, burden e budget.

## 12.6 Alternative architetturali e benchmark A-E

Confrontare almeno:

- A - encoder specializzati + piccolo LM di sintesi + verifier;
- B - piccolo LM monolitico con chunking;
- C - encoder multi-task;
- D - modello N-Truth fine-tuned/distillato;
- E - challenger più grande quantizzato e caricato sequenzialmente.

Nessun backbone, size, framework o quantizzazione è prescrizione scientifica prima del benchmark.

## 12.7 Structured decoding

Grammar/JSON validity attesta soltanto forma. Il modello produce candidate facts; non emette `experimental_unit_count`, design finding, `RuleResult` o `DeterminabilityState` finale.

Ogni decoding profile ha qualificazione runtime propria e non eredita automaticamente quella del modello base.

## 12.8 Verifier progressivo

Nel bootstrap il verifier semantico può essere:

- rule-based cross-check;
- sample-sheet consistency;
- metadata validation;
- open-world semantics check;
- human decisive review.

Un secondo modello viene attivato soltanto se dimostra valore sui campi ad alto impatto e rientra nel resource budget.

## 12.9 Synthetic Task Use Matrix

Il ruolo del synthetic è task-specifico:

- synthetic-heavy per routing, entità, counts e relazioni esplicite;
- hybrid per assignment/application esplicite, eventi e conflitti controllati;
- real-heavy per coreference decisiva, assignment implicito, source interpretation e subtle conflicts;
- real-only per final evaluation e release claims.

## 12.10 Divieto di predizione diretta

Target primari vietati al parser:

```text
n = 4
paper valid
pseudoreplication = true
determinability = DETERMINATE
design adequate = true
```

Il modello emette evidence, candidate facts, alternatives, confidence, coverage e missing predicates.

## 12.11 Pretraining contamination risk

Ogni backbone deve registrare:

- model/version;
- training-data disclosure disponibile;
- cutoff dichiarato o sconosciuto;
- public benchmark exposure risk;
- known fine-tuning datasets;
- contamination tests eseguiti e limiti.

Un paper “unseen by the project” non è automaticamente unseen dal backbone. Le prestazioni su public OA challenge devono essere riportate con contamination-risk caveat [R43-R46].

# 13. Contratto del parser AI e del verifier

## 13.1 Input stage-gated

| Fase | Input |
|---|---|
| v0.1-D | wizard, TXT/Markdown, CSV semplice |
| v0.2-A | Methods/caption testuali |
| v0.5-A | più blocchi, CSV e codice read-only |
| post-v0.5 | JATS/XML, XLSX, DOCX, PDF testuale |
| estensioni | OME/OMERO/REMBI, immagini/layout multimodale |

## 13.2 Stage contracts

- `DocumentRouteResult`;
- `ExperimentBlockCandidateSet`;
- `EvidenceExtractionResult`;
- `EntityCountResult`;
- `FactorEndpointQueryResult`;
- `ProceduralEventResult`;
- `CandidateRelationSet`;
- `CandidateGraphSet`;
- `VerifierResult`;
- `HumanRevisionPatch`;
- `ConfirmationEvent`;
- `DerivedClaimSet`;
- `QuestionRecord`;
- `ReportBundle`.

Ogni oggetto include schema version, provenance, errors, warnings, coverage e `complete|partial|failed`.

## 13.3 Candidate-only output

Il parser restituisce Experiment Block candidate, evidence, nodes/edges candidate, factors, counts, assignment/application/exposure candidate, source state candidate, events, alternatives, missing facts, confidence e coverage. Non include il verdict del Rulebook.

## 13.4 Validation stack

![](ntruth_v8_assets/fig4_validation_stack_v8.png){width=82%}

*Figura 4 - La validità sintattica è il primo livello. Il prodotto viene validato anche end-to-end e dopo la revisione umana.*

Prima della proposta all'utente:

1. syntax/JSON;
2. schema validation;
3. KnowledgeState/open-world validation;
4. referential integrity e type constraints;
5. graph topology/cardinality e block boundaries;
6. temporal consistency;
7. count/scope invariants;
8. evidence support e scenario coverage;
9. conflict/authority/support policy;
10. human review dei predicati decisivi;
11. rule conformance e DerivedClaimSet validation;
12. blind residual audit su campione.

## 13.5 Question bank

Le domande sono template legati a missing predicate. Ogni domanda dichiara:

- predicato mancante;
- claim modificati;
- scenari;
- scenario coverage;
- output che cambierebbe;
- destinatario;
- evidence richiesta;
- priorità primaria/secondaria;
- support grade atteso.

Free-form question generation è P2.

## 13.6 Partial success ed error taxonomy

Errori minimi:

- `UNSUPPORTED_FORMAT`;
- `CHUNK_COVERAGE_INCOMPLETE`;
- `MISSING_REQUIRED_EVIDENCE`;
- `AMBIGUOUS_COREFERENCE`;
- `CONFLICTING_SOURCES`;
- `INVALID_COUNT_INVARIANT`;
- `AMBIGUOUS_NULL_SEMANTICS`;
- `NON_EXHAUSTIVE_SCENARIO_SET`;
- `UNSUPPORTED_DESIGN_PROFILE`;
- `VERIFIER_DISAGREEMENT`;
- `AUTHORITY_CONFLICT`;
- `INTERFERENCE_STATUS_UNKNOWN`;
- `RULE_THEORY_MISMATCH`;
- `PROFILE_COVERAGE_GAP`;
- `REALITY_GATE_BLOCKED`.

Artefatti validi precedenti sono conservati.

## 13.7 No semantic repair by normalization

Il normalizer può canonicalizzare forma, non inventare fatti. Sono vietati:

- stringa libera -> evidence/fact;
- `null` -> absence;
- keyword “independent” -> assignment separability;
- well ID -> experimental unit;
- random-intercept code -> allocation;
- rule output usato per correggere retroattivamente il parser target.

# 14. Strategia dati complessiva

## 14.1 Sette classi di dataset

| Dataset | Ruolo | Sostituisce real gold? |
|---|---|---|
| Theory/Falsification Fixtures | Test della teoria e controfattuali | No |
| Implementation Conformance Fixtures | Test del Rulebook | No |
| Derivation Gold | Grafo confermato -> claim attesi | Sì per il motore, nello scope |
| Parser Gold | Artefatti reali -> evidence/grafo | Sì per il parser |
| Silver auditato | SourceData, PreClinIE, CRAFT, MeasEval, metadata | No |
| Synthetic augmentation | Volume, rare cases, perturbazioni | No |
| External Challenge | Real-only, custodito, contamination-attested | Solo valutazione |

## 14.2 Real Anchor Acquisition Programme

![](ntruth_v8_assets/fig5_real_anchor_v8.png){width=90%}

*Figura 5 - Canali distinti producono dati con autorità, rischio e usi differenti.*

### A. Prospective laboratory cases

Piano, sample sheet, esecuzione, deviazioni e conferma post-esperimento. Fonte preferita per assignment, application e source lineage.

### B. Expert consensus su letteratura open access

Paper CC0/CC BY, evidence span, doppia review sui predicati decisivi e adjudication. Il source text resta una descrizione, non osservazione diretta dell'esecuzione.

### C. Core facility cases

Metadata e provenance reali; gold soltanto dopo consenso, de-identificazione e review.

### D. Teaching-derived candidates

Restano candidate data finché non sono autorizzati e revisionati da esperti.

### E. Author-confirmed retrospective cases

Chiarimenti con provenance e support grade. Utili ma lenti e non scalabili.

### F. Cross-domain expert datasets

Il ruolo è deciso prima dell'accesso completo ai label.

## 14.3 Prospective Gold

Distinguere planned, executed, deviations, substitutions, exclusions, pooling, lost samples, treatment changes, final sample sheet e source log. Il diff è immutabile e auditabile.

## 14.4 Cross-domain data role

Il ruolo è profile-relative:

- un dataset expert-adjudicated in vivo può essere gold per Animal Profile;
- è auxiliary o schema-alignment per il profilo in vitro;
- non può validare v1.0-A in vitro;
- può sostenere concetti generali, theory counterfactual, stress test e future expansion;
- train/test role viene concordato prima di ispezionare tutti i label.

Per il dataset Lazic sono possibili: schema-alignment subset, calibration subset, held-out in vivo challenge o future Animal Profile. Nessun ruolo viene assunto a priori.

## 14.5 Target progressivi e unità indipendenti

| Stadio | Casi reali indicativi | Funzione |
|---|---:|---|
| Reality check | 3-5 | Stressare protocollo/schema |
| Schema bootstrap | 10-20 | Verificare micro-dominio |
| Calibration pilot | 30-50 | Reference stability, tempi, determinability |
| Feasibility | 100-150 | Baseline, learning curve, dev/test |
| Expansion | 150-500 | Fine-tuning e validation |
| Research corpus | 800-2.000 | Programma finanziato |

I numeri non sono soglie magiche. Ogni gate deve considerare il numero di laboratori, articoli, study families e altre unità indipendenti di generalizzazione.

## 14.6 Doppia annotazione stratificata

- 100% doppia sui predicati decisivi;
- 100% doppia su test e nuovi profili;
- campione full-double sul training;
- adjudication su disaccordi critici;
- blind re-adjudication su un campione dei grafi confermati;
- resto primary + audit.

## 14.7 Split anti-leakage e lineage

Devono restare nello stesso leakage group:

- article, supplement, preprint e dataset;
- versioni/translation/paraphrase dello stesso testo;
- `study_family_id` e document lineage;
- lab/facility e corresponding-author group quando rilevanti;
- synthetic family e counterfactual family.

Journal, venue o anno non sono leakage group sufficienti o necessari da soli. Generator e teacher non accedono al test.

## 14.8 External Challenge e pretraining contamination

Ogni item del challenge registra:

- source provenance;
- publication date;
- prospective/private/public status;
- backbone cutoff disclosure;
- known web availability;
- contamination risk `LOW|MEDIUM|HIGH|UNKNOWN`;
- exposure test eseguito e limite;
- permitted model families.

Preferenza:

1. prospective/private/custodial cases;
2. post-cutoff cases quando il cutoff è noto;
3. public OA cases con contamination caveat.

Nessun test prova definitivamente assenza di pretraining exposure; il rischio residuo deve essere riportato [R43-R46].

## 14.9 Synthetic preconditions

SYN-G0/G1 può essere creato prima del real baseline per fixture, smoke e engineering pre-adaptation non promuovibile. Nessun lotto diventa training-approved o sostiene claim finché:

- esiste real development congelato;
- real-only baseline è eseguita;
- hybrid comparison è disponibile;
- shortcut e calibration non peggiorano;
- audit umano è completato;
- test e external challenge restano inaccessibili al generator.

# 15. Synthetic Data Factory e revisione dei facsimile manuali

## 15.1 Principio di autorità del dato

Le dodici tavole allegate rappresentano molto bene come un annotatore, un reviewer o un data curator dovrebbe vedere un caso. Non sono però, da sole, esempi utilizzabili per addestrare il parser.


Regole vincolanti:

- i file sorgente sono immutabili e identificati da hash;
- evidence span, grafi, conteggi, alternative, conflitti e gold vivono nel record canonico;
- la tavola è generata dal record, non annotata manualmente come unica fonte;
- ogni tavola deve riportare `record_hash` e `render_hash`;
- se una tavola è errata, si corregge il record e si rigenera la tavola;
- un'immagine non può essere promossa a gold tramite OCR;
- il parser testuale non deve apprendere da testo rasterizzato quando è disponibile il testo originale.

## 15.2 Struttura minima di un training bundle reale o sintetico

```text
bundle/
  manifest.json
  sources/
    methods.txt | methods.pdf
    caption.txt
    article.xml
    samples.csv | samples.xlsx
    analysis.R
    metadata.json
  annotations/
    evidence.jsonl
    candidate_graph.json
    adjudicated_graph.json
    alternative_graphs.json
    counts_by_scope.json
    contradictions.json
    annotation_submissions.jsonl
    adjudication.json
    eligibility_gates.json
  renders/
    tavola_annotazione.png
    render_manifest.json
```

Il record deve distinguere almeno:

- candidate facts e adjudicated facts;
- `author_assertion` e `structural_fact`;
- `declared_n`, `allocated_n`, `analyzed_n`, `observational_n`, `experimental_unit_count`;
- `biological_source_count` e `experimental_unit_count`;
- factor, contrast, endpoint e timepoint a cui ogni conteggio si riferisce;
- allocation, application, measurement e aggregation level;
- determinability, alternative graphs e minimal question;
- split, leakage group, license state, training eligibility ed evaluation eligibility.

## 15.3 Synthetic Data Factory: ruolo e architettura

La Synthetic Data Factory è un **amplificatore del pool di training**, non una scorciatoia per evitare la realtà. Il flusso è graph-first:

1. Design DSL versionato;
2. coverage planner per casi canonici e rare cases;
3. graph sampler biologicamente vincolato;
4. deterministic label compiler;
5. observation model che decide cosa è visibile, omesso o conflittuale;
6. renderer per Methods, caption, sample sheet, XML, metadata e codice;
7. perturbation engine per coreference, inconsistenze e rumore controllato;
8. hard validators e round-trip;
9. dedup, family split e contamination scan;
10. audit umano stratificato;
11. registry con seed, teacher, prompt family e hash.

La factory deve produrre almeno tre gradi:

| Grade | Requisiti | Uso |
|---|---|---|
| `SYN-G0` | grafo e label compiler validi | test del motore e training strutturale |
| `SYN-G1` | testo supera hard validation e round-trip | training candidato |
| `SYN-G2` | campione o famiglia revisionata da umano | training-approved per task critici |

Per ogni ciclo, almeno 50 realizzazioni stratificate devono essere valutate come plausibili, troppo semplici, realisticamente ambigue, artificialmente ambigue, implausibili o incoerenti.

I dati sintetici sono particolarmente adatti a:

- entità e conteggi;
- quantificatori;
- relazioni esplicite;
- counterfactual;
- errori tabellari;
- rare graph topologies;
- stress test degli invarianti.

Richiedono forte real-data anchoring per:

- allocation implicita;
- decisive coreference;
- indipendenza biologica;
- contraddizioni sottili;
- estimand e inference target;
- valutazione finale.

La quantità non è un KPI autonomo. Un lotto viene mantenuto soltanto se migliora il development reale o riduce il tempo di revisione senza peggiorare calibrazione e shortcut sensitivity.

## 15.4 Curriculum synthetic-to-real e mixture search

Stadi consigliati:

1. template espliciti e single-source;
2. variazioni linguistiche controllate;
3. counterfactual minimal pairs;
4. bundle multi-documento con omissioni;
5. conflitti e decisive coreference;
6. adattamento sul gold reale;
7. deliberate practice guidata dagli errori reali.

Devono essere confrontate almeno le condizioni:

- real-only;
- synthetic-only;
- silver+real;
- synthetic+real;
- hybrid completa.

La miscela viene scelta sul development reale. Non si fissa a priori una percentuale del 50%, 70% o altra quota. I risultati devono includere TSTR, hybrid uplift, calibration, decisive-edge F1, errori per classe e human-review time.

Parafrasi, mutazioni e tavole dello stesso grafo condividono `family_id` e split. Il corpus mantiene un real-data anchor e vieta self-training ricorsivo non auditato, in linea con i rischi di model collapse [R26]. Cycle consistency è un quality signal, non una prova autonoma di fedeltà [R23].

## 15.5 Valutazione generale delle dodici tavole

Le tavole sono **visivamente eccellenti** e coprono quasi tutti i problemi operativi rilevanti: Methods, gerarchie, figure, conteggi, sample sheet, codice, XML, experiment block, grafi alternativi, conflitti, doppia annotazione e training record.

Giudizio complessivo:

- molto valide come annotation guideline, materiale di onboarding e specifica UI;
- molto utili come blueprint per generare record sintetici;
- non utilizzabili come gold image-only;
- alcune scientificamente corrette con revisioni minori;
- alcune richiedono correzioni sostanziali prima del training;
- Tavola 12 contiene un blocking error di governance;
- Tavole 9 e 10 mostrano la necessità di separare indipendenza sperimentale e numero di fonti biologiche.




## 15.6 Matrice di idoneità

| Tavola | Valutazione | Uso raccomandato | Correzione principale |
|---|---|---|---|
| 01 Methods annotati | Revision required | evidence-to-graph fixture | application level non provato; `n` deve essere scope-aware |
| 02 Gerarchia e conteggi | Accept with revisions | repeated-measures/count fixture | TIME non ha application level; usare repeated-measure unit |
| 03 Figura e caption | Major revision | ambiguity/caption fixture | il conteggio di 150 cellule non è supportato dalla caption |
| 04 Tabella conteggi | Accept with revisions | count derivation fixture | ogni `n` deve avere factor/contrast/endpoint scope |
| 05 Sample sheet | Strong, minor fixes | sample-sheet QA fixture | separare contenimento fisico e provenance biologica |
| 06 Codice statistico | Strong, minor fixes | silver-evidence fixture | confidence dimostrativa; parsing preciso di `(1|donor/culture)` |
| 07 JATS/XML | Strong with revisions | stand-off/XML fixture | EV-X02 è semanticamente collegato in modo scorretto |
| 08 Paper multiblocco | Major revision | experiment-block negative fixture | allocation sovrainferita; stretch a field level non provato |
| 09 Grafi alternativi | Major scientific revision | alternative-graph fixture | donor count e experimental-unit count sono confusi |
| 10 Evidenze in conflitto | Revision required | conflict fixture | stessi donor wells non implicano automaticamente repliche tecniche |
| 11 Doppia annotazione | Strong, minor fixes | adjudication workflow fixture | IAA è corpus-level; manca rationale completa |
| 12 Training record | Blocking error | governance fixture dopo fix | `split=TEST` non può avere `training_eligible=true` |

## 15.7 Correzioni scientifiche vincolanti per Tavole 01-04

### Tavola 01

- `allocation_level=CULTURE` è supportato.
- `application_level=WELL` è solo candidato finché una fonte non afferma che il composto è stato fisicamente applicato dopo lo splitting.
- `experimental_unit_count` per la query di trattamento è `6 donor-linked cultures/group`; non deve essere rinominato semplicemente `6 donors/group` senza dichiarare la relazione 1:1.
- “nessuna esclusione” deve diventare `EXCLUSIONS_NOT_REPORTED`, salvo dichiarazione esplicita.

### Tavola 02

- per GENOTYPE, `experimental_unit_count=12 donors/group` è plausibile come confronto osservazionale;
- per DRUG, `experimental_unit_count=6 cultures/group/genotype` è coerente se le colture sono allocate indipendentemente;
- per TIME, non esiste `application_level`: usare `repeated_measure_unit=culture` e `measurement_schedule_level=culture_trajectory`;
- `analyzed_n` deve distinguere righe del modello, traiettorie e unità indipendenti.

### Tavola 03

- endpoint, entity measured on e donor aggregation sono ben rappresentati;
- il conteggio `150 cells` non è derivabile dalla caption mostrata, poiché mancano numero di wells e cellule per field;
- la ripetizione degli stessi donor IDs nei gruppi suggerisce anche uno scenario paired da rappresentare;
- il claim `experimental_unit_count` deve restare `UNKNOWN` finché provenance e pairing non sono risolti.

### Tavola 04

- l'aritmetica è corretta per il disegno mostrato;
- i conteggi devono essere legati a `scope_id`, factor, contrast, endpoint e timepoint;
- Mean, SD e SEM sono indicazioni di reporting, non esempi osservazionali né target del parser.

## 15.8 Correzioni vincolanti per Tavole 05-08

### Tavola 05

- distinguere `well contained_in plate` da `sample_in_well derived_from culture`;
- sostituire `image measured_on well` con `image acquired_from field/well`;
- missing donor IDs, duplicate filename, license pending e `training_eligible=false` sono corretti;
- un record in quarantena non riceve split definitivo.

### Tavola 06

- il codice è silver evidence e non deve mai essere eseguito;
- `(1|donor/culture)` deve essere espanso semanticamente in grouping donor e donor:culture;
- endpoint, factor, declared clustering e candidate contrast sono fatti candidati validi;
- randomizzazione, assignment, biological-source independence ed `experimental_unit_count` non sono provati dal codice;
- confidence numeriche devono essere marcate `mock` oppure provenire da calibrazione reale.

### Tavola 07

- il modello stand-off e la sicurezza XML sono eccellenti;
- la cella “41 anni” non supporta la frase “donor-derived cultures”: deve collegarsi al donor entity o alla donor row;
- il peer-review sub-article va escluso dalle primary facts, ma può essere conservato come source class `REVIEW_COMMENT`;
- offset e line number devono essere generati automaticamente sul testo canonico normalizzato.

### Tavola 08

- è corretto vietare una label unica per l'intero paper;
- EB-01 ed EB-02 non provano l'allocation al well soltanto perché dichiarano replicati o una piastra;
- in EB-03 lo stretch meccanico è normalmente applicato a chamber, membrane, well o device, non al campo visivo; field-level application richiede prova esplicita di stimolazione locale;
- questi blocchi devono restare `INDETERMINATE` finché provenance e allocation non sono documentati.

## 15.9 Correzioni vincolanti per Tavole 09-12

### Tavola 09

La tavola coglie correttamente il principio “non indovinare”, ma il valore di `n` è scientificamente troppo semplificato.

Tre culture provenienti da un donatore possono essere:

- tre unità sperimentali di trattamento, se avviate e allocate indipendentemente;
- tre sottocampioni tecnici, se derivano dalla stessa preparazione e non sono allocate indipendentemente;
- tre culture con `n_experimental_units=3` ma `biological_source_count=1`, quindi inferenza limitata a un donatore.

Il record deve contenere separatamente:

- `experimental_unit_count`;
- `biological_source_count`;
- `inference_target`;
- `independent_preparation_status`.

La domanda minima deve quindi verificare sia l'origine da donatori distinti sia l'indipendenza delle preparazioni.

### Tavola 10

Il conflitto va conservato, ma “tre wells dallo stesso donor” non prova che siano repliche tecniche. Senza fattore e allocation, i wells potrebbero essere unità sperimentali al livello well con portata inferenziale limitata. La formulazione neutra è:

- author assertion: tre repliche biologiche indipendenti;
- metadata fact: W01-W03 condividono donor D1;
- allocation: unknown;
- experimental unit: `KnowledgeState=UNKNOWN`;
- minimal questions: livello di assegnazione del trattamento e modalità di preparazione di W01-W03.

### Tavola 11

- workflow append-only, doppia revisione, adjudication e gate sono corretti;
- IAA non si calcola su un singolo record: i valori mostrati devono essere etichettati “illustrative only”;
- reviewer confidence può essere raccolta, ma non sostituisce agreement e rationale;
- il gold deve includere adjudication rationale e differenze rispetto alle due submission.

### Tavola 12

Errore bloccante:

```text
split = TEST
training_eligible = true
```

Le due condizioni sono incompatibili. Correzioni ammesse:

- mantenere `split=TEST`, impostare `training_eligible=false` ed `evaluation_eligible=true`; oppure
- assegnare `split=TRAIN` dopo i gate e mantenere `training_eligible=true`.

Inoltre il supervised record deve contenere un oggetto `GoldParserTarget` distinto da `ParserAIOutput`: il primo è il target adjudicato, il secondo è l'output candidato del modello.

## 15.10 Schema scope-aware dei conteggi

Ogni count record deve essere almeno:

```yaml
count_id: CNT-001
kind: experimental_unit_count
value: 6
unit_type: culture
factor_id: treatment
contrast_id: vehicle_vs_drug
endpoint_id: mitochondrial_length
timepoint_id: T1
population_scope: donor_linked_primary_cultures
condition: confirmed_independent_cultures
source_evidence: [EV-01, EV-02, EV-03]
rule_trace: [EU-ALLOC-001, COUNT-004]
```

Sono vietati count globali senza scope quando il bundle contiene più fattori, endpoint o timepoint.

## 15.11 Gate di training ed evaluation

Il record deve usare stati distinti:

```yaml
split: UNASSIGNED | TRAIN | VALIDATION | TEST | EXTERNAL_CHALLENGE
training_eligible: false
evaluation_eligible: false
release_eligible: false
```

Invarianti:

- TEST ed EXTERNAL_CHALLENGE implicano `training_eligible=false`;
- record senza licenza verificata o provenance completa restano non idonei;
- record con conflitto irrisolto può essere usato per contradiction detection soltanto se il target è adjudicato come conflitto;
- una tavola non determina l'idoneità: visualizza i gate del record;
- IAA è una metrica di corpus, non un gate per singolo item;
- ogni item correlato condivide leakage group e split family.

## 15.12 Quality gate record-to-facsimile

Ogni rendering deve superare:

- tutti i valori visualizzati corrispondono al record hash;
- nessun valore gold è aggiunto manualmente nella grafica;
- colori e label seguono una legenda versionata;
- placeholder hash e timestamp sono esplicitamente marcati;
- formule aritmetiche sono ricalcolate dal record;
- stati null/unknown/not-reported non vengono convertiti in assenza certa;
- candidate e gold non condividono la stessa visual encoding;
- il render conserva `source_record_id`, `record_hash`, `render_version`, `render_hash`;
- un test automatico confronta testo estratto dalla tavola con i campi attesi, ma l'OCR non diventa sorgente di verità.

## 15.13 Uso delle tavole nel programma AI

Uso consentito:

- annotation guideline;
- formazione e calibrazione degli annotatori;
- UI/UX specification;
- test di completezza del record;
- documentazione pubblica;
- future evaluation multimodale separata;
- generazione di domande e report da un grafo confermato.

Uso vietato:

- OCR delle tavole come sostituto delle annotazioni strutturate;
- uso di testo inventato nelle tavole come external validation;
- miscelazione di tavole correlate tra train e test;
- attribuzione gold a valori presenti soltanto nella grafica;
- conservazione di contraddizioni grafiche senza blocking flag;
- addestramento del parser primario sui PNG quando il testo originale è disponibile.

## 15.14 Release gate dei facsimile

Una tavola entra nella documentazione ufficiale solo se:

1. record canonico validato;
2. revisione scientifica conclusa;
3. nessun blocking error;
4. render generato automaticamente;
5. record/render hash registrati;
6. dati e immagini chiaramente identificati come reali, sintetici o illustrativi;
7. numeri scope-aware;
8. training/evaluation gate coerenti;
9. reviewer approva leggibilità e assenza di overclaim.


## 15.15 Invarianti del record e test controfattuali

Il CI blocca almeno:

- TEST/EXTERNAL con `training_eligible=true`;
- record in più split;
- leakage group distribuito;
- confusione tra source count ed EU count;
- fusione di inference scope e allocation validity;
- claim determinability chiusa dalla sola AUTHOR_ASSERTION;
- synthetic presentato come real gold;
- count senza factor/contrast/endpoint scope;
- human clarification che cancella un conflitto senza ConflictRecord;
- `no_interference` dedotto dal silenzio.

## 15.16 Realism calibration da testo reale non etichettato

Testo reale autorizzato può stimare prior aggregati di lunghezza, lessico, abbreviazioni, posizione dei counts, alias/coreference, layout e missingness. Non produce target scientifici e non autorizza copia verbatim nel renderer.

## 15.17 Training approval rule

Un lotto sintetico viene mantenuto solo se migliora almeno una metrica sul real development o riduce il tempo di revisione senza peggiorare false certainty, calibration e shortcut sensitivity. Synthetic-only performance non è sufficiente.

## 15.18 Vincoli v8 su synthetic, scenario e semantica

La factory v8 deve generare separatamente:

- graph truth;
- observable record;
- KnowledgeState per ogni campo;
- candidate parser target;
- theory reference claims;
- scenario coverage;
- support grade simulato, chiaramente marcato synthetic;
- known profile gaps.

Un esempio sintetico non può dichiarare `exhaustive=true` se il sampler non possiede una dimostrazione di chiusura dello spazio definito dal profilo. Il renderer non può convertire `UNKNOWN`, `NOT_REPORTED` o `NOT_APPLICABLE` in assenza certa.

Gli errori reali osservati nel residual audit possono guidare deliberate practice, ma il test finale resta inaccessibile. La factory non crea nuove clausole di Derivation Theory: può soltanto istanziare e stressare clausole approvate.

# 16. Fonti pubbliche, baseline e condizioni d'uso

## 16.1 PMC Open Access Subset

PMC offre accesso mediante servizi ufficiali, inclusi Cloud Service, FTP, OAI-PMH, OA API, E-Utilities e BioC [R10-R11]. Per il percorso automatico iniziale N-Truth deve ammettere soltanto CC0 e CC BY verificate. Altre licenze richiedono revisione specifica.

Il manifest deve registrare PMCID, DOI, licenza, data, versione, URL di acquisizione e checksum. PMC fornisce testo e struttura, non il gold sull'unità sperimentale.

## 16.2 SourceData-NLP

SourceData-NLP integra curation nel processo editoriale e comprende oltre 620.000 annotazioni di bioentità curate da 18.689 figure in 3.223 articoli di biologia molecolare e cellulare. Include ruoli come entità controllata e oggetto misurato, oltre a modelli PubMedBERT e BioLinkBERT rilasciati come baseline [R12, R17].

Uso previsto:

- NER e normalizzazione;
- riconoscimento di assay;
- ruoli di intervento e misura;
- caption parsing;
- pretraining o multi-task auxiliary.

Non contiene allocation level, grafo completo o `n` indipendente.

## 16.3 PreClinIE

PreClinIE è un corpus open, manualmente annotato, composto da abstract e Methods di 725 pubblicazioni precliniche, con indicatori di rigore come random allocation e caratteristiche dello studio [R18]. È utile per baseline di information extraction e per testare indicatori di design, ma riguarda soprattutto studi animali e non risolve il target in vitro di N-Truth.

## 16.4 CRAFT e coreference

CRAFT offre full text biomedici con annotazioni semantiche, sintattiche e di coreference [R13, R19]. Può sostenere baseline di coreference e analisi full-text. Non annota allocation level, estimando o `n` indipendente.

## 16.5 REMBI, BioImage Archive, OME e OMERO

Queste risorse possono fornire strutture reali per biosample, specimen, acquisizione, analisi e file. Sono centrali per l'Imaging Profile e per allineare paper, campioni, immagini e metadata [R07-R08]. Licenza e possibilità di training devono essere verificate submission per submission.

## 16.6 ISA, BioStudies e SDRF

ISA-Tab/ISA-JSON e SDRF rappresentano source, sample, process e assay. Sono fonti preziose per la provenienza, ma non sempre esplicitano randomizzazione, allocazione o estimando.

## 16.7 Dataset Lazic e dati cross-domain

Il dataset pubblico associato a *What exactly is N* e ogni ulteriore materiale condiviso da Stan Lazic devono essere trattati separatamente per licenza, granularità e ruolo. Prima di accedere a tutti i label, N-Truth registra:

- dominio e unità di annotazione;
- source text disponibile;
- evidence/rationale;
- licenza e usi;
- leakage grouping;
- subset per schema alignment;
- eventuale held-out set.

Dati in vivo expert-adjudicated possono essere gold per un futuro Animal Profile, ma non sono gold diretto o external challenge per la release in vitro. Possono sostenere design concepts, rule fixtures, cross-domain stress test e future validation specifica.

## 16.8 Cell Painting e high-content screening

Può essere usato per parsing tabellare, plate mapping e scalabilità. Deve restare ausiliario: strutture standardizzate potrebbero insegnare la scorciatoia `well = experimental unit` al di fuori dei contesti in cui è vera.

## 16.9 Fonti escluse per default

- articoli senza licenza leggibile;
- scraping non autorizzato;
- dati clinici identificabili;
- tesi o protocolli interni senza consenso;
- dataset con termini incompatibili;
- output AI presentati come gold senza revisione;
- metadata privi di provenienza o versione.

## 16.10 Stato operativo e license scope

L'acquisizione tecnica, la trasformazione e l'idoneità al training sono stati distinti. Ogni dataset usa stati separati:

- `acquisition_status`;
- `processing_status`;
- `license_scope_status`;
- `training_readiness`;
- `evaluation_readiness`;
- `data_tier`.

La presenza di un file LICENSE nel repository upstream non prova automaticamente che la licenza copra codice, annotazioni e testo sorgente. Il License Manifest deve distinguere tali asset.

Al 6 agosto 2026, lo snapshot implementativo non normativo considera SourceData e PreClinIE auxiliary acquisiti, CRAFT auxiliary acquisito e MeasEval non training-ready per overlap/decisioni di licenza. Questi stati non costituiscono real anchor e devono essere verificati nel registry corrente prima di ogni uso.

## 16.11 Backbone exposure e corpus pubblici

Un corpus pubblico può essere utile per training auxiliary e al contempo essere inadatto come unico external challenge perché il backbone può averlo incontrato in pretraining. L'uso di paper pubblici in development deve registrare document lineage e contamination risk; il final challenge preferisce casi prospettici, custoditi o post-cutoff.

# 17. N-Truth Experiment Graph Corpus, unit economics e unità di generalizzazione

## 17.1 Asset scientifico

Il corpus pubblicabile documenta evidence, graph, alternative, authority, decision, DerivedClaim e provenance. `Parser Gold`, `Theory Reference Set` e `Derivation Gold` restano distinti:

- **Parser Gold**: artefatti reali -> evidence/fatti/grafo di riferimento;
- **Theory Reference Set**: casi e controfattuali scelti per falsificare le clausole della Derivation Theory;
- **Derivation Gold**: grafo confermato + query -> claim derivati di riferimento;
- **External Challenge**: casi reali custoditi, non accessibili al training o alla progettazione delle regole.

Un item può appartenere a più asset logici soltanto con split, leakage group, uso e provenance espliciti. Lo stesso item NON può essere contemporaneamente development e test finale.

## 17.2 Complexity tiers

Le stime di tempo non sono fissate a priori. Ogni bundle è classificato:

| Tier | Caratteristiche | Esempi |
|---|---|---|
| `SIMPLE` | single source, esplicito, una query primaria | Methods breve + conteggi chiari |
| `MODERATE` | multi-section, missingness limitata, una o due alternative | Methods + caption + sample sheet |
| `COMPLEX` | conflitti, multi-source, pairing/pooling/timeline implicita | paper + sheet + code + clarification |
| `OUT_OF_PROFILE` | topologia o claim non coperti | multifattore avanzato, organoid complex |

Il tier descrive il burden previsto, non la qualità del disegno.

## 17.3 Tempi da misurare

- triage/licenza;
- Experiment Block segmentation;
- evidence spans;
- units/relations/events;
- decisive predicates;
- Full Graph;
- second review;
- adjudication;
- Theory/Rule challenge;
- curation e freeze;
- synthetic audit;
- blind residual re-adjudication.

I primi casi devono produrre distribuzioni empiriche median/p90, non un singolo valore medio.

## 17.4 Schema Burden Gate

Dopo ogni tranche si misurano:

- median/p90 minutes per tier;
- campi `UNKNOWN`, `NOT_REPORTED` e `NOT_APPLICABLE`;
- free-text dependency;
- disagreement e adjudication burden;
- value per field;
- sensitivity frequency;
- claim coverage;
- residual error dopo revisione.

Se un campo è costoso, instabile e non cambia claim né reporting utile, viene spostato dal Bootstrap Core al Full Scientific Record o al profilo dedicato.

## 17.5 Unità indipendenti per la valutazione

Il numero di casi non coincide con il numero di fonti indipendenti di generalizzazione. Ogni protocollo di valutazione registra almeno:

- `case_count`;
- `study_family_count`;
- `article_count`;
- `laboratory_or_facility_count`;
- `biological_domain_count`;
- `annotator_pair_count`;
- distribuzione dei casi per fonte.

Gli intervalli di confidenza e i confronti tra sistemi devono usare la struttura gerarchica pertinente. Il cluster di resampling può essere paper, study family, laboratorio o facility a seconda del claim; non esiste un cluster universale valido per tutte le metriche.

## 17.6 Precision planning

Prima di ogni gate scientifico viene preregistrato:

- parametro o metrica primaria;
- unità di generalizzazione;
- errore critico;
- precisione desiderata o CI half-width;
- prevalence attesa e sua incertezza;
- correlazione intra-cluster plausibile;
- perdita prevista per astensione/OOD;
- analisi di sensibilità a numeri di cluster diversi.

Una numerosità espressa soltanto in “casi” non è sufficiente per autorizzare un claim cross-lab.

## 17.7 Scenari di carico e budget

Le person-hours sono planning assumptions e vanno sostituite con dati. Collaboration in-kind sostiene il bootstrap, non la scala. Il budget deve separare:

- real annotation;
- second review;
- adjudication;
- theory/rule review;
- data stewardship;
- external custodial evaluation;
- engineering e model evaluation.

## 17.8 Benchmark pubblico

Quando licenze e consenso lo permettono, pubblicare casi con split congelato, guideline, reference stability, baseline, decisive labels, profile coverage e contamination note. Generator, prompt development, rule authors e model selection non accedono al test.

# 18. Annotazione, adjudication e reference stability

## 18.1 Ruoli

- wet-lab annotator/reviewer;
- statistical-methods reviewer;
- adjudicator;
- Derivation Theory reviewer;
- data curator;
- ML/data engineer;
- external STOP reviewer.

Il founder non può essere unico autore di teoria/regole, annotatore, adjudicator e release owner.

## 18.2 Reality-check pilot

Prima del calibration corpus:

- dry-run sintetici/manuali separati dai casi reali;
- almeno 1-3 fonti reali/pubbliche;
- primary freeze;
- second review cieca;
- disagreement taxonomy;
- schema e theory feedback;
- nessuna eligibility per train/test;
- verifica di `KnowledgeState`, count registry e claim-specific determinability.

## 18.3 Calibration pilot - 30-50 casi

Obiettivi:

- stabilizzare Bootstrap Core e Core Semantic Kernel;
- misurare tempi per tier/campo;
- agreement sui decisive predicates;
- prevalence e claim-state distribution;
- reference stability;
- interazione biology-statistics;
- prior per synthetic observation model;
- decisione di learnability e burden.

Il numero di casi è una banda operativa, non una garanzia di precisione. Deve essere accompagnato dal numero di paper, study family e laboratori/facility.

## 18.4 Feasibility - 100-150 casi

Protocollo e guideline congelati, split protetti, external adjudication, B0-B5, anti-shortcut, real/synthetic/hybrid, theory/rules coverage e unit economics. L'Appendice D usa la stessa banda 100-150; eventuali ampliamenti sono una fase successiva e non una definizione concorrente.

## 18.5 Agreement e graph equality

Specificare:

- metrica e categorie;
- prevalence;
- trattamento di `UNKNOWN`, `NOT_REPORTED`, `NOT_APPLICABLE` e `CONFLICTING`;
- sufficient evidence;
- node/edge matching ID-free;
- decisive-subgraph agreement;
- alternative-set agreement;
- evidence-span agreement;
- biology-statistics agreement.

IAA è corpus-level. Un valore elevato misura coerenza secondo il protocollo, non prova automaticamente correttezza del reference standard.

## 18.6 Reference stability

Il concetto di “reference stability” viene sostituito da **reference stability**, composta da:

1. inter-annotator agreement pre-adjudication;
2. stabilità dell'adjudicator su un campione riannotato a distanza;
3. disaccordo fra wet-lab e statistical-methods reviewer;
4. sensitivity del reference a informazioni aggiuntive;
5. blind residual re-adjudication dei grafi confermati;
6. documented gold-noise budget.

Il modello non viene presentato come “vicino all'umano” senza descrivere queste componenti.

## 18.7 Determinability derivata

Gli annotatori marcano fatti, evidence, alternative, support grade e missing predicates. Ogni `DerivedClaim` e il relativo `DeterminabilityState` vengono prodotti dalla teoria/ruleset e revisionati; non sono scelti liberamente dall'annotatore.

L'annotatore può contestare un claim tramite `RuleChallenge`, ma non patchare direttamente un output derivato.

## 18.8 Confirmation protocol

Ogni conferma decisiva registra:

- actor/role;
- scope;
- evidence basis;
- support grade;
- attachment o rationale;
- indipendenza della review;
- eventuale corroborazione;
- sensitivity effect.

Le conferme self-report possono rendere un claim determinabile, ma il report deve mostrarne il support grade e la sensibilità. Determinabilità non equivale a alta affidabilità.

## 18.9 Standing residual audit

Dopo HITL, un campione stratificato di grafi/claim confermati viene rivalutato in cieco da un reviewer non coinvolto. Si misura:

- residual decisive-error rate;
- residual false-certainty rate;
- errori per support grade;
- errori per tier, laboratorio e source class;
- errori introdotti dalla review umana;
- errori del Rulebook a grafo corretto.

Il residual audit è release-gating per v1.0-A.

## 18.10 Redirect e kill criteria

Soglie finali sono preregistrate dopo il pilot. Regole di gestione:

- agreement o reference stability bassi -> ridurre Core, chiarire teoria o limitare parser a elicitation;
- residual false certainty elevata -> STOP claim/release;
- B6 non supera B5 -> non default;
- synthetic peggiora real dev/calibration -> ridurre o sospendere;
- majority insufficient/out-of-profile -> rafforzare prospective/teaching e restringere retrospective claims;
- theory/rules coverage insufficiente -> ampliare clausole o restringere profilo;
- assenza di reviewer/LOI/budget -> non aprire feasibility o training sostanziale.

Valori numerici restano PROVISIONAL finché non preregistrati con metrica, unità di generalizzazione e costo degli errori.

## 18.11 Active learning e pre-annotation

Entrano dopo guideline, theory e baseline stabili. Confidence automatica non promuove a gold. Gli item selezionati dall'active learning non entrano nel test e condividono il leakage group della famiglia originaria.

# 19. Collaborazione con professori, ricercatori e laboratori

## 19.1 Scopo prioritario

Collaborazioni per regole, real anchor, prospective gold, decisive review, external challenge, usability e funding.

## 19.2 Canali del Real Anchor Programme

### Laboratori partner

Uno o pochi esperimenti semplici, sample sheet, piano/eseguito e chiarimenti.

### Core facility

Metadata e standardizzazione; richiede custodia e consent.

### Teaching/workshop

Teaching-derived candidates, non gold automatico.

### Expert literature annotation

Paper OA con evidence e adjudication.

### Author clarification

Domande minime a basso carico; fonte lenta e non scalabile.

### Cross-domain experts

Dataset e rule review per profili futuri, incluso Animal Profile.

## 19.3 Richiesta iniziale minima

- 5-10 casi o 20-30 minuti;
- review di decisive fields;
- commento al SampleSheetSpec;
- uno o pochi casi de-identificati;
- introduzione a biostatistico/facility;
- descrizione di codebook/licenza prima di ricevere tutti i label.

## 19.4 Resource Gate

Prima della feasibility:

- wet-lab reviewer stabile;
- biostatistico con ore concordate;
- co-maintainer o PI host;
- lab/facility partner;
- data custodian;
- budget/in-kind register.

## 19.5 Autorità di STOP

Può bloccare per IAA insufficiente, leakage, ruleset, benchmark, overclaim, dati senza consenso, risorse o synthetic dependence.

## 19.6 Governance dati

Uso locale, stand-off, de-identification, aggregate statistics, synthetic calibration e custodial external set sono consentiti solo secondo permessi espliciti.
## 19.7 Ruolo specifico dei collaboratori v8

- wet-lab reviewer: fatti di esecuzione, provenance e plausibilità biologica;
- biostatistico/metodologo: Derivation Theory, Strategy Reference Set e precision planning;
- annotator/adjudicator: reference stability e rationale;
- data custodian: External Challenge e contamination attestation;
- author/lab contributor: chiarimenti locali con support grade, non modifica diretta della teoria;
- external STOP reviewer: false certainty, theory gaps e overclaim.

Una singola persona può coprire più ruoli nel bootstrap, ma i conflitti devono essere dichiarati e la release AI richiede separazione sufficiente.

# 20. Architettura software

## 20.1 Architettura logica target

```text
apps/
  cli/
  wizard/
packages/
  schemas/
  graph/
  evidence/
  authority/
  derivation_theory/
  rules/
  verifier/
  prospective/
  reports/
  ingest/
  parser_ai/
  model_backends/
  annotation/
  data/
  synthetic/
  evaluation/
  governance/
  runtime_resources/
```

Questa è un'architettura **logica target**, non un claim che ogni directory esista già. `graph` e `derivation_theory/rules` NON importano `parser_ai`.

## 20.2 Current-to-target architecture map

Il repository DEVE mantenere un file versionato, per esempio `docs/architecture/current-to-target-map.yaml`, contenente:

- modulo logico;
- package/path corrente;
- stato `IMPLEMENTED|PARTIAL|TARGET_ONLY|SUPERSEDED`;
- API pubblica;
- owner;
- migration issue/ADR;
- clean-checkout evidence.

La documentazione non deve usare nomi target come se fossero package implementati. Ogni snapshot implementativo resta separato dal PRD normativo.

## 20.3 Separazione Theory / Rulebook / Output

- `derivation_theory`: specifica versionata delle clausole e del predicate closure;
- `rules`: implementazione eseguibile delle clausole;
- `verifier`: invarianti e conformance;
- `reports`: serializzazione dei `DerivedClaim` senza ricalcolo scientifico;
- `RuleChallenge`: input governance per una nuova versione, mai patch runtime del claim.

Il Rulebook deve dichiarare la versione di teoria implementata. Il conformance harness deve verificare clause coverage e non soltanto fixture pass.

## 20.4 Persistenza

SQLite locale, content-addressed blob store, manifest bundle, JSON/YAML exchange, corpora/modelli fuori Git. PostgreSQL solo collaborativo; graph DB dopo benchmark.

Persistenza obbligatoria per:

- source hashes;
- graph versions;
- authority/conflict events;
- derived claims;
- theory/rules versions;
- sensitivities;
- profile coverage;
- migration lineage.

## 20.5 SampleSheetSpec minimo

`sample_id`, source/provenance state, preparation/culture/plate/well, factor applicability e level, batch, timepoint, endpoint, lifecycle status, exclusion reason e file ref.

Nessuna indipendenza viene dedotta dal solo ID. Planned e executed sheet sono classi distinte.

## 20.6 Runtime contracts

CLI, `ExperimentGraph`, `InferentialQuery`, `ParserStageResult`, `VerifierResult`, `HumanRevisionPatch`, `DerivedClaimSet`, `RuleResult`, `QuestionRecord`, `ReportBundle`, `ProfileCoverageStatement`, errors e migrations.

## 20.7 Runtime Resource Manager

I componenti AI vengono eseguiti sequenzialmente per default. Ogni stage dichiara lifecycle `load -> warmup -> run -> release`, backend, context cap, cache e fallback. Profili `LOW_MEMORY`, `BALANCED` e `QUALITY` sono configurazioni operative, non claim di accuratezza.

Monitorare memory, swap, latency, tokens, cache e fallback per bundle senza loggare contenuto scientifico. Ogni modifica di model, quantization, context, task profile o decoding invalida la relativa qualifica finché non viene ripetuto il benchmark.

## 20.8 Ingestione e sicurezza

Sandbox senza rete, MIME allowlist, macro bloccate, size/file limits, nessuna esecuzione di codice importato, redaction pre-export, no silent cloud.

## 20.9 UI iniziale

Wizard, tabelle, albero, evidence panel, claim panel, authority/support badges, scenario coverage, summary e proof trace. Canvas libero solo dopo usability evidence.

# 21. Requisiti funzionali

## 21.1 Fondazione deterministica [D0]

- **FR-001**: creare Experiment Block tramite Quick Design Session;
- **FR-002**: rappresentare Bootstrap Core e `KnowledgeState`;
- **FR-003**: validare invarianti strutturali, epistemici e count-specifici;
- **FR-004**: applicare Derivation Theory e Rulebook versionati;
- **FR-005**: produrre `DerivedClaim` claim-specifici;
- **FR-006**: emettere EU/count solo negli stati consentiti;
- **FR-007**: produrre output condizionale e `ScenarioCoverage`;
- **FR-008**: generare sample sheet e ID;
- **FR-009**: generare design/Methods statement;
- **FR-010**: JSON/YAML, proof trace e audit trail;
- **FR-011**: key counts e lifecycle esteso;
- **FR-012**: planned/executed reconciliation;
- **FR-013**: `ProfileCoverageStatement` per ogni report;
- **FR-014**: support grade e sensitivity per i claim decisivi;
- **FR-015**: `RuleChallenge` senza output patching.

## 21.2 Causal/exposure/measurement context [D0/A1]

- **FR-020**: registrare assignment event, mechanism e timing referenziato;
- **FR-021**: distinguere assignment, application, exposure, biological source, analytical e measurement dependence;
- **FR-022**: rappresentare interference pathway, exposure cluster e shared environment;
- **FR-023**: registrare comparability basis senza dedurre exchangeability;
- **FR-024**: associare ogni claim a `InferentialQuery`;
- **FR-025**: rappresentare measurement process nei profili pertinenti;
- **FR-026**: distinguere determinability da design adequacy;
- **FR-027**: produrre scope/estimand support claim separati da EU.

## 21.3 Ingestione [D0-A1]

- TXT/MD e CSV semplici;
- Methods/caption;
- più artefatti;
- codice read-only;
- formati complessi stage-gated;
- distinction planned/executed/review-comment;
- Experiment Block candidates con boundary evidence.

## 21.4 Parser AI [A0-A1]

- evidence, entity, count, factor, endpoint;
- core relations/events;
- assignment/application/exposure candidate;
- independence candidate con source class;
- conflicts, alternatives, missing predicates;
- confidence/provenance/coverage;
- nessun verdict diretto;
- nessuna normalizzazione che inventi contenuto scientifico.

## 21.5 Verifier e human-in-the-loop

- hard verification sempre;
- semantic verification solo su trigger;
- evidence/alternative visibili;
- confirm/reject/patch dei fatti, non dei claim derivati;
- authority type, evidence basis e support grade;
- consistency check planned/executed;
- sensitivity preview prima della conferma;
- ConflictRecord e RuleChallenge;
- audit immutabile.

## 21.6 Value of Abstention

- **FR-060**: missing predicate;
- **FR-061**: scenario set con exhaustive/coverage state;
- **FR-062**: domanda primaria;
- **FR-063**: reporting improvement;
- **FR-064**: inference limit;
- **FR-065**: artefatto utile anche senza verdict;
- **FR-066**: known coverage gaps;
- **FR-067**: distinzione tra unknown-unknown risk e known missingness.

## 21.7 Data e synthetic

- provenance/licenza/checksum;
- training/evaluation eligibility;
- stand-off annotations;
- decisive double review;
- study-family leakage groups;
- synthetic grades e family split;
- no synthetic external test;
- real-only/synthetic-only/hybrid ablation;
- backbone contamination attestation;
- reference stability metadata.

## 21.8 Evaluation e statistical handoff

- **FR-080**: report-level end-to-end scoring;
- **FR-081**: blind residual re-adjudication;
- **FR-082**: clustered precision report;
- **FR-083**: false-certainty event classification;
- **FR-084**: Strategy module `HANDOFF_ONLY` finché non validato;
- **FR-085**: few-cluster abstention floor;
- **FR-086**: contamination-risk report per challenge item.

# 22. Requisiti non funzionali

- **NFR-01** Local-first.
- **NFR-02** No scientific content in logs by default.
- **NFR-03** Provenance per fact/output/authority event/derived claim.
- **NFR-04** Derivation Theory e rules deterministic, versioned and reproducible.
- **NFR-05** Portabilità dichiarata da lockfile e test.
- **NFR-06** No silent cloud.
- **NFR-07** Safe parsers; no imported code execution.
- **NFR-08** Partial success.
- **NFR-09** No silent truncation; coverage report.
- **NFR-10** Resource profiles benchmark-derived sul M5 24 GB.
- **NFR-11** Rule latency p95 target <2 s sul Core, da validare.
- **NFR-12** Wizard operations target <500 ms, da validare.
- **NFR-13** Parser latency target per chunk PROVISIONAL.
- **NFR-14** Quick Design target <10 min; la soglia di domande riguarda la presentazione, non la completezza degli scenari.
- **NFR-15** English-first parser; UI IT/EN.
- **NFR-16** Explicit schema/theory/rules migration.
- **NFR-17** Family and document-lineage split consistency.
- **NFR-18** No silver/synthetic auto-gold.
- **NFR-19** Statistical diagnostics do not change design class.
- **NFR-20** External test real-only e contamination-attested.
- **NFR-21** Accessibility.
- **NFR-22** Publish RAM/latency/token/disk measurements.
- **NFR-23** Facsimile non-authority.
- **NFR-24** Anti-overclaim.
- **NFR-25** Human authority events append-only.
- **NFR-26** Interference absence cannot be inferred from silence.
- **NFR-27** Cross-domain results are profile-scoped.
- **NFR-28** Reality Gate fail-closed.
- **NFR-29** Bare null/empty scientific semantics forbidden.
- **NFR-30** Determinability and design adequacy stored/reported separately.
- **NFR-31** Every decisive claim exposes assumptions, authority chain and sensitivity where computable.
- **NFR-32** Non-exhaustive scenario sets are explicitly labelled.
- **NFR-33** Rulebook must declare Theory conformance version and coverage gaps.
- **NFR-34** Human disagreement with derived output cannot patch the output; it creates a RuleChallenge.
- **NFR-35** End-to-end residual error is measured after HITL.
- **NFR-36** Evaluation CIs respect the relevant clustering/generalization unit.
- **NFR-37** Analysis-strategy suggestions fail closed below validated evidence/cluster floors.
- **NFR-38** Planned and executed sources are never silently conflated.
- **NFR-39** Current implementation and target architecture are mapped explicitly.
- **NFR-40** Challenge-set backbone exposure risk is documented, never assumed absent.

# 23. UX, adozione e report

## 23.1 Quick Design Session

Il valore immediato è sample sheet + IDs + Methods draft + domande + export, non un audit punitivo. Prima del freeze, l'utente vede quali claim dipendono da sole dichiarazioni e quali sono corroborati.

## 23.2 Value-of-Abstention contract

Per ogni claim non determinato mostrare:

1. ciò che è osservato;
2. ciò che è assertion;
3. ciò che manca;
4. alternative;
5. coverage/exhaustiveness;
6. impatto delle alternative;
7. domanda primaria;
8. reporting improvement;
9. inference scope;
10. known profile gaps;
11. next action.

## 23.3 UI iniziale

Wizard progressivo, tabelle editabili, albero, evidence panel, authority/support badges, claim table, sensitivity panel, conflict badges, summary e export. Nessun JSON obbligatorio.

## 23.4 Friction budget

Target PROVISIONAL:

- Quick Design <=10 min;
- assisted reconstruction semplice <=15 min;
- presentare per prime <=3 domande decisive;
- <=5 correzioni decisive;
- possibilità di `not available`;
- output utile in abstention.

Il limite di tre domande NON autorizza a eliminare scenari o predicati. La coda restante viene conservata e resa accessibile.

## 23.5 Report contract

Ogni report separa obbligatoriamente:

- source claims e structural records;
- AI candidates;
- human confirmations;
- support grade;
- conflict records;
- confirmed graph;
- `DerivedClaim` per query;
- claim-specific `DeterminabilityState`;
- `ReportResolutionState` globale;
- `DesignAdequacyFinding` separato;
- counts;
- scenario coverage;
- sensitivities;
- statistical handoff;
- inference limits;
- profile coverage;
- provenance e versions.

La visualizzazione usa colori distinti per:

- completezza/determinabilità;
- supporto;
- adequacy finding;
- conflitto.

`DETERMINATE` non usa automaticamente verde e non significa “good design”.

## 23.6 Frase di confine epistemico

Ogni report retrospettivo contiene:

> “N-Truth ha valutato i record e le conferme disponibili; non ha osservato direttamente l'esperimento e non può recuperare deviazioni non registrate.”

## 23.7 No bulk-shaming

Nessuna scorecard nominativa automatica. Uso retrospettivo private/research-governed. Nessun badge “valid/invalid paper”.

# 24. Strategia di valutazione end-to-end

## 24.1 Obiettivo primario

La valutazione deve misurare ciò che l'utente consuma: il `ReportBundle` finale dopo parser, verifier, revisione umana e rules engine. Le metriche stage-level restano diagnostiche e non sostituiscono il target end-to-end.

## 24.2 Cinque metriche executive del primo pilot AI

1. **final decisive-claim correctness** su claim end-to-end;
2. **false-certainty rate** post-HITL;
3. **time-to-confirmed-report** vs manuale;
4. **decisive human correction count**;
5. **actionable abstention / unresolved-risk detection**.

Allocation/application accuracy, decisive-edge F1 e count exactness restano metriche secondarie indispensabili per localizzare gli errori.

## 24.3 False-certainty event - definizione operativa

Un evento di falsa certezza si verifica quando il sistema emette un claim `DETERMINATE` o un report senza caveat materiale e il reference audit mostra almeno una delle seguenti condizioni:

- EU/count errato;
- precondizione decisiva non supportata;
- scenario materialmente plausibile omesso e non segnalato;
- conflitto nascosto;
- profile coverage insufficiente non dichiarata;
- inference/estimand scope più ampio del supportato;
- design adequacy comunicata come positiva senza base.

Il denominatore, lo scope e la severity vengono preregistrati. La confidence del parser non è il solo criterio.

## 24.4 Metriche stage-level

- evidence-span F1;
- entity/count exactness;
- factor/endpoint accuracy;
- assignment/application/exposure candidate accuracy;
- event order;
- decisive relations;
- alternative graph recall;
- contradiction detection;
- schema/coverage/truncation;
- calibration e risk-coverage.

## 24.5 Motore deterministico

Misurare separatamente:

- Theory Reference Set clause pass;
- Rulebook conformance;
- Derivation Gold exact claim match;
- count invariants;
- proof completeness;
- scenario coverage;
- profile coverage;
- errori del motore con grafo corretto;
- RuleChallenge rate.

## 24.6 End-to-end evaluation

Per ogni caso reale:

1. congelare artefatti di input;
2. eseguire parser/verifier;
3. far revisionare secondo protocollo;
4. derivare il report;
5. confrontare il report completo con reference indipendente;
6. classificare origine dell'errore;
7. misurare burden e tempo;
8. eseguire un audit cieco su un campione.

Output primari:

- exact/partial claim match;
- report-resolution match;
- adequacy-finding match;
- residual error;
- false certainty;
- actionable abstention;
- review-time delta.

## 24.7 Question usefulness

Answerability, output-changing, scenario resolved, tempo, recipient, redundancy e rationale su casi reali. La domanda viene valutata rispetto alla teoria e al reference, non soltanto alla risposta dell'utente.

## 24.8 Reference stability e gold-noise budget

Ogni metrica del modello viene interpretata rispetto a:

- pre-adjudication agreement;
- adjudicator test-retest;
- biology-statistics disagreement;
- sensitivity a nuove fonti;
- residual audit;
- graph-matching uncertainty.

Non usare “reference stability” come sinonimo di verità.

## 24.9 Unità di generalizzazione e resampling

Ogni metrica dichiara:

- unità elementare;
- cluster di resampling;
- stratification variables;
- numero di cluster;
- bootstrap/CI method;
- small-cluster caveat.

Esempi:

- evidence spans: documento/study family;
- burden: utente/laboratorio;
- cross-lab claim: laboratorio/facility;
- graph accuracy: Experiment Block nested in study family.

CI item-level ignorando la gerarchia non autorizzano claim cross-lab.

## 24.10 Precision analysis e release gate

Prima del pilot preregistrare target di precisione o decision region per:

- false-certainty rate;
- final claim correctness;
- review-time reduction;
- abstention usefulness;
- residual-error rate.

La decisione GO/REVISE/LIMIT/STOP usa CI, severity e burden. Non usa una singola soglia senza prevalenza e costo dell'errore.

## 24.11 External Challenge

Real-only, custodito, preregistrato, training-ineligible e inaccessible a generator, prompt development, rule tuning e model selection.

Ogni item possiede `ContaminationAttestation`:

- publication/source date;
- public/private/prospective status;
- backbone release/pretraining-cutoff evidence disponibile;
- text exposure risk;
- study-family overlap;
- detection probes, se applicabili;
- residual risk;
- permitted claim.

Preferire casi prospettici, privati custoditi o post-cutoff. Un test pubblico potenzialmente visto dal backbone può essere diagnostico, non prova unica di generalizzazione.

## 24.12 Synthetic utility

Confrontare real-only, synthetic-only, silver+real, synthetic+real e hybrid. TSTR, hybrid uplift, shortcut sensitivity, calibration, review time e real-holdout persistence. La selezione della mixture non accede al test finale.

## 24.13 Statistical Strategy validation

Prima di abilitare suggerimenti di strategia:

- creare Strategy Reference Set;
- definire design patterns, admissible families e forbidden suggestions;
- few-cluster guardrails;
- reviewer esterno;
- exact exclusions;
- outcome/estimand assumptions;
- test end-to-end di interpretazione da parte dell'utente.

Fino a quel gate, il sistema genera solo statistical handoff e domande.

## 24.14 Soglie provvisorie

Valori F1/IAA/degradation sono planning examples. Le soglie finali richiedono metrica, prevalence, unità di generalizzazione, CI, reference stability, critical-error cost, baseline, burden e abstention rule.

# 25. Hardware, context engineering e strategia di training

## 25.1 Hardware

MacBook Pro Apple M5 Pro, 24 GB unified memory, SSD 1 TB. È target di sviluppo, inferenza e benchmark locale.

## 25.2 Fattibilità da dimostrare

Ogni candidato registra hardware fingerprint, OS/backend, precision, context, batch, memory, swap, latency, tokens, cache e thermal regime. Nessun nome o size garantisce qualità.

L'integrazione engineering di Granite/structured decoding non equivale a qualificazione semantica o scientifica.

## 25.3 Context engineering

Experiment Block routing, overlap/coverage, evidence registry, retrieval, post-stage merge, chunk-loss detection e cache per artefatti invariati.

## 25.4 Training tiers

- locale: baselines, encoder, LoRA limitati, ablation;
- university/cloud funded: teacher generation, sweep, larger training;
- distribution: variante locale nel micro-dominio o profilo hardware superiore dichiarato.

No silent cloud; dati privati richiedono autorizzazione e governance.

## 25.5 Training sequence

1. B0/B4 real baseline;
2. P0 stage metrics;
3. silver auxiliary training;
4. SYN-G0/G1 engineering experiments;
5. real-anchor adaptation;
6. B5 cascade;
7. B6 fine-tuned/distilled;
8. mixture search;
9. calibration;
10. external challenge.

## 25.6 Reality Gate per training

Il protocollo può essere pronto e il training restare HOLD. Public/synthetic data non sostituiscono real anchor.

## 25.7 Storage

Corpora e modelli fuori Git; manifest/checksum/script pubblici. FAT32/exFAT/APFS constraints devono essere documentati. Checkpoint grandi richiedono storage compatibile.
## 25.8 Qualification scope v8

Ogni adapter, quantization, backend, chat template, structured-decoding profile, theory/rules combination e task profile possiede una qualifica separata. Una qualifica runtime non implica accuratezza semantica; una qualifica semantica stage-level non implica correttezza end-to-end.

## 25.9 Test-set exposure policy

Prima di mixture search o model selection, development e challenge registrano backbone exposure risk. Il training sequence non usa il final custodial set per prompt, rule, threshold o schema tuning.

# 26. Ingegneria, repository e testing

## 26.1 Repository

README, LICENSE, SECURITY, CITATION, CONTRIBUTING, GOVERNANCE, docs, schemas, migrations, derivation theory, rules, fixtures, baselines, models, data manifests, annotation guidelines, source packages, tests ed evals.

## 26.2 Testing

- unit test per clause/regola;
- positive/negative/counterfactual fixture;
- theory closure tests;
- schema/migration;
- open-world semantic examples;
- round-trip;
- chunk coverage;
- coreference/timeline;
- conflict/authority/support;
- scenario exhaustiveness;
- count invariants;
- profile coverage;
- provenance;
- privacy/sandbox;
- resource regression;
- end-to-end;
- post-HITL residual audit harness;
- golden reports;
- Reality Gate tests.

## 26.3 Theory/Rule conformance harness

Per ogni clausola:

- clause ID/version;
- profile applicability;
- required predicates;
- irrelevant-dimension rationale;
- positive, negative e minimal counterfactual;
- executable rule mapping;
- expected DerivedClaim;
- proof trace;
- known gaps;
- reviewer.

La suite deve rilevare clausole non implementate, regole senza teoria, output non coperti e fixture che non discriminano il predicato decisivo.

## 26.4 Benchmark harness

Stesso snapshot, config, metrics/CI, resources, taxonomy e report comparativo. Include end-to-end frozen runs e contamination metadata.

## 26.5 Versionamento

Codice, schema, Core Semantic Kernel, theory, ruleset, guideline, dataset, model, prompt, evaluation protocol, authority/support policy e profile coverage versionati separatamente.

## 26.6 ADR

ADR obbligatori per model, backend, quantization, structured decoding, verifier, database, rule language, Derivation Theory revision e cross-domain role. Decisioni non benchmarkate restano OPEN/PROVISIONAL.

## 26.7 Clean-checkout truth

La documentazione GitHub descrive soltanto ciò che esiste in un checkout pulito. Implementazioni locali non committate non sostengono claim pubblici.

## 26.8 Current-to-target mapping

CI verifica che:

- i package citati come `IMPLEMENTED` esistano;
- i moduli `TARGET_ONLY` siano chiaramente marcati;
- lo snapshot non venga trattato come norma;
- il mapping sia aggiornato con ogni migration;
- nessun doc attribuisca al Rulebook una clausola non implementata.

## 26.9 PRD example conformance

Tutti gli esempi YAML/JSON del PRD devono essere:

- validati contro schema;
- privi di bare null/list semantics;
- coerenti con count registry;
- coerenti con eligibility;
- controllati in CI;
- aggiornati con migration tests.

# 27. Privacy, etica, licenze e uso responsabile

## 27.1 Privacy by design

La prima verticale deve evitare dati personali. ID di campione, nomi di file e metadata possono comunque contenere identificatori; il sistema deve eseguire un controllo locale prima di esportare o condividere.

## 27.2 Dati non pubblici

Nessun dato di laboratorio deve essere:

- pubblicato;
- redistribuito;
- inserito nel training;
- trasferito su cloud;

senza autorizzazione esplicita e documentata.

## 27.3 Rischio reputazionale

N-Truth non deve pubblicare accuse automatiche su paper o autori. L'uso retrospettivo deve essere descritto come supporto alla revisione, con linguaggio prudente e possibilità di errore.

## 27.4 DRIVER e proprietà intellettuale

Il progetto deve citare e mappare DRIVER senza riprodurre elementi protetti oltre i limiti consentiti e senza utilizzare loghi o formule che suggeriscano endorsement.
## 27.5 Confine epistemico e comunicazione

I report devono dichiarare che descrivono record e conferme, non osservazioni dirette dell'esperimento. `DETERMINATE` non viene comunicato come certificazione. Support grade, profile coverage e sensitivity devono essere leggibili senza conoscenze tecniche avanzate.

## 27.6 Dati di challenge e contamination risk

Il custode conserva separation of duties, access log e attestation. L'incertezza sul pretraining exposure viene riportata, non cancellata da una dichiarazione “unseen” project-level.

# 28. Roadmap completa e stage gate

## 28.1 Fase 0 - Semantic and reality freeze

- primary persona e micro-dominio;
- Core Semantic Kernel;
- Bootstrap Core;
- Derivation Theory alpha;
- authority/evidence/support policy;
- KnowledgeState e count registry;
- 3-5 reality-check cases;
- reviewer outreach;
- blocker register.

Gate: protocollo compilabile, clause coverage iniziale e nessun blocking schema/theory gap noto. Il tempo calendario è una planning assumption.

## 28.2 Fase 1 - Quick Design v0.1-D

- wizard;
- sample sheet planned/executed;
- Methods draft;
- rule core conforme alla teoria;
- 10-20 cases;
- 30-60 theory/fixture counterfactual;
- usability con utenti reali;
- support/sensitivity report.

Gate: valore immediato misurabile e nessuna conflazione determinability/adequacy.

## 28.3 Fase 2 - Minimum Viable Train A

- Methods/caption only;
- B0/B4 or encoder baseline;
- stage-level structured output;
- hard verifier;
- human review;
- decisive and end-to-end metrics;
- local benchmark;
- contamination inventory del development.

Gate: failure modes compresi e nessun aumento di false certainty.

## 28.4 Fase 3 - Calibration + Synthetic alpha

- 30-50 real cases;
- reference stability e timing;
- Theory Reference Set e Derivation Gold;
- SYN-G0/G1;
- human audit;
- real-only/hybrid comparison;
- Core/theory revision;
- residual audit pilot.

## 28.5 Fase 4 - Feasibility

- 100-150 real cases;
- decisive double review;
- external adjudication;
- B0-B5;
- anti-shortcut/coreference;
- SYN-G2 selettivo;
- unit economics;
- cluster-aware precision analysis;
- contamination-attested challenge plan;
- Resource Gate.

## 28.6 Fase 5 - N-Truth model

- B6 selected tasks;
- adapters/distillation;
- mixture search;
- calibration/abstention;
- verifier;
- cards;
- B5 vs B6 decision;
- residual-error and support-grade analysis.

## 28.7 Track v1.0-D

Compilatore stabile, laboratory pilot, theory/rules conformance, documentation e migration policy.

## 28.8 v1.0-A restricted-domain

L2/L3 parser, real external challenge, human confirmation, claim-specific report, local inference/profile, maintenance and rollback.

## 28.9 Cross-domain profiles

Animal, Imaging, organoids/iPSC e advanced designs richiedono vocabulary, theory clauses, gold, measurement context e challenge dedicati.

## 28.10 Stage gate

Ogni fase termina con GO/REVISE/LIMIT/STOP firmato. Il completamento del codice non è successo scientifico. Un gate deve distinguere:

- engineering readiness;
- semantic/theory readiness;
- data readiness;
- reference stability;
- product value;
- scientific validation.

# 29. Team, governance e sostenibilità

## 29.1 Bootstrap

- Massimiliano: product owner/engineering/initial biology annotation;
- wet-lab reviewer;
- biostatistical reviewer;
- ML/NLP consultant;
- external reviewer/STOP.

## 29.2 Resource redirect

Se entro il periodo preregistrato non esistono almeno reviewer wet-lab, biostatistico e un canale di casi reali, il progetto resta in bootstrap e non apre feasibility o training sostanziale. Il periodo di 30-60 giorni è una management assumption, non una legge scientifica.

## 29.3 Decision rights

| Decisione | Autorità |
|---|---|
| Definitions/rulebook | Biostatistico + domain expert |
| Schema/API | Engineering + scientific review |
| Guideline/gold | Annotation lead + adjudicator |
| Cross-domain role | Scientific reviewer + data owner |
| Synthetic training-approved | ML lead + scientific auditor |
| Model release | Validation committee |
| Data/license | Data steward |
| STOP/LIMIT | Independent reviewer |

## 29.4 Circularity safeguards

Founder non adjudica da solo, external set separato, preregistration, conflict disclosure e release decision.

## 29.5 Funding workstream

Outreach, LOI, budget, in-kind, storage/compute e LIMIT condition.

## 29.6 Governance progressiva

- A: vincoli permanenti;
- B: lean bootstrap;
- C: real gold/training;
- D: v1.0-A release.

Comitati onerosi entrano quando rischio, dati o claim lo richiedono.
## 29.7 Derivation Theory governance

Una revisione della teoria richiede:

- proposal e rationale;
- counterexample;
- affected claims/profiles;
- independent methodological review;
- rule conformance update;
- migration impact;
- re-derivation report;
- release decision.

Un RuleChallenge non equivale automaticamente ad accettazione della modifica.

## 29.8 External Challenge separation of duties

Custodian, model-development owner e release decision owner devono essere distinti o avere controlli compensativi documentati.

# 30. Rischi e mitigazioni

| Rischio | Impatto | Mitigazione |
|---|---|---|
| Derivation Theory incompleta/circolare | Critico | Theory indipendente, predicate closure, falsification fixtures |
| DETERMINATE interpretato come good design | Critico | Assi separati, neutral UX, DesignAdequacyFinding |
| Conferma umana fragile | Critico | SupportGrade, evidence basis, sensitivity, corroboration |
| Scenario space troncato | Critico | ScenarioCoverage e non-exhaustive banner |
| Real gold insufficiente | Critico | Acquisition portfolio, Reality Gate, funding |
| Informazione assente | Alto | Prospective-first, epistemic boundary, abstention value |
| Schema burden | Alto | Bootstrap Core, complexity tiers, Burden Gate |
| Human authority conflata | Critico | Orthogonal authority/evidence/support + ConflictRecord |
| Assignment = independence | Critico | Assi separati e theory clauses |
| Interference inferenzialmente inerte | Alto | Exposure mapping, claim consequences, UNKNOWN fail-closed |
| Measurement process ignorato | Alto nei profili imaging | MeasurementProcessContext |
| Causal overclaim | Critico | Causal-aware context, non causal engine |
| Statistical advice errato | Critico | HANDOFF_ONLY, Strategy Reference Set, few-cluster floor |
| Synthetic shortcut/collapse | Alto | Real baseline, family split, audits |
| Pretraining contamination | Alto | ContaminationAttestation, prospective/private challenge |
| Evaluation pseudo-replication | Alto | Cluster-aware CI e precision planning |
| Cross-domain leakage | Alto | Profile-specific role e challenge |
| Train D sostituisce Train A | Alto | Continuity covenant e quarterly review |
| AI locale insufficiente | Alto | Early benchmark, limited profile |
| Retrospettivo troppo indeterminato | Alto | Value-of-Abstention contract |
| Prospective adoption bassa | Alto | Quick Design value in minutes |
| Annotation/reference cost | Critico | Empirical timing, stratified review, funding |
| Reference standard instabile | Critico | Reference stability, adjudicator retest, residual audit |
| Rulebook non coprente | Alto | Theory/rule coverage e OUT_OF_SCOPE |
| JSON valid but false | Alto | Full validation stack |
| Open-world semantics ambigua | Critico | KnowledgeState, schema examples in CI |
| Count semantics drift | Alto | Canonical Count Registry + invariants |
| Statistical washing | Critico | Hard prohibition |
| Dati/licenze | Critico | DMP, manifests, custody |
| Circularity founder/reviewer | Alto | independent reviewers |
| Naming overclaim | Medio | naming review |
| Clean-checkout drift | Alto | publishability gate e architecture map |

Le classi sono prior iniziali da riesaminare con evidenza.

# 31. KPI e criteri di successo

Massimo cinque KPI executive per fase. Nessun KPI considera la percentuale `DETERMINATE` come successo autonomo.

## 31.1 v0.1-D

1. critical theory/fixture false-certainty performance;
2. utenti che completano Quick Design;
3. tempo mediano;
4. real-case theory/rules coverage;
5. blocker scientifici e RuleChallenge.

## 31.2 Calibration/feasibility

1. decisive-predicate reference stability;
2. person-hours per complexity tier;
3. claim-state + support-grade distribution;
4. MVT-A end-to-end baseline;
5. blind residual-error rate.

## 31.3 Train A

1. final decisive-claim correctness;
2. false certainty + calibration/abstention;
3. review-time reduction;
4. contamination-attested external challenge;
5. hybrid uplift vs real-only su real holdout.

## 31.4 Product value

- Quick Design completion;
- actionable abstention rate;
- answerable/output-changing questions;
- Methods/sample-sheet usefulness;
- biostatistician handoff quality;
- user understanding of support and limitations.

## 31.5 Open science/governance

Zero unlicensed asset, active reviewer/LOI, citable theory/schema/rules, cards per release, challenge attestation, no overclaim e no hidden conflict.

# 32. Definition of Done

## 32.1 Bootstrap Reality/Semantic Gate

- primary persona e micro-dominio;
- Core Semantic Kernel;
- Bootstrap Core;
- Derivation Theory alpha;
- KnowledgeState/count registry;
- authority/evidence/support policy;
- 3-5 reality checks;
- human second review su almeno un real case;
- no blocking schema/theory gap;
- training remains false.

## 32.2 v0.1-D

Core, theory, Rulebook conformance, claim-specific determinability, Quick Design, sample sheet, Methods, counts, sensitivity, proof, coverage, storage, security e external review.

## 32.3 v0.2-A

Methods routing, evidence/entity/count/factor extraction, structured output, hard verifier, human confirmation, end-to-end report baseline e local benchmark.

## 32.4 Calibration pilot

30-50 real cases, reference stability/prevalence, timing, theory/rules coverage, SYN-G0/G1 audit, residual audit pilot, budget e GO/REVISE/LIMIT/STOP.

## 32.5 Feasibility

100-150 real cases, decisive double review, external adjudication, B0-B5, anti-shortcut, ablation, cluster-aware precision analysis, challenge contamination plan e Resource Gate.

## 32.6 v1.0-D

Stable compiler, reviewed Derivation Theory, lab pilot, support, migration, no critical regression and communication review.

## 32.7 v1.0-A

L2 parser, trained/distilled component, B5/B6 decision, real contamination-attested external challenge, human decisive confirmation, calibration, residual-error gate, local/profile deployment, maintenance and rollback.

## 32.8 Release blockers

- gold senza provenance/reference stability;
- synthetic/silver as gold;
- AUTHOR_ASSERTION closes claim without support caveat;
- unresolved conflict hidden;
- interference assumed absent;
- effective_n repairs design;
- TEST training eligible;
- leakage;
- output count fuori claim determinability;
- unreviewed critical theory clause/rule;
- contaminated external set senza attestation;
- no real anchor;
- B6 without B5 comparison;
- public automated scorecard;
- bare null/empty scientific semantics;
- non-exhaustive scenario presented as exhaustive;
- DETERMINATE rendered as design approval;
- strategy suggestion below validated cluster floor;
- RuleChallenge applied as direct output patch;
- report privo di profile coverage o sensitivity per decisive self-report.

# 33. Istruzioni vincolanti per un agente AI di sviluppo

1. Preservare AI + deterministic engine come obiettivo finale.
2. Non confondere v1.0-D con completamento del progetto.
3. Applicare Reality Gate prima del fine-tuning sostanziale.
4. Separare Core Semantic Kernel, Bootstrap Core e Full Scientific Record.
5. Non ampliare il Core senza real-case evidence.
6. Implementare Derivation Theory prima di espandere il Rulebook.
7. Mappare ogni regola a una clause ID; una regola senza teoria è bloccante.
8. Definire decisive predicates rispetto alla teoria, non all'output corrente del codice.
9. Non hard-codificare backbone senza benchmark.
10. Non costruire monolite multi-task prematuro.
11. Implementare Minimum Viable Train A presto.
12. Separare evidence, candidate graph, human patch e DerivedClaim.
13. Non predire direttamente n/verdict/determinability.
14. Non dedurre independence da keyword, well o allocation.
15. Distinguere assignment, application, exposure, source, analytical e measurement dependence.
16. Registrare event timing con event ID.
17. Non emettere exchangeability come fatto automatico.
18. Registrare interference come UNKNOWN quando non documentata.
19. Non cambiare automaticamente EU per interference: derivare claim specifici su exposure/estimand/scope.
20. Associare ogni claim a InferentialQuery.
21. Usare KnowledgeState; vietare bare null/empty semantics.
22. Applicare Authority/Evidence/Support Policy.
23. Human confirmation non cancella conflict without record.
24. Ogni self-report decisivo porta support grade e sensitivity.
25. Applicare claim-specific DeterminabilityState.
26. Separare DeterminabilityState e DesignAdequacyFinding.
27. Non colorare DETERMINATE come approvazione del disegno.
28. Rendere l'astensione utile.
29. Etichettare ScenarioCoverage; non troncare la possibilità scientifica per UX.
30. Collegare counts a query/scope/cohort.
31. Usare un solo Canonical Count Registry.
32. Tenere effective_n separato.
33. Statistical strategy module resta HANDOFF_ONLY finché non validato.
34. Non produrre formula statistica universale.
35. Applicare few-cluster abstention floor.
36. Hard verifier sempre; model verifier solo se utile.
37. Question templates prima del free-form.
38. Stage-gate formati complessi.
39. No active learning prima di reference stability/baseline.
40. Synthetic augmentation, mai external test.
41. SYN-G0/G1 può esistere per engineering; training approval richiede real baseline.
42. Mantenere family/document-lineage anti-leakage.
43. Dati cross-domain hanno ruolo profile-specifico.
44. In-vivo gold non valida automaticamente in-vitro.
45. Parser Gold, Theory Reference Set e Derivation Gold separati.
46. Doppiare i decisive predicates.
47. Misurare person-hours per complexity tier.
48. Ridurre schema se burden non produce valore.
49. Misurare end-to-end final reports, non solo stage metrics.
50. Eseguire blind residual audit dopo HITL.
51. Dichiarare unità di generalizzazione e cluster dei CI.
52. External Challenge richiede ContaminationAttestation.
53. RuleChallenge produce nuova versione e re-derivation; mai output patch.
54. Ogni report contiene ProfileCoverageStatement e source-to-reality boundary.
55. Bloccare feasibility senza Resource Gate.
56. No imported code execution or macros.
57. B6 default solo se supera B5/burden.
58. Clean-checkout documentation truth.
59. Mantenere current-to-target architecture map.
60. No bulk-shaming or certification claims.
61. Ogni clause/rule decisiva ha positive, negative e counterfactual tests.
62. Ogni esempio PRD/schema deve passare conformance CI.

# 34. Riferimenti essenziali

- [R01] Lazic SE, Clarke-Williams CJ, Munafò MR. *What exactly is N in cell culture and animal experiments?* PLOS Biology, 2018. DOI: 10.1371/journal.pbio.2005282.
- [R02] NC3Rs Experimental Design Assistant. *Experimental unit*. https://eda.nc3rs.org.uk/index.php/experimental-design-unit
- [R03] NC3Rs. *The DRIVER recommendations: Improving the quality of in vitro research*, 23 July 2026. https://nc3rs.org.uk/news/driver-recommendations-improving-quality-vitro-research
- [R04] NC3Rs. *DRIVER recommendations - About*. https://nc3rs.org.uk/3rs-resources/driver-recommendations/about
- [R05] NC3Rs. Terms and conditions. https://nc3rs.org.uk/terms-and-conditions
- [R06] NC3Rs Experimental Design Assistant. https://eda.nc3rs.org.uk/experimental-design
- [R07] EMBL-EBI BioImage Archive. REMBI Overview.
- [R08] EMBL-EBI BioImage Archive. REMBI Model Reference.
- [R09] ISA Tools. ISA Model & Serialization Specifications.
- [R10] PubMed Central. PMC Open Access Subset.
- [R11] PubMed Central. For Developers.
- [R12] EMBO SourceData.
- [R13] CRAFT Corpus.
- [R14] University of Bristol. *What exactly is N - Dataset*.
- [R15] Eleftheriou C et al. *Better statistical reporting does not lead to statistical rigour*, Molecular Autism, 2025. DOI: 10.1186/s13229-025-00663-3.
- [R16] Hurlbert SH. *Pseudoreplication and the Design of Ecological Field Experiments*. Ecological Monographs, 1984. DOI: 10.2307/1942661.
- [R17] Abreu-Vicente J et al. *Integrating curation into scientific publishing to train AI models*. Bioinformatics, 2025. DOI: 10.1093/bioinformatics/btaf685.
- [R18] Doneva S et al. *PreClinIE*. BioNLP 2025. DOI: 10.18653/v1/2025.bionlp-1.8.
- [R19] Baumgartner WA Jr et al. *CRAFT Shared Tasks 2019 Overview*. DOI: 10.18653/v1/D19-5725.
- [R20] Geng S et al. *Generating Structured Outputs from Language Models*, 2025. arXiv:2501.10868.
- [R21] Sun X et al. *Earley-Driven Dynamic Pruning for Efficient Structured Decoding*. ICML 2025.
- [R22] Josifoski M et al. *SynthIE*. EMNLP 2023. DOI: 10.18653/v1/2023.emnlp-main.96.
- [R23] Wang Z et al. *Faithful Low-Resource Data-to-Text Generation through Cycle Training*. ACL 2023.
- [R24] Dao A et al. *Overcoming Data Scarcity in NER*. BioNLP 2025.
- [R25] Modarressi A et al. *Consistent Document-level Relation Extraction via Counterfactuals*. EMNLP 2024.
- [R26] Shumailov I et al. *AI models collapse when trained on recursively generated data*. Nature, 2024. DOI: 10.1038/s41586-024-07566-y.
- [R27] Xie SM et al. *DoReMi*. NeurIPS 2023.
- [R28] Askari-Hemmat R et al. *Improving the Scaling Laws of Synthetic Data with Deliberate Practice*. ICML 2025.
- [R29] Percie du Sert N et al. *ARRIVE guidelines 2.0 explanation and elaboration*. PLOS Biology, 2020.
- [R30] Ratner A et al. *Snorkel*. VLDB, 2018.
- [R31] Aarts E et al. *A solution to dependency: multilevel analysis*. Nature Neuroscience, 2014. DOI: 10.1038/nn.3648.
- [R32] ModernBERT: Warner B et al. *Smarter, Better, Faster, Longer: A Modern Bidirectional Encoder*. 2024/2025.
- [R33] IBM. Granite 4.1 model documentation and model cards, 2026.
- [R34] Qwen 3.8 Max red-team review supplied by the project owner, August 2026; treated as a review input, not a primary scientific source.
- [R35] Aronow PM, Samii C. *Estimating Average Causal Effects Under General Interference*. Annals of Applied Statistics, 2017. DOI: 10.1214/16-AOAS1005.
- [R36] Hudgens MG, Halloran ME. *Toward Causal Inference With Interference*. JASA, 2008. DOI: 10.1198/016214508000000292.
- [R37] ICH E9(R1). *Addendum on Estimands and Sensitivity Analysis in Clinical Trials*, 2020/2021. Concepts used as terminology guidance, not preclinical regulatory conformance.
- [R38] Rubin DB. *Estimating causal effects of treatments in randomized and nonrandomized studies*. Journal of Educational Psychology, 1974.
- [R39] Sävje F, Aronow PM, Hudgens MG. *Average Treatment Effects in the Presence of Unknown Interference*. Annals of Statistics, 2021. DOI: 10.1214/20-AOS1973.

- [R40] Artstein R, Poesio M. *Inter-Coder Agreement for Computational Linguistics*. Computational Linguistics, 2008;34(4):555-596. DOI: 10.1162/coli.07-034-R2.
- [R41] Saravanan V, Berman GJ, Sober SJ. *Application of the hierarchical bootstrap to multi-level data in neuroscience*. Neuron, Behavior, Data Analysis, and Theory, 2020;3(5). PMCID: PMC7906290.
- [R42] Cameron AC, Gelbach JB, Miller DL. *Bootstrap-Based Improvements for Inference with Clustered Errors*. Review of Economics and Statistics, 2008;90(3):414-427. DOI: 10.1162/rest.90.3.414.
- [R43] Oren Y, Meister N, Chatterji N, Ladhak F, Hashimoto T. *Proving Test Set Contamination in Black-Box Language Models*. ICLR 2024.
- [R44] Dekoninck J, Müller MN, Vechev M. *ConStat: Performance-Based Contamination Detection in Large Language Models*. NeurIPS 2024. DOI: 10.52202/079017-2935.
- [R45] Raoof N, Rout L, Daras G, Sanghavi S, Caramanis C, Shakkottai S, Dimakis A. *Infilling Score: A Pretraining Data Detection Algorithm for Large Language Models*. ICLR 2025.
- [R46] External critical review of N-Truth PRD v8.0 supplied by the project owner, 6 August 2026; treated as a red-team input, not a primary scientific source.
- [R47] NC3Rs DRIVER crosswalk snapshot. URL, retrieval timestamp, content hash and mapped item identifiers must be recorded in the project crosswalk registry; the news release alone is not a substitute for the mapped resource snapshot.

# Appendice A - Esempio completo di Experiment Bundle v8

```yaml
bundle_id: NT-EX-0001
bundle_version: 8.0-example
profile:
  id: simple_cell_culture
  theory_version: derivation-theory-0.1.0
  ruleset_version: ntruth-core-0.3.0
  coverage_status: PARTIAL_PROFILE_COVERAGE
  known_gaps:
    - undocumented_culture_origin_across_runs

domain: simple_cell_culture
record_context: RETROSPECTIVE_DOCUMENT_RECONSTRUCTION

sources:
  - id: methods_01
    source_class: PUBLISHED_METHODS
    planned_or_executed: CLAIMED_EXECUTED
    license: CC-BY-4.0
    sha256: example-placeholder
  - id: sheet_01
    source_class: SAMPLE_METADATA_EXECUTED
    planned_or_executed: EXECUTED_RECORD
    license: LOCAL_PERMISSION
    sha256: example-placeholder

inferential_query:
  id: IQ-001
  factor_id: treatment
  compared_levels: [vehicle, drug_x]
  endpoint_id: neurite_length
  condition_or_timepoint: 48h
  effect_measure_or_estimand:
    knowledge_state: PRESENT
    value: mean_difference
  inference_population:
    knowledge_state: PRESENT
    value: cultures_under_protocol_x
  inference_level:
    knowledge_state: PRESENT
    value: well

factor:
  id: treatment
  levels: [vehicle, drug_x]

assignment_event:
  id: ASSIGN-01
  factor_id: treatment
  assigned_unit_type:
    knowledge_state: PRESENT
    value: well
  mechanism:
    knowledge_state: UNKNOWN
  separability:
    knowledge_state: UNKNOWN
  timing:
    relation: AFTER
    reference_event_id: SPLIT-01
    knowledge_state: PRESENT

application_event:
  id: APPLY-01
  factor_id: treatment
  application_unit_type:
    knowledge_state: PRESENT
    value: well
  timing:
    relation: AFTER
    reference_event_id: PLATE-01
    knowledge_state: PRESENT

exposure_assessment:
  factor_id: treatment
  exposure_pathway:
    knowledge_state: UNKNOWN
  effective_exposure_cluster:
    knowledge_state: UNKNOWN
  interference_status:
    knowledge_state: PRESENT
    value: POSSIBLE
  shared_environment:
    knowledge_state: PRESENT
    items: [plate_01, day_01]

source_context:
  preparation_id:
    knowledge_state: PRESENT
    value: culture_batch_01
  biological_source_independence:
    knowledge_state: UNKNOWN
  biological_source_type:
    knowledge_state: PRESENT
    value: donor

endpoint:
  id: neurite_length
  measured_on: segmented_cell

contrast:
  id: drug_vs_vehicle
  factor_id: treatment
  compared_levels: [vehicle, drug_x]

units:
  - {id: donor_01, type: donor}
  - {id: culture_01, type: culture}
  - {id: well_A01, type: well}
  - {id: field_A01_01, type: field}

relations:
  - {source: culture_01, type: derived_from, target: donor_01}
  - {source: well_A01, type: derived_from, target: culture_01}
  - {source: field_A01_01, type: acquired_from, target: well_A01}

counts:
  - count_id: CNT-DECL-01
    kind: declared_n
    knowledge_state: PRESENT
    value: 3
    quantifier: EXACT
    unit_type:
      knowledge_state: PRESENT
      value: experiment_run
    query_id: IQ-001
    group_id: ALL
    cohort_id: COHORT-01
    scope_status: AMBIGUOUS
    source_evidence: [EV-02]
  - count_id: CNT-OBS-01
    kind: observational_n
    knowledge_state: NOT_REPORTED
    query_id: IQ-001
    group_id: ALL
    cohort_id: COHORT-01

planned_executed_reconciliation:
  status: NOT_AVAILABLE
  rationale: no prospective plan was provided

evidence:
  - id: EV-01
    type: STRUCTURAL_FACT
    text: Each culture was divided into six wells.
    source_id: methods_01
  - id: EV-02
    type: AUTHOR_ASSERTION
    text: Three independent experiments were performed.
    source_id: methods_01
  - id: EV-03
    type: PROCEDURAL_EVENT
    text: Drug X was added after plating.
    source_id: methods_01

missing_predicates:
  - predicate_id: PRED-RUN-SOURCE-IDENTITY
    knowledge_state: UNKNOWN
    affects_claims: [CLAIM-EU-01, CLAIM-N-01, CLAIM-SCOPE-01]

questions:
  - id: Q-001
    predicate_id: PRED-RUN-SOURCE-IDENTITY
    priority: PRIMARY
    text: Were the three experiment runs initiated from distinct biological preparations, and were treatment levels assignable separately within each run?

scenario_set:
  id: SCEN-01
  exhaustive: false
  coverage_basis:
    - DT-EU-ASSIGNMENT-01
    - DT-SOURCE-SCOPE-02
  coverage_caveat: Other undocumented preparation histories may remain possible.
  scenarios:
    - id: S-A
      assumption: distinct_preparations_and_separate_assignment
    - id: S-B
      assumption: repeated_runs_from_shared_preparation

derived_claims:
  - claim_id: CLAIM-EU-01
    claim_type: EXPERIMENTAL_UNIT
    query_id: IQ-001
    determinability: MULTIPLE_PLAUSIBLE_GRAPHS
    value:
      knowledge_state: UNKNOWN
    support_grade: MIXED_UNRESOLVED
    theory_clauses: [DT-EU-ASSIGNMENT-01, DT-EU-EXPOSURE-02]
    rule_trace: [EU-WELL-CANDIDATE-01]
    assumptions:
      - assignment separability unresolved
      - effective exposure cluster unresolved
    profile_coverage: PARTIAL_PROFILE_COVERAGE
  - claim_id: CLAIM-SOURCE-01
    claim_type: BIOLOGICAL_SOURCE_COUNT
    query_id: IQ-001
    determinability: INSUFFICIENT_INFORMATION
    value:
      knowledge_state: UNKNOWN
    support_grade: NOT_SUPPORTED
    theory_clauses: [DT-SOURCE-COUNT-01]
  - claim_id: CLAIM-ADEQUACY-01
    claim_type: DESIGN_ADEQUACY_FINDING
    query_id: IQ-001
    determinability: INSUFFICIENT_INFORMATION
    value:
      knowledge_state: UNKNOWN
    support_grade: NOT_SUPPORTED

report_resolution_state: MULTIPLE_PLAUSIBLE_GRAPHS

epistemic_boundary:
  statement: N-Truth evaluated the inspected records and confirmations; it did not observe the experiment directly.
```

# Appendice B - Template di annotazione v8

Per ogni Experiment Block:

1. identificare domanda, factor, contrast, endpoint e InferentialQuery;
2. scegliere il profilo e registrare il relativo coverage statement;
3. separare planned, executed, published claim e clarification;
4. marcare structural records, procedural events e assertions;
5. creare unità, relazioni ed eventi con ID stabili;
6. registrare assignment, application ed exposure separatamente;
7. registrare biological source e preparation provenance;
8. registrare counts con Canonical Count Registry, cohort e query scope;
9. usare KnowledgeState per tutti i campi scientifici;
10. identificare predicati mancanti, conflitti e scenari;
11. formulare domanda primaria e secondarie ordinate;
12. proporre candidate graph senza scegliere claim derivati;
13. registrare authority type, evidence basis e support grade;
14. eseguire freeze della primary;
15. second review cieca sui decisive predicates;
16. classificare disaccordi;
17. adjudicare fatti/reference, non patchare output del Rulebook;
18. derivare claim tramite theory/ruleset;
19. creare RuleChallenge se un claim derivato è contestato;
20. registrare burden, difficulty e reviewer confidence;
21. separare Parser Gold, Theory Reference Set e Derivation Gold;
22. assegnare eligibility e leakage group.

Campi derivati non devono essere usati come scorciatoia durante l'annotazione primaria.

# Appendice C - Domande minime per dominio

## C.1 Colture cellulari

- Da quante preparazioni biologiche indipendenti provengono le colture?
- I pozzetti sono stati trattati indipendentemente?
- Il trattamento è avvenuto prima o dopo lo splitting?
- Le ripetizioni sono nuovi thaw, nuovi donatori, nuovi passaggi o sole misure?
- Quante piastre e giornate sono coinvolte?

## C.2 Microscopia

- Quanti campi provengono dallo stesso pozzetto o specimen?
- Come sono associati i file ai campioni?
- Le immagini sono acquisizioni ripetute della stessa regione?
- Quale algoritmo ha definito gli oggetti analizzati?
- Qual è l'unità analitica per questo endpoint?
- A quale livello vengono aggregate le feature?

## C.3 Animali ed ex vivo

- A quale livello è stato somministrato il trattamento?
- Le sezioni derivano dallo stesso animale?
- Gabbia o litter sono fattori rilevanti?
- Esistono trattamenti contralaterali o crossover?
- Qual è la popolazione di generalizzazione?

# Appendice D - Pilot di reference stability

## D.1 Calibration pilot

- 30-50 casi reali;
- due annotatori indipendenti sui decisive predicates;
- Core Semantic Kernel e Bootstrap Core obbligatori;
- misura tempo per campo/tier;
- taxonomy dei disaccordi;
- graph-equality protocol congelato;
- adjudication rationale;
- adjudicator test-retest su campione;
- blind residual re-adjudication su campione;
- revisione guideline/theory consentita;
- nessun claim di validazione finale.

## D.2 Feasibility pilot

- 100-150 casi reali;
- protocollo e guideline congelati;
- doppia annotazione stratificata;
- adjudication esterna;
- report di reference stability e gold-noise budget;
- baseline B0-B5;
- precision analysis cluster-aware;
- nessun training sul test congelato;
- contamination inventory del backbone;
- decisione GO/REVISE/LIMIT/STOP.

## D.3 Unità di reporting obbligatorie

Riportare sempre:

- casi;
- study families;
- articoli;
- laboratori/facility;
- coppie di annotatori;
- distribuzione per complexity tier e profile.

# Appendice E - Modulo per contributori di dati

Il contributore deve indicare:

- titolo e dominio;
- proprietario;
- pubblico/non pubblico;
- licenza o permesso;
- file inclusi;
- rimozione di identificatori;
- uso consentito: analisi, annotazione, training, redistribuzione;
- embargo;
- contatto;
- riconoscimento;
- revoca per versioni future;
- disponibilità per chiarimenti o adjudication.

# Appendice F - Prima sequenza operativa v8

1. Congelare Core Semantic Kernel, micro-dominio e non-goal.
2. Scrivere Derivation Theory alpha prima di espandere il Rulebook.
3. Validare KnowledgeState, Count Registry e claim contracts.
4. Stabilizzare 10 casi canonici e minimal counterfactual.
5. Far revisionare teoria e Core da wet-lab e biostatistica.
6. Implementare Rulebook con conformance harness.
7. Costruire Quick Design, sample sheet planned/executed e neutral report.
8. Implementare router, chunking e candidate extraction.
9. Eseguire Minimum Viable Train A.
10. Avviare calibration pilot da 30-50 casi.
11. Misurare reference stability, burden e residual error.
12. Congelare feasibility protocol e contamination plan.
13. Addestrare soltanto dopo Reality Gate.
14. Mantenere l'AI come deliverable obbligatorio della v1.0.

## F.1 Deliverable dei primi novanta giorni

- Core Semantic Kernel e schema Bootstrap pubblicati;
- Derivation Theory alpha;
- vocabolario iniziale;
- almeno 30 fixture/counterfactual;
- Rulebook conforme alla teoria;
- editor/wizard visuale minimo;
- sample sheet generator;
- report neutrale con claim, support, sensitivity e domande;
- 10-20 bundle reali/pubblici;
- pipeline documentale prototipale;
- baseline locale few-shot/encoder;
- protocollo calibration pilot;
- contratto stabile del parser;
- current-to-target architecture map.

## F.2 Condizioni per iniziare il training

1. schema e teoria stabili su almeno venti disegni reali;
2. clausole/regole principali revisionate;
3. output strutturato valido e semanticamente valutato end-to-end;
4. guideline chiara su fatti/assertions/inferenze;
5. calibration pilot completato;
6. reference stability descritta;
7. licenze registrate;
8. split senza leakage;
9. budget annotativo e compute identificati;
10. baseline real-only eseguite;
11. synthetic factory calibrata;
12. contamination risk del test documentato.

## F.3 Condizioni per dichiarare utile il modello AI

- riduce il tempo di costruzione del report;
- identifica predicati decisivi e timeline;
- distingue assertions da record;
- supera baseline end-to-end;
- genera domande discriminative;
- si astiene fuori dominio;
- mantiene prestazioni su fonti indipendenti;
- conserva provenance, alternative e coverage;
- opera entro il budget locale;
- non aumenta residual false certainty.

# Appendice G - Matrice delle baseline AI

| Baseline | Training N-Truth richiesto | Vantaggio | Limite |
|---|---:|---|---|
| Regex/rule | No | Trasparente e veloce | Bassa copertura |
| SourceData-NLP model | No/adapter | Entità e ruoli sperimentali | Caption-centric, target incompleto |
| PreClinIE | No/adapter | Indicatori di rigore e Methods | In vivo, non allocation completa |
| Encoder + RE | Sì | Efficiente e calibrabile | Coreference/long context difficili |
| LLM few-shot | No | Rapida baseline end-to-end | Variabilità e costi locali |
| Cascata ibrida | Parziale | Controllo e specializzazione | Maggiore complessità |
| N-Truth fine-tuned | Sì | Target completo | Richiede gold e validazione |

# Appendice H - Protocollo per question usefulness, burden e residual audit

## H.1 Question usefulness

Per ogni domanda, reviewer indipendenti valutano:

- answerability 0/1;
- relevance 1-5;
- scenario resolution 0/1;
- output-changing 0/1;
- redundancy 0/1;
- recipient correctness;
- response time;
- evidence requested;
- remaining scenario coverage.

## H.2 Budget dati

Dopo il calibration pilot pubblicare:

- minuti median/p90 per tier;
- percentuale di doppia annotazione;
- tasso di disaccordo;
- tempo di adjudication;
- costo equivalente orario;
- ore disponibili in-kind;
- gap da finanziare;
- learning curve per tranche;
- numero di study family/lab indipendenti.

## H.3 Residual audit

Campionamento stratificato per:

- support grade;
- determinability state;
- complexity tier;
- source class;
- lab/article lineage;
- claim type.

Reviewer cieco rispetto all'output originale. Riportare errori residui, severity, origine e impatto sul claim.

# Appendice I - Canonical Training Record minimo v8

```yaml
record_id: NTR-REC-0001
bundle_id: BUNDLE-REAL-001
record_version: 8.0
profile_id: simple_cell_culture
schema_version: core-kernel-0.1.0

theory_version: derivation-theory-0.1.0
ruleset_version: ntruth-core-0.3.0

sources:
  - source_id: SRC-METHODS
    source_class: PUBLISHED_METHODS
    path: sources/methods.txt
    sha256: real-or-explicit-placeholder
    license_status: VERIFIED

annotation:
  evidence_spans: annotations/evidence.jsonl
  parser_target: annotations/gold_parser_target.json
  candidate_graph: annotations/candidate_graph.json
  adjudicated_graph: annotations/adjudicated_graph.json
  alternatives: annotations/alternative_graphs.json
  authority_events: annotations/authority_events.jsonl
  adjudication: annotations/adjudication.json

derivation_reference:
  inferential_queries: annotations/inferential_queries.json
  expected_claims: annotations/derived_claim_reference.json
  theory_clause_coverage: annotations/theory_clause_coverage.json

counts:
  - count_id: CNT-001
    kind: experimental_unit_count
    knowledge_state: PRESENT
    value: 6
    unit_type: culture
    query_id: IQ-001
    group_id: drug
    cohort_id: COHORT-01
    quantifier: EXACT

eligibility:
  split: TRAIN
  study_family_id: SF-001
  document_lineage_id: DL-001
  laboratory_or_facility_group: LAB-001
  training_eligible: true
  evaluation_eligible: false
  release_eligible: false

provenance:
  created_by: annotation-pipeline-v8
  record_hash: sha256:...
```

Il parser target non include verdict, `DerivedClaim` o determinability finale. Il derivation reference è usato per validare teoria/ruleset, non come target diretto del parser.

# Appendice J - Facsimile Render Manifest

```yaml
render_id: NTR-RENDER-0001
source_record_id: NTR-REC-0001
source_record_hash: sha256:...
render_template: methods_annotation_board-v3
render_version: 3.0
synthetic_notice: true
illustrative_hashes: true
panels:
  - source_evidence
  - candidate_relations
  - adjudicated_gold
  - uncertainty
  - conflicts
  - provenance
validator_results:
  record_view_field_match: 1.0
  count_consistency: PASS
  gate_consistency: PASS
  forbidden_manual_gold: PASS
render_hash: sha256:...
```

# Appendice K - Review matrix delle dodici tavole

| Tavola | Stato | Criticità principale | Azione richiesta |
|---|---|---|---|
| T01 | REVISION_REQUIRED | application_level=WELL is not explicit; experimental_unit_count should be scoped to culture and donor equivalence; absence of exclusions is not proof of none | Mark application as candidate unless source states physical dosing at well; report 6 donor-linked cultures/group; encode exclusions=NOT_REPORTED |
| T02 | ACCEPT_WITH_REVISIONS | TIME has no application_level; analyzed_n and experimental_unit_count need separate row/trajectory semantics; placeholder hashes look real | Use repeated_measure_unit/measurement_schedule_level; clarify analysis rows; mark hashes as placeholders |
| T03 | MAJOR_REVISION | 150-cell derivation is unsupported by caption; donor/culture pairing is ambiguous; panel labels suggest paired donors | Remove unsupported counts or attach source; model paired alternatives; keep experimental_unit_count UNKNOWN |
| T04 | ACCEPT_WITH_REVISIONS | n values are global-looking rather than factor/contrast/endpoint scoped; summary-statistic warning is pedagogical, not a label | Attach scope_id to every count; store mean/SD/SEM as report guidance, not training target |
| T05 | STRONG_WITH_MINOR_FIXES | Physical containment and biological provenance are conflated; image measured_on well is semantically weak | Separate contained_in_plate from derived_from_culture; use image acquired_from field/well |
| T06 | STRONG_WITH_MINOR_FIXES | Numeric confidence is illustrative and uncalibrated; lme4 nesting expansion should be represented precisely | Label confidence as mock or remove; parse (1|donor/culture) into donor and donor:culture grouping terms |
| T07 | STRONG_WITH_REVISIONS | Age cell EV-X02 does not support donor-derived culture claim; peer review should be a separate source class rather than always discarded | Relink table cell to donor entity/row; classify peer review as REVIEW_COMMENT excluded from primary facts by default |
| T08 | MAJOR_REVISION | allocation_level is over-inferred in EB-01/EB-02; stretch at field level is biologically implausible without local stimulation evidence | Downgrade allocation to candidate/unknown; model stretch application at chamber/well/device unless explicit; preserve block-level labels |
| T09 | MAJOR_SCIENTIFIC_REVISION | Different donor count is conflated with experimental-unit count; three cultures from one donor can still be three allocation units while inference scope is donor-limited | Separate n_experimental_units from n_biological_sources and inference_scope; ask both donor-origin and independent-preparation questions |
| T10 | REVISION_REQUIRED | Three wells from one donor are not automatically technical replicates; allocation context is missing | Use neutral interpretation: same-donor wells; ask allocation and preparation questions; keep EU and experimental-unit count UNKNOWN |
| T11 | STRONG_WITH_MINOR_FIXES | IAA values cannot be interpreted per single record; reviewer confidences are illustrative; rationale not shown | Compute IAA over a corpus subset; label scores as mock; add adjudication rationale and evidence delta |
| T12 | BLOCKING_ERROR | split=TEST conflicts with training_eligible=true; supervised record lacks a distinct adjudicated target object | For TEST set training_eligible=false and evaluation_eligible=true, or change split to TRAIN; add GoldParserTarget separate from candidates |

# Appendice L - Correzioni minime prima dell'uso

1. Tavola 01: application level candidato, exclusions NOT_REPORTED, `n` donor-linked culture.
2. Tavola 02: TIME come repeated-measure factor, non treatment application.
3. Tavola 03: rimuovere il conteggio di 150 cellule non supportato.
4. Tavola 04: rendere ogni count scope-aware.
5. Tavola 05: separare containment e biological provenance.
6. Tavola 06: confidence illustrativa e parsing esatto dei grouping terms.
7. Tavola 07: correggere EV-X02 e classificare peer review separatamente.
8. Tavola 08: non assegnare allocation a well/field senza evidenza.
9. Tavola 09: separare EU count, source count e inference scope.
10. Tavola 10: non chiamare automaticamente tecnici i wells dello stesso donor.
11. Tavola 11: IAA corpus-level e adjudication rationale.
12. Tavola 12: correggere l'incompatibilità TEST/training eligible e aggiungere GoldParserTarget.

# Appendice M - Claim-specific Determinability Reference

| Stato | Precondizione claim-specifica | Output ammesso | Output vietato |
|---|---|---|---|
| `DETERMINATE` | Tutti i predicati richiesti dalla clause del claim sono `PRESENT`/`ABSENT_EXPLICIT` o formalmente `NOT_APPLICABLE`; nessun conflitto materiale; profile coverage sufficiente | valore del claim, assumptions, support, sensitivity, proof | claim impliciti non valutati; design approval automatico |
| `CONDITIONALLY_DETERMINATE` | Uno o più predicati finiti non risolti; rami materialmente distinguibili | condizioni, branch outputs, primary question, coverage | singolo valore incondizionato |
| `MULTIPLE_PLAUSIBLE_GRAPHS` | >=2 grafi compatibili con conseguenze differenti | alternative, consequences, coverage status, question | forced choice; exhaustive claim senza prova |
| `INSUFFICIENT_INFORMATION` | Predicato decisivo assente o possibility space non delimitabile | `KnowledgeState`, reporting gap, question, next action | EU/n guess |
| `CONFLICTING_INFORMATION` | Fonti o confirmations incompatibili sul claim | ConflictRecord, retained interpretations | automatic source override |
| `INVALID_GRAPH` | Invariant violation | errors and required patch | scientific claim |
| `OUT_OF_SCOPE` | topology/profile/claim unsupported | structural summary, profile gaps | verdict o release claim |

## M.1 Regola claim-specifica

Non esiste un singolo `DETERMINATE` che certifichi l'intero bundle. Ogni `DerivedClaim` possiede il proprio stato. `ReportResolutionState` aggrega senza cancellare divergenze.

## M.2 Dimensioni irrilevanti

Una dimensione può essere `NOT_APPLICABLE_TO_CLAIM` soltanto con:

- clause ID;
- rationale;
- query scope;
- reviewer;
- proof trace.

Non può essere omessa.

## M.3 Adeguatezza separata

`DesignAdequacyFinding` non è un valore di `DeterminabilityState`. Un claim può essere determinato e descrivere un disegno problematico.

# Appendice N - Derivation Theory Decision Matrix

La tabella è un contratto iniziale del profilo `simple_cell_culture`; non sostituisce le clausole machine-readable.

| Assignment separability | Effective exposure/interference | Source state | Analytical state | Claim consequence |
|---|---|---|---|---|
| `TRUE` | no documented path that collapses level | any | dependent/independent | assignment unit è candidate EU; analytical dependence non crea o elimina EU |
| `TRUE` | `POSSIBLE`/unknown | any | any | EU strutturale può restare determinabile; exposure/estimand support diventa conditional/insufficient; scope caveat obbligatorio |
| `TRUE` | documented common exposure prevents distinct treatment realization | any | any | effective exposure cluster diventa il livello rilevante per il contrasto di esposizione; claim EU/count viene ricalcolato o reso conditional |
| `FALSE` | any | any | any | il livello dichiarato non è EU per quel fattore; risalire al livello assegnabile oppure registrare single-cluster/design-replication finding |
| `UNKNOWN` | any | any | any | EU/count non incondizionati; domande/scenari |
| any | any | source independence `UNKNOWN` | any | non blocca necessariamente EU within-source; blocca o limita biological-source/generalization claim |
| any | any | source count = 1 | any | non riduce automaticamente EU; inference scope e source-diversity finding limitati |
| any | any | any | repeated/correlated | analytical grouping claim; nessuna statistical washing |

## N.1 Formal contract

Per teoria `T`, grafo validato `G`, profilo `P` e query `Q`:

```text
D_T(G, P, Q) -> DerivedClaimSet
```

Ogni claim `c` definisce:

```text
required_predicates_T(c, P, Q)
irrelevant_predicates_T(c, P, Q)
value_T(c, G, P, Q)
determinability_T(c, G, P, Q)
adequacy_findings_T(c, G, P, Q)
```

## N.2 Closure obligation

Il profilo deve pubblicare un `predicate_sufficiency_statement`:

- claim coperti;
- decisive predicate set;
- counterexample search;
- known gaps;
- reviewer;
- version.

La completezza è sempre relativa al profilo e alla teoria dichiarata.

# Appendice O - SampleSheetSpec iniziale v8

| Colonna | Tipo | Obbligo | Nota |
|---|---|---|---|
| `sample_id` | string | required | univoco |
| `record_context` | enum | required | `PLANNED|EXECUTED|RECONCILED` |
| `source_id` | string + KnowledgeState | required | donor/stock/animal; UNKNOWN/NOT_APPLICABLE espliciti |
| `source_type` | enum + KnowledgeState | required | donor, line, animal, tissue, stock |
| `stock_id` | string + KnowledgeState | conditional | per linee immortalizzate |
| `thaw_id` | string + KnowledgeState | conditional | provenance della ripresa |
| `passage_number` | integer + KnowledgeState | conditional | non implica replica |
| `preparation_id` | string + KnowledgeState | required | preparazione biologica |
| `culture_id` | string + KnowledgeState | optional | coltura |
| `plate_id` | string + KnowledgeState | optional | contenimento fisico |
| `well_id` | string + KnowledgeState | optional | coordinate normalizzate |
| `factor_applicability_*` | enum | required per fattore | `APPLIES|NOT_APPLICABLE|UNKNOWN` |
| `factor_level_*` | categorical + KnowledgeState | conditional | richiesto solo se applies |
| `assignment_event_id_*` | string + KnowledgeState | recommended | collega livello a evento |
| `application_event_id_*` | string + KnowledgeState | recommended | delivery event |
| `batch_id` | string + KnowledgeState | optional | rende osservabile il batch |
| `timepoint` | typed + KnowledgeState | optional | unità temporale esplicita |
| `endpoint_id` | string + KnowledgeState | optional | per long format |
| `lifecycle_status` | enum | required | planned/treated/observed/excluded/analyzed |
| `exclusion_reason` | string + KnowledgeState | conditional | fase e autore |
| `file_ref` | string + KnowledgeState | optional | hash/URI locale |

Nessun blank cell ha semantica scientifica. L'importer deve chiedere o assegnare KnowledgeState esplicito.

# Appendice P - Count Registry, event timing ed edge case

## P.1 Canonical Count Registry

`planned_n`, `allocated_n`, `treated_n`, `observed_n`, `excluded_n`, `analyzed_n`, `declared_n`, `observational_n`, `analytical_n`, `experimental_unit_count`, `biological_source_count`, `effective_n_diagnostic`.

`independent_n` è un alias di report deprecato; il record canonico usa `experimental_unit_count` associato a una query.

Ogni count include:

- count ID;
- kind;
- KnowledgeState;
- value/interval;
- quantifier;
- unit type;
- query/factor/contrast/endpoint/timepoint;
- group;
- cohort;
- lifecycle phase;
- source evidence;
- rule trace se derivato.

## P.2 Quantifier compatibility

- `EXACT(a)` vs `EXACT(b)`: conflitto se a != b nello stesso scope/cohort;
- `EXACT(a)` è compatibile con `LOWER_BOUND(b)` se a >= b;
- `EXACT(a)` è compatibile con `UPPER_BOUND(b)` se a <= b;
- `RANGE(l,u)` compatibile se gli intervalli si sovrappongono;
- `APPROXIMATE` produce warning, non equivalenza automatica;
- scope/cohort diversi non vengono confrontati come conflitto numerico.

## P.3 Lifecycle invariants

Applicabili soltanto allo stesso cohort/query/scope e con semantics compatibili:

- allocated <= planned, quando planned è exact e il protocollo non ammette over-recruitment;
- treated <= allocated;
- observed <= treated, salvo observation pre-treatment documentata;
- analyzed <= observed;
- excluded è riconciliato per fase;
- declared deve essere mappato a un count kind o restare ambiguous.

Nessuna monotonicità cross-endpoint viene assunta.

## P.4 Event timing

Usare:

```yaml
timing:
  relation: BEFORE|AFTER|SAME_EVENT|OVERLAPS|UNKNOWN
  reference_event_id: SPLIT-02
```

`timing_relative_to_split` senza event ID è deprecato.

## P.5 Edge case minimi del Rulebook

1. Medium bath o co-treatment dell'intera piastra.
2. Conditioned medium e trasferimento del supernatante.
3. Stesso donor con più colture di source independence sconosciuta.
4. Linee immortalizzate: stock, thaw, passage, day o laboratory come presunta replica.
5. iPSC/organoids: clone e differentiation batch.
6. Insert e co-culture a due popolazioni.
7. Dose-response con EU per curva/query.
8. Time-lapse e repeated observations.
9. Best-field e outcome-guided ROI.
10. ML segmentation con correlated measurement error.
11. Day/operator/lot/plate confounded with treatment.
12. Pool -> split e split -> pool con event IDs.
13. Paired design same donor.
14. Post-outcome exclusions.
15. n differente per endpoint/cohort.
16. Replating post-treatment.
17. Plate randomization with well-level claim.
18. Multiple clones same donor.
19. Destructive and longitudinal endpoints.
20. Differential missingness and post-hoc batch removal.
21. Documented interference with unchanged assignment unit but unsupported direct-effect estimand.
22. Non-exhaustive alternative graph space.

# Appendice Q - Resource Gate Checklist

- [ ] micro-dominio e claim pubblici approvati;
- [ ] almeno un wet-lab reviewer;
- [ ] almeno un biostatistico con ore concordate;
- [ ] autorità esterna di STOP;
- [ ] co-maintainer o PI host prima della feasibility;
- [ ] budget annotativo low/expected/high;
- [ ] compute e storage disponibili;
- [ ] DMP e License Manifest;
- [ ] data custodian per external challenge;
- [ ] condition of LIMIT formalizzata.

# Appendice R - Confirmation Support, Sensitivity e RuleChallenge

## R.1 SupportGrade

| Grade | Significato |
|---|---|
| `ADJUDICATED_REFERENCE` | reference interpretation con protocollo/rationale |
| `CORROBORATED_EXECUTION_RECORD` | conferma supportata da record eseguito indipendente |
| `AUTHOR_CLARIFIED` | chiarimento dell'autore, non necessariamente corroborato |
| `DOMAIN_EXPERT_INTERPRETATION` | interpretazione metodologica con scope |
| `SELF_REPORT_ONLY` | conferma locale senza evidenza indipendente |
| `DOCUMENT_ASSERTION_ONLY` | assertion nella fonte |
| `MODEL_CANDIDATE_ONLY` | proposta AI |
| `MIXED_UNRESOLVED` | supporti incompatibili o insufficienti |

SupportGrade non è una probabilità e non sostituisce determinability.

## R.2 SensitivityRecord

Obbligatorio quando un singolo predicato confermato modifica materialmente EU, count, scope o adequacy finding. Deve contenere output corrente e counterfactual.

## R.3 RuleChallenge

Un expert disagreement con un derived claim produce:

1. freeze dell'output corrente;
2. RuleChallenge con clause/rule ID;
3. review metodologica;
4. theory/rules amendment o rejection;
5. new version;
6. re-derivation;
7. migration/change report.

È vietato sovrascrivere il claim senza questo percorso.

# Appendice S - Synthetic Task Use Matrix v8

**Stato:** specifica normativa per la progettazione degli esperimenti. Le bande sono ipotesi iniziali da confrontare sul development reale; non sono quote di produzione, soglie di release o prove di generalizzazione.

## S.1 Regole di interpretazione

- Le percentuali descrivono la composizione task-specifica dopo deduplica e family grouping.
- Non si applicano a validation, TEST o External Challenge.
- Il limite superiore sintetico è una banda sperimentale, non un obiettivo.
- `real gold minimo` significa casi umani autorizzati, double-reviewed o adjudicated sui campi decisivi.
- Silver e synthetic non soddisfano il real-gold floor.
- TEST ed External Challenge sono 100% reali, training-ineligible e inaccessibili al generator.
- Le bande possono essere ristrette verso il reale; un ampliamento richiede protocol amendment, shortcut audit e nuova mixture search.

## S.2 Bande iniziali

| Classe | Synthetic nel training task-specifico | Real gold minimo | Uso |
|---|---:|---:|---|
| `SYNTHETIC_HEAVY` | 50-80% | almeno 20% | Strutture esplicite, tassonomie chiuse, counts e perturbazioni controllabili |
| `HYBRID` | 20-60% | almeno 40% | Relazioni/eventi simulabili ma sensibili allo stile reale |
| `REAL_HEAVY` | 0-30% | almeno 70% | Inferenze decisive, implicite o biologicamente dipendenti |
| `REAL_ONLY_EVALUATION` | 0% | 100% | Test finale, External Challenge e claim di release |

## S.3 Matrice P0/P1/P2

| Livello | Task | Classe | Ruolo sintetico ammesso | Vincolo reale |
|---|---|---|---|---|
| P0 | Section routing e Methods/Caption detection | SYNTHETIC_HEAVY | Template, negative docs, section order, noise | Real dev/test per style e source shift |
| P0 | Entity extraction | SYNTHETIC_HEAVY | Lexical coverage, rare entities, spelling, minimal pairs | Real gold per boundaries e sinonimia |
| P0 | Count e quantifier extraction | SYNTHETIC_HEAVY | EXACT/RANGE/BOUND/UNKNOWN, unità, tabelle | Real test per layout, omissions e implicit numbers |
| P0 | `nested_in`/`derived_from` espliciti | SYNTHETIC_HEAVY | Known graphs, inversions, negatives | Real gold per language/cross-sentence |
| P0 | Factor, levels, endpoint espliciti | SYNTHETIC_HEAVY | Controlled combinations, name/order anti-shortcut | Real domain nomenclature |
| P0 | Allocation/application esplicite | HYBRID | Explicit events, minimal pairs, controlled confounds | hybrid real floor selected by protocol; separate scoring |
| P0 | Basic contradiction detection | HYBRID | Single-mutation conflicts with known provenance | Subtle/multi-source conflicts real-only evaluation |
| P1 | Cross-document nesting | HYBRID | Omissions, aliases, caption/sheet merge, artifact dropout | Real multi-artifact dev required |
| P1 | Procedural events/order | HYBRID | Graph-first timelines, split/pool/treat perturbations | Real protocols and implicit order |
| P1 | Simple alternative graphs | HYBRID | Controlled ambiguity and known questions | Scenario-set/usefulness on real cases |
| P1 | Decisive coreference | REAL_HEAVY | Counterfactuals and distractors from real error taxonomy | real-heavy; exact floor selected by real-development protocol and separate antecedent eval |
| P1 | Implicit allocation | REAL_HEAVY | Minimal perturbation of reviewed graphs | No claim without real gold/reference stability |
| P1 | Biological/operational independence | REAL_HEAVY | Negative examples and conditional scenarios | Wet-lab + statistical confirmation |
| P1 | Subtle contradictions | REAL_HEAVY | Deliberate practice, never from TEST | Evaluation on real custodial conflicts |
| P1 | Imaging Core | HYBRID | Metadata/hierarchy/missingness control | Real validation for acquisition dependencies |
| P2 | Implicit estimand/inference target | REAL_HEAVY | Supervised paraphrase and counterfactual | Methodological gold + human confirmation |
| P2 | Split-plot/multifactor complex | REAL_HEAVY | Rare topology/invariant stress | Real validation per profile |
| P2 | Free-form question generation | HYBRID | Controlled diversification with answer keys | Expert utility on real cases |
| P2 | Multi-graph calibration/OOD | REAL_HEAVY | Stress/ablation only | Real validation selects thresholds |
| All | External Challenge/release metrics | REAL_ONLY_EVALUATION | Vietato | 100% real, unseen, custodito |

## S.4 Promotion e stop rules

Un task avanza solo se:

1. esiste baseline real-only sullo stesso snapshot;
2. hybrid migliora metriche decisive o burden;
3. calibration e critical-error rate non peggiorano;
4. non emergono shortcut verso template/renderer/family;
5. sono riportati bootstrap CI e prevalence;
6. il miglioramento persiste su real holdout non usato nella mixture search.

Se synthetic-only supera hybrid sul development ma non sul real holdout, il lotto è `SHORTCUT_PRONE` e viene ristretto, rigenerato o escluso.

# Appendice T - Runtime Resource Budget

**Stato:** contratto di benchmark e runtime. Nessun valore di RAM, context window o model size è requisito scientifico finché non viene misurato sul MacBook Pro Apple M5 Pro con 24 GB indicato dal project owner.

## T.1 Principi

- componenti AI eseguiti sequenzialmente per default;
- lifecycle `load -> warmup -> run -> release`;
- chunking gerarchico per bundle, Experiment Block, section e span;
- nessuna truncation silenziosa;
- constrained decoding riguarda forma, non scienza;
- budget generati da benchmark versionato, non stime teoriche;
- ogni diverso adapter, quantization, backend, template o task profile ha qualificazione propria.

## T.2 Profili operativi

| Profilo | Obiettivo | Scheduling | Context/cache | Fallback |
|---|---|---|---|---|
| LOW_MEMORY | Evitare pressure/swap | un componente residente, unload aggressivo | max stabile da benchmark, LRU piccola | CPU compatibile o abstention |
| BALANCED | Default interattivo dopo benchmark | sequenziale, prefetch non-model | compromesso qualità/latency/peak | retry LOW_MEMORY, poi partial |
| QUALITY | Qualità massima nel limite misurato | challenger costoso solo se benchmarkato | context/cache più ampi con safety floor | degrado esplicito a BALANCED |

Un profilo registra `budget_bytes`, `context_tokens`, `batch_size`, `cache_bytes`, `swap_delta_limit_bytes`, hardware fingerprint, runtime, data e benchmark ID. Senza artifact misurato è `UNVERIFIED`.

## T.3 Calcolo del budget

Misurare:

1. baseline memory/swap;
2. load/warmup peak;
3. stage peak per batch/context;
4. post-release memory/cache clear;
5. swap delta e memory pressure;
6. latency p50/p95, input/output tokens, throughput;
7. cache hit/miss/eviction e temporary disk.

Il safety reserve deriva da benchmark concorrente, non da percentuale universale.

## T.4 Budget per stage

| Stage | Modello residente ammesso | Metriche | Release condition |
|---|---|---|---|
| Routing/segmentation | rules, encoder o small LM | latency, peak, input, coverage | map/coverage persisted |
| Evidence/entity/count | un estrattore o multi-task | peak, tokens, truncation, output count | schema-valid artifact |
| Relation/event/coreference | specialist o LM | peak, context, cache, evidence coverage | candidate relations |
| Candidate graph assembly | model/algorithm, never rules verdict | peak, alternatives, invalid outputs | graph + error model |
| Semantic verification | independent process/model on trigger | trigger, peak, latency, disagreement | verifier result |
| Rules engine | no model | latency, rule count, proof size | deterministic verified output |

## T.5 Chunking, context e cache

- Experiment Block è unità primaria;
- global entity/evidence registry per cross-chunk;
- context cap per stage/profile, oltre il massimo benchmarkato il runtime rifiuta;
- overlap/retrieval producono coverage report;
- decisive loss porta a partial/question/abstention;
- LRU byte-aware con key su input hash, stage, schema, model/runtime e config;
- model, artifact e tokenizer caches hanno budget distinti.

## T.6 Telemetria locale

```yaml
bundle_id: pseudonymous-or-local
profile: LOW_MEMORY|BALANCED|QUALITY
benchmark_id: required
stage_metrics:
  - stage: evidence_extraction
    latency_ms: measured
    peak_memory_bytes: measured
    swap_delta_bytes: measured
    input_tokens: measured
    output_tokens: measured
    cache_hits: measured
    cache_evictions: measured
    fallback: none|cpu|lower_profile|abstain
```

Log locali, disattivabili e privi di Methods/evidence/file names sensibili.

## T.7 Benchmark di selezione

Cold start, warm run, long-context, multi-document bundle, worst supported topology e background-load. Confrontare qualità, abstention, review time, latency, peak memory, swap e failure rate.

# Appendice U - Lean Governance Matrix

La governance cresce con il rischio; i vincoli scientifici permanenti valgono subito.

| Livello | Quando | Obblighi minimi | Ruoli/autorità | Evidenza di uscita |
|---|---|---|---|---|
| A. Vincoli permanenti | Sempre | HITL, abstention, provenance, anti-leakage, assertion/fact, allocation/application, no washing, no certification/scorecard | Product owner + scientific reviewer when rules change | tests, audit trail, blocker register |
| B. Lean bootstrap | D0, no scientific training | Bootstrap Core, rulebook, 30-60 fixture candidates, wizard, export, minimal external review | Product/engineering + wet-lab or biostatistical reviewer | Core review, fixture report, PROCEED/REVISE/LIMIT |
| C. Real gold/training | Before human corpus/calibration/fine-tuning | Guideline, DMP, license, Parser/Derivation Gold separation, decisive double review, custody, baseline, measured resource budget | Data steward, annotation lead, wet-lab, biostatistician, ML lead, adjudicator | frozen snapshot, pre-adjudication agreement, benchmark, Resource Gate |
| D. v1.0-A release | Before supported AI claim | preregistered protocol, real external challenge, validation committee, STOP, cards, rollback, maintenance, incident response | committee, external custodian, release owner, independent STOP | GO/REVISE/LIMIT/STOP dossier |

## U.1 Attivazione progressiva

- Resource Gate informativo nel bootstrap, bloccante prima di feasibility/costly training;
- STOP può essere nominata prima, mandato formale prima del custodial test/release;
- validation committee non richiesto per fixture/wizard, obbligatorio per v1.0-A;
- lean governance non autorizza training o claim di livelli successivi.

## U.2 Blocker register

Ogni blocker: ID, area, descrizione, severity, owner, evidence required, status, next review e decision. Obbligatori: false certainty, output fuori DeterminabilityState, critical unreviewed rule, provenance loss, uncertain license, Core scope drift, hidden conflict e Reality Gate bypass.

# Appendice V - Audit v6.1 preservato

La v7.0 conserva le decisioni execution-critical della v6.1: Synthetic Task Use Matrix, Runtime Resource Manager, benchmark A-E, sintassi distinta da semantica, governance progressiva, soglie PROVISIONAL, facsimile invariants, prospective planned/executed e ADR obbligatori.

# Appendice W - Matrice di risposta alla review Qwen 3.8 Max

| Area | Esito | Decisione v7 |
|---|---|---|
| Real gold bottleneck | ACCEPT | Reality Gate e acquisition portfolio |
| Synthetic non sostituisce gold | ALREADY ADDRESSED | Rafforzato |
| Core troppo grande | PARTIAL | Bootstrap Core + Full Record |
| 2-8 ore/caso | UNVERIFIED | Complexity tiers e timing reale |
| Assignment mechanism | ACCEPT | Causal Design Context |
| Interference | ACCEPT | Exposure/interference assessment |
| Exchangeability | MODIFY | Comparability basis, mai label automatica |
| Estimand | STRENGTHEN | InferentialQuery |
| Personas troppe | ACCEPT | Primary + secondary bootstrap |
| <10 min | PRODUCT HYPOTHESIS | Quick Design target PROVISIONAL |
| Baseline semplice | ACCEPT | Minimum Viable Train A |
| In-vivo data = silver | REJECT AS ABSOLUTE | Role profile-specifico |
| IAA 0.60 / 70% | REJECT AS FIXED | Threshold preregistrati |
| Governance pesante | ALREADY ADDRESSED | Lean levels preserved |
| Metriche troppe | PARTIAL | Five executive + diagnostics |

# Appendice X - Bootstrap Core, Core Semantic Kernel e profili

## X.1 Core Semantic Kernel - profile invariant

- `InferentialQuery` e claim identity;
- `KnowledgeState`;
- source class, authority type, evidence basis, support grade;
- `DerivedClaim` e claim-specific DeterminabilityState;
- `ReportResolutionState`;
- `DesignAdequacyFinding` separato;
- canonical counts e scope;
- scenario coverage;
- sensitivity;
- profile coverage;
- provenance, versions e RuleChallenge.

## X.2 Bootstrap Core required-or-unknown

- Experiment Block;
- sources/evidence;
- units/core relations;
- factor/levels;
- endpoint/contrast/query;
- assignment/application;
- event timing;
- source preparation;
- assignment separability;
- key counts;
- missing predicate/question;
- derived claims.

## X.3 Full Scientific Record additions

Lifecycle, multiple factors/endpoints, exclusions, planned/executed, conflicts, authority/support, analysis provenance, causal/exposure/measurement context e extensions.

## X.4 Profile contract

Ogni profilo dichiara vocabulary, theory clauses, decisive predicates, supported topologies, known gaps, migrations, real gold e challenge dedicati.

# Appendice Y - Causal, Exposure e Measurement Context Reference

| Component | Domanda | Stato |
|---|---|---|
| Assignment event | Quale unità poteva ricevere livelli diversi, come e quando? | explicit/candidate/unknown |
| Application event | Dove è stato materialmente applicato l'intervento? | explicit/candidate/unknown |
| Exposure pathway | Come si realizza e si propaga l'esposizione? | explicit/candidate/unknown |
| Effective exposure cluster | Quali unità condividono necessariamente l'esposizione? | explicit/candidate/unknown |
| Interference | Unità altrui possono modificarne l'outcome? | no_known_path/possible/documented/unknown |
| Biological source | Quale provenance e diversità biologica? | explicit/limited/unknown |
| Comparability basis | Quale evidenza sostiene il confronto? | supported/partial/contradicted/unknown |
| Estimand | Quale effetto è di interesse? | explicit/unknown |
| Inference scope | A quale popolazione/livello generalizzare? | explicit/limited/unknown |
| Measurement process | Come sono generati gli oggetti/feature e correlati gli errori? | explicit/partial/unknown |

N-Truth registra e controlla queste informazioni; non identifica automaticamente effetti causali.

## Y.1 Consequence classes

Interference/exposure può:

- non cambiare il claim EU ma limitare estimand/scope;
- rendere conditional il claim di esposizione;
- identificare un exposure cluster più grande;
- bloccare una direct-effect interpretation;
- richiedere modello di esposizione specialistico.

Non esiste la regola universale “interference => EU più grande”.

# Appendice Z - Real Anchor Acquisition Portfolio

| Canale | Autorità potenziale | Uso iniziale | Rischio |
|---|---|---|---|
| Prospective lab | Alta | allocation/source gold | adozione/consenso |
| OA expert annotation | Alta dopo adjudication | Parser/Derivation Gold | costo |
| Core facility | Alta dopo governance | metadata/provenance | privacy |
| Teaching-derived | Candidate | training support dopo review | semplicità/qualità |
| Author confirmation | Alta per fatti locali | ambiguity resolution | non scalabile |
| Cross-domain dataset | Profilo-specifica | auxiliary/challenge/profile | transfer mismatch |

# Appendice AA - Implementation Status Snapshot, 6 agosto 2026 - non normativo

- Granite backend and provider abstraction: engineering implemented.
- Artifact-bound runtime registry: engineering implemented; exact-artifact status only.
- Stage-level structured decoding: approved engineering integration; syntax-only smoke; not semantically qualified.
- Public dataset pipeline: repaired and verified; SourceData/PreClinIE/CRAFT auxiliary; MeasEval acquired/processed but not training-ready; license scope decisions remain asset-specific.
- Derivation Theory v8: normative PRD requirement; implementation migration not yet implied by this document.
- Substantive LoRA: `HOLD_PENDING_REAL_ANCHOR`.
- Scientific validation: `NOT_STARTED`.
- Annotation protocol: draft; human second review of first real trial remained pending at the last recorded project snapshot.
- Granite default promotion: HOLD.
- Cluster 3B/B4 expansion: requires separate authorization and v8 contract migration.

Questo snapshot non modifica i requisiti, non sostituisce il model registry e deve essere aggiornato separatamente dal PRD.

# Appendice AB - Changelog v7.0 preservato

## Added

Reality Gate, Human Authority Model, ConflictRecord, four independence dimensions, Causal Design Context, Bootstrap Core, Minimal Annotation Profile, Quick Design Session, Value-of-Abstention, Minimum Viable Train A, real-anchor portfolio, cross-domain policy, complexity tiers and decisive-edge definition.

## Changed

Roadmap re-ordered around real cases; metrics split executive/diagnostic; lifecycle counts moved to full record while Bootstrap Count Profile is smaller; crosswalk bounded; synthetic promotion clarified; Train A anti-deferral review added.

## Rejected as normative

Fixed 2-8 hour annotation estimate, fixed IAA/70% thresholds, automatic in-vivo-as-silver classification, `compliance: assumed` core field, automatic exchangeability, and any implication that causal effects are identified by the graph alone.

## Preserved

AI final objective, deterministic engine, human-in-the-loop, real gold, external challenge, graph-first synthetic, local-first, abstention, anti-leakage, no statistical washing, no certification and no public scorecard.

# Appendice AC - KnowledgeState e open-world semantics

| KnowledgeState | Valore richiesto? | Uso |
|---|---:|---|
| `PRESENT` | sì | valore osservato/dichiarato con supporto |
| `ABSENT_EXPLICIT` | no/empty | assenza dichiarata esplicitamente nello scope |
| `NOT_REPORTED` | no | le fonti ispezionate tacciono |
| `UNKNOWN` | no | non determinabile |
| `NOT_APPLICABLE` | no | non pertinente, rationale obbligatorio |
| `CONFLICTING` | lista valori | evidenze incompatibili |

Regole:

- bare null vietato;
- empty string vietata;
- empty list richiede state;
- `ABSENT_EXPLICIT` richiede evidence;
- `NOT_APPLICABLE` richiede claim/query scope e rationale;
- parser candidate non può convertire silenzio in `ABSENT_EXPLICIT`;
- migration da v7 mappa bare null a `UNKNOWN` o `NOT_REPORTED` soltanto mediante regole field-specific e audit.

# Appendice AD - Matrice di risposta alla critical review v7.0

| Finding | Valutazione v8 | Decisione |
|---|---|---|
| C1 derivation semantics assente | ACCEPT - CRITICAL | Derivation Theory, Theory Reference Set, non-circular decisiveness |
| C2 false certainty / confirmations | ACCEPT WITH MODIFICATION | claim-specific predicates, SupportGrade, Sensitivity; no new determinability enum |
| H1 interference inert | ACCEPT WITH MODIFICATION | consequences on exposure/estimand/scope; EU not automatically changed |
| H2 factor vs query scope | PARTIAL | assignment facts event/factor-specific; claims/counts query-specific |
| H3 no end-to-end evaluation | ACCEPT | final ReportBundle evaluation + residual audit |
| H4 pretraining contamination | ACCEPT | ContaminationAttestation |
| H5 cases vs clusters | ACCEPT WITH SCOPE | metric-specific generalization clusters |
| H6 scenario completeness | ACCEPT | ScenarioCoverage |
| H7 statistical strategy | ACCEPT | HANDOFF_ONLY + Strategy Reference Set |
| H8 null semantics | ACCEPT - FOUNDATIONAL | KnowledgeState |
| H9 determinability vs adequacy | ACCEPT | separate axes and neutral UX |
| M1 rule override | ACCEPT | RuleChallenge + re-derivation |
| M2 authority ranking | ACCEPT | orthogonal authority/evidence/support model |
| M3 count drift | ACCEPT | Canonical Count Registry |
| M4 timing referent | ACCEPT | event ID timing |
| M5 false certainty undefined | ACCEPT | operational event definition |
| M6 measurement model | ACCEPT PROFILE-GATED | MeasurementProcessContext |
| M7 IAA/human ceiling | ACCEPT WITH MODIFICATION | Reference stability |
| M8 prospective self-report | ACCEPT | consistency checks/support grade |
| M9 rule coverage caveat | ACCEPT | ProfileCoverageStatement |
| M10 invariant vs profile semantics | ACCEPT | Core Semantic Kernel |
| m1 feasibility inconsistency | ACCEPT | 100-150 harmonized |
| m2 package names drift | ACCEPT | current-to-target map |
| m3 exposure vocabulary | ACCEPT | pathway/container/cluster separation |
| m4 block boundaries | ACCEPT | boundary record |
| m5 DRIVER version | ACCEPT | snapshot/hash crosswalk |
| m7 rule/case arithmetic | ACCEPT | clause coverage/reuse explicit |
| m8 venue/year leakage | MODIFY | study/document/lab lineage; venue/year only covariates |
| m9 planned vs executed sheet | ACCEPT | source classes separated |
| m10 line provenance/NA | ACCEPT | SampleSheetSpec v8 |
| m11 multiplicity | ACCEPT AS NON-GOAL | explicit exclusion |

# Appendice AE - Migration map v7 -> v8

| Area v7 | Stato v8 | Migrazione |
|---|---|---|
| decisive field defined by output change | superseded | map to theory-versioned counterfactual decisive predicate |
| bundle-level DeterminabilityState | narrowed | create claim-level states + aggregate ReportResolutionState |
| green path | forbidden | neutral documentation-complete framing |
| linear authority ranking | superseded | source_class + authority_type + evidence_basis + support_grade |
| null/[] scientific fields | invalid | migrate to KnowledgeState wrapper |
| independent_n | deprecated alias | experimental_unit_count scoped to InferentialQuery |
| timing_relative_to_split | deprecated | event relation + reference_event_id |
| interference status annotation-only | expanded | exposure/estimand/scope claims |
| Derivation Gold only | expanded | Theory Reference Set + conformance + Derivation Gold |
| human ceiling | renamed/redefined | reference stability |
| stage-only evaluation | insufficient | end-to-end report evaluation + residual audit |
| external unseen | insufficient | ContaminationAttestation |
| candidate strategy families | restricted | HANDOFF_ONLY until Strategy Reference Set |
| target package layout presented as current | corrected | current-to-target architecture map |

## AE.1 Compatibility rule

Additive v8 migrations preserve raw evidence, graph history and human submissions. Derived claims are recomputed under the declared theory/rules version; old v7 outputs remain immutable historical artifacts.

# Appendice AF - DerivedClaim e ReportBundle contract

```yaml
derived_claim:
  claim_id: CLAIM-EU-001
  claim_type: EXPERIMENTAL_UNIT
  query_id: IQ-001
  value:
    knowledge_state: PRESENT
    unit_type: well
  determinability_state: DETERMINATE
  support_grade: SELF_REPORT_ONLY
  assumptions:
    - predicate_id: PRED-ASSIGN-SEPARABLE
      value: true
      authority_event_id: CONF-001
  theory_version: derivation-theory-0.1.0
  theory_clauses: [DT-EU-ASSIGNMENT-01]
  ruleset_version: ntruth-core-0.3.0
  rule_trace: [EU-WELL-001]
  sensitivity_records: [SENS-001]
  profile_coverage:
    status: COVERED_WITH_KNOWN_GAPS
    known_gaps: [interference_pathway_not_observed]
```

`ReportBundle` contiene:

- claims;
- report resolution;
- design adequacy findings;
- scenario sets/coverage;
- conflicts;
- sensitivities;
- questions;
- statistical handoff;
- profile coverage;
- epistemic boundary;
- provenance and versions.

# Appendice AG - External Challenge Contamination Attestation

```yaml
challenge_item_id: ECH-001
source_class: PROSPECTIVE_PRIVATE|POST_CUTOFF_PUBLIC|LEGACY_PUBLIC
publication_or_creation_date: 2026-09-01
study_family_id: SF-9001
training_eligible: false
model_selection_eligible: false
backbone:
  model_id: ibm-granite/granite-4.1-3b
  release_date: 2026-XX-XX
  documented_training_cutoff:
    knowledge_state: UNKNOWN
text_exposure_risk: LOW|MEDIUM|HIGH|UNKNOWN
exposure_assessment:
  evidence:
    - prospective_private_source
  probes_run: []
  residual_risk: LOW
permitted_claim:
  - project_pipeline_generalization
forbidden_claim:
  - proof_of_no_pretraining_exposure
custodian: external_or_independent
attested_by: reviewer_id
```

Un item `HIGH|UNKNOWN` può essere mantenuto come diagnostic set, ma non deve essere l'unica base di un claim di generalizzazione.

# Appendice AH - Changelog v8.0

## Added

Derivation Theory, Core Semantic Kernel, claim-specific determinability, DerivedClaim, ReportResolutionState, DesignAdequacyFinding, KnowledgeState, SupportGrade, SensitivityRecord, ScenarioCoverage, ProfileCoverageStatement, Theory Reference Set, RuleChallenge, MeasurementProcessContext, end-to-end validation, residual audit, cluster-aware precision planning e contamination attestation.

## Changed

- decisive predicate reso theory-relative e non circolare;
- authority model reso ortogonale;
- count vocabulary unificato;
- timing legato a event IDs;
- determinability separata da adequacy;
- interference resa operativa per claim senza auto-collassare EU;
- external challenge reso contamination-aware;
- statistical strategy module limitato a handoff;
- feasibility armonizzata a 100-150 casi;
- architecture section distinta fra target e implementation.

## Modified from review suggestions

- non tutte le dimensioni devono essere risolte per ogni claim: quelle irrilevanti sono esplicitamente N/A;
- nessuno stato `DETERMINATE_ON_SELF_REPORT`: SupportGrade e sensitivity preservano l'informazione;
- EU non diventa arbitrariamente endpoint/timepoint-specific; i claim e count sono query-specifici, l'assignment history resta event/factor-specific;
- lab/journal/year non sono leakage group universali.

## Preserved

AI final objective, deterministic engine, human-in-the-loop, real gold, external challenge, graph-first synthetic, local-first, abstention, anti-leakage, no statistical washing, no certification e no public scorecard.
