# Riconciliazione PRD v3 -> PRD v6 -> working tree

**Data del checkpoint:** 1 agosto 2026  
**Fonte primaria:** PRD v6 privato del project owner, conservato localmente e non
redistribuito  
**Record della fonte:** [PRD locale di riferimento](../prd/README.md)  
**Identita del PDF:** 50 pagine, 4.058.131 byte, SHA-256
`e99a660de778027301067793bf5ce8729e473a885dbd79c5c62ae728a2ad0be8`  
**Working tree osservato:** branch `codex/complete-open-source-foundation`, base
`4cfee29`, con modifiche non ancora consolidate  
**Stato del documento:** riconciliazione implementativa; non validazione scientifica,
non preregistrazione e non decisione di release.

Il PDF sorgente e materiale istruttorio locale. Nel repository pubblico fanno fede la
[specifica pubblica](public-specification-v0.1.md), gli schemi, i ruleset e i test
eseguibili. Il riferimento a un file o test indica soltanto evidenza nel working tree:
non dimostra agreement umano, validita esterna, qualita del gold o readiness di una
release.

## 1. Metodo e sette stati di riconciliazione

Sono stati letti testo, note, tabelle, esempi, figure e Appendici A-R. Le figure 1-11 e
le dodici tavole facsimile sono state controllate anche come rendering, non soltanto
tramite estrazione testuale.

Ogni requisito riceve uno dei sette stati seguenti.

| Stato | Significato probatorio |
|---|---|
| `VERIFICATO_SW` | Implementazione presente e test automatico mirato superato nel checkpoint; non equivale a validazione scientifica. |
| `IMPLEMENTATO_SW` | Codice o artefatto operativo presente, ma non verificato end-to-end in questo checkpoint. |
| `PARZIALE` | Una parte sostanziale esiste, ma manca almeno un comportamento o gate richiesto. |
| `SOLO_CONTRATTO` | Schema, interfaccia o placeholder esiste; manca un runtime o un asset scientifico utilizzabile. |
| `ASSENTE` | Nessuna implementazione pertinente individuata. |
| `GATE_UMANO` | Il requisito dipende per definizione da esperti, dati autorizzati, IAA, custodia o approvazione esterna. |
| `DEFERITO_PRD` | Il PRD vieta o sconsiglia l'attivazione nella fase corrente; l'assenza e intenzionale finche il gate non e superato. |

Quando piu stati sarebbero applicabili, la matrice usa quello che descrive il blocker
dominante e specifica nella colonna "Residuo" il software gia presente.

## 2. Errata e problemi di rendering della fonte

### 2.1 Erratum aperto sulla dimensione della feasibility

Il PRD v6 contiene un'incoerenza interna:

- nota di revisione, sezioni 14.3, 17.4, 18.3, 28.5 e 32.4 indicano
  **100-150 casi reali** per la feasibility;
- Appendice D.2 conserva **150-250 casi**.

Decisione operativa provvisoria: adottare **100-150** per il feasibility pilot, perche
e il valore ripetuto nel corpo normativo, nella roadmap e nella DoD. L'Appendice D.2 e
registrata come erratum aperto. Questa scelta non e una giustificazione statistica
della numerosita: il protocollo deve ancora essere approvato e congelato da
biostatistico, wet-lab lead ed evaluation custodian. Una revisione futura del PRD deve
correggere esplicitamente l'una o l'altra cifra.

### 2.2 Difetti editoriali non normativi

L'ispezione visuale ha rilevato che:

- le tabelle delle sezioni 9.1 e 15.6 e l'Appendice K sono renderizzate in parte come
  testo delimitato da pipe anziche come vere tabelle;
- nella Figura 11 alcune stringhe nei riquadri inferiori escono dai bordi.

Il contenuto resta recuperabile dal testo circostante. Questi difetti non cambiano
l'interpretazione adottata, ma devono essere corretti in una futura esportazione del
PRD prima di usarla come artefatto pubblico o materiale formativo definitivo.

## 3. Matrice esaustiva v3 -> v6

