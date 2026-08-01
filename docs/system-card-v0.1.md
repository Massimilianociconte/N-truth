# N-Truth System Card v0.1

**Stato:** alpha deterministica in sviluppo; non è una release scientificamente
validata.

## Sistema

N-Truth è un compilatore locale del disegno sperimentale. La baseline importa
documenti, sample sheet e codice statistico read-only, costruisce candidate fact e un
grafo tipizzato, compila un target inferenziale e applica regole versionate. Il report
separa percorso positivo, alert, domande, ipotesi e limiti.

Il contratto v3 mantiene distinti:

- replicazione del disegno (`DESIGN_REPLICATION`);
- dipendenza analitica (`ANALYTICAL_DEPENDENCE`);
- portata dell'inferenza (`INFERENCE_SCOPE`);
- allocazione indipendente e applicazione fisica del fattore;
- unità sperimentale, osservazionale e analitica;
- `n` dichiarato, osservazionale, allocato, analizzato e indipendente;
- fatti strutturali, dichiarazioni dell'autore, metadata, codice statistico,
  conferme utente, inferenze del modello, fatti derivati e conflitti.

Il working tree supporta le tre classi a livello di schema, motore e UI. Tutte le 32
regole valorizzano esplicitamente `alert_class`: 10 design replication, 17 analytical
dependence e 5 inference scope. I test vietano il default implicito e congelano la
mappatura. La correttezza scientifica di ogni assegnazione resta da revisionare
esternamente.

Se i fatti decisivi mancano, il sistema si astiene o presenta scenari condizionali. Il
compilatore non sceglie una formula statistica, un test o una power analysis.

## Track A e Track B

La Track A deterministica è implementata nel working tree, ma la DoD v0.1 resta aperta
per fixture canoniche complete, revisione esterna, Experiment Bundle reali/pubblici e
prova CI cross-platform su una revisione candidata.

Per la Track B esiste un contratto parser AI con structured output e validazione, ma
non un backend attivo o un modello. Non sono disponibili gold, metriche ML,
calibrazione, risk-coverage o external challenge. Le correzioni restano candidate
annotations finché un processo umano non le promuove.

## Uso previsto iniziale

Supporto prospettico alla formalizzazione del disegno e supporto retrospettivo alla
revisione nel dominio iniziale di colture cellulari, esperimenti in vitro e microscopia
quantitativa. Ogni output va confrontato con la fonte; i fatti decisivi richiedono
conferma umana.

La checklist DRIVER-aligned è informativa e indipendente. Non è una valutazione di
conformità e non implica approvazione NC3Rs.

## Usi vietati

- Certificare validità, riproducibilità, conformità o integrità della ricerca.
- Accusare autori o ricercatori di frode o misconduct.
- Trasformare una dipendenza analitica o un limite di generalizzazione in una
  pseudoreplicazione del disegno senza evidenza.
- Trattare autovalutazioni come “independent experiments” come prova strutturale.
- Eseguire script R/Python importati o inviare dati a servizi cloud non dichiarati.
- Addestrare, condividere o redistribuire asset senza uso autorizzato e manifest.
- Usare la baseline per decisioni cliniche o su dati identificativi.

## Evidenza disponibile

Le fixture sintetiche e i test verificano contratti software, invarianti, regressioni,
sicurezza e comportamento offline. Non costituiscono un gold corpus, agreement umano,
validazione esterna, prova di accuratezza o verifica delle regole da parte di esperti.

## Failure mode noti

- Estrazione e coreference deterministiche possono perdere formulazioni non standard.
- PDF senza testo estraibile e OCR degradato richiedono un fallimento esplicito o una
  pipeline separata non ancora validata.
- Fonti contraddittorie restano irrisolte finché non interviene una persona.
- Il codice statistico descrive ciò che è stato modellato, non dimostra come il fattore
  è stato allocato.
- Il privacy scanner è euristico e non sostituisce revisione privacy/DPIA.
- Il flusso standard crea privacy scan e readiness negata per default; API/CLI possono
  autorizzare gli artefatti correnti dopo i gate, ma non trasferiscono file né creano un
  token persistente.
- Una scrittura di basso livello del solo report senza Document IR non scansiona le
  fonti e non dimostra readiness di distribuzione.
- Domini, specie, tecniche e lingue non valutati devono essere mostrati come fuori dal
  perimetro validato.

## Gate di rilascio

Prima di chiamare completa la v0.1 servono almeno 30 fixture canoniche complete,
revisione della classificazione/ruleset da wet-lab e biostatistica documentata e CI
cross-platform riuscita. Prima di
una release AI servono protocollo congelato, corpus autorizzato, agreement/human
ceiling, baseline, calibrazione e model card. Prima della v1.0 servono parser AI nel
flusso, external challenge, dominio dichiarato, rollback e riproducibilità verificata.
