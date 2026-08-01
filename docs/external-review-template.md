# External scientific review — template

> Template vuoto. Non costituisce una review, approvazione scientifica, conformità
> DRIVER/NC3Rs o endorsement. Compilare una copia versionata senza pubblicare dati
> personali non necessari.

## A. Identificazione della review

| Campo | Valore |
|---|---|
| Review ID | `PENDING` |
| Data | `PENDING` |
| Revisione/commit del software | `PENDING` |
| Schema / ruleset / guideline | `PENDING` |
| Fixture/casi inclusi | `PENDING` |
| Ruolo del reviewer | wet-lab / biostatistico / microscopia / data steward / altro |
| Indipendenza e conflitti dichiarati | `PENDING` |
| Identità conservata in record sicuro separato | sì / no / non applicabile |

## B. Perimetro

Selezionare ciò che è stato realmente esaminato:

- [ ] definizioni scientifiche;
- [ ] schema e vocabolario;
- [ ] fixture canoniche;
- [ ] ruleset e trace;
- [ ] output condizionale di n;
- [ ] Methods statement/percorso verde;
- [ ] UI di correzione;
- [ ] protocollo annotativo/validazione;
- [ ] governance/licenze/privacy;
- [ ] altro: `PENDING`.

Materiale non esaminato: `PENDING`

## C. Checklist scientifica

Per ogni riga usare `accepted`, `change_requested`, `blocking`, `out_of_scope` e
aggiungere un rationale con riferimento a caso/regola/evidenza.

| Oggetto | Esito | Rationale/riferimento |
|---|---|---|
| Unità sperimentale relativa al fattore/contrasto | `PENDING` | |
| Allocation e application non fuse | `PENDING` | |
| EU, OU e AU separate | `PENDING` | |
| n declared/allocated/analyzed/observational/independent | `PENDING` | |
| Estimando minimo completo | `PENDING` | |
| Design replication distinto da analytical dependence | `PENDING` | |
| Inference scope distinto dalla pseudoreplicazione | `PENDING` | |
| Astensione/scenari condizionali appropriati | `PENDING` | |
| Author assertion non trattata come prova | `PENDING` | |
| Statistical code non determina allocation | `PENDING` | |
| Alternative e conflitti conservati | `PENDING` | |
| Linguaggio prudente e non accusatorio | `PENDING` | |

## D. Review delle fixture

Ripetere la tabella per ogni caso esaminato.

| Campo | Valore |
|---|---|
| Fixture ID/versione | `PENDING` |
| Il grafo rappresenta il disegno? | `PENDING` |
| Allocation/application corrette? | `PENDING` |
| Estimando/target appropriati? | `PENDING` |
| n e scenario condizionale corretti? | `PENDING` |
| Classe alert corretta? | `PENDING` |
| Eccezione valida? | `PENDING` |
| Controesempio cambia l'esito come previsto? | `PENDING` |
| Domanda minima realmente decisiva? | `PENDING` |
| Riferimento scientifico adeguato? | `PENDING` |
| Disposition | accept / revise / block |
| Note | `PENDING` |

## E. Review delle regole

| Rule ID/versione | Classe alert | Premesse | Eccezioni/astensione | Messaggio | Esito | Note |
|---|---|---|---|---|---|---|
| `PENDING` | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `PENDING` | |

La review deve verificare il contenuto scientifico, non soltanto che il test passi.

## F. Sicurezza delle affermazioni

- [ ] Nessun output è presentato come certificazione o verità definitiva.
- [ ] Nessuna checklist suggerisce conformità o endorsement DRIVER/NC3Rs.
- [ ] Le conseguenze deterministiche non hanno una “confidence” separata dalle premesse.
- [ ] Synthetic, silver, gold e external sono nominati correttamente.
- [ ] Non sono riportate metriche non misurate.
- [ ] Licenza del codice e licenza dei dati restano separate.

## G. Findings

### Finding `REV-XXX`

- **Priorità:** blocking / high / medium / low
- **Oggetto:** `PENDING`
- **Evidenza:** `PENDING`
- **Impatto scientifico:** `PENDING`
- **Modifica richiesta:** `PENDING`
- **Criterio di chiusura:** `PENDING`
- **Disposition del maintainer:** `PENDING`
- **Verifica del reviewer:** `PENDING`

## H. Conclusione

Selezionare una sola disposition:

- [ ] Accepted for continued development — non è approvazione per uso scientifico.
- [ ] Accepted with required changes.
- [ ] Revision required before pilot.
- [ ] Blocked pending scientific clarification.

Rationale conclusivo: `PENDING`

Domini/perimetro cui si applica: `PENDING`

Limiti espliciti: `PENDING`

## I. Sign-off e audit

| Campo | Valore |
|---|---|
| Reviewer record/reference | `PENDING` |
| Data e fuso orario | `PENDING` |
| Maintainer acknowledgement | `PENDING` |
| Findings aperti | `PENDING` |
| Findings chiusi e prova | `PENDING` |
| Hash/URI del record finale | `PENDING` |

Una copia compilata chiude il gate “revisione esterna documentata” soltanto se indica
versioni, perimetro, findings e disposition e se le modifiche bloccanti sono state
verificate. Il template vuoto non chiude alcun gate.
