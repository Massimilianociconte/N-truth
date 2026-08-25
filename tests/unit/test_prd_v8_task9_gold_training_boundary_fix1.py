from __future__ import annotations

import json
import pickle
from collections.abc import Callable
from math import isnan
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel

from ntruth.governance.lineage import CorpusSplit
from ntruth.mvt_a.stage_schema import (
    MvtAStageOutput,
    StageCompletionStatus,
    StageCoverage,
)
from ntruth.parser_ai.contract import (
    GoldParserTarget,
    ParserAIInput,
    ParserCandidateOutput,
    ParserModelMetadata,
    validate_candidate_contract_pair,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.mlx_runtime import MLXPipelineError
from ntruth.training.preparation import prepare_dataset
from ntruth.training.records import (
    AnnotationStatus,
    PreparedDataset,
    PreparedRecord,
    SupervisedRecord,
    SupervisionProvenance,
    dumps_prepared_jsonl,
)


class _CandidateSubclass(ParserCandidateOutput):
    pass


class _MetadataSubclass(ParserModelMetadata):
    pass


class _ControlFlowSignal(BaseException):
    pass


class _ExplodingCandidate(ParserCandidateOutput):
    failure: ClassVar[BaseException | None] = None

    def __getattribute__(self, name: str) -> Any:
        if name == "__dict__" and type(self).failure is not None:
            raise type(self).failure
        return super().__getattribute__(name)


def _candidate() -> ParserCandidateOutput:
    return ParserCandidateOutput(
        coverage=StageCoverage(
            status=StageCompletionStatus.COMPLETE,
            covered_artifact_ids=("source-1",),
            rationale="The complete source was inspected.",
        ),
        model_metadata=ParserModelMetadata(
            adapter_name="gold-boundary-fixture",
            model_name="candidate-parser",
            model_version="1",
            prompt_template_version="candidate-v8",
        ),
    )


def _gold_payload(candidate: ParserCandidateOutput) -> dict[str, object]:
    return {
        "candidate_target": candidate,
        "adjudication_id": "adjudication-1",
        "reviewer_ids": ("reviewer-a", "reviewer-b"),
        "adjudication_rationale": "Two independent submissions were reconciled.",
        "submission_references": (
            {
                "submission_id": "submission-a",
                "submission_sha256": "a" * 64,
                "reviewer_id": "reviewer-a",
                "reviewer_role": "wet-lab",
            },
            {
                "submission_id": "submission-b",
                "submission_sha256": "b" * 64,
                "reviewer_id": "reviewer-b",
                "reviewer_role": "statistical-methods",
            },
        ),
        "comparison_status": "AGREED",
        "material_differences": (),
    }


def _gold(candidate: ParserCandidateOutput) -> GoldParserTarget:
    return GoldParserTarget.model_validate(_gold_payload(candidate))


def _provenance() -> SupervisionProvenance:
    return SupervisionProvenance(
        source_id="source-1",
        source_asset_id="asset-1",
        source_sha256="c" * 64,
        governance_hash="d" * 64,
        guideline_version="8.0.0",
    )


def _record(gold: GoldParserTarget) -> SupervisedRecord:
    return SupervisedRecord(
        record_id="record-1",
        task="parser_candidate_v8",
        language="en",
        input_text=ParserAIInput().model_dump_json(),
        target=gold,
        provenance=_provenance(),
    )


def _training_record(gold: GoldParserTarget) -> SupervisedRecord:
    return SupervisedRecord(
        record_id="training-record-1",
        task="parser_candidate_v8",
        language="en",
        input_text=ParserAIInput().model_dump_json(),
        target=gold,
        provenance=SupervisionProvenance(
            source_id="training-source-1",
            source_asset_id="training-asset-1",
            source_sha256="f" * 64,
            governance_hash="0" * 64,
            license_or_authorization_id="training-authorization-1",
            guideline_version="8.0.0",
            reviewer_count=2,
            reviewer_ids=gold.reviewer_ids,
            reviewer_roles=tuple(
                reference.reviewer_role for reference in gold.submission_references
            ),
            adjudication_id=gold.adjudication_id,
        ),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=True,
        split=CorpusSplit.TRAIN,
    )


def _stage_payload(candidate: ParserCandidateOutput) -> dict[str, object]:
    return {
        "stage_id": "stage-1",
        "status": StageCompletionStatus.COMPLETE,
        "candidates": candidate,
        "coverage": {
            "status": StageCompletionStatus.COMPLETE,
            "covered_artifact_ids": ("source-1",),
            "rationale": "The complete source was inspected.",
        },
        "provenance": {
            "producer_id": "gold-boundary-fixture",
            "producer_version": "1",
            "input_artifact_ids": ("source-1",),
            "input_checksum": "e" * 64,
        },
    }


def _hidden_final(candidate: ParserCandidateOutput) -> ParserCandidateOutput:
    forged = candidate.model_copy()
    forged.__dict__["determinability"] = "DETERMINATE"
    return forged


def _undeclared_nested_extra(candidate: ParserCandidateOutput) -> ParserCandidateOutput:
    metadata = candidate.model_metadata.model_copy()
    metadata.__dict__["opaque_candidate_state"] = "must not be stripped"
    return candidate.model_copy(update={"model_metadata": metadata})


def _root_subclass(candidate: ParserCandidateOutput) -> ParserCandidateOutput:
    return _CandidateSubclass.model_validate(candidate.model_dump(mode="python", round_trip=True))


def _nested_subclass(candidate: ParserCandidateOutput) -> ParserCandidateOutput:
    metadata = _MetadataSubclass.model_validate(
        candidate.model_metadata.model_dump(mode="python", round_trip=True)
    )
    return candidate.model_copy(update={"model_metadata": metadata})


def _model_construct_with_hidden_final(
    candidate: ParserCandidateOutput,
) -> ParserCandidateOutput:
    forged = ParserCandidateOutput.model_construct(**candidate.__dict__)
    forged.__dict__["determinability"] = "DETERMINATE"
    return forged


def _underscored_hidden_state(candidate: ParserCandidateOutput) -> ParserCandidateOutput:
    forged = candidate.model_copy()
    forged.__dict__["_determinability"] = "DETERMINATE"
    return forged


def _pydantic_private_hidden_state(candidate: ParserCandidateOutput) -> ParserCandidateOutput:
    forged = candidate.model_copy()
    object.__setattr__(
        forged,
        "__pydantic_private__",
        {"_determinability": "DETERMINATE"},
    )
    return forged


_FORGERIES: tuple[tuple[str, Callable[[ParserCandidateOutput], ParserCandidateOutput]], ...] = (
    ("hidden-final", _hidden_final),
    ("undeclared-nested-extra", _undeclared_nested_extra),
    ("root-subclass", _root_subclass),
    ("nested-subclass", _nested_subclass),
    ("model-construct-hidden-final", _model_construct_with_hidden_final),
    ("underscored-hidden-state", _underscored_hidden_state),
    ("pydantic-private-hidden-state", _pydantic_private_hidden_state),
)


@pytest.mark.parametrize("construction", ("constructor", "model_validate"))
@pytest.mark.parametrize(("_case", "forge"), _FORGERIES, ids=[case for case, _ in _FORGERIES])
def test_gold_target_rejects_noncanonical_candidate_instances(
    construction: str,
    _case: str,
    forge: Callable[[ParserCandidateOutput], ParserCandidateOutput],
) -> None:
    """Catches GoldParserTarget treating a nested candidate model as opaque."""

    payload = _gold_payload(forge(_candidate()))

    with pytest.raises(ValueError, match=r"final field|canonical|runtime|undeclared"):
        if construction == "constructor":
            GoldParserTarget(**payload)  # type: ignore[arg-type]
        else:
            GoldParserTarget.model_validate(payload)


@pytest.mark.parametrize(("_case", "forge"), _FORGERIES, ids=[case for case, _ in _FORGERIES])
def test_supervised_record_rejects_noncanonical_candidate_inside_existing_gold(
    _case: str,
    forge: Callable[[ParserCandidateOutput], ParserCandidateOutput],
) -> None:
    """Catches the training boundary accepting an already-built opaque gold model."""

    canonical_candidate = _candidate()
    forged_gold = _gold(canonical_candidate).model_copy(
        update={"candidate_target": forge(canonical_candidate)}
    )

    with pytest.raises(ValueError, match=r"final field|canonical|runtime|undeclared"):
        SupervisedRecord(
            record_id="record-1",
            task="parser_candidate_v8",
            language="en",
            input_text=ParserAIInput().model_dump_json(),
            target=forged_gold,
            provenance=_provenance(),
        )


@pytest.mark.parametrize("construction", ("constructor", "model_validate"))
@pytest.mark.parametrize(("_case", "forge"), _FORGERIES, ids=[case for case, _ in _FORGERIES])
def test_mvt_a_stage_rejects_noncanonical_existing_candidate(
    construction: str,
    _case: str,
    forge: Callable[[ParserCandidateOutput], ParserCandidateOutput],
) -> None:
    """Catches the MVT-A envelope passing an existing candidate instance through."""

    payload = _stage_payload(forge(_candidate()))

    with pytest.raises(ValueError, match=r"final field|canonical|runtime|undeclared"):
        if construction == "constructor":
            MvtAStageOutput(**payload)  # type: ignore[arg-type]
        else:
            MvtAStageOutput.model_validate(payload)


@pytest.mark.parametrize(("_case", "forge"), _FORGERIES, ids=[case for case, _ in _FORGERIES])
def test_coordinate_pair_rejects_noncanonical_existing_candidate(
    _case: str,
    forge: Callable[[ParserCandidateOutput], ParserCandidateOutput],
) -> None:
    """Catches coordinate validation dumping hidden state then returning the original."""

    with pytest.raises(ValueError, match=r"final field|canonical|runtime|undeclared"):
        validate_candidate_contract_pair(ParserAIInput(), forge(_candidate()))


def test_candidate_consumers_return_fresh_exact_canonical_objects() -> None:
    """Catches reintroducing any exact-instance or isinstance passthrough."""

    candidate = _candidate()
    gold = _gold(candidate)
    stage = MvtAStageOutput.model_validate(_stage_payload(candidate))
    coordinate_checked = validate_candidate_contract_pair(ParserAIInput(), candidate)

    assert type(gold.candidate_target) is ParserCandidateOutput
    assert type(stage.candidates) is ParserCandidateOutput
    assert type(coordinate_checked) is ParserCandidateOutput
    assert gold.candidate_target is not candidate
    assert stage.candidates is not candidate
    assert coordinate_checked is not candidate


@pytest.mark.parametrize(
    "state_kind",
    ("underscored-key", "private-empty", "private-hidden-value"),
)
def test_candidate_direct_gate_rejects_undeclared_private_runtime_state(
    state_kind: str,
) -> None:
    """Catches private or underscored state being treated as safely opaque."""

    candidate = _candidate().model_copy()
    if state_kind == "underscored-key":
        candidate.__dict__["_determinability"] = "DETERMINATE"
    else:
        private_state = {} if state_kind == "private-empty" else {"_secret": "value"}
        object.__setattr__(candidate, "__pydantic_private__", private_state)

    with pytest.raises(ValueError, match=r"private|undeclared|canonical|runtime"):
        candidate.assert_raw_candidate_only()
    with pytest.raises(ValueError, match=r"private|undeclared|canonical|runtime"):
        candidate.model_dump(warnings="none")


def test_candidate_direct_gate_rejects_undeclared_enum_runtime_state() -> None:
    """Catches an underscored final field hidden on a canonical enum singleton."""

    candidate = _candidate()
    status_state = candidate.coverage.status.__dict__
    status_state["_determinability"] = "DETERMINATE"
    try:
        with pytest.raises(ValueError, match=r"enum|undeclared|canonical|runtime"):
            candidate.assert_raw_candidate_only()
        with pytest.raises(ValueError, match=r"enum|undeclared|canonical|runtime"):
            candidate.model_dump(warnings="none")
    finally:
        status_state.pop("_determinability", None)


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    (
        ("_value_", "PARTIAL"),
        ("_name_", "PARTIAL"),
        ("__objclass__", StageCompletionStatus.PARTIAL),
        ("_sort_order_", 1),
    ),
)
def test_candidate_direct_gate_rejects_incoherent_canonical_enum_state(
    field_name: str,
    forged_value: object,
) -> None:
    """Catches canonical enum slots no longer matching the declared member."""

    candidate = _candidate()
    status_state = candidate.coverage.status.__dict__
    canonical_state = dict(status_state)
    status_state[field_name] = forged_value
    try:
        with pytest.raises(ValueError, match=r"enum.*canonical|canonical.*enum"):
            candidate.assert_raw_candidate_only()
    finally:
        status_state.clear()
        status_state.update(canonical_state)


