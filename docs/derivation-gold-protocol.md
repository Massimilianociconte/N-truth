# Derivation Gold Protocol v0.1-draft

Stato: **bozza preregistrabile, non eseguita e non approvata**. Il protocollo separa
la correttezza del motore deterministico dalla correttezza del parser. Il suo owner
scientifico deve essere un biostatistico; la conferma della topologia biologica
richiede anche un reviewer wet-lab.

## 1. Oggetto della valutazione

Il Derivation Gold prende in ingresso un grafo già confermato e valuta soltanto:

- `DeterminabilityState` atteso;
- unità sperimentale e `independent_n` attesi per fattore/contrasto/scope;
- lifecycle count e attrition attesi;
- classi di output e astensioni;
- rule result, proof trace, severity, eccezioni e domande minime;
- invarianti hard e policy degli output.

Non misura NER, relation extraction, coreference o recupero degli evidence span. Il
Parser Gold resta un corpus e un target separato.

## 2. Record minimo

Ogni caso deve contenere:

```text
case_id, bundle_id, graph_schema_version, ontology_version,
ruleset_id, ruleset_version, ruleset_checksum,
confirmed_graph, expected_determinability,
expected_outputs_by_scope, expected_rule_evaluations,
expected_proof_trace, expected_questions,
exceptions, reviewer_roles, adjudication_status,
source_hashes, record_hash, created_at, approved_at
```

Gli output attesi devono distinguere `null`, `UNKNOWN`, `NOT_REPORTED`, bounds e
valori esatti. Ogni `n` deve includere unit type, fattore, contrasto, gruppo,
endpoint, timepoint/lifecycle e condizioni. Il record non può includere identità
personali dei reviewer: si conserva il ruolo e un riferimento locale non pubblico.

## 3. Costruzione e revisione

1. Congelare schema, ontologia, Core Profile e ruleset.
2. Creare o importare il grafo senza usare l'output del motore come gold.
3. Far confermare la struttura biologica al reviewer wet-lab.
4. Far compilare gli output attesi a un biostatistico indipendente.
5. Eseguire il motore soltanto dopo il congelamento del target.
6. Registrare ogni differenza come errore del record, del ruleset o del motore.
7. Adjudicare senza sovrascrivere le submission originali.
8. Calcolare hash e pubblicare una nuova versione immutabile del caso.

Chi implementa una regola non deve essere l'unico adjudicator dei casi che la
valutano. Un counterfactual deve modificare il minimo insieme di fatti decisivi e
conservare lo stesso `family_id` e split del caso sorgente.

## 4. Composizione iniziale e split

Il primo set pianificato comprende 30-60 fixture canoniche e 20-30 casi reali con
grafo confermato. Ogni regola critica richiede almeno tre casi reali e un
counterfactual. Articolo, supplementi, laboratorio, autori, versioni, repository e
famiglie sintetiche restano nello stesso leakage group.

Le fixture software esistenti possono essere candidate per il set canonico, ma non
diventano Derivation Gold finché non completano il workflow umano. Casi TEST ed
EXTERNAL non sono mai training eligible.

## 5. Metriche e report

Il report deve includere almeno:

- accuratezza esatta di stato, EU e `n` per scope;
- errori per regola, classe e severità;
- proof-premise precision/recall e rule coverage;
- percentuale di grafi validi e coperti da almeno una regola;
- distribuzione `DETERMINATE`, condizionale/multi-grafo, reporting gap e
  `OUT_OF_SCOPE`;
- violazioni dei count invariant e output proibiti;
- casi nuovi richiesti dal rulebook.

Se oltre il 50% dei casi reali è fuori profilo o indeterminato per pattern assente,
si restringe il claim o si amplia il rulebook con review; non si mascherano i veri
reporting gap.

## 6. Release gate

Una release è bloccata se una regola critica manca di reviewer esterno, il motore
emette un singolo `n` fuori dallo stato ammesso, `AUTHOR_ASSERTION` chiude la
determinabilità, effective sample size cambia una classe di disegno o il risultato
non è riproducibile dal grafo e dalle versioni registrate.

L'esecuzione effettiva, i nomi dei custodi, gli split e le soglie finali devono essere
congelati nel [Validation Protocol](validation-protocol-draft.md) prima dell'apertura
del test.

