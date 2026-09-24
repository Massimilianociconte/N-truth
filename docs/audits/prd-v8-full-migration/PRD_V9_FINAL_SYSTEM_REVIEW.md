# Revisione finale di sistema — PRD v9 rispetto all’albero v8

**Data:** 2026-08-13  
**HEAD recensito:** `84983943cc702712b94097967c5dec1bb68b99c5` (e successori solo per le
chiusure engineering documentate nel resoconto)  
**Albero:** `prd-v8-full-20260808` / `codex/prd-v8-full-migration-20260808`  
**Fonte dei requisiti per questa revisione:** PRD versione 9.0  
**Contratto di implementazione vincolante nell’albero:** PRD v8.0  
**Conclusione di repository:** `IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`  
**scientific validation remains NOT_STARTED**  
**training/External Challenge remain HOLD**

Questa revisione **non** tratta CI verde come validazione scientifica. I due
contratti non sono lo stesso documento: la v9 è la specifica ufficiale da
seguire per il lavoro nuovo; l’albero implementa il kernel v8 fail-closed.

Matrice: [FINAL_IMPLEMENTATION_MATRIX.md](FINAL_IMPLEMENTATION_MATRIX.md)  
Blocker: [SCIENTIFIC_REVIEW_REGISTER.md](SCIENTIFIC_REVIEW_REGISTER.md)  
Snapshot: [status-snapshot.md](../../status-snapshot.md)

Parser machine-readable: `ntruth.governance.prd_matrix`.

---

## 1. Problemi critici

### 1.1 Nessun P0/P1/P2 di review indipendente sul kernel v8

Il Task 9 e la review commit-exact su `c120b43..8498394` chiudono con P0=0,
P1=0, P2=0. I gate engineering (contratti 6/6, pytest 3229/1 skipped, Desktop
50/50, ruff/mypy, SBOM, wheel/sdist, smoke offline) sono verdi. **Questo non
chiude la scienza.**

### 1.2 Blocker scientifici ancora aperti (non sono bug di codice)

Ogni riga `PARTIAL`/`MISSING` della matrice ha almeno un `SRR-V8-*`. I più
gravi:

| Classe | ID | Perché è critico |
|---|---|---|
| Vocabolari PRD inconsistenti | `SRR-V8-001`, `011`, `015` | Un mapping inventato rompe gold e report |
| Chiusura di profilo/topologia | `SRR-V8-008`, `012`, `014`, `017` | Partial score, aggregazione eterogenea, interferenza non enumerata |
| Evidenza esterna assente | `SRR-V8-021`, `022`, `026`, `027`, `030` | Niente Theory Reference Set, Real Anchor, gold, attestation |
| Strategy / cluster | `SRR-V8-013` | Qualsiasi soglia numerica sarebbe statistical washing |
| Piattaforma/attestazioni | `SRR-V8-028`, `029` | Hardware, a11y, sandbox e privacy non si attestano da un scan |

Il codice è già fail-closed su questi punti. Chiuderli in software senza
revisione umana sarebbe una regressione scientifica.

### 1.3 Divario contrattuale v9 (non è un crash, è un delta di specifica)

La v9 aggiunge token che **this tree does not treat as the shipped binding
kernel**:

| Token v9 | Ruolo | Stato in questo albero |
|---|---|---|
| FactorRole | Decide se un fattore può generare EU | Non è il kernel vincolante; assente come enum/gate |
| ContrastType | Tipo della domanda | Non è il kernel vincolante |
| SupportProfile | Profilo di supporto a più assi | Non è il kernel vincolante; esiste `SupportGrade` v8, bloccato da `SRR-V8-001` |
| ContrastSupportClaim | Presenza livelli / aliasing / variazione | Non è il kernel vincolante; c’è confounding/diagnostica v8 |
| MaterialLineage | Eventi SPLIT/POOL/PASSAGE con invarianti | Non è il kernel vincolante; relazioni grafo più povere |
| TeamEvaluationProtocol | H / A / H+A | Non è il kernel vincolante; non serve per Train D |

L’albero v8 **già** vieta la riscrittura silenziosa dell’EU da interferenza
(`SRR-V8-017`) e tiene la strategy su `HANDOFF_ONLY`. Non è SupportProfile, non
è FactorRole.

### 1.4 Vulnerabilità residue (engineering)

- **Directory symlink (chiusa in questo giro).** `Path.rglob` seguiva symlink di
  cartella e poteva copiare file esterni. Ora
  `discover_ingest_candidates` rifiuta file e directory symlink e
  `Project.add` lo usa.
- **API locale senza autenticazione.** Resta un rischio accettato
  loopback-only (`127.0.0.1`). Non è un bug da “aprire in LAN”.
- **Scanner privacy = detection-only** (`SRR-V8-029`). Un esito pulito non è
  attestation.
