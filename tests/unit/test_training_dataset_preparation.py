from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from ntruth.governance.lineage import CorpusSplit
from ntruth.training import (
    AnnotationStatus,
    DatasetFormatError,
    DatasetManifest,
    DatasetValidationError,
    DuplicateKind,
    PreparationConfig,
    SplitRatios,
    SupervisedRecord,
    SupervisionProvenance,
    dumps_dataset_manifest,
    dumps_preparation_report,
    dumps_prepared_jsonl,
    dumps_supervised_jsonl,
    loads_supervised_jsonl,
    prepare_dataset,
)
from ntruth.training.records import normalize_record


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provenance(
    source_id: str,
    *,
    publication_id: str | None = None,
    project_id: str | None = None,
    bundle_id: str | None = None,
    laboratory_id: str | None = None,
    corresponding_author_id: str | None = None,
    synthetic: bool = False,
    adjudication_id: str | None = None,
) -> SupervisionProvenance:
    return SupervisionProvenance(
        source_id=source_id,
        source_asset_id=f"asset-{source_id}",
        source_sha256=_hash(f"source:{source_id}"),
        governance_hash=_hash(f"governance:{source_id}"),
        publication_id=publication_id,
        project_id=project_id,
        bundle_id=bundle_id,
        laboratory_id=laboratory_id,
        corresponding_author_id=corresponding_author_id,
        license_or_authorization_id=f"authorization-{source_id}",
        guideline_version="3.0",
        reviewer_count=2,
        reviewer_roles=("biologist", "biostatistician"),
        adjudication_id=adjudication_id,
        synthetic=synthetic,
    )


def _record(
    record_id: str,
    input_text: str | None = None,
    *,
    target: dict[str, object] | None = None,
    source_id: str | None = None,
    publication_id: str | None = None,
    project_id: str | None = None,
    bundle_id: str | None = None,
    laboratory_id: str | None = None,
    corresponding_author_id: str | None = None,
    status: AnnotationStatus = AnnotationStatus.DOUBLE_REVIEWED,
    eligible: bool = True,
    requested_split: CorpusSplit | None = None,
    synthetic: bool = False,
) -> SupervisedRecord:
    source = source_id or record_id
    adjudication_id = (
        f"adjudication-{record_id}" if status is AnnotationStatus.ADJUDICATED else None
    )
    return SupervisedRecord(
        record_id=record_id,
        task="experimental_design",
        language="it",
        domain="life_sciences",
        input_text=input_text or f"testo sperimentale univoco {record_id}",
        target=target or {"label": record_id},
        provenance=_provenance(
            source,
            publication_id=publication_id,
            project_id=project_id,
            bundle_id=bundle_id,
            laboratory_id=laboratory_id,
            corresponding_author_id=corresponding_author_id,
            synthetic=synthetic,
            adjudication_id=adjudication_id,
        ),
        annotation_status=status,
        training_eligible=eligible,
        requested_split=requested_split,
    )


def test_supervised_record_enforces_curation_and_authorization() -> None:
    candidate_provenance = _provenance("candidate")
    with pytest.raises(ValidationError, match="candidate/single_reviewed"):
        SupervisedRecord(
            record_id="candidate",
            task="design",
            language="it",
            input_text="testo",
            target={"label": "x"},
            provenance=candidate_provenance,
            annotation_status=AnnotationStatus.CANDIDATE,
            training_eligible=True,
        )

    with pytest.raises(ValidationError, match="adjudication_id"):
        SupervisedRecord(
            record_id="adjudicated",
            task="design",
            language="it",
            input_text="testo",
            target={"label": "x"},
            provenance=_provenance("adjudicated"),
            annotation_status=AnnotationStatus.ADJUDICATED,
            training_eligible=True,
        )

    unauthorized = candidate_provenance.model_copy(update={"license_or_authorization_id": None})
    with pytest.raises(ValidationError, match="licenza o autorizzazione"):
        SupervisedRecord(
            record_id="unauthorized",
            task="design",
            language="it",
            input_text="testo",
            target={"label": "x"},
            provenance=unauthorized,
            annotation_status=AnnotationStatus.DOUBLE_REVIEWED,
            training_eligible=True,
        )


def test_jsonl_round_trip_is_canonical_and_reports_physical_line() -> None:
    first = _record("a")
    second = _record("b")
    payload = dumps_supervised_jsonl((second, first))

    assert payload.endswith("\n")
    assert '"record_id":"a"' in payload.splitlines()[0]
    assert loads_supervised_jsonl(payload) == (first, second)

    with pytest.raises(DatasetFormatError) as captured:
        loads_supervised_jsonl(payload.splitlines()[0] + "\n\n{}\n")
    assert captured.value.line_number == 3


