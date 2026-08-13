"""PRD v9 registry decision pack: complete, not self-approved, migration checkable."""

from __future__ import annotations

from pathlib import Path

import pytest

from ntruth.schemas.core import Determinability
from ntruth.schemas.registry_v9 import (
    FORBIDDEN_CANONICAL_V9_LABELS,
    NORMATIVE_REGISTRY_V9_FROZEN,
    REGISTRY_STATUS,
    assert_registry_not_self_approved,
    build_registry_decision_pack,
    load_registry_draft,
    migrate_v7_record,
    reject_public_adapter_v9_labels,
)

REQUIRED_TOPICS = (
    "enum",
    "field name",
    "claim type",
    "error code",
    "count kind",
    "status",
)
NAMED_V9_FIELDS = (
    "FactorRole",
    "ContrastType",
    "ContrastSupportClaim",
    "ObservedEvidenceScope",
    "TargetPopulationClaim",
)


def test_decision_pack_covers_required_topics_and_does_not_self_approve() -> None:
    pack = build_registry_decision_pack()
    draft = load_registry_draft()

    assert pack.status == REGISTRY_STATUS
    assert pack.normative_registry_v9_frozen is False
    assert NORMATIVE_REGISTRY_V9_FROZEN is False
    assert pack.human_approval is None
    assert pack.gold_frozen is False
    assert pack.implemented_root_contract == "PRD_V7"
    assert tuple(pack.single_canonical_registry_topics) == REQUIRED_TOPICS
    kinds = {entry.kind.value for entry in pack.entries}
    assert kinds == {
        "enum",
        "field_name",
        "claim_type",
        "error_code",
        "count_kind",
        "status",
    }
    names = {entry.name for entry in pack.entries}
    assert set(NAMED_V9_FIELDS) <= names
    assert "INSUFFICIENT_INFORMATION" in pack.ambiguous_indeterminate_states
    assert "INDETERMINATE" in pack.ambiguous_indeterminate_states
    assert "Rulebook" in pack.rulebook_status
    assert "annotation guideline" in pack.annotation_guideline_status.lower()
    for field in NAMED_V9_FIELDS:
        assert field in pack.experiment_graph_field_authority
    assert pack.experiment_graph_field_authority["FactorRole"] == "decisive"
    assert pack.experiment_graph_field_authority["TargetPopulationClaim"] == (
        "candidate_inference"
    )
    assert draft["normative_registry_v9_frozen"] is False
    assert_registry_not_self_approved(draft)


def test_registry_draft_rejects_self_freeze() -> None:
    payload = load_registry_draft()
    payload["normative_registry_v9_frozen"] = True
    with pytest.raises(ValueError, match="cannot set normative_registry_v9_frozen"):
        assert_registry_not_self_approved(payload)


def test_v7_record_migration_does_not_invent_decisive_v9_labels() -> None:
    record = {
        "determinability": {"status": Determinability.INDETERMINATE.value},
        "factors": [{"id": "f1", "kind": "genotype", "name": "genotype"}],
        "contrasts": [{"id": "c1", "label": "wt vs ko"}],
        "status": "INSUFFICIENT_INFORMATION",
    }

    report = migrate_v7_record(record)

    assert report.mapped_statuses[Determinability.INDETERMINATE.value] == (
        "INSUFFICIENT_INFORMATION"
    )
    assert "INSUFFICIENT_INFORMATION" in report.preserved_ambiguous_states
    assert "FactorRole" in report.unmigrated_decisive_fields
    assert "ContrastType" in report.unmigrated_decisive_fields
    assert report.invented_v9_labels == ()
    assert report.silent_factor_role_inference is False
    assert report.registry_frozen is False
    assert report.accepted is True


def test_v7_record_with_invented_v9_label_is_rejected() -> None:
    record = {
        "determinability": "DETERMINATE",
        "FactorRole": "ASSIGNED_INTERVENTION",
    }

    report = migrate_v7_record(record)

    assert "FactorRole" in report.invented_v9_labels
    assert report.accepted is False


def test_public_adapter_helper_rejects_named_v9_labels() -> None:
    with pytest.raises(ValueError, match="cannot emit canonical N-Truth v9 labels"):
        reject_public_adapter_v9_labels(
            {"entity_labels": ["B-FactorRole"], "role_labels": ["O"]},
            adapter="unit-test",
        )
    assert frozenset(NAMED_V9_FIELDS) == FORBIDDEN_CANONICAL_V9_LABELS


def test_decision_pack_document_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "docs" / "training" / "prd-v9-registry-decision-pack-v1.md"
    text = path.read_text(encoding="utf-8")
    for topic in (
        "single canonical registry",
        "enum",
        "field name",
        "claim type",
        "error code",
        "count kind",
        "status",
        "stati ambigui",
        "Rulebook",
        "Annotation guideline",
        "migration",
        "FactorRole",
        "ContrastType",
        "ContrastSupportClaim",
        "ObservedEvidenceScope",
        "TargetPopulationClaim",
        "Does not approve itself",
    ):
        assert topic.lower() in text.lower()
