# Theory Assets — separazione in tre asset (PRD v8.0 §10.9)

La validazione di N-Truth è divisa in **tre asset separati** che non devono
mai essere confusi né alimentati l'uno dall'altro in modo circolare.

| Asset | Percorso | Ruolo | Origine delle aspettative |
| --- | --- | --- | --- |
| **Theory Reference Set** | `tests/theory_reference/` | Casi e counterfactual expert-reviewed che verificano la Derivation Theory | **Solo** testo normativo PRD v8.0 e revisione esperta |
| **Implementation Conformance Fixtures** | `tests/rule_fixtures/` | Verificano che il Rulebook implementi ogni theory clause | Contratti delle regole (precondizioni/eccezioni/astensioni) |
| **Derivation Gold** | `tests/scientific_fixtures/` + `tests/golden/` | Grafi reali confermati con claim attesi, support grade, design findings e rationale | Casi reali adjudicati da biostatistico e domain expert |

## Regola anti-circolarità (normativa)

> Il **Theory Reference Set non consuma MAI l'output del Rulebook** come
> riferimento (PRD v8.0 §10.9, §7.13).

Conseguenze operative:

1. Le aspettative del Theory Reference Set (`tests/theory_reference/clauses/`)
   non possono essere generate, copiate o validate a partire dagli output di
   `apply_rules` o dai golden snapshot del software.
2. I counterfactual minimali (§7.13: due record ammissibili identici salvo il
   valore di un predicato decisivo) sono definiti nella teoria prima e
   indipendentemente dal comportamento corrente del codice: un Rulebook può
   implementare male un predicato decisivo senza che questo cambi la teoria.
3. Le Implementation Conformance Fixtures verificano la **fedeltà** del
   Rulebook alle clausole, non la verità scientifica delle clausole.
4. La Derivation Gold valida il contratto end-to-end su casi reali confermati
   e non può essere sostituita da fixture sintetiche.

## Stato corrente (fail-closed)

- `derivation-theory-0.1.0` (**non revisionata**, registro `SRR-0003`):
  clausole §7.15 famiglie A-G; gli enunciati normativi sono il testo PRD
  verbatim; i clause ID `DT-EU-COUNT-01` e `DT-ANALYTICAL-01` sono convenzioni
  della migrazione (il PRD non mostra ID per le famiglie C e F).
- Tutte le voci del Theory Reference Set sono
  `SCIENTIFIC_REVIEW_REQUIRED`: il contenuto sotto-determinato non viene
  inventato (registro SRR).
- `ntruth-core-0.3.0` dichiara `theory_version: derivation-theory-0.1.0`;
  27/32 regole sono collegate a una clausola §7.15, 5 regole senza clausola
  difendibile restano disabilitate e marcate `SCIENTIFIC_REVIEW_REQUIRED`
  (registro `SRR-0012`); `DT-EXP-02` è dichiarata coverage gap (NFR-33).

## Struttura

```text
tests/theory_reference/
├── manifest.json            # indice delle voci, teoria dichiarata, regola anti-circolarità
└── clauses/
    └── <clause_id>.yaml     # una voce per clausola: positive/negative expectation + minimal counterfactual
tests/rule_fixtures/         # Implementation Conformance Fixtures (NFR-12)
tests/scientific_fixtures/   # candidati Derivation Gold (casi d'uso)
tests/golden/                # snapshot software deterministici (NON sono Derivation Gold esperta)
```
