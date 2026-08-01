# Validation Protocol — preregistration draft v3

**Stato:** template non preregistrato, non approvato e non eseguito. Deve essere
completato e congelato da biostatistico, wet-lab lead e evaluation custodian prima di
aprire qualsiasi test. Nessun numero in questo documento è un risultato N-Truth.

## 1. Obiettivi

Valutare separatamente:

1. coerenza e copertura dello schema;
2. correttezza del motore sulle fixture approvate;
3. agreement umano e determinabilità;
4. parsing/estrazione del parser AI candidato;
5. grafo, allocation/application, estimando e domande;
6. tre classi di alert;
7. selettività, calibrazione e astensione;
8. utilità e tempo per l'utente;
9. generalizzazione a laboratori e tecniche unseen.

## 2. Fasi e separazione dei dati

| Fase | Dimensione prevista dal PRD v3 | Uso |
|---|---:|---|
| Calibration set | 30 casi | scoprire ambiguità e correggere schema/guideline; escluso dal test |
| Feasibility pilot | 150–250 bundle | agreement, human ceiling, determinabilità e baseline |
| Research corpus | 1.200–2.000 bundle | training/ablation dopo i gate |
| External challenge | da definire prima dell'apertura | laboratori, tecniche e stili unseen |

Il pilot è 100% doppiamente annotato e tutti i disaccordi sono adjudicati. L'IAA viene
misurata prima dell'adjudication. La dimensione dell'external set, i domini, la
prevalenza e il criterio di successo devono essere congelati prima della valutazione;
non sono inventati in questa bozza.

Train, validation, test ed external sono separati per articolo, preprint/versione,
laboratorio/corresponding author quando possibile, dataset/supplementi collegati e
template sintetico. Synthetic è ammesso soltanto nel train/stress test. Il custode del
test non partecipa alla model selection.

## 3. Endpoint

| Livello | Endpoint da predefinire |
|---|---|
| Rule fixtures | pass rate per fixture completa e regressioni per regola/eccezione |
| Parsing | section/span/table accuracy e failure rate per formato |
| Evidence | classificazione tra structural fact, assertion, metadata, code, model e conflict |
| Entità/relazioni | strict/relaxed entity F1; micro/macro relation F1 |
| Grafo | node/edge F1, riferimenti validi, graph edit distance |
| Fattori | macro-F1 su `allocation_level` e, separatamente, `application_level` |
| Estimando | completezza/esattezza dei campi minimi per oggetto determinabile |
| Determinabilità | metriche per categorie e confusion matrix |
| n | exact match per gruppo/scope e correttezza degli scenari condizionali |
| Alert | precision/recall per `DESIGN_REPLICATION`, `ANALYTICAL_DEPENDENCE`, `INFERENCE_SCOPE` |
| Domande | capacità della domanda prioritaria di discriminare i grafi alternativi |
| Astensione | risk-coverage, selective accuracy, OOD e failure espliciti |
| Utente | correttezza del grafo/unità; tempo e carico come endpoint separati |

La severity non sostituisce la classe scientifica. Una valutazione di dipendenza
analitica non viene conteggiata come errore di replicazione del disegno.

## 4. Human ceiling

Riportare separatamente:

- accordo sui tipi di unità;
- accordo su `allocation_level` e `application_level`;
- accordo sugli estimandi;
- accordo sulla determinabilità;
- agreement graph-level;
- differenze tra annotatore wet-lab e statistico.

Per categorie fisse si possono usare accordo grezzo, confusion matrix, Cohen κ o
Krippendorff α con intervalli. Per grafi/nodi variabili servono F1 su archi, graph edit
distance o una metrica predefinita adatta allo schema. Non si riduce il pilot a un solo
coefficiente o kill-switch.

## 5. Baseline e confronti

Prima di aprire il test vanno congelati:

- baseline manuale/rules-only;
- eventuale baseline few-shot locale;
- modello candidato e policy di selezione;
- ablation text-only, table-only, code-only e combinazioni pertinenti;
- seed, versioni, snapshot del corpus e lockfile;
- test statistici, intervalli, molteplici confronti e missingness.

Il codice statistico è silver evidence del clustering dichiarato; una sua formula non
può essere valutata come gold dell'allocazione.

## 6. Criteri di redirect e stop

Il protocollo definitivo deve predefinire come cambiare il prodotto se il target non è
apprendibile. Il PRD v3 fornisce esempi da discutere e congelare:

- agreement su `allocation_level` inferiore a 0,60 → niente verdetti automatici;
- oltre il 60% dei casi pubblici insufficiente → enfatizzare elicitation e dati interni;
- mancato superamento della baseline → sospendere il fine-tuning e rivedere contratto;
- degrado external oltre soglia prestabilita → limitare la release al dominio validato.

Questi valori non sono metriche ottenute. Qualsiasi modifica successiva all'apertura
del test deve essere registrata come deviazione, non riscritta retroattivamente.

## 7. Blinding, custodia e reporting

- annotatori indipendenti prima dell'adjudication;
- test/external custoditi e non visibili durante l'iterazione;
- esclusioni e dati mancanti registrati per endpoint;
- error analysis stratificata per dominio, lingua, formato e determinabilità;
- report di disagreement taxonomy;
- risultati negativi, regressioni e limiti pubblicati insieme ai risultati positivi;
- nessuna valutazione principale sul sintetico;
- nessuna dichiarazione DRIVER/NC3Rs di conformità o endorsement.

## 8. Approvazioni e freeze

- [ ] Biostatistico lead.
- [ ] Wet-lab/domain reviewer indipendente.
- [ ] Annotation lead/adjudicator.
- [ ] Evaluation custodian.
- [ ] Data steward per licenze, autorizzazioni e revoca.
- [ ] Versioni congelate di schema, contratto parser, guideline, ruleset e ontologia.
- [ ] Snapshot corpus e leakage audit congelati.
- [ ] Endpoint, metriche, CI, redirect e dimensione external predefiniti.
- [ ] Registrazione o timestamp pubblico del protocollo prima del test.
