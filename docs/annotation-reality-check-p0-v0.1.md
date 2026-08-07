# Annotation Guideline — Reality Check P0 v0.1

**Stato:** bozza operativa per reality check (3–5 prova → 10–20 formal)  
**Non è gold. Non autorizza training. Non sostituisce**  
[`annotation-guideline-v0.1.md`](annotation-guideline-v0.1.md) (guideline completa PRD).  
**Owner richiesti:** annotation lead, wet-lab reviewer, data steward.  
**Congelamento:** solo dopo trial interno 3–5, revisione feedback e (consigliato) audit multi-agente.

## Scopo di questa fase

Verificare se lo schema P0 **rappresenta esperimenti reali** con carico annotativo
sostenibile, prima di:

- raccogliere 10–20 reality-check formali;
- calibration pilot 30–50;
- qualunque LoRA P0 sostanziale.

```yaml
training_execution_gate: HOLD_PENDING_REAL_ANCHOR
substantive_p0_training_allowed: false
annotation_protocol_status: REALITY_CHECK_PROTOCOL_DRAFT
real_anchor_status: NOT_STARTED
```

## Vincoli obbligatori del pilot (3–5)

1. **Fonti immutabili** — i file originali non si modificano dopo l’hash; ogni source ha
   `sha256` stabile. Correzioni di OCR/redaction → nuovo file + nuovo hash + nota.
2. **Tempi e difficoltà** — ogni annotatore registra minuti, difficoltà e campi
   problematici (`fields_unclear`, `schema_fields_missing`, `guideline_ambiguities`).
3. **Second review cieca sui campi decisivi** — il secondo revisore **non** vede le
   scelte del primario su count/relation/allocation/application finché non ha
   compilato la propria scheda decisiva; poi si confronta e si adjudica se serve.
4. **Triade distinta** — `UNKNOWN` ≠ `NOT_REPORTED` ≠ `NOT_APPLICABLE` ≠ array vuoto ≠ 0.
5. **Niente revisioni retroattive** — un cambio di guideline produce
   `guideline_version` nuova; i bundle vecchi restano con la versione usata.
6. **Pilot non entrano in train** — mai `training_eligible: true` automatico;
   promozione train solo con governance esplicita e split dedicato.
7. **Versioning obbligatorio** su ogni bundle: `guideline_version`, `schema_version`,
   `review_status` (e `annotation_status`).

### Stato consigliato dei primi bundle

```yaml
bundle_role: INTERNAL_REALITY_CHECK
gold: false
training_eligible: false
evaluation_eligible: false
annotation_status: PRIMARY_DRAFT   # o draft → primary_complete → ...
review_status: NOT_STARTED         # poi SECOND_REVIEW_PENDING / COMPLETE / ADJUDICATED
```

## Unità di annotazione

| Unità | Ruolo |
|-------|--------|
| **Real Experiment Bundle** | Contenitore di fonti + provenance + licenza |
| **Experiment Block** | Un disegno/contrasto coerente all’interno del bundle |

Un paper può produrre più Experiment Block. Non si assegna una label globale al paper.

## In scope (P0 reality check)

Annotare **solo** se esplicito o supportato da metadata strutturati:

1. **Evidence spans** (testo + coordinate o cella)
2. **Entità** (tipo + label + evidence)
3. **Conteggi** (quantifier, value/bounds, unit/scope, evidence)
4. **Fattore, livelli, endpoint** espliciti
5. **Relazioni strutturali esplicite** (`nested_in`, `derived_from`; se incerte usare
   `other_explicit` + nota, non forzare)
6. **Allocation / application** — se non dimostrati: `UNKNOWN` (non indovinare)
7. **Fonte biologica / preparazione** se nominata, altrimenti `UNKNOWN`
8. **Missing decisive fact** (una frase)
9. **Domanda minima** che discriminerebbe le alternative (una frase)
10. **Grafo alternativo** solo se due letture sono entrambe plausibili e brevi

## Out of scope (non in questa fase)

- coreference decisiva multi-frase sottile
- estimando / inference target implicito
- `n_independent` come verdetto
- pseudoreplicazione / alert scientifici finali
- DeterminabilityState completo (opzionale nota libera `notes`)
- P2, alternative graph complesse multi-documento
- `training_eligible: true`

## Principi non negoziabili

1. **Candidate facts only** — niente verdetto scientifico N-Truth.
2. **Triade assenze** (non collassare):

   | Codice | Significato |
   |--------|-------------|
   | `UNKNOWN` | il testo non permette di stabilire il valore |
   | `NOT_REPORTED` | ci si aspetterebbe il fatto ma non è nel bundle |
   | `NOT_APPLICABLE` | il campo non ha senso per questo disegno |
   | `[]` (lista vuota) | nessun candidato estratto (non “nulla manca”) |
   | `0` / valore numerico | solo se esplicito nel testo |

