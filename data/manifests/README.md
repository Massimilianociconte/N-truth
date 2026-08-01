# Data manifests

Inserire qui soltanto manifest versionati e privi di segreti, dati personali o contenuto
scientifico riservato. I file sorgente non vengono committati automaticamente.

Per ogni asset reale/pubblico vanno registrati almeno origine primaria, checksum, data di
acquisizione, prova della licenza o dell'autorizzazione, attribuzione, stato di review e usi
distinti: `analyze`, `annotate`, `train`, `share`, `redistribute`. Un permesso per un uso non
implica gli altri.

Ogni Experiment Bundle deve inoltre dichiarare i ruoli dei file, l'eventuale mapping
file-campione e il record di governance. Gli snapshot del corpus devono includere versioni di
schema, contratto parser, guideline e ontologia, più gruppi anti-leakage per articolo/versione,
laboratorio, dataset, supplemento e template sintetico.

`fixture-catalog-v3.json` è un inventario del materiale sintetico di test presente nel
repository. Non è un corpus, non contiene licenze di terzi e non trasforma le fixture in gold o
in casi expert-reviewed.
