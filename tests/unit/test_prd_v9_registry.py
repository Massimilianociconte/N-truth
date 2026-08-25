"""PRD v9 Canonical Schema Registry contract."""

from __future__ import annotations

import json

import pytest

from ntruth.schemas.factor_role import ContrastType, FactorRole
from ntruth.schemas.knowledge import KnowledgeState
from ntruth.schemas.support_profile import SUPPORT_PROFILE_DIMENSIONS
from ntruth.schemas.v9_registry import (
    CANONICAL_SCHEMA_REGISTRY,
    DEPRECATED_V8_WRITER_ALIASES,
    REGISTRY_ID,
    CanonicalSchemaRegistry,
    ContrastSupportStatus,
    MaterialLineageEventKind,
    assert_known_registry_object,
    assert_known_token,
    assert_v9_writer_payload,
    dump_registry,
    registry_fingerprint,
)


def test_registry_id_and_required_token_lists() -> None:
    payload = dump_registry()
    assert REGISTRY_ID == "ntruth-canonical-schema-registry-9.0.0"
    assert payload["registry_id"] == REGISTRY_ID
    assert payload["factor_roles"] == [member.value for member in FactorRole]
    assert payload["contrast_types"] == [member.value for member in ContrastType]
    assert payload["contrast_support_statuses"] == [
        member.value for member in ContrastSupportStatus
    ]
    assert payload["material_lineage_event_kinds"] == [
        "SPLIT",
        "ALIQUOT",
        "POOL",
        "REPLATE",
        "PASSAGE",
        "THAW",
        "MERGE",
        "SUBSAMPLE",
        "DERIVE",
    ]
    assert payload["support_profile_dimensions"] == list(SUPPORT_PROFILE_DIMENSIONS)
    assert payload["knowledge_states"] == [member.value for member in KnowledgeState]
    aliases = payload["deprecated_v8_writer_aliases"]
    assert isinstance(aliases, list)
    assert "independent_n" in aliases
    assert json.loads(json.dumps(payload)) == payload
    assert_known_registry_object(CANONICAL_SCHEMA_REGISTRY)
    assert isinstance(CANONICAL_SCHEMA_REGISTRY, CanonicalSchemaRegistry)


def test_fingerprint_is_stable_across_two_calls() -> None:
    first = registry_fingerprint()
    second = registry_fingerprint()
    assert first == second
    assert len(first) == 64
    assert int(first, 16) >= 0


def test_assert_known_token_rejects_unknown_enum() -> None:
    assert_known_token("factor_role", FactorRole.ASSIGNED_INTERVENTION.value)
    assert_known_token("contrast_type", ContrastType.ASSIGNED_INTERVENTION_EFFECT.value)
    assert_known_token("knowledge_state", KnowledgeState.UNKNOWN.value)
    assert_known_token("material_lineage", MaterialLineageEventKind.SPLIT.value)
    with pytest.raises(ValueError, match="unknown factor_role token"):
        assert_known_token("factor_role", "NOT_A_FACTOR_ROLE")
    with pytest.raises(ValueError, match="unknown registry category"):
        assert_known_token("not_a_category", "ASSIGNED_INTERVENTION")


def test_writers_cannot_emit_deprecated_v8_aliases() -> None:
    assert "independent_n" in DEPRECATED_V8_WRITER_ALIASES
    assert_v9_writer_payload(
        {
            "experimental_unit_count": 6,
            "support_profile": {"directness": "DIRECT_RECORD"},
            "support_grade": {"token": "DIRECT_SINGLE_SOURCE"},
        }
    )
    with pytest.raises(ValueError, match="independent_n"):
        assert_v9_writer_payload({"independent_n": 6})
    with pytest.raises(ValueError, match="sole support authority"):
        assert_v9_writer_payload({"support_grade": {"token": "DIRECT_SINGLE_SOURCE"}})
