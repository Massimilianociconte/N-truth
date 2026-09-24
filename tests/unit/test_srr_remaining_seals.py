"""Sigilli SRR restanti: scanner esempi PRD, boundary qualitativo, freeze SRR-021."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.conformance.examples import _appendix_a_diagnostics
from ntruth.conformance.external_references import (
    EXTERNAL_REFERENCE_REVIEW_ISSUE_ID,
    ExternalReferenceFreeze,
    ExternalReferenceResource,
)
from ntruth.schemas.block_boundary import BlockBoundaryStatus
from ntruth.schemas.support import ScientificReviewRequirement

# ------------------------------------------------ SRR-005/006/007 scanner


def test_appendix_a_scanner_flags_the_inconsistent_prd_examples() -> None:
    verbatim = """
    report_resolution_state: MULTIPLE_PLAUSIBLE_GRAPHS
    claim_type: DESIGN_ADEQUACY_FINDING
scenario_set:
  exhaustive: true
    query_id: legacy
    determinability: DETERMINATE
    """
    diagnostics = _appendix_a_diagnostics(verbatim)
    assert {"SRR-V8-002", "SRR-V8-004", "SRR-V8-005", "SRR-V8-006", "SRR-V8-007"} <= diagnostics


def test_clean_example_produces_no_false_diagnostics() -> None:
    verbatim = """
    inferential_query_id: query-1
    determinability_state: DETERMINATE
    required_predicates: [p]
    irrelevant_predicates: []
    """
    assert _appendix_a_diagnostics(verbatim) == set()


# ------------------------------------------------ SRR-016 qualitative only


def test_block_boundary_status_is_qualitative_without_probabilities() -> None:
    assert {item.value for item in BlockBoundaryStatus} == {
        "CONFIRMED",
        "CANDIDATE",
        "CONFLICTING",
    }
    from ntruth.schemas.block_boundary import ExperimentBlockBoundaryRecord

    numeric_confidence_fields = [
        name
        for name, field in ExperimentBlockBoundaryRecord.model_fields.items()
        if "confidence" in name
    ]
    assert numeric_confidence_fields == []


# ------------------------------------------------ SRR-021 freeze mechanism


def _review() -> ScientificReviewRequirement:
    return ScientificReviewRequirement(
        issue_id=EXTERNAL_REFERENCE_REVIEW_ISSUE_ID,
        rationale="rights closure and independent review are external",
    )


def _resource(rid: str = "driver-about") -> ExternalReferenceResource:
    return ExternalReferenceResource(
        resource_id=rid,
        title="DRIVER recommendations",
        canonical_url="https://nc3rs.org.uk/3rs-resources/driver-recommendations/about",
        retrieval_sha256="a" * 64,
        retrieved_at="2026-08-23",
        license_note="cite-only per NC3Rs terms; no reproduction",
        mapped_clause_ids=("DT-A-ASSIGNMENT-UNIT",),
    )


def test_empty_freeze_is_valid_but_blocked() -> None:
    freeze = ExternalReferenceFreeze(
        freeze_id="extref",
        freeze_version="0.1.0",
        resources=(),
        review_requirement=_review(),
        declared_checksum="b" * 64,
    )
    assert freeze.is_empty
    assert freeze.resources_for_clause("DT-A-ASSIGNMENT-UNIT") == ()


def test_resource_requires_real_hash_and_unique_mapping() -> None:
    with pytest.raises(ValidationError):
        _resource().__class__.model_validate(
            {
                **_resource().model_dump(mode="json"),
                "retrieval_sha256": "ZZ" * 32,
            }
        )
    with pytest.raises(ValidationError):
        ExternalReferenceFreeze(
            freeze_id="extref",
            freeze_version="0.1.0",
            resources=(_resource("dup"), _resource("dup")),
            review_requirement=_review(),
            declared_checksum="b" * 64,
        )


def test_freeze_rejects_foreign_review_issue() -> None:
    with pytest.raises(ValidationError):
        ExternalReferenceFreeze(
            freeze_id="extref",
            freeze_version="0.1.0",
            resources=(_resource(),),
            review_requirement=ScientificReviewRequirement(
                issue_id="SRR-V8-999", rationale="wrong blocker"
            ),
            declared_checksum="b" * 64,
        )


def test_clause_mapping_projection() -> None:
    freeze = ExternalReferenceFreeze(
        freeze_id="extref",
        freeze_version="0.1.0",
        resources=(
            _resource("driver"),
            _resource("arrive").model_copy(
                update={"mapped_clause_ids": ("DT-B-EXPERIMENTAL-UNIT",)}
            ),
        ),
        review_requirement=_review(),
        declared_checksum="b" * 64,
    )
    assert [item.resource_id for item in freeze.resources_for_clause("DT-A-ASSIGNMENT-UNIT")] == [
        "driver"
    ]
