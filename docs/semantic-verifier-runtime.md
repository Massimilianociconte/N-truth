# Semantic Verifier Runtime

**Stato:** implementato (`algorithmic_v1`); backend modello **non** scientificamente validato.

## A cosa serve

N-Truth ha **due strati di verifica automatica** distinti, più la conferma umana:

| Strato | Domanda | Esempio di fallimento |
|---|---|---|
| **Hard verifier** (sempre attivo) | Il grafo viola un invariante strutturale o di policy? | `INDEPENDENT_N` senza indipendenza; grafo ciclico; output vietati |
| **Semantic verifier** (runtime) | I claim decisivi sono *supportati* e coerenti? | Indipendenza basata solo su `AUTHOR_ASSERTION`; planned_n &lt; allocated_n; span non nel testo |
| **Human confirmation** | L’esperto conferma i campi decisivi? | Allocation implicita, coreference ambigua |

Il semantic verifier **non**:

- sostituisce l’hard verifier;
- “ripulisce” un grafo hard-invalid;
- certifica paper o DRIVER;
- chiude missing facts assenti.

Serve a **bloccare o segnalare** ricostruzioni semanticamente deboli *prima* della revisione umana, riducendo falsa certezza.

## Cosa c’è oggi

Implementazione: `packages/ntruth/verifier/semantic.py`

- Backend default: `algorithmic_v1` — regole deterministiche, indipendenti dai pesi del parser.
- Check tipici:
  - supporto all’indipendenza (non solo AUTHOR_ASSERTION/MODEL_INFERENCE);
  - coerenza allocation/application + mechanism;
  - ordine numerico lifecycle EXACT;
  - contradiction records → review;
  - DETERMINATE non chiudibile con sole AUTHOR_ASSERTION;
  - grounding opzionale degli evidence span su `source_texts`.
- Backend `model_provisional`: **fail-closed** finché non è configurato un secondo modello con lineage indipendente.

API:

```python
from ntruth.verifier import verify_semantic, SemanticBackend

result = verify_semantic(block)  # algorithmic
result = verify_semantic(block, source_texts={"methods.md": text})
result = verify_semantic(block, backend=SemanticBackend.MODEL_PROVISIONAL)  # FAIL esplicito
```

Integrazione stack:

```python
from ntruth.verifier import build_validation_stack_report, verify_block, verify_semantic

hard = verify_block(block)
sem = verify_semantic(block)
report = build_validation_stack_report(
    schema_valid=True,
    referentially_valid=True,
    hard_verified=hard.valid,
    semantic_invoked=True,
    semantic_passed=sem.passed,
    human_confirmed_decisive=False,
    require_human_confirmation=True,
)
```

## Cosa serve per un “secondo modello”

ADR-0006 richiede **indipendenza** dal generator. Non basta ri-usare lo stesso Granite (o qualsiasi monolitico) con un prompt diverso e chiamarlo “validato”.

Prerequisiti minimi:

1. **Lineage indipendente**: pesi e/o training diversi dal generator (almeno distillation/verifier-specific o modello alternativo benchmarkato).
2. **Contratto VERIFY-only**: JSON di check (pass/fail/codes), **senza** generare nuovi fatti o grafi.
3. **Benchmark**: agreement/disagreement, errori critici corretti, falsi blocchi, latenza, peak RAM su decisive fields e contradiction challenge.
4. **Budget runtime**: stage `semantic_verifier` nel budget M5 misurato (già previsto nel harness).
5. **Governance**: non promuovere a release gate finché non supera il protocollo di valutazione; fino ad allora resta `PROVISIONAL`.

Finché questi punti non sono chiusi, `algorithmic_v1` è il runtime corretto e onesto.

## Relazione col benchmark RAM

Lo stage `semantic_verifier` è misurato nel protocollo `ntruth-ml benchmark-resources` insieme a `rules_engine` e `hard_verifier`, così il resource manager può schedulare la verifica senza stime teoriche.
