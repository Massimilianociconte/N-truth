"""Every ruleset reference must resolve to a public, versioned registry entry."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULESET_PATH = ROOT / "rulesets" / "ntruth-core-0.1.0.json"
REGISTRY_PATH = ROOT / "rulesets" / "scientific-references-0.1.0.json"


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_rule_reference_resolves_to_the_versioned_registry() -> None:
    ruleset = _read(RULESET_PATH)
    registry = _read(REGISTRY_PATH)
    entries = registry["references"]
    assert isinstance(entries, list)
    ids = [entry["reference_id"] for entry in entries]
    assert len(ids) == len(set(ids))

    cited = {reference for rule in ruleset["rules"] for reference in rule["references"]}
    assert cited == set(ids)


def test_reference_records_are_actionable_and_do_not_claim_approval() -> None:
    registry = _read(REGISTRY_PATH)
    assert registry["scientific_review_status"] == "candidate_pending_external_review"
    entries = registry["references"]
    assert isinstance(entries, list)
    for entry in entries:
        assert str(entry["url"]).startswith("https://")
        assert str(entry["license_evidence_url"]).startswith("https://")
        assert entry["responsible_entity"]
        assert entry["role"]
        assert entry["usage_scope"]
