"""Clause-ID based PRD v8 derivation runtime, independent from Rulebook metadata."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from ntruth.conformance.harness import ConformanceReport, evaluate_conformance
from ntruth.derivation_theory.contracts import ConformanceBundle, DerivationTheory, TheoryClause
from ntruth.derivation_theory.loader import (
    THEORY_FILENAME,
    load_canonical_bundle,
    load_derivation_theory_file,
    load_installed_bundle,
)
from ntruth.schemas.causal_context import QueryCausalEventAggregate
from ntruth.schemas.claims import (
    DerivedClaim,
    DerivedClaimSet,
    DeterminabilityState,
    IrrelevantPredicate,
    PredicateProofReference,
    ProofTraceStep,
)
from ntruth.schemas.core import stable_id
from ntruth.schemas.coverage import ProfileCoverageStatement, ScenarioCoverage
from ntruth.schemas.graph_v8 import V8ExperimentGraph, V8GraphNodeType
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.query import InferentialQuery
from ntruth.schemas.support import EvidenceBasis, ScientificReviewRequirement, SupportDescriptor

CLAIM_STATE_REVIEW_ISSUE_ID = "SRR-V8-023"

_IMPLEMENTATION_RULE_ID_BY_CLAUSE = {
    "DT-A-ASSIGNMENT-UNIT": "V8-A-ASSIGNMENT-UNIT",
    "DT-B-EXPERIMENTAL-UNIT": "V8-B-EXPERIMENTAL-UNIT",
    "DT-C-EXPERIMENTAL-UNIT-COUNT": "V8-C-EXPERIMENTAL-UNIT-COUNT",
    "DT-D-BIOLOGICAL-SOURCE-COUNT": "V8-D-BIOLOGICAL-SOURCE-COUNT",
    "DT-E-INTERFERENCE-ESTIMAND": "V8-E-INTERFERENCE",
    "DT-F-ANALYTICAL-DEPENDENCE": "V8-F-ANALYTICAL-DEPENDENCE",
    "DT-G-INFERENCE-SCOPE": "V8-G-INFERENCE-SCOPE",
}


class V8DerivationInput(KernelModel):
    experiment_block_id: NonBlankStr
    graph: V8ExperimentGraph
    query: InferentialQuery
    causal_aggregate: QueryCausalEventAggregate
    predicate_values: dict[NonBlankStr, KnowledgeValue[JsonValue]] = Field(min_length=1)
    support_by_clause: dict[NonBlankStr, SupportDescriptor] = Field(min_length=1)
    profile_coverage: ProfileCoverageStatement
    scenario_coverages: tuple[ScenarioCoverage, ...] = ()
    runtime_ruleset_version: NonBlankStr

    @field_validator("predicate_values", mode="before")
    @classmethod
    def _normalize_json_predicates(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return {
            key: item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for key, item in value.items()
        }

    @model_validator(mode="after")
    def _scope_integrity(self) -> V8DerivationInput:
        if self.causal_aggregate.experiment_block_id != self.experiment_block_id:
            raise ValueError("causal aggregate must share the pipeline Experiment Block")
        if self.causal_aggregate.causal_context.inferential_query_id != self.query.id:
            raise ValueError("causal aggregate must share the pipeline InferentialQuery")
        block_nodes = {
            node.node_id
            for node in self.graph.nodes
            if node.node_type is V8GraphNodeType.EXPERIMENT_BLOCK
        }
        query_nodes = {
            node.node_id
            for node in self.graph.nodes
            if node.node_type is V8GraphNodeType.INFERENTIAL_QUERY
        }
        if self.experiment_block_id not in block_nodes:
            raise ValueError("v8 graph does not contain the requested Experiment Block")
        if self.query.id not in query_nodes:
            raise ValueError("v8 graph does not contain the requested InferentialQuery")
        for predicate_id, value in self.predicate_values.items():
            if value.query_scope_id is not None and value.query_scope_id != self.query.id:
                raise ValueError(f"predicate {predicate_id} has a cross-query scope")
        if self.profile_coverage.profile_id != self.query.profile_id:
            raise ValueError("profile coverage must share the InferentialQuery profile")
        for coverage in self.scenario_coverages:
            if coverage.profile_id != self.query.profile_id:
                raise ValueError("scenario coverage must share the InferentialQuery profile")
        return self


_IRRELEVANT_PREDICATES: dict[str, tuple[IrrelevantPredicate, ...]] = {
    "DT-A-ASSIGNMENT-UNIT": (
        IrrelevantPredicate(
            id="biological_source_independence",
            rationale="Biological-source independence is not assignment evidence.",
        ),
    ),
    "DT-B-EXPERIMENTAL-UNIT": (
        IrrelevantPredicate(
            id="biological_source_independence",
            rationale="Source independence cannot identify the treatment experimental unit.",
        ),
    ),
    "DT-C-EXPERIMENTAL-UNIT-COUNT": (
        IrrelevantPredicate(
            id="analytical_rows",
            rationale="Analytical rows and repeated measures do not multiply EU count.",
        ),
    ),
    "DT-D-BIOLOGICAL-SOURCE-COUNT": (
        IrrelevantPredicate(
            id="assignment_separability",
            rationale="Assignment separability does not establish biological provenance.",
        ),
    ),
    "DT-E-INTERFERENCE-ESTIMAND": (
        IrrelevantPredicate(
            id="biological_source_count",
            rationale="Source count does not resolve an exposure or interference pathway.",
        ),
    ),
    "DT-F-ANALYTICAL-DEPENDENCE": (
        IrrelevantPredicate(
            id="experimental_unit_count",
            rationale="EU count does not determine analytical grouping.",
        ),
    ),
    "DT-G-INFERENCE-SCOPE": (
        IrrelevantPredicate(
            id="raw_numerosity",
            rationale="Inference scope is not derived from numerosity alone.",
        ),
    ),
}


def load_runtime_theory() -> DerivationTheory:
    """Load only the theory asset; never load Rulebook expectations into derivation."""

    resource = files("ntruth").joinpath("_bundled", "theories", THEORY_FILENAME)
    if not resource.is_file():
        resource = Path(__file__).resolve().parents[3] / "theories" / THEORY_FILENAME
    return load_derivation_theory_file(resource)


def load_runtime_bundle() -> ConformanceBundle:
    """Load the pinned implementation bundle, with a source-checkout fallback."""

    try:
        return load_installed_bundle()
    except FileNotFoundError:
        repository_root = Path(__file__).resolve().parents[3]
        return load_canonical_bundle(repository_root)


def verify_runtime_bundle(bundle: ConformanceBundle) -> ConformanceReport:
    """Gate implementation conformance; the evaluator still reads theory only."""

    return evaluate_conformance(bundle)


def implementation_rule_ids(bundle: ConformanceBundle) -> Mapping[str, str]:
    """Return trace identifiers only after bundle conformance has been established."""

    return {rule.theory_clause_id: rule.rule_id for rule in bundle.rulebook.rules}


def _required_values(
    request: V8DerivationInput, clause: TheoryClause
) -> tuple[tuple[str, KnowledgeValue[JsonValue]], ...]:
    values: list[tuple[str, KnowledgeValue[JsonValue]]] = []
    for requirement in clause.required_predicates:
        value = request.predicate_values.get(requirement.predicate_id)
        if value is None:
            raise ValueError(
                "missing predicate must be represented with an explicit KnowledgeState: "
                f"{requirement.predicate_id}"
            )
        values.append((requirement.predicate_id, value))
    return tuple(values)


def _state_for(
    required: tuple[tuple[str, KnowledgeValue[JsonValue]], ...],
    support: SupportDescriptor,
    sensitivity_record_ids: tuple[str, ...],
) -> DeterminabilityState:
    states = {value.knowledge_state for _, value in required}
    if KnowledgeState.CONFLICTING in states:
        return DeterminabilityState.CONFLICTING_INFORMATION
    if states & {KnowledgeState.UNKNOWN, KnowledgeState.NOT_REPORTED}:
        return DeterminabilityState.INSUFFICIENT_INFORMATION
    if support.evidence_basis in {
        EvidenceBasis.AUTHOR_ASSERTED,
        EvidenceBasis.INFERRED_CANDIDATE,
    }:
        return DeterminabilityState.INSUFFICIENT_INFORMATION
    if support.evidence_basis is EvidenceBasis.SELF_REPORT and not sensitivity_record_ids:
        return DeterminabilityState.INSUFFICIENT_INFORMATION
    return DeterminabilityState.DETERMINATE


def _resolved_payload(claim_type: str, request: V8DerivationInput) -> JsonValue | None:
    values = request.predicate_values
    if claim_type in {"ASSIGNMENT_UNIT", "EXPERIMENTAL_UNIT_CANDIDATE"}:
        if values["assignment_separability_support"].value is not True:
            return None
        return values["candidate_unit"].value
    if claim_type == "EXPERIMENTAL_UNIT":
        if (
            values["assignment_separability"].value is not True
            or values["realized_exposure_separability"].value is not True
        ):
            return None
        return values["candidate_unit"].value
    if claim_type == "EXPERIMENTAL_UNIT_COUNT":
        instances = values["experimental_unit_instances"].value
        if not isinstance(instances, list) or not instances:
            return None
        return len({str(item) for item in instances})
    if claim_type == "BIOLOGICAL_SOURCE_COUNT":
        if values["confirmed_biological_provenance"].value is not True:
            return None
        instances = values["biological_source_instances"].value
        if not isinstance(instances, list) or not instances:
            return None
        return len({str(item) for item in instances})
    if claim_type == "INTERFERENCE_ESTIMAND_SUPPORT":
        consequences = {
            "no_known_path": "NO_KNOWN_PATH_DOES_NOT_PROVE_ABSENCE",
            "possible": "CAVEAT_OR_SENSITIVITY_REQUIRED",
            "documented": "UNSUPPORTED_OR_UNSPECIFIED_WITHOUT_EXPOSURE_MAPPING",
            "unknown": "CAVEAT_QUESTION_OR_SENSITIVITY_REQUIRED",
        }
        return consequences.get(str(values["interference_status"].value))
    if claim_type == "ANALYTICAL_UNIT":
        return values["analytical_grouping"].value
    if claim_type == "STATISTICAL_HANDOFF_REQUIREMENTS":
        return "HANDOFF_ONLY"
    if claim_type == "INFERENCE_SCOPE":
        return "LIMITED_TO_DECLARED_QUERY_PROTOCOL_AND_SOURCE_SCOPE"
    raise ValueError(f"no clause evaluator for claim type {claim_type}")


def _evidence_ids(
    required: tuple[tuple[str, KnowledgeValue[JsonValue]], ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(evidence_id for _, value in required for evidence_id in value.evidence_ids)
    )


def _derive_clause_claims(
    request: V8DerivationInput,
    theory: DerivationTheory,
    clause: TheoryClause,
    rule_ids: Mapping[str, str],
) -> tuple[DerivedClaim, ...]:
    required = _required_values(request, clause)
    support = request.support_by_clause.get(clause.clause_id)
    if support is None:
        raise ValueError(f"missing explicit support descriptor for {clause.clause_id}")
    evaluator_id = rule_ids.get(clause.clause_id)
    if evaluator_id is None:
        raise ValueError(f"no conformant implementation rule for {clause.clause_id}")
    evidence_ids = _evidence_ids(required)
    claims: list[DerivedClaim] = []
    for claim_type in clause.output_claim_types:
        sensitivity_record_ids: tuple[str, ...] = ()
        state = _state_for(required, support, sensitivity_record_ids)
        payload = (
            _resolved_payload(claim_type, request)
            if state is DeterminabilityState.DETERMINATE
            else None
        )
        if payload is None:
            state = DeterminabilityState.INSUFFICIENT_INFORMATION
            value = KnowledgeValue[JsonValue](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale=(
                    f"Clause {clause.clause_id} cannot emit an unconditional {claim_type} "
                    "from the verified predicates."
                ),
                query_scope_id=request.query.id,
            )
            state_review = ScientificReviewRequirement(
                issue_id=CLAIM_STATE_REVIEW_ISSUE_ID,
                rationale=(
                    "Positive non-determinate payloads remain unavailable; retain an explicit "
                    "unknown value and review blocker."
                ),
            )
        else:
            if not evidence_ids:
                raise ValueError(f"DETERMINATE {claim_type} requires factual evidence")
            value = KnowledgeValue[JsonValue](
                knowledge_state=KnowledgeState.PRESENT,
                value=payload,
                evidence_ids=evidence_ids,
                query_scope_id=request.query.id,
            )
            state_review = None
        proof = ProofTraceStep(
            step_id=stable_id(
                "proof",
                request.experiment_block_id,
                request.query.id,
                clause.clause_id,
                claim_type,
            ),
            predicate_references=tuple(
                PredicateProofReference(predicate_id=predicate_id, predicate_value=value)
                for predicate_id, value in required
            ),
            theory_clause_id=clause.clause_id,
            rule_id=evaluator_id,
        )
        claims.append(
            DerivedClaim(
                claim_id=stable_id(
                    "claim",
                    request.experiment_block_id,
                    request.query.id,
                    theory.theory_version,
                    claim_type,
                ),
                claim_type=claim_type,
                inferential_query_id=request.query.id,
                value=value,
                determinability_state=state,
                support_grade=support.support_grade,
                required_predicates=tuple(predicate_id for predicate_id, _ in required),
                irrelevant_predicates=_IRRELEVANT_PREDICATES[clause.clause_id],
                assumptions=("record_complete_for_claim",),
                sensitivity_records=sensitivity_record_ids,
                theory_version=theory.theory_version,
                theory_clauses=(clause.clause_id,),
                ruleset_version=request.runtime_ruleset_version,
                rule_trace=(evaluator_id,),
                proof_trace=(proof,),
                profile_coverage=request.profile_coverage.claim_reference(),
                state_contract_review=state_review,
            )
        )
    return tuple(claims)


def derive_claim_set(
    request: V8DerivationInput,
    *,
    theory: DerivationTheory,
    rule_ids: Mapping[str, str] | None = None,
) -> DerivedClaimSet:
    implementation_ids = rule_ids or _IMPLEMENTATION_RULE_ID_BY_CLAUSE
    claims = tuple(
        claim
        for clause in theory.clauses
        for claim in _derive_clause_claims(request, theory, clause, implementation_ids)
    )
    return DerivedClaimSet(
        claim_set_id=stable_id(
            "claim-set", request.experiment_block_id, request.query.id, theory.theory_version
        ),
        inferential_query_id=request.query.id,
        claims=claims,
    )


__all__ = [
    "CLAIM_STATE_REVIEW_ISSUE_ID",
    "V8DerivationInput",
    "derive_claim_set",
    "implementation_rule_ids",
    "load_runtime_bundle",
    "load_runtime_theory",
    "verify_runtime_bundle",
]
