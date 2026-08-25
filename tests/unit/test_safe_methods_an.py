"""Appendice AN: mode normative, sentence contract e no-invented-claims.

Aggiunge SOLO nuovi test sul contratto AN; i test storici in
``test_prd_v9_safe_methods.py`` restano immutati.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.reporting.safe_methods import (
    SafeMethodsKnowledgeState,
    SafeMethodsMode,
    SafeMethodsSentence,
    render_safe_methods,
    validate_no_strengthening,
)


def _sentence(**overrides: object) -> SafeMethodsSentence:
    base: dict[str, object] = {
        "sentence_id": "an-001",
        "mode": SafeMethodsMode.TEMPLATE_FROM_CONFIRMED_PLAN,
        "text": "Planned treatment levels are assigned at the well after splitting.",
        "claim_or_evidence_refs": ("fact:assignment",),
        "knowledge_state": SafeMethodsKnowledgeState.PRESENT,
    }
    base.update(overrides)
    return SafeMethodsSentence.model_validate(base)


def test_appendix_an_modes_exist_and_legacy_modes_are_preserved() -> None:
    assert SafeMethodsMode.TEMPLATE_FROM_CONFIRMED_PLAN.value == ("TEMPLATE_FROM_CONFIRMED_PLAN")
    assert SafeMethodsMode.DESCRIPTIVE_RECORD_ONLY.value == "DESCRIPTIVE_RECORD_ONLY"
    assert SafeMethodsMode.CONDITIONAL_DRAFT.value == "CONDITIONAL_DRAFT"
    assert SafeMethodsMode.USER_EDITED_WITH_DIFF.value == "USER_EDITED_WITH_DIFF"
    # Alias di compatibilita storici, richiesti dai contratti pre-AN.
    assert SafeMethodsMode.PLANNED.value == "PLANNED"
    assert SafeMethodsMode.EXECUTED.value == "EXECUTED"
    assert SafeMethodsMode.CONDITIONAL.value == "CONDITIONAL"
    assert SafeMethodsMode.UNKNOWN_PLACEHOLDER.value == "UNKNOWN_PLACEHOLDER"


def test_template_from_confirmed_plan_sentence_round_trips() -> None:
    sentence = _sentence()
    rendered = render_safe_methods((sentence,))
    validate_no_strengthening(sentence, rendered)
    assert sentence.mode is SafeMethodsMode.TEMPLATE_FROM_CONFIRMED_PLAN


def test_descriptive_record_only_requires_refs() -> None:
    with pytest.raises(ValidationError, match="claim_or_evidence_refs"):
        _sentence(
            mode=SafeMethodsMode.DESCRIPTIVE_RECORD_ONLY,
            claim_or_evidence_refs=(),
            text="Records describe two preparations per donor.",
        )
    ok = _sentence(
        mode=SafeMethodsMode.DESCRIPTIVE_RECORD_ONLY,
        text="Records describe two preparations per donor.",
    )
    assert ok.claim_or_evidence_refs == ("fact:assignment",)


def test_conditional_draft_mode_is_valid() -> None:
    ok = _sentence(
        mode=SafeMethodsMode.CONDITIONAL_DRAFT,
        knowledge_state=SafeMethodsKnowledgeState.UNKNOWN,
        text=("The draft remains incomplete if assignment stays UNKNOWN unless it is reported."),
    )
    assert ok.uncertainty_preserved is True
    # La visibilita del placeholder e richiesta solo alla mode UNKNOWN_PLACEHOLDER.
    validate_no_strengthening(ok, ok.text)


def test_uncertainty_flag_must_hold_for_unknown_sentences() -> None:
    with pytest.raises(ValidationError, match="uncertainty"):
        _sentence(
            mode=SafeMethodsMode.UNKNOWN_PLACEHOLDER,
            text="[UNKNOWN: assignment mechanism]",
            claim_or_evidence_refs=(),
            knowledge_state=SafeMethodsKnowledgeState.UNKNOWN,
            uncertainty_preserved=False,
        )
    present_fact = _sentence(uncertainty_preserved=False)
    assert present_fact.knowledge_state is SafeMethodsKnowledgeState.PRESENT


def test_user_edited_with_diff_requires_diff_and_approver() -> None:
    edited = _sentence(
        mode=SafeMethodsMode.USER_EDITED_WITH_DIFF,
        approver="reviewer-2",
        user_edit_diff="- Planned levels assigned ...\\n+ Levels planned at well ...",
    )
    assert edited.approver == "reviewer-2"

    with pytest.raises(ValidationError, match="user_edit_diff"):
        _sentence(mode=SafeMethodsMode.USER_EDITED_WITH_DIFF, approver="reviewer-2")
    with pytest.raises(ValidationError, match="approver"):
        _sentence(
            mode=SafeMethodsMode.USER_EDITED_WITH_DIFF,
            user_edit_diff="- old\\n+ new",
        )
    # diff fuori dalla mode dedicata non e ammesso
    with pytest.raises(ValidationError, match="only on USER_EDITED_WITH_DIFF"):
        _sentence(user_edit_diff="- old\\n+ new", approver="reviewer-2")


def test_invented_exclusion_is_rejected() -> None:
    original = _sentence()
    with pytest.raises(ValueError, match="invented exclusion"):
        validate_no_strengthening(
            original,
            f"{original.text} Two wells were excluded after hemolysis.",
        )


def test_invented_blinding_is_rejected_but_placeholder_mention_passes() -> None:
    original = _sentence()
    with pytest.raises(ValueError, match="invented blinding"):
        validate_no_strengthening(
            original,
            f"{original.text} Scoring was blinded.",
        )
    declared_unknown = _sentence(
        mode=SafeMethodsMode.UNKNOWN_PLACEHOLDER,
        text="[UNKNOWN: blinding]",
        claim_or_evidence_refs=(),
        knowledge_state=SafeMethodsKnowledgeState.UNKNOWN,
    )
    validate_no_strengthening(declared_unknown, declared_unknown.text)


def test_invented_randomization_is_rejected() -> None:
    original = _sentence()
    with pytest.raises(ValueError, match="invented randomization"):
        validate_no_strengthening(
            original,
            f"{original.text} Plates were randomized across incubator positions.",
        )


def test_strengthened_user_edit_requires_new_confirmation_event() -> None:
    """AN.4: l'edit utente che rafforza crea un nuovo evento, mai silent."""

    original = _sentence()
    strengthened_text = f"{original.text} Blinded scoring was used."
    strengthened = _sentence(
        sentence_id="an-004",
        mode=SafeMethodsMode.USER_EDITED_WITH_DIFF,
        approver="reviewer-2",
        user_edit_diff=f"- {original.text}\\n+ {strengthened_text}",
        text=strengthened_text,
    )
    assert strengthened.mode is SafeMethodsMode.USER_EDITED_WITH_DIFF
    with pytest.raises(ValueError, match="invented blinding"):
        validate_no_strengthening(original, strengthened.text)


def test_weaker_or_equal_round_trip_holds_for_all_new_modes() -> None:
    sentences = (
        _sentence(),
        _sentence(
            sentence_id="an-002",
            mode=SafeMethodsMode.DESCRIPTIVE_RECORD_ONLY,
            text="Records describe one preparation per source.",
        ),
        _sentence(
            sentence_id="an-003",
            mode=SafeMethodsMode.CONDITIONAL_DRAFT,
            knowledge_state=SafeMethodsKnowledgeState.UNKNOWN,
            text="Assignment stays UNKNOWN unless it is reported.",
        ),
    )
    rendered = render_safe_methods(sentences)
    for sentence in sentences:
        validate_no_strengthening(sentence, sentence.text)
        validate_no_strengthening(sentence, rendered)
