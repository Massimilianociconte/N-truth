# Audit validazione, confidence e governance N-Truth

Audit read-only del checkout locale del repository, 2026-09-12. Nessuna modifica al codice. Analisi statica e riproduzioni locali; nessun PDF letto e nessun training avviato.

## Bug confermati

### [P1] La metrica di errore critico ad alta confidence conta gli esempi corretti

**File:** `packages/ntruth/confidence/records.py:324` (funzione righe 307–328).

`false_high_confidence_critical_error_rate` incrementa il numeratore quando `label == 1`. Nel medesimo modulo Brier, log-loss e curva rischio/copertura assumono invece 1=corretto, 0=errore. L'aggregatore `compute_calibration_metrics` passa le stesse etichette a tutte le metriche: non è quindi possibile interpretare questa funzione con una codifica alternativa coerente.

Riproduzione eseguita con `.venv/bin/python`: `compute_calibration_metrics([.99], [0], critical_flags=[True])` produce Brier 0.9801, rischio 1.0, ma false-high-confidence-critical-error-rate **0.0**. Sostituendo label=1, Brier=0.0001, rischio=0.0, false-high=**1.0**. L'indicatore di sicurezza viene invertito, potenzialmente premiando esattamente gli errori che deve segnalare. Correggere il predicato in label==0 e le attese test.

La suite attuale perpetua il difetto: `tests/unit/test_confidence_records.py:166–191` si aspetta 0 per l'unico caso critico errato ad alta confidence e 1 per quello corretto. Test verdi qui non costituiscono una verifica indipendente della formula. Non ho trovato integrazione di queste metriche nella pipeline principale oltre alle esportazioni del modulo: impatto accertato sull'API di metriche; impatto sui claim di produzione non dimostrato e attualmente limitato dal HOLD.

### [P2] La selezione della soglia di astensione spezza i pareggi di confidence

**File:** `packages/ntruth/training/calibration.py:169–177`.

La ricerca valuta ogni prefisso ordinato e restituisce una soglia numerica anche quando il prefisso termina all'interno di un gruppo con identico score. Una soglia non può selezionare solo alcuni elementi di quel gruppo.

Riproduzione eseguita: 20 `ConfidenceObservation(.9, correct)`, prima 10 corrette poi 10 errate, parametri default (rischio massimo .10, copertura minima 10). Risultato: threshold=.9, covered=11, coverage=.55, empirical_risk=.090909. Applicando score>=.9 vengono selezionate tutte le 20 osservazioni, con rischio **.50**, cinque volte il massimo richiesto. La selezione dipende inoltre dall'ordine delle etichette entro il pareggio. Valutare soglie solo alla fine di ciascun gruppo di score uguali e registrare l'esatta convenzione di confronto.

Il risultato entra realmente nell'artefatto prodotto da `calibration_report` e dal workflow `packages/ntruth/training/mlx_inference.py:1470–1474`. Non ho trovato un consumatore runtime della soglia nel checkout: il bug dimostrato è nell'artefatto/raccomandazione di calibrazione, non un comportamento runtime già misurato.

## Limiti dichiarati, da non classificare come bug

- `docs/prd-v8-data-training-evaluation-boundary.md:3–6,43–49`: HOLD esplicito; niente real anchor, Derivation Gold, riferimento indipendente o autorità External Challenge nel clean checkout. Lo stato scientifico resta NOT_STARTED. L'assenza di questi dati impedisce validazione di accuratezza, calibrazione, generalizzabilità e benefici H+A.
- `packages/ntruth/team_evaluation/models.py:1–5`: contratti di preregistrazione, nessun dato raccolto, risultato o autorità di rilascio. Sono infrastruttura di studio; non evidenza di superiorità/complementarità uomo+AI.
- `packages/ntruth/reality_gate/v9.py:275–298,377–383`: distinzione esplicita tra completezza dei predicati e autorizzazione; nessun trust verifier indipendente presente, HOLD canonico con riferimenti placeholder. I checksum dei placeholder dimostrano consistenza di contratto, non autenticità scientifica.
- `data/training/p0-alpha/manifest.json`: 2000 train/300 validation sintetici, famiglie separate, SYN_G1_UNANCHORED, substantive_training_allowed=false e scientific_validation_status=NOT_STARTED. `TEST_REAL_PLACEHOLDER.README.md` dichiara test reale vuoto. Non scambiare questa numerosità con campione reale.
- `benchmarks/README.md:3–5`: benchmark locali sintetici non dimostrano accuratezza/generalizzabilità. `benchmarks/fewshot_p0/constrained/SEMANTIC_C_REPORT.md` riporta sviluppo n=39, F1 di stadio circa .103–.325, schema 100%; documenta correttamente che schema valido non implica contenuto corretto. Il GO_LORA_P0 storico in fondo non prevale sul HOLD corrente.
- Confidence/OOD v9 sono funzioni pure e contratti: `evaluate_ood` è usato solo nel modulo/esportazioni e test, non ho trovato un detector integrato nella pipeline principale. `OODTrigger()` restituisce IN_PROFILE perché tutti i segnali default sono NOT_OBSERVED; ciò non è una misura sperimentale di in-distribution. L'astensione legacy dichiara esplicitamente calibrazione appresa/conformal/OOD futuri in `packages/ntruth/calibration/abstention.py:1–6`.
- `docs/status-snapshot.md` contiene paragrafi storici ormai contraddetti da aggiornamenti più sotto (portabilità Python risolta e nuovi predicati gate v9 presenti). Utile come registro, meno affidabile come snapshot sintetico: leggere codice e aggiornamenti correnti insieme.

## Verifiche effettuate

Eseguita selezione pytest **143 test, tutti passati** (exit 0): `test_confidence_records`, `test_team_evaluation_protocol`, `test_team_evaluation_freeze_gate`, `test_reality_gate_v9`, `test_training_dedup_split_integrity`, `test_prd_v8_training_reality_gate_boundary` in `tests/unit/`.

Eseguite separatamente le due riproduzioni numeriche sopra, senza modifiche ai test o sorgenti. La selezione copre contratti e invarianti ingegneristici; non è l'intera suite né una nuova validazione su dati reali. Non verificati payload locali ignorati, corpus esterni o artefatti di training fuori repository. Nessuna conclusione circa contaminazione o gold in tali ambienti.

## Priorità

Correggere e verificare indipendentemente la metrica falsa sicurezza e la selezione delle soglie con tie prima di usare artefatti di calibrazione per decisioni. Mantenere HOLD scientifico finché esistano realmente riferimento indipendente, annotazioni/adjudication, split e preregistrazione congelati: tali blocker sono dichiarati e coerenti con la natura delle evidenze presenti.
