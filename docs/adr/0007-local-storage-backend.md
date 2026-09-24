# ADR-0007 — SQLite e blob content-addressed per la baseline locale

**Stato:** accepted for local baseline; backend collaborativo open<br>
**Data:** 2026-08-01<br>
**Revisione:** quando emerge un requisito multi-user o un benchmark di scala reale

## Contesto

N-Truth deve conservare revisioni, audit e provenance senza richiedere un servizio
remoto. La scelta locale non deve però diventare un vincolo prematuro per una futura
modalità collaborativa.

## Alternative

- soli file JSON/YAML atomici;
- SQLite con blob content-addressed su filesystem;
- database embedded differente;
- PostgreSQL;
- graph database;
- storage ibrido locale/remoto soggetto a governance.

## Benchmark ed evidenza

La baseline viene verificata su recovery, foreign key, migrazioni, atomicità,
immutabilità degli audit, deduplica, checksum, portabilità degli export e tempi di
apertura/scrittura su bundle realistici. Una modalità collaborativa richiederà inoltre
concorrenza, autorizzazione, backup/restore e threat model.

## Decisione e motivazione

SQLite più blob SHA-256 è il backend locale iniziale perché mantiene deployment
single-user, transazioni e ispezionabilità. Gli schema scientifici e gli export non
dipendono da query o tipi esclusivi di SQLite. PostgreSQL o un graph database saranno
valutati solo quando un requisito misurato lo giustifica.

## Limiti e conseguenze

Questa decisione non dichiara sessioni collaborative, replica remota o disponibilità
multi-processo. Il registro prospettico corrente resta effimero finché non viene
collegato esplicitamente allo storage canonico.
