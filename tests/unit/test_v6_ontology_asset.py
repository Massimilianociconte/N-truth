"""Coerenza tra versione dichiarata ed ontologia candidata distribuita."""

from __future__ import annotations

import json
from pathlib import Path

from ntruth import ONTOLOGY_VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_declared_ontology_version_has_a_matching_candidate_asset() -> None:
    path = ROOT / "ontology" / f"ntruth-core-{ONTOLOGY_VERSION}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["ontology_id"] == "ntruth-core"
    assert payload["version"] == ONTOLOGY_VERSION
    assert payload["status"] == "candidate"
    assert payload["profile"] == "prd-v6-d0-core"
    assert payload["nodes"]
    assert payload["relations"]
    assert all(item["reviewed"] is False for item in (*payload["nodes"], *payload["relations"]))


def test_v6_ontology_does_not_invent_unreviewed_operational_mappings() -> None:
    path = ROOT / "ontology" / f"ntruth-core-{ONTOLOGY_VERSION}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    relations = {item["ntruth"]: item for item in payload["relations"]}

    for name in (
        "assigned_to",
        "applied_to",
        "independently_assigned_at",
        "has_shared_environment",
        "confounded_with",
        "excluded_from",
    ):
        assert relations[name]["candidate"] is None
        assert relations[name]["reviewed"] is False
