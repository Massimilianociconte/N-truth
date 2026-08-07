"""Regressioni v3 per oggetti inferenziali e determinabilita."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ntruth.design import compile_experiment_block
from ntruth.graph.builder import materialize_inferential_graph
from ntruth.graph.determinability import derive_determinability
from ntruth.graph.validation import validate_experiment_block
from ntruth.pipeline import _supported_by_release_profile
from ntruth.reporting import render_html
from ntruth.reporting.positive import build_positive_output
from ntruth.schemas.core import (
    Determinability,
    EvidenceSpan,
    EvidenceType,
    Provenance,
    ProvenanceKind,
    Severity,
)
from ntruth.schemas.experiment import (
    Alert,
    ConditionalScenario,
    Contradiction,
    Contrast,
    Endpoint,
    Estimand,
    ExperimentBlock,
    Factor,
    GraphAlternativeConsequence,
    GraphStatus,
    Hierarchy,
    Inferability,
    InferenceTarget,
    InferenceTargetStatus,
    NScope,
    PlausibleGraphAlternative,
    PlausibleGraphSet,
    Question,
    TriState,
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import GraphNode, NodeType
from ntruth.schemas.manifest import ReleaseProfile
from ntruth.schemas.report import Report
from ntruth.verifier import apply_output_policy, output_policy_violations, verify_block


def _provenance(origin: ProvenanceKind = ProvenanceKind.USER) -> Provenance:
    if origin in {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION}:
        return Provenance(
            origin=origin,
            actor_role="researcher",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            correction_id="test-correction",
        )
    if origin is ProvenanceKind.DERIVED:
        return Provenance(origin=origin, derivation="deterministic test fixture")
    return Provenance(origin=origin)


def _versions() -> Versions:
    return Versions(
        schema_version="0.3.0",
        parser_version="0.3.0",
        graph_version="0.3.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.1.0",
    )


def _complete_block() -> ExperimentBlock:
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("control", "drug"),
        allocation_level=NodeType.ANIMAL,
        application_level=NodeType.ANIMAL,
        allocation_confidence=1.0,
        application_confidence=1.0,
        allocation_evidence_ids=("evidence-allocation",),
        independence_evidence_ids=("evidence-allocation",),
        independently_assigned=TriState.TRUE,
        independence_mechanism="four distinct animals received one allocated level each",
        provenance=_provenance(),
    )
    endpoint = Endpoint(
        id="endpoint-weight",
        name="body weight",
        measured_on=NodeType.ANIMAL,
        provenance=_provenance(),
    )
    contrast = Contrast(
        id="contrast-drug-control",
        label="drug vs control",
        factor_ids=(factor.id,),
        compared_levels=("drug", "control"),
        endpoint_ids=(endpoint.id,),
        provenance=_provenance(),
    )
    target = InferenceTarget(
        id="target-animals",
        question_text="Qual e l'effetto del farmaco sul peso?",
        population_of_inference="animali nelle condizioni dichiarate",
        factor_ids=(factor.id,),
        contrast_ids=(contrast.id,),
        endpoint_ids=(endpoint.id,),
        target_biological_unit=NodeType.ANIMAL,
        provenance=_provenance(),
        status=InferenceTargetStatus.USER_CONFIRMED,
    )
    estimand = Estimand(
        id="estimand-weight",
        endpoint_id=endpoint.id,
        effect_measure="mean difference",
        target_population_or_unit="animali nelle condizioni dichiarate",
        generalization_level="animal",
        factor_ids=(factor.id,),
        provenance=_provenance(),
    )
    animal = GraphNode(
        id="animal",
        type=NodeType.ANIMAL,
        label="animals",
        count=4,
        provenance=_provenance(),
    )
    hierarchy = materialize_inferential_graph(
        Hierarchy(nodes=(animal,)),
        block_id="block-v3",
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
        evidence_ids=("evidence-allocation",),
        provenance=_provenance(ProvenanceKind.DERIVED),
    )
    return ExperimentBlock(
        id="block-v3",
        document_id="document-v3",
        inference_targets=(target,),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        estimands=(estimand,),
        hierarchy=hierarchy,
        unit_assessments=(assessment,),
        evidence=(
            EvidenceSpan(
                id="evidence-allocation",
                file_id="user-wizard",
                text="Four distinct animals were allocated independently.",
                evidence_type=EvidenceType.USER_CONFIRMATION,
            ),
        ),
        versions=_versions(),
    )


def _with_plausible_graphs(block: ExperimentBlock) -> ExperimentBlock:
    evidence_ids = ("evidence-allocation",)
    traced = Provenance(
        origin=ProvenanceKind.USER,
        evidence_ids=evidence_ids,
        actor_role="researcher",
    )
    question = Question(
        id="question-discriminate-graphs",
        text="L'allocazione avveniva sui singoli animali o sulle gabbie?",
        reason="La risposta distingue due strutture di indipendenza compatibili.",
        scope=block.unit_assessments[0].scope,
        priority=100,
        decisive=True,
        impact="Determina unita sperimentale e n per gruppo.",
    )
    animal_consequence = GraphAlternativeConsequence(
        id="consequence-animal",
        scope=block.unit_assessments[0].scope,
        description="Ogni animale e una unita sperimentale indipendente.",
        experimental_unit=NodeType.ANIMAL,
        n_independent_by_group={"control": 2, "drug": 2},
        evidence_ids=evidence_ids,
        provenance=traced,
    )
    cage_consequence = GraphAlternativeConsequence(
        id="consequence-cage",
        scope=block.unit_assessments[0].scope,
        description="Gli animali condividono l'assegnazione a livello di gabbia.",
        experimental_unit=NodeType.CAGE,
        n_independent_by_group={"control": 1, "drug": 1},
        evidence_ids=evidence_ids,
        provenance=traced,
    )
    cage_node = GraphNode(
        id="cage",
        type=NodeType.CAGE,
        label="cages",
        count=2,
        evidence_ids=evidence_ids,
        provenance=traced,
    )
    alternatives = (
        PlausibleGraphAlternative(
            id="alternative-animal",
            label="Allocazione per animale",
            hierarchy=block.hierarchy,
            consequences=(animal_consequence,),
            evidence_ids=evidence_ids,
            provenance=traced,
        ),
        PlausibleGraphAlternative(
            id="alternative-cage",
            label="Allocazione per gabbia",
            hierarchy=Hierarchy(
                nodes=(*block.hierarchy.nodes, cage_node),
                relations=block.hierarchy.relations,
            ),
            consequences=(cage_consequence,),
            evidence_ids=evidence_ids,
            provenance=traced,
        ),
    )
    graph_set = PlausibleGraphSet(
        id="plausible-graph-set",
        alternatives=alternatives,
        discriminating_question_id=question.id,
        evidence_ids=evidence_ids,
        provenance=traced,
    )
    return block.model_copy(
        update={
            "graph_status": GraphStatus.CONDITIONAL,
            "plausible_graph_set": graph_set,
            "questions": (*block.questions, question),
        }
    )


def test_inference_target_and_estimand_are_idempotent_formal_graph_nodes() -> None:
    block = _complete_block()
    synchronized = materialize_inferential_graph(
        block.hierarchy,
        block_id=block.id,
        inference_targets=block.inference_targets,
        estimands=block.estimands,
    )
    assert synchronized == block.hierarchy
    assert {node.type for node in synchronized.nodes} >= {
        NodeType.EXPERIMENT_BLOCK,
        NodeType.INFERENCE_TARGET,
        NodeType.ESTIMAND,
    }
    codes = {item.code for item in validate_experiment_block(block)}
    assert "missing_inference_target_node" not in codes
    assert "missing_estimand_node" not in codes


def test_missing_inferential_graph_nodes_are_visible_until_recalculation() -> None:
    block = _complete_block().model_copy(
        update={
            "hierarchy": Hierarchy(
                nodes=tuple(
                    node
                    for node in _complete_block().hierarchy.nodes
                    if node.type not in {NodeType.INFERENCE_TARGET, NodeType.ESTIMAND}
                )
            )
        }
    )
    violations = validate_experiment_block(block)
    codes = {item.code for item in violations}
    assert {"missing_inference_target_node", "missing_estimand_node"} <= codes
    assert all(
        not item.blocking
        for item in violations
        if item.code in {"missing_inference_target_node", "missing_estimand_node"}
    )


def test_determinability_is_derived_from_conflicts_alternatives_and_completeness() -> None:
    block = _complete_block()
    compilation = compile_experiment_block(block)
    assert compilation.abstained is False
    assert derive_determinability(block, compilation) is Determinability.DETERMINATE

    scenario = ConditionalScenario(
        conditional_on="animals_are_independent",
        if_confirmed={"drug": 2, "control": 2},
        if_rejected={"drug": 1, "control": 1},
        question="Gli animali sono unita indipendenti?",
        rule_id="V3-TEST",
    )
    conditional_assessment = block.unit_assessments[0].model_copy(
        update={
            "n_independent": None,
            "inferability": Inferability.CONDITIONAL,
            "conditional_scenarios": (scenario,),
        }
    )
    conditional = block.model_copy(update={"unit_assessments": (conditional_assessment,)})
    assert (
        derive_determinability(conditional, compile_experiment_block(conditional))
        is Determinability.CONDITIONALLY_DETERMINATE
    )

    conflicting = block.model_copy(
        update={
            "contradictions": (
                Contradiction(
                    id="conflict",
                    description="fonti incompatibili",
                    retained_interpretations=("fonte A", "fonte B"),
                    provenance=Provenance(
                        origin=ProvenanceKind.USER,
                        actor_role="test_reviewer",
                    ),
                ),
            )
        }
    )
    assert (
        derive_determinability(conflicting, compile_experiment_block(conflicting))
        is Determinability.CONFLICTING_INFORMATION
    )

    incomplete = ExperimentBlock(
        id="incomplete",
        document_id="document-incomplete",
        versions=_versions(),
    )
    assert (
        derive_determinability(incomplete, compile_experiment_block(incomplete))
        is Determinability.INSUFFICIENT_INFORMATION
    )


def test_requires_confirmation_without_alternative_graphs_is_insufficient() -> None:
    block = _complete_block()
    requires_confirmation = block.unit_assessments[0].model_copy(
        update={
            "n_independent": None,
            "inferability": Inferability.REQUIRES_CONFIRMATION,
            "conditional_scenarios": (),
        }
    )
    unresolved = block.model_copy(
        update={
            "graph_status": GraphStatus.CANDIDATE,
            "unit_assessments": (requires_confirmation,),
        }
    )

    assert (
        derive_determinability(unresolved, compile_experiment_block(unresolved))
        is Determinability.INSUFFICIENT_INFORMATION
    )

    marker_only = unresolved.model_copy(update={"graph_status": GraphStatus.CONDITIONAL})
    assert (
        derive_determinability(marker_only, compile_experiment_block(marker_only))
        is Determinability.INSUFFICIENT_INFORMATION
    )


def test_alternative_graph_validation_is_fail_closed() -> None:
    multiple = _with_plausible_graphs(_complete_block())
    assert not {item.code for item in validate_experiment_block(multiple) if item.blocking}

    graph_set = multiple.plausible_graph_set
    assert graph_set is not None
    dangling = multiple.model_copy(
        update={
            "plausible_graph_set": graph_set.model_copy(
                update={"discriminating_question_id": "missing-question"}
            )
        }
    )
    codes = {item.code for item in validate_experiment_block(dangling)}
    assert "dangling_alternative_graph_question" in codes
    assert (
        derive_determinability(dangling, compile_experiment_block(dangling))
        is Determinability.INVALID_GRAPH
    )

    first = graph_set.alternatives[0]
    paraphrased_consequence = first.consequences[0].model_copy(
        update={
            "id": "paraphrased-consequence",
            "description": "Interpretazione riscritta, con lo stesso contenuto strutturato.",
        }
    )
    paraphrased_alternative = first.model_copy(
        update={
            "id": "paraphrased-alternative",
            "label": "Label diversa",
            "consequences": (paraphrased_consequence,),
        }
    )
    with pytest.raises(ValueError, match="scientificamente duplicate"):
        PlausibleGraphSet(
            id="duplicate-set",
            alternatives=(first, paraphrased_alternative),
            discriminating_question_id=graph_set.discriminating_question_id,
            evidence_ids=graph_set.evidence_ids,
            provenance=graph_set.provenance,
        )


def test_positive_json_and_html_retain_every_graph_without_forced_choice() -> None:
    source = _with_plausible_graphs(_complete_block())
    state = derive_determinability(source, compile_experiment_block(source))
    assert state is Determinability.MULTIPLE_PLAUSIBLE_GRAPHS
    block = apply_output_policy(source.model_copy(update={"determinability": state}))
    output = build_positive_output(block)
    payload = output.model_dump(mode="json")

    assert payload["determinability"] == "MULTIPLE_PLAUSIBLE_GRAPHS"
    assert payload["discriminating_question"]["id"] == "question-discriminate-graphs"
    assert len(payload["plausible_graph_set"]["alternatives"]) == 2
    assert {
        item["consequences"][0]["experimental_unit"]
        for item in payload["plausible_graph_set"]["alternatives"]
    } == {"Animal", "Cage"}
    assert "selected_alternative" not in payload["plausible_graph_set"]
    assert all(row["n_independent"] is None for row in payload["n_table"])

    report = Report(
        report_id="report-multiple",
        project_id="project-multiple",
        project_name="Multiple graph regression",
        versions=_versions(),
        blocks=(block,),
        positive_outputs={block.id: output},
    )
    rendered = render_html(report)
    assert "Grafi alternativi plausibili (2)" in rendered
    assert "Nessuna alternativa e selezionata automaticamente." in rendered
    assert "Allocazione per animale" in rendered
    assert "Allocazione per gabbia" in rendered
    assert "control=2" in rendered and "control=1" in rendered
    assert "L&#39;allocazione avveniva sui singoli animali o sulle gabbie?" in rendered


def test_extended_input_profile_does_not_expand_the_d0_scientific_scope() -> None:
    animal_block = _complete_block()

    for release_profile in ReleaseProfile:
        supported = _supported_by_release_profile(animal_block, release_profile)
        assert supported is False
        assert (
            derive_determinability(
                animal_block,
                compile_experiment_block(animal_block),
                supported_profile=supported,
            )
            is Determinability.OUT_OF_SCOPE
        )


def test_all_seven_v6_states_are_reachable_and_gate_single_outputs() -> None:
    complete = _complete_block()
    multiple = _with_plausible_graphs(complete)
    scenario = ConditionalScenario(
        conditional_on="preparations_are_independent",
        if_confirmed={"per_group": 4},
        if_rejected={"per_group": 1},
        question="Le preparazioni erano indipendenti?",
        rule_id="V6-STATE-TEST",
    )
    conditional_assessment = complete.unit_assessments[0].model_copy(
        update={
            "n_independent": None,
            "inferability": Inferability.CONDITIONAL,
            "conditional_scenarios": (scenario,),
        }
    )
    cases = {
        Determinability.DETERMINATE: complete,
        Determinability.CONDITIONALLY_DETERMINATE: complete.model_copy(
            update={"unit_assessments": (conditional_assessment,)}
        ),
        Determinability.MULTIPLE_PLAUSIBLE_GRAPHS: multiple,
        Determinability.INSUFFICIENT_INFORMATION: ExperimentBlock(
            id="insufficient-v6",
            document_id="document-insufficient-v6",
            versions=_versions(),
        ),
        Determinability.CONFLICTING_INFORMATION: complete.model_copy(
            update={
                "contradictions": (
                    Contradiction(
                        id="conflict-v6",
                        description="fonti incompatibili",
                        retained_interpretations=("fonte A", "fonte B"),
                        provenance=Provenance(
                            origin=ProvenanceKind.USER,
                            actor_role="test_reviewer",
                        ),
                    ),
                )
            }
        ),
        Determinability.INVALID_GRAPH: complete.model_copy(
            update={"graph_status": GraphStatus.INVALID}
        ),
        Determinability.OUT_OF_SCOPE: complete,
    }
    decisive_alert = Alert(
        id="alert-single-output-v6",
        rule_id="GEN-001",
        ruleset_version="0.2.0",
        severity=Severity.INFO,
        message="Il livello Well e l'unita candidata; n indipendente = 4.",
        missing_information=("synthetic_output_policy_fixture",),
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            rule_id="GEN-001",
            ruleset_version="0.2.0",
            derivation="fixture per la proiezione degli alert",
        ),
    )
    pseudobulk_alert = Alert(
        id="alert-pseudobulk-single-output-v6",
        rule_id="SC-002",
        ruleset_version="0.2.0",
        severity=Severity.INFO,
        message=(
            "L'aggregazione pseudobulk preserva il livello indipendente e il numero "
            "di unita resta quello dei soggetti."
        ),
        missing_information=("synthetic_output_policy_fixture",),
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            rule_id="SC-002",
            ruleset_version="0.2.0",
            derivation="fixture pseudobulk per la proiezione degli alert",
        ),
    )

    observed: set[Determinability] = set()
    for expected, source in cases.items():
        source = source.model_copy(
            update={"alerts": (*source.alerts, decisive_alert, pseudobulk_alert)}
        )
        state = derive_determinability(
            source,
            compile_experiment_block(source),
            supported_profile=expected is not Determinability.OUT_OF_SCOPE,
        )
        observed.add(state)
        assert state is expected

        stateful = source.model_copy(update={"determinability": state})
        projected = apply_output_policy(stateful)
        assert output_policy_violations(projected) == ()
        if state is Determinability.DETERMINATE:
            assert projected.unit_assessments[0].n_independent == 4
            assert {item.id for item in projected.alerts} >= {
                decisive_alert.id,
                pseudobulk_alert.id,
            }
        elif projected.unit_assessments:
            assert all(item.n_independent is None for item in projected.unit_assessments)
            if state is Determinability.CONDITIONALLY_DETERMINATE:
                assert projected.unit_assessments[0].conditional_scenarios == (scenario,)
            else:
                assert all(not item.conditional_scenarios for item in projected.unit_assessments)
        if state is not Determinability.DETERMINATE:
            assert {decisive_alert.id, pseudobulk_alert.id}.isdisjoint(
                item.id for item in projected.alerts
            )

    assert observed == set(Determinability)


def test_output_validator_rejects_every_scalar_field_removed_by_projection() -> None:
    complete = _complete_block()
    unsafe_assessment = complete.unit_assessments[0].model_copy(
        update={"effective_n": 2.5, "independent_entity_type": "animal"}
    )
    unsafe = complete.model_copy(
        update={
            "determinability": Determinability.INSUFFICIENT_INFORMATION,
            "unit_assessments": (unsafe_assessment,),
        }
    )

    assert {item.code for item in output_policy_violations(unsafe)} == {
        "effective_n_must_use_diagnostic_register",
        "independent_entity_forbidden_by_state",
        "single_experimental_unit_forbidden_by_state",
        "single_n_forbidden_by_state",
    }
    projected = apply_output_policy(unsafe)
    assert output_policy_violations(projected) == ()


def test_public_alert_filter_cannot_be_bypassed_by_a_forged_withheld_marker() -> None:
    leaked = Alert(
        id="forged-alert-output-leak",
        rule_id="GEN-001",
        ruleset_version="0.2.0",
        severity=Severity.INFO,
        message="Well is the experimental unit; independent n = 2.",
        missing_information=("output_withheld_by_determinability:INSUFFICIENT_INFORMATION",),
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            rule_id="GEN-001",
            ruleset_version="0.2.0",
            derivation="fixture di tampering sul public block",
        ),
    )
    block = _complete_block().model_copy(
        update={
            "determinability": Determinability.INSUFFICIENT_INFORMATION,
            "alerts": (leaked,),
        }
    )

    assert "decisive_alert_forbidden_by_state" in {
        item.code for item in output_policy_violations(block)
    }
    assert "decisive_alert_forbidden_by_state" in {
        item.code for item in verify_block(block).violations
    }
    projected = apply_output_policy(block)
    assert projected.alerts == ()


@pytest.mark.parametrize(
    "message",
    (
        "Well is the experimental unit; independent n = 7.",
        "Well e l'unita sperimentale; n indipendente = 7.",
        "Template locale: experimental_unit=Well; n_independent=7.",
    ),
)
def test_unknown_local_rule_cannot_publish_decisive_text_outside_determinate(
    message: str,
) -> None:
    custom_alert = Alert(
        id="custom-alert-output-leak",
        rule_id="LOC-001",
        ruleset_version="local-1.0.0",
        severity=Severity.INFO,
        message=message,
        missing_information=("custom-rule-output-policy-fixture",),
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            rule_id="LOC-001",
            ruleset_version="local-1.0.0",
            derivation="fixture di ruleset locale non classificato",
        ),
    )
    block = _complete_block().model_copy(
        update={
            "determinability": Determinability.INSUFFICIENT_INFORMATION,
            "alerts": (custom_alert,),
        }
    )

    assert "decisive_alert_forbidden_by_state" in {
        item.code for item in output_policy_violations(block)
    }
    assert apply_output_policy(block).alerts == ()


def test_output_validator_rejects_vacuous_determinability_states() -> None:
    empty = ExperimentBlock(id="empty-state", document_id="document", versions=_versions())
    cases = {
        Determinability.DETERMINATE: "determinate_without_assessments",
        Determinability.CONDITIONALLY_DETERMINATE: "conditional_without_assessments",
        Determinability.CONFLICTING_INFORMATION: "conflicting_state_without_conflict",
        Determinability.MULTIPLE_PLAUSIBLE_GRAPHS: (
            "multiple_graph_state_without_materialized_alternatives"
        ),
    }

    for state, expected_code in cases.items():
        candidate = empty.model_copy(update={"determinability": state})
        assert expected_code in {item.code for item in output_policy_violations(candidate)}


def test_human_confirmation_in_one_scope_does_not_legitimize_author_assertion_in_another() -> None:
    block = _complete_block()
    asserted_factor = block.factors[0].model_copy(
        update={
            "provenance": Provenance(
                origin=ProvenanceKind.EXPLICIT,
                evidence_ids=("evidence-allocation",),
            )
        }
    )
    asserted_assessment = block.unit_assessments[0].model_copy(
        update={
            "provenance": Provenance(
                origin=ProvenanceKind.DERIVED,
                evidence_ids=("evidence-allocation",),
                derivation="candidate from author assertion",
            )
        }
    )
    human_factor = block.factors[0].model_copy(update={"id": "factor-human-confirmed"})
    human_assessment = block.unit_assessments[0].model_copy(
        update={
            "id": "assessment-human-confirmed",
            "scope": block.unit_assessments[0].scope.model_copy(
                update={"factor_id": human_factor.id}
            ),
            "provenance": _provenance(),
        }
    )
    contrast = block.contrasts[0].model_copy(
        update={"factor_ids": (asserted_factor.id, human_factor.id)}
    )
    target = block.inference_targets[0].model_copy(
        update={"factor_ids": (asserted_factor.id, human_factor.id)}
    )
    estimand = block.estimands[0].model_copy(
        update={"factor_ids": (asserted_factor.id, human_factor.id)}
    )
    mixed = block.model_copy(
        update={
            "factors": (asserted_factor, human_factor),
            "contrasts": (contrast,),
            "inference_targets": (target,),
            "estimands": (estimand,),
            "unit_assessments": (asserted_assessment, human_assessment),
            "evidence": (
                block.evidence[0].model_copy(
                    update={"evidence_type": EvidenceType.AUTHOR_ASSERTION}
                ),
            ),
        }
    )

    assert (
        derive_determinability(mixed, compile_experiment_block(mixed))
        is Determinability.INSUFFICIENT_INFORMATION
    )
