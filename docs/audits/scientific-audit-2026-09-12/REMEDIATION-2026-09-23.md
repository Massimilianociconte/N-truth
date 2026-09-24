# Remediation dell'audit scientifico 2026-09-12 — record del 2026-09-23

Questo documento registra le correzioni applicate ai difetti riprodotti
dall'audit del 12 settembre 2026 ([REPORT.md](REPORT.md)) e ai difetti nuovi
trovati durante la revisione successiva. Il report originale resta invariato
come snapshot storico.

**Confine:** sono correzioni di correttezza del software (metriche, parser,
gate strutturali, verifier, calcolatore di potenza). Non chiudono alcun blocker
scientifico: validation `NOT_STARTED`, training `HOLD_PENDING_REAL_ANCHOR`,
Reality Gate `HOLD`, SRR-V8-008 e gli altri SRR restano aperti. Nessun gold,
anchor o reviewer indipendente e stato simulato.

Metodo: ogni difetto e stato prima riprodotto sul worktree corrente (gli
script in `evidence/` riproducevano ancora A01-A05 e A09), poi corretto con un
controesempio conservato come test di regressione. I test sono controlli
d'ingegneria con oracoli indipendenti dove possibile (tabella di verita,
G*Power 3.1, Connor 1987, scipy per le distribuzioni); non sono evidenza
scientifica.

## Esito per finding

| ID | Esito | Correzione | Regressione |
|---|---|---|---|
| A01 | CORRETTO | `confidence/records.py`: il numeratore conta gli errori (`label == 0`) ad alta confidenza; codifica 1=corretto documentata | `test_confidence_records.py` (tabella di verita corretto/errato x alta/bassa) |
| A02 | CORRETTO | `scientific/design_matrix.py`: la variazione intra-blocco usa solo livelli registrati; `unassigned_units` esplicito; assegnazione incompleta limita a `PARTIALLY_SUPPORTED` | `test_design_matrix.py` (rimuovere informazione non aumenta mai il supporto) |
| A03 | CORRETTO (parte strutturale) | alias per-fattore (`aliased_with`); nuovo fatto `constant_within_levels_of`: un fattore costante dentro livelli multi-unita di un altro fattore (trattamento per gabbia, topi come unita) limita a `PARTIALLY_SUPPORTED` | `test_design_matrix.py`, `test_v9_surface.py` |
| A04 | CORRETTO | `parsers/tabular.py`, `parsers/pdf.py`: nomi di colonna liberi anche rispetto ai nomi originali; warning sui rinomini | `test_parser_fidelity_audit.py` |
| A05 | CORRETTO | `training/calibration.py`: soglie solo ai confini dei pareggi, regola `>=` esplicita, rischio dichiarato in-sample | `test_mlx_training_pipeline.py` |
| A06 | CORRETTO | `verifier/v8.py`: `DUPLICATE_FACT_CONFLICT` quando `predicate_values.interference_status` diverge dal causal context | `test_prd_v8_derivation_runtime.py` |
| A07 | CORRETTO al confine canonico | `verifier/v8.py`: `COMPLETE_UNDER_DECLARED_ASSUMPTION_SET` richiede `BOUNDED_SEARCH_COMPLETED_NO_COUNTEREXAMPLE` | `test_prd_v8_derivation_runtime.py` |
| A08 | CORRETTO | `graph/index.py`: se un target non ha assegnazione il conteggio di gruppo resta `None` (limite inferiore, non esatto) | `test_prd_v3_graph_design.py` |
| A09 | CORRETTO | `parsers/pdf.py`: troncamento righe/colonne dichiarato con dimensioni originali; documento `PARTIAL` | `test_parser_fidelity_audit.py` |
| A10 | CORRETTO | `parsers/pdf.py`: ogni pagina senza testo e elencata (bianca o scansione: OCR/ispezione), documento `PARTIAL` | `test_parser_fidelity_audit.py` |
| A11 | CORRETTO | `scripts/check_normative_examples.py`: zero esempi = `NO_COVERAGE`, mai `PASS`; registry non importabile = errore; `--require-coverage` per i gate di release | `test_normative_examples_checker.py` |
| A12 | CORRETTO | README: `ntruth quick-design reality-gate`; ogni comando `uv run ntruth ...` nei documenti principali e verificato contro la CLI reale | `test_documented_cli_commands.py` |
| SCI-L01 | MITIGATO | `verifier/v8.py`: `PREDICATE_DOMAIN_MISMATCH` per predicati consumati come booleani o token di interferenza | `test_prd_v8_derivation_runtime.py` |

