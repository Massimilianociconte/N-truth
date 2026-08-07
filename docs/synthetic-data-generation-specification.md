# Synthetic Data Generation Specification v0.1-draft

Stato: **specifica di progetto; nessuno snapshot synthetic è approvato**. Owner
richiesti: Data/ML lead e reviewer scientifico. La factory amplifica copertura e
variabilità; non sostituisce il gold reale e non fornisce validazione esterna.

## 1. Flusso graph-first

Ogni generazione segue, in ordine:

1. Design DSL versionato;
2. coverage plan per casi canonici, errori e rare topology;
3. graph sampler biologicamente vincolato;
4. deterministic label compiler;
5. observation model per visibilità, omissioni e conflitti;
6. renderer di Methods, caption, sample sheet, XML, metadata e codice read-only;
7. perturbation engine per coreference, inconsistenze e rumore controllato;
8. hard validation e round-trip record-grafo;
9. deduplica, family split e contamination scan;
10. audit umano stratificato;
11. registry immutabile con seed, generator/teacher, prompt family, versioni e hash.

Il generator non accede a TEST o EXTERNAL_CHALLENGE. Un output del teacher è sempre
candidato finché non supera i gate previsti.

## 2. Bundle e manifest

Ogni bundle conserva fonti sintetiche, record canonico e viste renderizzate in
directory separate. Il manifest registra almeno `bundle_id`, `family_id`, seed,
Design DSL/versione, compiler/ruleset checksum, renderer/versione, prompt family,
teacher e licenza, hash di ogni file, grado, split, leakage group ed eligibility.

Parafrasi, mutazioni, controfattuali e facsimile dello stesso grafo condividono
`family_id` e split. I file raster non diventano source of truth e non sostituiscono
testo o annotazioni strutturate.

## 3. Gradi e usi

| Grado | Requisiti minimi | Uso massimo consentito |
|---|---|---|
| `SYN-G0` | grafo e label compiler validi | test del motore e training strutturale isolato |
| `SYN-G1` | G0 + documenti validi + round-trip riuscito | candidato per training, non task critici senza audit |
| `SYN-G2` | G1 + campione/famiglia revisionato da umano | training-approved per i task esplicitamente autorizzati |

`synthetic`, `gold`, `training_eligible` ed `evaluation_eligible` sono assi distinti.
Nessun grado sintetico è ammesso nell'External Challenge reale.

## 4. Quality gate automatici

Il lotto fallisce se:

- schema, referential integrity, topologia o count invariant non passano;
- testo, tabella e codice non ricostruiscono il grafo dichiarato nei limiti previsti;
- `null`, `UNKNOWN` e `NOT_REPORTED` diventano zero o assenza certa;
- allocation, indipendenza, source count o inference scope vengono sovrainferiti;
- una mutazione cambia più fatti del necessario senza registrarli;
- sono presenti duplicati o leakage cross-split;
- un asset non ha hash, provenance o stato licenza/eligibility.

Round-trip e cycle consistency sono segnali di qualità, non prove autonome di
realismo. Il codice generato è sempre `never_execute`.

## 5. Audit umano

Per ogni ciclo almeno 50 realizzazioni stratificate vengono classificate come
plausibili, troppo semplici, realisticamente ambigue, artificialmente ambigue,
implausibili o incoerenti. L'audit deve sovracampionare allocation implicita,
indipendenza biologica, coreference decisiva, conflitti, estimand/target e rare
topology.

Il report conserva tasso e tipologia degli errori, tempo di review, correzioni,
reviewer role e decisione KEEP/REVISE/QUARANTINE/DELETE per famiglia. Un record
quarantinato resta `training_eligible=false` e senza split definitivo.

## 6. Esperimenti di miscela

La percentuale synthetic non è prefissata. Sul development reale si confrontano
almeno real-only, synthetic-only, silver+real, synthetic+real e hybrid completa,
riportando TSTR, hybrid uplift, calibrazione, decisive-edge F1, errori per classe,
shortcut sensitivity e tempo umano. Un lotto viene mantenuto solo se migliora dati
reali o riduce review time senza degradare calibrazione.

Sono vietati self-training ricorsivo non auditato, selezione sul test, uso di PNG al
posto del testo disponibile e presentazione dei risultati synthetic-only come prova
di prestazione scientifica.

