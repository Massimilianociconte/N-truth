"""PRD v3: contratto stabile, constrained e referenzialmente integro del parser AI."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ntruth.parser_ai import (
    CandidateContrast,
    CandidateEdge,
    CandidateEndpoint,
    CandidateEstimand,
    CandidateExperimentBlock,
    CandidateFactor,
    CandidateNode,
    DeterminabilityAssessment,
    NodeOntologyValue,
    ParserAIDocumentInput,
    ParserAIEvidenceSpan,
    ParserAIInput,
    ParserAIModelMetadata,
    ParserAIOutput,
    RelationOntologyValue,
    parser_ai_json_schemas,
    run_parser_adapter,
    validate_contract_pair,
)
from ntruth.schemas.core import Determinability, EvidenceType
from ntruth.schemas.graph import NodeType, RelationType

SHA = "a" * 64


def _request() -> ParserAIInput:
    return ParserAIInput(
        documents=(
            ParserAIDocumentInput(
                file_id="file-1",
                filename="methods.md",
                sha256=SHA,
                text="donor nested in cohort",
            ),
        ),
        metadata={"source": "fixture", "revision": 1},
        domain_hint="biology",
        language="en",
    )


def _output() -> ParserAIOutput:
    evidence = ParserAIEvidenceSpan(
        evidence_id="ev-1",
        file_id="file-1",
        evidence_type=EvidenceType.STRUCTURAL_FACT,
        text="donor",
        confidence=0.98,
        start=0,
        end=5,
    )
    return ParserAIOutput(
        experiment_blocks=(
            CandidateExperimentBlock(
                block_id="block-1",
                title="Experiment",
                evidence_ids=("ev-1",),
                confidence=0.9,
            ),
        ),
        evidence_spans=(evidence,),
        candidate_nodes=(
            CandidateNode(
                node_id="node-donor",
                block_id="block-1",
                node_type=NodeOntologyValue(value=NodeType.HUMAN_DONOR),
                label="donor",
                evidence_ids=("ev-1",),
                confidence=0.9,
            ),
            CandidateNode(
                node_id="node-cohort",
                block_id="block-1",
                node_type=NodeOntologyValue(value=NodeType.COHORT),
                label="cohort",
                evidence_ids=("ev-1",),
                confidence=0.8,
            ),
        ),
        candidate_edges=(
            CandidateEdge(
                edge_id="edge-1",
                block_id="block-1",
                source_id="node-donor",
                target_id="node-cohort",
                relation_type=RelationOntologyValue(value=RelationType.NESTED_IN),
                evidence_ids=("ev-1",),
                confidence=0.75,
            ),
        ),
        factors=(
            CandidateFactor(
                factor_id="factor-1",
                block_id="block-1",
                name="treatment",
                levels=("drug", "vehicle"),
                allocation_level=NodeOntologyValue(value=NodeType.HUMAN_DONOR),
                application_level=NodeOntologyValue(value=NodeType.HUMAN_DONOR),
                evidence_ids=("ev-1",),
                confidence=0.7,
            ),
        ),
        endpoints=(
            CandidateEndpoint(
                endpoint_id="endpoint-1",
                block_id="block-1",
                name="signal",
                evidence_ids=("ev-1",),
                confidence=0.7,
            ),
        ),
        contrasts=(
            CandidateContrast(
                contrast_id="contrast-1",
                block_id="block-1",
                factor_ids=("factor-1",),
                compared_levels=("drug", "vehicle"),
                endpoint_ids=("endpoint-1",),
                evidence_ids=("ev-1",),
                confidence=0.7,
            ),
        ),
        candidate_estimands=(
            CandidateEstimand(
                estimand_id="estimand-1",
                block_id="block-1",
                factor_ids=("factor-1",),
                contrast_id="contrast-1",
                endpoint_id="endpoint-1",
                effect_measure="mean difference",
                target_population_or_unit="sampled donors",
                generalization_level="HumanDonor",
                evidence_ids=("ev-1",),
                confidence=0.65,
            ),
        ),
        determinability=DeterminabilityAssessment(
            status=Determinability.DETERMINATE,
            rationale="All required references are present.",
            confidence=0.7,
            evidence_ids=("ev-1",),
        ),
        model_metadata=ParserAIModelMetadata(
            adapter_name="fixture",
            model_name="none",
            model_version="fixture",
            prompt_template_version="1",
        ),
    )


def test_contract_round_trip_and_source_validation() -> None:
    request = _request()
    output = _output()

    restored = ParserAIOutput.model_validate_json(output.model_dump_json())

    assert restored == output
    assert validate_contract_pair(request, output) is output


def test_json_schema_is_strict_and_contains_all_prd_output_channels() -> None:
    schemas = parser_ai_json_schemas()
    output_schema = schemas["output"]
    properties = output_schema["properties"]

    assert output_schema["additionalProperties"] is False
    assert {
        "experiment_blocks",
        "evidence_spans",
        "candidate_nodes",
        "candidate_edges",
        "factors",
        "endpoints",
        "contrasts",
        "candidate_estimands",
        "determinability",
        "alternatives",
        "clarification_questions",
        "model_metadata",
    } <= set(properties)

    definitions = output_schema["$defs"]
    factor_schema = definitions["CandidateFactor"]
    contrast_schema = definitions["CandidateContrast"]
    estimand_schema = definitions["CandidateEstimand"]
    assert {"allocation_level", "application_level"} <= set(factor_schema["required"])
    assert {"factor_ids", "compared_levels", "endpoint_ids"} <= set(contrast_schema["required"])
    assert {
        "endpoint_id",
        "effect_measure",
        "target_population_or_unit",
        "generalization_level",
        "factor_ids",
    } <= set(estimand_schema["required"])


def test_contract_supports_multifactor_contrasts_and_estimands() -> None:
    payload = _output().model_dump(mode="json")
    payload["factors"].append(
        {
            "factor_id": "factor-2",
            "block_id": "block-1",
            "name": "genotype",
            "levels": ["wild-type", "mutant"],
            "allocation_level": {"value": "HumanDonor", "original_text": None},
            "application_level": None,
            "evidence_ids": ["ev-1"],
            "confidence": 0.68,
        }
    )
    payload["contrasts"][0]["factor_ids"] = ["factor-1", "factor-2"]
    payload["contrasts"][0]["compared_levels"] = ["vehicle + wild-type", "drug + mutant"]
    payload["candidate_estimands"][0]["factor_ids"] = ["factor-1", "factor-2"]
    payload["candidate_estimands"][0]["timepoint"] = "day 7"
    payload["candidate_estimands"][0]["condition"] = "mutant background"

    output = ParserAIOutput.model_validate(payload)

    assert output.contrasts[0].factor_ids == ("factor-1", "factor-2")
    assert output.candidate_estimands[0].timepoint == "day 7"


def test_contract_rejects_incomplete_estimand_and_cross_block_factor() -> None:
    incomplete = _output().model_dump(mode="json")
    incomplete["candidate_estimands"][0]["effect_measure"] = ""
    with pytest.raises(ValidationError, match="effect_measure"):
        ParserAIOutput.model_validate(incomplete)

    cross_block = _output().model_dump(mode="json")
    cross_block["experiment_blocks"].append(
        {
            "block_id": "block-2",
            "title": "Second experiment",
            "evidence_ids": ["ev-1"],
            "confidence": 0.8,
        }
    )
    cross_block["factors"].append(
        {
            "factor_id": "factor-2",
            "block_id": "block-2",
            "name": "genotype",
            "levels": ["wild-type", "mutant"],
            "allocation_level": None,
            "application_level": None,
            "evidence_ids": ["ev-1"],
            "confidence": 0.7,
        }
    )
    cross_block["contrasts"][0]["factor_ids"] = ["factor-1", "factor-2"]
    with pytest.raises(ValidationError, match="altro experiment block"):
        ParserAIOutput.model_validate(cross_block)


def test_factor_levels_reject_non_units_but_preserve_explicit_other() -> None:
    payload = _output().model_dump(mode="json")
    payload["factors"][0]["allocation_level"] = {
        "value": "Endpoint",
        "original_text": None,
    }
    with pytest.raises(ValidationError, match="NodeType allocabile"):
        ParserAIOutput.model_validate(payload)

    payload["factors"][0]["allocation_level"] = {
        "value": "OTHER",
        "original_text": "microfluidic chamber",
    }
    assert ParserAIOutput.model_validate(payload).factors[0].allocation_level is not None


@pytest.mark.parametrize("cross_reference", ["edge", "alternative", "question"])
def test_contract_rejects_cross_block_candidate_references(cross_reference: str) -> None:
    payload = _output().model_dump(mode="json")
    payload["experiment_blocks"].append(
        {
            "block_id": "block-2",
            "title": "Second experiment",
            "evidence_ids": ["ev-1"],
            "confidence": 0.8,
        }
    )
    payload["candidate_nodes"].append(
        {
            "node_id": "node-second",
            "block_id": "block-2",
            "node_type": {"value": "Animal", "original_text": None},
            "label": "second animal",
            "evidence_ids": ["ev-1"],
            "confidence": 0.8,
        }
    )
    if cross_reference == "edge":
        payload["candidate_edges"][0]["target_id"] = "node-second"
    elif cross_reference == "alternative":
        payload["alternatives"] = [
            {
                "alternative_id": "alternative-1",
                "block_id": "block-1",
                "description": "cross-block alternative",
                "candidate_node_ids": ["node-second"],
                "candidate_edge_ids": [],
                "evidence_ids": ["ev-1"],
                "confidence": 0.6,
            }
        ]
    else:
        payload["clarification_questions"] = [
            {
                "question_id": "question-1",
                "block_id": "block-1",
                "question": "Which block owns this node?",
                "resolves_candidate_ids": ["node-second"],
                "rationale": "Block scope must stay explicit.",
            }
        ]

    with pytest.raises(ValidationError, match="altro experiment block"):
        ParserAIOutput.model_validate(payload)


def test_contract_rejects_hidden_verdict_unknown_vocab_and_bad_confidence() -> None:
    payload = _output().model_dump(mode="json")
    payload["verdict"] = "valid"
    with pytest.raises(ValidationError, match="Extra inputs"):
        ParserAIOutput.model_validate(payload)

    with pytest.raises(ValidationError):
        NodeOntologyValue(value="UnknownNode")
    with pytest.raises(ValidationError, match="original_text"):
        NodeOntologyValue(value="OTHER")
    assert NodeOntologyValue(value="OTHER", original_text="bioreactor")

    with pytest.raises(ValidationError):
        CandidateNode(
            node_id="bad",
            block_id="block-1",
            node_type=NodeOntologyValue(value=NodeType.ANIMAL),
            label="bad",
            evidence_ids=("ev-1",),
            confidence=float("nan"),
        )


def test_contract_rejects_dangling_references_and_mismatched_evidence() -> None:
    payload = _output().model_dump(mode="json")
    payload["candidate_edges"][0]["target_id"] = "missing-node"
    with pytest.raises(ValidationError, match="node_id sconosciuti"):
        ParserAIOutput.model_validate(payload)

    request = _request()
    response_payload = _output().model_dump(mode="json")
    response_payload["evidence_spans"][0]["text"] = "wrong"
    response = ParserAIOutput.model_validate(response_payload)
    with pytest.raises(ValueError, match="non coincide"):
        validate_contract_pair(request, response)


def test_statistical_code_cannot_support_an_allocation_edge() -> None:
    payload = _output().model_dump(mode="json")
    payload["evidence_spans"][0].update(
        {
            "evidence_type": EvidenceType.STATISTICAL_CODE,
            "code_artifact_id": "code-1",
        }
    )
    payload["candidate_edges"][0]["relation_type"] = {
        "value": RelationType.ALLOCATED_TO,
        "original_text": None,
    }

    with pytest.raises(ValidationError, match="non puo sostenere"):
        ParserAIOutput.model_validate(payload)


def test_adapter_protocol_is_backend_replaceable_and_validated() -> None:
    class FixtureAdapter:
        name = "fixture"
        version = "1"

        def parse(self, request: ParserAIInput) -> ParserAIOutput:
            assert request.contract_version == "2.0.0"
            return _output()

    assert run_parser_adapter(FixtureAdapter(), _request()) == _output()


def test_adapter_mapping_output_is_validated_too() -> None:
    class MappingAdapter:
        name = "mapping"
        version = "1"

        def parse(self, request: ParserAIInput) -> Any:
            del request
            return _output().model_dump(mode="json")

    assert run_parser_adapter(MappingAdapter(), _request()) == _output()
