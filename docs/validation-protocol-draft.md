# Validation Protocol — preregistration draft (rev. v6)

> **HISTORICAL_NON_NORMATIVE.** Questo documento è la revisione v6 di una bozza
> nata dal PRD v3; non è il protocollo v8 e le sue numerosità non sono correnti,
> preregistrate o approvate. Il repository v8 non ha avviato validazione scientifica.
> Vedere
> [prd-v8-data-training-evaluation-boundary.md](prd-v8-data-training-evaluation-boundary.md)
> e il [Scientific Review Register](audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md).

**Stato:** bozza non preregistrata, non approvata e non eseguita. Deve essere
completata, firmata e congelata da biostatistico, wet-lab lead, annotation lead ed
evaluation custodian prima dell'apertura di test o external challenge. Nessun numero
in questo documento e un risultato N-Truth.

**Training status:** vietato in questa fase. La pipeline software e gli smoke test
sintetici non autorizzano fine-tuning scientifico, model selection o claim di
prestazione.

## 1. Obiettivi e domande decisionali

Valutare separatamente:

1. rappresentabilita e stabilita del Core Profile nel micro-dominio;
2. accordo umano sui campi decisivi e sul supporto probatorio;
3. correttezza del motore su grafo confermato, cioe Derivation Gold;
4. prestazioni del parser candidato da fonti a grafo, cioe Parser Gold;
5. hard verification, semantic verification mirata e false certainty;
6. allocation, application e operational independence;
7. conteggi scope-aware, lifecycle, attrition e sette DeterminabilityState;
8. decisive coreference, procedural order, alternative graph e conflitti;
9. calibrazione, astensione, question usefulness e carico di correzione;
10. generalizzazione a laboratori, facility, tecniche e stili unseen.

Ogni fase termina con `GO`, `REVISE`, `LIMIT` o `STOP`. Completare codice o raggiungere
un numero nominale di casi non determina automaticamente `GO`.

## 2. Perimetro iniziale

Il bootstrap valuta soltanto il Core Profile D0:

- colture cellulari in well plate;
- un fattore primario;
- due livelli o un contrasto esplicito;
- un endpoint primario;
- riferimenti prevalentemente espliciti;
- TXT/Markdown e CSV semplice come input supportati D0.

Imaging avanzato, pooling complesso, split-plot, multifattore, organoidi/iPSC,
longitudinale complesso e formati post-stage sono sottogruppi esplorativi o
`OUT_OF_SCOPE`, non errori del Core. Un'espansione richiede un protocollo e un gate
separati.

## 3. Designazione dei dati

Prima dell'inclusione, ogni bundle deve registrare:

- identita, versione e SHA-256 delle fonti immutabili;
- reale prospettico/retrospettivo, pubblico, silver, synthetic o counterfactual;
- ruolo tra Rule Fixtures, Derivation Gold, Parser Gold, silver auditato, synthetic
  augmentation ed External Challenge;
- stato candidate, single-reviewed, double-reviewed o adjudicated;
- licenza/consenso e usi granulari analyze, annotate, train, share, redistribute;
- privacy, retention, embargo, revoca e custode;
- split ed eligibility separata per training, evaluation e release;
- leakage group completo;
- source class ed evidence coordinates.

I default sono `split=UNASSIGNED` e tutte le eligibility false. TEST ed
EXTERNAL_CHALLENGE implicano sempre `training_eligible=false`. Un record in quarantena
non riceve uno split definitivo.

## 4. Fasi e numerosita

| Fase | Casi reali previsti | Uso | Modifiche consentite |
|---|---:|---|---|
| Schema bootstrap | 10-20 | verificare micro-dominio, campi e carico | schema/guideline/rulebook modificabili |
| Calibration pilot | 30-50 | IAA, tempo, determinability, guideline e budget | correzioni consentite; non e test finale |
| Feasibility pilot | 100-150 | baseline B0-B5, learning curve, real dev/test e unit economics | protocollo congelato; deviazioni registrate |
| Restricted-domain expansion | 150-500 | eventuale fine-tuning e external validation guidati da learning curve | solo dopo tutti i gate |
| Research corpus | 800-2.000 | programma finanziato/consortile | fuori dal bootstrap |
| External challenge | da predefinire prima dell'apertura | release gate v1.0-A, esclusivamente reale e unseen | nessuna modifica dopo apertura |

