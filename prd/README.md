# PRD locale di riferimento

Il contesto istruttorio primario corrente è
`N-Truth_PRD_scientifico_completo_v6.1` (versione 6.1, 1 agosto 2026):

| Artefatto | Ruolo |
|---|---|
| `N-Truth_PRD_scientifico_completo_v6.1.source.md` | Sorgente markdown governata (editabile) |
| `N-Truth_PRD_scientifico_completo_v6.1.docx` | Layout tabellare e tipografico |
| `N-Truth_PRD_scientifico_completo_v6.1.pdf` | Deliverable di revisione multidisciplinare |

La v6.1 è una revisione **execution-critical** della v6.0: integra le osservazioni
tecniche dell'audit Gemini senza ridurre lo scopo scientifico né il ruolo
centrale del modello AI. Companion docs:

- [changelog v6.1](../docs/prd-v6.1-changelog.md)
- [matrice audit → decisioni](../docs/prd-v6.1-gemini-response-matrix.md)
- [Synthetic Task Use Matrix](../docs/synthetic-task-use-matrix-v6.1.md)
- [Runtime Resource Budget](../docs/runtime-resource-budget-v6.1.md)
- [Lean Governance Matrix](../docs/lean-governance-matrix-v6.1.md)
- [registro affermazioni assolute](../docs/absolute-claims-register-v6.1.md)
- [ADR 0002–0009](../docs/adr/)

I PDF/DOCX/source PRD sono conservati localmente in questa directory ma restano
esclusi da Git: il repository Apache-2.0 non attribuisce né presume diritti di
redistribuzione sul documento sorgente.

## Baseline v6.0 (immutabile)

| Campo | Valore |
|---|---|
| Fonte fornita dal project owner | Google Drive privato; URL non riprodotto nel repository |
| Nome locale | `N-Truth_PRD_scientifico_completo_v6.0.pdf` |
| Data di acquisizione | 2026-08-01 |
| Pagine verificate | 50 |
| Dimensione | 4.058.131 byte |
| SHA-256 | `e99a660de778027301067793bf5ce8729e473a885dbd79c5c62ae728a2ad0be8` |
| Stato | baseline letta e riconciliata; sostituita operativamente dalla v6.1 |

## Record v6.1

I checksum SHA-256 di source/DOCX/PDF v6.1 sono ricalcolati ad ogni rebuild da
`tmp/prd_v61/build_prd_v61.py` e vanno verificati localmente:

```bash
shasum -a 256 prd/N-Truth_PRD_scientifico_completo_v6.1.*
```

Per una clone pubblica fanno fede la
[specifica pubblica](../docs/public-specification-v0.1.md), gli schemi versionati,
la [riconciliazione v6](../docs/prd-v6-reconciliation.md) e i test eseguibili.
Il PDF non è necessario per installare o usare il software.
