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
            "interference_gold",
            "estimand_gold",
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


def test_evaluation_eligible_fails_closed_when_unknown():
    with pytest.raises(ValidationError):
        _record(
            split="validation",
            evaluation_eligible=True,  # licence.evaluation_allowed defaults unknown
        )


def test_evaluation_eligible_requires_explicit_true():
    rec = _record(
        split="validation",
        evaluation_eligible=True,
        licence=_licence(evaluation_allowed=True),
    )
    assert rec.evaluation_eligible is True


def test_training_eligible_requires_development_allowed():
    with pytest.raises(ValidationError):
        _record(
            training_eligible=True,
            licence=_licence(
                training_allowed=True,
                development_allowed=False,
                evaluation_allowed=False,
            ),
        )


def test_groups_crossing_splits_counter():
    from ntruth.task_corpora.validate import count_groups_crossing_splits

    assert count_groups_crossing_splits({"a": {"train"}, "b": {"test"}}) == 0
    assert count_groups_crossing_splits({"a": {"train", "test"}}) == 1


def test_synthetic_forbidden_c0_c1():
    with pytest.raises(ValidationError):
        _record(supervision_source=SupervisionSource.SYNTHETIC)


def test_ntruth_gold_forbidden_for_public_adapter():
    with pytest.raises(ValidationError):
        _record(authority_level=AuthorityLevel.NTRUTH_GOLD)


def test_auxiliary_must_forbid_interference_and_estimand_gold():
    with pytest.raises(ValidationError):
        _record(
            forbidden_uses=[
                "experimental_unit_gold",
                "independent_n_gold",
                "pseudoreplication_verdict_gold",
                "allocation_gold",
                "biological_independence_gold",
                # missing interference_gold and estimand_gold
            ]
        )


def test_author_assertion_is_not_experimental_unit_gold_label():
    """Reported assertions remain distinct from gold roles (semantic invariant)."""
    from ntruth.task_corpora.config import FORBIDDEN_GOLD_USES

    assert "experimental_unit_gold" in FORBIDDEN_GOLD_USES
    # AUTHOR_ASSERTION is a reporting semantics tag, not a gold use.
    assert "AUTHOR_ASSERTION" not in FORBIDDEN_GOLD_USES
    assert "REPORTED_METHOD_INDICATOR" not in FORBIDDEN_GOLD_USES


def test_build_manifest_readiness_triad_defaults():
    from ntruth.task_corpora.schemas import BuildManifest

    m = BuildManifest(
        task_type="entity_roles",
        source_dataset="SourceData",
        source_version="2.0.3",
        adapter="test",
        schema_version="0.2.0",
        transform_version="0.2.0",
        mapping_version="0.1.0",
        seed="s",
        root="/tmp",
        output_dir="out",
        record_counts={"train": 0},
        exclusion_counts={},
        records_sha256="00" * 32,
        groups_crossing_splits=0,
    )
    assert m.engineering_readiness == "VERIFIED_FOR_C0_C1"
    assert m.data_readiness == "BLOCKED"
    assert m.scientific_validation == "NOT_STARTED"
    assert m.reality_gate_status == "BLOCKED"
    assert m.reality_gate_satisfied_by_public_corpora is False
    assert m.reality_gate_satisfied_by_silver_adapter is False
    assert m.ntruth_partition_approved is False
    assert m.model_use_status == "BLOCKED"


def test_permission_helpers_fail_closed():
    from ntruth.task_corpora.license_loader import (
        evaluation_permitted,
        permission_granted,
        training_permitted,
    )

    assert permission_granted(True) is True
    assert permission_granted(False) is False
    assert permission_granted("unknown") is False
    lic = _licence(
        training_allowed=True,
        development_allowed="unknown",
        evaluation_allowed="unknown",
    )
    assert training_permitted(lic) is False
    assert evaluation_permitted(lic) is False