| Area | Baseline v3 | Decisione vincolante v6 | Conseguenza |
|---|---|---|---|
| Obiettivo finale | Programma deterministico + AI da convergere | L'AI locale resta deliverable obbligatorio; la release deterministica puo precederla | Non dichiarare "progetto completo" con il solo rules engine |
| Release strategy | Track A/B senza gate di release completamente separati | Train D (`v0.1-D` -> `v1.0-D`) e Train A (`v0.2-A` -> `v1.0-A`) | Claim e DoD devono essere distinti per train |
| Scope iniziale | Dominio in vitro ampio | Micro-dominio bootstrap: colture cellulari, well plate, un fattore, due livelli, un endpoint, riferimenti prevalentemente espliciti | Il Core non deve assorbire imaging e disegni avanzati |
| Profili schema | Schema esteso come obiettivo comune | Core Profile field-by-field, Assisted, Imaging e Advanced Design Profile stage-gated | Ogni run deve dichiarare il profilo attivo |
| Modalita d'uso | Prospettico, retrospettivo e annotativo | Prospective design diventa il wedge predefinito | Wizard, sample sheet e riconciliazione piano/esecuzione precedono il canvas libero |
| Unita sperimentale | Per fattore e contrasto | Confermata, ma `allocation_level` non basta | Derivazione vietata senza indipendenza operativa |
| Indipendenza operativa | Allocation/application separate | Aggiunti `independently_assigned`, `randomization_unit`, `independence_mechanism`, `shared_environment`, `confounded_with`, source preparation, event e timing | Il well o la parola "independent" non provano indipendenza |
| Conteggi | Declared/allocated/analyzed/observational/independent | Lifecycle completo: planned, allocated, treated, observed, excluded, analysed, declared, analytical, biological source ed effective diagnostic | Ogni conteggio deve essere scope-aware e per endpoint |
| Quantificatori | Incertezza conservata, senza tassonomia completa | `EXACT`, `LOWER_BOUND`, `UPPER_BOUND`, `APPROXIMATE`, `RANGE`, `UNKNOWN`, `NOT_REPORTED` | Limiti e silenzio non diventano valori esatti o zero |
| Attrition | Gap e conteggi parziali | `ExclusionRecord` con fase, prespecificazione, endpoint, gruppo, autore, evidenza e impatto | `analysed_n` puo variare per endpoint senza riscrivere gli altri conteggi |
| Determinabilita | Stati conservativi e alternative | Tabella normativa unica a sette stati con matrice degli output consentiti | Un singolo EU/n e ammesso solo in `DETERMINATE`; i rami solo in `CONDITIONALLY_DETERMINATE` |
| Grafo | Grafo tipizzato ricco | Core minimo esplicito; imaging e topologie avanzate sono estensioni | Il pilot iniziale valuta il Core, non l'intera ontologia |
| Evidence | Fatti, assertion, metadata, code, conferma, model, derived, conflict | Aggiunti enfasi su `PROCEDURAL_EVENT`, `IMAGE_METADATA`, sequenza e supporto decisivo | L'ordine delle frasi non prova l'ordine biologico |
| Codice statistico | Silver evidence read-only | Confermato; `declared_clustering` resta separato dall'allocazione | Nessuna formula o grouping term chiude EU/n |
| Motore | Regole deterministiche e trace | Derivation Gold separato, coverage su casi reali, count invariants e release blocker | Il 100% delle fixture sintetiche non basta |
| Statistical washing | Distinzione design/analisi | Divieto esplicito: ICC, design effect, effective sample size e mixed model non sanano la replicazione | `effective_n` resta diagnostico e separato |
| Parser AI | Contratto candidato JSON | Task P0/P1/P2 e capability L0-L3; vietato il monolite a 14 task | Si promuovono task apprendibili, non un output end-to-end unico |
| Pipeline AI | Boundary parser -> graph -> rules | Dieci stage versionati con `complete`, `partial`, `failed` | Il partial success deve preservare gli artefatti validi |
| Baseline | Few-shot e pipeline ML previste | Ladder B0-B6; B6 diventa default solo se supera B5 sui task decisivi o sul carico umano | Il backbone non puo essere hard-coded come vincitore |
| Verifier | Validazione schema/semantica generica | Hard verifier sempre attivo; semantic verifier indipendente solo sui campi critici | Lo stesso modello non puo essere unico generatore e giudice |
| Domande | Domande decisive | Template bank iniziale; free-form rinviata a P2; question usefulness su circa 50 domande | Ogni domanda deve dichiarare scenari e output che cambierebbe |
| Dataset | Fixture, parser gold, silver, synthetic, external | Sei responsabilita: Rule Fixtures, Derivation Gold, Parser Gold, silver auditato, synthetic augmentation, External Challenge | Gli errori parser e rules engine devono essere attribuibili separatamente |
| Gold prospettico | Percorso positivo | Il grafo pianificato e riconciliato post-esecuzione diventa fonte prioritaria | I partner devono registrare piano, scostamenti ed eseguito |
| Scala dati | Pilot v3 150-250; ricerca piu ampia | 10-20 bootstrap, 30-50 calibration, 100-150 feasibility, 150-500 expansion, 800-2.000 finanziato | La crescita dipende da learning curve e person-hours, non da una soglia magica |
| Doppia annotazione | Pilot integralmente doppio | 100% sui campi decisivi e test/nuovi domini; 25-40% full-double sul training; audit/adjudication stratificati | Non ogni dettaglio deve essere doppiato per default |
| Active learning | Previsto dopo set congelati | Vietato nel cold start fino a guideline, IAA, baseline e calibrazione stabili | Nessuna pre-annotazione automatica e gold promotion anticipata |
| Synthetic | Graph-to-text come supporto | Factory graph-first, gradi SYN-G0/G1/G2, lineage, round-trip, audit >=50/ciclo e mixture search | Synthetic e augmentation train-only, mai gold finale o external test |
| Facsimile | Esempi visuali richiesti | Record canonico autorevole; tavola derivata con record/render hash; correzioni vincolanti alle 12 tavole | OCR o PNG non possono diventare gold quando esiste la fonte strutturata |
| Eligibility | Licenza e split governati | `training_eligible`, `evaluation_eligible`, `release_eligible` distinti | TEST/EXTERNAL implicano training false; conflitti richiedono target specifico |
| Anti-leakage | Articolo/dataset/template | Aggiunti preprint, supplementi, laboratorio, facility, corresponding author, synthetic family e counterfactual family | Tutta la famiglia resta nello stesso leakage group |
| Fonti pubbliche | Registry e due diligence | Whitelist iniziale automatica PMC limitata a CC0/CC BY; ogni fonte silver ha task consentiti/vietati | Open access non equivale a permesso di training |
| Unit economics | Costo annotativo da misurare | Person-hours per attivita, budget low/expected/high e LOI prima della feasibility | Il volontariato non e un piano di scala |
| Governance | Review multidisciplinare | Resource Gate, data custodian, co-maintainer/PI host e autorita esterna di STOP | Il founder non puo coprire da solo regole, gold, adjudication e release |
| Persistenza | Workspace, manifest e revisioni | SQLite iniziale + blob store content-addressed; PostgreSQL solo collaborativo; graph DB solo dopo benchmark | La persistenza locale diventa requisito D0 |
| Input | Molti parser disponibili | D0 supporta solo wizard, TXT/MD e CSV semplice; codice e formati complessi sono esplicitamente sperimentali/post-stage | Disponibilita tecnica non equivale a supporto di release |
| Sicurezza ingest | Limiti, no execute e privacy | Aggiunti no-network sandbox, MIME allowlist, macro block, no scientific content nei log, retention e redaction | Ogni opt-in esteso deve restare fail-closed |
| UI | Graph/editor locale | Wizard, tabelle, albero, evidence e summary; canvas libero post-v0.1 solo se utile nei test | La UI iniziale privilegia correggibilita e basso attrito |
| Friction | Usabilita da valutare | Target <=3 domande, <=5 modifiche, <=15 minuti per caso semplice | Sono target da misurare, non risultati correnti |
| Valutazione | F1, graph metrics, agreement, utente | Decisive-edge F1, allocation/application, scenario set, astensione, risk-coverage, correction count e time-to-confirmed-graph | Exact graph match e secondaria |
| Hardware | MLX/Apple Silicon pianificato | Mac target da 24 GB; profili runtime e candidati A-E scelti da benchmark, senza peak RAM o classi dimensionali normative | Il config modello esistente e soltanto uno smoke/bootstrap riproducibile; non e la baseline scientifica |
| Roadmap | Programma ampio | Fasi 0-7 con decisione GO/REVISE/LIMIT/STOP e gate di risorse | Il completamento del codice non chiude una fase scientifica |
| DoD | Release generale | DoD separate per v0.1-D, v0.2-A, calibration, feasibility, v1.0-D e v1.0-A | Ogni claim deve nominare la milestone effettivamente soddisfatta |
| Comunicazione | Anti-overclaim presente | Naming review, no bulk-shaming e no certificazione DRIVER diventano release blocker | Nessuna scorecard pubblica automatica di paper terzi |

