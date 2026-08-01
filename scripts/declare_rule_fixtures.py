#!/usr/bin/env python3
"""Dichiara le quattro fixture NFR-12 per ogni regola del ruleset core."""

from __future__ import annotations

import json
from pathlib import Path

RULESET = Path("rulesets/ntruth-core-0.1.0.json")
FIXTURE_SOURCE = "tests/rule_fixtures/context_factory.py"


def main() -> None:
    payload = json.loads(RULESET.read_text(encoding="utf-8"))
    for rule in payload["rules"]:
        rule_id = rule["rule_id"]
        has_abstention = bool(rule.get("abstain_if"))
        has_exception = bool(rule.get("exceptions"))
        ambiguous_outcome = "not_applicable"
        if has_abstention and rule_id != "GEN-002":
            ambiguous_outcome = "abstained"
        rule["fixtures"] = [
            {
                "id": f"{rule_id}-positive",
                "kind": "positive",
                "description": "Contesto sintetico minimo che soddisfa le precondizioni.",
                "path": FIXTURE_SOURCE,
                "scenario": "positive",
                "expected_outcome": "fired",
            },
            {
                "id": f"{rule_id}-negative",
                "kind": "negative",
                "description": "Contesto fuori dalle precondizioni della regola.",
                "path": FIXTURE_SOURCE,
                "scenario": "negative",
                "expected_outcome": "not_applicable",
            },
            {
                "id": f"{rule_id}-ambiguous",
                "kind": "ambiguous",
                "description": (
                    "Contesto con la condizione di astensione dichiarata."
                    if has_abstention
                    else "Contesto incompleto che non autorizza l'applicazione della regola."
                ),
                "path": FIXTURE_SOURCE,
                "scenario": "ambiguous",
                "expected_outcome": ambiguous_outcome,
            },
            {
                "id": f"{rule_id}-exception",
                "kind": "exception",
                "description": (
                    "Contesto positivo con l'eccezione dichiarata attiva."
                    if has_exception
                    else "Nessuna eccezione approvata: contesto non applicabile esplicito."
                ),
                "path": FIXTURE_SOURCE,
                "scenario": "exception",
                "expected_outcome": "excepted" if has_exception else "not_applicable",
            },
        ]
    RULESET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
