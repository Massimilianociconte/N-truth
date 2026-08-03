"""PRD v7 cross-domain role and public-registry privacy invariants (no PyYAML)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    path = REPO / rel
    if not path.exists():
        import pytest

        pytest.skip(f"file not on this branch: {rel}")
    return path.read_text(encoding="utf-8")


def test_lazic_role_decision_pending_not_training_eligible():
    text = _read("data_manifests/external-source-candidates.yaml")
    assert "source_id: lazic_in_vivo_pseudoreplication_data" in text
    assert "status: OFFERED_IN_PRINCIPLE_DETAILS_PENDING" in text
    assert "cross_domain_role_status: ROLE_DECISION_PENDING" in text
    assert "training_eligible: false" in text
    assert "development_eligible: false" in text
    assert "evaluation_eligible: false" in text
    assert "access_status: NOT_RECEIVED" in text
    assert re.search(r"licence_status:\s*UNKNOWN", text, re.I)
    assert "proposed_role: null" in text
    assert "SCHEMA_ALIGNMENT_SUBSET" in text
    assert "HELD_OUT_IN_VIVO_CHALLENGE" in text
    assert "FUTURE_ANIMAL_PROFILE_GOLD" in text
    # Must not still default to approved EXTERNAL_CHALLENGE_CANDIDATE as proposed_role
    assert "proposed_role: EXTERNAL_CHALLENGE_CANDIDATE" not in text


def test_in_vivo_not_automatic_in_vitro_gold():
    text = _read("data_manifests/external-source-candidates.yaml")
    assert "not_direct_gold_for_bootstrap_in_vitro_profile" in text
    assert "cannot_validate_ntruth_v1_0_A_in_vitro" in text
    assert "train_dev_test_role_must_be_agreed_before_inspecting_complete_labels" in text
    assert "no_access_or_ingestion_has_occurred" in text


def test_role_decision_pending_never_training_eligible_string():
    text = _read("data_manifests/external-source-candidates.yaml")
    assert "ROLE_DECISION_PENDING_never_training_eligible" in text


def test_nc3rs_auxiliary_announced_not_endorsement():
    text = _read("data_manifests/external-source-candidates.yaml")
    assert "source_id: nc3rs_arrive_compliance_checker_dataset" in text
    assert "status: ANNOUNCED_NOT_RELEASED" in text
    assert "proposed_role: AUXILIARY_CANDIDATE" in text
    assert "training_eligible: false" in text
    assert "partner" in text.lower()
    assert "not claimed as a partner" in text.lower() or "not a partnership" in text.lower()
    for ban in (
        "experimental_unit_gold",
        "independent_n_gold",
        "allocation_gold",
        "biological_independence_gold",
        "pseudoreplication_verdict_gold",
    ):
        assert ban in text


def test_public_registry_has_no_emails_or_phones():
    text = _read("docs/governance/collaboration-registry.public.yaml")
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    assert not re.search(r"\+?\d[\d\s\-()]{8,}\d", text)
    assert "commitment_status: FORMAL_PARTNER" not in text
    assert "ROLE_DECISION_PENDING" in text


def test_workstream_namespace_vocabulary_documented():
    text = _read("docs/governance/legacy-vs-v7-workstream-mapping.md")
    for token in (
        "LEGACY_WS_B",
        "LEGACY_WS_C",
        "V7_WS_A",
        "V7_WS_B",
        "V7_WS_C",
        "V7_WS_D",
    ):
        assert token in text
    assert "silently" in text.lower() or "reinterpret" in text.lower()


def test_silver_forbidden_uses_block_ntruth_gold_roles():
    from ntruth.task_corpora.config import FORBIDDEN_GOLD_USES

    for ban in (
        "experimental_unit_gold",
        "independent_n_gold",
        "allocation_gold",
        "biological_independence_gold",
        "pseudoreplication_verdict_gold",
    ):
        assert ban in FORBIDDEN_GOLD_USES


def test_author_assertion_not_in_forbidden_gold_uses_as_gold_label():
    """AUTHOR_ASSERTION is reporting semantics, not a gold use to promote."""
    from ntruth.task_corpora.config import FORBIDDEN_GOLD_USES

    assert "AUTHOR_ASSERTION" not in FORBIDDEN_GOLD_USES
    assert "REPORTED_METHOD_INDICATOR" not in FORBIDDEN_GOLD_USES
    assert "experimental_unit_gold" in FORBIDDEN_GOLD_USES
