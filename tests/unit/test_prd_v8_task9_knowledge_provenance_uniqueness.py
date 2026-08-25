"""PRD v8 Task 9 regressions for exact KnowledgeValue provenance identity."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


@pytest.mark.parametrize(
    "payload",
    [
        {
            "knowledge_state": KnowledgeState.PRESENT,
            "value": "documented",
            "evidence_ids": ("EVIDENCE-001", "EVIDENCE-001"),
        },
        {
            "knowledge_state": KnowledgeState.ABSENT_EXPLICIT,
            "evidence_ids": ("EVIDENCE-001", "EVIDENCE-001"),
        },
        {
            "knowledge_state": KnowledgeState.NOT_REPORTED,
            "source_scope_ids": ("SOURCE-METHODS", "SOURCE-METHODS"),
        },
        {
            "knowledge_state": KnowledgeState.UNKNOWN,
            "rationale": "The reviewed evidence does not resolve the value.",
            "query_scope_id": "IQ-001",
            "evidence_ids": ("EVIDENCE-001", "EVIDENCE-001"),
        },
        {
            "knowledge_state": KnowledgeState.NOT_APPLICABLE,
            "rationale": "This value is outside the declared query scope.",
            "query_scope_id": "IQ-001",
            "source_scope_ids": ("SOURCE-METHODS", "SOURCE-METHODS"),
        },
        {
            "knowledge_state": KnowledgeState.CONFLICTING,
            "conflicting_values": ("A", "B"),
            "evidence_ids": ("EVIDENCE-001", "EVIDENCE-001"),
        },
    ],
)
def test_knowledge_value_rejects_duplicate_provenance_ids(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="unique and order-preserving"):
        KnowledgeValue[object].model_validate(payload)


def test_knowledge_value_preserves_distinct_provenance_order() -> None:
    value = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EVIDENCE-002", "EVIDENCE-001"),
        source_scope_ids=("SOURCE-SAMPLE-SHEET", "SOURCE-METHODS"),
    )

    assert value.evidence_ids == ("EVIDENCE-002", "EVIDENCE-001")
    assert value.source_scope_ids == ("SOURCE-SAMPLE-SHEET", "SOURCE-METHODS")
