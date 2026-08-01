"""PRD v3: import read-only di codice statistico e candidate silver."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ntruth.ingest.project import Project
from ntruth.parsers.code import CodeParser
from ntruth.parsers.registry import build_document_ir
from ntruth.schemas.core import EvidenceType
from ntruth.schemas.document import EvidenceTier, ParserStatus, StatisticalCodeLanguage


@pytest.mark.parametrize(
    ("filename", "language"),
    [
        ("analysis.R", StatisticalCodeLanguage.R),
        ("analysis.py", StatisticalCodeLanguage.PYTHON),
        ("analysis.Rmd", StatisticalCodeLanguage.R_MARKDOWN),
    ],
)
def test_statistical_code_is_imported_as_read_only_text(
    tmp_path: Path,
    filename: str,
    language: StatisticalCodeLanguage,
) -> None:
    marker = tmp_path / "must-not-exist"
    source = tmp_path / filename
    text = f'open({str(marker)!r}, "w").write("executed")\ngroups = donor\n'
    source.write_text(text, encoding="utf-8")
    project = Project.create(tmp_path / "project", name="code-read-only")

    result = project.add(source)
    ir = build_document_ir(project)

    assert result.accepted
    assert not marker.exists()
    assert len(ir.statistical_code) == 1
    artifact = ir.statistical_code[0]
    assert artifact.language is language
    assert artifact.text == text
    assert artifact.sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert artifact.execution_policy == "never_execute"
    assert ir.texts[artifact.file_id] == text
    # Il codice non diventa Methods e non puo alimentare gli estrattori legacy.
    assert ir.sections == ()
    assert ir.paragraphs == ()
    assert ir.design_text() == []


@pytest.mark.parametrize(
    ("filename", "text", "expected"),
    [
        ("model.R", "fit <- lmer(y ~ treatment + (1 | donor), data=d)\n", "donor"),
        (
            "model.py",
            'fit = sm.MixedLM.from_formula("y ~ treatment", groups=df["subject"], data=df)\n',
            'df["subject"]',
        ),
    ],
)
def test_declared_clustering_is_silver_statistical_code_never_allocation(
    tmp_path: Path,
    filename: str,
    text: str,
    expected: str,
) -> None:
    source = tmp_path / filename
    source.write_text(text, encoding="utf-8")
    project = Project.create(tmp_path / "project", name="clustering")
    project.add(source)

    artifact = build_document_ir(project).statistical_code[0]
    candidate = next(item for item in artifact.candidates if item.cluster_expression == expected)

    assert candidate.evidence_tier is EvidenceTier.SILVER
    assert candidate.source_kind is EvidenceType.STATISTICAL_CODE
    assert candidate.is_allocation is False
    assert artifact.text[candidate.start : candidate.end] == expected
    assert candidate.line_start == candidate.line_end == 1


def test_treatment_assignment_syntax_does_not_create_an_allocation_candidate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "assignment.py"
    source.write_text('treatment = "drug"\nrandomize(subjects)\n', encoding="utf-8")
    project = Project.create(tmp_path / "project", name="no-allocation")
    project.add(source)

    artifact = build_document_ir(project).statistical_code[0]

    assert artifact.candidates == ()


def test_python_union_operator_is_not_misread_as_r_random_effect(tmp_path: Path) -> None:
    source = tmp_path / "types.py"
    source.write_text("Result = Success | Failure\n", encoding="utf-8")
    project = Project.create(tmp_path / "project", name="python-union")
    project.add(source)

    assert build_document_ir(project).statistical_code[0].candidates == ()


def test_binary_code_is_failed_explicitly(tmp_path: Path) -> None:
    source = tmp_path / "binary.py"
    source.write_bytes(b"print('safe')\x00malicious")
    project = Project.create(tmp_path / "project", name="binary")
    project.add(source)

    ir = build_document_ir(project)

    assert ir.files[0].status is ParserStatus.FAILED
    assert "byte NUL" in ir.files[0].warnings[0]
    assert ir.statistical_code == ()


def test_code_parser_supports_extensions_case_insensitively(tmp_path: Path) -> None:
    assert CodeParser().supports(tmp_path / "MODEL.R", "text/x-r-source")
    assert CodeParser().supports(tmp_path / "NOTE.RMD", "text/x-r-markdown")
