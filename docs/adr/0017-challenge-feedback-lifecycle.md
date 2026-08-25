# ADR-0017 — Challenge feedback: no item-level mentre ACTIVE, aggregato solo RETIRED_DIAGNOSTIC

**Status:** accepted
**Date:** 2026-08-25
**Scope:** PRD v9 §26.9 (challenge feedback), §24.14, Appendice AG, NFR-20/NFR-41; `packages/ntruth/governance/challenge_lifecycle.py`

## Context

Il valore misurativo dell'External Challenge dipende dal fatto che gli item non
 siano stati visti. Il feedback item-level (punteggi per caso, pass/fail, diff,
diagnostiche puntuali) rilasciato mentre una versione di challenge è attiva
permette overfitting, prompt/rule tuning mirato e ricostruzione del corpus.
La lifecycle implementata (`ChallengeLifecycleState`: FROZEN → ACTIVE →
RETIRED_DIAGNOSTIC → PUBLIC_ARCHIVE, transizioni fail-closed) già marca il
feedback item-level come `PROHIBITED_WHILE_ACTIVE`. Manca la decisione esplicita
su cosa si può pubblicare e su quando gli item escono dalla rotazione.

## Decision

1. **Nessun feedback item-level mentre ACTIVE.** Nessun punteggio per item,
   nessun verdetto per singolo caso, nessuna diagnosticca puntuale verso
   partecipanti o pubblico finché la versione è `ACTIVE`. L'esito comunicato al
   submitter è limitato all'acquisizione/custodia (ricevuto, accettato in
   round), mai alla correttezza.
2. **Feedback solo aggregato, solo RETIRED_DIAGNOSTIC.** Statistiche aggregate
   (distribuzioni di errore per classe, copertura, metriche preregistrate senza
   identificazione degli item) sono pubblicabili soltanto quando lo stato della
   versione è `RETIRED_DIAGNOSTIC`; gli item ritirati diventano corpus
   diagnostico e non sono riutilizzabili come item attivi in round futuri.
3. **Rotation policy.** Ogni versione di challenge ha:
   - durata massima dichiarata al momento del freeze;
   - ritiro anticipato obbligatorio su trigger documentato di rischio di
     esposizione (fuga, pubblicazione post-cutoff compromessa, segnali di
     tuning); il rischio è documentato, non assunto assente (NFR-41);
   - preregistrazione di metriche ed esclusioni prima dell'attivazione;
   - custodia immutable con chain-of-custody e contamination attestation
     (Appendice AG).
4. Nessun risultato di challenge può essere usato per selezionare schemi,
   regole, prompt o modelli: è misurazione, non ottimizzazione.

## Consequences

- Gli team esterni ricevono segnali poveri nel breve periodo: iterazione lenta,
  ma misura non contaminata.
- Serve disciplina amministrativa su freeze/rotation/attestazioni; i costi sono
  espliciti e registrati nella lifecycle.
- Il corpus diagnostico cresce a ogni ritiro e alimenta residual audit, non
  release.

## Alternatives considered

- **Dashboard continuo item-level:** rifiutato; è la definizione stessa di
  leakage e abilita gaming diretto.
- **Mai ritirare gli item (challenge permanente):** rifiutato; l'esposizione
  cumulativa cresce senza gestione e rende insostenibile la claim di "non visti".
- **Pubblicare gli item dopo il primo uso:** rifiutato; crea rischio di
  contaminazione pretraining per i round successivi.

## Review trigger

Nuovo ADR prima di qualsiasi modifica ai tipi di feedback pubblicabili o alla
policy di rotation; revisione obbligatoria al primo ritiro reale di una versione
ACTIVE, per verificare che la policy sia operativa e non solo dichiarativa.
