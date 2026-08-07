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
| SRR-0003 | 2026-08-07 | §7.15 | Formulazione delle clausole di Derivation Theory oltre gli esempi PRD | Teoria in versione `0.1.0` dichiarata **non revisionata**; nessuna clausola aggiuntiva viene introdotta oltre gli esempi espliciti del PRD. Aggiornamento FASE 2: prodotto l'artefatto `theories/derivation-theory-0.1.0.json` (9 clausole famiglie A-G, enunciati normativi = testo PRD §7.15 verbatim; ID `DT-EU-COUNT-01`/`DT-ANALYTICAL-01` sono convenzioni della migrazione perché il PRD non mostra ID per le famiglie C e F), il loader `packages/ntruth/derivation_theory/` e il Theory Reference Set `tests/theory_reference/` (tutte le voci `SCIENTIFIC_REVIEW_REQUIRED`); nessun comportamento derivato dalla teoria è attivo nel default della pipeline | PENDING_REVIEW | — |
| SRR-0004 | 2026-08-07 | §0.3 | Casi limite della politica di assegnazione SupportGrade | I casi limite non coperti esplicitamente dal PRD v8.0 restano non decisi: nessun grading automatico oltre i casi determinati; esito conservativo in attesa di revisione | PENDING_REVIEW | — |
| SRR-0005 | 2026-08-07 | §0.4, App. R.1, App. A | Insieme normativo `SupportGrade` | Il PRD pubblica tre elenchi divergenti (§0.4: 8 valori; R.1: 8 valori in parte diversi; esempi Appendice A/§10.2 aggiungono `NOT_SUPPORTED`). Fail-closed: l'enum `SupportGrade` accetta l'unione verbatim dei tre elenchi (15 token); nessun valore inventato; la revisione deve scegliere l'insieme canonico | PENDING_REVIEW | — |
| SRR-0006 | 2026-08-07 | §7.9, App. P.1, App. AE.1 | Denominazione del Canonical Count Registry | §7.9 usa `*_unit_count`/`diagnostic_effective_n`; Appendice P.1 e gli esempi usano `planned_n`/`effective_n_diagnostic`. Fail-closed: entrambi i vocabolari sono accettati in lettura; per Appendice AE.1 (immutabilità degli output storici e degli stable_id v7-era) la serializzazione del registro v6 resta sui valori v6 congelati, mentre il naming §7.9 è esposto solo dal wire v8 (`COUNT_KIND_V8_WIRE`, `V8CountRecord`); pattern `INDETERMINATE` | PENDING_REVIEW | — |
| SRR-0007 | 2026-08-07 | §10.4, App. A | Token `report_resolution_state` dell'esempio Appendice A | L'Appendice A usa `MULTIPLE_PLAUSIBLE_GRAPHS` a livello report: è uno stato di determinabilità claim-level, fuori dal vocabolario §10.4. Fail-closed: l'enum `ReportResolutionState` contiene solo i 6 valori §10.4 e rifiuta il token dell'esempio; il test di conformance registra il finding | PENDING_REVIEW | — |
| SRR-0008 | 2026-08-07 | §10.7 vs App. AC | Esempio ScenarioCoverage privo dei requisiti AC | §10.7 mostra `omitted_dimensions` ABSENT_EXPLICIT senza evidence e `caveat` NOT_APPLICABLE senza rationale, violando le regole Appendice AC. Fail-closed: le regole AC sono applicate in modo stretto; i due sotto-campi dell'esempio sono rifiutati dal contratto e il test di conformance documenta la discrepanza | PENDING_REVIEW | — |
| SRR-0009 | 2026-08-07 | §0.3, §9.1, App. A/AG | Insieme normativo `SourceClass` | §0.3 descrive le classi in prosa senza elenco di token. Fail-closed: enum chiusa sui soli token verbatim presenti negli esempi normativi (PUBLISHED_METHODS, SAMPLE_METADATA_EXECUTED, PROSPECTIVE_PRIVATE, POST_CUTOFF_PUBLIC, LEGACY_PUBLIC); nessun token inventato per le classi solo descritte (instrument log, metadata, chiarimento, output del modello) | PENDING_REVIEW | — |
| SRR-0010 | 2026-08-07 | §10.2 vs App. A/AF | Denominazione campi DerivedClaim | §10.2 usa `inferential_query_id` e `determinability`; Appendice A/AF usano `query_id` e `determinability_state`. Fail-closed: entrambe le denominazioni sono accettate via alias; la forma canonica serializzata è quella Appendice A/AF | PENDING_REVIEW | — |
| SRR-0011 | 2026-08-07 | §10.4 | Precedenza di aggregazione ReportResolutionState | Il PRD elenca i 6 stati ma non definisce la precedenza di aggregazione. Fail-closed: precedenza `INVALID > CONFLICTED > PARTIAL_WITH_ACTIONABLE_GAPS > MULTI_SCENARIO/OUT_OF_SCOPE > COMPLETE` implementata in `aggregate_report_resolution`; insieme claim vuoto rifiutato; il summary non sostituisce mai gli stati dei singoli claim | PENDING_REVIEW | — |
| SRR-0012 | 2026-08-07 | §7.15, §10.11, NFR-33 | Mappatura regola↔clausola nel ruleset `ntruth-core-0.3.0` | La scelta della clausola §7.15 per ciascuna delle 32 regole è un giudizio scientifico: fail-closed, l'intera mappatura (27 regole collegate) è dichiarata non revisionata. Le 5 regole senza clausola difendibile (`GEN-005`, `GEN-007`, `GEN-009`, `MIC-006`, `SC-004`: confounding, conflitti, adeguatezza modello statistico, reporting adequacy — ambiti §7.18/§7.19 senza clausole §7.15) restano nel ruleset disabilitate con `theory_clause=null` e `theory_status=SCIENTIFIC_REVIEW_REQUIRED` (mai eliminate; audit esplicito nel motore) e sono release blocker per §10.11 fino a revisione. La clausola `DT-EXP-02` (famiglia E) è dichiarata coverage gap nel ruleset. `ntruth-core-0.2.0` resta il default della pipeline; il conformance harness `scripts/conformance_check.py` riporta i blocker | PENDING_REVIEW | — |

## Storico delle revisioni

_Nessuna revisione registrata. Le voci entrano in questo registro in stato
`PENDING_REVIEW` e vengono aggiornate solo a seguito di revisione umana._