def test_supervised_record_returns_a_fresh_exact_gold_tree() -> None:
    """Catches training retaining a mutable prevalidated GoldParserTarget instance."""

    gold = _gold(_candidate())
    record = _record(gold)

    assert type(record.target) is GoldParserTarget
    assert type(record.target.candidate_target) is ParserCandidateOutput
    assert record.target is not gold
    assert record.target.candidate_target is not gold.candidate_target


def _serialization_subject(name: str, *, forged: bool) -> BaseModel:
    candidate = _candidate()
    nested = _hidden_final(candidate) if forged else candidate
    if name == "candidate":
        return nested
    gold = _gold(candidate)
    if forged:
        gold = gold.model_copy(update={"candidate_target": nested})
    if name == "gold":
        return gold
    if name == "record":
        record = _record(_gold(candidate))
        return record.model_copy(update={"target": gold}) if forged else record
    if name == "stage":
        stage = MvtAStageOutput.model_validate(_stage_payload(candidate))
        return stage.model_copy(update={"candidates": nested}) if forged else stage
    if name in {"prepared-record", "prepared-dataset"}:
        dataset = _prepared_dataset()
        return dataset.records[0] if name == "prepared-record" else dataset
    raise AssertionError(f"unknown serialization subject: {name}")


def _prepared_dataset() -> PreparedDataset:
    return prepare_dataset((_training_record(_gold(_candidate())),))


