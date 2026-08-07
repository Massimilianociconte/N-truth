# Core Profile D0

## Stato e perimetro

`ntruth-core@0.1-D` e il capability contract scientifico ufficiale della fondazione
deterministica Train D. `d0_core` e invece il release profile degli input. La loro
presenza nel software indica una superficie riproducibile e sottoposta a test, non
una validazione scientifica completata. Regole, soglie e tassonomie restano
candidate finche non terminano revisione biostatistica, revisione wet-lab,
Derivation Gold e validazione esterna.

Il profilo di rilascio e il profilo scientifico sono due confini distinti:

| Confine | `d0_core` | `extended_experimental` |
|---|---|---|
| Input | TXT, Markdown e CSV semplice delimitato da virgole | Aggiunge DOCX, JATS/XML/NXML, PDF, TSV, XLSX e codice R/Python/R Markdown in sola lettura |
| Disegno scientifico dichiarato | Bootstrap in colture cellulari/well plate, un fattore, massimo due livelli, un endpoint primario | Superficie per esperimenti e parser oltre D0; nessun claim di supporto stabile o validazione |
| Attivazione | Predefinita | Opt-in esplicito con `--release-profile extended_experimental` |
| Claim consentito | Alpha deterministica nel micro-dominio, con astensione e limiti pubblici | Risultato sperimentale da verificare integralmente |

L'abilitazione di un formato non valida il disegno contenuto nel file. In
particolare, multifattore, pairing/matching, fattori crossed, pooling, split,
split-plot, misure ripetute, imaging avanzato, organoidi/iPSC e disegni longitudinali
appartengono a profili successivi. `extended_experimental` abilita parser e formati,
ma attraversa lo stesso capability check scientifico `ntruth-core@0.1-D`.

## Micro-dominio D0

Il percorso ufficiale iniziale richiede riferimenti prevalentemente espliciti e
supporta la ricostruzione conservativa di un `ExperimentBlock` alla volta con:

- colture cellulari, colture primarie, piastre e pozzetti come livelli di
  allocazione candidati;
- cellule anche come livello di applicazione, senza trasformarle automaticamente in
  unita sperimentali;
- un fattore primario;
- non piu di due livelli o un contrasto primario esplicito;
- un endpoint primario;
- gerarchia minima delle unita, evidenze decisive e conteggi con scope quando
  riportati.

Un blocco con piu fattori, piu endpoint, piu di due livelli o livelli di
allocazione/applicazione non ammessi da D0 viene classificato `OUT_OF_SCOPE`. Lo
stesso vale se il blocco materializza una delle seguenti capacita fuori Core:

- relazioni o nodi di repeated measures, pairing, matching, blocking, crossing,
  splitting o pooling;
- processi strutturati equivalenti, anche se la relazione non e stata materializzata;
- piu timepoint distinti in endpoint, fattore temporale, estimand o scope dei conteggi
  e degli assessment;
- un modello statistico diverso dal kind esplicitamente ammesso `simple`, un modello
  con clustering dichiarato oppure un modello semplice che dichiara una topologia
  paired, two-way, repeated-measures, mixed, gerarchica o longitudinale.

Il controllo e fail-closed: un nuovo `model.kind` non amplia automaticamente D0 e
richiede una nuova versione della matrice di capacita. Un campo decisivo assente,
senza segnali espliciti fuori profilo, produce uno stato incompleto/di astensione,
mai un default implicito.

La decisione machine-readable espone sempre `profile_id`, `profile_version`, stato,
reason code e dettagli deterministici. Il report registra
`extras.scientific_profile = ntruth-core@0.1-D`; `release_profile` resta un campo
separato.

## Matrice minima dei campi

| Campo | Obbligo nel Core | Regola |
|---|---|---|
| `experiment_block_id` | richiesto | L'unita di annotazione e il blocco, non l'intero paper |
| nodi unita e `derived_from`/`nested_in` | richiesti | Conservano la gerarchia minima |
| fattore e livelli | richiesti | Un fattore primario nel bootstrap |
| contrasto primario | richiesto | Due livelli o contrasto esplicito |
| `allocation_level` | richiesto o `UNKNOWN` | Non e dedotto da una keyword |
| `application_level` | opzionale o `UNKNOWN` | Va valorizzato solo con evidenza |
| `independently_assigned` | tri-state richiesto | `TRUE`, `FALSE` o `UNKNOWN` |
| `independence_mechanism` | richiesto se `TRUE` | Evento o procedura osservabile |
| `independence_evidence_ids` | richiesto per fatti non umani con `TRUE` | Non coincide implicitamente con l'evidenza di allocation |
| `randomization_unit` | opzionale | Non viene inventata |
| `shared_environment` | opzionale | Per esempio piastra, giorno o operatore |
| `confounded_with` | opzionale | Sospetto e conferma devono restare distinguibili |
| endpoint e `measured_on` | richiesti | Un endpoint primario |
| evidence span decisivi | richiesti | Fonte e coordinate verificabili |
| conteggi e quantificatore | quando riportati | Sempre scope-aware; il silenzio non e zero |
| `inference_target` | opzionale o `UNKNOWN` | Raccolto soprattutto nel prospettico |
| `determinability` | derivato | Non e una label libera del parser o annotatore |

## Invarianti non negoziabili

