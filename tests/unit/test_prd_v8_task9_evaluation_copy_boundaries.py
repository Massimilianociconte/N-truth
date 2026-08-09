from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, PydanticDeprecatedSince20, ValidationError

import ntruth.evaluation_v8 as evaluation
from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

base = importlib.import_module("test_prd_v8_task7_evaluation")
fix1 = importlib.import_module("test_prd_v8_task7_evaluation_fix1")


def _observed() -> evaluation.ReportEvaluationSnapshot:
    return base._snapshot(
        claims=(
            base._claim(
                "C-1",
                state=DeterminabilityState.DETERMINATE,
                value="evaluated",
            ),
        )
    )


def _reference_context(
    *,
    independent: bool,
) -> tuple[
    evaluation.ReportEvaluationSnapshot,
    evaluation.IndependentReportReference,
    KnowledgeValue[evaluation.IndependentReportReference],
    evaluation.ReferenceStabilityReport | None,
]:
    observed = _observed()
    stability = fix1._complete_stability_report() if independent else None
    purpose = (
        evaluation.IndependentReferencePurpose.INDEPENDENT_EVALUATION
        if independent
        else evaluation.IndependentReferencePurpose.CONFORMANCE_ONLY
    )
    reference = evaluation.build_independent_report_reference(
        reference_id="REF-INDEPENDENT" if independent else "REF-CONFORMANCE",
        purpose=purpose,
        report_scope_id=observed.report_id,
        snapshot=observed,
        source_record_ids=("SOURCE-REFERENCE",),
        evidence_ids=("E-REFERENCE",),
        reviewer_actor_ids=("REVIEWER-INDEPENDENT",),
        reference_stability_report=stability,
    )
    reference_value = KnowledgeValue[evaluation.IndependentReportReference](
        knowledge_state=KnowledgeState.PRESENT,
        value=reference,
        evidence_ids=("E-REFERENCE",),
        query_scope_id=observed.report_id,
    )
    return observed, reference, reference_value, stability


def _end_to_end_result() -> evaluation.EndToEndEvaluationReport:
    observed, _reference, reference_value, stability = _reference_context(independent=True)
    assert stability is not None
    return evaluation.evaluate_end_to_end(
        observed,
        reference_value,
        reference_stability_reports=(stability,),
    )


def _blind_audit_result() -> evaluation.BlindResidualAuditResult:
    sample = evaluation.ResidualAuditSampleItem(
        report_id="REPORT-1",
        query_id="IQ-1",
        claim_id="C-1",
        reference_id="REF-1",
    )
    protocol = evaluation.BlindResidualAuditProtocol(
        protocol_id="AUDIT-COPY-BOUNDARY",
        sample_manifest_checksum=base._digest("audit-copy-boundary"),
        sample_items=(sample,),
        strata=tuple(evaluation.ResidualAuditStratum),
        blind_to_original_output=True,
        role_assignments=base._audit_assignments(auditor="AUDITOR-COPY-BOUNDARY"),
        evidence_ids=("E-AUDIT",),
    )
    finding = fix1._audit_finding(
        report_id=sample.report_id,
        query_id=sample.query_id,
        claim_id=sample.claim_id,
        reference_id=sample.reference_id,
    )
    return evaluation.summarize_blind_residual_audit(protocol, (finding,))


def _all_governed_outputs() -> tuple[BaseModel, ...]:
    _observed_snapshot, reference, _reference_value, _stability = _reference_context(
        independent=False
    )
    return (
        reference,
        _end_to_end_result(),
        _blind_audit_result(),
        fix1._complete_stability_report(),
    )


def _unsafe_framework_construct(model: BaseModel, **updates: Any) -> BaseModel:
    payload = model.model_dump(mode="python", round_trip=True)
    payload.update(updates)
    return BaseModel.model_construct.__func__(type(model), **payload)


@pytest.mark.parametrize("deep", (False, True))
def test_governed_outputs_keep_valid_normal_and_deep_model_copies(deep: bool) -> None:
    """Catches hardening the bypass by breaking ordinary validated model copies."""

    for output in _all_governed_outputs():
        copied = output.model_copy(deep=deep)

        assert copied == output
        assert copied is not output
        assert type(output).model_validate(copied.model_dump(mode="python")) == output


@pytest.mark.parametrize("deep", (False, True))
def test_governed_outputs_keep_valid_normal_and_deep_deprecated_copies(deep: bool) -> None:
    """Catches removing deprecated-copy compatibility instead of validating it."""

    for output in _all_governed_outputs():
        with pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"):
            copied = output.copy(deep=deep)

        assert copied == output
        assert copied is not output
        assert type(output).model_validate(copied.model_dump(mode="python")) == output


@pytest.mark.parametrize("projection", ("include", "exclude"))
def test_governed_output_deprecated_copy_rejects_partial_models(projection: str) -> None:
    """Catches include/exclude producing a serializable partial governed result."""

    for output in _all_governed_outputs():
        kwargs = {projection: {"content_checksum"}}
        with (
            pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"),
            pytest.raises(TypeError, match="partial evaluation output copies are forbidden"),
        ):
            output.copy(**kwargs)


