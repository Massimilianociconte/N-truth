# ADR-0004 — Quantizzazione scelta mediante qualità e risorse misurate

**Stato:** benchmark-gated<br>
**Data:** 2026-08-01<br>
**Revisione:** insieme all'ADR-0002, prima del congelamento della baseline

## Contesto

La quantizzazione può rendere eseguibile un candidato sul dispositivo locale, ma può
anche modificare extraction, relazioni decisive, calibrazione e astensione. La sola
riduzione dello snapshot non dimostra che il candidato sia adatto.

## Alternative

- pesi non quantizzati compatibili col budget;
- quantizzazione 8 bit;
- quantizzazione 4 bit;
- quantizzazione differenziata per componente;
- modello più piccolo non quantizzato;
- modello più grande quantizzato ed eseguito sequenzialmente.

## Benchmark richiesto

Ogni variante usa la stessa revisione base quando il confronto lo consente e registra
formato, toolchain, revisione, dimensione, latenza, picco RAM, swap e tutte le metriche
scientifiche dell'ADR-0002. Va misurato anche il delta rispetto alla variante di
riferimento, con particolare attenzione a decisive coreference, allocation/application,
confidence calibration e false certainty.

## Decisione e motivazione

Nessun bit-width è congelato. Il profilo 4-bit già presente è un candidato bootstrap
per verificare meccanica, checkpoint e formati; non è la quantizzazione della release.
Una variante è accettabile solo se rientra nel budget misurato e il suo costo di qualità
e revisione è compatibile col protocollo approvato.

## Limiti e conseguenze

Non esiste ancora un gold reale su cui stimare il delta. Non si scaricano ulteriori
pesi per completare questa decisione. Backend e quantizzazione possono interagire e
devono essere benchmarkati come configurazione congiunta, non sommando stime teoriche.