def _forged_prepared_dataset() -> tuple[PreparedRecord, PreparedDataset]:
    dataset = _prepared_dataset()
    prepared = dataset.records[0]
    candidate = prepared.record.target.candidate_target
    forged_gold = prepared.record.target.model_copy(
        update={"candidate_target": _hidden_final(candidate)}
    )
    forged_record = prepared.record.model_copy(update={"target": forged_gold})
    forged_prepared = prepared.model_copy(update={"record": forged_record})
    forged_dataset = dataset.model_copy(update={"records": (forged_prepared,)})
    return forged_prepared, forged_dataset


def _tampered_custody_dataset(case: str) -> PreparedDataset:
    dataset = _prepared_dataset()
    prepared = dataset.records[0]
    record = prepared.record
    if case == "input-text":
        record = record.model_copy(
            update={"input_text": ParserAIInput(language="it").model_dump_json()}
        )
    elif case == "source-id":
        provenance = record.provenance.model_copy(update={"source_id": "tampered-source"})
        record = record.model_copy(update={"provenance": provenance})
    else:
        raise AssertionError(f"unknown custody tamper: {case}")
    prepared = prepared.model_copy(update={"record": record})
    return dataset.model_copy(update={"records": (prepared,)})


@pytest.mark.parametrize("name", ("candidate", "gold", "record", "stage"))
@pytest.mark.parametrize("serializer", ("model_dump", "model_dump_json"))
def test_class_owned_serialization_rejects_hidden_candidate_state(
    name: str,
    serializer: str,
) -> None:
    """Catches a parent serializer stripping hidden state before revalidation."""

    subject = _serialization_subject(name, forged=True)

    with pytest.raises(ValueError, match=r"determinability|final field|canonical"):
        getattr(subject, serializer)(round_trip=True, warnings="none")


