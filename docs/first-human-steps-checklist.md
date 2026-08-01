# Checklist dei primi passi umani

**Stato:** piano operativo non ancora eseguito. Le caselle non costituiscono
approvazione, consenso o contatto già avvenuto.

## 1. Preparare il pacchetto di revisione

- [ ] Congelare commit/revisione, schema, ruleset, guideline e fixture da revisionare.
- [ ] Includere una sintesi di due pagine con obiettivo, anti-claim e tre classi di
  alert.
- [ ] Fornire dieci casi canonici leggibili senza aprire il codice sorgente.
- [ ] Per ogni caso mostrare fonti sintetiche, grafo, allocation/application,
  estimando, n, alert, alternativa e domanda minima.
- [ ] Evidenziare che fixture e output sono sintetici e non gold.
- [ ] Allegare il template `external-review-template.md` con campi ancora vuoti.
- [ ] Definire canale sicuro per eventuale materiale non pubblico; niente allegati
  sensibili via repository o issue pubblica.

## 2. Profili da coinvolgere

- [ ] Biostatistico/experimental design: definizioni, estimandi, regole, n e protocollo.
- [ ] Wet-lab in vitro/neurobiologia: processi reali, allocazione/applicazione e casi.
- [ ] Microscopia/core facility: file-to-sample mapping, immagini, pooling e pipeline.
- [ ] Data steward/privacy: licenze, permessi, minimizzazione, revoca e retention.
- [ ] NLP/ML: schema annotativo, structured output ed evaluation; non training precoce.

Una singola approvazione non sostituisce le competenze mancanti. Dichiarare conflitti
di interesse e indipendenza del reviewer.

## 3. Richiesta a basso carico

Per ridurre la barriera iniziale, proporre una sola attività delimitata:

- review di 10 casi in 30–45 minuti;
- review di 20–30 regole;
- condivisione di un template di sample sheet;
- indicazione di repository pubblici adatti;
- prova del prototipo su un esperimento;
- introduzione a un collega/dottorando.

Non chiedere subito un corpus di migliaia di casi o promettere authorship/benefici non
definiti.

## 4. Review scientifica iniziale

- [ ] Definizione di unità sperimentale per fattore.
- [ ] Separazione tra allocation e application.
- [ ] Distinzione EU/OU/AU e n declared/allocated/analyzed/observational/independent.
- [ ] Campi minimi dell'estimando.
- [ ] Separazione tra design replication, analytical dependence e inference scope.
- [ ] Condizioni di astensione e scenari condizionali.
- [ ] Trattamento delle author assertion.
- [ ] Codice statistico come declared clustering, non prova di allocation.
- [ ] Linguaggio del percorso verde e degli alert non accusatorio.
- [ ] Limiti e mapping DRIVER non certificante.

Registrare per ogni punto: accettato, modifica richiesta, bloccante o fuori scope, con
rationale e riferimento al caso/regola.

## 5. Experiment Bundle da richiedere

Per 5–20 esperimenti, quando possibile:

- Methods o breve descrizione;
- caption pertinente;
- schema gruppi;
- sample sheet;
- mapping file-campione;
- conteggi ai diversi livelli;
- allocation e application dichiarate;
- endpoint, contrasto ed effetto target;
- codice o descrizione statistica;
- risposta esperta su unità, n e limiti;
- autorizzazione d'uso esplicita.

Le immagini grezze non sono richieste salvo necessità di provenance approvata.

## 6. Intake e governance per ogni contributo

- [ ] Proprietario/responsabile e referente autorizzato.
- [ ] Stato pubblico/non pubblico e fonte primaria.
- [ ] File inclusi e checksum.
- [ ] Licenza o prova dell'autorizzazione.
- [ ] Usi separati: analyze, annotate, train, share, redistribute.
- [ ] Rimozione/verifica di identificatori e metadata sensibili.
- [ ] Embargo, retention, scadenza e possibilità di revoca.
- [ ] Modalità di riconoscimento/attribuzione.
- [ ] Split previsto e gruppi anti-leakage.
- [ ] Nessun upload/cloud senza autorizzazione specifica.

Un sì a “analisi locale” non equivale a sì per training o redistribuzione.

## 7. Calibration e pilot

Prima del pilot:

- [ ] completare 30 calibration cases fuori dal test;
- [ ] farli annotare indipendentemente da wet-lab e statistico;
- [ ] misurare disagreement per unità, allocation, determinabilità e grafo;
- [ ] correggere schema/guideline senza guardare il test futuro;
- [ ] congelare protocollo, metriche e redirect criteria.

Pilot:

- [ ] 150–250 bundle con 100% doppia annotazione;
- [ ] IAA prima dell'adjudication;
- [ ] adjudication di tutti i disaccordi;
- [ ] human ceiling e determinability rate stratificati;
- [ ] disagreement taxonomy e carico annotativo documentati;
- [ ] test/pilot congelato non usato per training.

## 8. Gate di training

Non avviare fine-tuning finché anche una sola voce è aperta:

- [ ] schema stabile su almeno 20 disegni reali;
- [ ] regole principali revisionate;
- [ ] parser few-shot valido rispetto allo schema;
- [ ] guideline distingue fatti, assertion e inferenze;
- [ ] protocollo del pilot congelato;
- [ ] manifest e permessi `train` completi;
- [ ] split senza leakage dimostrabile.

## 9. Evidenze da conservare

- review compilata e versione dei materiali;
- issue/disagreement log e disposition;
- manifest/checksum senza includere dati sensibili;
- protocollo congelato e deviazioni;
- decisione esplicita su readiness o redirect.

Un template vuoto, una email inviata o un incontro svolto non equivalgono a revisione
completata. La DoD si chiude soltanto con evidenza compilata e verificabile.
