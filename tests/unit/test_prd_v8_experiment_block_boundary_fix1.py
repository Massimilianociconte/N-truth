"""Regressions for the PRD v8 Experiment Block boundary review."""

from __future__ import annotations

import pickle
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import ntruth.schemas.block_boundary as boundary
from ntruth.mvt_a.verifier import hard_verify_candidates
from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.schemas.authority import AuthorityType
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


def _restore_unchecked_candidate(
    model_type: type[BaseModel],
    state: dict[str, Any],
    use_custom_setstate: bool,
) -> BaseModel:
    restored = model_type.__new__(model_type)
    custom_setstate = model_type.__dict__.get("__setstate__")
    if use_custom_setstate and custom_setstate is not None:
        custom_setstate(restored, state)
    else:
        BaseModel.__setstate__(restored, state)
    return restored


class _UncheckedCandidatePickle:
    def __init__(self, candidate: ParserCandidateOutput) -> None:
        self.candidate = candidate

    def __reduce__(
        self,
    ) -> tuple[
        object,
        tuple[type[BaseModel], dict[str, Any], bool],
    ]:
        model_type = type(self.candidate)
        custom_getstate = (
            None if model_type is ParserCandidateOutput else model_type.__dict__.get("__getstate__")
        )
        use_custom_state = custom_getstate is not None
        state = (
            custom_getstate(self.candidate)
            if custom_getstate is not None
            else BaseModel.__getstate__(self.candidate)
        )
        return _restore_unchecked_candidate, (model_type, state, use_custom_state)


def _unsafe_candidate_pickle_roundtrip(
    candidate: ParserCandidateOutput,
) -> ParserCandidateOutput:
    restored = pickle.loads(pickle.dumps(_UncheckedCandidatePickle(candidate)))
    assert isinstance(restored, ParserCandidateOutput)
    return restored


def _support() -> SupportDescriptor:
    return SupportDescriptor(
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
    )


def _evidence(evidence_id: str, text: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_id="METHODS-S2",
        evidence_type=EvidenceTypeV8.STRUCTURAL_FACT,
        locator=f"Methods section 2: {evidence_id}",
        original_text=text,
    )


def _confirmation(
    *,
    event_id: str,
    scope_id: str,
    evidence_refs: tuple[str, ...],
    confirmed_evidence_ids: tuple[str, ...],
    value: object,
) -> ConfirmationEvent:
    return ConfirmationEvent(
        event_id=event_id,
        support=_support(),
        evidence_refs=evidence_refs,
        scope_id=scope_id,
        confirmed_value=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=value,
            evidence_ids=confirmed_evidence_ids,
        ),
        actor_role="experiment_owner",
        review_independent=False,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )


def _predicate(
    criterion: boundary.BlockBoundaryCriterion = (
        boundary.BlockBoundaryCriterion.DISTINCT_EXPERIMENT_SOURCE_DOCUMENT
    ),
    representability: boundary.InternalQueryRepresentability = (
        boundary.InternalQueryRepresentability.NOT_REPRESENTABLE
    ),
) -> boundary.BlockBoundaryPredicate:
    return boundary.BlockBoundaryPredicate(
        criterion=criterion,
        internal_query_representability=representability,
    )


def _predicate_payload(
    criterion: str = "DISTINCT_EXPERIMENT_SOURCE_DOCUMENT",
    representability: str = "NOT_REPRESENTABLE",
) -> dict[str, str]:
    return {
        "criterion": criterion,
        "internal_query_representability": representability,
    }


