# External Challenge Protocol v0.1-draft

Stato: **bozza non preregistrata; nessun challenge set esiste**. Il protocollo deve
essere congelato con un custode indipendente prima dell'apertura dei dati. Il set è
real-only e non può essere usato per training, calibrazione, prompt selection o
debugging.

## Scopo e unità di split

Il challenge misura generalizzazione a laboratori, tecniche, stili e bundle non visti.
Articolo, supplementi, preprint, dataset, repository, laboratorio, facility,
corresponding author e versioni appartengono allo stesso leakage group. Un caso con
qualunque sovrapposizione a train/dev/calibration viene escluso o mantenuto soltanto
come audit di contaminazione, mai come risultato principale.

## Eligibility

Ogni bundle richiede provenienza, checksum, diritto d'uso documentato, privacy review,
grafo/reference target adjudicato e conferma `synthetic=false`. Sono vietati dati
generati, parafrasi sintetiche, tavole illustrative, silver non adjudicato e casi usati
per modificare schema, rulebook o guideline.

Il manifest deve imporre:

```text
split=EXTERNAL_CHALLENGE
training_eligible=false
evaluation_eligible=true
custody_status=SEALED
```

## Custodia e apertura

Il custode conserva asset, identity mapping e gold in uno spazio separato. Il team
riceve prima soltanto schema, numero di casi, strata consentiti e checksum commitment.
Prima dell'apertura vengono congelati commit, modelli/adapters, prompt, ruleset,
threshold, calibration transform, metriche, subgroup e criteri di esclusione.

Ogni accesso registra ruolo, timestamp, motivazione e hash. Un errore operativo non
autorizza un secondo run selettivo: rerun e deviazioni vengono dichiarati e separati
dal risultato preregistrato.

## Metriche minime

- stato di determinabilità e coverage;
- EU e `independent_n` esatti per scope quando ammessi;
- decisive-edge precision/recall/F1;
- evidence-span precision/recall per artefatto;
- calibrazione/coverage-risk e abstention;
- errori hard, conflitti, OOD e overclaim;
- risultati per laboratorio/tecnica/stile, con intervalli compatibili col campione;
- human review time su un sottoinsieme preregistrato.

Parser e motore vengono riportati separatamente: il parser usa Parser Gold; il motore
usa il grafo confermato/Derivation Gold. Nessuna media aggregata può nascondere un
blocking error su output proibiti.

## Decisione

Gli esiti ammessi sono `GO`, `REVISE`, `LIMIT` e `STOP`. `LIMIT` restringe dominio o
claim in modo esplicito; `STOP` si applica a leakage, diritti non validi, overclaim
grave, output proibiti o impossibilità di audit. Soglie numeriche e dimensione finale
devono essere preregistrate dopo calibration/feasibility, non inventate in questa
bozza.

