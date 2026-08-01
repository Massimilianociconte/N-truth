# Scrivere e modificare le regole

Le regole vivono in `rulesets/<id>-<versione>.json`, **fuori dal codice e fuori dai
prompt**. Modificarle non richiede retraining: basta versionare il ruleset e
rieseguire l'analisi. Un pacchetto distribuito deve comunque includere la nuova risorsa.

```bash
ntruth rules list
ntruth rules show MIC-004
ntruth rules predicates
```

## Anatomia di una regola

```json
{
  "rule_id": "MIC-004",
  "version": "1.0.0",
  "domain": "quantitative_microscopy",
  "title": "Cellule trattate come indipendenti con intervento a livello di coltura",
  "preconditions": [
    "Cell nested_in Field",
    "Field nested_in Well",
    "Well nested_in Culture",
    "Analysis analyzed_as Cell",
    "Treatment assigned_at Culture or higher"
  ],
  "inference": "Cell-level observations are not independent for the treatment effect.",
  "message_it": "... {experimental_unit} ... {n_independent}",
  "message_en": "...",
  "severity": "critical",
  "alert_class": "analytical_dependence",
  "exceptions": ["model_accounts_for_assignment()"],
  "abstain_if": ["sufficiency_below(source_independence, medium)"],
  "questions": ["Le colture usate derivano da preparazioni o donatori indipendenti?"],
  "requires_human_confirmation": true,
  "scope_dimension": "contrast"
}
```

Semantica della valutazione, in quest'ordine:

1. **preconditions** — tutte vere (AND). Se una e falsa: `not_applicable`.
2. **exceptions** — se una e vera: `excepted`, nessun alert.
3. **abstain_if** — se una e vera: l'alert viene emesso con severita
   `insufficient` e l'informazione mancante dichiarata.
4. altrimenti: `fired` con la severita della regola.

Un predicato sconosciuto non e mai considerato falso: la regola diventa `unevaluable`,
non scatta e il fatto viene riportato nei limiti del report.

Nel PRD v3 `alert_class` è concettualmente obbligatoria e separata dalla severity:

- `DESIGN_REPLICATION`: replicazione/allocazione dell'intervento;
- `ANALYTICAL_DEPENDENCE`: osservazioni correlate e analisi;
- `INFERENCE_SCOPE`: portata del claim rispetto alla popolazione replicata.

Una regola non va spostata tra classi per renderne il messaggio più severo. La severity
descrive impatto/correggibilità, non il tipo scientifico del problema.

Il modello dati conserva temporaneamente `DESIGN_REPLICATION` come default per leggere
snapshot legacy. Il ruleset v3 deve valorizzare il campo esplicitamente: ometterlo non è
una classificazione scientifica e non chiude la DoD.

## Sintassi delle precondizioni

Due forme equivalenti:

| Forma triple (come nel PRD) | Forma funzionale |
|---|---|
| `Cell nested_in Field` | `nested(Cell, Field)` |
| `Well derived_from Culture` | `derived(Well, Culture)` |
| `Analysis analyzed_as Cell` | `analyzed_as(Cell)` |
| `Treatment assigned_at Culture or higher` | `assigned_at_or_above(Culture)` |

Ogni espressione puo essere negata con `not `:

```json
"preconditions": ["model_is_mixed()", "not model_accounts_for_assignment()"]
```

## Predicati disponibili

**Struttura del grafo**
`level_present(X)`, `nested(A, B)`, `derived(A, B)`, `multiple_instances(X)`,
`single_instance(X)`, `count_unknown(X)`, `technical_level(X)`,
`independence_declared(X)`

**Unita e n**
`assigned_at(X)`, `assigned_at_or_above(X)`, `assigned_at_or_below(X)`,
`assignment_unknown()`, `analyzed_as(X)`, `measured_on(X)`,
`analysis_finer_than_assignment()`, `observation_finer_than_assignment()`,
`n_independent_unknown()`, `declared_equals_observational()`,
`declared_exceeds_independent()`, `declared_n_scope_global()`, `multiple_scopes()`,
`ambiguous_replicate_term()`

**Modello statistico**
`model_declared()`, `model_is_mixed()`, `model_is_simple()`, `model_accounts_for(X)`,
`model_accounts_for_assignment()`

**Processo**
`pooling_present()`, `aggregation_present()`, `repeated_measures_present()`,
`exclusions_reported()`, `blinding_reported()`, `perfect_confounding()`,
`contradiction_unresolved()`, `factor_kind(k)`, `endpoint_unlinked()`

**Completezza**
`sufficiency_below(dimensione, livello)`, `sufficiency_at_least(dimensione, livello)`
con dimensione in `intervention_level`, `source_independence`, `exclusions`,
`aggregation`, `statistical_model` e livello in `unknown`, `low`, `medium`, `high`.

Alias dei tipi accettati nelle regole: `Culture`, `Donor`, `Subject`, `Animal`, `Dam`,
`Litter`, `Cage`, `CellLine`, `Tissue`, `Pool`, `Plate`, `Well`, `Section`, `Field`,
`Image`, `ROI`, `Cell`, `Library`, `Run`, `Batch`.

## Segnaposto nei messaggi

`{factor}`, `{contrast}`, `{endpoint}`, `{experimental_unit}`, `{observational_unit}`,
`{analytical_unit}`, `{biological_unit}`, `{n_declared}`, `{n_observational}`,
`{n_independent}`. Un segnaposto senza valore diventa `non determinato`: un messaggio non
puo affermare piu di quanto il grafo contenga.

## Vincoli di qualita verificati dai test

- Ogni predicato citato da una regola deve esistere (`test_every_predicate_exists`).
- Tutte le 32 regole del ruleset core devono essere presenti, dichiarare esplicitamente
  una classe v3 e coprire insieme l'intera tassonomia.
- Una regola `critical` deve dichiarare almeno un'eccezione o una condizione di
  astensione **e** richiedere conferma umana: una regola critica senza via d'uscita
  produce falsi allarmi e richiede review scientifica.
- Ogni regola deve avere messaggio italiano e inglese: il layer linguistico è separato
  da quello scientifico (PRD v3 NFR-11).
- La confidenza delle premesse può essere riportata; l'outcome deterministico non riceve
  una probabilità propria.

## Aggiungere una regola

1. Scrivere la regola nel ruleset, assegnare la classe di alert e alzare la versione.
2. Aggiungere i quattro scenari di contratto: positivo, negativo, ambiguo ed eccezione.
3. Aggiungere o aggiornare una fixture canonica completa con grafo, output atteso,
   controesempio, eccezione e riferimento scientifico. Il generatore del test harness
   non sostituisce questa fixture.
4. Eseguire l'intera suite: le regressioni storiche non devono cambiare senza decisione
   scientifica documentata.
5. Far revisionare regola e fixture da biostatistico e domain expert. Finché la review
   non è registrata, la regola resta development e non “approvata”.
