"""Rights/eligibility and GOLD-pilot contracts for the four named sources."""

from __future__ import annotations

import pytest

from ntruth.data.gold_pilot import (
    REQUIRED_SPLIT_KEYS,
    AdjudicationRecord,
    AmbiguousAnswer,
    DecisiveFieldReview,
    GoldPilotRecord,
    GoldPilotStatus,
    HumanClosureInputs,
    IndependentAnnotation,
    ProvenanceBundle,
    SplitKeys,
    evaluate_gold_promotion,
    measure_agreement,
)
from ntruth.data.rights import (
    CANONICAL_SOURCES,
    evaluate_record_eligibility,
    load_source_rights,
    record_is_eligible,
)
from ntruth.task_corpora.authority import AuthorityLevel


def _annotation(role: str, annotation_id: str, **payload: object) -> IndependentAnnotation:
    return IndependentAnnotation(
        annotator_role=role,
        annotation_id=annotation_id,
        payload=dict(payload) or {"FactorRole": "UNKNOWN"},
        ambiguous=AmbiguousAnswer.INDETERMINATE,
        created_at="2026-08-13T00:00:00Z",
    )


def _split_keys() -> SplitKeys:
    return SplitKeys(
        experiment_bundle_id="bundle-1",
        paper_id="10.0000/example",
        version="v1",
        laboratory="lab-a",
        semantic_family="family-x",
    )


def _provenance() -> ProvenanceBundle:
    return ProvenanceBundle(
        source_id="sourcedata",
        source_asset_id="asset-1",
        source_sha256="a" * 64,
        license_or_authorization_id="pending",
        guideline_version="gold-pilot-v1",
    )


def test_four_sources_have_per_asset_rights_and_stay_ineligible() -> None:
    catalog = load_source_rights()
    assert set(catalog) == set(CANONICAL_SOURCES)
    for source, record in catalog.items():
        assert record.asset_id
        assert record.license_status
        assert record.dua.training in {False, "unknown"} or record.blockers
        assert record.steward_authorization is None
        assert record.training_eligible is False
        assert record.evaluation_eligible is False
        assert record_is_eligible(record, use="training") is False
        assert record_is_eligible(record, use="evaluation") is False
        eligible, blockers = evaluate_record_eligibility(source)
        assert eligible is False
        assert "identity_incomplete" in blockers
        assert any(
            item in blockers
            for item in (
                "license_incomplete",
                "dua_missing",
                "training_unknown",
                "training_forbidden",
                "evaluation_unknown",
                "evaluation_forbidden",
                "redistribution_unknown",
                "redistribution_forbidden",
            )
        )


def test_complete_identity_without_grants_stays_ineligible() -> None:
    eligible, blockers = evaluate_record_eligibility(
        "CRAFT",
        identity={
            "paper_id": "10.1186/1471-2105-10-s1-s1",
            "experiment_id": "craft-article-1",
            "family_id": "craft-family-1",
            "source_asset_id": "craft-v5.0.2",
            "source_ref": "v5.0.2",
        },
    )
    assert eligible is False
    assert "identity_incomplete" not in blockers
    assert "steward_authorization_absent" in blockers


def test_gold_pilot_requires_dual_annotation_agreement_before_adjudication() -> None:
    first = _annotation("annotator-a", "ann-1", FactorRole="UNKNOWN")
    second = _annotation("annotator-b", "ann-2", FactorRole="ASSIGNED_INTERVENTION")
    agreement = measure_agreement(first, second, measured_at="2026-08-13T01:00:00Z")
    assert agreement.measured_before_adjudication is True
    assert "FactorRole" in agreement.decisive_field_disagreements

    with pytest.raises(ValueError, match="adjudication requires pre-adjudication agreement"):
        GoldPilotRecord(
            record_id="pilot-1",
            status=GoldPilotStatus.ADJUDICATION_RECORDED,
            annotations=(first, second),
            agreement=None,
            adjudication=AdjudicationRecord(
                adjudication_id="adj-1",
                adjudicator_role="adjudicator",
                rationale="resolve role",
                resolution={"FactorRole": "UNKNOWN"},
                recorded_at="2026-08-13T02:00:00Z",
            ),
            provenance=_provenance(),
            split_keys=_split_keys(),
        )


def test_gold_pilot_never_writes_gold_and_keeps_insufficient_states() -> None:
    first = _annotation("annotator-a", "ann-1")
    second = _annotation("annotator-b", "ann-2")
    agreement = measure_agreement(first, second, measured_at="2026-08-13T01:00:00Z")
    record = GoldPilotRecord(
        record_id="pilot-1",
        status=GoldPilotStatus.PILOT_COMPLETE_NOT_GOLD,
        annotations=(first, second),
        agreement=agreement,
        adjudication=AdjudicationRecord(
            adjudication_id="adj-1",
            adjudicator_role="adjudicator",
            rationale="insufficient evidence remains insufficiente",
            resolution={"answer": AmbiguousAnswer.INSUFFICIENT.value},
            recorded_at="2026-08-13T02:00:00Z",
        ),
        decisive_review=DecisiveFieldReview(
            fields_reviewed=(
                "FactorRole",
                "ContrastType",
                "ContrastSupportClaim",
                "ObservedEvidenceScope",
                "ExperimentalUnitClaim",
            ),
            reviewer_role="scientific-owner",
            complete=True,
            reviewed_at="2026-08-13T03:00:00Z",
        ),
        provenance=_provenance(),
        split_keys=_split_keys(),
        rights_eligible=False,
    )
    assert record.authority_level is AuthorityLevel.CANDIDATE
    assert record.gold_quantity_declared is None
    for key in REQUIRED_SPLIT_KEYS:
        assert getattr(record.split_keys, key)

    dumped = record.model_dump(mode="json")
    dumped["authority_level"] = AuthorityLevel.NTRUTH_GOLD.value
    with pytest.raises(ValueError, match=r"cannot set AuthorityLevel\.NTRUTH_GOLD"):
        GoldPilotRecord.model_validate(dumped)

    assert evaluate_gold_promotion(record)["promoted"] is False
    closure = HumanClosureInputs(
        steward_signed_artifact_sha256="b" * 64,
        steward_role="data-steward",
        closed_at="2026-08-13T04:00:00Z",
    )
    decision = evaluate_gold_promotion(record, closure)
    assert decision["promoted"] is False
    assert decision["authority_level"] != AuthorityLevel.NTRUTH_GOLD.value
