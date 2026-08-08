"""Adapter sostituibile del parser AI; nessun backend concreto e incluso."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ntruth.mvt_a.stage_schema import (
    MvtAStageOutput,
    StageCompletionStatus,
    StageCoverage,
    StageErrorCode,
    StageIssue,
    StageProvenance,
)
from ntruth.mvt_a.verifier import attach_verifier
from ntruth.parser_ai.contract import (
    ParserAIInput,
    ParserAIOutputV3,
    ParserCandidateOutput,
    validate_candidate_contract_pair,
    validate_contract_pair_v3,
)
from ntruth.schemas.core import content_checksum


@runtime_checkable
class ParserAIAdapter(Protocol):
    """Active v8 backend: candidate-only response."""

    name: str
    version: str

    def parse(self, request: ParserAIInput) -> ParserCandidateOutput: ...


def run_parser_adapter(adapter: ParserAIAdapter, request: ParserAIInput) -> MvtAStageOutput:
    """Return the single versioned v8 stage after hard structural verification."""

    artifact_ids = tuple(
        dict.fromkeys(
            (
                *(document.file_id for document in request.documents),
                *(table.table_id for table in request.tables),
                *(artifact.file_id for artifact in request.statistical_code),
            )
            or ("parser-request",)
        )
    )
    provenance = StageProvenance(
        producer_id=adapter.name,
        producer_version=adapter.version,
        input_artifact_ids=artifact_ids,
        input_checksum=content_checksum(request.model_dump(mode="json")),
    )
    try:
        raw = adapter.parse(request)
        response = (
            raw
            if isinstance(raw, ParserCandidateOutput)
            else ParserCandidateOutput.model_validate(raw)
        )
        response = validate_candidate_contract_pair(request, response)
    except (TypeError, ValueError) as exc:
        issue = StageIssue(
            code=StageErrorCode.VERIFIER_DISAGREEMENT,
            detail=f"parser candidate validation failed: {exc}",
            artifact_ids=artifact_ids,
        )
        return MvtAStageOutput(
            stage_id=f"parser-stage-{provenance.input_checksum[:20]}",
            status=StageCompletionStatus.FAILED,
            candidates=None,
            errors=(issue,),
            coverage=StageCoverage(
                status=StageCompletionStatus.FAILED,
                missing_artifact_ids=artifact_ids,
                rationale="Parser output failed canonical validation; input artifacts are preserved.",
            ),
            provenance=provenance,
            preserved_artifact_ids=artifact_ids,
            verifier_passed=False,
            verifier_errors=(issue,),
            model_id=f"{adapter.name}@{adapter.version}",
        )

    stage_errors: tuple[StageIssue, ...] = ()
    if response.coverage.status is StageCompletionStatus.FAILED:
        stage_errors = (
            StageIssue(
                code=StageErrorCode.MISSING_REQUIRED_EVIDENCE,
                detail="Parser reported FAILED coverage.",
                artifact_ids=response.coverage.missing_artifact_ids,
            ),
        )
    stage = MvtAStageOutput(
        stage_id=f"parser-stage-{content_checksum(response.model_dump(mode='json'))[:20]}",
        status=response.coverage.status,
        candidates=response,
        errors=stage_errors,
        coverage=response.coverage,
        provenance=provenance,
        preserved_artifact_ids=response.coverage.covered_artifact_ids,
        model_id=f"{response.model_metadata.model_name}@{response.model_metadata.model_version}",
    )
    return attach_verifier(stage)


@runtime_checkable
class ParserAIAdapterV3(Protocol):
    """Deprecated, explicitly named PRD-v3 adapter boundary."""

    name: str
    version: str

    def parse(self, request: ParserAIInput) -> ParserAIOutputV3: ...


def run_parser_adapter_v3(adapter: ParserAIAdapterV3, request: ParserAIInput) -> ParserAIOutputV3:
    response = adapter.parse(request)
    if not isinstance(response, ParserAIOutputV3):
        response = ParserAIOutputV3.model_validate(response)
    return validate_contract_pair_v3(request, response)
