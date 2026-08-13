"""Identity/eligibility join from real FLASH128-derived envelopes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.data.eligibility_join import (
    assert_join_not_gold,
    join_envelope_eligibility,
    summarize_root_identity,
)
from ntruth.data.identity import extract_stable_identity, scholarly_paper_id
from ntruth.data.schemas import CommonEnvelope
from ntruth.task_corpora.authority import AuthorityLevel

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "eligibility"
FLASH = Path("/Volumes/FLASH128/N-Truth-Datasets")


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_scholarly_paper_id_rejects_internal_names() -> None:
    assert scholarly_paper_id("") is None
    assert scholarly_paper_id("My_pdf325new_method") is None
    assert scholarly_paper_id("unknown_document_scope:abc") is None
    assert scholarly_paper_id("PMC1064854") == "PMC1064854"
    assert scholarly_paper_id("S0019103512001388") == "S0019103512001388"


def test_join_four_real_fixtures_never_eligible_or_gold() -> None:
    expected = {
        "sourcedata.json": {
            "source": "SourceData",
            "paper": None,
            "family": None,
            "experiment": None,
        },
        "preclinie.json": {
            "source": "PreClinIE",
            "paper": None,
            "family": "my_pdf325",
            "experiment": None,
        },
        "measeval.json": {
            "source": "MeasEval",
            "paper": "S0019103512001388",
            "family": "S0019103512001388",
            "experiment": None,
        },
        "craft.json": {
            "source": "CRAFT",
            "paper": "PMC1064854",
            "family": "PMC1064854",
            "experiment": None,
        },
    }
    for name, expect in expected.items():
        envelope = _load(name)
        parsed = CommonEnvelope.model_validate(envelope)
        result = join_envelope_eligibility(parsed)
        assert_join_not_gold(result)
        assert result.source == expect["source"]
        assert result.paper_id == expect["paper"]
        assert result.family_id == expect["family"]
        assert result.experiment_id == expect["experiment"]
        assert result.identity_complete is False
        assert result.training_eligible is False
        assert result.evaluation_eligible is False
        assert result.authority_level is not AuthorityLevel.NTRUTH_GOLD
        assert result.gold_quantity is None
        assert "identity_incomplete" in result.blockers
        identity = extract_stable_identity(
            parsed, source_asset_id="fixture", source_ref="fixture"
        )
        assert identity.complete() is False


def test_join_does_not_invent_experiment_or_gold_from_source_tier() -> None:
    envelope = _load("sourcedata.json")
    assert envelope["native_annotation_tier"] == "HUMAN_CURATED_GOLD"
    result = join_envelope_eligibility(envelope)
    assert result.authority_level is AuthorityLevel.CANDIDATE
    assert result.experiment_id is None


def test_missing_license_or_identity_keeps_record_non_eligible() -> None:
    envelope = _load("craft.json")
    result = join_envelope_eligibility(envelope)
    assert result.paper_id == "PMC1064854"
    assert result.training_eligible is False
    assert any(
        code in result.blockers
        for code in ("dua_missing", "training_unknown", "steward_authorization_absent")
    )


@pytest.mark.skipif(not FLASH.is_dir(), reason="FLASH128 not mounted")
def test_live_flash128_join_matches_fixtures_and_writes_no_gold() -> None:
    summary = summarize_root_identity(FLASH, per_source_limit=8)
    assert summary["eligible_records"] == 0
    assert summary["gold_records"] == 0
    assert summary["writes_training_ready"] is False
    for source, row in summary["sources"].items():
        assert row["eligible"] == 0
        if row["path_present"]:
            assert row["recovered"]["experiment"] == 0
            assert row["recovered"]["complete"] == 0
        if source == "SourceData" and row["path_present"]:
            assert row["recovered"]["paper"] == 0
        if source in {"MeasEval", "CRAFT"} and row["path_present"]:
            assert row["recovered"]["paper"] == row["recovered"]["scanned"]
