# Checklist dei primi passi umani - PRD v6

**Stato:** piano operativo non ancora eseguito. Le caselle vuote sono evidenze
mancanti, non attivita implicitamente completate. Una email, un template o un test
sintetico non equivalgono a consenso, review, gold, IAA o validazione.

**Regola di stop:** nessun fine-tuning scientifico finche Core Profile, guideline,
calibration, licenze, split, baseline e Resource Gate non sono documentati. Sono
ammessi sviluppo deterministico e smoke test sintetici dichiarati non scientifici.

## 1. Designare dati e autorita prima di acquisire

Per ogni asset o Experiment Bundle creare un record di designazione prima di copiarlo
in un corpus:

- [ ] `bundle_id`, versione e checksum delle fonti immutabili.
- [ ] Tipo: reale prospettico, reale retrospettivo, pubblico, silver, sintetico o
  counterfactual.
- [ ] Ruolo dataset: Rule Fixture, Derivation Gold, Parser Gold, silver auditato,
  synthetic augmentation o External Challenge.
- [ ] Autorita: source fact, candidate, single-reviewed, double-reviewed o adjudicated.
- [ ] Proprietario, referente autorizzato e data custodian.
- [ ] Licenza o permesso con usi distinti: analyze, annotate, train, share,
  redistribute.
- [ ] Stato privacy, identificatori rimossi, retention, embargo e revoca.
- [ ] `split=UNASSIGNED` finche lo split non e congelato.
- [ ] `training_eligible=false`, `evaluation_eligible=false` e
  `release_eligible=false` per default.
- [ ] Leakage group comprendente articolo, versioni/preprint, supplementi, dataset,
  laboratorio, facility, corresponding author, synthetic family e counterfactual.

Un permesso di analisi locale non autorizza training o redistribuzione. Un facsimile,
un PNG o un output del modello non diventa gold perche leggibile o plausibile.

## 2. Nominare ruoli, decision rights e Resource Gate

- [ ] Wet-lab reviewer stabile per preparazioni, provenance e indipendenza operativa.
- [ ] Biostatistico/metodologo per EU, DeterminabilityState, Rulebook e stop criteria.
- [ ] Annotation lead distinto dall'adjudicator sui casi critici.
- [ ] Data steward per licenze, consenso, privacy e revoca.
- [ ] ML/NLP reviewer per contratti, baseline e calibrazione; non per anticipare il
  training.
- [ ] Reviewer esterno con mandato scritto di `STOP` o `LIMIT`.
- [ ] Co-maintainer engineering/ML o PI host prima della feasibility.
- [ ] Laboratorio/facility partner e custode separato dell'external challenge.
- [ ] Registro di ore in-kind e budget low/expected/high.
- [ ] Conflitti di interesse e indipendenza dei reviewer dichiarati.

Il founder non puo essere contemporaneamente unico autore delle regole, unico
annotatore, unico adjudicator e unico decisore di release.

## 3. Preparare il pacchetto di review D0

- [ ] Congelare una revisione identificabile di schema, Core Profile,
  DeterminabilityState, SampleSheetSpec, Rulebook, guideline e fixture.
- [ ] Dichiarare il micro-dominio: colture cellulari, well plate, un fattore, due
  livelli, un endpoint e riferimenti prevalentemente espliciti.
- [ ] Mostrare separatamente allocation, application e operational independence.
- [ ] Includere conteggi lifecycle e quantificatori scope-aware.
- [ ] Includere almeno un caso per ciascuno dei sette stati di determinabilita.
- [ ] Mostrare evidence, assertion, alternative, conflitti, proof trace e domanda
  minima senza verdict del parser.
- [ ] Etichettare fixture, demo e confidence illustrative come non gold.
- [ ] Allegare il [template di review esterna](external-review-template.md) vuoto.

## 4. Bootstrap esplorativo: 10-20 bundle

Il PRD v6 usa 10-20 casi per verificare il micro-dominio e richiede 10-20 bundle
reali/pubblici nei primi novanta giorni. Sono esplorativi, non un test finale.

- [ ] Selezionare 10-20 bundle reali o pubblici con uso autorizzato.
- [ ] Preferire disegni monofattoriali semplici, includendo casi determinati,
  condizionali, conflittuali, insufficienti e out-of-scope.