@pytest.mark.parametrize("name", ("candidate", "gold", "record", "stage"))
def test_valid_class_owned_serialization_still_round_trips(name: str) -> None:
    """Catches serialization hardening breaking canonical model compatibility."""

    subject = _serialization_subject(name, forged=False)

    python_payload = subject.model_dump(mode="python", round_trip=True, warnings="error")
    json_payload = subject.model_dump_json(round_trip=True, warnings="error")

    assert type(subject).model_validate(python_payload) == subject
    assert type(subject).model_validate_json(json_payload) == subject


@pytest.mark.parametrize("serializer", ("model_dump", "model_dump_json"))
@pytest.mark.parametrize("name", ("prepared-record", "prepared-dataset"))
def test_prepared_parent_serialization_rejects_hidden_candidate_state(
    serializer: str,
    name: str,
) -> None:
    """Catches prepared parent dumps laundering an invalid supervised target."""

    prepared, dataset = _forged_prepared_dataset()
    subject = prepared if name == "prepared-record" else dataset

    with pytest.raises(ValueError, match=r"determinability|final field|canonical"):
        getattr(subject, serializer)(round_trip=True, warnings="none")


@pytest.mark.parametrize(
    "name",
    (
        "candidate",
        "gold",
        "record",
        "stage",
        "prepared-record",
        "prepared-dataset",
    ),
)
@pytest.mark.parametrize("serializer", ("model_dump", "model_dump_json"))
def test_class_owned_serialization_rejects_hidden_root_state(
    name: str,
    serializer: str,
) -> None:
    """Catches envelope-level final state being silently omitted by Pydantic."""

    subject = _serialization_subject(name, forged=False).model_copy()
    subject.__dict__["determinability"] = "DETERMINATE"

    with pytest.raises(ValueError, match=r"determinability|final field|canonical"):
        getattr(subject, serializer)(round_trip=True, warnings="none")


