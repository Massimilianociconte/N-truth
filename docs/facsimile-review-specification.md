# Facsimile Review Specification v0.1-draft

Stato: **bozza tecnica, renderer canonico non ancora implementato**. Owner richiesti:
Annotation lead e biostatistico; ogni release richiede anche un reviewer di
leggibilità. Le tavole sono viste derivate, non record annotativi.

## 1. Autorità e separazione

- fonti e record canonico sono immutabili e content-addressed;
- evidence span, grafi, count, alternative, conflitti e gold vivono nel record;
- il facsimile è generato dal record e non riceve gold manuale;
- una correzione modifica il record tramite audit e rigenera la vista;
- OCR e testo estratto dal PNG sono test di consistenza, non fonti di verità;
- quando il testo originale esiste, il parser primario non apprende dal raster.

Ogni immagine deve essere marcata `real`, `synthetic` o `illustrative`. Hash e
timestamp dimostrativi devono riportare chiaramente `placeholder`.

## 2. Render manifest minimo

```yaml
render_id: NTR-RENDER-0001
source_record_id: NTR-REC-0001
source_record_hash: sha256:<digest-reale>
render_template: methods-annotation-board
render_version: 1.0.0
synthetic_notice: true
illustrative_hashes: false
panels:
  - source_evidence
  - candidate_relations
  - adjudicated_gold
  - uncertainty
  - conflicts
  - provenance
validator_results:
  record_view_field_match: 1.0
  count_consistency: PASS
  gate_consistency: PASS
  forbidden_manual_gold: PASS
render_hash: sha256:<digest-del-render>
```

Il manifest è calcolato sul record canonico e sull'esatto file renderizzato. Il
`render_hash` non entra nel record sorgente, evitando dipendenze circolari.

## 3. Gate record-to-view

Prima della review umana devono passare:

1. corrispondenza di ogni valore visualizzato al record hash;
2. ricalcolo di formule e conteggi dal record;
3. scope visibile per ogni `n`;
4. distinzione visuale fra candidate, confirmed/adjudicated e rejected;
5. conservazione di `null`, `UNKNOWN`, `NOT_REPORTED`, bounds e conflitti;
6. legenda, palette e template versionati;
7. coerenza di split, training/evaluation eligibility e synthetic notice;
8. confronto automatico fra testo atteso ed estratto, senza autorità dell'OCR;
9. assenza di valori aggiunti soltanto nella grafica.

Qualunque blocking error impedisce la pubblicazione della tavola.

## 4. Review scientifica e di leggibilità

Il reviewer scientifico verifica allocation/application, operational independence,
source count versus EU count, topology, count scope, alternative e overclaim. Il
reviewer di leggibilità verifica che legenda, diff, evidence locator, conflitto e
stato di eligibility siano comprensibili senza interpretare i colori da soli.

Il report registra `reviewer_role`, template/versione, record/render hash, finding,
severity, decisione e correction ID. Le decisioni ammesse sono
`ACCEPT`, `ACCEPT_WITH_REVISIONS`, `REVISION_REQUIRED`, `MAJOR_REVISION` e
`BLOCKED`.

## 5. Usi consentiti e vietati

Consentiti: guideline, onboarding, calibrazione annotatori, specifica UI, test di
completezza del record, documentazione pubblica, futura valutazione multimodale
separata e generazione di domande/report da un grafo confermato.

Vietati: OCR come annotazione, valori illustrativi come external validation, split di
tavole correlate fra train/test, gold presente solo nell'immagine, rimozione grafica
di conflitti o blocking flag e training del parser primario sui PNG quando esiste il
testo.

## 6. Release gate

Una tavola entra nella documentazione ufficiale soltanto dopo record valido, review
scientifica, zero blocking error, render automatico, manifest e hash reali, notice
corretto, count scope-aware, gate training/evaluation coerenti e approvazione di
leggibilità/anti-overclaim. Fino all'esistenza del renderer questa specifica non rende
alcuna tavola training-ready.