- [ ] Per ogni bundle raccogliere, quando disponibili, Methods, caption, schema gruppi,
  sample sheet, mapping file-campione, endpoint, contrasto, eventi e codice read-only.
- [ ] Non richiedere immagini grezze se non necessarie e autorizzate.
- [ ] Far verificare rappresentabilita, campi mancanti e carico da wet-lab e
  biostatistico.
- [ ] Registrare ogni modifica dello schema richiesta dai bundle.
- [ ] Non assegnare questi bundle automaticamente a train, validation o test.
- [ ] Non chiamarli Parser Gold o Derivation Gold senza il workflow umano pertinente.

Gate bootstrap: procedere soltanto se il Core Profile rappresenta almeno venti disegni
reali senza modifiche sostanziali oppure registrare `REVISE/LIMIT` e restringere il
micro-dominio.

## 5. Review scientifica del nucleo

- [ ] Unita sperimentale per fattore e contrasto.
- [ ] `allocation_level` distinto da `application_level`.
- [ ] `independently_assigned=TRUE/FALSE/UNKNOWN` e meccanismo osservabile se `TRUE`.
- [ ] Randomization unit, source preparation, shared environment, confounding e timing
  dello split.
- [ ] Unita osservazionale, oggetto computazionale e unita analitica distinte.
- [ ] Conteggi planned/allocated/treated/observed/excluded/analysed/declared,
  observational/analytical/independent e biological source.
- [ ] Exclusion phase, prespecificazione, endpoint, gruppo, autore e impatto.
- [ ] `effective_n` solo diagnostico e nessun statistical washing.
- [ ] Tabella dei sette DeterminabilityState e output vietati.
- [ ] AUTHOR_ASSERTION mai sufficiente per chiudere la determinabilita.
- [ ] Parser Gold distinto da Derivation Gold.
- [ ] Linguaggio non accusatorio, no bulk-shaming e no certificazione DRIVER.

Per ogni punto registrare `ACCEPT`, `REVISE`, `BLOCK` o `OUT_OF_SCOPE`, con rationale,
versione e riferimento al caso/regola.

## 6. Costruire fixture e Derivation Gold prima del parser training

- [ ] Portare il catalogo a 30-60 fixture canoniche complete.
- [ ] Per ogni regola critica includere positivo, negativo, caso ambiguo/eccezione e
  counterfactual.
- [ ] Collegare precondizioni, output, proof trace, riferimento, reviewer, data e
  changelog.
- [ ] Ottenere almeno 20 casi reali/canonici con grafo confermato per il Derivation
  Gold.
- [ ] Includere almeno tre casi reali e un counterfactual per ogni regola critica,
  quando disponibili e autorizzati.
- [ ] Misurare coverage, DETERMINATE, conditional/multiple, reporting gaps e
  OUT_OF_SCOPE senza mascherare le astensioni.

Gli scenari software esistenti verificano contratti, ma non sostituiscono questo gate.

## 7. Calibration pilot: 30-50 casi

Prima di iniziare:

- [ ] Guideline, schema Core, ruoli e modulo di designazione versionati.
- [ ] Due annotatori indipendenti: wet-lab e figura con formazione statistica.
- [ ] Ordine dei casi randomizzato e annotatori ciechi alle decisioni reciproche.
- [ ] Eligibility false e split non definitivo durante la calibration.
- [ ] Metriche, missingness e disagreement taxonomy dichiarate in anticipo.

Esecuzione:

- [ ] Annotare 30-50 casi reali con Core Profile obbligatorio.
- [ ] Doppiare i campi decisivi: allocation, independently assigned, critical edge e
  sufficient evidence/determinability.
- [ ] Misurare minuti per campo, annotazione primaria, seconda review e adjudication.
- [ ] Calcolare IAA **prima** dell'adjudication, riportando prevalence, UNKNOWN e
  `INSUFFICIENT_INFORMATION` senza fondere missingness e determinabilita.
- [ ] Usare metriche per campo e decisive-edge agreement; non ridurre tutto a un
  singolo kappa.