def test_normalization_and_fingerprints_are_unicode_and_key_order_stable() -> None:
    first = _record(
        "first",
        "Caf\u00e9\u00a0A\r\nB",
        target={"nested": {"b": 2, "a": 1}},
    )
    second = _record(
        "second",
        "Cafe\u0301 a b",
        target={"nested": {"a": 1, "b": 2}},
    )
    changed_target = _record(
        "third",
        "Cafe\u0301 a b",
        target={"nested": {"a": 1, "b": 3}},
    )

    normalized_first = normalize_record(first, shingle_size=2)
    normalized_second = normalize_record(second, shingle_size=2)
    normalized_changed = normalize_record(changed_target, shingle_size=2)
    assert normalized_first.normalized_input == "caf\u00e9 a b"
    assert normalized_first.exact_fingerprint == normalized_second.exact_fingerprint
    assert normalized_first.exact_fingerprint != normalized_changed.exact_fingerprint


def test_exact_deduplication_prefers_adjudicated_provenance() -> None:
    text = "Dodici animali appartengono alle stesse quattro gabbie sperimentali."
    target = {"independent_unit": "cage"}
    reviewed = _record("a-reviewed", text, target=target, source_id="paper-a")
    adjudicated = _record(
        "z-adjudicated",
        text,
        target=target,
        source_id="paper-b",
        status=AnnotationStatus.ADJUDICATED,
    )

    dataset = prepare_dataset((reviewed, adjudicated))

    assert [record.record.record_id for record in dataset.records] == ["z-adjudicated"]
    assert dataset.report.exact_duplicate_count == 1
    decision = dataset.report.duplicate_decisions[0]
    assert decision.kind is DuplicateKind.EXACT
    assert decision.duplicate_source_asset_id == "asset-paper-a"
    assert decision.canonical_source_asset_id == "asset-paper-b"


def test_near_deduplication_does_not_use_transitive_chaining() -> None:
    first = _record("a", "uno due tre quattro cinque sei sette otto nove dieci", target={"x": 1})
    bridge = _record("b", "uno due tre quattro cinque sei sette otto nove alfa", target={"x": 1})
    endpoint = _record(
        "c",
        "uno due tre quattro cinque sei sette otto alfa beta",
        target={"x": 1},
    )
    config = PreparationConfig(
        shingle_size=1,
        near_duplicate_threshold=0.8,
        split_ratios=SplitRatios(train=1.0, validation=0.0, test=0.0),
    )

    dataset = prepare_dataset((endpoint, bridge, first), config=config)

    assert {record.record.record_id for record in dataset.records} == {"a", "c"}
    assert dataset.report.near_duplicate_count == 1
    assert dataset.report.duplicate_decisions[0].canonical_record_id == "a"


def test_conflicting_targets_fail_strictly_and_remain_visible_in_diagnostic_mode() -> None:
    left = _record("left", "stesso input", target={"unit": "animal"}, source_id="source-left")
    right = _record("right", "stesso input", target={"unit": "cage"}, source_id="source-right")

    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset((left, right))
    assert {issue.code for issue in captured.value.issues} == {"conflicting_targets"}

    diagnostic = prepare_dataset(
        (right, left),
        config=PreparationConfig(fail_on_error=False),
    )
    assert diagnostic.report.kept_count == 2
    assert diagnostic.report.exact_duplicate_count == 0
    assert {issue.code for issue in diagnostic.report.issues} == {"conflicting_targets"}


def test_split_components_are_transitive_and_respect_fixed_and_synthetic_sets() -> None:
    publication_anchor = _record(
        "a",
        publication_id="publication-1",
        project_id="project-1",
        requested_split=CorpusSplit.TEST,
    )
    publication_link = _record(
        "b",
        publication_id="publication-1",
        project_id="project-2",
    )
    project_link = _record(
        "c",
        publication_id="publication-2",
        project_id="project-2",
    )
    source_anchor = _record("d", source_id="shared-source")
    source_link = _record("e", source_id="shared-source")
    synthetic = _record("synthetic", synthetic=True)
    external = _record("external", requested_split=CorpusSplit.EXTERNAL)
    laboratory_anchor = _record("lab-a", laboratory_id="laboratory-1")
    laboratory_link = _record(
        "lab-b",
        laboratory_id="laboratory-1",
        corresponding_author_id="author-1",
    )
    records = (
        publication_anchor,
        publication_link,
        project_link,
        source_anchor,
        source_link,
        synthetic,
        external,
        laboratory_anchor,
        laboratory_link,
    )

    dataset = prepare_dataset(records)
    by_id = {record.record.record_id: record for record in dataset.records}

    assert {by_id[item].split for item in ("a", "b", "c")} == {CorpusSplit.TEST}
    assert len({by_id[item].leakage_group_id for item in ("a", "b", "c")}) == 1
    assert by_id["d"].split is by_id["e"].split
    assert by_id["d"].leakage_group_id == by_id["e"].leakage_group_id
    assert by_id["synthetic"].split is CorpusSplit.TRAIN
    assert by_id["external"].split is CorpusSplit.EXTERNAL
    assert by_id["lab-a"].split is by_id["lab-b"].split
    assert by_id["lab-a"].leakage_group_id == by_id["lab-b"].leakage_group_id
    assert dataset.report.leakage_group_count == 5


