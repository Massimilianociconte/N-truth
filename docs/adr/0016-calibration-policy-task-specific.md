# ADR-0016 — Calibration policy: task-specific o UNQUALIFIED

**Status:** accepted
**Date:** 2026-08-25
**Scope:** PRD v9 §26.9 (calibration), §24.8, NFR-44; `packages/ntruth/confidence/`

## Context

NFR-44: la confidenza del modello è task-calibrated oppure esplicitamente
unqualified. La machinery `ConfidenceRecord` (packages/ntruth/confidence/) è
stata introdotta nella baseline unificata v9 insieme a metriche di calibrazione,
risk–coverage e stati OOD. Il rischio scientifico è duplice: (a) mostrare
all'utente probabilità prodotte da score non calibrati per quel task, generando
false certainty; (b) fissare soglie decisionali usando dati di test o challenge,
contaminando la misura.

## Decision

1. **Calibrazione task-specific obbligatoria per mostrare probabilità.** Un
   valore numerico probabilistico può essere mostrato all'utente solo se esiste,
   per quella combinazione (task, profilo, versione schema/theory/rules,
   backbone/artifact, decoding/prompt), una calibrazione documentata con
   dataset/split, metodo, e metriche riportate. Non esiste calibrazione
   "ereditata" tra task o riutilizzabile per default.
2. **Altrimenti `UNQUALIFIED`.** In assenza di calibrazione idonea, ogni
   ConfidenceRecord emesso porta qualificazione `UNQUALIFIED`; l'UI non deve
   presentare il valore come probabilità calibrata né usare semantica visiva di
   certezza (coerente con ADR-0018).
3. **Threshold solo su development.** Qualsiasi soglia decisionale
   (risk-coverage operating point, cutoff di abstention) è selezionata e
   riportata esclusivamente su dati development. TEST ed EXTERNAL_CHALLENGE non
   sono mai eleggibili per la scelta di soglie; il loro uso a posteriori è solo
   misurazione.
4. **Ricalibrazione obbligatoria** dopo cambio di backbone artifact, prompt/
   decoding, theory/profile pin che influenzi gli score; la calibrazione è un
   artefatto versionato con lineage, non una proprietà eterna del modello.
5. Gli stati OOD/profile-shift attivano abstention e degradano la qualificazione;
   non vengono mai ricondotti silenziosamente dentro il profilo.

## Consequences

- Onestà incerta: molte superfici mostreranno stati qualitativi invece di
  numeri; è intenzionale.
- Costo sperimentale aggiuntivo: ogni uso sostanziale richiede un pilot di
  calibrazione task-specific (PRD v9 Appendice D.2).
- Le soglie cambiano fra profili: confronti trasversali di "confidenza" non sono
  ammissibili senza rianalisi.

## Alternatives considered

- **Temperature scaling globale unico riusato su tutti i task:** rifiutato; lo
  shift di task invalida la calibrazione e produce false certainty con vene
  quantitative.
- **Nascondere sempre la confidenza:** rifiutato; elimina il valore della
  selective prediction dove la calibrazione esiste e impedisce lo studio di
  risk–coverage (PRD §24.8).
- **Soglie tarate su TEST per "sfruttare" i dati:** vietato per costruzione;
  contaminerebbe ogni valutazione successiva (anti-leakage, NFR-18).

## Review trigger

Nuovo ADR se emerge un metodo di calibrazione cross-task con evidenza di
trasferibilità validata esternamente, o se la policy UNQUALIFIED risulta
aggirabile in qualche surface; altrimenti revisione alla prima campagna di
calibrazione reale completata.