## 4. Matrice PRD v6 -> working tree

### 4.1 Fondazione scientifica e Train D

| Requisito v6 | Stato | Evidenza osservata | Residuo o gate |
|---|---|---|---|
| Core Profile e micro-dominio D0 | `VERIFICATO_SW` | `capabilities.py` espone il contract versionato `ntruth-core@0.1-D`; release profile e regressioni fail-closed restano separati | Serve approvazione field-by-field di wet-lab e biostatistico |
| Sette `DeterminabilityState` | `VERIFICATO_SW` | `schemas/core.py`, `graph/determinability.py`, `verifier/output_policy.py`, test sui sette stati | La tabella resta candidata finche non revisionata scientificamente |
| Indipendenza operativa | `VERIFICATO_SW` | [policy dedicata](operational-independence-policy.md), campi tri-state, mechanism, environment e invarianti nel resolver | Casi reali e approvazione field-by-field assenti |
| Conteggi lifecycle scope-aware | `VERIFICATO_SW` | `CountRecord`, `CountScope`, quantificatori, lifecycle, `ExclusionRecord`, hard verifier | Coverage end-to-end su bundle reali assente |
| Grafo tipizzato e profili | `PARZIALE` | schema e validazione ricchi; Core usabile | Confine Core/Assisted/Imaging/Advanced non ancora validato su 10-20 bundle |
| Rules engine e proof trace | `IMPLEMENTATO_SW` | `rules/`, ruleset da 32 regole, predicati e report trace | Regole critiche non hanno review esterna; Derivation Gold reale assente |
| Fixture per regola | `PARZIALE` | 128 scenari software: positive, negative, ambiguous ed exception su 32 regole; 12 casi sintetici di regressione | Non sono 30-60 fixture canoniche complete e non sono expert-reviewed |
| Derivation Gold | `SOLO_CONTRATTO` | [protocollo dedicato](derivation-gold-protocol.md), separazione concettuale e fixture sintetiche con output attesi | Il protocollo non e approvato e mancano 20+ casi con grafo confermato, expected rule output e reviewer |
| Wizard prospettico D0 | `PARZIALE` | `ProspectiveD0Workspace.tsx` raccoglie fattore, target, estimand, indipendenza e lifecycle; il compile chiama la API canonica, che restituisce capability, hard verification, audit e stato | Sessione API ancora effimera; servono QA browser/accessibilita e 5-10 utenti esterni |
| SampleSheetSpec | `VERIFICATO_SW` | `packages/ntruth/sample_sheet/` e test CSV/schema | Review domain/data engineer e prova in laboratorio assenti |
| Methods/design statement e report positivo | `IMPLEMENTATO_SW` | `design/`, `reporting/positive.py`, HTML/JSON/RO-Crate | Review scientifica/linguistica e golden v6 completi assenti |
| Correzioni e revisione umana | `IMPLEMENTATO_SW` | JSON Patch, ledger, undo/redo, ricalcolo, candidate export | Non sostituisce doppia annotazione/adjudication; studio utente assente |

