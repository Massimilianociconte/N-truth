"""Normative PRD v8 KnowledgeState and open-world value wrapper."""

from __future__ import annotations

import json
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
        state = self.knowledge_state
        if state is KnowledgeState.PRESENT:
            if _blank_or_empty(self.value):
                raise ValueError("PRESENT requires a non-null, non-blank, non-empty value")
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
            if any(_blank_or_empty(item) for item in self.conflicting_values):
                raise ValueError("CONFLICTING values must be non-blank and non-empty")
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
        if state is KnowledgeState.NOT_APPLICABLE:
            if self.rationale is None:
                raise ValueError("NOT_APPLICABLE requires rationale")
            if self.claim_scope_id is None and self.query_scope_id is None:
                raise ValueError("NOT_APPLICABLE requires claim_scope_id or query_scope_id")
        return self


ScientificKnowledgeValue = KnowledgeValue[object]

__all__ = ["KnowledgeState", "KnowledgeValue", "ScientificKnowledgeValue"]
