"""PRD v9 Safe Methods Generation Contract.

Sentence-level Methods drafts preserve unknowns, planned/executed mode, and
claim/evidence refs. Semantic strengthening is a release blocker (NFR-42, AN.4).
This increment does not rewrite the v8 report kernel.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, Self

from pydantic import Field, field_validator, model_validator

from ntruth.schemas.core import FrozenModel

ASSIGNMENT_MECHANISM_FIELD: Final = "assignment mechanism"
ASSIGNMENT_PLACEHOLDER: Final = "[UNKNOWN: assignment mechanism]"

_HEDGE_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("UNKNOWN", re.compile(r"UNKNOWN")),
    ("NOT_REPORTED", re.compile(r"NOT_REPORTED")),
    ("if", re.compile(r"\bif\b", re.IGNORECASE)),
    ("unless", re.compile(r"\bunless\b", re.IGNORECASE)),
)
_VISIBLE_PLACEHOLDER: Final = re.compile(r"\[(?:UNKNOWN|NOT_REPORTED):[^\]]+\]")
_N_EQUALS: Final = re.compile(r"\bn\s*=", re.IGNORECASE)
_ASSERTIVE_ASSIGNMENT: Final = re.compile(
    r"\b(?:were|was|are|is)\s+(?:independently\s+)?assigned\b",
    re.IGNORECASE,
)
_PRAISE: Final = re.compile(
    r"\b(good|great|valid(?:ated)?|quality|excellent|approved|certified|sound|robust)\b",
    re.IGNORECASE,
)
_COUNT_REF_SEGMENT: Final = re.compile(r"(?:^|[:/_-])(?:count|n)(?:$|[:/_-])", re.IGNORECASE)


class SafeMethodsMode(StrEnum):
    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN_PLACEHOLDER = "UNKNOWN_PLACEHOLDER"


class SafeMethodsKnowledgeState(StrEnum):
    PRESENT = "PRESENT"
    UNKNOWN = "UNKNOWN"
    NOT_REPORTED = "NOT_REPORTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SafeMethodsSentence(FrozenModel):
    """One generated Methods sentence with mode, refs, and knowledge state."""

    sentence_id: str = Field(min_length=1)
    mode: SafeMethodsMode
    text: str = Field(min_length=1)
    claim_or_evidence_refs: tuple[str, ...] = ()
    knowledge_state: SafeMethodsKnowledgeState

    @field_validator("sentence_id", "text")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("sentence fields must be non-blank")
        return stripped

    @field_validator("claim_or_evidence_refs")
    @classmethod
    def _strip_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned: list[str] = []
        for item in value:
            token = item.strip()
            if not token:
                raise ValueError("claim_or_evidence_refs must not contain blank entries")
            cleaned.append(token)
        return tuple(cleaned)

    @model_validator(mode="after")
    def _enforce_contract(self) -> Self:
        _assert_sentence_contract(self)
        return self


def render_safe_methods(sentences: tuple[SafeMethodsSentence, ...]) -> str:
    """Join sentence texts. Placeholders stay visible in the rendered draft."""

    texts: list[str] = []
    for sentence in sentences:
        _assert_sentence_contract(sentence)
        validate_no_strengthening(sentence, sentence.text)
        texts.append(sentence.text)
    return " ".join(texts)


def validate_no_strengthening(original: SafeMethodsSentence, edited_text: str) -> None:
    """Reject edits that drop hedges or introduce forbidden strengthening."""

    _assert_sentence_contract(original)
    if _uses_determinate_as_praise(edited_text):
        raise ValueError("cannot use DETERMINATE as quality praise")
    lowered = edited_text.casefold()
    if "biological replicates" in lowered:
        raise ValueError("forbidden phrase: biological replicates")
    if "independently assigned" in lowered and original.knowledge_state is not (
        SafeMethodsKnowledgeState.PRESENT
    ):
        raise ValueError("forbidden phrase: independently assigned")
    if "validated design" in lowered:
        raise ValueError("forbidden phrase: validated design")
    if _N_EQUALS.search(edited_text) and not _has_count_claim_ref(original.claim_or_evidence_refs):
        raise ValueError("forbidden phrase: n =")
    for token, pattern in _HEDGE_PATTERNS:
        if pattern.search(original.text) and not pattern.search(edited_text):
            raise ValueError(f"removed hedge token: {token}")
    if "[" in original.text and "[" not in edited_text:
        raise ValueError("removed placeholder brackets")
    if "]" in original.text and "]" not in edited_text:
        raise ValueError("removed placeholder brackets")


def draft_from_facts(
    *,
    planned: bool,
    assignment_known: bool,
    assignment_text: str | None,
    unit_text: str | None,
    unknown_fields: tuple[str, ...],
) -> tuple[SafeMethodsSentence, ...]:
    """Deterministic sentence draft. Unknown assignment stays a placeholder."""

    sentences: list[SafeMethodsSentence] = []
    known_mode = SafeMethodsMode.PLANNED if planned else SafeMethodsMode.EXECUTED
    tense = "Planned" if planned else "Executed"
    unit = _optional_text(unit_text)
    assignment = _optional_text(assignment_text)
    unknowns = _normalize_unknown_fields(unknown_fields)

    if unit is not None:
        sentences.append(
            SafeMethodsSentence(
                sentence_id="sm-unit",
                mode=known_mode,
                text=_as_sentence(f"{tense} experimental unit: {unit}"),
                claim_or_evidence_refs=("fact:unit",),
                knowledge_state=SafeMethodsKnowledgeState.PRESENT,
            )
        )

    if assignment_known:
        if assignment is None:
            raise ValueError("assignment_text is required when assignment_known is True")
        sentences.append(
            SafeMethodsSentence(
                sentence_id="sm-assignment",
                mode=known_mode,
                text=_as_sentence(f"{tense} assignment: {assignment}"),
                claim_or_evidence_refs=("fact:assignment",),
                knowledge_state=SafeMethodsKnowledgeState.PRESENT,
            )
        )
    else:
        sentences.append(
            SafeMethodsSentence(
                sentence_id="sm-assignment",
                mode=SafeMethodsMode.UNKNOWN_PLACEHOLDER,
                text=ASSIGNMENT_PLACEHOLDER,
                claim_or_evidence_refs=(),
                knowledge_state=SafeMethodsKnowledgeState.UNKNOWN,
            )
        )

    emitted = {ASSIGNMENT_MECHANISM_FIELD.casefold()} if not assignment_known else set()
    unknown_index = 0
    for field in unknowns:
        key = field.casefold()
        if key in emitted:
            continue
        unknown_index += 1
        emitted.add(key)
        sentences.append(
            SafeMethodsSentence(
                sentence_id=f"sm-unknown-{unknown_index:03d}",
                mode=SafeMethodsMode.UNKNOWN_PLACEHOLDER,
                text=f"[UNKNOWN: {field}]",
                claim_or_evidence_refs=(),
                knowledge_state=SafeMethodsKnowledgeState.UNKNOWN,
            )
        )

    if any(item.mode is SafeMethodsMode.UNKNOWN_PLACEHOLDER for item in sentences):
        sentences.append(
            SafeMethodsSentence(
                sentence_id="sm-conditional",
                mode=SafeMethodsMode.CONDITIONAL,
                text=(
                    "The draft remains incomplete if those fields stay UNKNOWN "
                    "unless they are reported."
                ),
                claim_or_evidence_refs=("fact:unknown-fields",),
                knowledge_state=SafeMethodsKnowledgeState.UNKNOWN,
            )
        )

    return tuple(sentences)


def _assert_sentence_contract(sentence: SafeMethodsSentence) -> None:
    if not sentence.claim_or_evidence_refs and sentence.mode is not (
        SafeMethodsMode.UNKNOWN_PLACEHOLDER
    ):
        raise ValueError("claim_or_evidence_refs may be empty only for UNKNOWN_PLACEHOLDER")
    if _uses_determinate_as_praise(sentence.text):
        raise ValueError("cannot use DETERMINATE as quality praise")
    lowered = sentence.text.casefold()
    if "biological replicates" in lowered:
        raise ValueError("forbidden phrase: biological replicates")
    if "validated design" in lowered:
        raise ValueError("forbidden phrase: validated design")
    if _N_EQUALS.search(sentence.text) and not _has_count_claim_ref(
        sentence.claim_or_evidence_refs
    ):
        raise ValueError("forbidden phrase: n =")
    unknown_or_unreported = sentence.knowledge_state in {
        SafeMethodsKnowledgeState.UNKNOWN,
        SafeMethodsKnowledgeState.NOT_REPORTED,
    }
    if unknown_or_unreported and sentence.mode is SafeMethodsMode.EXECUTED:
        raise ValueError("cannot turn UNKNOWN/NOT_REPORTED into assertive executed prose")
    if unknown_or_unreported and _is_assertive_executed_prose(sentence.text):
        raise ValueError("cannot turn UNKNOWN/NOT_REPORTED into assertive executed prose")
    if sentence.knowledge_state is not SafeMethodsKnowledgeState.PRESENT and (
        "independently assigned" in lowered
    ):
        raise ValueError("forbidden phrase: independently assigned")
    if sentence.mode is SafeMethodsMode.UNKNOWN_PLACEHOLDER and (
        _VISIBLE_PLACEHOLDER.search(sentence.text) is None
    ):
        raise ValueError("UNKNOWN_PLACEHOLDER text must remain a visible placeholder")


def _is_assertive_executed_prose(text: str) -> bool:
    if _VISIBLE_PLACEHOLDER.search(text) is not None:
        return False
    if "independently assigned" in text.casefold():
        return True
    return _ASSERTIVE_ASSIGNMENT.search(text) is not None


def _uses_determinate_as_praise(text: str) -> bool:
    if "DETERMINATE" not in text:
        return False
    return _PRAISE.search(text) is not None


def _has_count_claim_ref(refs: tuple[str, ...]) -> bool:
    return any(_COUNT_REF_SEGMENT.search(ref) is not None for ref in refs)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_unknown_fields(fields: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for field in fields:
        stripped = field.strip()
        if not stripped:
            continue
        key = stripped.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(stripped)
    return tuple(ordered)


def _as_sentence(text: str) -> str:
    body = " ".join(text.split())
    if not body.endswith((".", "!", "?")):
        return f"{body}."
    return body


__all__ = [
    "ASSIGNMENT_PLACEHOLDER",
    "SafeMethodsKnowledgeState",
    "SafeMethodsMode",
    "SafeMethodsSentence",
    "draft_from_facts",
    "render_safe_methods",
    "validate_no_strengthening",
]