### 4.2 Train A, parser e verifier

| Requisito v6 | Stato | Evidenza osservata | Residuo o gate |
|---|---|---|---|
| Stage contracts e partial success | `VERIFICATO_SW` | `parser_ai/stages.py`: 10 envelope, provenance, error taxonomy, status complete/partial/failed | Orchestrazione runtime a stadi non completa |
| Parser candidate-only | `VERIFICATO_SW` | `CandidateGraphSet`, export MLX `parser_candidate_graph_v6`, metriche v6 e regressioni rifiutano determinability/verdict e il task legacy | Nessuna baseline validata su real gold |
| Routing/segmentazione deterministica | `PARZIALE` | parser text/section/block e baseline estrattiva | P0 AI Methods-only e coverage report non validati |
| Evidence/entity/count baseline | `PARZIALE` | estrattori deterministici e tabelle con coordinate | Nessun evidence-span/entity/count benchmark reale |
| Procedural events | `SOLO_CONTRATTO` | stage e campi di schema presenti | Estrattore/metriche event-order non dimostrati |
| Decisive coreference | `PARZIALE` | coreference rules-only e schemi | Nessun decisive-coreference set o F1 reale |
| Candidate graph set e alternative | `IMPLEMENTATO_SW` | graph builder, alternative e conflict records | Scenario-set accuracy non misurata |
| Hard verifier sempre attivo | `VERIFICATO_SW` | `verifier/hard.py`, output policy e test invarianti/count | Va dimostrato in ogni entry point e su dati reali |
| Semantic verifier indipendente | `SOLO_CONTRATTO` | trigger/risultato previsti nei contratti | Nessun secondo modello o passaggio indipendente implementato/validato |
| Template question bank | `PARZIALE` | elicitazione e domande conservative presenti | Banca v6 versionata e studio usefulness su circa 50 domande assenti |
| Baseline B0-B5 | `PARZIALE` | B0 deterministico, parser contract, runtime MLX/few-shot configurabile | Harness comparativo unico e risultati su snapshot reale assenti |
| Modello B6 addestrato/distillato | `DEFERITO_PRD` | pipeline locale disponibile, nessun peso N-Truth nel repository | Vietato fino a Core, gold, baseline, licenze, split e Resource Gate |
| Calibrazione/astensione del parser | `SOLO_CONTRATTO` | moduli di temperature scaling/abstention e metriche candidate-only | Nessun validation gold o risk-coverage scientifico |

