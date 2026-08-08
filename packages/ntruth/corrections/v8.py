"""PRD v8 correction boundary: facts may be corrected, derived claims may not."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import model_validator

from ntruth.corrections.json_patch import apply_json_patch, parse_json_patch, parse_pointer
from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.pipeline_v8 import (
    V8PipelineRequest,
    V8PipelineResult,
    run_v8_pipeline,
)
from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.support import (
    RuleChallenge,
    RuleChallengeDecision,
    RuleChallengeDecisionOutcome,
    ScientificReviewRequirement,
)


class DirectDerivedClaimPatchError(ValueError):
    """A deterministic claim can change only through RuleChallenge and re-derivation."""


class RuleChallengeOutcomeReviewRequired(ValueError):
    """The PRD does not yet define this RuleChallenge outcome-to-runtime mapping."""

    def __init__(self, review_requirement: ScientificReviewRequirement) -> None:
        self.review_requirement = review_requirement
        super().__init__("SCIENTIFIC_REVIEW_REQUIRED: RuleChallenge outcome mapping is not closed")


_DERIVED_OUTPUT_ROOTS = frozenset(
    {
        "claims",
        "claim_sets",
        "claim_set",
        "derived_claim",
        "derived_claims",
        "derived_claim_set",
        "derived_claim_sets",
        "design_adequacy_evaluations",
        "design_adequacy_findings",
        "execution_manifest",
        "profile_coverage",
        "report_resolution",
        "scenario_coverages",
    }
)


def reject_direct_derived_claim_patch(
    patch: Sequence[Mapping[str, object]],
) -> None:
    """Reject every RFC 6902 operation whose source or target is derived output."""

    operations = parse_json_patch(tuple(dict(item) for item in patch))
    for operation in operations:
        pointers = (operation.path, operation.from_path)
        for pointer in pointers:
            if pointer is None:
                continue
            tokens = parse_pointer(pointer)
            if any(token in _DERIVED_OUTPUT_ROOTS for token in tokens):
                raise DirectDerivedClaimPatchError(
                    "DerivedClaim output is immutable; submit a RuleChallenge and re-derive "
                    "under reviewed theory/rules versions."
                )


def apply_v8_patch(
    document: Any,
    patch: Sequence[Mapping[str, object]],
) -> Any:
    """The sole v8 patch API always enforces the DerivedClaim immutability boundary."""

    reject_direct_derived_claim_patch(patch)
    return apply_json_patch(document, patch)


class ReDerivationEvent(KernelModel):
    rederivation_id: NonBlankStr
    challenge_id: NonBlankStr
    decision_id: NonBlankStr
    change_record_id: NonBlankStr
    previous_theory_version: NonBlankStr
    new_theory_version: NonBlankStr
    previous_ruleset_version: NonBlankStr
    new_ruleset_version: NonBlankStr
    previous_claim_set_checksum: NonBlankStr
    new_claim_set_checksum: NonBlankStr
    previous_execution_manifest_id: NonBlankStr
    new_execution_manifest_id: NonBlankStr
    outcome_contract_review: ScientificReviewRequirement

    @model_validator(mode="after")
    def _retains_governance_blocker(self) -> ReDerivationEvent:
        if self.outcome_contract_review.issue_id != "SRR-V8-024":
            raise ValueError("RuleChallenge re-derivation must retain blocker SRR-V8-024")
        return self


class V8ReDerivationResult(KernelModel):
    result: V8PipelineResult
    event: ReDerivationEvent


def rederive_after_rule_challenge(
    *,
    previous: V8PipelineResult,
    request: V8PipelineRequest,
    conformance_bundle: ConformanceBundle,
    challenge: RuleChallenge,
    decision: RuleChallengeDecision,
) -> V8ReDerivationResult:
    """Re-run reviewed successor contracts; never mutate the frozen claim set."""

    if decision.challenge_id != challenge.challenge_id:
        raise ValueError("RuleChallengeDecision does not resolve the supplied RuleChallenge")
    if decision.outcome is not RuleChallengeDecisionOutcome.ACCEPTED:
        raise RuleChallengeOutcomeReviewRequired(decision.outcome_contract_review)
    if decision.created_at < challenge.created_at:
        raise ValueError("RuleChallengeDecision cannot precede its RuleChallenge")
    if decision.outcome_contract_review.issue_id != "SRR-V8-024":
        raise ValueError("RuleChallengeDecision must retain blocker SRR-V8-024")
    theory = conformance_bundle.theory
    expected_ruleset_version = (
        f"{conformance_bundle.rulebook.rulebook_id}-{conformance_bundle.rulebook.rulebook_version}"
    )
    if decision.resulting_theory_version != theory.theory_version:
        raise ValueError("decision and successor Derivation Theory version differ")
    if decision.resulting_ruleset_version != expected_ruleset_version:
        raise ValueError("decision and successor Rulebook version differ")
    if request.runtime_ruleset_version != expected_ruleset_version:
        raise ValueError("decision and successor runtime rules version differ")
    if theory.theory_version == challenge.theory_version:
        raise ValueError("accepted RuleChallenge requires a successor Derivation Theory version")
    if request.runtime_ruleset_version == challenge.ruleset_version:
        raise ValueError("accepted RuleChallenge requires a successor runtime rules version")
    if previous.execution_manifest.theory_version != challenge.theory_version:
        raise ValueError("frozen execution manifest and RuleChallenge Theory version differ")
    if (
        f"{previous.execution_manifest.rulebook_id}-"
        f"{previous.execution_manifest.rulebook_version}" != challenge.ruleset_version
    ):
        raise ValueError("frozen execution manifest and RuleChallenge rules version differ")

    frozen_claim = next(
        (
            claim
            for claim in previous.claim_set.claims
            if claim.claim_id == challenge.derived_claim_id
        ),
        None,
    )
    if frozen_claim is None:
        raise ValueError("RuleChallenge references no claim in the frozen DerivedClaimSet")
    if content_checksum(frozen_claim.model_dump(mode="json")) != challenge.frozen_claim_checksum:
        raise ValueError("RuleChallenge frozen claim checksum does not match the prior output")
    if frozen_claim.theory_version != challenge.theory_version:
        raise ValueError("RuleChallenge theory version does not match the frozen claim")
    if frozen_claim.ruleset_version != challenge.ruleset_version:
        raise ValueError("RuleChallenge rules version does not match the frozen claim")

    result = run_v8_pipeline(request, conformance_bundle=conformance_bundle)
    event = ReDerivationEvent(
        rederivation_id=decision.rederivation_record_id,
        challenge_id=challenge.challenge_id,
        decision_id=decision.decision_id,
        change_record_id=decision.change_record_id,
        previous_theory_version=challenge.theory_version,
        new_theory_version=theory.theory_version,
        previous_ruleset_version=challenge.ruleset_version,
        new_ruleset_version=request.runtime_ruleset_version,
        previous_claim_set_checksum=content_checksum(previous.claim_set.model_dump(mode="json")),
        new_claim_set_checksum=content_checksum(result.claim_set.model_dump(mode="json")),
        previous_execution_manifest_id=previous.execution_manifest.manifest_id,
        new_execution_manifest_id=result.execution_manifest.manifest_id,
        outcome_contract_review=decision.outcome_contract_review,
    )
    return V8ReDerivationResult(result=result, event=event)


__all__ = [
    "DirectDerivedClaimPatchError",
    "ReDerivationEvent",
    "RuleChallengeOutcomeReviewRequired",
    "V8ReDerivationResult",
    "apply_v8_patch",
    "rederive_after_rule_challenge",
    "reject_direct_derived_claim_patch",
]
