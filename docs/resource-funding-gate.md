# Resource & Funding Gate v0.1-draft

Stato: **checklist vuota; non costituisce una decisione GO**. Il gate deve essere
firmato dai ruoli responsabili prima della feasibility e nuovamente prima di una
release scientifica.

## Persone e autorità

- [ ] micro-dominio e claim approvati;
- [ ] wet-lab reviewer con ore e responsabilità concordate;
- [ ] biostatistico con ore e responsabilità concordate;
- [ ] adjudicator indipendente per i disaccordi critici;
- [ ] autorità esterna con potere di `STOP`;
- [ ] co-maintainer o PI host;
- [ ] data custodian per External Challenge;
- [ ] owner per DMP, licenze/privacy e incident response.

Un nome suggerito, una bozza email o una conversazione non vale come commitment. La
prova resta in un registro privato con ruolo, periodo, ore, deliverable e stato della
LOI; il repository pubblico non contiene contatti personali.

## Dati e governance

- [ ] 10-20 bundle bootstrap autorizzati;
- [ ] Parser Gold e Derivation Gold separati;
- [ ] DMP, License Manifest e privacy/DPIA review approvati;
- [ ] leakage groups e custodia test/external congelati;
- [ ] double annotation/adjudication pianificata e finanziata;
- [ ] policy di retention, revoca e cancellazione;
- [ ] nessun diritto presunto dal solo accesso pubblico.

## Budget e capacità

Il foglio privato deve riportare scenari low/expected/high per acquisizione, screening,
annotazione primaria, doppia, adjudication, data engineering, QA, compute, storage,
supporto e manutenzione. Per ogni voce si registrano tariffa equivalente, ore cash,
ore in-kind, contingenza e gap da finanziare.

- [ ] spazio disponibile con safety floor;
- [ ] compute riproducibile per baseline B0-B6;
- [ ] backup e custodia separata;
- [ ] person-hours per 50, 100, 250 casi e successivi;
- [ ] learning-curve checkpoint e stop-loss;
- [ ] costo del review time incluso, non soltanto del training.

## Decision record

```yaml
gate_id: RESOURCE-GATE-YYYY-MM
scope: calibration|feasibility|release
decision: GO|REVISE|LIMIT|STOP
approved_claim: null
limitations: []
open_blockers: []
evidence_refs: []
approver_roles: []
decided_at: null
next_review_at: null
```

`GO` richiede tutti i blocker risolti. `REVISE` richiede un nuovo gate; `LIMIT`
restringe formalmente dominio, output o scala; `STOP` interrompe il lavoro che dipende
dal gate senza cancellare audit e risultati già prodotti.

