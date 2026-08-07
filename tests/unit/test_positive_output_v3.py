"""Contratti del report positivo e non certificante introdotto dal PRD v3."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from ntruth.ingest.project import Project
from ntruth.pipeline import analyze_project
from ntruth.reporting import render_html, write_all
from ntruth.reporting.positive import build_positive_output
from ntruth.schemas.core import Determinability, EvidenceType
from ntruth.schemas.experiment import (
    ConditionalScenario,
    Contradiction,
    CountKind,
    CountQuantifier,
    GraphStatus,
    Inferability,
)
from ntruth.verifier import apply_output_policy, output_policy_violations

METHODS = (
    "Primary neurons were prepared from three independent preparations. "
    "Each preparation was plated into four wells. Cells were treated with drug or "
    "vehicle at the level of the culture. Intensity per cell was quantified; n = 40 cells."
)

ProjectFactory = Callable[..., Project]


def test_positive_output_separates_layers_and_is_non_certifying(
    make_project: ProjectFactory,
) -> None:
    result = analyze_project(make_project({"methods.md": METHODS}))
    block = result.report.blocks[0]
    output = result.report.positive_outputs[block.id]

    assert output.non_certifying is True
    assert output.methods_statement.non_certifying is True
    assert output.methods_statement.text
    assert output.path_status.value == "incomplete"
    compilation = result.report.design_compilations[block.id]
    compiler_decisive = {
        question.id for question in compilation.elicitation.questions if question.decisive
    }
    assert compiler_decisive <= set(output.decisive_question_ids)
    assert len(output.driver_checklist) == 6
    assert {item.item_id for item in output.driver_checklist} == {
        "DRIVER-1",
        "DRIVER-2",
        "DRIVER-3",
        "DRIVER-4",
        "DRIVER-5",
        "DRIVER-6",
    }
    assert all(
        item.source_url.startswith("https://nc3rs.org.uk/") for item in output.driver_checklist
    )
    assert {statement.layer.value for statement in output.statements} >= {
        "assertion",
        "inference",
    }
    assert all(
        statement.layer.value != "fact"
        for statement in output.statements
        if "independent" in statement.text.casefold()
    )
    assert all(
        statement.source == "author_assertion"
        for statement in output.statements
        if "independent" in statement.text.casefold()
    )
    assert output.n_table
    assert all(row.scope for row in output.n_table)


def test_user_confirmation_is_not_misattributed_to_the_author(
    make_project: ProjectFactory,
) -> None:
    result = analyze_project(make_project({"methods.md": METHODS}))
    block = result.report.blocks[0]
    statement = next(item for item in block.n_statements if item.evidence_ids)
    evidence_ids = set(statement.evidence_ids)
    evidence = tuple(
        item.model_copy(update={"evidence_type": EvidenceType.USER_CONFIRMATION})
        if item.id in evidence_ids
        else item
        for item in block.evidence
    )
    confirmed = block.model_copy(update={"evidence": evidence})

    output = build_positive_output(confirmed)
    emitted = next(item for item in output.statements if set(item.evidence_ids) == evidence_ids)

    assert emitted.layer.value == "assertion"
    assert emitted.source == "user_confirmation"


def test_positive_methods_output_is_bilingual_and_does_not_choose_a_model(
    make_project: ProjectFactory,
) -> None:
    result = analyze_project(make_project({"methods.md": METHODS}), lang="en")
    output = result.report.positive_outputs[result.report.blocks[0].id]

    assert output.methods_statement.language == "en"
    assert "Draft not generated" in output.methods_statement.text
    assert result.report.blocks[0].determinability.value == "INSUFFICIENT_INFORMATION"
    prohibited = ("lmer(", "anova(", "t-test", "power =", "~ treatment")
    materialized = json.dumps(output.model_dump(mode="json"), ensure_ascii=False).casefold()
    assert not any(token.casefold() in materialized for token in prohibited)


def test_effective_n_remains_outside_the_primary_count_table(
    make_project: ProjectFactory,
) -> None:
    result = analyze_project(make_project({"methods.md": METHODS}))
    assessment = result.block.unit_assessments[0].model_copy(update={"effective_n": 2.5})
    source_count = result.block.count_records[0]
    diagnostic = source_count.model_copy(
        update={
            "count_id": "diagnostic-effective-n",
            "kind": CountKind.EFFECTIVE_N,
            "value": 2.5,
            "quantifier": CountQuantifier.EXACT,
            "lower_bound": None,
            "upper_bound": None,
            "diagnostic_only": True,
        }
    )
    block = result.block.model_copy(
        update={
            "determinability": Determinability.DETERMINATE,
            "unit_assessments": (assessment,),
            "count_records": (*result.block.count_records, diagnostic),
        }
    )

    assert "effective_n_must_use_diagnostic_register" in {
        item.code for item in output_policy_violations(block)
    }
    projected = apply_output_policy(block)
    output = build_positive_output(projected)
    report = result.report.model_copy(
        update={
            "blocks": (projected,),
            "positive_outputs": {projected.id: output},
        }
    )
    rendered = render_html(report)

    assert projected.unit_assessments[0].effective_n is None
    assert output.n_table[0].effective_n is None
    assert diagnostic.count_id not in {item.count_id for item in output.count_records}
    assert [item.count_id for item in output.diagnostic_count_records] == [diagnostic.count_id]
    assert "Diagnostica statistica separata — non replication" in rendered
    assert "effective_n" in rendered


def test_html_renders_both_conditional_scenario_branches(
    make_project: ProjectFactory,
) -> None:
    result = analyze_project(make_project({"methods.md": METHODS}))
    block = result.report.blocks[0]
    scenario = ConditionalScenario(
        conditional_on="preparations_are_independent",
        if_confirmed={"drug": 3, "vehicle": 3},
        if_rejected={"drug": 1, "vehicle": 1},
        question="Le tre preparazioni sono state generate indipendentemente?",
        rule_id="TEST-CONDITIONAL",
        evidence_ids=block.unit_assessments[0].evidence_ids,
    )
    assessment = block.unit_assessments[0].model_copy(
        update={
            "experimental_unit": None,
            "n_independent": None,
            "inferability": Inferability.CONDITIONAL,
            "conditional_scenarios": (scenario,),
        }
    )
    conditional = block.model_copy(
        update={
            "determinability": Determinability.CONDITIONALLY_DETERMINATE,
            "graph_status": GraphStatus.CONDITIONAL,
            "unit_assessments": (assessment,),
        }
    )
    report = result.report.model_copy(
        update={
            "blocks": (conditional,),
            "positive_outputs": {conditional.id: build_positive_output(conditional)},
        }
    )

    rendered = render_html(report)

    assert "Scenari condizionali if/then (1)" in rendered
    assert "preparations_are_independent" in rendered
    assert "Le tre preparazioni sono state generate indipendentemente?" in rendered
    assert "drug=3" in rendered and "vehicle=3" in rendered
    assert "drug=1" in rendered and "vehicle=1" in rendered
    assert "TEST-CONDITIONAL" in rendered


def test_unresolved_conflict_requires_lineage_and_html_retains_both_interpretations(
    make_project: ProjectFactory,
) -> None:
    with pytest.raises(ValueError, match="statement/evidence"):
        Contradiction(
            id="untraceable",
            description="fonti incompatibili",
            retained_interpretations=("interpretazione A", "interpretazione B"),
        )

    result = analyze_project(make_project({"methods.md": METHODS}))
    block = result.report.blocks[0]
    evidence_id = block.evidence[0].id
    conflict = Contradiction(
        id="conflict-visible",
        description="Due fonti primarie riportano conteggi incompatibili.",
        evidence_ids=(evidence_id,),
        retained_interpretations=("n per gruppo = 3", "n per gruppo = 1"),
    )
    conflicting = block.model_copy(
        update={
            "determinability": Determinability.CONFLICTING_INFORMATION,
            "contradictions": (conflict,),
        }
    )
    report = result.report.model_copy(
        update={
            "blocks": (conflicting,),
            "positive_outputs": {conflicting.id: build_positive_output(conflicting)},
        }
    )

    rendered = render_html(report)

    assert "Due fonti primarie riportano conteggi incompatibili." in rendered
    assert "n per gruppo = 3" in rendered
    assert "n per gruppo = 1" in rendered
    assert block.evidence[0].locator() in rendered


def test_write_all_includes_logically_identical_json_and_yaml(
    make_project: ProjectFactory,
    tmp_path: Path,
) -> None:
    result = analyze_project(make_project({"methods.md": METHODS}))
    written = write_all(result.report, tmp_path / "out")

    assert "yaml" in written
    assert json.loads(written["yaml"].read_text(encoding="utf-8")) == json.loads(
        written["json"].read_text(encoding="utf-8")
    )
    rendered = render_html(result.report)
    assert "Percorso positivo e bozza Methods" in rendered
    assert "Fattori, allocazione e applicazione" in rendered
    assert "Allocation level" in rendered
    assert "Application level" in rendered
    assert "Checklist DRIVER informativa" in rendered
    assert "Fatti, asserzioni, inferenze, ipotesi e limiti" in rendered
