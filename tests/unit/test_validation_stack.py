"""Validation stack: sintassi ≠ ricostruzione scientifica."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.core import EvidenceType
from ntruth.verifier import (
    AUTHOR_ASSERTION_ALONE_CODE,
    LayerOutcome,
    ValidationLayer,
    ValidationStackReport,
    build_validation_stack_report,
    evidence_support_from_types,
)
from ntruth.verifier.validation_stack import EVIDENCE_SUPPORT_EMPTY_CODE


def test_syntax_only_is_never_scientifically_acceptable() -> None:
    report = build_validation_stack_report(
        schema_valid=False,
        hard_verifier_passed=False,
        grammar_constrained_ok=True,
        json_schema_ok=True,
        referentially_valid=False,
        human_confirmed_decisive=False,
        require_human_confirmation=True,
    )

    assert report.syntax_valid is True
    assert report.schema_valid is False
    assert report.scientifically_acceptable is False
    assert report.semantically_reviewed is False
    grammar = next(
        item for item in report.layers if item.layer is ValidationLayer.GRAMMAR_CONSTRAINED
    )
    assert grammar.outcome is LayerOutcome.PASS


def test_hard_fail_blocks_scientific_acceptability() -> None:
    report = build_validation_stack_report(
        schema_valid=True,
        hard_verifier_passed=False,
        referentially_valid=True,
        human_confirmed_decisive=True,
        require_human_confirmation=True,
        failed_codes={ValidationLayer.HARD_VERIFIER: ("count_lifecycle_mismatch",)},
    )

    assert report.hard_verified is False
    assert report.scientifically_acceptable is False
    hard = next(item for item in report.layers if item.layer is ValidationLayer.HARD_VERIFIER)
    assert hard.outcome is LayerOutcome.FAIL
    assert "count_lifecycle_mismatch" in hard.codes


def test_d0_path_accepts_without_semantic_verifier() -> None:
    report = build_validation_stack_report(
        schema_valid=True,
        hard_verifier_passed=True,
        referentially_valid=True,
        human_confirmed_decisive=True,
        require_human_confirmation=True,
        semantic_invoked=False,
    )

    assert report.scientifically_acceptable is True
    assert report.semantically_reviewed is False
    semantic = next(
        item for item in report.layers if item.layer is ValidationLayer.SEMANTIC_VERIFIER
    )
    assert semantic.outcome is LayerOutcome.NOT_RUN


def test_semantic_reviewed_only_when_invoked_and_passed() -> None:
    passed = build_validation_stack_report(
        schema_valid=True,
        hard_verifier_passed=True,
        referentially_valid=True,
        human_confirmed_decisive=True,
        semantic_invoked=True,
        semantic_passed=True,
    )
    failed = build_validation_stack_report(
        schema_valid=True,
        hard_verifier_passed=True,
        referentially_valid=True,
        human_confirmed_decisive=True,
        semantic_invoked=True,
        semantic_passed=False,
    )

    assert passed.semantically_reviewed is True
    assert failed.semantically_reviewed is False
    assert passed.scientifically_acceptable is True
    # Semantic failure does not by itself flip scientifically_acceptable on D0 policy;
    # hard/schema/human still gate. Callers may tighten policy separately.
    assert failed.scientifically_acceptable is True


def test_missing_human_confirmation_blocks_when_required() -> None:
    report = build_validation_stack_report(
        schema_valid=True,
        hard_verifier_passed=True,
        referentially_valid=True,
        human_confirmed_decisive=False,
        require_human_confirmation=True,
    )
    assert report.scientifically_acceptable is False
    human = next(item for item in report.layers if item.layer is ValidationLayer.HUMAN_CONFIRMATION)
    assert human.outcome is LayerOutcome.FAIL


def test_human_not_required_policy_allows_acceptability() -> None:
    report = build_validation_stack_report(
        schema_valid=True,
        hard_verifier_passed=True,
        referentially_valid=True,
        human_confirmed_decisive=False,
        require_human_confirmation=False,
    )
    assert report.scientifically_acceptable is True
    human = next(item for item in report.layers if item.layer is ValidationLayer.HUMAN_CONFIRMATION)
    assert human.outcome is LayerOutcome.NOT_APPLICABLE


def test_model_rejects_forged_scientifically_acceptable() -> None:
    with pytest.raises(ValidationError, match="schema_valid"):
        ValidationStackReport(
            syntax_valid=True,
            schema_valid=False,
            referentially_valid=False,
            hard_verified=False,
            semantically_reviewed=False,
            human_confirmed_decisive=False,
            layers=(),
            scientifically_acceptable=True,
            require_human_confirmation=True,
        )


def test_author_assertion_alone_fails_evidence_support() -> None:
    result = evidence_support_from_types([EvidenceType.AUTHOR_ASSERTION])
    assert result.layer is ValidationLayer.EVIDENCE_SUPPORT
    assert result.outcome is LayerOutcome.FAIL
    assert AUTHOR_ASSERTION_ALONE_CODE in result.codes

    empty = evidence_support_from_types([])
    assert empty.outcome is LayerOutcome.FAIL
    assert EVIDENCE_SUPPORT_EMPTY_CODE in empty.codes

    ok = evidence_support_from_types([EvidenceType.AUTHOR_ASSERTION, EvidenceType.SAMPLE_METADATA])
    assert ok.outcome is LayerOutcome.PASS

    report = build_validation_stack_report(
        schema_valid=True,
        hard_verifier_passed=True,
        referentially_valid=True,
        human_confirmed_decisive=True,
        evidence_support=result,
    )
    evidence_layer = next(
        item for item in report.layers if item.layer is ValidationLayer.EVIDENCE_SUPPORT
    )
    assert evidence_layer.outcome is LayerOutcome.FAIL
    assert AUTHOR_ASSERTION_ALONE_CODE in evidence_layer.codes