- **Niente cifratura a riposo.** FileVault resta fuori dal codice.

### 1.5 Bug scientifici *non* da “aggiustare” nel kernel v8

Payload positivi non chiusi (`SRR-V8-023`), aggregazione report (`SRR-V8-014`),
pesi di uguaglianza parziale del grafo (`SRR-V8-012`): il fail-closed è la
implementazione corretta. Inventare il default sarebbe il bug.

---

## 2. Nuove implementazioni necessarie

Due code: (A) **non implementabili ora** perché servono evidenza/revisione
umana; (B) **prossimo incremento di contratto v9**, da fare solo dopo il
freeze dei vocabolari v8, non come rinomina del kernel verde.

### 2.A Bloccate da evidenza (non codice)

1. Real Anchor e seconda review umana (`SRR-V8-022`).
2. Theory Reference Set e Derivation Gold firmati (`SRR-V8-021`, `022`).
3. Crosswalk DRIVER/ARRIVE/EDA con hash (`V8-CROSSWALK` / `SRR-V8-021`).
4. Graph Corpus reale (`V8-CORPUS`).
5. Ablation real/synthetic/hybrid su holdout reale (`V8-SYNTH-ABLATION`).
6. Validazione esterna della strategy (`V8-STRATEGY-VALIDATION`).
7. Protocollo H/A/H+A (v9) — solo prima di un *claim di utilità AI*, non per
   Train D.
8. Attestazioni privacy/licenza/contaminazione (`SRR-V8-029`).

### 2.B Incremento v9 (engineering sidecar — implementato)

Contratti eseguibili, **non** validazione scientifica. Il kernel v8 resta
vincolante per i claim già shippati.

1. Canonical Schema Registry 9.0.0 (`ntruth.schemas.v9_registry`).
2. FactorRole / ContrastType + `eu_claim_permitted`.
3. ExperimentalUnitClaim assignment-anchored + ContrastSupport.
4. MaterialLineage eventi tipizzati e invarianti di count.
5. SupportProfile writer (SupportGrade resta read-only; SRR-V8-001).
6. Safe Methods sentence-level.
7. Quick Design v9 (ruolo prima dei livelli).
8. Gate combinato `gate_experimental_unit_claim`.

**Non** è un rename del kernel v8. Strategy resta `HANDOFF_ONLY`.

---

## 3. Opportunità di ottimizzazione

1. **Un solo worktree di verità.** Questa revisione vive sull’albero
   `prd-v8-full-20260808`, non sul checkout `baseline/pre-v8`.
2. **Non ricalibrare B4 / LoRA / constrained decoding** finché HOLD resta HOLD.
3. **Desktop:** il percorso PREVIEW/CONFIRM è già neutrale e testato. Non
   reintrodurre verde = approvazione.
4. **Documenti storici.** Lasciare v3/v6/v7 sotto `HISTORICAL_NON_NORMATIVE`.
   Non “aggiornarli” al linguaggio v9.
5. **Test tautologici delle 32 regole** (fixture costruite per far scattare la
   regola). Sostituirli solo quando esiste un Theory Reference Set.
6. **Factory backend Granite/Qwen** e constrained decoding: debito Train A,
   irrilevante finché il parser non è nel prodotto e il training è HOLD.

---

## 4. Elementi ridondanti

| Elemento | Azione |
|---|---|
| Superfici `DEPRECATED_V7_ADAPTER` (`analyze-v7`, `/v7/*`) | Tenere come adapter espliciti; non cancellare |
| Ruleset/ontologia `0.1.0` | Storici immutabili; default resta `0.2.0` |
| Snapshot AA nel PRD v9 (6 agosto, HISTORICAL) | Non è lo stato di questo albero |
| PRD v8 markdown + PDF v9 | v9 = requisiti nuovi; v8 = implementazione; non fondere i file |
| Demo desktop + wizard D0 | Già separati nel flusso v8 guidato; non reintrodurre “Studio microbioma” come report |
| Strategy module | Non implementare; `HANDOFF_ONLY` è la feature |
| Worktree di prova temporanei | Già rimossi; non ricrearli |

Niente va cancellato “per pulizia” se è pin di riproducibilità o adapter
versionato.

---

## 5. Raccomandazione strategica — 4 MISSING e 48 PARTIAL

Parser: `disposition_for()` in `ntruth.governance.prd_matrix`.

### 5.1 I quattro MISSING

