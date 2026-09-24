"""Fail-closed v7 adapters for PRD v8 counts and event timing."""

from __future__ import annotations

from ntruth.migrations import migrate_v7_count_kind, migrate_v7_global_timing
from ntruth.schemas.count_registry import CanonicalCountKind
from ntruth.schemas.events import TemporalRelation


def test_inconsistent_appendix_p_count_name_requires_review() -> None:
    result = migrate_v7_count_kind(
        "planned_n",
        source_contract="ntruth-count-registry/7.0.0",
        query_id="IQ-001",
    )
    assert result.value is None
    assert result.requires_scientific_review
    assert result.diagnostics[0].issue_id == "SRR-V8-011"


def test_independent_n_migrates_only_with_explicit_query_scope() -> None:
    blocked = migrate_v7_count_kind(
        "independent_n",
        source_contract="ntruth-count-registry/7.0.0",
    )
    assert blocked.value is None
    assert blocked.requires_scientific_review
    assert blocked.diagnostics[0].issue_id == "SRR-V8-011"

    migrated = migrate_v7_count_kind(
        "independent_n",
        source_contract="ntruth-count-registry/7.0.0",
        query_id="IQ-001",
    )
    assert migrated.value is CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT
    assert migrated.lineage[0].field_name == "kind"
    assert migrated.lineage[0].migration_rule_id == "PRD-V8-7.9-independent-n"


def test_global_timing_without_event_ids_fails_closed() -> None:
    result = migrate_v7_global_timing(
        "before",
        source_contract="ntruth-causal-context/7.0.0",
        evidence_refs=("EV-TIMING-01",),
    )
    assert result.value is None
    assert result.requires_scientific_review
    assert result.diagnostics[0].issue_id == "PRD-V8-7.7"
    assert "event ID" in result.diagnostics[0].message


def test_global_timing_uses_caller_supplied_event_ids_only() -> None:
    result = migrate_v7_global_timing(
        "after",
        source_contract="ntruth-causal-context/7.0.0",
        subject_event_id="EVT-APPLY-01",
        reference_event_id="EVT-SPLIT-02",
        evidence_refs=("EV-TIMING-01",),
    )
    assert result.value is not None
    assert result.value.subject_event_id == "EVT-APPLY-01"
    assert result.value.reference_event_id == "EVT-SPLIT-02"
    assert result.value.relation is TemporalRelation.AFTER
