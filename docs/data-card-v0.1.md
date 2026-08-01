# N-Truth Data Card v0.1

**Stato:** nessun corpus N-Truth acquisito, congelato o rilasciato.

## Contenuto corrente del repository

Il repository contiene soltanto materiale sintetico per test software:

- 12 fixture scientifiche storiche usate come regressioni;
- 128 scenari generati dal contratto delle 32 regole (positivo, negativo,
  ambiguo ed eccezione);
- test mirati di schema, parser, formati, sicurezza, governance e PRD v3.

Questi asset non sono Experiment Bundle reali, non sono stati doppiamente annotati e
non devono essere chiamati gold, pilot, external set o prova di accuratezza. La matrice
del test harness non soddisfa da sola il requisito delle 30–60 fixture canoniche
complete e revisionate del PRD v3 §14.2.

L'inventario machine-readable è in
`data/manifests/fixture-catalog-v3.json`.

## Architettura dati pianificata

Il PRD v3 distingue cinque dataset complementari:

1. **Rule Fixtures:** 30–60 casi canonici, completi di grafo, regola, output,
   eccezione, controesempio e riferimento scientifico; servono al motore, non al
   parser.
2. **Parser Gold Corpus:** Experiment Bundle con sorgenti, evidence span, entità,
   conteggi, grafo, fattori, allocazioni, endpoint, contrasti, target inferenziale,
   determinabilità, alternative, domanda minima, rationale, licenza e provenance.
3. **Silver / Weak Supervision:** sample sheet, metadata e codice statistico; non
   entra nel test gold senza revisione.
4. **Synthetic Graph-to-Text:** solo train e stress test; mai stima principale delle
   prestazioni.
5. **External Challenge Set:** laboratori, tecniche e stili non visti; chiuso fino
   alla valutazione finale.

## Obiettivi progressivi, non risultati

| Fase | Target indicativo PRD v3 | Stato |
|---|---:|---|
| Calibration set | 30 casi, fuori dal test | non acquisito |
| Feasibility pilot | 150–250 bundle | non acquisito |
| Research corpus | 1.200–2.000 bundle | non iniziato |
| Restricted-domain v1 | 3.000–6.000 bundle gold/verified | non iniziato |
| Scale layer | 10.000+ silver/synthetic | non iniziato |

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

Train, validation, test ed external devono essere separati per articolo,
preprint/versione pubblicata, laboratorio/corresponding author quando possibile,
dataset e supplementi collegati e template sintetico. Gli asset synthetic sono ammessi
soltanto nel train. Test ed external restano congelati e non vengono usati per iterare.

## Limitazioni

Non sono disponibili statistiche di copertura, lingue, laboratori, bilanciamento,
agreement, human ceiling, determinabilità o errori perché nessun corpus reale è stato
raccolto. Questi campi saranno compilati da misure effettive, non stimati.
