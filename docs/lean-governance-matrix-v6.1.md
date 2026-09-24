# Lean Governance Matrix v6.1

La governance cresce con il rischio. I vincoli scientifici permanenti non vengono
rinviati; comitati, firme e gate organizzativi diventano obbligatori quando il progetto
usa dati reali, addestra modelli o sostiene claim di release.

| Livello | Quando | Obblighi minimi | Ruoli/autorità | Evidenza di uscita |
|---|---|---|---|---|
| A. Vincoli permanenti | Sempre | Human-in-the-loop, astensione, provenance, anti-leakage, separazione assertion/fact e allocation/application, no statistical washing, no DRIVER certification, no public paper scorecard | Product owner; reviewer scientifico quando una regola cambia | Test, audit trail e blocker register |
| B. Lean 0-90 giorni | Bootstrap D0 e senza training scientifico | Core Schema, rulebook, 30-60 fixture candidate, wizard prospettico, export, review esterna minima, registro blocker; privacy/licenza solo per asset effettivamente acquisiti | Product owner, engineering owner, almeno un wet-lab o biostatistical reviewer esterno al codice per il nucleo | Core review, fixture report, export smoke, decisione PROCEED/REVISE/LIMIT |
| C. Ricerca/gold/training | Prima di corpus umano, calibration o fine-tuning | Guideline, DMP, license manifest, Parser/Derivation Gold separati, doppia sui campi decisivi, adjudication, split custoditi, baseline, Runtime Resource Budget misurato, Resource Gate per la fase | Data steward, annotation lead, wet-lab reviewer, biostatistico, ML lead, adjudicator indipendente | Snapshot congelato, IAA pre-adjudication, benchmark, Resource Gate GO/LIMIT |
| D. Release v1.0-A | Prima di claim AI supportato | Protocollo preregistrato, External Challenge reale e custodito, validation committee, STOP Authority, model/data/system card, rollback, maintenance e incident response | Comitato di validazione, external challenge custodian, release owner, STOP Authority indipendente | Decisione GO/REVISE/LIMIT/STOP e release dossier |

## Attivazione progressiva dei gate

- Il `Resource Gate` è informativo durante il bootstrap e diventa bloccante prima di
  feasibility, training scientifico costoso o impegni esterni non reversibili.
- La `STOP Authority` può essere nominata in anticipo, ma il mandato formale diventa
  obbligatorio prima dell'apertura di test custoditi o di una decisione di release.
- Il validation committee non è richiesto per scrivere fixture o costruire il wizard;
  è richiesto per congelare protocolli e valutare v1.0-A.
- La governance lean non autorizza dati, training o claim che appartengono ai livelli
  successivi.

## Registro dei blocker nei primi 90 giorni

Ogni blocker contiene `id`, area, descrizione, severità, owner, evidenza richiesta,
stato, data della prossima review e decisione. Sono blocker obbligatori almeno falsa
certezza, output fuori DeterminabilityState, regola critica non revisionata, perdita di
provenance, licenza incerta su un asset acquisito e scope drift del Core.
