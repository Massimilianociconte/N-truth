from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from ntruth.parser_ai import (
    CandidateContrast,
    CandidateEdge,
    CandidateEndpoint,
    CandidateEstimand,
    CandidateExperimentBlock,
    CandidateFactor,
    CandidateGraphSet,
    CandidateNode,
    ChunkCoverageRecord,
    DocumentRouteKind,
    DocumentRouteRecord,
    DocumentRouteResult,
    EntityCountResult,
    EvidenceExtractionResult,
    HumanRevisionPatch,
    JsonPatchOperation,
    NodeOntologyValue,
    ParserAIDocumentInput,
    ParserAIEvidenceSpan,
    ParserAIInput,
    ParserAISectionInput,
    ProceduralEventResult,
    QuestionRecord,
    QuestionScenario,
    RelationOntologyValue,
    ReportBundle,
    RuleResult,
    StageAuthority,
    StageError,
    StageErrorCode,
    StageName,
    StageProvenance,
    StageStatus,
    StageWarning,
    StageWarningCode,
    VerificationCheck,
    VerificationStatus,
    VerifierKind,
    VerifierResult,
    parser_stage_json_schemas,
    validate_candidate_graph_pair,
)
from ntruth.schemas.core import EvidenceType
from ntruth.schemas.graph import NodeType, RelationType
from ntruth.training import GoldParserTarget, SubmissionComparison


def _provenance(
    stage: StageName,
    *,
    authority: StageAuthority = StageAuthority.DETERMINISTIC,
) -> StageProvenance:
    return StageProvenance(
        stage_run_id=f"run-{stage.value}",
        stage=stage,
        authority=authority,
        producer="ntruth-test",
        producer_version="1.0.0",
    )


def _common(stage: StageName) -> dict[str, object]:
    return {
        "result_id": f"result-{stage.value}",
        "status": StageStatus.COMPLETE,
        "provenance": _provenance(stage),
    }


def _complete_stage_factories() -> tuple[Callable[[], object], ...]:
    return (
        lambda: DocumentRouteResult(
            **_common(StageName.DOCUMENT_ROUTE),
            routes=(
                DocumentRouteRecord(
                    file_id="file-1",
                    route=DocumentRouteKind.TEXT,
                    parser_id="plain-text",
                    supported=True,
                ),
            ),
        ),
        lambda: EvidenceExtractionResult(**_common(StageName.EVIDENCE_EXTRACTION)),
        lambda: EntityCountResult(**_common(StageName.ENTITY_COUNT)),
        lambda: ProceduralEventResult(**_common(StageName.PROCEDURAL_EVENT)),
        lambda: CandidateGraphSet(
            **_common(StageName.CANDIDATE_GRAPH_SET), graph_set_id="graph-set-1"
        ),
        lambda: VerifierResult(
            **_common(StageName.VERIFIER),
            graph_set_id="graph-set-1",
            checks=(
                VerificationCheck(
                    check_id="schema",
                    kind=VerifierKind.HARD,
                    status=VerificationStatus.PASS,
                    code="JSON_SCHEMA_VALID",
                    message="schema valido",
                ),
            ),
            hard_verifier_passed=True,
        ),
        lambda: HumanRevisionPatch(
            **{
                **_common(StageName.HUMAN_REVISION_PATCH),
                "provenance": _provenance(
                    StageName.HUMAN_REVISION_PATCH, authority=StageAuthority.USER
                ),
            },
            patch_id="patch-1",
            target_graph_set_id="graph-set-1",
            base_checksum="a" * 64,
            operations=(
                JsonPatchOperation(op="replace", path="/factors/0/name", value="treatment"),
            ),
            rationale="Correzione verificata sulla fonte.",
        ),
        lambda: RuleResult(
            **_common(StageName.RULE_RESULT),
            graph_set_id="graph-set-1",
            ruleset_id="ntruth-core",
            ruleset_version="1.0.0",
        ),
        lambda: QuestionRecord(
            **_common(StageName.QUESTION_RECORD),
            question_id="question-1",
            block_id="block-1",
            missing_predicate="factor.independently_assigned",
            text="Le preparazioni erano indipendenti?",
            scenarios=(
                QuestionScenario(
                    scenario_id="yes",
                    condition="preparazioni indipendenti",
                    changed_output_fields=("independent_n",),
                ),
                QuestionScenario(
                    scenario_id="no",
                    condition="preparazione condivisa",
                    changed_output_fields=("experimental_unit", "independent_n"),
                ),
            ),
        ),
        lambda: ReportBundle(
            **_common(StageName.REPORT_BUNDLE),
            report_id="report-1",
            graph_set_id="graph-set-1",
        ),
    )