### A07: perche solo al confine del verifier

`schemas/coverage.py` appartiene alla chiusura di identita dell'evaluator
pinnato (`reviewed-evaluator-registry-0.1.2`): modificarne il sorgente
invalida tutti i pin DERIVATION e richiede una transizione auditata
(`docs/audits/prd-v8-full-migration/EVALUATOR_PIN_TRANSITIONS.md`). Tutti i
`ScenarioCoverage` che raggiungono il ReportBundle passano da
`verify_v8_pipeline_request`, che ora rifiuta la completezza senza ricerca di
controesempi. Il vincolo va comunque spostato nello schema alla prossima
transizione auditata del registry, cosi che il contratto serializzabile non
ammetta lo stato.

### A03: cosa resta aperto

Il controllo resta combinatorio sulle partizioni registrate. Non rileva
confondimenti lineari generali e non riceve i coefficienti del contrasto
(`contrast_type` e una famiglia, non il contrasto): la stimabilita di un
contrasto sotto un modello dichiarato e un compito del biostatistico
(HANDOFF_ONLY). `blocks = None` significa blocking non documentato (al massimo
`PARTIALLY_SUPPORTED`); un disegno senza blocchi per costruzione si dichiara
con un unico blocco che contiene tutte le unita.

Il controesempio `nested_confounding` di `evidence/reproduce_design.py` (quattro
batch con una sola unita ciascuno) resta `SUPPORTED_WITHIN_RECORDED_DESIGN`: con
una unita per batch il batch coincide con l'unita e non e un cluster; la sua
varianza rientra in quella fra unita. Il nuovo controllo scatta quando un
livello del fattore di raggruppamento contiene due o piu unita (gabbia,
cucciolata, piastra trattate per intero). Lo script storico si interrompe ora
sulla soglia `None` di A05: e il comportamento corretto (nessuna soglia rispetta
il rischio massimo) e lo script resta invariato come evidenza datata.

## Difetti nuovi trovati e corretti

