# SampleSheetSpec v6

## Scopo

Il `SampleSheetSpec` iniziale e un CSV UTF-8 che registra identificatori locali,
provenance biologica, contenimento fisico, livelli dei fattori, lifecycle e
collegamenti ai file. Lo schema implementato ha versione `6.0`.

Il foglio non contiene campi di allocazione o indipendenza: la presenza, unicita o
costanza di un ID non dimostra che un trattamento sia stato assegnato in modo
indipendente. Quelle conclusioni richiedono evidenza procedurale o conferma umana
auditabile nel grafo.

## Schema canonico

| Colonna | Valore per riga | Obbligo | Validazione attuale |
|---|---|---|---|
| `sample_id` | stringa | header e valore richiesti | Non vuoto e univoco nel file |
| `source_id` | stringa o null | header richiesto | La cella puo essere vuota |
| `preparation_id` | stringa o null | header richiesto | La cella puo essere vuota |
| `culture_id` | stringa o null | opzionale | Identificatore locale opaco |
| `plate_id` | stringa o null | opzionale | Contenimento fisico, non prova di indipendenza |
| `well_id` | stringa o null | opzionale | Coordinata/ID locale |
| `factor_level_<nome>` | categoria | almeno una colonna; valore richiesto per ogni fattore e riga | Nome normalizzato; per esempio `factor_level_treatment` |
| `batch_id` | stringa o null | opzionale | Rende il batch osservabile, non ne prova il ruolo |
| `timepoint` | stringa tipizzata | opzionale | Un numero nudo come `24` e rifiutato; usare `24 h` |
| `endpoint_id` | stringa o null | opzionale | Utile per rappresentazione long |
| `lifecycle_status` | enum | header e valore richiesti | `planned`, `treated`, `observed`, `excluded`, `analysed` |
| `exclusion_reason` | stringa o null | richiesto se `excluded` | Il CSV corrente valida la motivazione; fase e autore appartengono al record di esclusione completo |
| `file_ref` | stringa o null | opzionale | Hash o URI/path locale; oggi e opaco e non viene risolto dal validatore |

Colonne di estensione sono ammesse e preservate durante load/write. Non devono
ridefinire il significato delle colonne canoniche.

Il wizard D0 espone inoltre tre estensioni operative facoltative, inviate in
`extra_fields`: `day_id`, `operator_id` e `incubator_id`. Servono a rendere
osservabile un possibile confondimento perfetto tra livello del fattore e giornata,
operatore o incubatore. Devono contenere soltanto ID locali pseudonimi, mai nomi o
altri dati personali. La loro presenza non prova indipendenza; una cella vuota resta
`null`.

## Esempio valido

```csv
sample_id,source_id,preparation_id,culture_id,plate_id,well_id,factor_level_treatment,batch_id,day_id,operator_id,incubator_id,timepoint,endpoint_id,lifecycle_status,exclusion_reason,file_ref
S001,SRC01,PREP01,CULT01,P01,A01,vehicle,B01,DAY01,OP01,INC01,0 h,viability,observed,,raw/S001.tif
S002,SRC02,PREP02,CULT02,P01,B01,drug,B01,DAY01,OP01,INC01,24 h,viability,excluded,QC failure after measurement,raw/S002.tif
S003,,,CULT03,P02,A01,vehicle,B02,DAY02,,INC02,0 h,viability,planned,,raw/S003.tif
```

La terza riga mostra null espliciti per `source_id` e `preparation_id`: gli header
restano presenti e le celle sono vuote. Il record e strutturalmente valido, ma la
provenance mancante deve rimanere visibile come informazione non riportata.

## Esempi invalidi

Header obbligatorio mancante:

```csv
sample_id,preparation_id,factor_level_treatment,lifecycle_status
S001,PREP01,vehicle,planned
```

`source_id` deve essere presente come colonna anche quando i suoi valori sono null.

ID duplicato:

```csv
sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status
S001,SRC01,PREP01,vehicle,observed
S001,SRC02,PREP02,drug,observed
```

Fattore senza valore:

```csv
sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status
S001,SRC01,PREP01,,treated
```

