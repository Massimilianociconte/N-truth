"""Explicit, audited compatibility adapters into PRD v8 contracts."""

from ntruth.migrations.v7_to_v8 import (
    MigrationDiagnostic,
    MigrationDiagnosticCode,
    MigrationLineage,
    MigrationResult,
    migrate_support_grade,
    migrate_v7_claim_field_names,
    migrate_v7_count_kind,
    migrate_v7_global_timing,
    migrate_v7_scientific_field,
)

__all__ = [
    "MigrationDiagnostic",
    "MigrationDiagnosticCode",
    "MigrationLineage",
    "MigrationResult",
    "migrate_support_grade",
    "migrate_v7_claim_field_names",
    "migrate_v7_count_kind",
    "migrate_v7_global_timing",
    "migrate_v7_scientific_field",
]
