# Architecture Decision Records

Gli ADR registrano decisioni tecniche che non devono essere dedotte dal solo codice o
dal nome di un modello. Ogni record include alternative, evidenza/benchmark richiesto,
decisione corrente, motivazione, limiti e data o trigger di revisione.

Una decisione `proposed` o `benchmark-gated` non è una scelta di release. Modelli,
framework e valori di memoria osservati durante il bootstrap non diventano baseline
scientifiche senza il protocollo comparativo e i gate umani previsti.

| ADR | Decisione | Stato |
|---|---|---|
| [0001](0001-inference-target-compiler-first.md) | Target inferenziale e compiler-first | accepted for development |
| `0002` | Architettura del modello | voce storica; file non presente in questo checkout |
| `0003` | Backend e resource manager | voce storica; file non presente in questo checkout |
| `0004` | Quantizzazione | voce storica; file non presente in questo checkout |
| `0005` | Structured decoding e validità | voce storica; file non presente in questo checkout |
| `0006` | Confine del verifier | voce storica; file non presente in questo checkout |
| `0007` | Database locale | voce storica; file non presente in questo checkout |
| `0008` | Linguaggio del rules engine | voce storica; file non presente in questo checkout |
| `0009` | Piano ed esecuzione prospettici | voce storica; file non presente in questo checkout |
| [0010](0010-granite-4.1-3b-migration.md) | Migrazione a Granite 4.1 3B Instruct | architettura accepted; profilo corrente `configuration_defined_execution_blocked`, runtime `NOT_RUN_CURRENT_PROFILE`, science `NOT_STARTED` |
| `0011` | Constrained decoding Outlines + MLX-LM | voce storica; file non presente in questo checkout |
| `0012` | Approvazione protocollo LoRA P0 | voce storica; file non presente in questo checkout |

## Template minimo

Ogni nuovo ADR deve dichiarare:

1. contesto e decisione da prendere;
2. alternative realistiche;
3. benchmark o evidenza utilizzata;
4. decisione e motivazione;
5. limiti e conseguenze;
6. data della decisione e data/trigger della revisione.

Un benchmark deve identificare dataset/split, macchina, runtime, configurazione,
numero di ripetizioni e metriche. Le deviazioni dalla decisione vengono documentate
con un nuovo ADR che sostituisce il precedente, non riscrivendo retroattivamente la
storia.
