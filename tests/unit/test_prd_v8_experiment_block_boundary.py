"""PRD v8 §8.6 Experiment Block boundary semantics."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ntruth.parser_ai.contract import (
    CandidateBlockBoundary,
    ParserCandidateOutput,
)
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.block_boundary import (
    BlockBoundaryChangeKind,
    BlockBoundaryStatus,
    ExperimentBlockBoundaryRecord,
    build_experiment_block_boundary_change,
    verify_experiment_block_boundaries,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import (
    SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
    ConfirmationEvent,
    EpistemicEventLedger,
    EvidenceBasis,
    EvidenceRecord,
    EvidenceTypeV8,
    SourceClassRef,
    SupportDescriptor,
    SupportGrade,
)
from ntruth.training.metrics import score_output


def _basis(*, evidence: tuple[str, ...] = ("EV-BOUNDARY-1",)) -> KnowledgeValue[tuple[str, ...]]:
    return KnowledgeValue[tuple[str, ...]](
        knowledge_state=KnowledgeState.PRESENT,
        value=("distinct_assignment_history", "distinct_source_population"),
        evidence_ids=evidence,
    )


def _record(
    *,
    status: BlockBoundaryStatus = BlockBoundaryStatus.CANDIDATE,
    confirmation_event_ids: tuple[str, ...] = (),
) -> ExperimentBlockBoundaryRecord:
    return ExperimentBlockBoundaryRecord(
        block_id="EB-01",
        boundary_basis=_basis(),
        source_refs=("EV-BOUNDARY-1",),
        status=status,
        rationale="Treatment and endpoint have a distinct allocation history.",
        confirmation_event_ids=confirmation_event_ids,
    )


def _confirmation() -> ConfirmationEvent:
    return ConfirmationEvent(
        event_id="CONF-BOUNDARY-1",
        support=SupportDescriptor(
            source_class=SourceClassRef(
                registry_id="ntruth-source-class-v8.0",
                token="clarification",
            ),
            authority_type=AuthorityType.AUTHOR_CLARIFICATION,
            evidence_basis=EvidenceBasis.CORROBORATED_CONFIRMATION,
            support_grade=SupportGrade(
                vocabulary_id=SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
                token="AUTHOR_CLARIFIED",
            ),
        ),
        evidence_refs=("EV-BOUNDARY-1",),
        scope_id="EB-01",
        confirmed_value=KnowledgeValue[list[str]](
            knowledge_state=KnowledgeState.PRESENT,
            value=["distinct_assignment_history", "distinct_source_population"],
            evidence_ids=("EV-BOUNDARY-1",),
        ),
        actor_role="experiment_owner",
        review_independent=False,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )


def _ledger() -> EpistemicEventLedger:
    return EpistemicEventLedger(
        ledger_id="LEDGER-BOUNDARY-1",
        evidence_records=(
            EvidenceRecord(
                evidence_id="EV-BOUNDARY-1",
                source_id="METHODS-S2",
                evidence_type=EvidenceTypeV8.STRUCTURAL_FACT,
                locator="Methods section 2",
                original_text="Experiment 1 used a distinct treatment allocation.",
            ),
        ),
        confirmation_events=(_confirmation(),),
    )


def _candidate_payload() -> dict[str, object]:
    return {
        "contract_version": "8.0.0",
        "experiment_blocks": [
            {
                "block_id": "EB-01",
                "title": "Experiment 1",
                "evidence_ids": ["EV-BOUNDARY-1"],
                "confidence": 0.8,
            }
        ],
        "block_boundaries": [
            {
                "block_id": "EB-01",
                "boundary_basis_candidates": ["distinct_assignment_history"],
                "rationale": "Explicit Experiment 1 heading and allocation history.",
                "evidence_ids": ["EV-BOUNDARY-1"],
                "confidence": 0.8,
            }
        ],
        "evidence_spans": [
            {
                "evidence_id": "EV-BOUNDARY-1",
                "file_id": "methods",
                "evidence_type": "STRUCTURAL_FACT",
                "text": "Experiment 1",
                "confidence": 0.8,
                "start": 0,
                "end": 12,
            }
        ],
        "coverage": {
            "status": "COMPLETE",
            "covered_artifact_ids": ["methods"],
            "missing_artifact_ids": [],
            "rationale": "The supplied Methods artifact was routed.",
        },
        "model_metadata": {
            "adapter_name": "fixture",
            "model_name": "fixture",
            "model_version": "1",
            "prompt_template_version": "candidate-v8",
            "contract_version": "8.0.0",
            "local_execution": True,
        },
    }


def test_candidate_boundary_is_not_a_confirmed_boundary() -> None:
    record = _record()
    assert record.status is BlockBoundaryStatus.CANDIDATE
    assert record.confirmation_event_ids == ()


def test_confirmed_boundary_requires_exact_confirmation_scope_value_and_evidence() -> None:
    record = _record(
        status=BlockBoundaryStatus.CONFIRMED,
        confirmation_event_ids=("CONF-BOUNDARY-1",),
    )
    assert verify_experiment_block_boundaries((record,), ledger=_ledger()) == (record,)

    wrong_scope = _confirmation().model_copy(update={"scope_id": "EB-OTHER"})
    with pytest.raises(ValueError, match="scope"):
        verify_experiment_block_boundaries(
            (record,),
            ledger=_ledger().model_copy(update={"confirmation_events": (wrong_scope,)}),
        )


def test_confirmed_boundary_cannot_be_self_declared_without_confirmation() -> None:
    with pytest.raises(ValidationError, match="CONFIRMED"):
        _record(status=BlockBoundaryStatus.CONFIRMED)


def test_conflicting_boundary_retains_alternatives_and_cannot_be_confirmed() -> None:
    conflicting = KnowledgeValue[tuple[str, ...]](
        knowledge_state=KnowledgeState.CONFLICTING,
        conflicting_values=(("distinct_assignment_history",), ("shared_assignment_history",)),
        evidence_ids=("EV-BOUNDARY-1", "EV-BOUNDARY-2"),
    )
    record = ExperimentBlockBoundaryRecord(
        block_id="EB-01",
        boundary_basis=conflicting,
        source_refs=("EV-BOUNDARY-1", "EV-BOUNDARY-2"),
        status=BlockBoundaryStatus.CONFLICTING,
        rationale="Methods and sample sheet imply different allocation histories.",
    )
    assert record.boundary_basis.knowledge_state is KnowledgeState.CONFLICTING
    with pytest.raises(ValidationError, match="CONFLICTING"):
        ExperimentBlockBoundaryRecord.model_validate(
            {
                **record.model_dump(mode="json"),
                "confirmation_event_ids": ["CONF-BOUNDARY-1"],
            }
        )


@pytest.mark.parametrize(
    ("kind", "prior", "resulting"),
    [
        (BlockBoundaryChangeKind.SPLIT, ("EB-OLD",), ("EB-01", "EB-02")),
        (BlockBoundaryChangeKind.MERGE, ("EB-01", "EB-02"), ("EB-MERGED",)),
    ],
)
def test_split_and_merge_have_typed_auditable_shapes(
    kind: BlockBoundaryChangeKind,
    prior: tuple[str, ...],
    resulting: tuple[str, ...],
) -> None:
    change = build_experiment_block_boundary_change(
        change_kind=kind,
        prior_block_ids=prior,
        resulting_block_ids=resulting,
        boundary_basis=("distinct_assignment_history",),
        source_refs=("EV-BOUNDARY-1",),
        rationale="Human review changed the block boundary.",
        confirmation_event_ids=("CONF-BOUNDARY-1",),
    )
    assert change.change_kind is kind


def test_parser_requires_exactly_one_candidate_boundary_per_candidate_block() -> None:
    parsed = ParserCandidateOutput.model_validate(_candidate_payload())
    assert parsed.block_boundaries == (
        CandidateBlockBoundary(
            block_id="EB-01",
            boundary_basis_candidates=("distinct_assignment_history",),
            rationale="Explicit Experiment 1 heading and allocation history.",
            evidence_ids=("EV-BOUNDARY-1",),
            confidence=0.8,
        ),
    )

    missing = _candidate_payload()
    missing["block_boundaries"] = []
    with pytest.raises(ValidationError, match="one boundary candidate"):
        ParserCandidateOutput.model_validate(missing)


def test_parser_boundary_cannot_reference_another_or_unknown_block() -> None:
    payload = _candidate_payload()
    payload["block_boundaries"][0]["block_id"] = "EB-UNKNOWN"  # type: ignore[index]
    with pytest.raises(ValidationError, match="boundary candidate"):
        ParserCandidateOutput.model_validate(payload)


def test_boundary_candidates_are_scored_instead_of_ignored() -> None:
    gold = ParserCandidateOutput.model_validate(_candidate_payload())
    changed_payload = _candidate_payload()
    changed_payload["block_boundaries"][0]["boundary_basis_candidates"] = [  # type: ignore[index]
        "distinct_source_population"
    ]
    predicted = ParserCandidateOutput.model_validate(changed_payload)

    score = score_output(predicted, gold)
    assert score["categories"]["block_boundaries"]["false_positive"] == 1
    assert score["categories"]["block_boundaries"]["false_negative"] == 1
    assert score["micro"]["f1"] < 1.0
