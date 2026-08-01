# Dati, annotazione e sviluppo del modello

## Stato corrente

Non esistono ancora un corpus gold N-Truth, un backend AI attivo o un comando di
training. `models/configs/` contiene soltanto configurazioni dichiarative e
`ntruth.parser_ai` definisce il contratto stabile degli output candidati. Nessun comando
documentato in questa pagina addestra un modello.

## Layout locale

I dati reali o scaricati devono restare in `local-data/`, ignorata integralmente da Git:

```text
local-data/
├── raw/incoming/       # byte originali, immutabili
├── metadata/assets/    # URL, licenza, checksum, retrieval e review
├── metadata/sources/   # due diligence delle fonti
├── annotations/pending/# annotazioni non adjudicate
├── train/              # solo asset promossi dopo i gate
├── validation/         # congelata prima dell'ottimizzazione
├── test/               # mai usata per iterare
├── external/           # laboratori/tecniche unseen
└── quarantine/         # licenza, privacy o integrità non risolte
```

Un file scaricato resta in `raw/incoming`; non va copiato subito in uno split. Gli split
possono usare manifest o riferimenti content-addressed per evitare duplicazioni fisiche.

## Gate di acquisizione

Per ogni asset registrare almeno:

- URL primario e responsabile;
- versione/data di recupero e checksum SHA-256;
- licenza per singolo asset e URL della prova;
- attribuzione e usi separati (`analyze`, `annotate`, `train`, `share`, `redistribute`);
- eventuali restrizioni commerciali, privacy, embargo o revoca;
- famiglia articolo/preprint, laboratorio, dataset e supplementi collegati;
- stato `pending`, `approved_tier_a` o `rejected`.

Un eventuale downloader futuro dovrà limitare l'acquisizione automatizzata iniziale a
`CC0-1.0` e `CC-BY-4.0` con prova machine-readable per singolo asset. Il software
corrente non contiene un downloader. “Open access”, accesso gratuito o presenza in un
repository pubblico non bastano. CC BY-NC, CC BY-ND, licenze custom e licenza assente
richiedono review scritta e non entrano automaticamente nel corpus.

## Separazione degli split

La separazione avviene per bundle/articolo, mai per frase. Lo stesso leakage group non
può attraversare split:

- DOI/PMCID e tutte le revisioni;
- preprint e versione pubblicata;
- supplementi e dataset collegati;
- laboratorio/corresponding author quando disponibile;
- template synthetic o trasformazioni dello stesso grafo.

Gli asset synthetic sono ammessi soltanto nel train. Validation, test ed external
restano congelati e non vengono usati per prompt engineering o scelta delle regole.

## Annotazione manuale

1. completare 30 calibration cases fuori dal test;
2. doppia annotazione indipendente wet-lab/biostatistica;
3. misurare agreement prima dell'adjudication;
4. aggiornare guideline/schema e congelare il protocollo;
5. eseguire il pilot 150–250 bundle con disagreement log;
6. stimare human ceiling e determinability rate per dominio.

Le correzioni UI restano `candidate_annotations` con `training_eligible=false` finché
review e adjudication non le promuovono esplicitamente.

## Sequenza futura del modello

1. baseline deterministica e few-shot constrained sul contratto v2;
2. benchmark di evidence span, entity/relation e determinabilità;
3. confronto text-only vs text+sample-sheet;
4. solo dopo i gate, fine-tuning con snapshot content-addressed;
5. calibrazione, risk-coverage, astensione e OOD;
6. external challenge chiuso e ablation;
7. compilazione di Model Card e System Card con metriche misurate.

Ogni run futuro deve registrare snapshot, split, seed, checksum di configurazione,
lockfile, versioni schema/parser/guideline/ontologia e codice. Pesi, cache e log restano
in `models/checkpoints/` o `models/runs/`, entrambi esclusi da Git.

## Token e servizi esterni

Il software corrente non richiede token per analisi o training. Eventuali `HF_TOKEN`,
chiavi repository o credenziali di storage appartengono a un keychain o secret manager,
mai a `.env.example`, manifest, issue, log o commit.