def test_dumps_prepared_jsonl_rejects_hidden_candidate_state() -> None:
    """Catches canonical JSONL silently stripping an invalid prepared target."""

    prepared, _dataset = _forged_prepared_dataset()

    with pytest.raises(ValueError, match=r"determinability|final field|canonical"):
        dumps_prepared_jsonl((prepared,))


def test_export_rejects_hidden_candidate_before_any_write(tmp_path: Path) -> None:
    """Catches export laundering a forged dataset after creating output artifacts."""

    _prepared, dataset = _forged_prepared_dataset()
    output = tmp_path / "must-not-exist"

    with pytest.raises(MLXPipelineError, match=r"dataset MLX.*non valido"):
        export_mlx_dataset(dataset, output)

    assert not output.exists()


@pytest.mark.parametrize("case", ("input-text", "source-id"))
def test_prepared_dataset_revalidation_rejects_stale_manifest_custody(case: str) -> None:
    """Catches prepared content no longer bound to its manifest record checksum."""

    dataset = _tampered_custody_dataset(case)

    with pytest.raises(ValueError, match=r"manifest incoerente|record checksum|input|source"):
        dataset._revalidated_for_serialization()


@pytest.mark.parametrize("case", ("input-text", "source-id"))
def test_export_rejects_stale_manifest_custody_before_any_write(
    case: str,
    tmp_path: Path,
) -> None:
    """Catches export writing tampered chat data beside a stale source manifest."""

    dataset = _tampered_custody_dataset(case)
    output = tmp_path / f"must-not-exist-{case}"

    with pytest.raises(MLXPipelineError, match=r"dataset MLX.*non valido"):
        export_mlx_dataset(dataset, output)

    assert not output.exists()


