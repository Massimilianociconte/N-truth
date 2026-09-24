# Audit scientifico — derivazione, schema, grafo e verifier

Audit read-only del codice nel checkout locale del repository. Nessun sorgente modificato. Verifiche locali Python 3.12 della .venv, fixture canonica del repository. Non è una validazione scientifica esterna della teoria, né una dimostrazione di completezza. Non sono stati aperti PDF.

## Mappa e confini

- `derivation_theory/runtime.py`: conformance bundle, checksum e identità eseguibile, derivazione clausole A–G. Assignment unit, EU, conteggio EU, conteggio sorgenti biologiche, interferenza, unità analitica/handoff e scope. Gli output positivi del kernel v8 sono deliberatamente bloccati da SRR-V8-008.
- `schemas/knowledge.py`: sei stati epistemici distinti e wrapper tipizzato; controlli strutturali estesi, scope e provenienza. La tipizzazione si perde semanticamente nel dizionario di predicati generici `KnowledgeValue[JsonValue]`.
- `schemas/count_registry.py` + `verifier/v8.py`: registro con scope articolato; verifier confronta dieci dimensioni con query/predicati e verifica cardinalità degli identificativi distinti. Non è sufficiente un mero numero totale.
- `pipeline_v8.py`: conformance → fact verification → derivazione → claim verification → adequacy → report resolution. Claim verification re-esegue lo stesso derivatore: ottima garanzia di integrità/riproducibilità, non oracolo scientifico indipendente.
- `rules/v8_engine.py`: conserva asse epistemico interferenza e blocker SRR-V8-017; non è un verdetto universale di adeguatezza.
- `graph/index.py`, `graph/units.py`: lane precedente con gerarchie aggregate/istanze, scope per fattore/contrasto/endpoint/gruppo, n osservazionale/analitico/indipendente, condizioni d'astensione. Distinta dalla lane v8 e dal sidecar v9.
- `schemas/contrast_support.py`: sidecar v9 distingue EU ancorata all'assegnazione da exposure partition. Non sostituisce automaticamente il kernel v8.

## Finding SCI-01 — P2: incoerenza tra causal aggregate e predicati supera la pipeline

Posizione primaria `packages/ntruth/verifier/v8.py:303-312`: il join del causal aggregate controlla solo block/query. Non confronta la sua interferenza con `predicate_values['interference_status']`. Consumo `packages/ntruth/rules/v8_engine.py` campo outcome (circa linea 72): pubblica direttamente il predicato.

Riproduzione effettivamente eseguita:

```python
# PYTHONPATH=packages:tests/unit .venv/bin/python
import test_prd_v8_derivation_runtime as f
from ntruth.derivation_theory.runtime import V8DerivationInput
from ntruth.pipeline_v8 import run_v8_pipeline

_, request = f._request()
payload = request.model_dump(mode="json")
payload["predicate_values"]["interference_status"] = f._present("documented").model_dump(
    mode="json"
)
changed = V8DerivationInput.model_validate(payload)
result = run_v8_pipeline(changed, conformance_bundle=f.CANONICAL_BUNDLE)
print(changed.causal_aggregate.causal_context.interference_status.value)
print(result.design_adequacy_evaluations[0].outcome.value)
# possible
# documented
```

La pipeline completa senza errori. `documented` è un token scientificamente ammesso di InterferenceStatus, non una stringa estranea. SupportDescriptor della fixture è EXPERT_ADJUDICATION / ADJUDICATED_REFERENCE / ADJUDICATED (test_prd_v8_derivation_runtime.py:198-209), non AUTHOR_ASSERTED. Gli evidence_ids e lo scope della fixture restano invariati (EV-RUNTIME-001; IQ-RUNTIME-001); il test non falsifica checksum né bypassa validatori. Questi ID sono sintetici della fixture: non si afferma che il contenuto di un documento reale sia stato verificato. Proprio la conservazione della stessa evidenza su due valori incompatibili rende evidente il join scientifico mancante.

Impatto: l'output epistemico di adeguatezza può contraddire l'aggregato causale verificato nello stesso input senza stato CONFLICTING o errore. SRR-V8-008 blocca i claim determinati ma non questo outcome PRESENT; pertanto finding attuale e non soltanto ipotetico. Correzione suggerita: unicità della sorgente canonica o confronto di stato/valore tra fatti duplicati prima della derivazione; conflitti espliciti mai scegliere implicitamente un lato.

## Finding SCI-02 — P2: completezza accettata senza ricerca di controesempi

