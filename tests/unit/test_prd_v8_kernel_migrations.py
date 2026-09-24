"""Fail-closed v7 to v8 Core Semantic Kernel migration contracts."""

from __future__ import annotations

from importlib import import_module


def _knowledge() -> object:
    return import_module("ntruth.schemas.knowledge")


def _support() -> object:
    return import_module("ntruth.schemas.support")


def _migration() -> object:
    return import_module("ntruth.migrations.v7_to_v8")


def test_v7_null_without_field_policy_requires_scientific_review() -> None:
    """Catches guessing UNKNOWN versus NOT_REPORTED for a legacy null."""
    migration = _migration()
    result = migration.migrate_v7_scientific_field(
        field_name="experimental_unit",
        value=None,
        source_contract="ntruth-v7-unit-assessment",
    )
    assert result.value is None
    assert result.requires_scientific_review is True
    assert result.diagnostics[0].code.value == "SCIENTIFIC_REVIEW_REQUIRED"


def test_v7_null_uses_only_explicit_field_specific_policy() -> None:
    """Catches applying a global legacy-null mapping."""
    knowledge = _knowledge()
    migration = _migration()
    result = migration.migrate_v7_scientific_field(
        field_name="experimental_unit",
        value=None,
        source_contract="ntruth-v7-unit-assessment",
        null_semantics=knowledge.KnowledgeState.UNKNOWN,
        migration_rule_id="MIG-V7-EU-NULL-UNKNOWN",
        rationale="The v7 field does not preserve enough information to resolve the value.",
        claim_scope_id="CLAIM-EU-001",
    )
    assert result.requires_scientific_review is False
    assert result.value is not None
    assert result.value.knowledge_state is knowledge.KnowledgeState.UNKNOWN
    assert result.lineage[0].migration_rule_id == "MIG-V7-EU-NULL-UNKNOWN"


def test_v7_nonempty_value_requires_evidence_before_present() -> None:
    """Catches promoting an untraceable legacy scalar to PRESENT."""
    migration = _migration()
    blocked = migration.migrate_v7_scientific_field(
        field_name="experimental_unit",
        value="well",
        source_contract="ntruth-v7-unit-assessment",
    )
    assert blocked.value is None
    assert blocked.requires_scientific_review

    migrated = migration.migrate_v7_scientific_field(
        field_name="experimental_unit",
        value="well",
        evidence_ids=("EV-001",),
        source_contract="ntruth-v7-unit-assessment",
    )
    assert migrated.value is not None
    assert migrated.value.value == "well"


def test_v7_blank_or_empty_never_becomes_scientific_absence() -> None:
    """Catches interpreting empty legacy containers as ABSENT_EXPLICIT."""
    migration = _migration()
    for legacy_value in ("", "   ", (), [], {}):
        result = migration.migrate_v7_scientific_field(
            field_name="scientific_value",
            value=legacy_value,
            source_contract="ntruth-v7",
        )
        assert result.value is None
        assert result.requires_scientific_review


def test_cross_vocabulary_support_conversion_fails_closed_without_review() -> None:
    """Catches inventing the unresolved SRR-V8-001 SupportGrade mapping."""
    support = _support()
    migration = _migration()
    source = support.SupportGrade(
        vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
        token="DIRECT_SINGLE_SOURCE",
    )
    result = migration.migrate_support_grade(
        source,
        target_vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1,
    )
    assert result.value is None
    assert result.requires_scientific_review
    assert result.diagnostics[0].issue_id == "SRR-V8-001"


def test_same_vocabulary_support_grade_round_trips_without_mapping() -> None:
    """Catches needless token rewriting within an already pinned vocabulary."""
    support = _support()
    migration = _migration()
    source = support.SupportGrade(
        vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1,
        token="DOMAIN_EXPERT_INTERPRETATION",
    )
    result = migration.migrate_support_grade(
        source,
        target_vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1,
    )
    assert result.value == source
    assert result.requires_scientific_review is False


def test_reviewed_support_mapping_records_decision_lineage() -> None:
    """Catches a cross-vocabulary conversion without an auditable review decision."""
    support = _support()
    migration = _migration()
    source = support.SupportGrade(
        vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
        token="ASSERTION_ONLY",
    )
    result = migration.migrate_support_grade(
        source,
        target_vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1,
        reviewed_mapping={"ASSERTION_ONLY": "DOCUMENT_ASSERTION_ONLY"},
        review_decision_id="DEC-SRR-V8-001-001",
    )
    assert result.value is not None
    assert result.value.token == "DOCUMENT_ASSERTION_ONLY"
    assert result.lineage[0].review_decision_id == "DEC-SRR-V8-001-001"


def test_legacy_claim_keys_require_explicit_alias_migration_with_lineage() -> None:
    """Catches accepting query_id/determinability directly in the v8 claim model."""
    migration = _migration()
    result = migration.migrate_v7_claim_field_names(
        {
            "claim_id": "CLAIM-EU-001",
            "query_id": "IQ-001",
            "determinability": "DETERMINATE",
        },
        source_contract="ntruth-prd-v7-derived-claim",
    )
    assert result.value is not None
    assert result.value["inferential_query_id"] == "IQ-001"
    assert result.value["determinability_state"] == "DETERMINATE"
    assert "query_id" not in result.value
    assert "determinability" not in result.value
    assert {item.migration_rule_id for item in result.lineage} == {
        "SRR-V8-002-query-id",
        "SRR-V8-004-determinability",
    }


def test_conflicting_legacy_and_canonical_claim_keys_fail_closed() -> None:
    """Catches silently choosing one of two incompatible query identifiers."""
    migration = _migration()
    result = migration.migrate_v7_claim_field_names(
        {
            "query_id": "IQ-LEGACY",
            "inferential_query_id": "IQ-CANONICAL",
        },
        source_contract="ntruth-prd-v7-derived-claim",
    )
    assert result.value is None
    assert result.requires_scientific_review
    assert result.diagnostics[0].issue_id == "SRR-V8-002"