### 4.1 Erratum operativo

Le sezioni 14.3, 17.4, 18.3, 28.5 e 32.4 del PRD v6 indicano 100-150 casi per la
feasibility; l'Appendice D.2 indica 150-250. Fino a correzione formale si adotta
**100-150**, per coerenza con il corpo, la roadmap e la DoD. La cifra deve comunque
essere riesaminata con learning curve, prevalence, precisione degli intervalli e
budget: non e una power calculation. Nessuna di queste cifre e un impegno
preregistrato.

Il pilot e 100% doppiamente annotato e tutti i disaccordi sono adjudicati. L'IAA viene
misurata prima dell'adjudication. La dimensione dell'external set, i domini, la
prevalenza e il criterio di successo devono essere congelati prima della valutazione;
non sono inventati in questa bozza.

Train, validation, test ed external sono separati per articolo, preprint/versione,
laboratorio/corresponding author quando possibile, dataset/supplementi collegati e
template sintetico. Synthetic e ammesso soltanto nel train/stress test. Il custode del
test non partecipa alla model selection.

## 5. Separazione Parser Gold / Derivation Gold

### 5.1 Derivation Gold: grafo -> conseguenze

Ogni item include:

- grafo confermato;
- DeterminabilityState;
- EU e conteggi attesi per fattore/contrasto, soltanto se ammessi;
- classi design/analytical/inference/reporting;
- proof trace, regole, eccezioni e severity;
- reviewer, versione e rationale.

Target iniziale: 30-60 fixture canoniche, 20+ casi con grafo confermato e, per ogni
regola critica, almeno tre casi reali e un counterfactual quando disponibili.

### 5.2 Parser Gold: artefatti -> grafo

Ogni item include:

- fonti autorizzate;
- evidence span e coordinate;
- entita, conteggi, quantificatori ed eventi;
- operational-independence fields;
- candidate e adjudicated graph distinti;
- alternative, conflitti e missing predicates;
- due submission e adjudication sui campi previsti.

`GoldParserTarget` è il wrapper adjudicato e non va confuso né con il legacy
`ParserAIOutput` né con il `CandidateGraphSet` a autorità `model` esportato per il
training. Il verifier non promuove un candidato a gold.

## 6. Campionamento, split e anti-leakage

Prima di congelare gli split, costruire gruppi indivisibili che comprendano:

- articolo, correzioni, preprint e versioni;
- supplementi e sample sheet;
- repository/dataset/accession e mirror;
- laboratorio, facility e corresponding author quando identificabili;
- template, prompt o renderer sintetico;
- `synthetic_family_id` e `counterfactual_family_id`.

Train, validation, test ed external devono essere disgiunti per gruppo, non per frase o
file. Il generator e chi esegue model selection non accedono al test/external. Il
custode del test non partecipa alla scelta del modello. Parafrasi e viste dello stesso
grafo restano nello stesso split.

## 7. Annotazione, blinding e adjudication

### 7.1 Calibration 30-50

- due annotatori indipendenti, wet-lab e statistico/metodologico;
- Core Profile obbligatorio;
- doppia sui campi decisivi;
- ordine randomizzato e nessuna visibilita della submission altrui;
- tempo per campo e per ruolo;
- disagreement taxonomy;
- adjudication con rationale dopo il calcolo dell'IAA.

### 7.2 Feasibility 100-150

- 100% doppia su allocation, independently assigned, critical edge,
  sufficient-evidence e determinability;
- 100% doppia sul test e sui nuovi domini;
- full double annotation su campione stratificato;
- per l'eventuale training futuro, 25-40% full-double come target iniziale;
- adjudicator esterno sul 10-20% complessivo e su tutti i disaccordi critici;
- resto con annotazione primaria e audit, se predefinito dal protocollo.

L'IAA viene calcolata prima dell'adjudication. Reviewer confidence puo essere raccolta,
ma non sostituisce agreement, evidence e rationale.

## 8. Inter-annotator agreement e human ceiling

Riportare almeno:

- accordo grezzo e prevalence per categorie fisse;
- gestione esplicita di `UNKNOWN`, `NOT_REPORTED` e
  `INSUFFICIENT_INFORMATION`, senza trattarli come sinonimi;
- Cohen kappa o Krippendorff alpha solo dove appropriati;
- evidence-span overlap/F1;
- decisive-edge precision, recall e F1;
- agreement su allocation e application separatamente;
- agreement su `independently_assigned` e independence mechanism;
- agreement su sufficient evidence e candidate graph set;
- graph edge agreement o metrica predefinita, non un solo coefficiente;
- differenze wet-lab vs biostatistico;
- intervalli di incertezza e missingness.

Il DeterminabilityState finale e derivato dalla tabella normativa dopo i fatti, poi
revisionato. Non e una label impressionistica scelta liberamente.

## 9. Endpoint del motore deterministico

| Endpoint | Misura da congelare |
|---|---|
| Fixture | pass rate per positivo, negativo, ambiguous/exception e counterfactual |
| Derivation Gold | accuratezza EU/n per fattore/contrasto e per stato ammesso |
| Determinabilità | confusion matrix sui sette stati e false-certainty rate |
| Count invariants | lifecycle, scope, quantificatore, exclusion ed effective_n diagnostic-only |
| Rule coverage | covered, determinate, conditional/multiple, reporting gap, out-of-scope |
| Proof trace | completezza e correttezza di precondizioni/evidence/rule ID |
| Classi | separazione tra design replication, analytical dependence e inference scope |

La severity non sostituisce la classe scientifica. Una valutazione di dipendenza
analitica non viene conteggiata come errore di replicazione del disegno.

Il 100% sulle fixture approvate e necessario ma non sufficiente. Se oltre il 50% dei
casi reali e OUT_OF_SCOPE o indeterminato per pattern non coperti, restringere il
profilo o ampliare il Rulebook con review; non forzare un verdetto.

## 10. Endpoint del parser e del verifier

| Task | Endpoint primario |
|---|---|
| Routing/block detection | block precision/recall e chunk coverage |
| Evidence | span F1 e source-coordinate validity |
| Entita/count | strict/relaxed entity F1, count/quantifier exactness |
| Relazioni | micro/macro F1, con decisive-edge F1 primario |
| Allocation/application | F1 separati |
| Operational independence | tri-state accuracy e mechanism support |
| Coreference | antecedent selection e decisive-coreference F1 |
| Procedural order | event-order e split-before/after-treatment accuracy |
| Candidate graphs | scenario-set accuracy; exact graph match secondario |
| Conflitti | precision/recall e source retention |
| Astensione | risk-coverage, selective accuracy e OOD failure esplicito |
| Revisione | correction count e time-to-confirmed-graph |

### 10.1 Hard verifier

E sempre attivo e misura:

- schema/JSON validity;
- referential e type integrity;
- count invariants;
- cicli vietati e timeline impossibili;
- evidence anchor mancanti;
- split/eligibility coherence;
- facts non supportati;
- matrice DeterminabilityState -> output.

### 10.2 Semantic verifier

E un passaggio indipendente, attivato soltanto su allocation/application a bassa
confidenza, decisive coreference, conflitti, grafi che cambiano EU/n o altri output ad
alto impatto. Riportare trigger rate, agreement/disagreement col generatore, errori
corretti e falsi blocchi. Lo stesso modello non puo essere unico generatore e giudice.

## 11. Baseline e model-selection policy

Congelare prima del test:

- B0 regex/dizionari/table parser;
- B1 encoder NER/section classifier;
- B2 relation/coreference classifier;
- B3 pipeline modulare;
- B4 LLM locale few-shot con schema;
- B5 cascata ibrida;
- B6 fine-tuned/distilled, soltanto dopo i gate.

Stesse fonti, split, metriche, seed, config, snapshot, lockfile e budget per ogni
confronto. B6 diventa default solo se supera B5 su allocation/application,
decisive-edge F1, astensione, calibrazione o riduce significativamente il tempo di
revisione. Exact graph match non puo compensare errori sui campi decisivi.

Il codice statistico e silver evidence del clustering dichiarato; una sua formula non
puo essere valutata come gold dell'allocazione.

## 12. Question usefulness

Nel primo pilot valutare un campione di circa 50 domande. Due esperti in cieco
registrano:

