"""PRD v9 §6.1 step 7/9: bundle Quick Design (sheet + ID + Methods + handoff)."""

from __future__ import annotations

import pytest

from ntruth.quick_design.v9 import QuickDesignV9State, advance, start_session
from ntruth.quick_design.v9_bundle import (
    DEFAULT_ID_PREFIXES,
    QUICK_DESIGN_V9_BUNDLE_SCHEMA_VERSION,
    QuickDesignV9Bundle,
    build_quick_design_v9_bundle,
    freeze_quick_design_v9_plan,
)
from ntruth.reporting.safe_methods import SafeMethodsMode
from ntruth.sample_sheet.v9_schema import (
    PlannedOrExecutedContext,
    RowLifecycleStatus,
    SampleSheetRowV9,
    UnitType,
    present,
    unknown,
)
from ntruth.schemas.factor_role import ContrastType, FactorRole

_FORBIDDEN_KEYS = frozenset({"n", "sample_size", "test_recommendation", "recommended_test"})


def _assigned_state() -> QuickDesignV9State:
    return advance(
        start_session(),
        factor_role=FactorRole.ASSIGNED_INTERVENTION,
        contrast_type=ContrastType.ASSIGNED_INTERVENTION_EFFECT,
        assignment=True,
    )


def _rows(row_id: str = "ROW-001") -> tuple[SampleSheetRowV9, ...]:
    return (
        SampleSheetRowV9.model_validate(
            {
                "row_id": row_id,
                "experiment_block_id": "BLOCK-A",
                "unit_instance_id": "UNIT-001",
                "unit_type": UnitType.WELL,
                "source_instance_id": present("SRC-01"),
                "preparation_id": unknown("split non documentato"),
                "factors": {
                    "treatment": {
                        "factor_id": present("FAC-treatment"),
                        "factor_role": present("ASSIGNED_INTERVENTION"),
                        "factor_level": present("L1"),
                        "assignment_event_id": present("EVT-ASSIGN-01"),
                    }
                },
                "lifecycle_status": RowLifecycleStatus.PLANNED,
                "planned_or_executed_context": PlannedOrExecutedContext.PLANNED,
            }
        ),
    )


def _bundle(row_id: str = "ROW-001") -> QuickDesignV9Bundle:
    return build_quick_design_v9_bundle(
        _assigned_state(),
        rows=_rows(row_id),
        experiment_block_id="BLOCK-A",
        planned=True,
        unit_text="well",
        assignment_text="levels assigned at the well after splitting",
        unknown_fields=("blinding",),
    )


def test_bundle_composes_sheet_ids_methods_handoff_and_hash() -> None:
    bundle = _bundle()

    assert bundle.schema_version == QUICK_DESIGN_V9_BUNDLE_SCHEMA_VERSION
    assert bundle.sample_sheet.experiment_block_id == "BLOCK-A"
    assert len(bundle.sample_sheet.rows) == 1
    assert bundle.id_convention["row"] == DEFAULT_ID_PREFIXES["row"]
    assert bundle.id_convention["experiment_block"] == "BLOCK-A"
    assert bundle.id_convention["_note"].startswith("IDs are non-semantic placeholders")
    assert any(
        sentence.mode is SafeMethodsMode.UNKNOWN_PLACEHOLDER
        for sentence in bundle.methods_sentences
    )
    assert "[UNKNOWN: blinding]" in bundle.methods_draft_text
    handoff: dict[str, object] = dict(bundle.handoff)
    assert handoff["strategy_module_status"] == "HANDOFF_ONLY"
    assert len(bundle.content_sha256) == 64


def test_bundle_is_deterministic_and_hash_tracks_content() -> None:
    first = _bundle()
    second = _bundle()
    assert first.content_sha256 == second.content_sha256

    third = _bundle(row_id="ROW-002")
    assert third.content_sha256 != first.content_sha256


def test_bundle_refuses_unclassified_sessions() -> None:
    with pytest.raises(ValueError, match="FactorRole and ContrastType"):
        build_quick_design_v9_bundle(
            start_session(),
            rows=_rows(),
            experiment_block_id="BLOCK-A",
        )


def test_bundle_never_emits_n_or_test_recommendations() -> None:
    bundle = _bundle()
    assert not _FORBIDDEN_KEYS.intersection(dict(bundle.handoff))
    payload = bundle.to_payload()
    assert not _FORBIDDEN_KEYS.intersection(payload)


def test_freeze_verifies_content_hash_and_detects_tampering() -> None:
    bundle = _bundle()
    frozen = freeze_quick_design_v9_plan(bundle)
    assert frozen.status == "FROZEN"
    assert frozen.plan_content_sha256 == bundle.content_sha256

    tampered = _bundle()
    object.__setattr__(tampered, "content_sha256", "0" * 64)
    with pytest.raises(ValueError, match="hash mismatch"):
        freeze_quick_design_v9_plan(tampered)


def test_unknown_slot_prefixes_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown id prefix slot"):
        build_quick_design_v9_bundle(
            _assigned_state(),
            rows=_rows(),
            experiment_block_id="BLOCK-A",
            id_prefixes={"mystery": "M"},
        )