`packages/ntruth/schemas/coverage.py:110-119` respinge None e COUNTEREXAMPLE_FOUND, ma accetta NOT_PERFORMED. Questo contraddice il contratto dichiarato nel docstring (ricerca che non ha trovato controesempi). Il seguente oggetto valido è stato costruito senza model_construct/copy:

```python
from ntruth.schemas.coverage import ScenarioCoverage

x = ScenarioCoverage.model_validate(
    dict(
        status="COMPLETE_UNDER_DECLARED_ASSUMPTION_SET",
        profile_id="p",
        theory_version="1",
        emitting_clause_ids=["DT-A"],
        omitted_dimensions=dict(
            knowledge_state="ABSENT_EXPLICIT", rationale="No omissions", evidence_ids=["ev"]
        ),
        caveat=dict(knowledge_state="NOT_APPLICABLE", rationale="No caveat", query_scope_id="q"),
        assumption_set_id="a",
        assumption_set_version="1",
        assumption_set_finalized=True,
        counterexample_search_status="NOT_PERFORMED",
    )
)
print(x.status, x.counterexample_search_status)
# COMPLETE_UNDER_DECLARED_ASSUMPTION_SET NOT_PERFORMED
```

Richiedere esattamente BOUNDED_SEARCH_COMPLETED_NO_COUNTEREXAMPLE. Limitazione importante: V8PipelineResult.scenario_space_complete resta False per SRR-V8-008; non è stato dimostrato un bypass di quel flag aggregato. Rimane falsa dichiarazione nel contratto ScenarioCoverage serializzabile e consumabile da altri percorsi.

## Finding SCI-03 — P2: assegnazioni parziali diventano conteggi esatti incluso zero

`packages/ntruth/graph/index.py:269-286` richiede soltanto una assegnazione presente in qualunque istanza e conta i match; non distingue un target assegnato ad altro gruppo da uno privo di assegnazione. `derived_count_for_scope` consuma il risultato intero senza qualificatore (327-329). Con tre pozzetti, uno control e due non assegnati, ritorna control=1, treated=0. Scientficamente sono limiti inferiori, non conteggi completi.

Riproduzione eseguita:

```python
from ntruth.graph.index import GraphIndex
from ntruth.schemas.experiment import Hierarchy
from ntruth.schemas.graph import GraphNode, NodeType
from ntruth.schemas.core import Provenance, ProvenanceKind

p = Provenance(origin=ProvenanceKind.USER)
nodes = tuple(
    GraphNode(id=i, type=NodeType.WELL, label=i, attributes={"instance": True, **a}, provenance=p)
    for i, a in [("w1", {"assignment:drug": "control"}), ("w2", {}), ("w3", {})]
)
x = GraphIndex(Hierarchy(nodes=nodes))
print(x.count(NodeType.WELL))  # 3
print(x.scoped_instance_count(NodeType.WELL, factor_name="drug", group="control"))  # 1
print(x.scoped_instance_count(NodeType.WELL, factor_name="drug", group="treated"))  # 0
```

Correzione: preservare sconosciuti/limiti inferiori oppure richiedere copertura completa delle assegnazioni dei target e antenati prima di emettere un intero esatto. Limite della prova: test del componente GraphIndex, non costruita una pubblicazione finale API di n indipendente; altri gate potrebbero asternersi a valle.

## Osservazione latente SCI-L01: semantica dei predicati generici non validata

`runtime.py:656`, `verifier/v8.py:366-395`: un predicato assignment_separability PRESENT stringa 'false' supera V8DerivationInput.model_validate e verify_v8_pipeline_request con passed=True. Usato stessa fixture, cambiato solo quel predicato. Non è bug di coercizione dei bool di KnowledgeValue: il payload è deliberatamente JsonValue e nessun registro di predicati impone bool. `_state_for` verifica gli stati, non il dominio dei valori. La derivazione usa `is True` per i predicati positivi; quindi l'input errato non promuove oggi un EU positivo. Non classificare come falso positivo dimostrato. È un requisito di hardening scientifico prima di eliminare i blocker o aggiungere evaluator.

## Limiti e meriti

La distinzione tra assegnazione, esposizione, unità analitica e sorgente biologica è presente e articolata. I vincoli di scope, cardinalità, provenienza e i blocker espliciti riducono molto i falsi positivi. Le riproduzioni non dimostrano né pretendono che il sistema emetta oggi n indipendente positivo dal kernel v8: il blocker globale impedisce questa lettura. Restano separati bug correnti di consistenza/conteggio e incompletezza scientifica deliberatamente dichiarata. Non valutate sensibilità/specificità su studi reali, accordo fra esperti, completezza del dominio né correttezza bibliografica della derivazione; servono corpus indipendente e revisione scientifica autorizzata.
