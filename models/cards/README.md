# Model cards

## Stato corrente

Nessun modello N-Truth è stato scientificamente addestrato, selezionato o rilasciato.
Il profilo iniziale seleziona come base tecnica
`mlx-community/Qwen3-4B-Instruct-2507-4bit`, Apache-2.0, a una revisione e checksum
fissati. Il modello base, il runtime smoke e ogni adapter restano locali e ignorati da
Git. La presenza del contratto, del profilo o di un adapter tecnico non autorizza il
training scientifico.

`modernbert-span-ner-baseline.json` resta un'ipotesi di ablation/decomposizione futura:
non ha revisione fissata, non viene eseguito dalla CLI e non è il modello selezionato
per il percorso iniziale.

Non esistono ancora risultati NER/relation extraction su gold, metriche su
`allocation_level`, risk-coverage, calibrazione, ablation o validazione esterna da
riportare in una model card.

La pipeline implementa i meccanismi necessari per produrre questi artefatti in futuro:
manifest, seed, ambiente/lock checksum, checkpoint/ripresa, validation loss, metriche
strutturate, temperature scaling e adapter export. Lo smoke di due iterazioni non è un
risultato di modello e non soddisfa alcun gate qui sotto.

## Gate prima del training

Una model card può essere aperta soltanto dopo che siano documentati almeno:

- schema capace di rappresentare senza modifiche sostanziali almeno venti disegni
  reali;
- regole principali revisionate e testate;
- output few-shot valido rispetto al contratto del parser;
- guideline che separa fatti strutturali, dichiarazioni dell'autore e inferenze;
- protocollo del pilot congelato;
- licenze, autorizzazioni e usi `train` registrati per ogni asset;
- split per articolo/versione/laboratorio/dataset/template senza leakage.

## Contenuto minimo futuro

La model card dovrà riportare modello e configurazione, snapshot del corpus, lineage,
seed, ambiente, dominio e lingue, confronto con baseline, metriche stratificate,
human ceiling, calibrazione e astensione, errori noti, external challenge, usi vietati,
privacy, licenze, rollback e procedura di correzione umana.

Synthetic e silver devono essere dichiarati separatamente e non possono essere
presentati come prestazioni su gold reale.
