"""Export and plan freeze for Quick Design Session (PRD v7 §6.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ntruth.quick_design.session import QuickDesignResult
from ntruth.schemas.core import content_checksum


def export_for_biostatistician(result: QuickDesignResult) -> dict[str, Any]:
    """JSON-serialisable packet for biostatistician handoff.

    Contains design facts, open questions and sample sheet - not a scientific
    validation claim and not an independent_n verdict.
    """
    bootstrap = result.bootstrap
    payload: dict[str, Any] = {
        "export_kind": "quick_design_biostat_handoff",
        "schema_version": bootstrap.schema_version,
        "domain": bootstrap.domain,
        "experiment_block_id": bootstrap.experiment_block_id,
        "factor_id": bootstrap.factor_id,
        "factor_levels": list(bootstrap.factor_levels),
        "endpoint_id": bootstrap.endpoint_id,
        "primary_contrast_id": bootstrap.primary_contrast_id,
        "allocation_level": bootstrap.allocation_level,
        "application_level": bootstrap.application_level,
        "independently_assigned": bootstrap.independently_assigned,
        "source_preparation_id": bootstrap.source_preparation_id,
        "determinability_derived": (
            bootstrap.determinability_derived.value
            if bootstrap.determinability_derived is not None
            and hasattr(bootstrap.determinability_derived, "value")
            else bootstrap.determinability_derived
        ),
        "determinability_reviewed": bootstrap.determinability_reviewed,
        "primary_question": result.primary_question,
        "missing_decisive_fact": (
            bootstrap.missing_decisive_fact.model_dump(mode="json")
            if bootstrap.missing_decisive_fact
            else None
        ),
        "independence": bootstrap.independence.model_dump(mode="json"),
        "causal_context": (
            bootstrap.causal_context.model_dump(mode="json") if bootstrap.causal_context else None
        ),
        "inferential_query": (
            bootstrap.inferential_query.model_dump(mode="json")
            if bootstrap.inferential_query
            else None
        ),
        "counts": [c.model_dump(mode="json") for c in bootstrap.counts],
        "units": [u.model_dump(mode="json") for u in bootstrap.units],
        "relations": [r.model_dump(mode="json") for r in bootstrap.relations],
        "id_convention": result.id_convention,
        "methods_draft": result.methods_draft,
        "sample_sheet_csv": result.sample_sheet_csv,
        "plan_frozen": result.plan_frozen,
        "disclaimer": (
            "Quick Design export is a planning aid. It does not certify "
            "experimental validity, final independent n, or scientific readiness."
        ),
    }
    payload["export_checksum"] = content_checksum(payload)
    return payload


def freeze_plan(result: QuickDesignResult) -> QuickDesignResult:
    """Freeze the current design snapshot (append-only semantic: new result)."""
    if result.plan_frozen:
        return result
    payload = export_for_biostatistician(result)
    payload["frozen_at"] = datetime.now(tz=UTC).isoformat()
    payload["plan_frozen"] = True
    payload["export_checksum"] = content_checksum(
        {k: v for k, v in payload.items() if k != "export_checksum"}
    )
    return QuickDesignResult(
        bootstrap=result.bootstrap,
        determinability=result.determinability,
        sample_sheet_csv=result.sample_sheet_csv,
        id_convention=result.id_convention,
        methods_draft=result.methods_draft,
        primary_question=result.primary_question,
        plan_frozen=True,
        export_payload=payload,
    )
