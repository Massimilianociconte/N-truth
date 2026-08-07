"""Genera rulesets/ntruth-core-0.3.0.json dal ruleset immutabile 0.2.0 (FASE 2).

Il PRD v8.0 rende la Derivation Theory normativa (§7.14, §10.11, NFR-33):
ogni regola eseguibile di un ruleset v8 deve riferire una clausola theory.
Questo script copia programmaticamente le 32 regole di ntruth-core-0.2.0
(file IMMUTABILE: nessuna trascrizione a mano) e aggiunge:

- ``theory_version: derivation-theory-0.1.0`` a livello ruleset;
- ``theory_clause`` per regola, mappata sulla clausola §7.15 che meglio
  corrisponde alla semantica reale della regola (mappatura registrata come
  SCIENTIFIC_REVIEW_REQUIRED nel registro SRR, voce SRR-0012);
- per le regole senza clausola difendibile: ``theory_clause: null`` +
  ``theory_status: SCIENTIFIC_REVIEW_REQUIRED`` + ``enabled: false``
  (forma fail-closed esplicita: mai eliminate, audit esplicito nel motore);
- ``theory_coverage_gaps`` per le clausole non implementate (NFR-33).

Uso: ``uv run python scripts/derive_ruleset_v8_theory.py [--check]``.
Con ``--check`` lo script verifica soltanto che il file generato sia
riproducibile, senza sovrascriverlo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "rulesets" / "ntruth-core-0.2.0.json"
TARGET = REPO_ROOT / "rulesets" / "ntruth-core-0.3.0.json"

THEORY_VERSION = "derivation-theory-0.1.0"

#: Mappatura regola -> clausola §7.15 basata sulla semantica reale della regola.
#: None = nessuna clausola difendibile: la regola resta nel ruleset ma viene
#: disabilitata e marcata SCIENTIFIC_REVIEW_REQUIRED (registro SRR-0012).
THEORY_CLAUSE_BY_RULE: dict[str, str | None] = {
    # GEN: unita candidata = livello di applicazione indipendente -> famiglia A.
    "GEN-001": "DT-EU-ASSIGNMENT-01",
    # GEN: misure multiple non moltiplicano n -> famiglia C (EU count).
    "GEN-002": "DT-EU-COUNT-01",
    # GEN: keyword "independent" non prova la separabilita' -> famiglia A.
    "GEN-003": "DT-EU-ASSIGNMENT-01",
    # GEN: righe/record non diventano n senza provenance -> famiglia C.
    "GEN-004": "DT-EU-COUNT-01",
    # GEN: confondimento perfetto -> DesignAdequacyFinding (§7.18), nessuna
    # clausola §7.15 lo determina: fail-closed, disabilitata.
    "GEN-005": None,
    # GEN: n per gruppo/contrasto/endpoint -> famiglia C.
    "GEN-006": "DT-EU-COUNT-01",
    # GEN: fonti contraddittorie -> gestione CONFLICTING (§9.5/§10.3), nessuna
    # clausola §7.15: fail-closed, disabilitata.
    "GEN-007": None,
    # GEN: aggregazione ≠ unita biologica -> famiglia F.
    "GEN-008": "DT-ANALYTICAL-01",
    # GEN: adeguatezza del modello statistico -> non-goal esplicito (§7.19):
    # fail-closed, disabilitata.
    "GEN-009": None,
    # GEN: indipendenza non stabilibile -> informazione insufficiente, famiglia A.
    "GEN-010": "DT-EU-ASSIGNMENT-01",
    # CC: stessa preparazione collassa la separabilita' -> famiglia B (DT-EU-04).
    "CC-001": "DT-EU-04",
    # CC: stesso donatore = provenienza confermata unica -> famiglia D.
    "CC-002": "DT-SOURCE-COUNT-01",
    # CC: thaw/passaggi stimano variabilita di processo -> scope, famiglia G.
    "CC-003": "DT-SOURCE-SCOPE-02",
    # CC: batch potenziali -> grouping finding, famiglia F.
    "CC-004": "DT-ANALYTICAL-01",
    # CC: una linea non generalizza -> inference scope, famiglia G.
    "CC-005": "DT-SOURCE-SCOPE-02",
    # CC: trattamento per pozzetto, preparazione = cluster di esposizione -> B.
    "CC-006": "DT-EU-EXPOSURE-02",
    # MIC: cellule/campi/immagini non moltiplicano n -> famiglia C.
    "MIC-001": "DT-EU-COUNT-01",
    "MIC-002": "DT-EU-COUNT-01",
    "MIC-003": "DT-EU-COUNT-01",
    # MIC: intervento a livello di coltura -> EU non e la cellula, famiglia B.
    "MIC-004": "DT-EU-01",
    # MIC: aggregazione non cambia il livello indipendente -> famiglia F.
    "MIC-005": "DT-ANALYTICAL-01",
    # MIC: ROI/blinding -> reporting adequacy (§7.18), nessuna clausola §7.15:
    # fail-closed, disabilitata.
    "MIC-006": None,
    # SC: cellule per donatore subsamples -> famiglia C.
    "SC-001": "DT-EU-COUNT-01",
    # SC: pseudobulk preserva il livello indipendente -> famiglia F.
    "SC-002": "DT-ANALYTICAL-01",
    # SC: libreria/lane/run livelli tecnici -> famiglia F.
    "SC-003": "DT-ANALYTICAL-01",
    # SC: confondimento condizione/soggetto -> §7.18, nessuna clausola §7.15:
    # fail-closed, disabilitata.
    "SC-004": None,
    # SC: spot/regioni annidati -> famiglia C.
    "SC-005": "DT-EU-COUNT-01",
    # ANI: intervento materno/gabbia -> EU assegnata, famiglia B.
    "ANI-001": "DT-EU-01",
    "ANI-002": "DT-EU-01",
    # ANI: tessuti dello stesso animale non aumentano n -> famiglia C.
    "ANI-003": "DT-EU-COUNT-01",
    # ANI: paired/contralaterale -> repeated-measure finding, famiglia F.
    "ANI-004": "DT-ANALYTICAL-01",
    # ANI: esclusione aggiorna n nel lifecycle -> famiglia C.
    "ANI-005": "DT-EU-COUNT-01",
}

#: Clausole theory non implementate da alcuna regola 0.3.0 (NFR-33).
COVERAGE_GAPS = [
    {
        "clause_id": "DT-EXP-02",
        "rationale": (
            "Nessuna regola ntruth-core-0.3.0 implementa la famiglia E "
            "(interference/estimand support): il ruleset 0.2.0 precede il "
            "contratto v8 e il PRD §10.8 ammette regole avanzate soltanto con "
            "theory clause, fixture, casi reali e revisione esterna."
        ),
    }
]

DESCRIPTION = (
    "Ruleset core di N-Truth collegato alla Derivation Theory "
    f"{THEORY_VERSION} (PRD v8.0 §7.14, §10.11, §20.3, NFR-33). "
    "Generato programmaticamente da ntruth-core-0.2.0 (immutabile) con "
    "scripts/derive_ruleset_v8_theory.py. Le regole senza clausola §7.15 "
    "difendibile restano nel ruleset, disabilitate e marcate "
    "SCIENTIFIC_REVIEW_REQUIRED (registro SRR-0012): il motore le salta con "
    "audit esplicito. Artefatto non revisionato: SCIENTIFIC_REVIEW_REQUIRED."
)


def build_ruleset() -> dict:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = []
    for rule in payload["rules"]:
        rule_id = rule["rule_id"]
        if rule_id not in THEORY_CLAUSE_BY_RULE:
            raise KeyError(f"mappatura theory mancante per la regola {rule_id}")
        clause = THEORY_CLAUSE_BY_RULE[rule_id]
        new_rule = dict(rule)
        new_rule["theory_clause"] = clause
        if clause is None:
            new_rule["theory_status"] = "SCIENTIFIC_REVIEW_REQUIRED"
            new_rule["enabled"] = False
        rules.append(new_rule)
    return {
        "ruleset_id": payload["ruleset_id"],
        "version": "0.3.0",
        "description": DESCRIPTION,
        "theory_version": THEORY_VERSION,
        "theory_coverage_gaps": COVERAGE_GAPS,
        "rules": rules,
    }


def main() -> int:
    generated = build_ruleset()
    text = json.dumps(generated, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        if not TARGET.is_file():
            print(f"MANCANTE: {TARGET}")
            return 1
        if TARGET.read_text(encoding="utf-8") != text:
            print(f"NON RIPRODUCIBILE: {TARGET} differisce dalla generazione")
            return 1
        print(f"OK: {TARGET} riproducibile")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    mapped = sum(1 for c in THEORY_CLAUSE_BY_RULE.values() if c is not None)
    disabled = sum(1 for c in THEORY_CLAUSE_BY_RULE.values() if c is None)
    print(f"scritto {TARGET}: {mapped} regole mappate, {disabled} disabilitate fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