def _parser_payload(
    *,
    blocks: tuple[tuple[str, str], ...] = (("EB-01", "Experiment 1"),),
    evidence_ids: tuple[str, ...] = ("EV-METHODS",),
    predicates: tuple[dict[str, str], ...] | None = None,
) -> dict[str, object]:
    if predicates is None:
        predicates = (_predicate_payload(),)
    return {
        "contract_version": "8.0.0",
        "experiment_blocks": [
            {
                "block_id": block_id,
                "title": title,
                "evidence_ids": list(evidence_ids),
                "confidence": 0.8,
            }
            for block_id, title in blocks
        ],
        "block_boundaries": [
            {
                "block_id": block_id,
                "boundary_predicates": list(predicates),
                "rationale": "Explicit heading and distinct allocation history.",
                "evidence_ids": list(evidence_ids),
                "confidence": 0.8,
            }
            for block_id, _title in blocks
        ],
        "evidence_spans": [
            {
                "evidence_id": "EV-METHODS",
                "file_id": "methods",
                "evidence_type": "STRUCTURAL_FACT",
                "text": "Experiment 1 has a distinct allocation history.",
                "confidence": 0.8,
                "start": 0,
                "end": 48,
            },
            {
                "evidence_id": "EV-FIGURE",
                "file_id": "figure",
                "evidence_type": "STRUCTURAL_FACT",
                "text": "Figure 2.",
                "confidence": 0.8,
                "start": 0,
                "end": 9,
            },
        ],
        "coverage": {
            "status": "COMPLETE",
            "covered_artifact_ids": ["methods", "figure"],
            "missing_artifact_ids": [],
            "rationale": "Both supplied artifacts were routed.",
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


def _epistemic_change_ledger(
    *changes: boundary.ExperimentBlockBoundaryChangeRecord,
) -> EpistemicEventLedger:
    return EpistemicEventLedger(
        ledger_id="LEDGER-CHANGE-CLOSURE",
        evidence_records=(
            _evidence("EV-1", "The allocation ledger resolves the boundary history."),
        ),
        confirmation_events=tuple(
            _confirmation(
                event_id=change.confirmation_event_ids[0],
                scope_id=change.change_id,
                evidence_refs=change.source_refs,
                confirmed_evidence_ids=change.source_refs,
                value=boundary.experiment_block_boundary_change_confirmation_value(change),
            )
            for change in changes
        ),
    )


def test_candidate_metrics_are_local_id_invariant_but_evidence_binding_sensitive() -> None:
    gold_payload = _parser_payload()
    gold = ParserCandidateOutput.model_validate(gold_payload)

    renamed_payload = _parser_payload(blocks=(("LOCAL-PREDICTED-ID", "Experiment 1"),))
    renamed_payload["evidence_spans"][0]["evidence_id"] = "LOCAL-EVIDENCE-ID"  # type: ignore[index]
    renamed_payload["experiment_blocks"][0]["evidence_ids"] = [  # type: ignore[index]
        "LOCAL-EVIDENCE-ID"
    ]
    renamed_payload["block_boundaries"][0]["evidence_ids"] = [  # type: ignore[index]
        "LOCAL-EVIDENCE-ID"
    ]
    renamed = ParserCandidateOutput.model_validate(renamed_payload)
    assert score_output(renamed, gold)["micro"]["f1"] == 1.0

    rebound_payload = _parser_payload(evidence_ids=("EV-FIGURE",))
    rebound = ParserCandidateOutput.model_validate(rebound_payload)
    rebound_score = score_output(rebound, gold)
    assert rebound_score["categories"]["block_boundaries"]["false_positive"] == 1
    assert rebound_score["categories"]["block_boundaries"]["false_negative"] == 1
    assert rebound_score["micro"]["f1"] < 1.0


@pytest.mark.parametrize(("predicted_count", "gold_count"), ((2, 1), (1, 2)))
def test_candidate_metrics_count_semantic_duplicates_and_omissions(
    predicted_count: int,
    gold_count: int,
) -> None:
    duplicate_blocks = (("EB-01", "Experiment 1"), ("EB-02", "Experiment 1"))
    predicted = ParserCandidateOutput.model_validate(
        _parser_payload(blocks=duplicate_blocks[:predicted_count])
    )
    gold = ParserCandidateOutput.model_validate(
        _parser_payload(blocks=duplicate_blocks[:gold_count])
    )

    score = score_output(predicted, gold)
    assert score["categories"]["experiment_blocks"]["f1"] < 1.0
    assert score["categories"]["block_boundaries"]["f1"] < 1.0
    assert score["micro"]["f1"] < 1.0


def test_confirmed_boundary_requires_exact_unique_confirmed_value_evidence() -> None:
    record = boundary.ExperimentBlockBoundaryRecord(
        block_id="EB-01",
        boundary_basis=KnowledgeValue[tuple[boundary.BlockBoundaryPredicate, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=(_predicate(),),
            evidence_ids=("EV-1", "EV-2"),
        ),
        source_refs=("EV-1", "EV-2"),
        status=boundary.BlockBoundaryStatus.CONFIRMED,
        rationale="The allocation history is distinct.",
        confirmation_event_ids=("CONF-1",),
    )
    event = _confirmation(
        event_id="CONF-1",
        scope_id="EB-01",
        evidence_refs=("EV-1", "EV-2"),
        confirmed_evidence_ids=("EV-1",),
        value=[_predicate().model_dump(mode="json")],
    )
    ledger = EpistemicEventLedger(
        ledger_id="LEDGER-1",
        evidence_records=(
            _evidence("EV-1", "The treatment was assigned after splitting."),
            _evidence("EV-2", "The allocation table records the split."),
        ),
        confirmation_events=(event,),
    )

    with pytest.raises(ValueError, match=r"confirmed_value evidence|exact"):
        boundary.verify_experiment_block_boundaries((record,), ledger=ledger)

    with pytest.raises(ValidationError, match="unique"):
        boundary.ExperimentBlockBoundaryRecord(
            block_id="EB-01",
            boundary_basis=KnowledgeValue[tuple[boundary.BlockBoundaryPredicate, ...]](
                knowledge_state=KnowledgeState.PRESENT,
                value=(_predicate(),),
                evidence_ids=("EV-1", "EV-1"),
            ),
            source_refs=("EV-1",),
            status=boundary.BlockBoundaryStatus.CANDIDATE,
            rationale="Retained candidate with malformed duplicated evidence.",
        )


def test_unknown_or_unstructured_basis_never_promotes_a_boundary() -> None:
    candidate = ParserCandidateOutput.model_validate(
        _parser_payload(
            predicates=(
                _predicate_payload(
                    representability="UNKNOWN",
                ),
            )
        )
    )
    result = hard_verify_candidates(candidate)
    assert result.passed is True
    assert "experiment_block_boundaries" in result.checks_run

    with pytest.raises(ValidationError, match=r"not representable|CONFIRMED"):
        boundary.ExperimentBlockBoundaryRecord(
            block_id="EB-01",
            boundary_basis=KnowledgeValue[tuple[boundary.BlockBoundaryPredicate, ...]](
                knowledge_state=KnowledgeState.PRESENT,
                value=(
                    _predicate(representability=boundary.InternalQueryRepresentability.UNKNOWN),
                ),
                evidence_ids=("EV-1",),
            ),
            source_refs=("EV-1",),
            status=boundary.BlockBoundaryStatus.CONFIRMED,
            rationale="Only the figure changed.",
            confirmation_event_ids=("CONF-1",),
        )

    with pytest.raises(ValueError, match="not representable"):
        boundary.build_experiment_block_boundary_change(
            change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
            prior_block_ids=("EB-OLD",),
            resulting_block_ids=("EB-01", "EB-02"),
            boundary_basis=(
                _predicate(representability=boundary.InternalQueryRepresentability.UNKNOWN),
            ),
            source_refs=("EV-1",),
            rationale="Figure or panel changed; retained only as a non-decisive note.",
            confirmation_event_ids=("CONF-1",),
        )

    invalid_other = _parser_payload(predicates=(_predicate_payload(criterion="OTHER"),))
    with pytest.raises(ValidationError, match="criterion"):
        ParserCandidateOutput.model_validate(invalid_other)


def test_free_text_boundary_synonym_cannot_be_a_decisive_predicate() -> None:
    payload = _parser_payload()
    candidate = payload["block_boundaries"][0]  # type: ignore[index]
    candidate.pop("boundary_predicates")
    candidate["boundary_basis_candidates"] = ["figure_or_panel_changed_only"]
    with pytest.raises(ValidationError, match=r"structured|predicate|boundary"):
        ParserCandidateOutput.model_validate(payload)


def test_boundary_basis_uses_the_closed_prd_section_6_6_predicate_vocabulary() -> None:
    criterion_type = getattr(boundary, "BlockBoundaryCriterion", None)
    representability_type = getattr(boundary, "InternalQueryRepresentability", None)
    predicate_type = getattr(boundary, "BlockBoundaryPredicate", None)
    assert criterion_type is not None, "closed PRD boundary criterion vocabulary is missing"
    assert representability_type is not None, "query representability vocabulary is missing"
    assert predicate_type is not None, "structured boundary predicate is missing"

    predicate = predicate_type(
        criterion=criterion_type.INCOMPATIBLE_TIMELINE,
        internal_query_representability=representability_type.NOT_REPRESENTABLE,
    )
    assert predicate.criterion is criterion_type.INCOMPATIBLE_TIMELINE
    assert predicate.internal_query_representability is representability_type.NOT_REPRESENTABLE


def test_boundary_criterion_cannot_have_contradictory_representability_states() -> None:
    contradictory = (
        _predicate_payload(representability="UNKNOWN"),
        _predicate_payload(representability="NOT_REPRESENTABLE"),
    )
    with pytest.raises(ValidationError, match=r"criterion|duplicate|contradictory"):
        ParserCandidateOutput.model_validate(_parser_payload(predicates=contradictory))

    predicates = (
        _predicate(representability=boundary.InternalQueryRepresentability.UNKNOWN),
        _predicate(representability=boundary.InternalQueryRepresentability.NOT_REPRESENTABLE),
    )
    with pytest.raises(ValidationError, match=r"criterion|duplicate|contradictory"):
        boundary.ExperimentBlockBoundaryRecord(
            block_id="EB-01",
            boundary_basis=KnowledgeValue[tuple[boundary.BlockBoundaryPredicate, ...]](
                knowledge_state=KnowledgeState.PRESENT,
                value=predicates,
                evidence_ids=("EV-1",),
            ),
            source_refs=("EV-1",),
            status=boundary.BlockBoundaryStatus.CONFIRMED,
            rationale="The note is non-decisive.",
            confirmation_event_ids=("CONF-1",),
        )
    with pytest.raises((ValueError, ValidationError), match=r"criterion|duplicate|contradictory"):
        boundary.build_experiment_block_boundary_change(
            change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
            prior_block_ids=("EB-OLD",),
            resulting_block_ids=("EB-01", "EB-02"),
            boundary_basis=predicates,
            source_refs=("EV-1",),
            rationale="The note is non-decisive.",
            confirmation_event_ids=("CONF-1",),
        )


def test_hard_verifier_rechecks_structured_boundary_criterion_uniqueness() -> None:
    valid = ParserCandidateOutput.model_validate(_parser_payload())
    forged_boundary = valid.block_boundaries[0].model_copy(
        update={
            "boundary_predicates": (
                _predicate(representability=boundary.InternalQueryRepresentability.UNKNOWN),
                _predicate(
                    representability=(boundary.InternalQueryRepresentability.NOT_REPRESENTABLE)
                ),
            )
        }
    )
    forged = valid.model_copy(update={"block_boundaries": (forged_boundary,)})

    result = hard_verify_candidates(forged)
    assert result.passed is False
    assert any("criterion" in error.detail for error in result.errors)


@pytest.mark.parametrize(
    ("field", "forged_value"),
    (
        ("criterion", "OTHER"),
        ("criterion", "figure_or_panel_changed_only"),
        ("internal_query_representability", "OTHER"),
    ),
)
def test_hard_verifier_revalidates_forged_nested_boundary_predicates(
    field: str,
    forged_value: str,
) -> None:
    valid = ParserCandidateOutput.model_validate(_parser_payload())
    forged_predicate = (
        valid.block_boundaries[0].boundary_predicates[0].model_copy(update={field: forged_value})
    )
    forged_boundary = valid.block_boundaries[0].model_copy(
        update={"boundary_predicates": (forged_predicate,)}
    )
    forged = valid.model_copy(update={"block_boundaries": (forged_boundary,)})

    result = hard_verify_candidates(forged)
    assert result.passed is False
    assert any(
        "boundary_predicates" in error.detail
        or "criterion" in error.detail
        or "internal_query_representability" in error.detail
        for error in result.errors
    )


@pytest.mark.parametrize("forgery", ("unknown", "duplicate"))
def test_boundary_verifier_revalidates_forged_confirmed_records(forgery: str) -> None:
    valid = boundary.ExperimentBlockBoundaryRecord(
        block_id="EB-01",
        boundary_basis=KnowledgeValue[tuple[boundary.BlockBoundaryPredicate, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=(_predicate(),),
            evidence_ids=("EV-1",),
        ),
        source_refs=("EV-1",),
        status=boundary.BlockBoundaryStatus.CONFIRMED,
        rationale="The source document explicitly describes a distinct experiment.",
        confirmation_event_ids=("CONF-1",),
    )
    if forgery == "unknown":
        forged_predicates = (
            _predicate(representability=boundary.InternalQueryRepresentability.UNKNOWN),
        )
    else:
        forged_predicates = (_predicate(), _predicate())
    forged_basis = valid.boundary_basis.model_copy(update={"value": forged_predicates})
    forged = valid.model_copy(update={"boundary_basis": forged_basis})
    epistemic = EpistemicEventLedger(
        ledger_id="LEDGER-FORGED-RECORD",
        evidence_records=(_evidence("EV-1", "The source describes the experiment."),),
        confirmation_events=(
            _confirmation(
                event_id="CONF-1",
                scope_id="EB-01",
                evidence_refs=("EV-1",),
                confirmed_evidence_ids=("EV-1",),
                value=[predicate.model_dump(mode="json") for predicate in forged_predicates],
            ),
        ),
    )

    with pytest.raises((ValueError, ValidationError), match=r"CONFIRMED|criterion|duplicate"):
        boundary.verify_experiment_block_boundaries((forged,), ledger=epistemic)


def test_boundary_rationale_is_a_non_decisive_metric_note() -> None:
    gold = ParserCandidateOutput.model_validate(_parser_payload())
    predicted_payload = _parser_payload()
    predicted_payload["block_boundaries"][0]["rationale"] = (  # type: ignore[index]
        "A differently worded descriptive note with the same structured predicates."
    )
    predicted = ParserCandidateOutput.model_validate(predicted_payload)

    score = score_output(predicted, gold)
    assert score["categories"]["block_boundaries"]["f1"] == 1.0
    assert score["micro"]["f1"] == 1.0
    assert score["exact_contract_match"] is False


def test_split_merge_ledger_is_append_only_content_addressed_and_version_chained() -> None:
    build_change = getattr(boundary, "build_experiment_block_boundary_change", None)
    build_ledger = getattr(boundary, "build_experiment_block_boundary_change_ledger", None)
    append_ledger = getattr(boundary, "append_experiment_block_boundary_change_ledger", None)
    verify_ledger = getattr(boundary, "verify_experiment_block_boundary_change_ledger", None)
    assert callable(build_change), "content-addressed boundary change builder is missing"
    assert callable(build_ledger), "content-addressed boundary change ledger builder is missing"
    assert callable(append_ledger), "append-only boundary ledger operation is missing"
    assert callable(verify_ledger), "boundary change confirmation resolver is missing"

    split = build_change(
        change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
        prior_block_ids=("EB-OLD",),
        resulting_block_ids=("EB-01", "EB-02"),
        boundary_basis=(_predicate(),),
        source_refs=("EV-1",),
        rationale="Review resolved two distinct allocation histories.",
        confirmation_event_ids=("CONF-SPLIT",),
    )
    initial = build_ledger(changes=(split,))
    merge = build_change(
        change_kind=boundary.BlockBoundaryChangeKind.MERGE,
        prior_block_ids=("EB-01", "EB-02"),
        resulting_block_ids=("EB-MERGED",),
        boundary_basis=(
            _predicate(
                boundary.BlockBoundaryCriterion.DISTINCT_EXPERIMENT_SOURCE_DOCUMENT,
                boundary.InternalQueryRepresentability.REPRESENTABLE,
            ),
        ),
        source_refs=("EV-1",),
        rationale="Later evidence established one shared allocation history.",
        confirmation_event_ids=("CONF-MERGE",),
        previous=split,
    )
    appended = append_ledger(initial, merge)

    assert appended.changes[: len(initial.changes)] == initial.changes
    assert split.sequence == 1
    assert merge.sequence == 2
    assert merge.parent_change.value is not None
    assert merge.parent_change.value.change_id == split.change_id
    assert merge.parent_change.value.sha256 == split.record_checksum
    assert appended.ledger_id != initial.ledger_id
    assert appended.content_checksum != initial.content_checksum

    split_value = {
        "change_kind": "SPLIT",
        "prior_block_ids": ["EB-OLD"],
        "resulting_block_ids": ["EB-01", "EB-02"],
        "boundary_basis": [_predicate().model_dump(mode="json")],
    }
    merge_value = {
        "change_kind": "MERGE",
        "prior_block_ids": ["EB-01", "EB-02"],
        "resulting_block_ids": ["EB-MERGED"],
        "boundary_basis": [
            _predicate(
                boundary.BlockBoundaryCriterion.DISTINCT_EXPERIMENT_SOURCE_DOCUMENT,
                boundary.InternalQueryRepresentability.REPRESENTABLE,
            ).model_dump(mode="json")
        ],
    }
    epistemic = EpistemicEventLedger(
        ledger_id="LEDGER-CHANGES",
        evidence_records=(_evidence("EV-1", "The allocation ledger resolves the boundary."),),
        confirmation_events=(
            _confirmation(
                event_id="CONF-SPLIT",
                scope_id=split.change_id,
                evidence_refs=("EV-1",),
                confirmed_evidence_ids=("EV-1",),
                value=split_value,
            ),
            _confirmation(
                event_id="CONF-MERGE",
                scope_id=merge.change_id,
                evidence_refs=("EV-1",),
                confirmed_evidence_ids=("EV-1",),
                value=merge_value,
            ),
        ),
    )
    assert verify_ledger(appended, ledger=epistemic) == appended

    forged_ledger = appended.model_copy(update={"content_checksum": "0" * 64})
    with pytest.raises((ValueError, ValidationError), match="ledger checksum"):
        verify_ledger(forged_ledger, ledger=epistemic)

    tampered = merge.model_dump(mode="json")
    tampered["resulting_block_ids"] = ["EB-FORGED"]
    with pytest.raises(ValidationError, match="checksum"):
        type(merge).model_validate(tampered)
    with pytest.raises((ValueError, ValidationError), match=r"initial|sequence|parent"):
        build_ledger(changes=(merge,))


def test_change_ledger_rejects_an_orphan_merge() -> None:
    merge = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.MERGE,
        prior_block_ids=("EB-01", "EB-02"),
        resulting_block_ids=("EB-MERGED",),
        boundary_basis=(
            _predicate(representability=boundary.InternalQueryRepresentability.REPRESENTABLE),
        ),
        source_refs=("EV-1",),
        rationale="No prior split is present in this chain.",
        confirmation_event_ids=("CONF-MERGE",),
    )
    change_ledger = boundary.build_experiment_block_boundary_change_ledger(changes=(merge,))

    with pytest.raises(ValueError, match=r"MERGE|prior SPLIT|orphan"):
        boundary.verify_experiment_block_boundary_change_ledger(
            change_ledger,
            ledger=_epistemic_change_ledger(merge),
        )


@pytest.mark.parametrize(
    "merge_criteria",
    (
        (boundary.BlockBoundaryCriterion.DISTINCT_EXPERIMENT_SOURCE_DOCUMENT,),
        (
            boundary.BlockBoundaryCriterion.DISTINCT_EXPERIMENT_SOURCE_DOCUMENT,
            boundary.BlockBoundaryCriterion.INCOMPATIBLE_TIMELINE,
            boundary.BlockBoundaryCriterion.UNSHAREABLE_CONTRAST_OR_GROUP,
        ),
    ),
    ids=("missing", "extraneous"),
)
def test_change_ledger_requires_exact_merge_criterion_closure(
    merge_criteria: tuple[boundary.BlockBoundaryCriterion, ...],
) -> None:
    split = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
        prior_block_ids=("EB-OLD",),
        resulting_block_ids=("EB-01", "EB-02"),
        boundary_basis=(
            _predicate(),
            _predicate(boundary.BlockBoundaryCriterion.INCOMPATIBLE_TIMELINE),
        ),
        source_refs=("EV-1",),
        rationale="Two decisive criteria required the split.",
        confirmation_event_ids=("CONF-SPLIT",),
    )
    merge = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.MERGE,
        prior_block_ids=("EB-01", "EB-02"),
        resulting_block_ids=("EB-MERGED",),
        boundary_basis=tuple(
            _predicate(criterion, boundary.InternalQueryRepresentability.REPRESENTABLE)
            for criterion in merge_criteria
        ),
        source_refs=("EV-1",),
        rationale="The merge must close exactly the split predicates.",
        confirmation_event_ids=("CONF-MERGE",),
        previous=split,
    )
    change_ledger = boundary.build_experiment_block_boundary_change_ledger(changes=(split, merge))

    with pytest.raises(ValueError, match=r"MERGE|criterion|criteria|closure"):
        boundary.verify_experiment_block_boundary_change_ledger(
            change_ledger,
            ledger=_epistemic_change_ledger(split, merge),
        )


def test_change_ledger_requires_merge_prior_ids_to_match_one_prior_split() -> None:
    split = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
        prior_block_ids=("EB-OLD",),
        resulting_block_ids=("EB-01", "EB-02"),
        boundary_basis=(_predicate(),),
        source_refs=("EV-1",),
        rationale="The source establishes two blocks.",
        confirmation_event_ids=("CONF-SPLIT",),
    )
    merge = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.MERGE,
        prior_block_ids=("EB-01", "EB-03"),
        resulting_block_ids=("EB-MERGED",),
        boundary_basis=(
            _predicate(representability=boundary.InternalQueryRepresentability.REPRESENTABLE),
        ),
        source_refs=("EV-1",),
        rationale="One prior block was never produced by the split.",
        confirmation_event_ids=("CONF-MERGE",),
        previous=split,
    )
    change_ledger = boundary.build_experiment_block_boundary_change_ledger(changes=(split, merge))

    with pytest.raises(ValueError, match=r"MERGE|prior SPLIT|prior block"):
        boundary.verify_experiment_block_boundary_change_ledger(
            change_ledger,
            ledger=_epistemic_change_ledger(split, merge),
        )


