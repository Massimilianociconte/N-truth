"""Contratti del report positivo e non certificante introdotto dal PRD v3."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ntruth.ingest.project import Project
from ntruth.pipeline import analyze_project
from ntruth.reporting import render_html, write_all

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
    assert {statement.layer.value for statement in output.statements} >= {"fact", "inference"}
    assert output.n_table
    assert all(row.scope for row in output.n_table)


def test_positive_methods_output_is_bilingual_and_does_not_choose_a_model(
    make_project: ProjectFactory,
) -> None:
    result = analyze_project(make_project({"methods.md": METHODS}), lang="en")
    output = result.report.positive_outputs[result.report.blocks[0].id]

    assert output.methods_statement.language == "en"
    assert "candidate experimental unit" in output.methods_statement.text
    prohibited = ("lmer(", "anova(", "t-test", "power =", "~ treatment")
    materialized = json.dumps(output.model_dump(mode="json"), ensure_ascii=False).casefold()
    assert not any(token.casefold() in materialized for token in prohibited)


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
    assert "Fatti, inferenze, ipotesi e limiti" in rendered
