"""PRD v9 Safe Methods Generation Contract (Appendix AN, §13.6, NFR-42)."""

from __future__ import annotations

import pytest

from ntruth.reporting.safe_methods import (
    ASSIGNMENT_PLACEHOLDER,
    SafeMethodsKnowledgeState,
    SafeMethodsMode,
    SafeMethodsSentence,
    draft_from_facts,
    render_safe_methods,
    validate_no_strengthening,
)


def _unknown_assignment_draft() -> tuple[SafeMethodsSentence, ...]:
    return draft_from_facts(
        planned=False,
        assignment_known=False,
        assignment_text="cells were independently assigned",
        unit_text=None,
        unknown_fields=(),
    )


def _known_assignment_draft(*, planned: bool) -> tuple[SafeMethodsSentence, ...]:
    return draft_from_facts(
        planned=planned,
        assignment_known=True,
        assignment_text="treatment levels assigned at the well after splitting",
        unit_text="well",
        unknown_fields=(),
    )


def test_unknown_assignment_stays_placeholder() -> None:
    sentences = _unknown_assignment_draft()
    rendered = render_safe_methods(sentences)
    placeholders = tuple(
        sentence for sentence in sentences if sentence.mode is SafeMethodsMode.UNKNOWN_PLACEHOLDER
    )

    assert placeholders
    assert all(
        sentence.knowledge_state is SafeMethodsKnowledgeState.UNKNOWN for sentence in placeholders
    )
    assert all(sentence.claim_or_evidence_refs == () for sentence in placeholders)
    assert ASSIGNMENT_PLACEHOLDER in rendered
    assert "independently assigned" not in rendered.casefold()
    assert "cells were independently assigned" not in rendered.casefold()


def test_strengthening_independently_assigned_is_rejected() -> None:
    original = next(
        sentence
        for sentence in _unknown_assignment_draft()
        if sentence.mode is SafeMethodsMode.UNKNOWN_PLACEHOLDER
    )

    with pytest.raises(ValueError, match="independently assigned"):
        validate_no_strengthening(
            original,
            f"{original.text} Cells were independently assigned to treatment.",
        )


def test_forbidden_biological_replicates_is_rejected() -> None:
    original = _known_assignment_draft(planned=False)[0]

    with pytest.raises(ValueError, match="biological replicates"):
        validate_no_strengthening(
            original,
            f"{original.text} Three biological replicates were used.",
        )


def test_planned_vs_executed_modes_differ() -> None:
    planned = _known_assignment_draft(planned=True)
    executed = _known_assignment_draft(planned=False)

    assert planned
    assert executed
    assert {sentence.mode for sentence in planned} == {SafeMethodsMode.PLANNED}
    assert {sentence.mode for sentence in executed} == {SafeMethodsMode.EXECUTED}
    assert render_safe_methods(planned) != render_safe_methods(executed)
    assert "Planned" in render_safe_methods(planned)
    assert "Executed" in render_safe_methods(executed)


def test_render_round_trip_each_sentence_still_validates() -> None:
    sentences = draft_from_facts(
        planned=False,
        assignment_known=False,
        assignment_text=None,
        unit_text="well",
        unknown_fields=("blinding", "exclusion rule"),
    )
    rendered = render_safe_methods(sentences)

    assert ASSIGNMENT_PLACEHOLDER in rendered
    assert "[UNKNOWN: blinding]" in rendered
    assert "[UNKNOWN: exclusion rule]" in rendered
    for sentence in sentences:
        assert sentence.text in rendered
        validate_no_strengthening(sentence, sentence.text)
        validate_no_strengthening(sentence, rendered)


def test_dropping_hedges_or_placeholder_brackets_is_rejected() -> None:
    sentences = _unknown_assignment_draft()
    placeholder = next(
        sentence for sentence in sentences if sentence.mode is SafeMethodsMode.UNKNOWN_PLACEHOLDER
    )
    caveat = next(
        sentence for sentence in sentences if sentence.mode is SafeMethodsMode.CONDITIONAL
    )

    with pytest.raises(ValueError, match="placeholder brackets"):
        validate_no_strengthening(placeholder, "UNKNOWN: assignment mechanism")
    with pytest.raises(ValueError, match="UNKNOWN"):
        validate_no_strengthening(
            caveat,
            "The draft remains incomplete if those fields stay hidden unless they are reported.",
        )
    with pytest.raises(ValueError, match="if"):
        validate_no_strengthening(
            caveat,
            "The draft remains incomplete while those fields stay UNKNOWN unless they are reported.",
        )
    with pytest.raises(ValueError, match="unless"):
        validate_no_strengthening(
            caveat,
            "The draft remains incomplete if those fields stay UNKNOWN.",
        )


def test_validated_design_and_bare_n_equals_are_rejected() -> None:
    original = _known_assignment_draft(planned=True)[0]

    with pytest.raises(ValueError, match="validated design"):
        validate_no_strengthening(original, f"{original.text} This is a validated design.")
    with pytest.raises(ValueError, match=r"n ="):
        validate_no_strengthening(original, f"{original.text} n = 6")


def test_present_assignment_may_retain_independently_assigned() -> None:
    original = SafeMethodsSentence(
        sentence_id="sm-present-assignment",
        mode=SafeMethodsMode.EXECUTED,
        text="Executed assignment: wells were independently assigned after splitting.",
        claim_or_evidence_refs=("fact:assignment",),
        knowledge_state=SafeMethodsKnowledgeState.PRESENT,
    )

    validate_no_strengthening(original, original.text)
    assert "independently assigned" in render_safe_methods((original,)).casefold()
