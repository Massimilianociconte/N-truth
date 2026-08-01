# Governance dati v3

I contratti in `ntruth.governance` implementano i prerequisiti locali delle
sezioni 15, 18.5, 20.6 e 26 del PRD. Non pubblicano dati, non avviano training e
non contattano servizi esterni.

## Gate fail-closed

Ogni asset ha un `GovernanceRecord` immutabile con checksum dell'asset, prova di
autorizzazione e relativo hash, stato del consenso, scadenza, revoca,
anonimizzazione e usi consentiti. Gli usi sono distinti:

- `analyze`;
- `annotate`;
- `train`;
- `share`;
- `redistribute`.

`authorize()` nega l'azione quando il record è assente/non approvato, il consenso
è pending o withdrawn, l'autorizzazione è revocata/scaduta, l'uso non è elencato
o checksum e governance hash non coincidono. Il controllo deve essere eseguito
immediatamente prima dell'azione, non soltanto all'ingestione, così una revoca
successiva non viene ignorata.

Quando il record richiama un `LicenseManifest`, ID e hash del manifest sono
vincolanti e il gate richiede la stessa versione. Per gli usi automatizzati
`train`, `share` e `redistribute`, un asset pubblico è ammesso soltanto con
licenza Tier A completa e CC0 1.0 o CC BY 4.0, oltre all'allowed use esplicito.

L'analisi locale non implica autorizzazione a condividere, addestrare o
redistribuire. Anche materiali pubblici richiedono una base registrata e lo
specifico allowed use.

## Experiment Bundle

`ExperimentBundleManifest` associa ogni file a un ruolo esplicito, fra cui
Methods, caption, group scheme, sample sheet, file-to-sample mapping, codice
statistico ed expert answer. I mapping possono riferire soltanto file assegnati
al bundle e un `sample_sheet_file_id` deve avere il relativo ruolo.

Il checksum di `ProjectManifest` comprende manifest licenza, ID e hash del
record di governance e bundle. Aggiornare correttamente consenso, licenza, ruolo
o mapping cambia quindi l'identità del progetto. Le dichiarazioni degli autori
e quelle esperte restano campi distinti dai fatti dichiarati.

## Snapshot corpus e lineage

`CorpusSnapshotManifest` è content-addressed e include:

- checksum degli asset e dei rispettivi record di governance;
- ID e checksum dell'Experiment Bundle, oltre allo split;
- versioni schema, contratto parser, guideline e ontologia;
- gruppi anti-leakage per articolo/versione, laboratorio, dataset, supplemento
  e template sintetico;
- snapshot parent.

Un leakage group non può attraversare split distinti. Gli asset sintetici sono
ammessi soltanto in `train`. `validate_snapshot_dag()` verifica parent assenti e
cicli quando viene fornita una collezione di snapshot.

`ModelRunLineage` registra in modo dichiarativo modello/configurazione, snapshot,
split, versioni, seed e checksum del lockfile. Il modello non contiene funzioni
di training né le autorizza.

## Scanner privacy locale

`scan_text()` rileva email, path utente locali, nomi esplicitamente etichettati
e sample/subject/participant/patient/donor ID. I finding sono stand-off:
conservano coordinate, tipo, confidence, preview mascherata e hash del match, non
una copia dell'identificatore.

Le policy prima di export/share sono:

- `blocked`: qualsiasi finding blocca;
- `acknowledged`: richiede un riferimento esplicito alla revisione;
- `redacted_copy`: richiede una derivata e un `RedactionManifest` che copra tutti
  i finding.

`make_redacted_copy()` controlla il checksum e restituisce una nuova stringa;
non muta mai la fonte. Il risultato dello scanner è assistivo: i name-like e i
sample ID richiedono revisione umana e non costituiscono una classificazione
legale automatica.

## Integrazione e confini residui

Il flusso applicativo standard scansiona Document IR e report senza mutare le
fonti e scrive due artefatti:

- `privacy-scan.json`, che contiene solo finding stand-off mascherati/hash;
- `share-readiness.json`, che mantiene `share_ready=false` e
  `redistribute_ready=false` finché non viene eseguito un controllo esplicito.

`POST /v1/distribution/readiness` e il comando `ntruth distribution-check`
applicano governance e privacy agli artefatti correnti in modalità fail-closed.
Un esito autorizzato vale per checksum, audit e record presentati; il controllo
non copia, carica o distribuisce file e non crea un permesso persistente.

La chiamata di basso livello `write_all(report, out)` esporta gli schemi, ma
senza un `DocumentIR` non può scansionare le fonti: non equivale a readiness di
distribuzione. Non esiste ancora un generatore applicativo di pacchetti o copie
redatte. Nessun comando è autorizzato al training soltanto perché i modelli dati
o i record governance esistono.
