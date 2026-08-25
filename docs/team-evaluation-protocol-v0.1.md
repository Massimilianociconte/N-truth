# Team Evaluation Protocol H / A / H+A — preregistration draft v0.1

> **PREREGISTRATION_DRAFT (v0.1).** Questo documento è una bozza di
> preregistrazione del protocollo di valutazione del team umano-AI (PRD v9,
> §18.9, §24.2–24.7 e Appendice AM; decisione in Appendice D.4–D.5).
>
> **Stato:** `PREREGISTRATION_DRAFT` — non congelato, non approvato.
> **Dati:** NESSUN dato è stato raccolto. Nessun risultato esiste. Nessun claim
> di prestazione è autorizzato da questo documento o dal modulo
> `packages/ntruth/team_evaluation/`, che definisce soltanto i contratti
> fail-closed del protocollo.
>
> Congelamento richiesto prima dell'arruolamento: firma di biostatistico,
> wet-lab lead, annotation lead ed evaluation custodian. Dopo il congelamento il
> campo `status` passa a `FROZEN_PREREGISTRATION` e ogni modifica è una
> deviazione preregistrata da documentare separatamente.

| Campo | Valore |
| --- | --- |
| Protocol ID | `TEAM-EVAL-V0.1` |
| Status | `PREREGISTRATION_DRAFT` |
| Versione | 0.1 |
| Data raccolta iniziata | No |
| Schema di riferimento | `ntruth.team_evaluation.TeamEvaluationProtocolRecord` (`schema_version = "9.0.0"`) |

## 1. Obiettivo (AM.1)

Stimare se il workflow H+A migliora il lavoro rispetto a H (human-only),
distinguendo:

- capacità del modello candidato (condizione A, diagnostica);
- effetti di interazione del team;
- automation bias;
- apprendimento/carryover fra bracci.

Il valore dell'AI è attribuito mediante confronto fra condizioni, non dalla sola
accuratezza del modello. Le stage metriche diagnosticano l'origine degli errori
ma non sostituiscono la valutazione end-to-end del ReportBundle consumato
dall'utente (§24.1).

## 2. Design minimo (AM.2, §18.9, §24.2, §24.6)

### 2.1 Condizioni obbligatorie

- **H**: human-only;
- **A**: output candidato AI senza correzione umana, esclusivamente diagnostico
  (`diagnostic_only = true`; non costituisce uso previsto);
- **H+A**: workflow completo;
- opzionali: **H+A-no-explanations** o UI variants per testare interaction design.

Un record senza condizioni H, A e H+A complete non è valido (fail-closed).

### 2.2 Disegno sperimentale

- design: counterbalanced crossover con washout adeguato **oppure**
  parallel cluster-randomized;
- casi assegnati per study family/lab cluster, isolati fra condizioni;
- partecipanti stratificati per ruolo ed esperienza;
- case-order randomizzato con seed sigillato: commitment via fingerprint
  SHA-256 del seed, copertura di allocazione ai bracci e ordine dei casi,
  registrato prima dell'arruolamento;
- periodo di washout/training con learning/carryover assessment preregistrato
  (obbligatorio per crossover);
- stessa disponibilità di fonti (`uniform_source_access = true`) e stesso time
  budget dichiarato in tutte le condizioni;
- reference indipendente e blind (`reference_policy = INDEPENDENT_BLIND`,
  fail-closed);
- capture dell'initial human judgement su un subset cieco di casi, prima della
  visualizzazione dell'AI;
- logging di accept/reject/override, evidence inspection e active review time;
- regole di missing-data e stopping rule preregistrate, incluso safety stop su
  critical-error rate inaccettabile.

## 3. Outcomes preregistrati (AM.3, §24.3)

### 3.1 Primary outcomes (tutti obbligatori)

1. decisive-claim correctness;
2. critical false-certainty rate;
3. active review time;
4. unresolved material gap detection.

Ogni primary outcome richiede una decision region preregistrata
(superiority o non-inferiority, con margine esplicito per la non-inferiorità).
La critical false-certainty event è definita da §24.5.

### 3.2 Secondary outcomes (tutti obbligatori)

evidence inspection; correction/acceptance patterns; confidence calibration;
question usefulness; subjective burden and comprehension; subgroup heterogeneity.

### 3.3 Analysis plan

