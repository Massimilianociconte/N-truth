# DRIVER / ARRIVE / EDA crosswalk v0.2-snapshot

Stato: **snapshot strutturato non approvato; content hash pinnato dal custodian tecnico il 2026-08-27 (freeze driver-arrive-crosswalk-freeze)**
N-Truth è un progetto indipendente: non è un prodotto NC3Rs, non certifica
conformità DRIVER/ARRIVE, non riproduce le risorse e non implica alcun
endorsement, implicito o esplicito, da parte di NC3Rs. Il crosswalk deve essere
revisionato dal Methodology lead prima di qualunque claim pubblico di mapping.

## 1. Relazioni ammesse

Ogni voce usa uno dei soli valori:

- `implements`: esiste un requisito interno verificabile e una suite di mapping;
- `supports`: N-Truth espone dati o feedback utili, senza coprire l'intero item;
- `requires_user_judgement`: la decisione resta umana;
- `out_of_scope`: il requisito non appartiene al profilo dichiarato.

Una relazione non equivale a conformità. Ogni record definitivo deve includere
standard, versione/data, URL ufficiale, item/sezione, adattamento N-Truth, versione
schema/ruleset, test, ultima review e ruolo del responsabile scientifico.

## 2. Perimetro iniziale DRIVER

| Area | Relazione candidata v0.1-v1.0 | Implementazione N-Truth | Fuori dal claim corrente |
|---|---|---|---|
| Experimental unit | `supports` | fattore/contrasto, allocation, operational independence, EU e count scope-aware | certificazione DRIVER; multi-fattore validato |
| Risk of bias | `supports` | metadati minimi e alert selezionati | modulo completo di risk-of-bias |
| Experimental model | `supports` | identità, origine, preparazione/passaggio e provenance | suitability e quality attributes completi |
| Experimental procedures | `supports` | evento e livello di applicazione, lifecycle | protocol audit completo |
| Groups and exclusions | `supports` | gruppi, attrition ed `ExclusionRecord` endpoint-specifico | audit organizzativo completo |
| Data availability/presentation | `supports` | export locale, lineage, RO-Crate e distribution gate | conformità FAIR o packaging universale |

Nessuna riga è `implements` finché non esistono owner, item ufficiale preciso,
versione congelata e test di mapping.

## 3. ARRIVE ed EDA

ARRIVE ed EDA sono riferimenti metodologici soprattutto per in vivo. N-Truth può
collegare definizioni di unità sperimentale, allocazione, gruppi, esclusioni, sample
size e disegno; target inferenziale, parser multi-documento, evidence span e modello
interno restano specifici di N-Truth. Il feedback deterministico di EDA è un precedente
concettuale, non una prova di equivalenza fra domini o workflow.

Ogni mapping in vivo deve essere `out_of_scope` nel profilo D0 corrente oppure
`requires_user_judgement` finché il relativo profilo non è validato.

## 4. REMBI, ISA e OME

Gli standard di metadata restano formati/interfacce esterni. N-Truth può importare
identificatori e provenance e aggiungere fattore, allocation, contrasto, estimand,
evidence e determinability. Non dichiara compatibilità completa senza una suite di
conformance. I mapping futuri devono essere versionati e testati separatamente dal
grafo interno.

## 5. Snapshot versionato DRIVER (PRD v9 §3.5)

Lo snapshot sostituisce il vecchio template `pending_review`. Il primo pin del
content hash è avvenuto in via puramente meccanica il 2026-08-27 tramite il
meccanismo fail-closed `ExternalReferenceFreeze`
(`data_manifests/driver-arrive-crosswalk-freeze.json`, ruolo custode
`repository-maintainer`, chiusura dei diritti esterna), con checksum canonico
SHA-256 del materiale mappato (calcolato sulla chiave blocco-snapshot, escluso
il campo `content_hash` stesso): `4afcfb5b0e47ab5eee7523850685d4e35697f7aaa8f4099378a0b2419e939eb6`.
Il pin è un atto di custodia, non una validazione scientifica: lo snapshot resta
**non approvato**, la review del Methodology lead prima di qualunque claim
pubblico di mapping e l'accuratezza claim-grade delle righe restano requisiti
invariati, nessuna voce può essere promossa a `implements` e nessun claim
pubblico di mapping è ammesso finché tali chiusure esterne non sono completate.

```yaml
crosswalk_snapshot:
  crosswalk_id: CW-DRIVER-SNAPSHOT-001
  standard: DRIVER
  standard_version: LAUNCH-2026-07-23
  official_url: https://nc3rs.org.uk/driver-recommendations
  snapshot_date: 2026-08-25
  content_hash: 4afcfb5b0e47ab5eee7523850685d4e35697f7aaa8f4099378a0b2419e939eb6
  relation_types_allowed:
    - implements
    - supports
    - requires_user_judgement
    - out_of_scope
  endorsement_declared: false
  last_reviewed_by: project owner
  review_task_on_upstream_change: true
  mapped_items:
    - item: experimental unit
      relation: supports
      note: Derivation Theory assignment-anchored, fattore e count scope-aware.
    - item: randomisation/allocation
      relation: supports
      note: AssignmentEvent e allocation nel grafo; nessun audit randomizzazione completo.
    - item: replicates e reporting di n
      relation: supports
      note: CountRecord, replica hierarchy e n indipendente per claim.
    - item: exclusions/attrition
      relation: supports
      note: ExclusionRecord endpoint-specifico e attrition nei gruppi.
    - item: blinding come metadata di rigor, non derivazione di EU
      relation: requires_user_judgement
      note: Metadata dichiarato; la decisione di rigore resta umana.
    - item: sample-size justification
      relation: requires_user_judgement
      note: Precision planning supporta; la giustificazione finale è umana.
    - item: biological source e provenance
      relation: supports
      note: MaterialLineage su identità, origine e preparazione/passaggio.
    - item: data availability
      relation: supports
      note: Export locale, lineage e distribution gate; non conformità FAIR completa.
    - item: image/sample metadata minimi
      relation: supports
      note: Provenance dell'analisi delle immagini nel profilo dichiarato.
    - item: limiti di inferenza
      relation: supports
      note: Determinability claim-specific, abstention e SupportGrade espliciti.
    - item: distinzione fra record completeness e design adequacy
      relation: supports
      note: DesignDiagnosticFinding separato da AdequacyAssessment criterion-bound.
```

Il mapping esteso (ARRIVE/EDA item-per-item, REMBI, ISA, OME) resta post-Core e
richiede uno snapshot separato con hash pinnato dal custodian. Una modifica
upstream a DRIVER non aggiorna automaticamente il Rulebook: genera una review
task (`review_task_on_upstream_change: true`). I riferimenti correnti sono
elencati nel [registry scientifico](scientific-references.md).