### 4.3 Dati, eligibility, synthetic e persistenza

| Requisito v6 | Stato | Evidenza osservata | Residuo o gate |
|---|---|---|---|
| Parser Gold distinto dal Derivation Gold | `VERIFICATO_SW` | `training/gold.py` conserva doppia submission/adjudication e proietta soltanto il grafo candidate-only nel target MLX | Nessun corpus umano disponibile e contratto Derivation Gold dedicato ancora assente |
| Training/evaluation/release eligibility | `VERIFICATO_SW` | tre flag, invarianti TEST/EXTERNAL e manifest MLX | Permessi reali per asset assenti |
| Anti-leakage esteso | `VERIFICATO_SW` | split tokens per articolo, preprint, supplemento, dataset, lab, facility, synthetic/counterfactual family | Audit su un corpus reale non possibile |
| Deduplica e snapshot | `IMPLEMENTATO_SW` | `training/dedup.py`, `splits.py`, manifest/checksum e export MLX | Nessuno snapshot reale autorizzato |
| Synthetic Data Factory | `ASSENTE` | fixture e smoke sintetici isolati, ma nessuna Design DSL/factory G0-G2 | Specifica, renderer, round-trip, audit >=50 e mixture search mancanti |
| Facsimile record/render | `SOLO_CONTRATTO` | requisiti nel PRD e record strutturati riutilizzabili | Nessun renderer automatico con record_hash/render_hash e visual report |
| Registry fonti/licenze/privacy | `PARZIALE` | manifest, governance, DMP/registry template, fail-closed training | Due diligence per ogni asset e data owner reali assenti |
| SQLite applicativo | `VERIFICATO_SW` | `storage/` con migrazioni idempotenti, FK, transazioni, revisioni/audit append-only | Pack/unpack e migrazione di workspace reali ancora da specificare |
| Blob store content-addressed | `VERIFICATO_SW` | layout `sha256/<2>/<digest>`, scrittura atomica, dedup e tamper detection; ingest conserva `sources/` legacy | Policy di retention/cancellazione e stress test su volume reale assenti |
| Corpora/modelli fuori da Git | `IMPLEMENTATO_SW` | `.gitignore`, manifest e directory locali dedicate | Verifica pre-release continua necessaria |

### 4.4 Sicurezza, UI, valutazione e governance

| Requisito v6 | Stato | Evidenza osservata | Residuo o gate |
|---|---|---|---|
| D0 TXT/MD/CSV e profilo esteso esplicito | `VERIFICATO_SW` | `ReleaseProfile`, allowlist e registry parser | Il claim pubblico deve continuare a distinguere supportato da sperimentale |
| No-execute, macro, MIME, limiti, traversal | `IMPLEMENTATO_SW` | `ingest/safety.py`, code parser read-only, boundary output/workspace fuori dalle sorgenti e security test | Audit indipendente e sandbox OS-level non dimostrati |
| No silent cloud/local-first | `IMPLEMENTATO_SW` | core senza dipendenze di rete, API loopback e test offline | Telemetria/log/retention vanno verificati nella release candidata |
| Privacy e redaction pre-export | `PARZIALE` | scanner, policy e readiness fail-closed | Nessun DMP approvato, DPIA finale o dataset reale valutato |
| UI wizard/tabelle/albero/evidence | `PARZIALE` | UI locale; il wizard D0 e collegato alla compilazione canonica senza fallback silenzioso e registra per riga day/operator/incubator pseudonimi per il gate di confondimento | Accessibilita, friction budget e usability non misurati; sessione/export prospettici non sono ancora durevoli |
| Canvas libero | `DEFERITO_PRD` | nessun requisito D0 di canvas autorevole | Aggiungerlo solo se riduce tempo/errori in uno studio utente |
| Benchmark harness B0-B6 | `PARZIALE` | metriche, MLX runtime e test software separati | Config unica, snapshot reale, intervalli e report comparativo assenti |
| Calibration 30-50 | `GATE_UMANO` | guideline e protocollo sono bozze | Servono dati autorizzati, due annotatori, IAA, tempi e adjudication |
| Feasibility 100-150 | `GATE_UMANO` | piano aggiornato in questo checkpoint | Erratum da ratificare, protocollo congelato, LOI/budget e Resource Gate |
| External challenge | `GATE_UMANO` | [protocollo real-only in bozza](external-challenge-protocol-draft.md), leakage groups e custodia descritti | Set reale chiuso, custode, preregistrazione e laboratorio unseen assenti |
| DRIVER/ARRIVE crosswalk | `PARZIALE` | [crosswalk v0.1-draft](driver-arrive-crosswalk.md) informativo e non certificante | Item/versioni ufficiali congelati, owner e suite di mapping assenti |
| Resource Gate e STOP authority | `GATE_UMANO` | [checklist e decision record](resource-funding-gate.md) | Nessuna LOI, nomina, budget o STOP authority dimostrati dal repository |
| Model/Data/System Card | `PARZIALE` | bozze Data/System Card; nessun modello scientifico | Card finali richiedono snapshot, metriche e release AI reale |
| Portabilita/performance | `PARZIALE` | CI macOS/Linux e performance test deterministici | Nessuna misura completa p95/RAM/parser chunk sulla release candidata |

