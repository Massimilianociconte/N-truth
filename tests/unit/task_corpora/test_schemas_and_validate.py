"""Schema invariants, licence fail-closed, BIO validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.task_corpora.authority import AuthorityLevel, LicenseStatus, SupervisionSource
from ntruth.task_corpora.schemas import (
    EntityRolesPayload,
    LicenseUseDecision,
    SourceIdentity,
    TaskRecord,
    TransformLineage,
)
from ntruth.task_corpora.validate import (
    ValidationError as VE,
)
from ntruth.task_corpora.validate import (
    assert_bio_tags_known,
    assert_token_label_lengths,
)


def _licence(**kwargs) -> LicenseUseDecision:
    base = dict(
        license_status=LicenseStatus.RESTRICTED,
        training_allowed=False,
        redistribution_allowed=False,
        derived_labels_allowed=True,
        decision_basis="test",
        reviewed_at="2026-08-03T00:00:00Z",
    )
    base.update(kwargs)
    return LicenseUseDecision(**base)


def _record(**kwargs) -> TaskRecord:
    payload = EntityRolesPayload(
        tokens=["a", "b"],
        entity_labels=["O", "B-GENEPROD"],
        role_labels=["O", "B-MEASURED_VAR"],
    )
    data = dict(
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
        ],
        licence=_licence(),
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
        payload=payload,
    )
    data.update(kwargs)
    return TaskRecord(**data)


def test_payload_length_mismatch_rejected():
    with pytest.raises(ValidationError):
        EntityRolesPayload(
            tokens=["a", "b"],
            entity_labels=["O"],
            role_labels=["O", "O"],
        )


def test_assert_token_label_lengths():
    assert_token_label_lengths(["a"], ["O"], ["O"])
    with pytest.raises(VE):
        assert_token_label_lengths(["a", "b"], ["O"], ["O", "O"])


def test_unknown_bio_tags():
    unknown = assert_bio_tags_known(["B-GENEPROD", "B-FOO", "O"], {"GENEPROD"})
    assert unknown == ["B-FOO"]


def test_auxiliary_requires_forbidden_gold_uses():
    with pytest.raises(ValidationError):
        _record(forbidden_uses=["experimental_unit_gold"])


def test_test_split_cannot_be_training_eligible():
    with pytest.raises(ValidationError):
        _record(split="test", training_eligible=True)


def test_unknown_licence_cannot_train():
    with pytest.raises(ValidationError):
        _record(
            licence=_licence(license_status=LicenseStatus.UNKNOWN, training_allowed=True),
            training_eligible=True,
        )


def test_training_eligible_requires_licence_flag():
    with pytest.raises(ValidationError):
        _record(training_eligible=True)  # licence.training_allowed False


def test_synthetic_forbidden_c0_c1():
    with pytest.raises(ValidationError):
        _record(supervision_source=SupervisionSource.SYNTHETIC)


def test_ntruth_gold_forbidden_for_public_adapter():
    with pytest.raises(ValidationError):
        _record(authority_level=AuthorityLevel.NTRUTH_GOLD)
