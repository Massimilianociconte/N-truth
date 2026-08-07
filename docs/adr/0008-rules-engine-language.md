# ADR-0008 — Regole dichiarative versionate con predicati controllati

**Stato:** provisional<br>
**Data:** 2026-08-01<br>
**Revisione:** dopo fixture review e benchmark di manutenibilità del rulebook

## Contesto

Il rules engine deve essere deterministico, versionabile, leggibile dagli esperti e
capace di produrre proof trace. Il linguaggio di implementazione non è un principio
scientifico e può cambiare se un'alternativa migliora auditabilità senza modificare la
semantica approvata.

## Alternative

- JSON dichiarativo con predicati Python in allowlist;
- DSL N-Truth dedicato;
- tabelle decisionali compilate;
- Datalog o altro linguaggio logico;
- policy engine general-purpose;
- regole codificate direttamente in Python.

## Benchmark richiesto

Confrontare equivalenza sui fixture positivi, negativi, ambigui ed eccezioni;
completezza del proof trace; capacità di schema validation; tempo di authoring/review;
diff semantico tra versioni; sandboxing; prestazioni e facilità di migrazione. Ogni
motore deve riprodurre byte-for-byte o semanticamente gli output del ruleset congelato
su un corpus di compatibilità.

## Decisione e motivazione

La baseline usa asset JSON versionati e predicati Python registrati esplicitamente.
È semplice da ispezionare e già coperta dai test, ma resta provvisoria. Il parser AI
non può scrivere o eseguire regole; propone candidate fact che il motore consuma solo
dopo i gate previsti.

## Limiti e conseguenze

Python non è automaticamente leggibile dai reviewer scientifici e una DSL dedicata
potrebbe migliorare l'authoring. Nessuna migrazione è autorizzata senza doppia
esecuzione, verifica della proof trace e ADR sostitutivo.