## 5. Copertura dei requisiti funzionali v6

| IDs | Stato dominante | Riconciliazione |
|---|---|---|
| FR-001 - FR-009, fondazione D0 | `PARZIALE` | Core, determinability, EU/n condizionale, sample sheet, report, audit, lifecycle e compile UI/API hanno implementazioni; persistenza della sessione e validazione scientifica restano incomplete. |
| FR-010, TXT/MD/CSV | `VERIFICATO_SW` | Profilo D0 e parser minimi sono esercitati. |
| FR-011, Methods/caption | `PARZIALE` | Segmentazione rules-only presente; A0 valutato assente. |
| FR-012 - FR-013, multi-artifact e codice read-only | `IMPLEMENTATO_SW` | Bundle e code parser esistono nel profilo sperimentale. |
| FR-014 - FR-016, JATS/PDF/DOCX/XLSX/metadata | `DEFERITO_PRD` | Parser tecnici esistono in parte, ma sono correttamente esclusi dal profilo D0; metadata standard completi assenti. |
| FR-020 - FR-022, evidence/entity/count/factor espliciti | `PARZIALE` | Baseline deterministica e contratti esistono; nessuna A0 scientificamente valutata. |
| FR-023 - FR-029, relazioni/eventi/allocation/independence/conflict/coreference | `SOLO_CONTRATTO` | Copertura software disomogenea; nessuna capability L2/L3 validata. |
| FR-030, hard verification | `VERIFICATO_SW` | Verifier strutturale e output matrix presenti. |
| FR-031, semantic verification | `SOLO_CONTRATTO` | Nessun verifier indipendente operativo. |
| FR-032 - FR-035, evidence/alternative/patch/question/audit | `PARZIALE` | Componenti presenti, ma flusso A1 e studio umano assenti. |
| FR-040, fixture/counterfactual | `PARZIALE` | Scenario software presente; manca Design DSL e set canonico revisionato. |
| FR-041 - FR-046, synthetic factory/grade/ablation | `ASSENTE` | Nessuna factory o ablation reale; non va simulata con smoke fixture. |
| FR-050 - FR-051, licenza e eligibility | `VERIFICATO_SW` | Contratti e fail-closed software presenti. |
| FR-052 - FR-054, stand-off/doppia/active learning | `DEFERITO_PRD` | Export candidate stand-off esiste; doppia annotazione e active learning dipendono dal pilot. |
| FR-055, JSON-LD/RO-Crate | `IMPLEMENTATO_SW` | Export presente; conformance REMBI/ISA non dichiarata. |
| FR-060 - FR-064, output positivo | `IMPLEMENTATO_SW` | Grafo, n table, classi separate, gaps e limiti parser sono rappresentati; manca review esterna. |
| FR-065, crosswalk DRIVER/ARRIVE | `PARZIALE` | Checklist informativa presente, crosswalk versionato incompleto. |

## 6. Copertura dei requisiti non funzionali v6

