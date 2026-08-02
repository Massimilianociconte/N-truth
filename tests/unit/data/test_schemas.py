"""Tests for CommonEnvelope, discriminated unions, and validation invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.data.schemas import (
    CommonEnvelope,
    Eligibility,
    NativeAnnotationTier,
    NTruthUsageTier,
    OffsetAuthority,
    Provenance,
    SourceReference,
    SpanRecord,
    SpanRelationPayload,
    SplitAssignment,
    TokenClassificationPayload,
)


def test_token_classification_payload_valid():
    payload = TokenClassificationPayload(
        tokens=["Cells", "were", "glucose"],
        normalized_text="Cells were glucose",
        token_offsets=[(0, 5), (6, 10), (11, 18)],
        offset_authority=OffsetAuthority.DERIVED_NORMALIZED_TEXT,
        entity_tags=["O", "O", "B-SMALL_MOLECULE"],
        role_tags=["O", "O", "B-CONTROLLED_VAR"],
    )
    assert payload.kind == "token_classification"


def test_token_classification_mismatched_lengths():
    with pytest.raises(ValidationError, match="entity_tags length"):
        TokenClassificationPayload(
            tokens=["Cells", "were"],
            entity_tags=["O"],
        )


def test_common_envelope_test_split_cannot_be_training_eligible():
    with pytest.raises(ValidationError, match="cannot be training_eligible=True"):
        CommonEnvelope(
            record_id="rec:1",
            source=SourceReference(dataset="ds", version="1", commit="c", document_id="d", segment_id="s"),
            split=SplitAssignment(name="test", authority="official", group_id="g1"),
            eligibility=Eligibility(training_eligible=True, evaluation_eligible=True, requires_review=False),
            provenance=Provenance(source_url="url", sha256="hash", transform_version="1.0"),
            native_annotation_tier=NativeAnnotationTier.HUMAN_CURATED_GOLD,
            allowed_tasks=["task"],
            forbidden_targets=["independent_n"],
            task_type="token_classification",
            payload=TokenClassificationPayload(tokens=["a"], entity_tags=["O"]),
        )


def test_common_envelope_missing_annotation_tier_gold_restriction():
    with pytest.raises(ValidationError, match="Missing annotation"):
        CommonEnvelope(
            record_id="rec:2",
            source=SourceReference(dataset="ds", version="1", commit="c", document_id="d", segment_id="s"),
            split=SplitAssignment(name="train", authority="official", group_id="g1"),
            eligibility=Eligibility(training_eligible=False, evaluation_eligible=False, requires_review=True),
            provenance=Provenance(source_url="url", sha256="hash", transform_version="1.0"),
            native_annotation_tier=NativeAnnotationTier.HUMAN_CURATED_GOLD,
            allowed_tasks=["task"],
            forbidden_targets=["independent_n"],
            annotation_status="missing_annotation_file",
            task_type="token_classification",
            payload=TokenClassificationPayload(tokens=["a"], entity_tags=["O"]),
        )