| ID | Difetto riprodotto | Correzione | Regressione |
|---|---|---|---|
| N01 | CSV con righe vuote (tipiche degli export): riga fantasma di celle vuote e stato `PARTIAL` spurio; una riga vuota iniziale faceva fallire il parse benche il gate D0 accettasse il file | righe interamente vuote saltate come gia per XLSX; i warning conservano il numero di riga della sorgente; il troncamento colonne marca `PARTIAL` | `test_parser_fidelity_audit.py` |
| N02 | `power.distributions`: la cache dei quantili chi2 era indicizzata da `round(df)`; dopo un df non intero (17.3) la CDF t noncentrale per df=17 sbagliava di ~0.007 | chiave sul df esatto | `test_power_audit_regressions.py` |
| N03 | `t_ppf(df, p)` con p < 0.5 invertiva una funzione decrescente e sollevava sempre errore | simmetria `-t_ppf(df, 1-p)` | idem |
| N04 | t a due campioni e z a due proporzioni: con ratio 1 la soluzione poteva essere sbilanciata (d=2: 6/5) e con ratio 2 non rispettava il rapporto (64/127) | ricerca su n1 con n2 = ceil(ratio * n1), come G*Power 3.1 | idem |
| N05 | McNemar: una sola varianza (sotto H1) al posto delle due di Connor (1987); potenza sovrastimata, N sottodimensionato | formula di Connor; psi=0.3, OR=2 -> 234 coppie | idem |
| N06 | Poisson: varianza per unita calcolata ad allocazione 1:1 anche con ratio != 1; con ratio < 1 il piano era sottodimensionato | Var[log RR] = 1/(n1 mu0) + 1/(n2 mu1) con l'allocazione reale; potenza raggiunta calcolata, non assunta uguale al target | idem |
| N07 | Binomiale esatto: la bisezione assume potenza monotona; il test esatto ha potenza a dente di sega (p0=.5, p1=.7, potenza .9: restituiva 70, il minimo e 65) | scansione lineare del minimo; il piano dichiara l'N "stabile" (potenza >= target su una finestra di 30 N successivi) | idem |
| N08 | Logistica (Hsieh 1998) e Poisson senza limiti di validita esposti; `paired_correlation` accettato e ignorato in silenzio | caveat espliciti nel piano: covariata continua con OR per SD (non esposizione binaria), assenza di sovradispersione, campo non usato | idem |
| N09 | chi2 noncentrale approssimata con una normale per lambda > 400 (errore di CDF ~4e-3); F noncentrale con `exp(-lambda/2)` in underflow oltre lambda ~1490; `beta_inc` in overflow con parametri grandi | mistura di Poisson sommata dalla moda in spazio logaritmico; fattore della beta incompleta in log-space | idem (valori scipy congelati) |
| N10 | Pipeline legacy (`pipeline.py`): un file `PARTIAL` era escluso dal gate "output utilizzabile" (fonte unica -> abort con messaggio fuorviante) ma il suo contenuto entrava comunque nel Document IR, e il report si dichiarava `complete` anche con contenuto troncato | `PARTIAL` e utilizzabile come contenuto, marca il report `partial` e aggiunge un limite esplicito (il contenuto mancante non e assente); l'astensione resta invariata | `test_parser_fidelity_audit.py` |

Verifica numerica aggiuntiva (fuori dai test, con scipy 1.18): quantili t, chi2
e F entro 1e-6; t noncentrale entro 5e-4 (tolleranza dichiarata del modulo);
chi2 e F noncentrali entro ~1e-12 fino a lambda = 6000; beta incompleta entro
~2e-13 fino a a = 3000.

## Non coperto da questa remediation

- Nessun blocker scientifico chiuso; nessuna evidenza di accuratezza,
  calibrazione, accordo fra esperti o utilita H+A.
- `REPORT.md` rimanda a un `VERIFICATION.md` che non esiste nel folder
  dell'audit (esistono `VALIDATION.md`, `SCIENCE.md`, `SURFACES.md`): lasciato
  invariato perche snapshot storico.
- Tipizzazione semantica completa dei predicati (tipo, dominio, regola di
  evidenza per ogni predicato della Theory): richiede un contratto versionato e
  una transizione di pin; il verifier copre solo i predicati consumati come
  booleani o token.

## Secondo giro (2026-09-24): prestazioni, UI desktop, simulazione