def _evaluation_mutation(
    target: str,
) -> tuple[BaseModel, dict[str, Any]]:
    if target == "end-scientific-use":
        return _end_to_end_result(), {"scientific_use_permitted": True}
    if target == "end-hold":
        result = _end_to_end_result()
        return result, {
            "blockers": tuple(
                blocker
                for blocker in result.blockers
                if blocker.issue_id != evaluation.EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID
            )
        }
    if target == "end-checksum":
        return _end_to_end_result(), {"content_checksum": "0" * 64}
    if target == "audit-scientific-use":
        return _blind_audit_result(), {"scientific_use_permitted": True}
    if target == "audit-hold":
        return _blind_audit_result(), {
            "blocker": ScientificReviewRequirement(
                issue_id="SRR-CALLER-REISSUED",
                rationale="Caller attempted to replace the scientific HOLD.",
            )
        }
    if target == "audit-checksum":
        return _blind_audit_result(), {"content_checksum": "0" * 64}
    if target == "reference-checksum":
        return _reference_context(independent=False)[1], {"content_checksum": "0" * 64}
    return fix1._complete_stability_report(), {"content_checksum": "0" * 64}


@pytest.mark.parametrize("copy_method", ("model_copy", "copy"))
@pytest.mark.parametrize(
    "target",
    (
        "end-scientific-use",
        "end-hold",
        "end-checksum",
        "audit-scientific-use",
        "audit-hold",
        "audit-checksum",
        "reference-checksum",
        "stability-checksum",
    ),
)
def test_governed_output_copy_updates_are_revalidated(
    copy_method: str,
    target: str,
) -> None:
    """Catches copy updates bypassing HOLD, Literal[False], or content addressing."""

    output, update = _evaluation_mutation(target)
    copier: Callable[..., BaseModel] = getattr(output, copy_method)
    if copy_method == "copy":
        with (
            pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"),
            pytest.raises(ValidationError),
        ):
            copier(update=update)
    else:
        with pytest.raises(ValidationError):
            copier(update=update)


@pytest.mark.parametrize(
    "target",
    (
        "end-scientific-use",
        "audit-scientific-use",
        "reference-checksum",
        "stability-checksum",
    ),
)
def test_governed_output_model_construct_revalidates_mutations(target: str) -> None:
    """Catches the public model_construct boundary bypassing output validators."""

    output, update = _evaluation_mutation(target)
    payload = output.model_dump(mode="python", round_trip=True)
    payload.update(update)

    with pytest.raises(ValidationError):
        type(output).model_construct(**payload)


def test_governed_output_model_construct_accepts_only_a_complete_valid_payload() -> None:
    """Catches replacing model_construct with an unusable blanket prohibition."""

    for output in _all_governed_outputs():
        reconstructed = type(output).model_construct(
            **output.model_dump(mode="python", round_trip=True)
        )

        assert reconstructed == output
        assert reconstructed is not output


def test_build_reference_revalidates_nested_stability_report_before_addressing() -> None:
    """Catches an internally stale reviewed conclusion being pinned as external authority."""

    observed = _observed()
    stability = fix1._complete_stability_report()
    changed_conclusion = stability.reference_stability_conclusion.model_copy(
        update={
            "value": (
                evaluation.ReferenceStabilityConclusion.REVIEWED_OUTSIDE_PREREGISTERED_DECISION_REGION
            )
        }
    )
    forged = _unsafe_framework_construct(
        stability,
        reference_stability_conclusion=changed_conclusion,
        blocker=None,
    )

    with pytest.raises(ValidationError, match="reference stability report checksum mismatch"):
        evaluation.build_independent_report_reference(
            reference_id="REF-FORGED-STABILITY",
            purpose=evaluation.IndependentReferencePurpose.INDEPENDENT_EVALUATION,
            report_scope_id=observed.report_id,
            snapshot=observed,
            source_record_ids=("SOURCE-REFERENCE",),
            evidence_ids=("E-REFERENCE",),
            reviewer_actor_ids=("REVIEWER-INDEPENDENT",),
            reference_stability_report=forged,
        )


def test_stale_present_stability_report_cannot_resolve_evaluation() -> None:
    """Catches PRESENT plus blocker=None resolving despite a stale addressed checksum."""

    observed, _reference, reference_value, stability = _reference_context(independent=True)
    assert stability is not None
    changed_conclusion = stability.reference_stability_conclusion.model_copy(
        update={
            "value": (
                evaluation.ReferenceStabilityConclusion.REVIEWED_OUTSIDE_PREREGISTERED_DECISION_REGION
            )
        }
    )
    forged = _unsafe_framework_construct(
        stability,
        reference_stability_conclusion=changed_conclusion,
        blocker=None,
    )

    result = evaluation.evaluate_end_to_end(
        observed,
        reference_value,
        reference_stability_reports=(forged,),
    )

    assert evaluation.REFERENCE_STABILITY_REVIEW_ISSUE_ID in {
        blocker.issue_id for blocker in result.blockers
    }


def test_outer_knowledge_value_cannot_promote_conformance_reference_purpose() -> None:
    """Catches a nested purpose promotion being consumed through a valid-looking outer value."""

    observed, reference, reference_value, _stability = _reference_context(independent=False)
    promoted = _unsafe_framework_construct(
        reference,
        purpose=evaluation.IndependentReferencePurpose.INDEPENDENT_EVALUATION,
    )
    forged_outer = _unsafe_framework_construct(reference_value, value=promoted)

    with pytest.raises(ValidationError):
        evaluation.evaluate_end_to_end(observed, forged_outer)


def test_valid_reviewed_stability_can_resolve_but_never_remove_scientific_hold() -> None:
    """Catches hardening that makes genuine reviewed authority impossible or removes HOLD."""

    observed, _reference, reference_value, stability = _reference_context(independent=True)
    assert stability is not None

    result = evaluation.evaluate_end_to_end(
        observed,
        reference_value,
        reference_stability_reports=(stability,),
    )

    blocker_ids = {blocker.issue_id for blocker in result.blockers}
    assert evaluation.REFERENCE_STABILITY_REVIEW_ISSUE_ID not in blocker_ids
    assert evaluation.EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID in blocker_ids
    assert result.scientific_use_permitted is False