Analisi cluster-aware per **partecipante E case family** (entrambe le dimensioni
obbligatorie). Stime e intervalli cluster-robust per ogni decision region.
Missing-data handling preregistrato per metrica. Nessuna analisi post-hoc può
sostituire una regione non registrata.

## 4. Automation-bias events (AM.4, §18.10)

Classificazione obbligatoria degli eventi:

| Evento | Definizione operativa |
| --- | --- |
| COMMISSION_ERROR | suggerimento AI errato accettato (richiede `ai_candidate_ref` e disposition ACCEPTED) |
| OMISSION_ERROR | errore o evidence contraria non scoperta (evidence non aperta prima della conferma) |
| ANCHORING | giudizio spostato dall'AI (richiede initial human judgement capturato prima del display AI) |
| CONFIRMATION_FATIGUE | conferme meccaniche degradate nel tempo |
| SELECTIVE_DISTRUST | underreliance selettiva su output corretti |
| EXPLANATION_INDUCED_OVERACCEPTANCE | accettazione eccessiva indotta dalle spiegazioni |

Ogni evento registra: initial_human_judgement (quando applicabile),
ai_candidate_ref, disposition (ACCEPTED/REJECTED/CORRECTED) e
`evidence_opened_before_confirm`. Il residual audit cieco campiona anche casi in
cui l'AI era high-confidence e sbagliata.

## 5. Claim policy (AM.5, §24.7)

Nessun claim è permesso senza il backing preregistrato corrispondente:

- **Time saving**: solo con regione di non-inferiorità preregistrata sul
  critical-risk (critical false-certainty rate);
- **Safety/accuracy improvement**: solo con comparatore appropriato (H) e
  incertezza clusterizzata;
- **Complementarity**: solo quando H+A supera sia H sia A sul criterio
  preregistrato, oppure con Pareto trade-off esplicitamente giustificato in
  preregistrazione.

L'accuracy H+A inferiore ad AI-only non è necessariamente un fallimento del
prodotto, ma segnala che il team non è complementare e richiede redesign.
Accuracy superiore a human-only senza controllo dei critical errors non basta.

## 6. Unità di reporting (Appendice D.4)

Riportare sempre: casi, study families, articoli, laboratori/facility, source
classes, coppie di reviewer, profili, complexity tier, factor role, contrast
type, critical-error class e condizioni sperimentali. Nessuna aggregazione in
media non pesata fra classi di errore.

## 7. Decisione GO / REVISE / LIMIT / PAUSE / STOP (Appendice D.5)

La decisione deve essere motivata esplicitamente su: critical risk, reference
stability, burden, complementarity, calibration, OOD, cluster precision, data
rights e sostenibilità. Il semplice raggiungimento di un numero di casi non
basta.

- **GO**: regioni preregistrate raggiunte con reference stabile e burden non
  peggiore;
- **REVISE**: risultati promettenti con deviationi correggibili del protocollo o
  dello strumento;
- **LIMIT**: claim ristretto al sotto-dominio supportato dai dati;
- **PAUSE**: evidenza instabile o incompleta che impedisce qualsiasi claim;
- **STOP**: automation bias o critical residual error oltre la soglia di
  sicurezza preregistrata → STOP del default AI (kill criteria §18.13).

## 8. Garanzie fail-closed del contratto dati

Il modulo `packages/ntruth/team_evaluation/` rifiuta (ValueError):

1. record privi di condizioni H, A o H+A complete;
2. preregistrazioni metriche senza decision region;
3. reference policy diversa da independent-blind;
4. assenza di uniform source access o time budget uniforme;
5. analysis plan non clusterizzato per partecipante E case family;
6. primary outcomes diversi dai quattro AM.3;
7. claim policy priva di regione decisionale a supporto;
8. draft con data collection avviata.

Questi vincoli sono testati in `tests/unit/test_team_evaluation_protocol.py`.

## 9. Nota anti-overclaim

Questo protocollo non produce evidenza. Finché `status` resta
`PREREGISTRATION_DRAFT` e `data_collection_started = false`, nessun numero,
benchmark interno o smoke test sintetico costituisce risultato del team H/A/H+A.
La validazione scientifica del progetto resta formalmente `NOT_STARTED`
(SCIENTIFIC_STATUS_PIN) con training ed external challenge in HOLD.