def test_change_ledger_rejects_ambiguous_prior_split_mapping() -> None:
    first = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
        prior_block_ids=("EB-OLD-1",),
        resulting_block_ids=("EB-01", "EB-02"),
        boundary_basis=(_predicate(),),
        source_refs=("EV-1",),
        rationale="First split declaration.",
        confirmation_event_ids=("CONF-SPLIT-1",),
    )
    second = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
        prior_block_ids=("EB-OLD-2",),
        resulting_block_ids=("EB-01", "EB-02"),
        boundary_basis=(_predicate(),),
        source_refs=("EV-1",),
        rationale="Conflicting second split declaration.",
        confirmation_event_ids=("CONF-SPLIT-2",),
        previous=first,
    )
    merge = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.MERGE,
        prior_block_ids=("EB-01", "EB-02"),
        resulting_block_ids=("EB-MERGED",),
        boundary_basis=(
            _predicate(representability=boundary.InternalQueryRepresentability.REPRESENTABLE),
        ),
        source_refs=("EV-1",),
        rationale="The source cannot identify which split is being closed.",
        confirmation_event_ids=("CONF-MERGE",),
        previous=second,
    )
    change_ledger = boundary.build_experiment_block_boundary_change_ledger(
        changes=(first, second, merge)
    )

    with pytest.raises(ValueError, match=r"MERGE|ambiguous|prior SPLIT"):
        boundary.verify_experiment_block_boundary_change_ledger(
            change_ledger,
            ledger=_epistemic_change_ledger(first, second, merge),
        )