1. L'unita sperimentale e relativa a fattore, contrasto ed endpoint; non esiste
   una label globale del paper.
2. `allocation_level` e `application_level` sono distinti. Il solo livello di
   allocazione non prova indipendenza.
3. `independently_assigned=TRUE` richiede un meccanismo di indipendenza esplicito.
4. ID, righe del sample sheet, nomi file e numerosita non dimostrano da soli
   allocazione, randomizzazione o indipendenza.
5. `planned_n`, `allocated_n`, `treated_n`, `observed_n`, `excluded_n`,
   `analysed_n`, `declared_n`, `observational_n` e `independent_n` non sono alias.
6. Ogni conteggio conserva quantificatore, unita, fattore/contrasto, endpoint,
   timepoint, lifecycle e condizione disponibili. Un limite non diventa un valore
   esatto e un valore mancante non diventa zero.
7. Un'asserzione dell'autore non chiude da sola la determinabilita.
8. Il codice statistico e evidenza read-only del modello dichiarato; non prova il
   processo fisico di allocazione.
9. Il rules engine legge il grafo validato, non il testo grezzo.
10. Solo `DETERMINATE` consente un singolo valore di unita sperimentale e
    `independent_n`. `CONDITIONALLY_DETERMINATE` consente valori solo nei rami
    espliciti; gli altri stati li sopprimono.
11. Correzioni, revisioni ed eventi di audit sono append-only. Le fonti e gli
    export precedenti non vengono riscritti.
12. Nessun input viene eseguito e nessun dato viene inviato in rete dal core
    locale.

## Comandi verificabili

Installare l'ambiente di sviluppo dal checkout:

```sh
uv sync --extra dev --locked
uv run ntruth --help
```

Creare e validare un sample sheet canonico con un fattore D0:

```sh
uv run ntruth sample-sheet init local-data/sample-sheet.csv --factor treatment
uv run ntruth sample-sheet validate local-data/sample-sheet.csv
```

Eseguire una prima analisi D0 in un workspace esplicito:

```sh
uv run ntruth analyze ./input \
  --out ./ntruth-out \
  --project ./workspace/project \
  --release-profile d0_core \
  --acknowledge-unvalidated-domain
uv run ntruth verify ./workspace/project
```

`--acknowledge-unvalidated-domain` conferma soltanto di aver letto l'avviso: non
trasforma il dominio in validato. Il comando `verify` ricontrolla i checksum della
copia sorgente e del blob content-addressed registrati nel progetto.

Per esercitare i parser estesi usare un workspace separato:

```sh
uv run ntruth analyze ./input-extended \
  --out ./ntruth-out-extended \
  --project ./workspace/project-extended \
  --release-profile extended_experimental \
  --acknowledge-unvalidated-domain
```

Il profilo e registrato nel manifest. Riaprire lo stesso workspace con un profilo
diverso viene rifiutato, evitando una reinterpretazione silenziosa degli input.

Avviare il wizard e il compiler prospettico canonico:

```sh
pnpm --dir apps/desktop install --frozen-lockfile
pnpm --dir apps/desktop build
uv run ntruth-api
```

Aprire `http://127.0.0.1:8765/app/`, completare i quattro passi D0 e usare
**Compila con verificatore D0**. Il client invia il contratto a
`POST /v1/prospective/d0/compile` con `ntruth-core@0.2.0`; stato, capability,
hard-verifier e readiness mostrati come canonici provengono dalla risposta Python.
La API rifiuta body oltre 8 MiB, piu di 10.000 righe e oltre 64 campi extra per
riga. Le sessioni prospettiche sono effimere nella memoria del processo.

## Fallimenti espliciti e limiti

- D0 rifiuta formati fuori profilo e CSV non rettangolari o non delimitati da
  virgole; la rettangolarita viene verificata sull'intero file bounded, non soltanto
  su un campione iniziale.
- Estensione e contenuto vengono confrontati tramite firma/media type; macro,
  symlink, path traversal e input oltre i limiti configurati sono rifiutati. Anche
  manifest, directory blob e database SQLite non possono essere symlink fuori dal
  workspace.
- JATS/XML con `DOCTYPE` o `ENTITY` e bloccato nel profilo esteso; R, Python e R
  Markdown sono importati come testo e non eseguiti.
- Un grafo con violazioni bloccanti diventa `INVALID_GRAPH`; le regole non vengono
  eseguite su quel blocco.
- Un grafo valido ma oltre `ntruth-core@0.1-D` diventa `OUT_OF_SCOPE`; il report
  sopprime unita sperimentale e `independent_n` singoli e indica i reason code. Il
  profilo input esteso non aggira questo gate.
- Il parser deterministico rules-only non ha la copertura attesa dal futuro parser
  AI. Nessun modello N-Truth addestrato o validato e incluso.
- La Evidence View mostra i locator ma non li modifica graficamente. Patch EvidenceSpan
  via API sono ricalcolate e validate contro il Document IR; mismatch di testo,
  offset, sezione o cella producono `INVALID_GRAPH` e bloccano le regole.
- Fixture sintetiche e test software non sono Parser Gold, Derivation Gold o prova
  di validita scientifica.

Vedere anche [SampleSheetSpec v6](sample-sheet-v6.md),
[architettura](architettura.md) e
[contratto parser/verifier](parser-ai-contract.md).