@pytest.mark.parametrize("serializer", ("model_dump", "model_dump_json"))
def test_nested_knowledge_serialization_rejects_hidden_candidate_state(
    serializer: str,
) -> None:
    """Catches Pydantic parent serialization bypassing candidate methods."""

    knowledge = KnowledgeValue[tuple[ParserCandidateOutput, ...]](
        knowledge_state=KnowledgeState.PRESENT,
        value=(_hidden_final(_candidate()),),
        evidence_ids=("evidence-1",),
        source_scope_ids=("source-1",),
    )

    with pytest.raises(ValueError, match=r"determinability|final field|canonical"):
        getattr(knowledge, serializer)(round_trip=True, warnings="none")


@pytest.mark.parametrize("name", ("candidate", "gold"))
def test_direct_pickle_rejects_hidden_candidate_state(name: str) -> None:
    """Catches class-owned pickle preserving hidden candidate state."""

    candidate = _candidate()
    forged_candidate = _hidden_final(candidate)
    subject: BaseModel = forged_candidate
    if name == "gold":
        subject = _gold(candidate).model_copy(update={"candidate_target": forged_candidate})

    with pytest.raises(ValueError, match=r"determinability|final field|canonical"):
        pickle.dumps(subject)


@pytest.mark.parametrize("name", ("candidate", "gold"))
def test_valid_direct_pickle_still_round_trips(name: str) -> None:
    """Catches pickle hardening breaking canonical candidate and gold values."""

    candidate = _candidate()
    subject: BaseModel = candidate if name == "candidate" else _gold(candidate)

    restored = pickle.loads(pickle.dumps(subject))

    assert restored == subject
    assert restored is not subject


@pytest.mark.parametrize("serializer", ("model_dump", "model_dump_json"))
@pytest.mark.parametrize(
    ("name", "expected_keys"),
    (
        ("candidate", {"coverage", "model_metadata"}),
        (
            "gold",
            {
                "candidate_target",
                "adjudication_id",
                "reviewer_ids",
                "adjudication_rationale",
                "submission_references",
                "comparison_status",
                "material_differences",
            },
        ),
        (
            "record",
            {"record_id", "task", "language", "input_text", "target", "provenance"},
        ),
        ("stage", {"stage_id", "status", "candidates", "coverage", "provenance"}),
        (
            "prepared-record",
            {
                "record",
                "normalized_input",
                "canonical_target",
                "exact_fingerprint",
                "near_fingerprint",
                "leakage_group_id",
                "split",
            },
        ),
        ("prepared-dataset", {"records", "manifest", "report"}),
    ),
)
def test_guarded_serialization_preserves_exclude_unset(
    serializer: str,
    name: str,
    expected_keys: set[str],
) -> None:
    """Catches canonical reconstruction marking every default as explicitly set."""

    subject = _serialization_subject(name, forged=False)
    serialized = getattr(subject, serializer)(exclude_unset=True, warnings="error")
    payload = json.loads(serialized) if serializer == "model_dump_json" else serialized

    assert set(payload) == expected_keys
    if name in {"gold", "record", "stage"}:
        candidate_payload = payload
        if name == "gold":
            candidate_payload = payload["candidate_target"]
        elif name == "record":
            candidate_payload = payload["target"]["candidate_target"]
        else:
            candidate_payload = payload["candidates"]
        assert set(candidate_payload) == {"coverage", "model_metadata"}


