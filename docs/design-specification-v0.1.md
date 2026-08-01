# Design Specification v0.1

## Scopo

`DesignSpecification` è il contratto JSON locale che rende esplicito il disegno di un
singolo `ExperimentBlock`. Formalizza fatti già presenti nel blocco e li passa a un
compilatore deterministico. Non seleziona test statistici, non genera formule di
modello e non esegue power analysis.

Il PRD v3 distingue due oggetti collegati ma non intercambiabili:

- `InferenceTarget`: domanda/claim, popolazione di inferenza e riferimenti agli
  oggetti del disegno;
- `Estimand`: endpoint, misura dell'effetto, popolazione o insieme di unità target,
  livello di generalizzazione, fattori ed eventuale tempo/condizione.

## Target inferenziale ed estimando

Ogni `InferenceTarget` contiene domanda e claim testuali, popolazione di inferenza,
riferimenti a fattori/contrasti/endpoint, eventuale unità biologica target, evidenze,
provenance e stato `extracted`, `user_confirmed`, `missing` o `conflicted`.

Un target `extracted` resta un candidate fact. Solo `user_confirmed` indica che una
persona ha confermato il mapping; neppure questo stato certifica validità,
generalizzabilità o correttezza del disegno.

Ogni `Estimand` valido richiede:

```text
endpoint_id
effect_measure
target_population_or_unit
generalization_level
factor_ids[]
timepoint? / condition?
evidence_ids[]
```

L'estimando non viene ricavato automaticamente da una formula R/Python. Il codice
statistico può alimentare `declared_clustering`, che resta separato dall'allocazione.

## Allocazione e applicazione

Per ogni fattore il contratto conserva:

- `allocation_level`, confidence ed evidence: dove i livelli possono essere assegnati
  indipendentemente;
- `application_level`, confidence ed evidence: dove la procedura è materialmente
  applicata.

I campi possono differire e non vengono sincronizzati tra loro. `assignment_level`
resta soltanto un alias di compatibilità della precedente v0.1 e corrisponde
all'allocazione, mai all'applicazione.

## Flusso del compiler

```text
ExperimentBlock
  -> DesignSpecification
  -> validazione dei riferimenti
  -> elicitazione dei campi mancanti
  -> AnalysisHandoff strutturale oppure astensione
```

L'elicitazione non completa valori per inferenza. Produce domande deterministiche su
target, popolazione, fattori, contrasti, endpoint, estimando, unità biologica,
allocazione e applicazione.

Il compiler si astiene quando il target manca/non è confermato, un estimando richiesto
è incompleto, esistono conflitti irrisolti o gli assessment non sono collegati allo
scope. In questi casi `target_population_support` resta `unknown` o `conditional`.

`NScope.inference_target_id` mantiene separati assessment che condividono lo stesso
grafo ma rispondono a domande o popolazioni diverse. Uno scope legacy viene collegato
solo se fattore, contrasto ed endpoint identificano un singolo target compatibile; non
esiste fallback globale o prodotto cartesiano.

Il valore `supported` significa soltanto che il mapping target-scope è confermato e
strutturalmente completo. Non è un verdetto scientifico.

## Analysis handoff

`AnalysisHandoff` espone:

- target e assessment associati;
- estimandi minimi;
- allocazioni e applicazioni in collezioni separate;
- nesting, derivazione, splitting e pooling espliciti;
- cluster da grafo/assessment e clustering dichiarato dai modelli;
- relazioni `repeated_measure_of`;
- endpoint, tempi e aggregazioni dichiarate;
- assunzioni e domande irrisolte.

Gli output vietati restano registrati nel contratto:
`statistical_test_selection`, `model_formula`, `power_analysis`.

## API Python

```python
from ntruth.design import (
    DesignSpecification,
    compile_experiment_block,
    load_design_specification,
    write_design_json_schema,
    write_design_specification,
)

spec = DesignSpecification.from_experiment_block(block)
write_design_specification(spec, "design.json")
write_design_json_schema("design.schema.json")

restored = load_design_specification("design.json")
compilation = compile_experiment_block(block)
assert restored.specification_id == compilation.specification_id
```

Import ed export sono offline e validano i riferimenti locali. La pipeline include la
specifica, lo schema e la compilazione tra gli artefatti versionati. L'API locale può
registrare una conferma del target come JSON Patch append-only e ricalcolare il
risultato; una conferma resta auditabile e non diventa automaticamente gold.