3. **Allocation ≠ application**.
4. **AUTHOR_ASSERTION** (“independent experiments”) non prova indipendenza.
5. **Niente inventare** da conoscenza di dominio assente dal testo.
6. **Fonti hashed e immutabili**.

## Batteria eterogenea per i primi 3–5 casi

Non cinque casi simili. Preferire:

| # | Profilo | Cosa stressa |
|---|---------|----------------|
| 1 | **Esplicito semplice** — coltura → pozzetto → cellule; trattamento al well | happy path schema |
| 2 | **Assertion ambigua** — “three independent experiments” senza meccanismo | AUTHOR_ASSERTION / UNKNOWN |
| 3 | **Multi-fonte** — Methods + caption + sample sheet | merge, conflitti leggeri |
| 4 | **Informazione insufficiente** — risposta corretta: lacuna / condizionale | missing fact, minimal question |
| 5 | **Possibile conflitto** — testo “biological replicates” vs sheet origine comune | alternative graphs, CONFLICT |

Così il trial verifica anche **incertezza, contraddizione e alternative**, non solo i casi facili.

## Metriche da registrare per ogni bundle

```yaml
annotation_minutes:        # primary
review_minutes:            # second review
adjudication_minutes:      # se serve
fields_unclear: []
schema_fields_missing: []
guideline_ambiguities: []
alternative_graphs_needed: true|false
minimal_question_useful: true|false|unknown
annotator_confidence: low|medium|high
```

Dopo i 3–5 casi rispondere esplicitamente:

1. Lo schema rappresenta i casi **senza** note libere eccessive?
2. Quali campi restano quasi sempre `UNKNOWN` / `NOT_REPORTED` / `NOT_APPLICABLE`?
3. Dove primario e revisore **divergono**?
4. Quali parti della guideline generano interpretazioni diverse?

## Workflow

```text
guideline v0.1 + template
  → 3–5 INTERNAL_REALITY_CHECK (non gold)
  → feedback reale
  → guideline v0.2 (nuova versione; bundle v0.1 immutati)
  → audit multi-agente read-only (opz. ma consigliato)
  → correzioni confermate
  → freeze v0.3
  → formal 10–20
  → calibration pilot 30–50
```

## Ruoli e second review cieca

| Ruolo | Compito |
|-------|---------|
| Annotatore primario | Compila il bundle completo |
| Secondo revisore | Compila **solo** scheda campi decisivi **senza** vedere le scelte del primario su quei campi |
| Adjudicator | Solo se disaccordo su campo decisivo |
| Data steward | Licenza, privacy, retention |

Campi decisivi: count con value; relation nested_in/derived_from; allocation/application
se non UNKNOWN; evidence che li supporta; missing decisive fact.

Procedura pratica:

1. Primario completa e imposta `review_status: SECOND_REVIEW_PENDING`.
2. Si esporta (o si copiare) la scheda decisiva **senza** le risposte del primario.
3. Revisore compila `second_review_blind.yaml` / sezione dedicata.
4. Si confronta → `review_status: SECOND_REVIEW_COMPLETE` o adjudication.

## Gate verso i 10–20 formali

Non passare alla raccolta formale finché:

```yaml
pilot_cases_completed: ">=3"          # meglio 5 se possibile
all_sources_hashed: true
second_review_completed: true         # su ogni pilot
blocking_schema_gaps: 0
guideline_major_revision_pending: false
training_eligibility_still_false: true
```

Checklist operativa:

- [ ] ≥3 (ideale 5) bundle con second review
- [ ] tutti gli `sources[].sha256` reali e file immutabili
- [ ] metriche tempo/difficoltà complete
- [ ] risposte alle quattro domande del pilot documentate
- [ ] nessun `training_eligible: true`
- [ ] nessun gap di schema **bloccante** aperto
- [ ] se serve major revision → **v0.2** prima del formal set

## Tempo target (da misurare, non da imporre)

| Attività | Indicativo |
|----------|------------|
| Intake + licenza + hash | 10–20 min |
| Evidence + entity + count | 20–40 min |
| Factor/endpoint + relations | 15–30 min |
| Second review cieca | 10–20 min |
| **Totale blocco semplice** | **~1–2 h** |

Se >3 h su P0: `difficulty: too_hard_for_p0` e restringere a un solo block / solo Methods.

## Formato artefatto

- Schema: `data/annotations/reality-check/schemas/real_experiment_bundle.schema.json`
- Template JSON/MD: `data/annotations/reality-check/templates/`
- Pilot: `data/annotations/reality-check/pilot-internal/`
- Formal 10–20: `data/annotations/reality-check/formal-10-20/` (**vuoto**)

## Collegamenti

- Guideline completa: `docs/annotation-guideline-v0.1.md`
- Piano anchor: `docs/training/human-anchored-calibration-plan.md`
- HOLD training: `docs/training/DECISION-hold-pending-real-anchor.md`