def test_conflicting_fixed_splits_are_rejected_without_creating_leakage() -> None:
    train = _record(
        "train",
        publication_id="shared-publication",
        requested_split=CorpusSplit.TRAIN,
    )
    test = _record(
        "test",
        publication_id="shared-publication",
        requested_split=CorpusSplit.TEST,
    )

    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset((train, test))
    assert {issue.code for issue in captured.value.issues} == {"conflicting_requested_splits"}

    diagnostic = prepare_dataset(
        (train, test),
        config=PreparationConfig(fail_on_error=False),
    )
    assert len({record.split for record in diagnostic.records}) == 1
    assert {record.split for record in diagnostic.records} == {CorpusSplit.TEST}


def test_different_row_ids_from_the_same_source_asset_cannot_cross_splits() -> None:
    left_provenance = _provenance("row-left").model_copy(
        update={
            "source_asset_id": "shared-asset",
            "source_sha256": _hash("shared-source-content"),
        }
    )
    right_provenance = _provenance("row-right").model_copy(
        update={
            "source_asset_id": "shared-asset",
            "source_sha256": _hash("shared-source-content"),
        }
    )
    left = _record("row-left", requested_split=CorpusSplit.VALIDATION).model_copy(
        update={"provenance": left_provenance}
    )
    right = _record("row-right").model_copy(update={"provenance": right_provenance})

    dataset = prepare_dataset((left, right))

    assert {record.split for record in dataset.records} == {CorpusSplit.VALIDATION}
    assert len({record.leakage_group_id for record in dataset.records}) == 1


def test_output_is_input_order_independent_and_manifest_is_content_addressed() -> None:
    records = tuple(_record(f"record-{index}") for index in range(12))
    config = PreparationConfig(
        seed="fixed-seed",
        split_ratios=SplitRatios(train=0.5, validation=0.25, test=0.25),
    )

    forward = prepare_dataset(records, config=config)
    reverse = prepare_dataset(reversed(records), config=config)

    assert forward == reverse
    assert forward.manifest.dataset_id.startswith("dataset-")
    assert sum(forward.report.split_counts.values()) == 12
    assert all(forward.report.split_counts[name] > 0 for name in ("train", "validation", "test"))

    tampered = forward.manifest.model_dump(mode="json")
    tampered["dataset_id"] = "dataset-00000000000000000000"
    with pytest.raises(ValidationError, match="dataset_id non coerente"):
        DatasetManifest.model_validate(tampered)


def test_manifest_carries_source_and_governance_hashes_and_serializers_are_stable() -> None:
    record = _record("provenance-record", source_id="asset-source")
    dataset = prepare_dataset((record,))
    entry = dataset.manifest.records[0]

    assert entry.source_id == record.provenance.source_id
    assert entry.source_asset_id == record.provenance.source_asset_id
    assert entry.source_sha256 == record.provenance.source_sha256
    assert entry.governance_hash == record.provenance.governance_hash
    assert dumps_dataset_manifest(dataset.manifest).endswith("\n")
    assert dumps_preparation_report(dataset.report).endswith("\n")
    assert dumps_prepared_jsonl(dataset.records).endswith("\n")


def test_ineligible_records_are_excluded_and_reported_by_default() -> None:
    eligible = _record("eligible")
    candidate = _record(
        "candidate",
        status=AnnotationStatus.CANDIDATE,
        eligible=False,
    )

    dataset = prepare_dataset((candidate, eligible))

    assert dataset.report.input_count == 2
    assert dataset.report.eligible_count == 1
    assert dataset.report.excluded_count == 1
    assert [record.record.record_id for record in dataset.records] == ["eligible"]
    assert {issue.code for issue in dataset.report.issues} == {"training_ineligible_excluded"}


def test_duplicate_record_ids_are_always_structural_errors() -> None:
    first = _record("duplicate", source_id="one")
    second = _record("duplicate", source_id="two")

    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset(
            (first, second),
            config=PreparationConfig(fail_on_error=False),
        )
    assert {issue.code for issue in captured.value.issues} == {"duplicate_record_id"}


def test_empty_diagnostic_artifact_is_hashable_but_strict_mode_rejects_it() -> None:
    candidate = _record(
        "candidate-only",
        status=AnnotationStatus.CANDIDATE,
        eligible=False,
    )
    with pytest.raises(DatasetValidationError) as captured:
        prepare_dataset((candidate,))
    assert {issue.code for issue in captured.value.issues} == {"no_records_selected"}

    diagnostic = prepare_dataset(
        (candidate,),
        config=PreparationConfig(fail_on_error=False),
    )
    assert diagnostic.records == ()
    assert diagnostic.report.kept_count == 0
    assert diagnostic.manifest.dataset_id.startswith("dataset-")