| ID | Stato | Evidenza/gap principale |
|---|---|---|
| NFR-01 local-first | `IMPLEMENTATO_SW` | Core locale; nessun servizio remoto necessario. |
| NFR-02 log privacy | `PARZIALE` | Policy dichiarata; serve audit di tutti i log/runtime. |
| NFR-03 provenance | `IMPLEMENTATO_SW` | Schemi, report e lineage; completezza su casi reali non provata. |
| NFR-04 determinismo | `IMPLEMENTATO_SW` | Rules engine e fixture riproducibili. |
| NFR-05 portabilita | `PARZIALE` | CI Apple/Linux configurata; release candidate non verificata in questo checkpoint. |
| NFR-06 no silent cloud | `IMPLEMENTATO_SW` | Nessun fallback remoto nel core. |
| NFR-07 parser safety | `IMPLEMENTATO_SW` | No execute, macro block, allowlist e limiti; security review indipendente assente. |
| NFR-08 partial success | `VERIFICATO_SW` | Envelope tipizzati; orchestrazione completa ancora parziale. |
| NFR-09 context integrity | `PARZIALE` | Coverage contract presente; nessun benchmark long-context reale. |
| NFR-10 resource budget benchmark-derived | `PARZIALE` | Runtime Resource Manager e contratti di profilo presenti; manca ancora un benchmark end-to-end firmato sul Mac target da 24 GB. |
| NFR-11 rule p95 <2 s | `PARZIALE` | Test budget sintetico; benchmark release/hardware non congelato. |
| NFR-12 wizard <500 ms | `ASSENTE` | Nessuna misura browser affidabile individuata. |
| NFR-13 parser <15 s/chunk | `GATE_UMANO` | Nessun parser candidato valutabile. |
| NFR-14 friction | `GATE_UMANO` | Nessuno studio utente. |
| NFR-15 lingua | `PARZIALE` | UI/report IT/EN; parser reale English-first non disponibile. |
| NFR-16 schema evolution | `VERIFICATO_SW` | Versioni e migrazioni SQLite; policy completa dei breaking change da consolidare. |
| NFR-17 split consistency | `VERIFICATO_SW` | Family/leakage invariants testate. |
| NFR-18 gold integrity | `VERIFICATO_SW` | Gold/candidate/synthetic authority separate nei contratti. |
| NFR-19 statistical integrity | `PARZIALE` | Invarianti effective_n presenti; review biostatistica assente. |
| NFR-20 external real-only | `GATE_UMANO` | Contratto presente, set reale assente. |
| NFR-21 accessibility | `PARZIALE` | UI strutturata; audit keyboard/screen reader assente. |
| NFR-22 resource reporting | `PARZIALE` | Logging MLX e stime; report pubblico di una release candidata assente. |
| NFR-23 view non-authority | `SOLO_CONTRATTO` | Separazione concettuale record/view; renderer facsimile autorevole assente. |
| NFR-24 anti-overclaim | `IMPLEMENTATO_SW` | Copy e documenti non certificanti; naming review esterna ancora aperta. |

## 7. Documenti derivati obbligatori

| Documento richiesto da v6 §0.4 | Stato | Artefatto o residuo |
|---|---|---|
| Core Profile Specification | `PARZIALE` | Specifica pubblica e schema; manca approvazione field-by-field. |
| DeterminabilityState Table | `PARZIALE` | Specifica, codice e test; manca review scientifica. |
| Operational Independence Policy | `PARZIALE` | [Policy dedicata](operational-independence-policy.md), schema e regressioni fail-closed; manca approvazione field-by-field. |
| Experiment Graph Schema e profili | `PARZIALE` | Schemi presenti; profile boundary non stabilizzato su casi reali. |
| Rulebook versionato | `PARZIALE` | JSON versionato e test; reviewer/date/reference per regole critiche non chiusi. |
| Derivation Gold Protocol | `PARZIALE` | [Bozza versionata](derivation-gold-protocol.md); da approvare e congelare prima della validazione del motore. |
| Annotation Guideline | `PARZIALE` | [bozza v0.1](annotation-guideline-v0.1.md), da calibrare. |
| SampleSheetSpec | `PARZIALE` | Implementazione e test; owner review assente. |
| Parser/Verifier Runtime Contract | `PARZIALE` | [contratto parser](parser-ai-contract.md) e stage code; semantic verifier incompleto. |
| Data Management Plan | `PARZIALE` | [DMP draft](data-management-plan-draft.md), non approvato. |
| License Manifest | `PARZIALE` | Schema/template presenti; manca un record per ogni futuro snapshot reale. |
| Synthetic Data Generation Specification | `PARZIALE` | [Bozza graph-first](synthetic-data-generation-specification.md); factory, audit umano e snapshot non esistono. |
| Synthetic Bias & Utility Report | `DEFERITO_PRD` | Richiesto per ogni snapshot training-approved, che non esiste. |
| Baseline & Evaluation Protocol | `PARZIALE` | Questo reconciliation record e il protocollo draft non sono una preregistrazione. |
| Validation Protocol preregistrato | `GATE_UMANO` | [bozza aggiornata](validation-protocol-draft.md), da congelare prima del test. |
| Model/Data/System Card | `PARZIALE` | Data/System Card draft; model card finale impossibile senza modello e risultati. |
| DRIVER/ARRIVE crosswalk | `PARZIALE` | [Template informativo versionato](driver-arrive-crosswalk.md); item ufficiali, owner e suite di mapping non sono ancora approvati. |
| External Challenge Protocol | `GATE_UMANO` | [Bozza real-only](external-challenge-protocol-draft.md); custode, preregistrazione e set indipendente non esistono. |
| Resource & Funding Gate | `GATE_UMANO` | [Checklist e decision record](resource-funding-gate.md); LOI, budget e STOP authority non sono acquisiti. |
| Facsimile Review Specification | `PARZIALE` | [Bozza record-to-view](facsimile-review-specification.md); manca approvazione e renderer canonico. |
| Render Manifest / Visual Consistency Report | `ASSENTE` | Nessun renderer canonico rilasciato. |

