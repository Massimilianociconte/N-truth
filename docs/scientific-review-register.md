# Scientific Review Register — Migrazione PRD v8.0

**Stato del registro:** attivo
**Data apertura:** 2026-08-07
**Branch di migrazione:** `migration/prd-v8-scientific-contract`
**Baseline pre-migrazione:** `baseline/pre-v8-migration-20260807` (snapshot del working tree v7-era)

## Scopo

Questo registro applica la politica **fail-closed** della migrazione PRD v8.0:
ogni decisione scientifica che **non è determinabile dal testo normativo del
PRD v8.0** non viene inventata, estrapolata o dedotta da prassi v7. Al suo
posto il contratto corrispondente viene congelato in uno stato
`SCIENTIFIC_REVIEW_REQUIRED` e registrato qui, in attesa di revisione umana
esperta.

Regole operative:

1. Nessun comportamento scientifico nuovo entra nel codice senza una voce di
   questo registro (o un riferimento esplicito a una sezione PRD v8.0 che lo
   determina completamente).
2. Gli stati validi sono: `PENDING_REVIEW`, `APPROVED`, `REJECTED`.
3. Una voce passa a `APPROVED` solo con revisione umana registrata (campo
   `Revisore` valorizzato); fino ad allora il comportamento fail-closed
   corrente resta l'unico comportamento lecito.
4. Ogni modifica ai contratti congelati richiede una nuova voce o
   l'aggiornamento di una voce esistente con tracciabilità della decisione.

Registro istituito da [ADR-0013](adr/0013-prd-v8-scientific-contract-migration.md).

## Registro

| ID | Data | Sezione PRD v8.0 | Argomento | Comportamento fail-closed corrente | Stato | Revisore |
| --- | --- | --- | --- | --- | --- | --- |
| SRR-0001 | 2026-08-07 | §8.8 | Specifica esatta di uguaglianza/scoring dei grafi | Specifica **congelata**: nessuna implementazione nuova o modifica allo scorer finché la specifica esatta non è approvata; lo scorer esistente resta l'unico riferimento | PENDING_REVIEW | — |
| SRR-0002 | 2026-08-07 | §11.5 | Valori-soglia del floor statistico per pochi cluster | Placeholder `WITHHELD_INSUFFICIENT_CLUSTER_SUPPORT`: nessuna soglia numerica viene dichiarata o applicata; le valutazioni che richiederebbero la soglia restano trattenute | PENDING_REVIEW | — |
| SRR-0003 | 2026-08-07 | §7.15 | Formulazione delle clausole di Derivation Theory oltre gli esempi PRD | Teoria in versione `0.1.0` dichiarata **non revisionata**; nessuna clausola aggiuntiva viene introdotta oltre gli esempi espliciti del PRD | PENDING_REVIEW | — |
| SRR-0004 | 2026-08-07 | §0.3 | Casi limite della politica di assegnazione SupportGrade | I casi limite non coperti esplicitamente dal PRD v8.0 restano non decisi: nessun grading automatico oltre i casi determinati; esito conservativo in attesa di revisione | PENDING_REVIEW | — |

## Storico delle revisioni

_Nessuna revisione registrata. Le voci entrano in questo registro in stato
`PENDING_REVIEW` e vengono aggiornate solo a seguito di revisione umana._
