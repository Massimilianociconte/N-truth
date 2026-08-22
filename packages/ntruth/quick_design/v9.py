"""PRD v9 Quick Design session: FactorRole and ContrastType before later steps.

EU/experimental-unit counts are gated; this increment never emits n and never
recommends a statistical test. Strategy status stays HANDOFF_ONLY.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from ntruth.schemas.factor_role import ContrastType, FactorRole

STEPS: Final[tuple[str, ...]] = (
    "factor_role",
    "contrast_type",
    "source_preparation",
    "assignment",
    "levels_endpoint",
    "lineage_exposure",
    "sample_sheet",
    "safe_methods",
    "handoff",
)

_CLASSIFICATION_STEPS: Final[frozenset[str]] = frozenset({"factor_role", "contrast_type"})
_ALLOWED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "step",
        "factor_role",
        "contrast_type",
        "factor_name",
        "source_preparation",
        "assignment",
        "assignment_recorded",
        "levels_endpoint",
        "lineage_exposure",
        "sample_sheet",
        "safe_methods",
    }
)
_LATER_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "source_preparation",
        "assignment",
        "assignment_recorded",
        "levels_endpoint",
        "lineage_exposure",
        "sample_sheet",
        "safe_methods",
    }
)
_BLOCKED_N_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "n",
        "planned_n",
        "planned_units_per_level",
        "experimental_unit",
        "experimental_unit_count",
        "sample_size",
        "independent_n",
        "allocated_n",
        "analyzed_n",
    }
)
_FORBIDDEN_HANDOFF_KEYS: Final[frozenset[str]] = frozenset(
    {
        "test_recommendation",
        "recommended_test",
        "recommended_model",
        "strategy_recommendation",
        "sample_size",
        "n",
    }
)
_COMPATIBLE_CONTRASTS: Final[Mapping[str, frozenset[str]]] = {
    "ASSIGNED_INTERVENTION": frozenset(
        {"ASSIGNED_INTERVENTION_EFFECT", "DESCRIPTIVE_ONLY", "UNKNOWN"}
    ),
    "OBSERVATIONAL_EXPOSURE": frozenset(
        {"OBSERVATIONAL_ASSOCIATION", "DESCRIPTIVE_ONLY", "UNKNOWN"}
    ),
    "INTRINSIC_ATTRIBUTE": frozenset(
        {"INTRINSIC_ATTRIBUTE_COMPARISON", "DESCRIPTIVE_ONLY", "UNKNOWN"}
    ),
    "REPEATED_MEASURE_INDEX": frozenset(
        {"WITHIN_UNIT_REPEATED_CONTRAST", "DESCRIPTIVE_ONLY", "UNKNOWN"}
    ),
    "BLOCKING_FACTOR": frozenset({"DESCRIPTIVE_ONLY", "UNKNOWN"}),
    "BATCH_NUISANCE": frozenset({"NUISANCE_OR_BATCH_COMPARISON", "DESCRIPTIVE_ONLY", "UNKNOWN"}),
    "MEASUREMENT_CONDITION": frozenset({"DESCRIPTIVE_ONLY", "UNKNOWN"}),
    "UNKNOWN": frozenset({member.value for member in ContrastType}),
}

_ROLE_QUESTION = (
    "What is the FactorRole of this factor? Classify whether it is an assigned "
    "intervention, an intrinsic attribute such as genotype, or another role "
    "before levels, assignment, sample sheet, or any count."
)


def _enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _coerce_enum[EnumT: StrEnum](enum_type: type[EnumT], value: object, label: str) -> EnumT:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, StrEnum):
        try:
            return enum_type(value.value)
        except ValueError:
            pass
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError:
            try:
                return enum_type[value]
            except KeyError:
                pass
    raise ValueError(f"invalid {label}: {value!r}")


def _coerce_factor_role(value: object) -> FactorRole:
    return _coerce_enum(FactorRole, value, "FactorRole")


def _coerce_contrast_type(value: object) -> ContrastType:
    return _coerce_enum(ContrastType, value, "ContrastType")


def _assert_compatible(role: FactorRole, contrast: ContrastType) -> None:
    allowed = _COMPATIBLE_CONTRASTS.get(
        _enum_value(role), frozenset({"UNKNOWN", "DESCRIPTIVE_ONLY"})
    )
    if _enum_value(contrast) not in allowed:
        raise ValueError(
            f"ContrastType {_enum_value(contrast)} is not compatible with "
            f"FactorRole {_enum_value(role)}"
        )


def _step_index(step: str) -> int:
    if step not in STEPS:
        raise ValueError(f"unknown Quick Design v9 step: {step}")
    return STEPS.index(step)


def _assignment_is_recorded(value: object) -> bool:
    if value is True:
        return True
    if value in (None, False, "", 0):
        return False
    if isinstance(value, Mapping) and not value:
        return False
    return not (isinstance(value, (list, tuple, set, frozenset)) and not value)


@dataclass(frozen=True, slots=True)
class QuickDesignV9State:
    """Immutable Quick Design v9 session. ``n`` is never populated."""

    step: str = "factor_role"
    factor_role: FactorRole = FactorRole.UNKNOWN
    contrast_type: ContrastType = ContrastType.UNKNOWN
    factor_role_classified: bool = False
    contrast_type_classified: bool = False
    factor_name: str | None = None
    source_preparation: object | None = None
    assignment: object | None = None
    assignment_recorded: bool = False
    levels_endpoint: object | None = None
    lineage_exposure: object | None = None
    sample_sheet: object | None = None
    safe_methods: object | None = None
    n: int | None = None

    def __post_init__(self) -> None:
        _step_index(self.step)
        if self.n is not None:
            raise ValueError("Quick Design v9 session must not emit n")
        object.__setattr__(self, "factor_role", _coerce_factor_role(self.factor_role))
        object.__setattr__(self, "contrast_type", _coerce_contrast_type(self.contrast_type))
        if self.factor_role_classified and self.contrast_type_classified:
            _assert_compatible(self.factor_role, self.contrast_type)
        if self.assignment_recorded and not _assignment_is_recorded(self.assignment):
            object.__setattr__(self, "assignment", True)
        elif _assignment_is_recorded(self.assignment):
            object.__setattr__(self, "assignment_recorded", True)


def start_session() -> QuickDesignV9State:
    """Open a session on ``factor_role``. No n is emitted."""

    return QuickDesignV9State()


def _classification_from(
    state: QuickDesignV9State, fields: Mapping[str, object]
) -> tuple[FactorRole, bool, ContrastType, bool]:
    if "factor_role" in fields:
        role = _coerce_factor_role(fields["factor_role"])
        role_classified = True
    else:
        role = state.factor_role
        role_classified = state.factor_role_classified
    if "contrast_type" in fields:
        contrast = _coerce_contrast_type(fields["contrast_type"])
        contrast_classified = True
    else:
        contrast = state.contrast_type
        contrast_classified = state.contrast_type_classified
    if role_classified and contrast_classified:
        _assert_compatible(role, contrast)
    return role, role_classified, contrast, contrast_classified


def _reject_skip(
    state: QuickDesignV9State,
    fields: Mapping[str, object],
    role_classified: bool,
    contrast_classified: bool,
) -> None:
    requested = fields.get("step")
    requested_step = requested if isinstance(requested, str) else None
    later_field_present = any(name in fields for name in _LATER_FIELDS)
    later_step_requested = (
        requested_step is not None and requested_step not in _CLASSIFICATION_STEPS
    )
    if (later_field_present or later_step_requested) and not (
        role_classified and contrast_classified
    ):
        if requested_step == "sample_sheet" or "sample_sheet" in fields:
            target = "sample_sheet"
        elif requested_step is not None:
            target = requested_step
        else:
            target = next((name for name in STEPS if name in fields), "later steps")
        raise ValueError(
            f"cannot advance to {target} before FactorRole and ContrastType are classified"
        )
    if (
        requested_step == "factor_role"
        and state.step != "factor_role"
        and "factor_role" not in fields
    ):
        raise ValueError("cannot skip FactorRole or ContrastType classification")


def _resolve_step(
    state: QuickDesignV9State,
    fields: Mapping[str, object],
    role_classified: bool,
    contrast_classified: bool,
) -> str:
    requested = fields.get("step")
    if requested is not None:
        return STEPS[_step_index(str(requested))]
    if not role_classified:
        return "factor_role"
    if not contrast_classified:
        return "contrast_type"
    provided_later = [name for name in STEPS[2:] if name in fields]
    if "assignment_recorded" in fields and "assignment" not in provided_later:
        provided_later.append("assignment")
    if provided_later:
        farthest = max(_step_index(name) for name in provided_later)
        return STEPS[min(farthest + 1, len(STEPS) - 1)]
    if state.step in _CLASSIFICATION_STEPS:
        return "source_preparation"
    if state.step in fields or (state.step == "assignment" and "assignment_recorded" in fields):
        return STEPS[min(_step_index(state.step) + 1, len(STEPS) - 1)]
    return state.step


def advance(state: QuickDesignV9State, **fields: object) -> QuickDesignV9State:
    """Apply session fields. Fail closed if role/type would be skipped."""

    if not fields:
        raise ValueError("advance requires at least one field")
    blocked = _BLOCKED_N_FIELDS.intersection(fields)
    if blocked:
        names = ", ".join(sorted(blocked))
        raise ValueError(
            f"Quick Design v9 does not emit {names}; FactorRole and ContrastType "
            "must be classified before any count"
        )
    unknown = set(fields) - _ALLOWED_FIELDS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unsupported Quick Design v9 field(s): {names}")

    role, role_classified, contrast, contrast_classified = _classification_from(state, fields)
    _reject_skip(state, fields, role_classified, contrast_classified)
    next_step = _resolve_step(state, fields, role_classified, contrast_classified)

    assignment = fields.get("assignment", state.assignment)
    if "assignment_recorded" in fields:
        assignment_recorded = bool(fields["assignment_recorded"])
        if assignment_recorded and not _assignment_is_recorded(assignment):
            assignment = True
    else:
        assignment_recorded = state.assignment_recorded or _assignment_is_recorded(assignment)

    factor_name = fields.get("factor_name", state.factor_name)
    if factor_name is not None:
        factor_name = str(factor_name)

    return replace(
        state,
        step=next_step,
        factor_role=role,
        contrast_type=contrast,
        factor_role_classified=role_classified,
        contrast_type_classified=contrast_classified,
        factor_name=factor_name,
        source_preparation=fields.get("source_preparation", state.source_preparation),
        assignment=assignment,
        assignment_recorded=assignment_recorded,
        levels_endpoint=fields.get("levels_endpoint", state.levels_endpoint),
        lineage_exposure=fields.get("lineage_exposure", state.lineage_exposure),
        sample_sheet=fields.get("sample_sheet", state.sample_sheet),
        safe_methods=fields.get("safe_methods", state.safe_methods),
        n=None,
    )


def can_emit_experimental_unit(state: QuickDesignV9State) -> bool:
    """True only for assigned intervention effect with recorded assignment."""

    return (
        state.factor_role_classified
        and state.contrast_type_classified
        and _enum_value(state.factor_role) == "ASSIGNED_INTERVENTION"
        and _enum_value(state.contrast_type) == "ASSIGNED_INTERVENTION_EFFECT"
        and state.assignment_recorded
    )


def primary_question(state: QuickDesignV9State) -> str:
    """Return the decisive next question. UNKNOWN role never asks for n."""

    if not state.factor_role_classified or _enum_value(state.factor_role) == "UNKNOWN":
        return _ROLE_QUESTION
    if not state.contrast_type_classified or _enum_value(state.contrast_type) == "UNKNOWN":
        return (
            "What is the ContrastType for this question? Classify the comparison "
            "family before levels, assignment, or sample sheet."
        )
    questions = {
        "source_preparation": (
            "What biological source and preparation produce the material under study?"
        ),
        "assignment": (
            "What assignment event, unit, and mechanism were used, or is assignment unknown?"
        ),
        "levels_endpoint": "What factor levels and endpoint define the contrast?",
        "lineage_exposure": (
            "What material lineage and exposure pathway apply, or are they unknown?"
        ),
        "sample_sheet": (
            "Which sample-sheet identifiers should be generated as non-semantic placeholders?"
        ),
        "safe_methods": "Which planned facts are confirmed for a safe Methods draft?",
        "handoff": "Statistical strategy remains HANDOFF_ONLY; no test is recommended.",
    }
    return questions.get(state.step, _ROLE_QUESTION)


def statistical_handoff(state: QuickDesignV9State) -> dict[str, object]:
    """Neutral biostatistician handoff. Never recommends a test."""

    payload: dict[str, object] = {
        "strategy_module_status": "HANDOFF_ONLY",
        "step": state.step,
        "factor_role": _enum_value(state.factor_role),
        "contrast_type": _enum_value(state.contrast_type),
        "factor_role_classified": state.factor_role_classified,
        "contrast_type_classified": state.contrast_type_classified,
        "assignment_recorded": state.assignment_recorded,
        "can_emit_experimental_unit": can_emit_experimental_unit(state),
        "unresolved_questions": (primary_question(state),),
        "structural_constraints": (
            "Experimental-unit counts require FactorRole=ASSIGNED_INTERVENTION, "
            "ContrastType=ASSIGNED_INTERVENTION_EFFECT, and a recorded assignment history.",
        ),
    }
    leaked = _FORBIDDEN_HANDOFF_KEYS.intersection(payload)
    if leaked:
        raise ValueError(f"statistical handoff must not contain {sorted(leaked)}")
    return payload