| ID | Difetto riprodotto | Correzione | Regressione |
|---|---|---|---|
| N11 | Il client desktop accettava solo i pin di conformance del registry 0.1.0 (rulebook `3e8cdb25…`, evaluator registry `303a61eb…`): dopo le transizioni 0.1.1/0.1.2 ogni anteprima guidata reale falliva con "malformed PRD v8 build response", mentre i test desktop restavano verdi su una fixture ferma a 0.1.0 | pin aggiornati in `apps/desktop/src/api.ts`; fixture rigenerata da `scripts/regenerate_desktop_fixtures.py`; test anti-drift che confronta pin client, checksum del bundle e fixture con il backend | `tests/unit/test_desktop_contract_pins.py` |
| N12 | Con un ReportBundle v8 aperto la navigazione mostrava viste v7 che non cambiavano il contenuto e badge calcolati dalla demo sintetica ("3 blocchi", "3 bloccanti") come se appartenessero al progetto dell'utente | viste non applicabili disabilitate con spiegazione; badge solo nel workspace v7 reale; "Progetto" resta la pagina corrente | `app-restore.test.tsx` |
| N13 | La voce di navigazione attiva non era mai evidenziata (CSS su `aria-current="true"`, markup con `"page"`); etichette troncate ("Esperi…") dai badge testuali; card di stato rientrate dal padding di default della lista; asterisco dei campi obbligatori D0 su riga propria e campi senza `aria-required` | selettori CSS corretti, badge che vanno a capo senza troncare l'etichetta, padding azzerato, etichetta e asterisco inline con `aria-required` | verifica visiva e `vitest` |
| N14 | Test desktop instabili sotto carico: il checkpoint autosalvato (debounce 400 ms) in localStorage passava da un test al successivo | `localStorage`/`sessionStorage` puliti dopo ogni test | suite desktop sotto carico |
| N15 | Il proxy del dev server Vite non inoltrava `/v9` (card Reality Gate v9 rotta in sviluppo) | proxy `/v9` aggiunto | — |
| N16 | Simulazione Monte Carlo: il pattern sbilanciato dei cluster (`counts_per_parent`) era scelto da un hash SHA-256 del percorso, fisso fra le simulazioni, invece che dall'indice ordinale dichiarato: i due bracci potevano ricevere composizioni diverse di cluster | indice ordinale della EU nel proprio braccio e indice fra fratelli, come da contratto `parent p -> pattern[p % len]` | `test_power_simulation.py` |
| P01 | Una conferma guidata richiedeva 20,5 s (22 esecuzioni della pipeline, 144 preflight del bundle); via API circa 34 s perche la serializzazione della risposta riverificava tutto da capo | scope di verifica per operazione (`ntruth/verification_scope.py`): contenuto byte-identico gia verificato nella stessa operazione non viene rieseguito; chiavi = checksum ricalcolati, mai identita o checksum dichiarati; fallimenti mai memorizzati; fuori scope comportamento invariato. Conferma 6,0 s, API 8,2 s, browser 5,2 s | `tests/unit/test_verification_scope.py` (anche contenuto manomesso con checksum ricalcolato) |

Il costo residuo della conferma e nella rivalidazione dei `KnowledgeValue` al
boundary di serializzazione (`schemas/knowledge.py`) e in
`revalidate_instances="always"` (`schemas/kernel.py`): entrambi i moduli sono
nella chiusura pinnata dell'evaluator e richiedono una transizione auditata.

Verifica numerica aggiuntiva della simulazione: su tre disegni gerarchici
bilanciati la potenza Monte Carlo (4000 simulazioni) coincide con la potenza
analitica del t test sulle medie EU entro 2 errori Monte Carlo.

Osservazioni di prodotto non corrette (richiedono decisioni di design): la coda
di domande e i claim del report v8 arrivano in inglese dentro la UI italiana e
mostrano identificativi interni (`SRR-V8-025`, `assignment_separability_support`)
alla persona primaria wet-lab; i pulsanti disabilitati del wizard non spiegano
quale campo manca.

## Terzo giro (2026-09-24): pseudoreplicazione e falsi positivi

