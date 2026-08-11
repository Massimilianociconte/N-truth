"""MVT-A stage schema: candidate-only parser outputs (PRD v8 §13.6).

Parser stages may emit evidence/entity/count/factor *candidates*. They must
never emit final independent_n, pseudoreplication verdict, RuleResult, or final
DeterminabilityState.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from ntruth.schemas.core import FrozenModel

FORBIDDEN_FINAL_FIELDS: frozenset[str] = frozenset(
    {
        "n",
        "independent_n",
        "experimental_unit",
        "experimental_unit_count",
        "final_count",
        "determinability",
        "adequacy",
        "design_adequacy",
        "design_verdict",
        "pseudoreplication",
        "pseudoreplication_verdict",
        "rule_result",
        "determinability_state",
        "final_determinability",
    }
)


class StageCompletionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class StageErrorCode(StrEnum):
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    CHUNK_COVERAGE_INCOMPLETE = "CHUNK_COVERAGE_INCOMPLETE"
    MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
    AMBIGUOUS_COREFERENCE = "AMBIGUOUS_COREFERENCE"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    INVALID_COUNT_INVARIANT = "INVALID_COUNT_INVARIANT"
    AMBIGUOUS_NULL_SEMANTICS = "AMBIGUOUS_NULL_SEMANTICS"
    NON_EXHAUSTIVE_SCENARIO_SET = "NON_EXHAUSTIVE_SCENARIO_SET"
    UNSUPPORTED_DESIGN_PROFILE = "UNSUPPORTED_DESIGN_PROFILE"
    VERIFIER_DISAGREEMENT = "VERIFIER_DISAGREEMENT"
    AUTHORITY_CONFLICT = "AUTHORITY_CONFLICT"
    INTERFERENCE_STATUS_UNKNOWN = "INTERFERENCE_STATUS_UNKNOWN"
    RULE_THEORY_MISMATCH = "RULE_THEORY_MISMATCH"
    PROFILE_COVERAGE_GAP = "PROFILE_COVERAGE_GAP"
    REALITY_GATE_BLOCKED = "REALITY_GATE_BLOCKED"


class StageIssue(FrozenModel):
    code: StageErrorCode
    detail: str
    artifact_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _non_blank_and_unique(self) -> Self:
        if not self.detail.strip():
            raise ValueError("stage issue detail must not be blank")
        if any(not artifact_id.strip() for artifact_id in self.artifact_ids):
            raise ValueError("stage issue artifact_ids must not contain blanks")
        if len(self.artifact_ids) != len(set(self.artifact_ids)):
            raise ValueError("stage issue artifact_ids must be unique")
        return self


class StageProvenance(FrozenModel):
    producer_id: str
    producer_version: str
    input_artifact_ids: tuple[str, ...]
    input_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if not self.producer_id.strip() or not self.producer_version.strip():
            raise ValueError("stage provenance producer id/version must not be blank")
        if not self.input_artifact_ids or any(
            not artifact_id.strip() for artifact_id in self.input_artifact_ids
        ):
            raise ValueError("stage provenance requires non-blank input artifact IDs")
        if len(self.input_artifact_ids) != len(set(self.input_artifact_ids)):
            raise ValueError("stage provenance input artifact IDs must be unique")
        return self


class StageCoverage(FrozenModel):
    status: StageCompletionStatus
    covered_artifact_ids: tuple[str, ...] = ()
    missing_artifact_ids: tuple[str, ...] = ()
    rationale: str

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if not self.rationale.strip():
            raise ValueError("coverage rationale must not be blank")
        all_ids = (*self.covered_artifact_ids, *self.missing_artifact_ids)
        if any(not artifact_id.strip() for artifact_id in all_ids):
            raise ValueError("coverage artifact IDs must not be blank")
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("coverage artifact IDs must be unique")
        if set(self.covered_artifact_ids) & set(self.missing_artifact_ids):
            raise ValueError("coverage artifact cannot be both covered and missing")
        if self.status is StageCompletionStatus.COMPLETE and self.missing_artifact_ids:
            raise ValueError("COMPLETE coverage cannot list missing artifacts")
        if self.status is StageCompletionStatus.COMPLETE and not self.covered_artifact_ids:
            raise ValueError("COMPLETE coverage requires at least one covered artifact")
        if self.status is StageCompletionStatus.PARTIAL and not self.missing_artifact_ids:
            raise ValueError("PARTIAL coverage requires at least one missing artifact")
        if self.status is StageCompletionStatus.FAILED and self.covered_artifact_ids:
            raise ValueError("FAILED coverage cannot claim covered artifacts")
        if self.status is StageCompletionStatus.FAILED and not self.missing_artifact_ids:
            raise ValueError("FAILED coverage requires explicit missing input artifacts")
        return self


ALLOWED_CANDIDATE_COUNT_KINDS: frozenset[str] = frozenset(
    {
        "reported_count_candidate",
        "sample_mention_count_candidate",
        "measurement_mention_count_candidate",
        "row_mention_count_candidate",
        "source_mention_count_candidate",
        "unit_mention_count_candidate",
        "exclusion_mention_count_candidate",
    }
)

LEGACY_V7_CANDIDATE_COUNT_KINDS: frozenset[str] = frozenset(
    {
        "declared_n",
        "observational_n",
        "n_analyzed",
        "biological_source_count",
        "experimental_unit_count_candidate",
        "excluded_n",
        "planned_n",
        "allocated_n",
        "treated_n",
        "observed_n",
    }
)


class EntityCandidate(FrozenModel):
    """Candidate entity mention from Methods/caption text."""

    text: str
    entity_type: str
    start: int | None = None
    end: int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_span_id: str | None = None


class FactorCandidate(FrozenModel):
    factor_id: str
    levels: tuple[str, ...] = ()
    evidence_span_ids: tuple[str, ...] = ()


class CountCandidate(FrozenModel):
    """Deprecated v7 candidate vocabulary, input-only."""

    kind: str
    value: int | None = Field(default=None, ge=0)
    raw_text: str = ""
    evidence_span_id: str | None = None

    @model_validator(mode="after")
    def _candidate_only(self) -> Self:
        if self.kind not in LEGACY_V7_CANDIDATE_COUNT_KINDS and not self.kind.endswith(
            "_candidate"
        ):
            raise ValueError(f"unrecognised legacy candidate count kind: {self.kind!r}")
        return self


class EvidenceCandidate(FrozenModel):
    span_id: str
    text: str
    section: str | None = None
    support_level: str = "INFERRED_CANDIDATE"


class RelationCandidate(FrozenModel):
    relation_id: str
    source_candidate_id: str
    target_candidate_id: str
    relation_type: str
    evidence_span_ids: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class EventCandidate(FrozenModel):
    event_id: str
    event_type: str
    participant_candidate_ids: tuple[str, ...] = ()
    evidence_span_ids: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class GraphCandidate(FrozenModel):
    graph_id: str
    entity_candidate_ids: tuple[str, ...] = ()
    relation_candidate_ids: tuple[str, ...] = ()
    event_candidate_ids: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class AlternativeCandidate(FrozenModel):
    alternative_id: str
    description: str
    candidate_ids: tuple[str, ...] = ()
    evidence_span_ids: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class MissingPredicateCandidate(FrozenModel):
    predicate_name: str
    rationale: str
    evidence_span_ids: tuple[str, ...] = ()


class ParserCandidateBundle(FrozenModel):
    """Candidate-only bundle: hard boundary before human review and rules."""

    stage: str = "mvt_a_candidate"
    source_text_checksum: str = ""
    entities: tuple[EntityCandidate, ...] = ()
    factors: tuple[FactorCandidate, ...] = ()
    counts: tuple[CountCandidate, ...] = ()
    evidence: tuple[EvidenceCandidate, ...] = ()
    relations: tuple[RelationCandidate, ...] = ()
    events: tuple[EventCandidate, ...] = ()
    graphs: tuple[GraphCandidate, ...] = ()
    alternatives: tuple[AlternativeCandidate, ...] = ()
    missing_predicates: tuple[MissingPredicateCandidate, ...] = ()
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_final_fields_in_dump(self) -> Self:
        payload = self.model_dump(mode="json")
        assert_no_final_scientific_fields(payload)
        return self


class MvtAStageOutputV7(FrozenModel):
    """Deprecated v7 input-only stage envelope."""

    stage_id: str
    input_kind: str = "methods_or_caption"
    candidates: ParserCandidateBundle
    verifier_passed: bool | None = None
    verifier_errors: tuple[str, ...] = ()
    model_id: str | None = None  # challenger id only; never "validated"
    model_role: str = "unqualified_challenger"


class MvtAStageOutput(FrozenModel):
    """Versioned v8 partial-success envelope preserving prior valid artifacts."""

    stage_contract_version: Literal["8.0.0"] = "8.0.0"
    stage_id: str
    input_kind: str = "methods_or_caption"
    status: StageCompletionStatus
    candidates: Any | None
    errors: tuple[StageIssue, ...] = ()
    warnings: tuple[StageIssue, ...] = ()
    coverage: StageCoverage
    provenance: StageProvenance
    preserved_artifact_ids: tuple[str, ...] = ()
    verifier_passed: bool | None = None
    verifier_errors: tuple[StageIssue, ...] = ()
    model_id: str | None = None
    model_role: str = "unqualified_challenger"

    @field_validator("candidates", mode="before")
    @classmethod
    def _canonical_active_candidate(cls, value: Any) -> Any:
        if value is None:
            return None
        # Local import breaks the schema dependency cycle while retaining a
        # single active ParserCandidateOutput payload on validation/round-trip.
        from ntruth.parser_ai.contract import canonicalize_parser_candidate_output

        return canonicalize_parser_candidate_output(value)

    def _revalidated_for_serialization(self) -> MvtAStageOutput:
        from ntruth.parser_ai.contract import canonicalize_candidate_boundary_model

        return canonicalize_candidate_boundary_model(
            self,
            model_type=MvtAStageOutput,
            boundary_name="MVT-A stage",
        )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize only after revalidating the complete candidate parent."""

        self._revalidated_for_serialization()
        return BaseModel.model_dump(self, **kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        """Serialize JSON only after revalidating the candidate parent."""

        self._revalidated_for_serialization()
        return BaseModel.model_dump_json(self, **kwargs)

    @model_serializer(mode="wrap")
    def _serialize_after_raw_validation(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> Any:
        """Apply the exact raw gate when serialized inside another model."""

        self._revalidated_for_serialization()
        return handler(self)

    @model_validator(mode="after")
    def _status_matches_diagnostics(self) -> Self:
        if self.status is StageCompletionStatus.COMPLETE and self.errors:
            raise ValueError("COMPLETE stage cannot contain errors")
        if self.status is StageCompletionStatus.FAILED and not self.errors:
            raise ValueError("FAILED stage requires a typed error")
        if self.candidates is None and self.status is not StageCompletionStatus.FAILED:
            raise ValueError("only a FAILED stage may omit candidate artifacts")
        if self.coverage.status is not self.status:
            raise ValueError("stage status and coverage status must match")
        reported_artifacts = set(self.coverage.covered_artifact_ids) | set(
            self.coverage.missing_artifact_ids
        )
        if reported_artifacts != set(self.provenance.input_artifact_ids):
            raise ValueError("stage coverage must exactly reconcile provenance input artifacts")
        if self.verifier_passed is False and self.status is not StageCompletionStatus.FAILED:
            raise ValueError("failed verifier requires FAILED stage status")
        if self.verifier_passed is True and self.verifier_errors:
            raise ValueError("passed verifier cannot retain verifier errors")
        if len(self.preserved_artifact_ids) != len(set(self.preserved_artifact_ids)):
            raise ValueError("preserved artifact IDs must be unique")
        return self


_FIELD_TOKEN = re.compile(r"[^a-z0-9]+")


def _canonical_field_name(value: str) -> str:
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return _FIELD_TOKEN.sub("_", snake.casefold()).strip("_")


def assert_no_final_scientific_fields(payload: Any, path: str = "$") -> None:
    """Recursively reject final scientific fields in parser-facing payloads."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and _canonical_field_name(key) in FORBIDDEN_FINAL_FIELDS:
                raise ValueError(
                    f"parser/stage payload must not contain final field {key!r} at {path}"
                )
            assert_no_final_scientific_fields(value, f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for i, item in enumerate(payload):
            assert_no_final_scientific_fields(item, f"{path}[{i}]")


def normalize_candidate_syntax(payload: Any) -> Any:
    """Canonicalize Unicode containers only; never infer scientific meaning."""

    if isinstance(payload, str):
        return unicodedata.normalize("NFKC", payload)
    if isinstance(payload, dict):
        return {key: normalize_candidate_syntax(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [normalize_candidate_syntax(value) for value in payload]
    if isinstance(payload, tuple):
        return tuple(normalize_candidate_syntax(value) for value in payload)
    return payload
