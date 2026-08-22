"""PRD v9 Canonical Schema Registry.

Single machine-readable source for FactorRole, ContrastType, ContrastSupport
status, MaterialLineage event kinds, SupportProfile dimensions and imported
KnowledgeState values. Writers cannot emit deprecated v8 aliases.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal

from ntruth.schemas.contrast_support import ContrastSupportStatus
from ntruth.schemas.core import FrozenModel
from ntruth.schemas.factor_role import ContrastType, FactorRole
from ntruth.schemas.knowledge import KnowledgeState
from ntruth.schemas.material_lineage import MaterialLineageKind
from ntruth.schemas.support_profile import SUPPORT_PROFILE_DIMENSIONS

REGISTRY_ID: Literal["ntruth-canonical-schema-registry-9.0.0"] = (
    "ntruth-canonical-schema-registry-9.0.0"
)
SUPPORT_GRADE_WRITER_POLICY: Literal["read_only_compatibility_not_sole_authority"] = (
    "read_only_compatibility_not_sole_authority"
)
DEPRECATED_V8_WRITER_ALIASES: frozenset[str] = frozenset({"independent_n"})
_SUPPORT_GRADE_KEYS = frozenset({"support_grade", "SupportGrade"})
_SUPPORT_PROFILE_KEYS = frozenset({"support_profile", "SupportProfile"})

MaterialLineageEventKind = MaterialLineageKind


def _enum_values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    return tuple(member.value for member in enum_cls)


REGISTRY_CATEGORIES: dict[str, frozenset[str]] = {
    "factor_role": frozenset(_enum_values(FactorRole)),
    "contrast_type": frozenset(_enum_values(ContrastType)),
    "contrast_support": frozenset(_enum_values(ContrastSupportStatus)),
    "material_lineage": frozenset(_enum_values(MaterialLineageEventKind)),
    "support_profile_dimension": frozenset(SUPPORT_PROFILE_DIMENSIONS),
    "knowledge_state": frozenset(_enum_values(KnowledgeState)),
}


class CanonicalSchemaRegistry(FrozenModel):
    """Frozen dump of the v9 token registry."""

    registry_id: Literal["ntruth-canonical-schema-registry-9.0.0"] = REGISTRY_ID
    factor_roles: tuple[str, ...]
    contrast_types: tuple[str, ...]
    contrast_support_statuses: tuple[str, ...]
    material_lineage_event_kinds: tuple[str, ...]
    support_profile_dimensions: tuple[str, ...]
    knowledge_states: tuple[str, ...]
    deprecated_v8_writer_aliases: tuple[str, ...]
    support_grade_writer_policy: Literal["read_only_compatibility_not_sole_authority"] = (
        SUPPORT_GRADE_WRITER_POLICY
    )


CANONICAL_SCHEMA_REGISTRY = CanonicalSchemaRegistry(
    factor_roles=_enum_values(FactorRole),
    contrast_types=_enum_values(ContrastType),
    contrast_support_statuses=_enum_values(ContrastSupportStatus),
    material_lineage_event_kinds=_enum_values(MaterialLineageEventKind),
    support_profile_dimensions=SUPPORT_PROFILE_DIMENSIONS,
    knowledge_states=_enum_values(KnowledgeState),
    deprecated_v8_writer_aliases=tuple(sorted(DEPRECATED_V8_WRITER_ALIASES)),
)


def dump_registry() -> dict[str, object]:
    """Return a JSON-serializable snapshot of the canonical registry."""

    return CANONICAL_SCHEMA_REGISTRY.model_dump(mode="json")


def registry_fingerprint() -> str:
    """Return the SHA-256 of the canonical JSON registry (sorted keys)."""

    canonical = json.dumps(
        dump_registry(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assert_known_token(category: str, token: str) -> None:
    """Fail closed when the category or token is not in the v9 registry."""

    allowed = REGISTRY_CATEGORIES.get(category)
    if allowed is None:
        raise ValueError(f"unknown registry category: {category!r}")
    if token not in allowed:
        raise ValueError(f"unknown {category} token: {token!r}")


def assert_v9_writer_payload(payload: object, *, path: str = "$") -> None:
    """Reject deprecated v8 writer aliases and SupportGrade as sole authority."""

    if isinstance(payload, Mapping):
        keys = {str(key) for key in payload}
        if "independent_n" in keys:
            raise ValueError(f"v9 writers cannot emit deprecated alias independent_n at {path}")
        if keys & _SUPPORT_GRADE_KEYS and not keys & _SUPPORT_PROFILE_KEYS:
            raise ValueError(
                f"SupportGrade cannot be the sole support authority at {path}; emit SupportProfile"
            )
        for key, value in payload.items():
            if value == "independent_n":
                raise ValueError(
                    f"v9 writers cannot emit deprecated alias independent_n at {path}.{key}"
                )
            assert_v9_writer_payload(value, path=f"{path}.{key}")
        return
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, item in enumerate(payload):
            assert_v9_writer_payload(item, path=f"{path}[{index}]")
        return
    if payload == "independent_n":
        raise ValueError(f"v9 writers cannot emit deprecated alias independent_n at {path}")


def assert_known_registry_object(registry: Mapping[str, Any] | CanonicalSchemaRegistry) -> None:
    """Fail closed if a dumped registry object drifts from the shipped tokens."""

    payload = dump_registry() if isinstance(registry, CanonicalSchemaRegistry) else dict(registry)
    if payload.get("registry_id") != REGISTRY_ID:
        raise ValueError(f"unknown registry_id: {payload.get('registry_id')!r}")
    for category, field_name in (
        ("factor_role", "factor_roles"),
        ("contrast_type", "contrast_types"),
        ("contrast_support", "contrast_support_statuses"),
        ("material_lineage", "material_lineage_event_kinds"),
        ("support_profile_dimension", "support_profile_dimensions"),
        ("knowledge_state", "knowledge_states"),
    ):
        tokens = payload.get(field_name)
        if not isinstance(tokens, list | tuple):
            raise ValueError(f"registry field {field_name} must be a list of tokens")
        for token in tokens:
            if not isinstance(token, str):
                raise ValueError(f"registry field {field_name} contains a non-string token")
            assert_known_token(category, token)


__all__ = [
    "CANONICAL_SCHEMA_REGISTRY",
    "DEPRECATED_V8_WRITER_ALIASES",
    "REGISTRY_CATEGORIES",
    "REGISTRY_ID",
    "SUPPORT_GRADE_WRITER_POLICY",
    "CanonicalSchemaRegistry",
    "ContrastSupportStatus",
    "MaterialLineageEventKind",
    "MaterialLineageKind",
    "assert_known_registry_object",
    "assert_known_token",
    "assert_v9_writer_payload",
    "dump_registry",
    "registry_fingerprint",
]