## 8. Definition of Done: stato reale

| Milestone | Stato | Perche non e chiusa |
|---|---|---|
| v0.1-D | `PARZIALE` | Software D0 consistente, ma 30-60 fixture canoniche, 20+ Derivation Gold, review scientifica e adozione esterna non sono soddisfatti. |
| v0.2-A | `PARZIALE` | Contratti e hard verifier esistono; Methods parser B0/B4, benchmark locale e conferma integrata non sono ancora valutati su gold reale. |
| Calibration pilot | `GATE_UMANO` | Nessun set reale 30-50, IAA, tempi, audit synthetic o decisione GO/REVISE/LIMIT/STOP. |
| Feasibility | `GATE_UMANO` | Nessun set 100-150, double annotation, adjudication esterna, baseline B0-B5 o Resource Gate. |
| v1.0-D | `GATE_UMANO` | Manca almeno un laboratorio pilota, review esterna, support/migration evidence e decisione di release. |
| v1.0-A | `DEFERITO_PRD` | Nessun parser L2 validato, componente N-Truth addestrato, external challenge, calibrazione o team di manutenzione. |

Release blocker ancora aperti includono gold/provenance assenti, regole critiche senza
reviewer esterno, assenza di LOI/budget, nessun external challenge custodito e nessun
confronto B5/B6. Gli invarianti software impediscono gia alcuni errori, come
`training_eligible=true` su TEST/EXTERNAL e un singolo `n` fuori dallo stato ammesso;
questa protezione non chiude gli altri blocker.

## 9. Sequenza autorizzata prima del training

1. Designare ogni asset e bundle per ruolo, autorita, licenza, privacy, split,
   eligibility, leakage group e custode.
2. Revisionare Core Profile, Operational Independence Policy, DeterminabilityState,
   SampleSheetSpec e regole principali con wet-lab e biostatistico.
3. Esplorare 10-20 bundle reali o pubblici autorizzati per verificare il micro-dominio;
   non chiamarli gold o test per default.
4. Completare 30-60 fixture canoniche e almeno 20 casi di Derivation Gold revisionati.
5. Eseguire calibration su 30-50 casi con due annotatori indipendenti, IAA prima
   dell'adjudication, tempi per campo e disagreement taxonomy.
6. Correggere schema/guideline/rulebook usando soltanto calibration; poi congelare
   protocollo, versioni, metriche, split, redirect criteria e custodia.
7. Eseguire la feasibility su 100-150 casi secondo il valore operativo provvisorio,
   con doppia sui campi decisivi e full-double stratificata.
8. Eseguire B0-B5, learning curve e audit real-only/synthetic-only/hybrid senza aprire
   test/external e senza promuovere pre-annotazioni a gold.
9. Autorizzare fine-tuning soltanto dopo tutti i gate, una decisione formale
   GO/REVISE/LIMIT/STOP e disponibilita documentata di persone, dati, compute e
   storage.

I dettagli operativi sono nella
[checklist dei primi passi umani](first-human-steps-checklist.md) e nel
[Validation Protocol draft v6](validation-protocol-draft.md).

## 10. Gap non chiudibili con altro codice in questa fase

- approvazione scientifica delle definizioni, soglie, regole e profili;
- 10-20 bundle esplorativi autorizzati e rappresentativi;
- Parser Gold e Derivation Gold reali, doppi o adjudicati dove richiesto;
- IAA, human ceiling, person-hours, determinability distribution e learning curve;
- LOI, budget, co-maintainer/PI host, data custodian e STOP authority;
- external challenge reale, chiuso, preregistrato e indipendente;
- studio di usabilita e friction budget;
- modello N-Truth addestrato/distillato, confronto B5/B6, calibrazione e card finali;
- verifica legale per ogni asset e consenso per dati non pubblici.

Questi elementi non sono "todo software". Dichiararli completati richiede evidenze
umane o sperimentali compilate, non nuovi test sintetici.
