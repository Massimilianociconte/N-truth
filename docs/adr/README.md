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
| [0002](0002-model-architecture-benchmark-gate.md) | Architettura del modello | benchmark-gated |
| [0003](0003-runtime-backend-and-resource-management.md) | Backend e resource manager | accepted for instrumentation; backend open |
| [0004](0004-quantization-benchmark-gate.md) | Quantizzazione | benchmark-gated |
| [0005](0005-structured-decoding-and-semantic-validity.md) | Structured decoding e validità | accepted |
| [0006](0006-independent-verifier-boundary.md) | Confine del verifier | accepted for development |
| [0007](0007-local-storage-backend.md) | Database locale | accepted for local baseline |
| [0008](0008-rules-engine-language.md) | Linguaggio del rules engine | provisional |
| [0009](0009-prospective-plan-versus-execution.md) | Piano ed esecuzione prospettici | accepted for contract |
| [0010](0010-granite-4.1-3b-migration.md) | Migrazione a Granite 4.1 3B Instruct | architetturale done; runtime artifact-bound `PARTIALLY_VERIFIED`; science `NOT_STARTED` |
| [0011](0011-constrained-decoding-outlines-mlx.md) | Constrained decoding Outlines + MLX-LM | accepted (forma ≠ semantica scientifica) |
| [0012](0012-p0-lora-approved.md) | Approvazione protocollo LoRA P0 | accepted + HOLD esecuzione sostanziale |
| [0013](0013-sourcedata-provenance-exporter-aligned-full-unit-hybrid.md) | SourceData provenance: ibrido full-unit allineato all'exporter (candidato Method C) | accepted (decisione progettuale umana, 2026-08-06) |

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