def test_all_ten_stage_contracts_share_the_versioned_envelope() -> None:
    stages = tuple(factory() for factory in _complete_stage_factories())

    assert len(stages) == 10
    assert {stage.stage for stage in stages} == set(StageName)
    assert all(stage.schema_version == "1.0.0" for stage in stages)
    assert all(stage.status is StageStatus.COMPLETE for stage in stages)
    assert all(stage.provenance.stage is stage.stage for stage in stages)
    assert all(stage.errors == () and stage.warnings == () for stage in stages)

    schemas = parser_stage_json_schemas()
    assert set(schemas) == {stage.value for stage in StageName}
    assert "determinability" not in schemas["candidate_graph_set"]["properties"]


def test_stage_status_and_typed_issues_are_coherent() -> None:
    error = StageError(
        error_id="error-1",
        code=StageErrorCode.UNSUPPORTED_FORMAT,
        message="formato non supportato",
    )
    warning = StageWarning(
        warning_id="warning-1",
        code=StageWarningCode.DEGRADED_INPUT,
        message="input degradato",
    )

    with pytest.raises(ValidationError, match="status=complete"):
        DocumentRouteResult(
            **_common(StageName.DOCUMENT_ROUTE),
            errors=(error,),
        )
    with pytest.raises(ValidationError, match="status=failed"):
        DocumentRouteResult(**{**_common(StageName.DOCUMENT_ROUTE), "status": StageStatus.FAILED})
    with pytest.raises(ValidationError, match="status=partial"):
        DocumentRouteResult(**{**_common(StageName.DOCUMENT_ROUTE), "status": StageStatus.PARTIAL})

    partial = DocumentRouteResult(
        **{**_common(StageName.DOCUMENT_ROUTE), "status": StageStatus.PARTIAL},
        warnings=(warning,),
    )
    failed = DocumentRouteResult(
        **{**_common(StageName.DOCUMENT_ROUTE), "status": StageStatus.FAILED},
        errors=(error,),
    )
    assert partial.status is StageStatus.PARTIAL
    assert failed.errors[0].code is StageErrorCode.UNSUPPORTED_FORMAT


def test_stage_name_must_match_stage_provenance() -> None:
    with pytest.raises(ValidationError, match=r"provenance\.stage"):
        EvidenceExtractionResult(
            result_id="wrong-stage",
            status=StageStatus.COMPLETE,
            provenance=_provenance(StageName.DOCUMENT_ROUTE),
        )


