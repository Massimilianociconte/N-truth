"""PRD v9 §6.1 step 7/9: bundle integrato della Quick Design session.

Compone il gap rimasto nella flow ``ntruth.quick_design.v9``: sample sheet v9
(Appendice O), convenzione ID non semantica, Methods draft sicuro, handoff
biostatistico neutrale e freeze del piano con content hash. Nessuna UI: i dati
per la vista separata di completeness/diagnostics (step 8) restano nel payload.

Il bundle non emette mai ``n`` ne raccomanda un test statistico; lo strategy
status resta HANDOFF_ONLY.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from ntruth.quick_design.v9 import QuickDesignV9State, statistical_handoff
from ntruth.reporting.safe_methods import (
    SafeMethodsSentence,
    draft_from_facts,
    render_safe_methods,
)
from ntruth.sample_sheet.v9_schema import SampleSheetRowV9, SampleSheetSpecV9
from ntruth.schemas.core import content_checksum

QUICK_DESIGN_V9_BUNDLE_SCHEMA_VERSION: Final = "9.0"
QUICK_DESIGN_V9_FROZEN_STATUS: Final = "FROZEN"

DEFAULT_ID_PREFIXES: Final[Mapping[str, str]] = {
    "experiment_block": "BLOCK",
    "row": "ROW",
    "unit_instance": "UNIT",
    "source_instance": "SRC",
    "preparation": "PREP",
    "event": "EVT",
    "plate": "PL",
}

_FORBIDDEN_BUNDLE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "n",
        "sample_size",
        "test_recommendation",
        "recommended_test",
        "recommended_model",
        "strategy_recommendation",
    }
)

_ID_CONVENTION_NOTE: Final = (
    "IDs are non-semantic placeholders: presence, uniqueness or constancy of "
    "identifiers is never evidence of allocation or independence."
)


@dataclass(frozen=True, slots=True)
class QuickDesignV9Bundle:
    """Artefatto deterministico degli step 7 del PRD v9 (§6.1)."""

    schema_version: str
    experiment_block_id: str
    sample_sheet: SampleSheetSpecV9
    id_convention: Mapping[str, str]
    methods_sentences: tuple[SafeMethodsSentence, ...]
    methods_draft_text: str
    handoff: Mapping[str, object]
    content_sha256: str

    def to_payload(self) -> dict[str, object]:
        """Payload serializzabile usato per il content hash."""

        return {
            "schema_version": self.schema_version,
            "experiment_block_id": self.experiment_block_id,
            "sample_sheet": self.sample_sheet.model_dump(mode="json"),
            "id_convention": dict(self.id_convention),
            "methods_sentences": [
                sentence.model_dump(mode="json") for sentence in self.methods_sentences
            ],
            "methods_draft_text": self.methods_draft_text,
            "handoff": dict(self.handoff),
        }


@dataclass(frozen=True, slots=True)
class QuickDesignV9FrozenPlan:
    """Manifest di freeze (step 9): status e content hash verificato."""

    schema_version: str
    status: str
    plan_content_sha256: str


def build_quick_design_v9_bundle(
    state: QuickDesignV9State,
    *,
    rows: Sequence[SampleSheetRowV9],
    experiment_block_id: str,
    planned: bool = True,
    unit_text: str | None = None,
    assignment_text: str | None = None,
    unknown_fields: tuple[str, ...] = (),
    id_prefixes: Mapping[str, str] | None = None,
) -> QuickDesignV9Bundle:
    """Compose step 7: sheet + IDs + safe Methods + handoff, poi content hash."""

    if not (state.factor_role_classified and state.contrast_type_classified):
        raise ValueError(
            "cannot build the Quick Design v9 bundle before FactorRole and "
            "ContrastType are classified"
        )

    prefixes: dict[str, str] = dict(DEFAULT_ID_PREFIXES)
    if id_prefixes is not None:
        unknown_slots = sorted(set(id_prefixes) - set(DEFAULT_ID_PREFIXES))
        if unknown_slots:
            raise ValueError(f"unknown id prefix slot(s): {', '.join(unknown_slots)}")
        prefixes.update(id_prefixes)
    prefixes["experiment_block"] = experiment_block_id
    id_convention: dict[str, str] = {**prefixes, "_note": _ID_CONVENTION_NOTE}

    sample_sheet = SampleSheetSpecV9(
        experiment_block_id=experiment_block_id,
        rows=tuple(rows),
    )
    sentences = draft_from_facts(
        planned=planned,
        assignment_known=assignment_text is not None,
        assignment_text=assignment_text,
        unit_text=unit_text,
        unknown_fields=unknown_fields,
    )
    rendered = render_safe_methods(sentences)
    handoff = statistical_handoff(state)

    def payload() -> dict[str, object]:
        return {
            "schema_version": QUICK_DESIGN_V9_BUNDLE_SCHEMA_VERSION,
            "experiment_block_id": experiment_block_id,
            "sample_sheet": sample_sheet.model_dump(mode="json"),
            "id_convention": id_convention,
            "methods_sentences": [sentence.model_dump(mode="json") for sentence in sentences],
            "methods_draft_text": rendered,
            "handoff": dict(handoff),
        }

    checked_payload = payload()
    _assert_no_forbidden_payload_keys(checked_payload)
    return QuickDesignV9Bundle(
        schema_version=QUICK_DESIGN_V9_BUNDLE_SCHEMA_VERSION,
        experiment_block_id=experiment_block_id,
        sample_sheet=sample_sheet,
        id_convention=id_convention,
        methods_sentences=sentences,
        methods_draft_text=rendered,
        handoff=handoff,
        content_sha256=content_checksum(checked_payload),
    )


def freeze_quick_design_v9_plan(bundle: QuickDesignV9Bundle) -> QuickDesignV9FrozenPlan:
    """Step 9: freeze con verifica del content hash del piano."""

    recomputed = content_checksum(bundle.to_payload())
    if recomputed != bundle.content_sha256:
        raise ValueError("plan content hash mismatch: the bundle changed after generation")
    return QuickDesignV9FrozenPlan(
        schema_version=bundle.schema_version,
        status=QUICK_DESIGN_V9_FROZEN_STATUS,
        plan_content_sha256=recomputed,
    )


def _assert_no_forbidden_payload_keys(payload: Mapping[str, Any]) -> None:
    leaked = _FORBIDDEN_BUNDLE_KEYS.intersection(payload)
    if leaked:
        raise ValueError(f"Quick Design v9 bundle must not contain {sorted(leaked)}")


__all__ = [
    "DEFAULT_ID_PREFIXES",
    "QUICK_DESIGN_V9_BUNDLE_SCHEMA_VERSION",
    "QUICK_DESIGN_V9_FROZEN_STATUS",
    "QuickDesignV9Bundle",
    "QuickDesignV9FrozenPlan",
    "build_quick_design_v9_bundle",
    "freeze_quick_design_v9_plan",
]
