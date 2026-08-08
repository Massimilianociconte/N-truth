"""PRD v8 design-adequacy rules evaluated after scientific claims."""

from __future__ import annotations

from ntruth.derivation_theory.runtime import V8DerivationInput
from ntruth.schemas.adequacy import DesignAdequacyFinding
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.core import stable_id
from ntruth.schemas.knowledge import KnowledgeState


def evaluate_design_adequacy(
    request: V8DerivationInput,
    claims: DerivedClaimSet,
) -> tuple[DesignAdequacyFinding, ...]:
    """Emit a separate finding without feeding it back into determinability."""

    if claims.inferential_query_id != request.query.id:
        raise ValueError("adequacy evaluation and DerivedClaimSet query scopes differ")
    interference = request.predicate_values["interference_status"]
    if interference.knowledge_state is not KnowledgeState.PRESENT:
        return ()
    finding_type = {
        "documented": "INTERFERENCE_DOCUMENTED",
        "possible": "INTERFERENCE_POSSIBLE",
        "no_known_path": "INTERFERENCE_NO_KNOWN_PATH",
        "unknown": "INTERFERENCE_UNKNOWN",
    }.get(str(interference.value))
    if finding_type is None or not interference.evidence_ids:
        return ()
    return (
        DesignAdequacyFinding(
            finding_id=stable_id("adequacy", request.query.id, finding_type),
            inferential_query_id=request.query.id,
            finding_type=finding_type,
            rationale="Interference is reported separately from claim determinability.",
            theory_clause_ids=("DT-E-INTERFERENCE-ESTIMAND",),
            rule_ids=("ADEQUACY-INTERFERENCE-V8",),
            evidence_ids=interference.evidence_ids,
        ),
    )


__all__ = ["evaluate_design_adequacy"]
