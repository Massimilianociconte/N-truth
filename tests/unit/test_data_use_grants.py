"""PRD v9 Appendix E data-use grants: fail-closed per-use authorization."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from ntruth.governance.data_use import (
    DataUseGrant,
    DataUseKind,
    DerivativeArtifactPolicy,
    PermittedUses,
    RevocationPolicy,
    TypedKnowledgeState,
    TypedKnowledgeValue,
    authorize_use,
    retention_expired,
)

RETENTION_END = date(2027, 12, 31)


def _grant(**overrides: Any) -> DataUseGrant:
    fields: dict[str, Any] = {
        "grant_id": "GRANT-001",
        "source_family_id": "STUDY-FAMILY-9001",
        "contributor_actor_id": "contributor-001",
        "custodian_actor_id": "custodian-001",
        "permission_basis": "CC-BY-4.0 verified 2026-08-25",
        "retention_until": TypedKnowledgeValue[date](
            knowledge_state=TypedKnowledgeState.PRESENT,
            value=RETENTION_END,
        ),
        "revocation_policy": RevocationPolicy.FUTURE_VERSIONS_ONLY,
        "derivative_artifact_policy": DerivativeArtifactPolicy.ALLOWED_WITH_LINEAGE,
        "verified_by": "data-custodian-reviewer-001",
    }
    fields.update(overrides)
    return DataUseGrant.model_validate(fields)


def test_default_grant_denies_every_use() -> None:
    grant = _grant()
    for use in DataUseKind:
        assert authorize_use(grant, use) is False


def test_listed_uses_are_authorized() -> None:
    grant = _grant(
        permitted_uses=PermittedUses(annotation=True, parser_training=True),
    )
    assert authorize_use(grant, DataUseKind.ANNOTATION) is True
    assert authorize_use(grant, DataUseKind.PARSER_TRAINING) is True
    assert authorize_use(grant, DataUseKind.REDISTRIBUTION) is False


def test_unlisted_use_is_never_defaulted_to_true() -> None:
    grant = _grant(permitted_uses=PermittedUses(redistribution=True))
    for use in DataUseKind:
        expected = use is DataUseKind.REDISTRIBUTION
        assert authorize_use(grant, use) is expected


def test_retention_window_is_enforced_only_with_as_of() -> None:
    grant = _grant(permitted_uses=PermittedUses(external_evaluation=True))
    assert authorize_use(grant, DataUseKind.EXTERNAL_EVALUATION) is True
    assert (
        authorize_use(
            grant,
            DataUseKind.EXTERNAL_EVALUATION,
            as_of=RETENTION_END,
        )
        is True
    )
    assert (
        authorize_use(
            grant,
            DataUseKind.EXTERNAL_EVALUATION,
            as_of=date(2028, 1, 1),
        )
        is False
    )


def test_unknown_retention_stays_authorizable_but_reports_none() -> None:
    grant = _grant(
        permitted_uses=PermittedUses(annotation=True),
        retention_until=TypedKnowledgeValue[date](knowledge_state=TypedKnowledgeState.UNKNOWN),
    )
    assert authorize_use(grant, DataUseKind.ANNOTATION) is True
    assert authorize_use(grant, DataUseKind.ANNOTATION, as_of=date(2999, 1, 1)) is True
    assert retention_expired(grant, date(2999, 1, 1)) is None


def test_typed_knowledge_value_state_value_agreement() -> None:
    with pytest.raises(ValidationError):
        TypedKnowledgeValue[date](knowledge_state=TypedKnowledgeState.PRESENT, value=None)
    with pytest.raises(ValidationError):
        TypedKnowledgeValue[date](
            knowledge_state=TypedKnowledgeState.UNKNOWN,
            value=RETENTION_END,
        )


def test_revocation_and_derivative_policies_round_trip() -> None:
    grant = _grant(
        revocation_policy=RevocationPolicy.IMMEDIATE,
        derivative_artifact_policy=DerivativeArtifactPolicy.REVIEW_REQUIRED,
    )
    assert grant.revocation_policy is RevocationPolicy.IMMEDIATE
    assert grant.derivative_artifact_policy is DerivativeArtifactPolicy.REVIEW_REQUIRED


def test_cloud_use_fails_closed_by_default() -> None:
    assert _grant().cloud_use_allowed is False


def test_missing_permission_basis_or_verifier_rejected() -> None:
    with pytest.raises(ValidationError):
        _grant(permission_basis="")
    with pytest.raises(ValidationError):
        _grant(verified_by="   ")