| ID | Difetto riprodotto | Correzione | Regressione |
|---|---|---|---|
| N17 | Falso negativo di pseudoreplicazione: `model_accounts_for_assignment()` accetta un effetto casuale per un livello **superiore** all'unita sperimentale. Con trattamento assegnato alla coltura, analisi sulle cellule e solo `(1\|donor)`, GEN-002, CC-001, MIC-003, MIC-004, SC-001, ANI-001 e ANI-003 venivano soppresse (`EXCEPTED`) anche se le cellule della stessa coltura restavano trattate come indipendenti | nuovo predicato `model_accounts_for_experimental_unit()`; ruleset successore `ntruth-core@0.3.0` (default) con eccezione stretta nelle sette regole di sottocampionamento e versioni di regola incrementate. `0.2.0` resta byte-identico (SHA fissato in test) e un progetto fissato a 0.2.0 riproduce il report golden byte per byte. GEN-009, il cui testo parla di "unita o livelli superiori", resta invariata | `tests/unit/test_rules_strict_model_exception.py`, `test_rules_contract.py`, golden parametrizzato per versione |
| N18 | L'estrattore dei termini del modello contava frasi di disegno ("per/for X", "nested within X") e perdeva quasi tutte le forme reali: `random intercept for mouse`, `(1\|animal_id)`, `(1\|Mouse/Cell)`, `(1 + time\|subject)`, `random = ~1\|animal`, "X was included as a random effect", liste coordinate ("litter and cage" → solo cage). Un termine perso produce un falso allarme; un termine inventato sopprime un alert vero | pattern specifici del modello (effetti casuali per/di X, "X incluso come effetto casuale", formule lme4/nlme, errori standard clusterizzati), identificatori normalizzati (`animal_id` → animal), negazioni prima e dopo la menzione escluse, niente "per/for" o "nested within" generici; lettura dell'intero paragrafo | `tests/unit/test_model_term_extraction.py` (22 casi, positivi e negativi) |
| N19 | Diagnostica cluster del power planner: `effective_n_diagnostic = n_EU/DEFF` e `clustered_total_diagnostic = ceil(n_EU·DEFF)` mescolavano unita e osservazioni (128 colture × 100 cellule, ICC 0,05 → "n efficace 21,5" invece di 2151 osservazioni indipendenti equivalenti) | conteggi in osservazioni: totale `n·m`, efficace `n·m/DEFF` (sempre tra n e n·m) | `test_power_planner.py::test_cluster_diagnostics_are_counted_in_observations_not_eu` |
| F01 | Mancava la quantificazione del costo della pseudoreplicazione | `ntruth.power.pseudoreplication`: alpha effettiva **esatta** di t a due campioni / ANOVA a una via sulle osservazioni sotto intercetto casuale bilanciato (integrale 1D via decomposizione beta-gamma, Simpson adattivo globale con budget). Esposta nel piano (`naive_false_positive_rate` + sensitivity sull'ICC), in `POST /v1/power/pseudoreplication-risk` e in `ntruth power false-positive`. Senza ICC dichiarata solo la griglia, mai ICC = 0 | `test_pseudoreplication_false_positive.py`, `test_power_api.py` |

| N20 | D0: se anche una sola riga non riportava una dimensione di contesto (per esempio `day_id`), il controllo di confondimento saltava la dimensione in silenzio, anche quando le righe dichiarate separavano perfettamente i due livelli (sconosciuto trattato come assenza) | logica comune `_confounding_patterns`; confondimento dichiarato solo con dimensione completa (invariato), altrimenti avviso `confounding_undeterminable_missing_values` con le righe mancanti | `test_prospective_d0_compiler.py::test_missing_context_values_make_confounding_undeterminable_not_absent` e controesempio con valore condiviso |
| F02 | Il D0 mostrava `effective_n NOT_CALCULATED` senza alcuna indicazione del costo di analizzare le righe come indipendenti | card desktop on demand (nessuna chiamata automatica) che invia unita allocate e righe per unita a `/v1/power/pseudoreplication-risk` e mostra la griglia ICC; righe escluse ignorate, unita condivise tra livelli o chiavi mancanti non producono numeri | `PseudoreplicationRiskCard.test.tsx`, verifica nel browser (2 piastre × 2 pozzetti: 5,1-13,1 %) |

Validazione numerica di F01: 14 configurazioni confrontate con una quadratura
scipy indipendente sulla variabile R ~ Beta (differenza massima 1,5·10⁻¹¹) e 9
con Monte Carlo a 200k repliche (|z| ≤ 2,1); casi estremi (2000 unita × 1000
osservazioni) in pochi millisecondi. Con m non intero la formula usa gradi di
liberta reali ed e dichiarata come approssimazione bilanciata.

Decisione scientifica documentata (N17): per un contrasto tra unita
sperimentali analizzato su osservazioni piu fini, la dipendenza da
rappresentare e quella entro l'unita sperimentale (Lazic 2010; Aarts et al.
2014; Lazic, Clarke-Williams e Munafo 2018). Un termine per un livello
superiore o intermedio non la rappresenta. La modifica va nella direzione
conservativa (piu alert, tutti con conferma umana) e resta
`candidate_pending_external_review` come il resto del ruleset.
