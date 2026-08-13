"""Public adapters cannot emit PRD v9 canonical labels."""

from __future__ import annotations

import json

import pytest

from ntruth.schemas.registry_v9 import FORBIDDEN_CANONICAL_V9_LABELS
from ntruth.task_corpora.adapters.sourcedata_entity_roles import (
    ADAPTER_NAME,
    load_label_map,
)
from ntruth.task_corpora.authority import AuthorityLevel, LicenseStatus, SupervisionSource
from ntruth.task_corpora.schemas import (
    EntityRolesPayload,
    LicenseUseDecision,
    SourceIdentity,
    TaskRecord,
    TransformLineage,
)


def _record() -> TaskRecord:
    return TaskRecord(
        record_id="r1",
        task_type="entity_roles",
        source=SourceIdentity(
            dataset="SourceData",
            version="2.0.3",
            commit="c",
            document_id="d1",
            segment_id="s1",
        ),
        split="train",
        split_authority="upstream_official",
        leakage_group="d1",
        supervision_source=SupervisionSource.HUMAN_PUBLIC,
        authority_level=AuthorityLevel.AUXILIARY,
        allowed_uses=["token_classification"],
        forbidden_uses=[
            "experimental_unit_gold",
            "independent_n_gold",
            "pseudoreplication_verdict_gold",
            "allocation_gold",
            "biological_independence_gold",
            "interference_gold",
            "estimand_gold",
        ],
        licence=LicenseUseDecision(
            license_status=LicenseStatus.RESTRICTED,
            training_allowed=False,
            redistribution_allowed=False,
            derived_labels_allowed=True,
            decision_basis="test",
            reviewed_at="2026-08-03T00:00:00Z",
        ),
        training_eligible=False,
        evaluation_eligible=False,
        requires_review=False,
        transform_lineage=TransformLineage(
            adapter="test",
            transform_version="0.1.0",
            parent_path="p",
            parent_checksum="abc",
            mapping_version="0.1.0",
        ),
        checksum="deadbeef",
        payload=EntityRolesPayload(
            tokens=["a", "b"],
            entity_labels=["O", "B-GENEPROD"],
            role_labels=["O", "B-MEASURED_VAR"],
        ),
    )


def test_sourcedata_label_map_has_no_v9_canonical_names() -> None:
    mapping = load_label_map()
    blob = json.dumps(mapping, sort_keys=True)
    for name in FORBIDDEN_CANONICAL_V9_LABELS:
        assert name not in blob
        assert name not in mapping.get("entity_types", [])
        assert name not in mapping.get("role_types", [])
        assert name not in mapping.get("source_to_canonical", {})
        assert name not in mapping.get("source_to_canonical", {}).values()


def test_task_record_rejects_v9_labels_in_payload() -> None:
    record = _record()
    payload = record.model_dump(mode="json")
    payload["payload"]["entity_labels"] = ["B-FactorRole"]
    payload["payload"]["tokens"] = ["x"]
    payload["payload"]["role_labels"] = ["O"]
    payload["checksum"] = "0" * 64

    with pytest.raises(ValueError, match="cannot emit canonical N-Truth v9 labels"):
        TaskRecord.model_validate(payload)


@pytest.mark.parametrize("label", sorted(FORBIDDEN_CANONICAL_V9_LABELS))
def test_entity_roles_payload_cannot_carry_named_v9_label(label: str) -> None:
    payload = _record().model_dump(mode="json")
    payload["payload"]["tokens"] = ["cell"]
    payload["payload"]["entity_labels"] = [f"B-{label}"]
    payload["payload"]["role_labels"] = ["O"]
    payload["payload"]["token_offsets"] = None

    with pytest.raises(ValueError, match="cannot emit canonical N-Truth v9 labels"):
        TaskRecord.model_validate(payload)


def test_public_adapter_never_emits_gold() -> None:
    record = _record()
    assert record.authority_level is not AuthorityLevel.NTRUTH_GOLD
    dumped = record.model_dump(mode="json")
    dumped["authority_level"] = AuthorityLevel.NTRUTH_GOLD.value
    with pytest.raises(ValueError, match="public adapters must not emit NTRUTH_GOLD"):
        TaskRecord.model_validate(dumped)
    assert ADAPTER_NAME == "sourcedata_entity_roles"
