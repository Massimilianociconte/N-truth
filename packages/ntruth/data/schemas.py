"""Strongly-typed Pydantic schemas, discriminated unions, and validation invariants for N-Truth data."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class OffsetAuthority(StrEnum):
    UPSTREAM = "upstream"
    DERIVED_NORMALIZED_TEXT = "derived_normalized_text"
    UNAVAILABLE = "unavailable"


class NativeAnnotationTier(StrEnum):
    HUMAN_CURATED_GOLD = "HUMAN_CURATED_GOLD"
    HUMAN_CURATED_PARTIAL = "HUMAN_CURATED_PARTIAL"
    DERIVED_FROM_UPSTREAM = "DERIVED_FROM_UPSTREAM"
    MISSING_ANNOTATION = "MISSING_ANNOTATION"
    UNVERIFIED = "UNVERIFIED"


class NTruthUsageTier(StrEnum):
    SILVER_AUXILIARY = "SILVER_AUXILIARY"


class SourceReference(BaseModel):
    dataset: str
    version: str
    commit: str
    document_id: str
    segment_id: str


class SplitAssignment(BaseModel):
    name: Literal["train", "validation", "test", "trial"]
    authority: str
    group_id: str


class Eligibility(BaseModel):
    training_eligible: bool
    evaluation_eligible: bool
    requires_review: bool


class Provenance(BaseModel):
    source_url: str
    sha256: str
    transform_version: str


class TokenClassificationPayload(BaseModel):
    kind: Literal["token_classification"] = "token_classification"
    tokens: list[str]
    token_offsets: list[tuple[int, int]] | None = None
    offset_authority: OffsetAuthority = OffsetAuthority.UNAVAILABLE
    normalized_text: str | None = None
    entity_tags: list[str] | None = None
    role_tags: list[str] | None = None
    tag_mask: list[int] | None = None

    @model_validator(mode="after")
    def check_token_lengths(self) -> TokenClassificationPayload:
        n = len(self.tokens)
        if self.entity_tags is not None and len(self.entity_tags) != n:
            raise ValueError(
                f"entity_tags length ({len(self.entity_tags)}) does not match tokens length ({n})"
            )
        if self.role_tags is not None and len(self.role_tags) != n:
            raise ValueError(
                f"role_tags length ({len(self.role_tags)}) does not match tokens length ({n})"
            )
        if self.tag_mask is not None and len(self.tag_mask) != n:
            raise ValueError(
                f"tag_mask length ({len(self.tag_mask)}) does not match tokens length ({n})"
            )
        if self.token_offsets is not None and len(self.token_offsets) != n:
            raise ValueError(
                f"token_offsets length ({len(self.token_offsets)}) does not match tokens length ({n})"
            )
        if (
            self.offset_authority == OffsetAuthority.DERIVED_NORMALIZED_TEXT
            and not self.normalized_text
        ):
            raise ValueError(
                "offset_authority DERIVED_NORMALIZED_TEXT requires non-null normalized_text"
            )
        if self.offset_authority == OffsetAuthority.UPSTREAM and self.token_offsets is None:
            raise ValueError("offset_authority UPSTREAM requires non-null token_offsets")
        return self


class SpanRecord(BaseModel):
    span_id: str
    label: str
    start: int
    end: int
    text: str


class RelationRecord(BaseModel):
    relation_id: str
    source_span_id: str
    target_span_id: str
    relation_type: str


class SpanRelationPayload(BaseModel):
    kind: Literal["span_relation"] = "span_relation"
    text: str
    spans: list[SpanRecord] = Field(default_factory=list)
    relations: list[RelationRecord] = Field(default_factory=list)


class DocumentClassificationPayload(BaseModel):
    kind: Literal["document_classification"] = "document_classification"
    text: str
    labels: list[str] = Field(default_factory=list)


class MentionRecord(BaseModel):
    mention_id: str
    start: int
    end: int
    text: str


class CoreferenceChain(BaseModel):
    chain_id: str
    mention_ids: list[str] = Field(default_factory=list)


class CoreferencePayload(BaseModel):
    kind: Literal["coreference"] = "coreference"
    text: str
    mentions: list[MentionRecord] = Field(default_factory=list)
    chains: list[CoreferenceChain] = Field(default_factory=list)


Payload = Annotated[
    TokenClassificationPayload
    | SpanRelationPayload
    | DocumentClassificationPayload
    | CoreferencePayload,
    Field(discriminator="kind"),
]


class CommonEnvelope(BaseModel):
    record_id: str
    source: SourceReference
    split: SplitAssignment
    eligibility: Eligibility
    provenance: Provenance
    native_annotation_tier: NativeAnnotationTier
    ntruth_usage_tier: NTruthUsageTier = NTruthUsageTier.SILVER_AUXILIARY
    allowed_tasks: list[str]
    forbidden_targets: list[str]
    annotation_status: str = "annotated"
    task_type: Literal[
        "token_classification", "span_relation", "document_classification", "coreference"
    ]
    payload: Payload

    @model_validator(mode="after")
    def check_invariants(self) -> CommonEnvelope:
        # Invariant: split test or trial cannot be training_eligible
        if self.split.name in {"test", "trial"} and self.eligibility.training_eligible:
            raise ValueError(f"Split {self.split.name} cannot be training_eligible=True")
        # Invariant: requires_review=True cannot be training_eligible=True
        if self.eligibility.requires_review and self.eligibility.training_eligible:
            raise ValueError("Record requiring review cannot be training_eligible=True")
        # Invariant: missing_annotation_file or requires_review cannot be HUMAN_CURATED_GOLD
        if (
            self.annotation_status == "missing_annotation_file" or self.eligibility.requires_review
        ) and self.native_annotation_tier == NativeAnnotationTier.HUMAN_CURATED_GOLD:
            raise ValueError(
                "Missing annotation or review-required record cannot have native_annotation_tier=HUMAN_CURATED_GOLD"
            )
        return self
