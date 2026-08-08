"""Pinned open-world adequacy evaluation after claim verification."""

from __future__ import annotations

from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.derivation_theory.runtime import V8DerivationInput, rule_content_checksum
from ntruth.schemas.adequacy import DesignAdequacyEvaluation
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.core import stable_id
from ntruth.schemas.execution import V8ExecutionManifest
from ntruth.schemas.support import ScientificReviewRequirement


def evaluate_design_adequacy(
    request: V8DerivationInput,
    claims: DerivedClaimSet,
    *,
    conformance_bundle: ConformanceBundle,
    execution_manifest: V8ExecutionManifest,
) -> tuple[DesignAdequacyEvaluation, ...]:
    """Retain interference epistemics without inventing a good/bad-design verdict."""

    if claims.inferential_query_id != request.query.id:
        raise ValueError("adequacy evaluation and DerivedClaimSet query scopes differ")
    rule = next(
        item
        for item in conformance_bundle.rulebook.rules
        if item.theory_clause_id == "DT-E-INTERFERENCE-ESTIMAND"
    )
    pin = next(
        item for item in execution_manifest.implementation_rules if item.rule_id == rule.rule_id
    )
    if pin.rule_checksum != rule_content_checksum(rule):
        raise ValueError("adequacy implementation rule checksum differs from execution manifest")
    dependency = next(
        claim for claim in claims.claims if claim.claim_type == "INTERFERENCE_ESTIMAND_SUPPORT"
    )
    return (
        DesignAdequacyEvaluation(
            evaluation_id=stable_id(
                "adequacy-evaluation",
                request.query.id,
                execution_manifest.manifest_id,
                rule.rule_id,
            ),
            inferential_query_id=request.query.id,
            axis="INTERFERENCE_STATUS",
            outcome=request.predicate_values["interference_status"],
            rationale=(
                "Interference evidence is retained as an epistemic axis; SRR-V8-017 blocks "
                "a universal design-adequacy verdict or topology resolver."
            ),
            theory_clause_id=rule.theory_clause_id,
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_checksum=pin.rule_checksum,
            dependency_claim_ids=(dependency.claim_id,),
            required_predicates=tuple(item.predicate_id for item in rule.required_predicates),
            irrelevant_predicates=rule.irrelevant_predicates,
            review_requirement=ScientificReviewRequirement(
                issue_id="SRR-V8-017",
                rationale="Interference topology requires a reviewed profile-specific contract.",
            ),
        ),
    )


__all__ = ["evaluate_design_adequacy"]
