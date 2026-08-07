# N-Truth Data Card v0.1

**Stato:** nessun corpus N-Truth approvato, congelato o rilasciato.

## Contenuto corrente del repository

Il repository contiene soltanto materiale sintetico per test software:

- 12 fixture scientifiche storiche usate come regressioni;
- 128 scenari generati dal contratto delle 32 regole (positivo, negativo,
  ambiguo ed eccezione);
- test mirati di schema, parser, formati, sicurezza, governance e contratti PRD v6.

Questi asset non sono Experiment Bundle reali, non sono stati doppiamente annotati e
non devono essere chiamati gold, pilot, external set o prova di accuratezza. La matrice
del test harness non soddisfa da sola il requisito delle 30–60 fixture canoniche
complete e revisionate del PRD v6 §14.1.

L'inventario machine-readable è in
`data/manifests/fixture-catalog-v3.json`.

La preparazione supervisionata è implementata ma non include dati: richiede ID di
governance/licenza e stato annotativo adeguato, normalizza, rileva duplicati/conflitti,
costruisce leakage group transitivi, assegna split deterministici e produce manifest
content-addressed. Lo snapshot schema v2 conserva i record preparati e ricostruisce gli
split chat durante la verifica; booleani di approvazione, checksum o conteggi alterati
non bastano a superare il gate. L'autenticità e la sufficienza legale/scientifica delle
approvazioni restano responsabilità umane. Gli otto
piccoli asset esplorativi presenti soltanto nel workspace locale restano
`training_eligible=false`, non fanno parte del repository e non modificano lo stato di
questa card.

## Architettura dati pianificata

Il PRD v6 distingue sei dataset con responsabilità non intercambiabili:

1. **Rule Fixtures:** 30–60 casi canonici, completi di grafo, regola, output,
   eccezione, controesempio e riferimento scientifico; servono al motore, non al
   parser.
2. **Derivation Gold:** grafi confermati con determinabilità, EU/count attesi,
   proof trace, eccezioni e reviewer; valida il motore, non il parser.
3. **Parser Gold Corpus:** Experiment Bundle con sorgenti, evidence span, entità,
   conteggi, grafo, fattori, allocazioni, endpoint, contrasti, target inferenziale,
   determinabilità, alternative, domanda minima, rationale, licenza e provenance.
4. **Silver auditato:** sample sheet, metadata, dataset NLP e codice statistico; non
   entra nel test gold senza revisione.
5. **Synthetic augmentation:** graph-first, solo train/stress test; mai stima principale delle
   prestazioni.
6. **External Challenge Set:** solo casi reali da laboratori, tecniche e stili non visti; chiuso fino
   alla valutazione finale.

## Obiettivi progressivi, non risultati

| Fase | Target indicativo PRD v6 | Stato |
|---|---:|---|
| Schema bootstrap | 10-20 casi reali | non acquisito |
| Calibration pilot | 30-50 casi, fuori dal test | non acquisito |
| Feasibility | 100-150 casi reali | non acquisito |
| Restricted-domain expansion | 150-500 guidati da learning curve | non iniziato |
| Research corpus | 800-2.000 | non iniziato |
| Long-term scale | 3.000+ | visione pluriennale |

I numeri sono obiettivi di programma da rivedere dopo aver misurato tempo di
annotazione, ridondanza, determinability rate e curve di apprendimento.

## Provenance, autorizzazioni e licenze

Ogni asset futuro richiede checksum e manifest per singolo file. La presenza in un
repository pubblico non equivale a permesso di training o redistribuzione. Gli usi
`analyze`, `annotate`, `train`, `share` e `redistribute` devono essere autorizzati
separatamente; revoca, scadenza e restrizioni fanno parte della lineage.

Materiale PMC o di altre fonti entra soltanto dopo verifica della licenza sul singolo
asset. Non è attribuita una licenza globale al futuro corpus. Annotazioni e riferimenti
possono essere distribuiti separatamente dal testo sorgente soltanto se i rispettivi
manifest lo consentono.

## Split e leakage

Train, validation, test ed external challenge devono essere separati per articolo,
preprint/versione pubblicata, laboratorio, facility, corresponding author, dataset,
supplementi, synthetic family e counterfactual. Gli asset synthetic sono ammessi
soltanto nel train. Training, evaluation e release eligibility sono gate separati;
TEST ed EXTERNAL_CHALLENGE non sono mai training-eligible.

Il codice rifiuta conflitti di label, vieta synthetic fuori dal train e impedisce che
pubblicazione, progetto, bundle, source o asset collegati attraversino split. DOI,
preprint/versioni, laboratorio e mirror richiedono comunque metadati curatoriali
corretti: un algoritmo non può ricostruire relazioni che il manifest omette.

## Limitazioni

Non sono disponibili statistiche di copertura, lingue, laboratori, bilanciamento,
agreement, human ceiling, determinabilità o errori perché nessun corpus reale è stato
approvato. Gli esiti del dataset smoke non sono statistiche di corpus. Questi campi
saranno compilati da misure effettive, non stimati.

Il corpo e la DoD del PRD v6 usano 100-150 casi per la feasibility; il valore 150-250
rimasto nell'Appendice D è registrato come erratum editoriale aperto.
