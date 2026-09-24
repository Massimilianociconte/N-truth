# ADR-0018 — UI defaults: wizard-first, expert opt-in, semantiche neutre

**Status:** accepted
**Date:** 2026-08-25
**Scope:** PRD v9 §26.9 (UI defaults), §23.1–23.6, Appendice AL.2; desktop `apps/desktop/`

## Context

Le decisioni di default dell'interfaccia determinano chi usa bene il sistema e
chi viene indotto in errore. Il Quick Design wizard (Core Profile D0,
prospettica) è il flusso primario progettato; la vista esperta espone superfici
raw che per un utente wet-lab sono fonte di automation bias. Le semantiche
visive possono implicare approvazione o certezza scientifica (AL.2: ogni label
sintetica richiede support_profile_id, policy version, dimensioni collassate,
caveat non-probabilistico e link al dettaglio). "Massimo tre domande iniziali"
è target UX dichiarato PROVISIONAL, non limite scientifico: la coda completa
delle missing predicates resta conservata e ordinata.

## Decision

1. **Primary view = wizard D0/prospettica.** La vista di default è il wizard
   guidato per la pianificazione prospettica sul Core Profile D0; nessun JSON da
   comporre o incollare nel percorso primario.
2. **Expert view opt-in.** La vista esperta (submission raw, manipolazione
   diretta della coda, campi CLI-equivalenti) è attivabile solo esplicitamente,
   per sessione/progetto, etichettata come superficie per utenti esperti.
3. **Semantiche visive neutre.** Nessun rosso/verde di determinabilità o
   adequacy, nessuna icona di completamento celebrativo che implichi approvazione
   scientifica. Gli stati si mostrano come valori tipati espliciti
   (QUESTION/BLOCKER/REVIEW_REQUIRED/…) con caveat testuali e link al dettaglio;
   le label sintetiche seguono AL.2 e non diventano target del parser né decidono
   determinability o adequacy.
4. **Massimo 3 domande iniziali visibili, PROVISIONAL.** La coda iniziale mostra
   al più tre domande scelte per expected information gain/burden/criticality;
   è un target UX PROVISIONAL soggetto a evidenza di usabilità (§23.7 friction
   budget), non un limite informativo: tutta la coda resta ispezionabile su
   richiesta e nessuna predicate viene scartata.
5. Qualsiasi cambiamento dei default richiede evidenza di usabilità e nuovo ADR.

## Consequences

- Gli utenti esperti accettano frizione extra per raggiungere le superfici raw:
  costo volontario a protezione degli utenti non esperti.
- Coerenza obbligatoria fra copy, colori e stati tipati: ogni nuova surface UI
  passa dal vincolo di neutralità.
- La cap delle domande iniziali va rivalutata con dati reali di burden; resta
  marcata PROVISIONAL finché non esiste pilot (Appendice H).

## Alternatives considered

- **Vista esperta come default dual-pane:** rifiutato; aumenta automation bias
  e burden per il pubblico primario (wet-lab), contro §23.1 e l'appendice AM su
  automation-bias events.
- **Semantiche semaforiche (verde = design ok):** rifiutato; implica
  certificazione gradata che il sistema non fornisce e viola NFR-24/NFR-28 nello
  spirito.
- **Mostrare tutta la coda di domande subito:** rifiutato come default; urta il
  friction budget §23.7 e degrada completion quality; resta disponibile su
  richiesta esplicita.

## Review trigger

Revisione alla prima valutazione di usabilità strutturata (§23.8) o prima che i
default debbano coprire profili oltre D0; qualunque inversione di default è
nuovo ADR sostitutivo.