def test_candidate_rejects_field_set_missing_required_fields() -> None:
    """Catches forged metadata making required candidate fields disappear."""

    candidate = _candidate().model_copy()
    object.__setattr__(candidate, "__pydantic_fields_set__", set())

    with pytest.raises(ValueError, match=r"field-set|canonical|required"):
        candidate.assert_raw_candidate_only()
    with pytest.raises(ValueError, match=r"field-set|canonical|required"):
        candidate.model_dump(exclude_unset=True)


@pytest.mark.parametrize("name", ("gold", "record", "stage", "prepared-dataset"))
def test_parent_serialization_rejects_nested_candidate_field_set_forgery(name: str) -> None:
    """Catches a parent dump accepting a nested candidate with empty fields-set."""

    subject = _serialization_subject(name, forged=False)
    if name == "gold":
        candidate = subject.candidate_target
    elif name == "record":
        candidate = subject.target.candidate_target
    elif name == "stage":
        candidate = subject.candidates
    else:
        candidate = subject.records[0].record.target.candidate_target
    assert isinstance(candidate, ParserCandidateOutput)
    object.__setattr__(candidate, "__pydantic_fields_set__", set())

    with pytest.raises(ValueError, match=r"field-set|canonical|required"):
        subject.model_dump(exclude_unset=True)


@pytest.mark.parametrize("forge", (_underscored_hidden_state, _pydantic_private_hidden_state))
@pytest.mark.parametrize("name", ("gold", "record", "stage", "prepared-dataset"))
def test_parent_serialization_rejects_nested_private_candidate_state(
    name: str,
    forge: Callable[[ParserCandidateOutput], ParserCandidateOutput],
) -> None:
    """Catches parent serialization omitting private nested candidate state."""

    subject = _serialization_subject(name, forged=False)
    candidate = _candidate()
    forged_candidate = forge(candidate)
    if name == "gold":
        subject = subject.model_copy(update={"candidate_target": forged_candidate})
    elif name == "record":
        gold = subject.target.model_copy(update={"candidate_target": forged_candidate})
        subject = subject.model_copy(update={"target": gold})
    elif name == "stage":
        subject = subject.model_copy(update={"candidates": forged_candidate})
    else:
        prepared = subject.records[0]
        record = prepared.record
        gold = record.target.model_copy(update={"candidate_target": forged_candidate})
        record = record.model_copy(update={"target": gold})
        prepared = prepared.model_copy(update={"record": record})
        subject = subject.model_copy(update={"records": (prepared,)})

    with pytest.raises(ValueError, match=r"private|undeclared|canonical|runtime"):
        subject.model_dump(warnings="none")


@pytest.mark.parametrize("name", ("gold", "record", "stage", "prepared-dataset"))
def test_parent_serialization_rejects_nested_enum_runtime_state(name: str) -> None:
    """Catches parent serialization trusting a mutated canonical enum singleton."""

    subject = _serialization_subject(name, forged=False)
    status_state = StageCompletionStatus.COMPLETE.__dict__
    status_state["_determinability"] = "DETERMINATE"
    try:
        with pytest.raises(ValueError, match=r"enum|undeclared|canonical|runtime"):
            subject.model_dump(warnings="none")
    finally:
        status_state.pop("_determinability", None)


def test_candidate_rejects_nested_non_default_field_missing_from_field_set() -> None:
    """Catches a valid non-default nested value hidden from exclude_unset dumps."""

    metadata = _candidate().model_metadata.model_copy(update={"model_checksum": "a" * 64})
    metadata_fields_set = set(metadata.__pydantic_fields_set__)
    metadata_fields_set.remove("model_checksum")
    object.__setattr__(metadata, "__pydantic_fields_set__", metadata_fields_set)
    candidate = _candidate().model_copy(update={"model_metadata": metadata})

    with pytest.raises(ValueError, match=r"field-set|canonical|default"):
        candidate.assert_raw_candidate_only()
    with pytest.raises(ValueError, match=r"field-set|canonical|default"):
        _gold(_candidate()).model_copy(update={"candidate_target": candidate}).model_dump(
            exclude_unset=True
        )


