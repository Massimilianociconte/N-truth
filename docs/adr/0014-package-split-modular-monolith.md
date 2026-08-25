# ADR-0014 — Package split: modular monolith confermato

**Status:** accepted
**Date:** 2026-08-25
**Scope:** PRD v9 §26.9 (package split), NFR-48, contracts/ (CP-SCI/EPI/DATA/EVAL/RUN)

## Context

PRD v9 consolida l'architettura in cinque Contract Packages logici e dichiara il
modular monolith come default. Il repository è oggi un singolo pacchetto Python
installabile (`packages/ntruth`, oltre trenta sottodomini: `schemas`,
`derivation_theory`, `rules`, `graph`, `verifier`, `quick_design`, `prospective`,
`reporting`, `evaluation_v8`, `governance`, `confidence`, `team_evaluation`,
`model_backends`, `reality_gate`, `release`, …) con un solo lockfile, un solo
wheel/sdist e confine di import verificato da test dedicati
(`tests/unit/test_import_boundaries.py`). I manifest `contracts/*.yaml`
documentano i confini logici, gli owner di ruolo e i gate senza richiedere uno
split fisico. NFR-48 vieta di aumentare il numero di pacchetti fisici senza una
giustificazione esplicita.

## Decision

1. **Modular monolith confermato.** Un unico pacchetto Python distribuibile,
   organizzato internamente secondo i cinque Contract Packages; i confini logici
   sono quelli dei manifest `contracts/*.yaml` e restano enforceable tramite test
   sui boundari di import.
2. **Lo split fisico è rimandato dopo v1.0-D.** Nessuna estrazione in
   distribuzioni separate prima del milestone v1.0-D e salvo nuovo ADR che lo
   sostituisca.
3. **Criteri di attivazione dello split** (nessuno è sufficiente da solo; due o
   più insieme, o uno persistente per due release, giustificano la proposta):
   - pressione di versionamento indipendente documentata (un dominio avanza
     mentre un altro resta congelato, con changelog a supporto);
   - consumatori esterni reali che necessitano installazioni parziali;
   - wall-time CI o dimensione artifact fuori budget con evidenza misurata;
   - necessità di governance separata con owner e reviewer non sovrapponibili;
   - conflitti ricorrenti sul confine che i test di import non contengono.
4. Finché lo split non avviene, ogni CP deve dichiarare in `contracts/*.yaml` i
   moduli e le evidenze correnti; un CP senza moduli tracciabili è un errore di
   manifest, non una licenza ad accoppiamento libero.

## Consequences

- Un solo ambiente locked (`uv.lock`), una sola pipeline di release, un solo
  SBOM: verifica riproducibilità semplice (NFR-06).
- L'accoppiamento interno resta visibile e governato da test, non da tooling di
  workspace; una violazione di confine è un bug di build/test, non un fallimento
  di packaging.
- Lo split futuro richiederà migrazione esplicita (import shim deprecati,
  transizione pin registry) e un ADR sostitutivo.

## Alternatives considered

- **Split immediato in cinque pacchetti fisici allineati ai CP:** rifiutato.
  Costo di versionamento/release ×5 senza benefici scientifici o operativi
  attuali; viola NFR-48 finché i criteri sopra non sono osservati.
- **Micro-pacchetti per sottodominio:** rifiutato; frammentazione massima,
  superficie di attacco supply-chain più ampia.
- **Workspace multi-pacchetto monorepo:** rinviato; valutabile insieme allo
  split fisico quando i criteri maturano.

## Review trigger

Nuovo ADR sostitutivo al superamento di v1.0-D o allorché due criteri di split
risultino osservati e documentati; mai riscrittura retroattiva di questo record.
