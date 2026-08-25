# Data Management Plan — draft v0.2 / PRD v6

> **HISTORICAL_NON_NORMATIVE.** Questa bozza PRD v3 non autorizza acquisizione o uso
> di dati nel contratto v8. Vedere [../GOVERNANCE.md](../GOVERNANCE.md),
> [privacy-dpia-screening.md](privacy-dpia-screening.md) e
> [prd-v8-data-training-evaluation-boundary.md](prd-v8-data-training-evaluation-boundary.md).

**Stato:** bozza operativa; richiede approvazione del data steward prima di acquisire dati reali.

## Scopo e minimizzazione

Il core usa soltanto Methods, caption, schema gruppi, sample sheet, mapping file-campione,
metadata e codice statistico necessari a ricostruire il disegno. Le immagini grezze non sono
richieste nel pilot salvo necessità di provenance approvata. Dati clinici identificabili e
genomica individuale sono esclusi per default. Nomi, email, path locali e codici campione non
necessari devono essere rimossi prima dell'intake; la pseudonimizzazione non equivale ad
anonimizzazione.

## Classi di dati

| Classe | Esempio | Default | Condizione di uso |
|---|---|---|---|
| Pubblico Tier A | JATS CC0/CC BY verificato per articolo | ammesso | manifest completo e checksum |
| Condizionale Tier B | studio con licenza specifica | bloccato | revisione scritta per singolo asset |
| Interno autorizzato A | caso di laboratorio | bloccato | accordo, minimizzazione e usi separati approvati |
| External test B | caso unseen privato | isolato | custode del test; metriche aggregate |
| Demo C | caso supervisionato | non riusabile | nessun training o pubblicazione |
| Escluso Tier C | paywall, licenza ignota, dati personali non necessari | rifiutato | nessuna deroga automatica |

## Manifest obbligatorio

Ogni asset registra origine primaria, licenza o autorizzazione, evidenza, data di acquisizione,
checksum SHA-256, attribuzione, split, reviewer, scadenza/revoca e stato. Gli usi `analyze`,
`annotate`, `train`, `share` e `redistribute` sono concessi separatamente. Un asset incompleto non
entra nel training e non viene condiviso o redistribuito.

Ogni Experiment Bundle registra inoltre ruolo dei file, mapping file-campione, dichiarazioni
dell'autore separate da risposte esperte e hash del record di governance.

## Storage e accesso

- Workspace locale su volume cifrato; rete e telemetria disattivate per default.
- SQLite locale per manifest, revisioni e audit; blob immutabili deduplicati per SHA-256.
- Accesso minimo per ruolo; external test separato dagli ambienti di sviluppo.
- Log privi di contenuto scientifico e identificatori per default.
- Backup cifrati solo se autorizzati dall'accordo dati.
- Gli script statistici sono memorizzati/analizzati come testo e non vengono eseguiti.

## Retention e cancellazione

La data di review/cancellazione e obbligatoria negli accordi per dati non pubblici. La cancellazione
deve includere workspace, cache, backup autorizzati e copie di lavoro, preservando soltanto record
di audit non identificativi quando richiesto.

## Versioning e split

Snapshot content-addressed; correzioni tramite nuova versione. Split per articolo, progetto,
preprint/versione, laboratorio, facility, corresponding author, dataset/supplementi,
synthetic family e counterfactual. Synthetic solo nel train; test ed external challenge
congelati prima della model selection e mai training-eligible. Ogni run
registra automaticamente lockfile, codice, runtime, modello, profilo, seed e snapshot. Le
versioni di schema, contratto parser, guideline e ontologia devono essere fissate nel manifest
del dataset e conservate insieme al run.

## Gate aperti

- [ ] Data steward e owner nominati.
- [ ] License policy approvata.
- [ ] Retention e incident response approvati.
- [ ] Accordi per eventuali dati di laboratorio firmati dalle parti autorizzate.
- [ ] 10-20 Experiment Bundle reali/pubblici autorizzati disponibili per lo schema bootstrap D0.
- [ ] DPIA screening completato se entrano dati personali o categorie particolari.
