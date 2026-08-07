"""Release blockers for split governance and record-to-facsimile semantics."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ntruth.design import compile_experiment_block
from ntruth.facsimile import FacsimileScientificProjection
from ntruth.governance.lineage import CorpusSplit
from ntruth.graph.builder import materialize_inferential_graph
from ntruth.graph.determinability import derive_determinability
from ntruth.schemas.core import (
    Determinability,
    EvidenceSpan,
    EvidenceType,
    Provenance,
    ProvenanceKind,
)
from ntruth.schemas.experiment import (
    Contrast,
    Endpoint,
    Estimand,
    ExperimentBlock,
    Factor,
    Hierarchy,
    Inferability,
    InferenceTarget,
    InferenceTargetStatus,
    NScope,
    TriState,
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import GraphNode, NodeType
from ntruth.training import AnnotationStatus, DatasetManifest, SupervisedRecord
from ntruth.training.records import ManifestRecord, SupervisionProvenance

pytestmark = pytest.mark.invariant

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests/fixtures/v6/facsimile_split_counterfactuals.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _apply_patch(payload: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    for dotted_path, value in patch.items():
        parts = dotted_path.split(".")
        target: dict[str, Any] = result
        for part in parts[:-1]:
            nested = target[part]
            assert isinstance(nested, dict), f"patch non applicabile a {dotted_path}"
            target = nested
        target[parts[-1]] = value
    return result


def _supervised_record(
    record_id: str,
    *,
    split: CorpusSplit,
    training_eligible: bool,
    evaluation_eligible: bool,
) -> SupervisedRecord:
    return SupervisedRecord(
        record_id=record_id,
        task="v6-invariant",
        language="en",
        input_text="Three cultures were independently allocated before treatment.",
        target={"candidate_graph": "fixture"},
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=_sha(f"source-{record_id}"),
            governance_hash=_sha(f"governance-{record_id}"),
            license_or_authorization_id="fixture-license",
            guideline_version="6.0",
            reviewer_count=2,
            reviewer_roles=("wet-lab", "biostatistician"),
        ),
        annotation_status=AnnotationStatus.DOUBLE_REVIEWED,
        training_eligible=training_eligible,
        evaluation_eligible=evaluation_eligible,
        requested_split=split,
    )


def _manifest_record(payload: dict[str, str], index: int) -> ManifestRecord:
    split = CorpusSplit(payload["split"])
    training_eligible = split is CorpusSplit.TRAIN
    return ManifestRecord(
        record_id=payload["record_id"],
        record_checksum=_sha(f"record-{index}-{payload['record_id']}"),
        exact_fingerprint=_sha(f"exact-{index}-{payload['record_id']}"),
        near_fingerprint=_sha(f"near-{index}-{payload['record_id']}"),
        split=split,
        leakage_group_id=payload["leakage_group_id"],
        source_id=f"source-{index}",
        source_asset_id=f"asset-{index}",
        source_sha256=_sha(f"source-{index}"),
        governance_hash=_sha(f"governance-{index}"),
        annotation_status=AnnotationStatus.DOUBLE_REVIEWED,
        training_eligible=training_eligible,
        evaluation_eligible=not training_eligible,
        license_or_authorization_id="fixture-license",
        reviewer_count=2,
    )


def _dataset_manifest(records: list[dict[str, str]]) -> DatasetManifest:
    return DatasetManifest(
        record_schema_version="1.0.0",
        normalization_version="1.0.0",
        config_checksum=_sha("config"),
        decisions_checksum=_sha("decisions"),
        report_checksum=_sha("report"),
        records=tuple(_manifest_record(item, index) for index, item in enumerate(records)),
    )


def test_split_eligibility_positive_contracts() -> None:
    train = _supervised_record(
        "train-record",
        split=CorpusSplit.TRAIN,
        training_eligible=True,
        evaluation_eligible=False,
    )
    test = _supervised_record(
        "test-record",
        split=CorpusSplit.TEST,
        training_eligible=False,
        evaluation_eligible=True,
    )

    assert train.training_eligible and not train.evaluation_eligible
    assert test.evaluation_eligible and not test.training_eligible


@pytest.mark.parametrize(
    ("split", "training_eligible", "evaluation_eligible", "message"),
    (
        (CorpusSplit.TEST, True, True, "training_eligible=false"),
        (CorpusSplit.EXTERNAL_CHALLENGE, True, True, "training_eligible=false"),
        (CorpusSplit.TRAIN, False, True, "evaluation_only=false"),
    ),
)
def test_split_eligibility_negative_contracts(
    split: CorpusSplit,
    training_eligible: bool,
    evaluation_eligible: bool,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _supervised_record(
            f"invalid-{split.value}",
            split=split,
            training_eligible=training_eligible,
            evaluation_eligible=evaluation_eligible,
        )


def test_counterfactual_projection_preserves_distinct_semantics() -> None:
    base = FacsimileScientificProjection.model_validate(FIXTURE["base_projection"])
    equal_counts_case = next(
        item
        for item in FIXTURE["projection_counterfactuals"]
        if item["case_id"] == "equal_numeric_counts_keep_distinct_semantics"
    )
    counterfactual = FacsimileScientificProjection.model_validate(
        _apply_patch(FIXTURE["base_projection"], equal_counts_case["patch"])
    )

    assert base.experimental_unit_count.value == 3
    assert base.biological_source_count.value == 1
    assert counterfactual.experimental_unit_count.value == 3
    assert counterfactual.biological_source_count.value == 3
    assert (
        counterfactual.experimental_unit_count.kind
        is not counterfactual.biological_source_count.kind
    )
    assert counterfactual.inference_scope.dimension.value == "inference_scope"
    assert counterfactual.validity_of_allocation.dimension.value == "allocation_validity"


INVALID_PROJECTION_CASES = tuple(
    item for item in FIXTURE["projection_counterfactuals"] if not item["expected_valid"]
)


@pytest.mark.parametrize(
    "case",
    INVALID_PROJECTION_CASES,
    ids=[item["case_id"] for item in INVALID_PROJECTION_CASES],
)
def test_counterfactual_projection_rejects_semantic_conflation(
    case: dict[str, Any],
) -> None:
    payload = _apply_patch(FIXTURE["base_projection"], case["patch"])
    with pytest.raises(ValidationError, match=case["error"]):
        FacsimileScientificProjection.model_validate(payload)


def test_dataset_manifest_accepts_one_split_per_record_and_leakage_group() -> None:
    records = FIXTURE["dataset_split_counterfactuals"]["positive"]
    manifest = _dataset_manifest(records)

    assert {record.split for record in manifest.records} == {CorpusSplit.TRAIN}
    assert len({record.record_id for record in manifest.records}) == len(manifest.records)


def test_dataset_manifest_rejects_one_record_in_multiple_splits() -> None:
    records = FIXTURE["dataset_split_counterfactuals"]["record_cross_split"]
    with pytest.raises(ValidationError, match="record_id duplicati"):
        _dataset_manifest(records)


def test_dataset_manifest_rejects_leakage_group_across_splits() -> None:
    records = FIXTURE["dataset_split_counterfactuals"]["leakage_group_cross_split"]
    with pytest.raises(ValidationError, match="leakage group attraversa split"):
        _dataset_manifest(records)


def _determinability_block(evidence_type: EvidenceType) -> ExperimentBlock:
    evidence_id = "evidence-allocation"
    explicit = Provenance(origin=ProvenanceKind.EXPLICIT, evidence_ids=(evidence_id,))
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("control", "drug"),
        allocation_level=NodeType.ANIMAL,
        application_level=NodeType.ANIMAL,
        allocation_confidence=1.0,
        application_confidence=1.0,
        allocation_evidence_ids=(evidence_id,),
        independence_evidence_ids=(evidence_id,),
        independently_assigned=TriState.TRUE,
        independence_mechanism="four animals were independently allocated",
        provenance=explicit,
    )
    endpoint = Endpoint(
        id="endpoint-weight",
        name="body weight",
        measured_on=NodeType.ANIMAL,
        evidence_ids=(evidence_id,),
        provenance=explicit,
    )
    contrast = Contrast(
        id="contrast-drug-control",
        label="drug vs control",
        factor_ids=(factor.id,),
        compared_levels=("drug", "control"),
        endpoint_ids=(endpoint.id,),
        evidence_ids=(evidence_id,),
        provenance=explicit,
    )
    human = Provenance(
        origin=ProvenanceKind.USER,
        evidence_ids=(evidence_id,),
        actor_role="researcher",
    )
    target = InferenceTarget(
        id="target-animals",
        question_text="What is the treatment effect on body weight?",
        population_of_inference="animals under the declared conditions",
        factor_ids=(factor.id,),
        contrast_ids=(contrast.id,),
        endpoint_ids=(endpoint.id,),
        target_biological_unit=NodeType.ANIMAL,
        evidence_ids=(evidence_id,),
        provenance=human,
        status=InferenceTargetStatus.USER_CONFIRMED,
    )
    estimand = Estimand(
        id="estimand-weight",
        endpoint_id=endpoint.id,
        effect_measure="mean difference",
        target_population_or_unit="animals under the declared conditions",
        generalization_level="animal",
        factor_ids=(factor.id,),
        evidence_ids=(evidence_id,),
        provenance=human,
    )
    hierarchy = materialize_inferential_graph(
        Hierarchy(
            nodes=(
                GraphNode(
                    id="animal",
                    type=NodeType.ANIMAL,
                    label="animals",
                    count=4,
                    evidence_ids=(evidence_id,),
                    provenance=explicit,
                ),
            )
        ),
        block_id="block-authority",
        inference_targets=(target,),
        estimands=(estimand,),
    )
    assessment = UnitAssessment(
        id="assessment-weight",
        scope=NScope(
            factor_id=factor.id,
            contrast_id=contrast.id,
            endpoint_id=endpoint.id,
            inference_target_id=target.id,
        ),
        experimental_unit=NodeType.ANIMAL,
        observational_unit=NodeType.ANIMAL,
        analytical_unit=NodeType.ANIMAL,
        n_independent=4,
        inferability=Inferability.INFERABLE,
        evidence_ids=(evidence_id,),
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            evidence_ids=(evidence_id,),
            derivation="deterministic fixture",
        ),
    )
    return ExperimentBlock(
        id="block-authority",
        document_id="document-authority",
        inference_targets=(target,),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        estimands=(estimand,),
        hierarchy=hierarchy,
        unit_assessments=(assessment,),
        evidence=(
            EvidenceSpan(
                id=evidence_id,
                file_id="methods",
                text="Four animals were independently allocated.",
                evidence_type=evidence_type,
            ),
        ),
        versions=Versions(
            schema_version="0.3.0",
            parser_version="0.3.0",
            graph_version="0.3.0",
            ruleset_id="ntruth-core",
            ruleset_version="0.2.0",
        ),
    )


def test_structural_evidence_can_close_but_author_assertion_alone_cannot() -> None:
    structural = _determinability_block(EvidenceType.STRUCTURAL_FACT)
    assertion_only = _determinability_block(EvidenceType.AUTHOR_ASSERTION)

    assert (
        derive_determinability(structural, compile_experiment_block(structural))
        is Determinability.DETERMINATE
    )
    assert (
        derive_determinability(assertion_only, compile_experiment_block(assertion_only))
        is Determinability.INSUFFICIENT_INFORMATION
    )