| ID | Disposition | Cosa fare | Cosa non fare |
|---|---|---|---|
| `V8-CROSSWALK` | `EXTERNAL_EVIDENCE_ONLY` | Un custode congela snapshot DRIVER/ARRIVE/EDA/REMBI/ISA/OME con hash e mapping (`SRR-V8-021`). Il registry dei ruoli di riferimento resta il confine engineering. | Inventare hash o dichiarare conformance DRIVER |
| `V8-CORPUS` | `EXTERNAL_EVIDENCE_ONLY` | Campagna di annotazione governata, doppia review, split. I gate `NO_CORPUS` restano. | Promuovere sintetici o trial 003 a corpus |
| `V8-SYNTH-ABLATION` | `EXTERNAL_EVIDENCE_ONLY` | Dopo holdout reale e gold: esperimento preregistrato real-only / synthetic-only / hybrid (`SRR-V8-022`, `026`, `030`). | Correre un’ablation sui 2000 P0-alpha e chiamarla scienza |
| `V8-STRATEGY-VALIDATION` | `KEEP_FAIL_CLOSED` | Lasciare `HANDOFF_ONLY`. Serve validazione statistica esterna (`SRR-V8-013`, `030`). | Abilitare raccomandazioni di test |

Nessuno dei quattro può diventare `IMPLEMENTED` da un agente di coding.

### 5.2 I 48 PARTIAL

Tutti sono **contratti eseguibili + blocker**. Strategia: non “finirli”,
**avanzarli per classe di blocker**.

1. **Errata e vocabolari PRD** (`SRR-V8-001`–`011`, `015`, `018`–`020`, `023`,
   `031`). Lavoro umano di schema/teoria. Il codice rifiuta già conversioni
   crociate. Priorità: `SupportGrade` (`001`) e count labels (`011`) prima di
   qualsiasi writer v9.
2. **Chiusure di topologia** (`008`, `012`, `014`, `017`). Restano
   NON_EXHAUSTIVE / review-required. Non introdurre pesi o precedenze.
3. **Evidenza e persone** (`021`, `022`, `026`, `027`). Seconda review umana
   di 003, poi 3–5 reality check, poi formal 10–20. In parallelo: Theory
   Reference Set con un metodologo.
4. **Piattaforma e attestation** (`028`, `029`). Misure hardware/a11y e review
   di sicurezza indipendenti. Il fix symlink di questo giro riduce il rischio
   ingest; non sostituisce `SRR-V8-029`.
5. **Challenge / domande** (`024`, `025`). Tenere l’ordinamento Quick Design
   etichettato UNREVIEWED.
6. **Evaluation HOLD** (`030`, cluster `013`). Interfacce pronte; risultati
   scientifici assenti. Non pubblicare scorecard.

**Regola operativa:** un `PARTIAL` cambia stato solo con un record append-only
nel Scientific Review Register e, se tocca claim derivati, re-derivazione. Mai
patch del `DerivedClaim`.

### 5.3 Prossimo passo (non IAI grande)

1. Tenere HOLD e `HANDOFF_ONLY`.
2. Usare questo albero come unica baseline engineering.
3. Lavoro umano: second review 003 + freeze vocabolari SRR.
4. Solo dopo: incremento kernel v9 (FactorRole / registry), non un rename.

---

## 6. Resoconto di implementazione (questo giro)

### Implementato (classe engineering, senza chiusura scientifica)

- `ntruth.ingest.safety.discover_ingest_candidates` e uso in `Project.add`:
  rifiuto dei symlink di file e di directory; niente `rglob` che esce dal
  workspace.
- Test ostili: cartella symlink verso l’esterno; source directory che è
  symlink.
- `ntruth.governance.prd_matrix`: parser della matrice finale, pin
  36/48/4, disposition dei 4 MISSING, detector di false claim v9.
- Test `tests/unit/test_prd_v9_final_disposition.py` che chiama le funzioni
  shippate sulla matrice e su questo documento.
- Questo documento, collegato da `docs/README.md`.

### Rimasto PARTIAL / MISSING e perché

I 48 `PARTIAL` e i 4 `MISSING` **non** sono stati ribaltati a `IMPLEMENTED`.
I blocker `SRR-V8-*` sono invariati. Non è stato creato Real Anchor, gold,
crosswalk hashato, ablation, né abilitata la strategy.

### Pin scientifici (invariati)

- `IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`
- scientific validation remains NOT_STARTED
- training/External Challenge remain HOLD

### Gate engineering (ri-eseguiti su questo albero)

| Gate | Esito |
|---|---|
| `check_prd_v8_contracts.py` | 6/6 PASS, `scientific_readiness=HOLD` |
| pytest | exit 0, 100%; 3237 collected (3236 + 1 skip); +7 test nuovi |
| Desktop | 50/50 PASS; Vite build PASS (1786 moduli) |
| ruff / format / mypy | PASS (195 file mypy) |
| repository policy | no finding; detection-only; non attestation |
| SBOM | PASS (CycloneDX, 280 component) |
| wheel + sdist + smoke offline | PASS |

Nessuna riga della matrice è stata cambiata di stato. Nessun HOLD è stato aperto.