def test_candidate_parser_contract_forbids_verdict_and_determinability() -> None:
    properties = CandidateGraphSet.model_json_schema()["properties"]
    assert "verdict" not in properties
    assert "determinability" not in properties

    payload = {
        **_common(StageName.CANDIDATE_GRAPH_SET),
        "graph_set_id": "graph-set-1",
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CandidateGraphSet.model_validate({**payload, "verdict": "valid"})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CandidateGraphSet.model_validate({**payload, "determinability": "DETERMINATE"})


def test_candidate_graph_pair_requires_model_authority_and_exact_source_coordinates() -> None:
    parser_input = ParserAIInput(
        documents=(
            ParserAIDocumentInput(
                file_id="file-1",
                filename="methods.txt",
                sha256="a" * 64,
                text="Grounded.",
            ),
        )
    )
    evidence = ParserAIEvidenceSpan(
        evidence_id="evidence-1",
        file_id="file-1",
        evidence_type=EvidenceType.STRUCTURAL_FACT,
        text="Grounded.",
        confidence=0.9,
        start=0,
        end=9,
    )
    graph = CandidateGraphSet(
        **{
            **_common(StageName.CANDIDATE_GRAPH_SET),
            "provenance": StageProvenance(
                stage_run_id="forged-stage",
                stage=StageName.CANDIDATE_GRAPH_SET,
                authority=StageAuthority.MODEL,
                producer="forged-producer",
                producer_version="forged-version",
                input_artifact_ids=("unseen-file",),
                input_checksums={"unseen-file": "b" * 64},
                parent_result_ids=("human-adjudication",),
                actor_role="wet-lab-adjudicator",
            ),
        },
        graph_set_id="graph-set-1",
        source_result_ids=("human-result",),
        evidence_spans=(evidence,),
        chunk_coverage=(
            ChunkCoverageRecord(
                file_id="file-1",
                total_chunks=1,
                processed_chunks=(0,),
            ),
        ),
    )

    validated = validate_candidate_graph_pair(parser_input, graph)
    assert validated is not graph
    assert validated.source_result_ids == ()
    assert validated.provenance.producer == "ntruth-model-candidate-host"
    assert validated.provenance.producer_version == "1.0.0"
    assert validated.provenance.input_artifact_ids == ("file-1",)
    assert validated.provenance.input_checksums == {"file-1": "a" * 64}
    assert validated.provenance.parent_result_ids == ()
    assert validated.provenance.actor_role is None
    with pytest.raises(ValueError, match="coordinate testuali non coincidono"):
        validate_candidate_graph_pair(
            parser_input,
            graph.model_copy(
                update={"evidence_spans": (evidence.model_copy(update={"text": "Invented"}),)}
            ),
        )


def test_chunk_coverage_is_exhaustive_and_bound_to_parser_input() -> None:
    with pytest.raises(ValidationError, match="ogni chunk deve essere classificato"):
        ChunkCoverageRecord(
            file_id="file-1",
            total_chunks=3,
            processed_chunks=(0,),
            failed_chunks=(2,),
        )

    parser_input = ParserAIInput(
        documents=(
            ParserAIDocumentInput(
                file_id="file-1",
                filename="methods.txt",
                sha256="a" * 64,
                text="Grounded.",
            ),
        )
    )
    graph = CandidateGraphSet(
        **{
            **_common(StageName.CANDIDATE_GRAPH_SET),
            "provenance": _provenance(
                StageName.CANDIDATE_GRAPH_SET,
                authority=StageAuthority.MODEL,
            ),
        },
        graph_set_id="graph-set-coverage",
    )
    with pytest.raises(ValueError, match="copertura integrale"):
        validate_candidate_graph_pair(parser_input, graph)

    unknown = graph.model_copy(
        update={
            "chunk_coverage": (
                ChunkCoverageRecord(
                    file_id="unknown-file",
                    total_chunks=1,
                    processed_chunks=(0,),
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="file_id sconosciuti"):
        validate_candidate_graph_pair(parser_input, unknown)
    with pytest.raises(ValueError, match="authority=model"):
        validate_candidate_graph_pair(
            parser_input,
            graph.model_copy(
                update={
                    "provenance": graph.provenance.model_copy(
                        update={"authority": StageAuthority.ADJUDICATION}
                    )
                }
            ),
        )


def _candidate_evidence() -> ParserAIEvidenceSpan:
    return ParserAIEvidenceSpan(
        evidence_id="evidence-1",
        file_id="file-1",
        evidence_type=EvidenceType.STRUCTURAL_FACT,
        text="Grounded.",
        confidence=0.9,
        start=0,
        end=9,
    )


def _candidate_block(block_id: str) -> CandidateExperimentBlock:
    return CandidateExperimentBlock(
        block_id=block_id,
        title=block_id,
        evidence_ids=("evidence-1",),
        confidence=0.9,
    )


def test_candidate_graph_set_rejects_edge_endpoints_from_another_block() -> None:
    nodes = tuple(
        CandidateNode(
            node_id=node_id,
            block_id="block-2",
            node_type=NodeOntologyValue(value=NodeType.ANIMAL),
            label=node_id,
            evidence_ids=("evidence-1",),
            confidence=0.9,
        )
        for node_id in ("node-1", "node-2")
    )
    edge = CandidateEdge(
        edge_id="edge-1",
        block_id="block-1",
        source_id="node-1",
        target_id="node-2",
        relation_type=RelationOntologyValue(value=RelationType.NESTED_IN),
        evidence_ids=("evidence-1",),
        confidence=0.9,
    )

    with pytest.raises(ValidationError, match="edge riferito a nodi di un altro"):
        CandidateGraphSet(
            **_common(StageName.CANDIDATE_GRAPH_SET),
            graph_set_id="graph-set-1",
            experiment_blocks=(_candidate_block("block-1"), _candidate_block("block-2")),
            evidence_spans=(_candidate_evidence(),),
            candidate_nodes=nodes,
            candidate_edges=(edge,),
        )


def _candidate_estimand_graph(estimand: CandidateEstimand) -> CandidateGraphSet:
    factor = CandidateFactor(
        factor_id="factor-1",
        block_id="block-1",
        name="treatment",
        levels=("drug", "vehicle"),
        allocation_level=None,
        application_level=None,
        evidence_ids=("evidence-1",),
        confidence=0.9,
    )
    endpoint = CandidateEndpoint(
        endpoint_id="endpoint-1",
        block_id="block-1",
        name="signal",
        evidence_ids=("evidence-1",),
        confidence=0.9,
    )
    contrast = CandidateContrast(
        contrast_id="contrast-1",
        block_id="block-1",
        factor_ids=("factor-1",),
        compared_levels=("drug", "vehicle"),
        endpoint_ids=("endpoint-1",),
        evidence_ids=("evidence-1",),
        confidence=0.9,
    )
    return CandidateGraphSet(
        **_common(StageName.CANDIDATE_GRAPH_SET),
        graph_set_id="graph-set-1",
        experiment_blocks=(_candidate_block("block-1"),),
        evidence_spans=(_candidate_evidence(),),
        factors=(factor,),
        endpoints=(endpoint,),
        contrasts=(contrast,),
        candidate_estimands=(estimand,),
    )


@pytest.mark.parametrize(
    ("update", "message"),
    (
        ({"factor_ids": ("missing-factor",)}, "factor_id sconosciuti"),
        ({"endpoint_id": "missing-endpoint"}, "endpoint_id sconosciuti"),
        ({"contrast_id": "missing-contrast"}, "contrast_id sconosciuti"),
    ),
)
def test_candidate_graph_set_rejects_dangling_estimand_references(
    update: dict[str, object],
    message: str,
) -> None:
    estimand = CandidateEstimand(
        estimand_id="estimand-1",
        block_id="block-1",
        factor_ids=("factor-1",),
        contrast_id="contrast-1",
        endpoint_id="endpoint-1",
        effect_measure="difference",
        target_population_or_unit="animals",
        generalization_level="animal",
        evidence_ids=("evidence-1",),
        confidence=0.9,
    ).model_copy(update=update)

    with pytest.raises(ValidationError, match=message):
        _candidate_estimand_graph(estimand)


def test_candidate_graph_pair_requires_section_to_belong_to_the_source_file() -> None:
    parser_input = ParserAIInput(
        documents=(
            ParserAIDocumentInput(
                file_id="file-1",
                filename="methods.txt",
                sha256="a" * 64,
                text="Grounded. Other.",
                sections=(
                    ParserAISectionInput(
                        section_id="methods-1",
                        role="methods",
                        title="Methods",
                        start=0,
                        end=9,
                        text="Grounded.",
                    ),
                ),
            ),
        )
    )
    graph = CandidateGraphSet(
        **{
            **_common(StageName.CANDIDATE_GRAPH_SET),
            "provenance": _provenance(
                StageName.CANDIDATE_GRAPH_SET,
                authority=StageAuthority.MODEL,
            ),
        },
        graph_set_id="graph-set-1",
        evidence_spans=(_candidate_evidence().model_copy(update={"section_id": "missing"}),),
        chunk_coverage=(
            ChunkCoverageRecord(
                file_id="file-1",
                total_chunks=1,
                processed_chunks=(0,),
            ),
        ),
    )

    with pytest.raises(ValueError, match="section_id sconosciuto"):
        validate_candidate_graph_pair(parser_input, graph)

    outside_section = graph.model_copy(
        update={
            "evidence_spans": (
                _candidate_evidence().model_copy(
                    update={
                        "section_id": "methods-1",
                        "text": "Other.",
                        "start": 10,
                        "end": 16,
                    }
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="fuori dalla section"):
        validate_candidate_graph_pair(parser_input, outside_section)


def test_verifier_requires_hard_checks_and_consistent_flags() -> None:
    common = _common(StageName.VERIFIER)
    with pytest.raises(ValidationError, match="hard verifier sempre attivo"):
        VerifierResult(
            **common,
            graph_set_id="graph-set-1",
            hard_verifier_passed=False,
        )
    with pytest.raises(ValidationError, match="hard_verifier_passed incoerente"):
        VerifierResult(
            **common,
            graph_set_id="graph-set-1",
            checks=(
                VerificationCheck(
                    check_id="schema",
                    kind=VerifierKind.HARD,
                    status=VerificationStatus.FAIL,
                    code="JSON_SCHEMA_INVALID",
                    message="schema non valido",
                ),
            ),
            hard_verifier_passed=True,
        )


def _gold_graph(*, authority: StageAuthority) -> CandidateGraphSet:
    return CandidateGraphSet(
        **{
            **_common(StageName.CANDIDATE_GRAPH_SET),
            "provenance": StageProvenance(
                stage_run_id="adjudication-stage",
                stage=StageName.CANDIDATE_GRAPH_SET,
                authority=authority,
                producer="adjudication-ui",
                producer_version="6.0",
                input_artifact_ids=("source-file",),
                input_checksums={"source-file": "a" * 64},
                parent_result_ids=("blind-a", "blind-b"),
                actor_role="adjudicator",
            ),
        },
        graph_set_id="adjudicated-graph",
        source_result_ids=("blind-result-a", "blind-result-b"),
    )


def _gold_payload(*, authority: StageAuthority = StageAuthority.ADJUDICATION) -> dict[str, object]:
    return {
        "target_id": "gold-1",
        "source_record_id": "record-1",
        "guideline_version": "1.0.0",
        "adjudication_id": "adj-1",
        "adjudication_rationale": "Risolto il disaccordo usando Methods e sample sheet.",
        "adjudicator_roles": ("wet-lab", "biostatistician"),
        "source_submission_ids": ("submission-a", "submission-b"),
        "comparisons": (
            SubmissionComparison(
                submission_id="submission-a",
                reviewer_role="wet-lab",
                changed_paths=("/factors/0/allocation_level",),
                summary="Allocation corretta usando la procedura.",
            ),
            SubmissionComparison(
                submission_id="submission-b",
                reviewer_role="biostatistician",
                changed_paths=(),
                summary="La submission coincide con il target adjudicato.",
            ),
        ),
        "adjudicated_graph": _gold_graph(authority=authority),
    }


def test_gold_parser_target_is_distinct_complete_and_adjudicated() -> None:
    target = GoldParserTarget(**_gold_payload())

    assert target.adjudicated_graph.provenance.authority is StageAuthority.ADJUDICATION
    assert len(target.checksum()) == 64
    projected = target.model_candidate_graph()
    assert projected.source_result_ids == ()
    assert projected.provenance.input_artifact_ids == ()
    assert projected.provenance.input_checksums == {}
    assert projected.provenance.parent_result_ids == ()
    assert projected.provenance.actor_role is None
    schema = GoldParserTarget.model_json_schema()["properties"]
    assert "determinability" not in schema
    assert "verdict" not in schema

    with pytest.raises(ValidationError, match="authority=adjudication"):
        GoldParserTarget(**_gold_payload(authority=StageAuthority.MODEL))
    with pytest.raises(ValidationError, match="comparisons deve coprire"):
        GoldParserTarget(
            **{
                **_gold_payload(),
                "source_submission_ids": ("submission-a", "submission-c"),
            }
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GoldParserTarget.model_validate({**_gold_payload(), "verdict": "valid"})


def test_human_patch_requires_human_authority_and_valid_json_patch() -> None:
    with pytest.raises(ValidationError, match="authority user o adjudication"):
        HumanRevisionPatch(
            **_common(StageName.HUMAN_REVISION_PATCH),
            patch_id="patch-1",
            target_graph_set_id="graph-set-1",
            base_checksum="a" * 64,
            operations=(JsonPatchOperation(op="remove", path="/factors/0"),),
            rationale="Rimozione verificata.",
        )
    with pytest.raises(ValidationError, match="replace richiede value"):
        JsonPatchOperation(op="replace", path="/factors/0")
