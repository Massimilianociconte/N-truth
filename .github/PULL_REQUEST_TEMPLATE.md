## Cosa cambia

<!-- Problema, soluzione e impatto utente. -->

## Contratti e rischio scientifico

- [ ] Nessun cambiamento semantico
- [ ] Schema/grafo
- [ ] Ruleset/classi di alert
- [ ] Parser AI
- [ ] Dati/licenze/privacy

Versioni aggiornate e compatibility note:

- [ ] Theory ↔ Rulebook closure preservata o migration/versione documentata
- [ ] Determinability ↔ adequacy separation verificata (`DETERMINATE` non è approval)
- [ ] Claim/count query-scoped e semantica open-world preservati
- [ ] Nessuna patch diretta dei claim derivati; eventuale RuleChallenge ricalcola
- [ ] Adapter v7 qualificati con `DEPRECATED_V7_ADAPTER`

## Verifica

<!-- Elencare i comandi realmente eseguiti. -->

- [ ] Ruff e format
- [ ] Mypy
- [ ] Pytest
- [ ] Test/build UI
- [ ] Build/distribution/SBOM
- [ ] PRD v8 examples, schema and architecture truth
- [ ] Theory ↔ Rulebook conformance e PRD-example conformance
- [ ] ScenarioCoverage, count invariants e Reality Gate v8

## Dati e sicurezza

- [ ] Non include credenziali, dati personali, corpus, checkpoint o file sorgente non redistribuibili
- [ ] Gate repository `NO_CORPUS` eseguito; esito non descritto come attestation
- [ ] Le fixture sono sintetiche oppure hanno manifest/licenza/review espliciti
- [ ] I limiti e i gate ancora aperti sono documentati

Reviewer richiesti: software / wet-lab / biostatistica / governance.