Timepoint privo di unita:

```csv
sample_id,source_id,preparation_id,factor_level_treatment,timepoint,lifecycle_status
S001,SRC01,PREP01,drug,24,observed
```

Esclusione priva di motivazione:

```csv
sample_id,source_id,preparation_id,factor_level_treatment,lifecycle_status,exclusion_reason
S001,SRC01,PREP01,drug,excluded,
```

Questi controlli sono strutturali. Non stabiliscono se gli ID, i livelli o la
motivazione siano scientificamente veri.

## Lifecycle

Ogni riga assume esattamente uno stato corrente:

| Stato | Significato operativo minimo |
|---|---|
| `planned` | Campione previsto nel piano |
| `treated` | Trattamento/procedura applicato |
| `observed` | Almeno un'osservazione acquisita |
| `excluded` | Campione escluso; `exclusion_reason` obbligatorio |
| `analysed` | Campione incluso nell'analisi dichiarata |

Lo spelling in ingresso `analyzed` e accettato per migrazione e normalizzato a
`analysed`. Non usarlo nei nuovi file canonici.

Il lifecycle del sample sheet non sostituisce i count record scope-aware: un campione
puo essere osservato per un endpoint e non analizzato per un altro. Fase,
prespecificazione, autore della decisione, endpoint, gruppo e impatto dell'esclusione
devono essere conservati nel grafo completo quando disponibili.

## Null espliciti

- Una cella CSV vuota rappresenta `null` per i campi nullable.
- `0`, `NA`, `unknown` e un ID inventato sono stringhe, non null. Non usarli come
  segnaposto.
- `sample_id`, `lifecycle_status` e ogni `factor_level_*` non possono essere null.
- `source_id` e `preparation_id` possono essere null, ma i relativi header sono
  sempre obbligatori.
- Il silenzio non e uno zero e non autorizza la derivazione di un conteggio.

## Alias legacy

Il loader accetta questi alias al confine CSV e produce un warning:

| Alias in ingresso | Nome canonico |
|---|---|
| `batch` | `batch_id` |
| `endpoint` | `endpoint_id` |
| `status` | `lifecycle_status` |
| `factor_level` | `factor_level_treatment` |

Nuovi template ed export usano sempre i nomi canonici. Dopo la normalizzazione,
header duplicati sono rifiutati. I valori scritti dal generatore vengono inoltre
neutralizzati se iniziano con un prefisso interpretabile come formula da un foglio di
calcolo.

## Comandi CLI

Creare il template D0 con il fattore predefinito `treatment`:

```sh
uv run ntruth sample-sheet init local-data/sample-sheet.csv
```

Specificare il fattore in modo esplicito:

```sh
uv run ntruth sample-sheet init local-data/sample-sheet.csv --factor treatment
```

Il comando non sovrascrive un file esistente. `--force` sostituisce atomicamente
soltanto un file regolare al path indicato; una destinazione symlink viene sempre
rifiutata:

```sh
uv run ntruth sample-sheet init local-data/sample-sheet.csv \
  --factor treatment \
  --force
```

Il generatore accetta piu opzioni `--factor`, ma un foglio multifattoriale e fuori
dal micro-dominio D0:

```sh
uv run ntruth sample-sheet init local-data/multifactor.csv \
  --factor treatment \
  --factor time
```

Validare senza modificare il CSV:

```sh
uv run ntruth sample-sheet validate local-data/sample-sheet.csv
```

L'exit code e `0` per uno spec valido e `1` per contenuto non valido; errori di
creazione del template terminano con `2`. La validazione stampa riga, colonna e codice
del problema quando disponibili. La lettura rifiuta symlink, file oltre 64 MiB, piu di
200.000 righe dati o piu di 512 colonne prima di materializzare uno spec.

La validazione canonica e attualmente un comando separato dall'analisi generale. Per
un bundle D0, validare prima il sample sheet e poi passare la cartella o il CSV a
`ntruth analyze`.

Vedere [Core Profile D0](core-profile-d0.md) per il perimetro scientifico e i limiti
di rilascio.