- answerability 0/1;
- rilevanza 1-5;
- scenario resolved 0/1;
- output-changing 0/1;
- ridondanza 0/1;
- destinatario corretto;
- tempo di risposta.

Le domande iniziali provengono da template legati a missing predicates e devono
esplicitare gli scenari. Information gain e generazione free-form restano secondari
finche non esiste un prior affidabile.

## 13. Synthetic augmentation

Synthetic e train/stress-test only. Non entra in calibration principale, test o
external. Ogni lotto deve avere Design DSL/versione, seed, family, lineage, hard
validation, round-trip, dedup e contamination scan.

Confrontare sul development reale:

- real-only;
- synthetic-only;
- silver+real;
- synthetic+real;
- hybrid.

Riportare TSTR, hybrid uplift, synthetic-to-real gap, shortcut sensitivity,
calibrazione, human-review time, long-tail coverage e rejection rate. Almeno 50
realizzazioni stratificate per ciclo devono ricevere audit umano. Nessuna percentuale
di synthetic e fissata a priori e nessun self-training ricorsivo non auditato e
ammesso. Nessuna valutazione principale sul sintetico.

## 14. Resource e storage accounting

Per ogni fase registrare:

- minuti/ore per triage, primary annotation, second review e adjudication;
- licenze, curation e synthetic audit;
- costo equivalente per ruolo e seniority;
- ore donate/in-kind e capacita residua;
- RAM peak, latenza, token, cache e disco;
- snapshot compressi/estratti, modello base, adapter, checkpoint e output.

Dopo calibration pubblicare budget low/expected/high. Prima della feasibility servono
almeno una LOI con ore mensili o budget equivalente, co-maintainer/PI host, laboratorio
partner e data custodian. In loro assenza la decisione e `LIMIT` o `STOP`.

## 15. Redirect e stop criteria

Da ratificare prima dell'apertura:

- allocation agreement <0,60 -> parser limitato a candidate facts ed elicitation;
- B6 non supera B5 -> B6 non diventa default;
- synthetic peggiora real development o calibrazione -> ridurre/sospendere synthetic;
- external degradation oltre soglia prestabilita -> restringere dominio e claim;
- ruleset coverage insufficiente -> ampliare il Rulebook o restringere il profilo;
- assenza di LOI/budget/STOP authority -> non avviare feasibility estesa;
- leakage, gold senza provenance o TEST training-eligible -> invalidare snapshot/run;
- false certainty o EU/n fuori dalla tabella normativa -> release blocker.

Questi valori sono criteri candidati, non risultati ottenuti. Le soglie finali, gli
intervalli e la gestione della molteplicita devono essere approvati dal biostatistico.
Qualsiasi modifica successiva all'apertura del test deve essere registrata come
deviazione, non riscritta retroattivamente.

## 16. Freeze, custodia e reporting

Prima della feasibility:

- [ ] schema, Core Profile, guideline, Rulebook e stage contracts congelati;
- [ ] protocollo, endpoint, CI, redirect e missingness congelati;
- [ ] snapshot, split, leakage groups e checksum congelati;
- [ ] baseline, seed, config e policy B5/B6 congelati;
- [ ] custode e access policy di test/external nominati;
- [ ] redirect/stop criteria e Resource Gate firmati;
- [ ] timestamp pubblico o preregistrazione eseguiti.

Il report finale include risultati negativi, error taxonomy, disagreement taxonomy,
subgroup per dominio/lingua/formato/determinabilita, risorse, deviazioni e limiti.
Nessuna dichiarazione DRIVER/NC3Rs di conformita o endorsement, nessuna scorecard
nominativa e nessuna conclusione principale su synthetic.

## 17. Approvazioni richieste

- [ ] Biostatistico/metodologo lead.
- [ ] Wet-lab/domain reviewer indipendente.
- [ ] Annotation lead.
- [ ] Adjudicator esterno.
- [ ] Evaluation custodian.
- [ ] Data steward/licence owner.
- [ ] ML/engineering lead.
- [ ] Reviewer con autorita di STOP.

Fino alla compilazione di queste approvazioni, il documento resta una bozza di lavoro e
non autorizza raccolta non pubblica, apertura del test, training o release.
