# Matrice audit Gemini -> decisione v6.1

| ID | Osservazione | Valutazione critica | Decisione | Sezioni v6.1 e artefatti |
|---|---|---|---|---|
| G-01 | Synthetic Task Use Matrix per P0/P1/P2 | Accolta. La v6.0 descriveva classi qualitative, ma non una matrice operativa con real-gold floor. | Bande task-specifiche, mixture search su real dev e real-only evaluation. | §§12, 14-15, 24; Appendice S; `synthetic-task-use-matrix-v6.1.md` |
| G-02 | Runtime Resource Manager | Accolta. Il target locale esisteva, ma mancavano lifecycle, profili, eviction e telemetry per bundle. | Runtime sequenziale, load/unload, chunking, cache LRU, profili e benchmark artifact. | §§20, 22, 25-26; Appendice T; `runtime-resource-budget-v6.1.md`; `packages/ntruth/runtime_resources/` |
| G-03 | Cascata preferita, non obbligatoria | Accolta. B5 era già una baseline, ma alcune formule potevano sembrare una decisione anticipata. | Confronto A-E; nessun backbone, size, framework o quantizzazione congelati prima dei benchmark. | §§12.3-12.6, 24-26; Appendice G |
| G-04 | Sintassi distinta da semantica | Accolta e rafforzata. La v6.0 elencava già più verifiche, ma la distinzione deve essere inequivoca. | Grammar/JSON valid non equivalgono a ricostruzione corretta; validation stack esplicito. | §13.4, §30, release blockers |
| G-05 | Governance progressiva | Accolta con salvaguardia: i vincoli scientifici e legali restano permanenti. | Quattro livelli A-D; primi 90 giorni lean; Resource Gate/STOP/committee attivati per rischio. | §§0.4, 28-29; Appendice U; `lean-governance-matrix-v6.1.md` |
| G-06 | Correggere assoluti | Accolta criticamente. Quattro frasi non erano letteralmente nella v6.0; il target RAM preciso invece sì. | Registro occurrence-aware e formulazioni conservative. | §§1, 6, 11-13, 22, 25; Appendice V; `absolute-claims-register-v6.1.md` |
| G-07 | Soglie release provvisorie | Accolta. | Threshold provisional fino a pilot e protocol approval, con CI/prevalence/human ceiling/cost. | §§18, 24, 31-32; validation protocol |
| G-08 | Correzioni facsimile -> invariant test | Accolta con chiarimento semantico: conteggi distinti possono avere lo stesso valore numerico. | Constraint di schema, positivo, negativo, counterfactual e CI blocker per ogni invariante. | §§15.10-15.15, 26.2, 32.7; `tests/unit/test_v6_split_facsimile_invariants.py`; fixture counterfactual v6; CI `invariant` |
| G-09 | Prospective Gold piano vs esecuzione | Accolta. La riconciliazione esisteva, ma non tutti i delta erano campi distinti. | Planned, executed, deviations, substitutions, exclusions, pooling, losses, treatment changes e final sample sheet separati. | §§6.1, 14.2, 18.6, 20, 23; `packages/ntruth/prospective/plan_execution.py` |
| G-10 | ADR per decisioni tecniche | Accolta. La v6.0 richiedeva ADR genericamente, non la copertura minima. | ADR obbligatori per model, backend, quantization, structured decoding, verifier, DB e rule language. | §§26.3-26.5, 29.6; `docs/adr/0002`-`0009` |
| G-11 | Non ridurre AI/scopo finale | Vincolo invariato e prioritario. | Train A e modello specializzato restano deliverable obbligatori; Train D non li sostituisce. | Statuto, §§0.1, 1, 4, 12, 32-33 |

## Principi non modificati

Restano vincolanti: AI centrale, motore deterministico, human-in-the-loop, real gold,
External Challenge, Synthetic Data Factory, prospective-first, local-first,
astensione, output condizionali, anti-leakage, separazione AUTHOR_ASSERTION/
STRUCTURAL_FACT e allocation/application, no statistical washing, nessuna
certificazione DRIVER e nessuna scorecard pubblica automatizzata di paper terzi.