- [ ] Adjudicare tutti i disaccordi critici con rationale e delta dalle submission.
- [ ] Misurare la distribuzione dei sette stati e il tasso out-of-scope.
- [ ] Valutare un campione di domande per answerability, output-changing, ridondanza e
  tempo.
- [ ] Registrare il budget annotativo empirico low/expected/high.

Durante la calibration schema e guideline possono cambiare; per questo il set non e
un test finale congelato.

## 8. Freeze dopo la calibration

- [ ] Correggere schema, guideline, Rulebook e question templates senza consultare il
  futuro test/external.
- [ ] Congelare versioni di Core Profile, stage contracts, guideline, ruleset e
  ontologia.
- [ ] Congelare protocollo, endpoint, metriche, intervalli e redirect criteria.
- [ ] Congelare split e leakage groups a livello di bundle/famiglia.
- [ ] Nominare evaluation custodian e limitare accesso a test/external.
- [ ] Congelare baseline B0-B5 e policy di selezione.
- [ ] Registrare una decisione `GO`, `REVISE`, `LIMIT` o `STOP` firmata dal reviewer
  esterno.
- [ ] Documentare ogni modifica successiva come deviazione, non riscrittura
  retroattiva.

## 9. Feasibility pilot: 100-150 casi

Il corpo del PRD v6, la roadmap e la DoD indicano 100-150; l'Appendice D.2 riporta
150-250. Fino a erratum formale si usa **100-150**, come documentato nella
[riconciliazione](prd-v6-reconciliation.md#21-erratum-aperto-sulla-dimensione-della-feasibility).

- [ ] Resource Gate superato: LOI/ore, budget, co-maintainer/PI host, laboratorio e
  custode disponibili.
- [ ] Protocollo e guideline congelati prima di aprire i casi custoditi.
- [ ] 100% doppia annotazione sui campi decisivi.
- [ ] 100% doppia sul test e sui nuovi domini.
- [ ] Full double annotation su campione stratificato; per eventuale training futuro,
  target PRD 25-40%.
- [ ] Adjudicator esterno sul campione previsto e su tutti i disaccordi critici.
- [ ] IAA e human ceiling calcolati prima dell'adjudication.
- [ ] Baseline B0-B5, ruleset coverage, anti-shortcut e decisive-coreference set.
- [ ] Learning curve e person-hours per decidere se 100-150 sono informativi.
- [ ] Real-only, synthetic-only e hybrid soltanto su split autorizzati; nessun
  generator access al test.
- [ ] Decisione finale `GO/REVISE/LIMIT/STOP` con failure modes e limiti pubblicabili.

## 10. Gate assoluto prima del fine-tuning

Non avviare training scientifico se una voce e aperta:

- [ ] Core Profile stabile su almeno venti disegni reali.
- [ ] Operational Independence Policy e regole principali revisionate.
- [ ] Derivation Gold sufficiente a separare errori del motore e del parser.
- [ ] Guideline distingue fatti, assertion, inferenze, candidate e adjudicated gold.
- [ ] Calibration 30-50 completata con IAA e decisione formale.
- [ ] Output strutturato e hard verifier valutati semanticamente.
- [ ] Baseline B0-B5 eseguite sullo stesso snapshot.
- [ ] Licenze, consenso, privacy e autorizzazione `train` complete per ogni asset.
- [ ] Split e leakage audit dimostrabili; TEST/EXTERNAL training-ineligible.
- [ ] Budget annotativo, compute, storage e checkpoint policy disponibili.
- [ ] Resource Gate e STOP authority attivi.

Se B6 non supera B5 sui task decisivi o non riduce il tempo di revisione, non diventa
il default. Questo limita la release AI, non cancella il Train A come obiettivo di
ricerca.

## 11. Evidenze da conservare

- record di designazione, manifest, checksum e versioni;
- review firmate e decision log;
- due submission indipendenti, IAA pre-adjudication e rationale finale;
- disagreement taxonomy, tempi e budget;
- snapshot, split, leakage audit e access log del custode;
- protocollo congelato e deviazioni;
- risultati negativi, regressioni e limiti;
- documento GO/REVISE/LIMIT/STOP.

La DoD si chiude solo con evidenza compilata e verificabile. Il repository puo
preparare i contratti, ma non puo produrre da solo review, consenso, agreement o
validazione esterna.
