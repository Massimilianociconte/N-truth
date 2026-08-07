# DRIVER / ARRIVE / EDA crosswalk v0.1-draft

Stato: **crosswalk informativo non approvato**. N-Truth è un progetto indipendente:
non è un prodotto NC3Rs, non certifica conformità DRIVER/ARRIVE, non riproduce le
risorse e non implica endorsement. Il crosswalk deve essere revisionato dal
Methodology lead prima di qualunque claim pubblico di mapping.

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

## 5. Registry operativo

Template per ogni item:

```yaml
crosswalk_id: CW-0001
standard: DRIVER
standard_version: pending_review
official_url: pending_review
accessed_at: null
item: pending_review
relation: requires_user_judgement
ntruth_artifact: null
ntruth_version: null
adaptation_note: null
test_ids: []
scientific_owner_role: null
last_reviewed_at: null
status: DRAFT
```

I valori `pending_review` impediscono di scambiare il template per un mapping
approvato. URL, versione e condizioni di riuso devono essere verificati dalla fonte
ufficiale al momento della review; i riferimenti correnti sono elencati nel
[registry scientifico](scientific-references.md).

