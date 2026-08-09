"""Normative PRD v8 KnowledgeState and open-world value wrapper."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import StrEnum

from pydantic import model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr


class KnowledgeState(StrEnum):
    PRESENT = "PRESENT"
    ABSENT_EXPLICIT = "ABSENT_EXPLICIT"
    NOT_REPORTED = "NOT_REPORTED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTING = "CONFLICTING"


def _blank_or_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (tuple, list, dict, set, frozenset)):
        return not value
    return False


def _ambiguous_scientific_path(value: object, path: str = "$") -> str | None:
    if value is None:
        return path
    if isinstance(value, str):
        return path if not value.strip() else None
    if isinstance(value, Mapping):
        if not value:
            return path
        for key, item in value.items():
            if isinstance(key, str) and not key.strip():
                return f"{path}.<blank-key>"
            issue = _ambiguous_scientific_path(item, f"{path}.{key}")
            if issue is not None:
                return issue
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return path
        for index, item in enumerate(value):
            issue = _ambiguous_scientific_path(item, f"{path}[{index}]")
            if issue is not None:
                return issue
        return None
    if isinstance(value, (set, frozenset)):
        if not value:
            return path
        for index, item in enumerate(value):
            issue = _ambiguous_scientific_path(item, f"{path}[{index}]")
            if issue is not None:
                return issue
    return None


def ensure_unambiguous_scientific_payload(value: object) -> None:
    """Reject any nested bare null, blank string or empty scientific container."""

    issue = _ambiguous_scientific_path(value)
    if issue is not None:
        raise ValueError(f"ambiguous scientific payload at {issue}")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class KnowledgeValue[T](KernelModel):
    """A scientific value whose absence semantics are always explicit."""

    knowledge_state: KnowledgeState
    value: T | None = None
    conflicting_values: tuple[T, ...] = ()
    evidence_ids: tuple[NonBlankStr, ...] = ()
    source_scope_ids: tuple[NonBlankStr, ...] = ()
    rationale: NonBlankStr | None = None
    claim_scope_id: NonBlankStr | None = None
    query_scope_id: NonBlankStr | None = None

    @model_validator(mode="after")
    def _open_world_invariants(self) -> KnowledgeValue[T]:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique and order-preserving")
        if len(set(self.source_scope_ids)) != len(self.source_scope_ids):
            raise ValueError("source_scope_ids must be unique and order-preserving")

        state = self.knowledge_state
        if state is KnowledgeState.PRESENT:
            ensure_unambiguous_scientific_payload(self.value)
            if not self.evidence_ids:
                raise ValueError("PRESENT requires evidence_ids")
            if self.conflicting_values:
                raise ValueError("PRESENT cannot carry conflicting_values")
            return self

        if isinstance(self.value, str) and not self.value.strip():
            raise ValueError("blank scientific strings are forbidden")

        if state is KnowledgeState.CONFLICTING:
            if self.value is not None:
                raise ValueError("CONFLICTING retains alternatives, not one preferred value")
            if len(self.conflicting_values) < 2:
                raise ValueError("CONFLICTING requires at least two retained values")
            for item in self.conflicting_values:
                ensure_unambiguous_scientific_payload(item)
            if len({_canonical(item) for item in self.conflicting_values}) < 2:
                raise ValueError("CONFLICTING requires at least two distinct values")
            if not self.evidence_ids:
                raise ValueError("CONFLICTING requires evidence_ids")
            return self

        if self.conflicting_values:
            raise ValueError(f"{state.value} cannot carry conflicting_values")
        if self.value is not None and not _blank_or_empty(self.value):
            raise ValueError(f"{state.value} cannot carry a present scientific value")

        if state is KnowledgeState.ABSENT_EXPLICIT and not self.evidence_ids:
            raise ValueError("ABSENT_EXPLICIT requires evidence_ids")
        if state is KnowledgeState.NOT_REPORTED and not self.source_scope_ids:
            raise ValueError("NOT_REPORTED requires source_scope_ids")
        if state is KnowledgeState.UNKNOWN:
            if self.rationale is None:
                raise ValueError("UNKNOWN requires rationale")
            if self.claim_scope_id is None and self.query_scope_id is None:
                raise ValueError("UNKNOWN requires claim_scope_id or query_scope_id")
        if state is KnowledgeState.NOT_APPLICABLE:
            if self.rationale is None:
                raise ValueError("NOT_APPLICABLE requires rationale")
            if self.claim_scope_id is None and self.query_scope_id is None:
                raise ValueError("NOT_APPLICABLE requires claim_scope_id or query_scope_id")
        return self


ScientificKnowledgeValue = KnowledgeValue[object]

__all__ = [
    "KnowledgeState",
    "KnowledgeValue",
    "ScientificKnowledgeValue",
    "ensure_unambiguous_scientific_payload",
]