def test_change_ledger_resolves_exact_source_and_confirmation_evidence() -> None:
    build_change = getattr(boundary, "build_experiment_block_boundary_change", None)
    build_ledger = getattr(boundary, "build_experiment_block_boundary_change_ledger", None)
    verify_ledger = getattr(boundary, "verify_experiment_block_boundary_change_ledger", None)
    assert callable(build_change)
    assert callable(build_ledger)
    assert callable(verify_ledger)

    change = build_change(
        change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
        prior_block_ids=("EB-OLD",),
        resulting_block_ids=("EB-01", "EB-02"),
        boundary_basis=(_predicate(),),
        source_refs=("EV-1", "EV-2"),
        rationale="Two allocation histories are explicitly documented.",
        confirmation_event_ids=("CONF-SPLIT",),
    )
    change_ledger = build_ledger(changes=(change,))
    incomplete_confirmation = _confirmation(
        event_id="CONF-SPLIT",
        scope_id=change.change_id,
        evidence_refs=("EV-1", "EV-2"),
        confirmed_evidence_ids=("EV-1",),
        value={
            "change_kind": "SPLIT",
            "prior_block_ids": ["EB-OLD"],
            "resulting_block_ids": ["EB-01", "EB-02"],
            "boundary_basis": [_predicate().model_dump(mode="json")],
        },
    )
    epistemic = EpistemicEventLedger(
        ledger_id="LEDGER-INCOMPLETE",
        evidence_records=(
            _evidence("EV-1", "The Methods name two histories."),
            _evidence("EV-2", "The allocation table corroborates them."),
        ),
        confirmation_events=(incomplete_confirmation,),
    )
    with pytest.raises(ValueError, match=r"confirmed_value evidence|exact"):
        verify_ledger(change_ledger, ledger=epistemic)
