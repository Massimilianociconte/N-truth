# Model cards

## Stato corrente

Nessun modello N-Truth è stato addestrato, selezionato o rilasciato. La presenza del
contratto `ParserAIInput` / `ParserAIOutput`, di configurazioni sotto `models/configs/`
o di un adapter software non costituisce un modello e non autorizza il training.

Non esistono ancora risultati NER/relation extraction, metriche su
`allocation_level`, risk-coverage, calibrazione, ablation o validazione esterna da
riportare in una model card.

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