def test_candidate_canonicalization_preserves_valid_sparse_field_sets() -> None:
    """Catches exact reconstruction broadening a valid sparse dump contract."""

    candidate = _candidate()
    canonical = candidate.assert_raw_candidate_only()

    assert canonical.__pydantic_fields_set__ == candidate.__pydantic_fields_set__
    assert (
        canonical.model_metadata.__pydantic_fields_set__
        == candidate.model_metadata.__pydantic_fields_set__
    )
    assert set(canonical.model_dump(exclude_unset=True)) == {
        "coverage",
        "model_metadata",
    }


@pytest.mark.parametrize("field_name", ("source_id", "reviewer_ids"))
@pytest.mark.parametrize("serializer", ("model_dump", "model_dump_json"))
def test_supervised_serialization_rejects_noncanonical_normalized_scalar_state(
    field_name: str,
    serializer: str,
) -> None:
    """Catches same-type raw values differing from their validated canonical value."""

    record = _training_record(_gold(_candidate()))
    forged_value: object = "  training-source-1  "
    if field_name == "reviewer_ids":
        forged_value = (" reviewer-a ", "reviewer-b")
    provenance = record.provenance.model_copy(update={field_name: forged_value})
    forged = record.model_copy(update={"provenance": provenance})

    with pytest.raises(ValueError, match=r"canonical|runtime|source_id|reviewer_ids"):
        getattr(forged, serializer)(warnings="none")


def test_scalar_comparison_failure_is_normalized_to_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches an ordinary exact-value comparison failure escaping the boundary."""

    def explode(_self: object, _other: object) -> bool:
        raise RuntimeError("scalar comparison failed")

    monkeypatch.setattr(StageCompletionStatus, "__eq__", explode)

    with pytest.raises(ValueError, match="scalar comparison failed"):
        _candidate().assert_raw_candidate_only()


def test_scalar_comparison_does_not_swallow_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keeps process-control signals outside exact-value comparison errors."""

    def explode(_self: object, _other: object) -> bool:
        raise _ControlFlowSignal()

    monkeypatch.setattr(StageCompletionStatus, "__eq__", explode)

    with pytest.raises(_ControlFlowSignal):
        _candidate().assert_raw_candidate_only()


def test_exact_scalar_comparison_preserves_schema_accepted_json_nan() -> None:
    """Keeps the existing JsonValue NaN behavior through exact reconstruction."""

    record = _record(_gold(_candidate())).model_copy(
        update={"metadata": {"schema_accepted_nan": float("nan")}}
    )

    python_payload = record.model_dump(mode="python", warnings="none")
    json_payload = json.loads(record.model_dump_json(warnings="none"))

    assert isnan(python_payload["metadata"]["schema_accepted_nan"])
    assert json_payload["metadata"]["schema_accepted_nan"] is None


def test_gold_boundary_wraps_ordinary_runtime_inspection_failure() -> None:
    """Catches an ordinary raw-tree failure escaping instead of denying the target."""

    candidate = _ExplodingCandidate.model_validate(
        _candidate().model_dump(mode="python", round_trip=True)
    )
    _ExplodingCandidate.failure = RuntimeError("raw candidate inspection failed")
    try:
        with pytest.raises(ValueError, match="raw candidate inspection failed"):
            GoldParserTarget.model_validate(_gold_payload(candidate))
    finally:
        _ExplodingCandidate.failure = None


def test_gold_boundary_does_not_swallow_base_exception() -> None:
    """Keeps process-control signals outside candidate validation errors."""

    candidate = _ExplodingCandidate.model_validate(
        _candidate().model_dump(mode="python", round_trip=True)
    )
    _ExplodingCandidate.failure = _ControlFlowSignal()
    try:
        with pytest.raises(_ControlFlowSignal):
            GoldParserTarget.model_validate(_gold_payload(candidate))
    finally:
        _ExplodingCandidate.failure = None
