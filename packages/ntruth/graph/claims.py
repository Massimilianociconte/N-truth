"""Motore di derivazione claim-specific del PRD v8.0 (§7.13-§7.16, §10.2).

Contratto formale (Appendice N.1): ``D_T(G, P, Q) -> DerivedClaimSet``. Questo
modulo e' l'adapter che proietta i nuclei di derivazione gia' esistenti —
``resolve_units``/``_assess`` (graph/units.py) e ``derive_determinability``
(graph/determinability.py) — in ``DerivedClaim`` keyed per ``InferentialQuery``,
senza riscriverne la logica scientifica.

Invariante di migrazione: il percorso block-level deprecato resta byte-identico
(pin ``tests/regression``); qui si aggiunge soltanto la proiezione claim-specific.

Politica fail-closed (Appendice AC, NFR-26): ogni silenzio diventa uno stato
esplicito; i gradi di supporto e i finding di adeguatezza usano il valore piu'
conservativo quando la policy non e' determinata dal PRD (registro SRR).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ntruth.derivation_theory.models import ClauseFamily, DerivationTheory
from ntruth.design.schema import DesignCompilation
from ntruth.graph.builder import BuildResult
from ntruth.graph.index import GraphIndex
from ntruth.graph.units import resolve_units
from ntruth.rules.predicates import RuleContext, UnknownPredicate, evaluate
from ntruth.schemas.claims import (
    ClaimType,
    DerivedClaim,
    DerivedClaimSet,
    DesignAdequacyFinding,
    IrrelevantPredicate,
    ReportResolutionState,
    RuleTraceEntry,
    aggregate_report_resolution,
)
from ntruth.schemas.core import (
    AlertClass,
    Determinability,
    EvidenceSpan,
    EvidenceType,
    ProvenanceKind,
    stable_id,
)
from ntruth.schemas.experiment import (
    ExperimentBlock,
    Inferability,
    UnitAssessment,
)
from ntruth.schemas.kernel import (
    InferentialQuery,
    KnowledgeState,
    KnowledgeValue,
    ProfileCoverageStatement,
    ProfileCoverageStatus,
    ScenarioCoverage,
    ScenarioCoverageStatus,
    SupportGrade,
)
from ntruth.schemas.rules import RuleEvaluation, Ruleset

#: Famiglie di clausole responsabili di ciascun tipo di claim (§7.15).
_CLAIM_TYPE_FAMILIES: dict[ClaimType, tuple[ClauseFamily, ...]] = {
    ClaimType.EXPERIMENTAL_UNIT: (ClauseFamily.ASSIGNMENT_UNIT, ClauseFamily.EXPERIMENTAL_UNIT),
    ClaimType.EXPERIMENTAL_UNIT_COUNT: (ClauseFamily.EXPERIMENTAL_UNIT_COUNT,),
    ClaimType.BIOLOGICAL_SOURCE_COUNT: (ClauseFamily.BIOLOGICAL_SOURCE_COUNT,),
}

#: Chiave della memo dei predicati: (nome predicato, assessment id).
PredicateMemoKey = tuple[str, str]


@dataclass
class PredicateMemo:
    """Memoizzazione delle valutazioni di predicato per blocco (singolo passaggio).

    Ogni valutazione e' keyed ``(predicate, assessment.id)`` e riusata tra claim
    e sensitivity: nessun predicato viene valutato due volte (NFR-06/NFR-07).
    ``None`` = predicato non valutabile (sconosciuto): mai vero per default.
    """

    _values: dict[PredicateMemoKey, bool | None] = field(default_factory=dict)
    evaluations: int = 0

    def get(self, predicate: str, assessment_id: str) -> bool | _Missing | None:
        """Ritorna il valore memoizzato o il sentinel ``_MISSING``."""
        return self._values.get((predicate, assessment_id), _MISSING)

    def evaluate(
        self,
        predicate: str,
        context: RuleContext,
        assessment_id: str,
    ) -> bool | None:
        key = (predicate, assessment_id)
        cached = self._values.get(key, _MISSING)
        if cached is not _MISSING:
            return cached  # type: ignore[return-value]
        try:
            value: bool | None = evaluate(predicate, context)
        except UnknownPredicate:
            value = None
        self._values[key] = value
        self.evaluations += 1
        return value

    def items(self) -> tuple[tuple[PredicateMemoKey, bool | None], ...]:
        return tuple(self._values.items())

    def flipped(self, predicate: str, assessment_id: str, value: bool) -> PredicateMemo:
        """Copia della memo con un singolo predicato capovolto (§9.7)."""
        clone = PredicateMemo(_values=dict(self._values), evaluations=self.evaluations)
        clone._values[(predicate, assessment_id)] = value
        return clone


class _Missing:
    """Sentinel distinto da ``None`` (che significa 'non valutabile')."""


_MISSING = _Missing()


@dataclass(frozen=True)
class ClaimDerivation:
    """Esito completo della derivazione claim-specific di un blocco."""

    claim_sets: tuple[DerivedClaimSet, ...]
    design_adequacy_findings: tuple[DesignAdequacyFinding, ...]
    scenario_coverages: tuple[ScenarioCoverage, ...]
    profile_coverage: ProfileCoverageStatement | None
    report_resolution_state: ReportResolutionState
    memo: PredicateMemo

    @property
    def claims(self) -> tuple[DerivedClaim, ...]:
        return tuple(claim for claim_set in self.claim_sets for claim in claim_set.claims)


def derive_claim_set(
    block: ExperimentBlock,
    compilation: DesignCompilation | None,
    queries: Sequence[InferentialQuery] | None,
    theory: DerivationTheory,
    ruleset: Ruleset,
    *,
    build: BuildResult,
    assessments: Sequence[UnitAssessment] | None = None,
    evaluations: Sequence[RuleEvaluation] = (),
    index: GraphIndex | None = None,
) -> ClaimDerivation:
    """Proietta il nucleo di derivazione in claim keyed per query (Appendice N.1).

    Riusa ``resolve_units`` come nucleo interno (mai riscritto): se gli
    assessment non sono forniti, vengono risolti dal grafo. L'indice del grafo
    e' accettato pre-costruito e mai ricostruito internamente quando passato.
    """
    graph_index = index if index is not None else GraphIndex(build.hierarchy)
    if assessments is None:
        assessments, _ = resolve_units(block.id, build)

    evidence_by_id = {item.id: item for item in block.evidence}
    memo = PredicateMemo()
    claim_sets: list[DerivedClaimSet] = []
    all_states: list[Determinability] = []

    requested = {query.id: query for query in (queries or ())}
    for assessment in assessments:
        query = _query_for_assessment(assessment, requested)
        context = _context_for(build, graph_index, assessment, evidence_by_id)
        _populate_memo(theory, context, memo, assessment.id)
        claims = _claims_for_assessment(
            block=block,
            assessment=assessment,
            query=query,
            theory=theory,
            ruleset=ruleset,
            context=context,
            memo=memo,
            evaluations=evaluations,
            evidence_by_id=evidence_by_id,
        )
        if claims:
            claim_sets.append(DerivedClaimSet(query_id=query.id, claims=tuple(claims)))
            all_states.extend(claim.determinability_state for claim in claims)

    findings = _design_adequacy_findings(block, claim_sets, evidence_by_id)
    coverages = _scenario_coverages(theory, claim_sets, queries)
    profile_coverage = _profile_coverage(theory, claim_sets)
    resolution = (
        aggregate_report_resolution(tuple(all_states))
        if all_states
        else (aggregate_report_resolution((block.determinability,)))
    )

    return ClaimDerivation(
        claim_sets=tuple(claim_sets),
        design_adequacy_findings=tuple(findings),
        scenario_coverages=tuple(coverages),
        profile_coverage=profile_coverage,
        report_resolution_state=resolution,
        memo=memo,
    )


# ---------------------------------------------------------------------------
# Memo dei predicati
# ---------------------------------------------------------------------------


def _populate_memo(
    theory: DerivationTheory, context: RuleContext, memo: PredicateMemo, assessment_id: str
) -> None:
    """Valuta una sola volta per assessment tutti i predicati richiesti dalle clausole.

    I predicati dichiarati ``known_gap`` dalla teoria non esistono nel registro
    v7: la valutazione restituisce ``None`` (non valutabile), mai un default
    (NFR-26). La memo keyed ``(predicate, assessment)`` garantisce il singolo
    passaggio (NFR-06/NFR-07).
    """
    for clause in theory.clauses:
        for ref in clause.required_predicates:
            memo.evaluate(ref.predicate, context, assessment_id)


# ---------------------------------------------------------------------------
# Query e contesto
# ---------------------------------------------------------------------------


def _query_for_assessment(
    assessment: UnitAssessment, requested: Mapping[str, InferentialQuery]
) -> InferentialQuery:
    """Query deterministica per lo scope dell'assessment.

    Se una query richiesta coincide per scope, il suo id viene riusato;
    altrimenti la query e' derivata deterministicamente dallo scope (v6->v8).
    """
    scope = assessment.scope
    for query in requested.values():
        if (
            query.factor_id == scope.factor_id
            and query.contrast_id == scope.contrast_id
            and query.endpoint_id == scope.endpoint_id
        ):
            return query
    try:
        return InferentialQuery.from_nscope(scope)
    except ValueError:
        # Scope globale senza factor/contrast/endpoint: query minimale
        # ancorata all'assessment, mai un claim senza query (§10.2).
        return InferentialQuery(
            id=stable_id("IQ", assessment.id),
            contrast_id=assessment.id,
        )


def _context_for(
    build: BuildResult,
    index: GraphIndex,
    assessment: UnitAssessment,
    evidence_by_id: Mapping[str, EvidenceSpan],
) -> RuleContext:
    scope = assessment.scope
    factor = next((f for f in build.factors if f.id == scope.factor_id), None)
    contrast = next((c for c in build.contrasts if c.id == scope.contrast_id), None)
    endpoint = next((e for e in build.endpoints if e.id == scope.endpoint_id), None)
    return RuleContext(
        index=index,
        build=build,
        assessment=assessment,
        factor=factor,
        contrast=contrast,
        endpoint=endpoint,
        evidence_by_id=evidence_by_id,
    )


# ---------------------------------------------------------------------------
# Emissione dei claim per assessment
# ---------------------------------------------------------------------------


def _claims_for_assessment(
    *,
    block: ExperimentBlock,
    assessment: UnitAssessment,
    query: InferentialQuery,
    theory: DerivationTheory,
    ruleset: Ruleset,
    context: RuleContext,
    memo: PredicateMemo,
    evaluations: Sequence[RuleEvaluation],
    evidence_by_id: Mapping[str, EvidenceSpan],
) -> list[DerivedClaim]:
    claims: list[DerivedClaim] = []

    eu_claim = _experimental_unit_claim(
        block, assessment, query, theory, ruleset, context, memo, evaluations, evidence_by_id
    )
    if eu_claim is not None:
        claims.append(eu_claim)

    count_claim = _eu_count_claim(
        block, assessment, query, theory, ruleset, context, memo, evaluations, evidence_by_id
    )
    if count_claim is not None:
        claims.append(count_claim)

    source_claim = _source_count_claim(
        block, assessment, query, theory, ruleset, context, memo, evaluations, evidence_by_id
    )
    if source_claim is not None:
        claims.append(source_claim)

    return claims


def _clause_ids(theory: DerivationTheory, families: tuple[ClauseFamily, ...]) -> tuple[str, ...]:
    ids: list[str] = []
    for family in families:
        ids.extend(clause.clause_id for clause in theory.clauses_by_family(family))
    return tuple(ids)


def _required_predicates(
    theory: DerivationTheory, families: tuple[ClauseFamily, ...]
) -> tuple[str, ...]:
    predicates: list[str] = []
    for family in families:
        for clause in theory.clauses_by_family(family):
            predicates.extend(ref.predicate for ref in clause.required_predicates)
    return tuple(dict.fromkeys(predicates))


def _irrelevant_predicates(
    theory: DerivationTheory, families: tuple[ClauseFamily, ...]
) -> tuple[IrrelevantPredicate, ...]:
    seen: dict[str, IrrelevantPredicate] = {}
    for family in families:
        for clause in theory.clauses_by_family(family):
            for ref in clause.irrelevant_predicates:
                # M.2: NOT_APPLICABLE_TO_CLAIM richiede clause+rationale; il
                # reviewer e' lo stato di revisione della teoria (fail-closed).
                rationale = (
                    f"{ref.rationale} [clause={clause.clause_id}; reviewer={_reviewer(theory)}]"
                )
                seen.setdefault(
                    ref.predicate,
                    IrrelevantPredicate(predicate_id=ref.predicate, rationale=rationale),
                )
    return tuple(seen.values())


def _reviewer(theory: DerivationTheory) -> str:
    return theory.metadata.reviewer or theory.metadata.status.value


def _rule_trace(
    theory_clauses: tuple[str, ...],
    ruleset: Ruleset,
    evaluations: Sequence[RuleEvaluation],
) -> tuple[RuleTraceEntry, ...]:
    """Rule ids collegati alle clausole del claim + valori delle premesse."""
    entries: dict[str, RuleTraceEntry] = {}
    clause_set = set(theory_clauses)
    for rule in ruleset.rules:
        if rule.theory_clause and rule.theory_clause in clause_set:
            entries[rule.rule_id] = RuleTraceEntry(rule_id=rule.rule_id, premise_values={})
    for evaluation in evaluations:
        if not evaluation.output_ids:
            continue
        premise_values = {pt.expression: pt.result for pt in evaluation.premise_trace}
        if evaluation.rule_id in entries or evaluation.rule_id in {
            rule.rule_id for rule in ruleset.rules
        }:
            entries[evaluation.rule_id] = RuleTraceEntry(
                rule_id=evaluation.rule_id, premise_values=premise_values
            )
    return tuple(entries.values())


def _support_grade(
    assessment: UnitAssessment, evidence_by_id: Mapping[str, EvidenceSpan]
) -> SupportGrade:
    """Migrazione §0.3-§0.4: grado conservativo quando la policy e' indeterminata.

    SRR: la mappatura provenienza->grado e' convenzione di migrazione
    fail-closed; il grado piu' conservativo compatibile con l'evidenza viene
    scelto finché la Confirmation Support & Sensitivity Policy non e' approvata.
    """
    origin = assessment.provenance.origin
    if origin in {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION}:
        return SupportGrade.ADJUDICATED
    if origin is ProvenanceKind.MODEL:
        return SupportGrade.MODEL_CANDIDATE
    if not assessment.evidence_ids:
        return SupportGrade.NOT_SUPPORTED
    types = [
        evidence.evidence_type
        for evidence_id in assessment.evidence_ids
        if (evidence := evidence_by_id.get(evidence_id)) is not None
    ]
    if types and all(t is EvidenceType.AUTHOR_ASSERTION for t in types):
        return SupportGrade.ASSERTION_ONLY
    return SupportGrade.DIRECT_SINGLE_SOURCE


def _floor_state(block: ExperimentBlock) -> Determinability | None:
    """Stati block-level che si propagano a ogni claim (invalido/conflitto/scope)."""
    state = block.determinability
    if state in {
        Determinability.INVALID_GRAPH,
        Determinability.CONFLICTING_INFORMATION,
        Determinability.OUT_OF_SCOPE,
    }:
        return state
    return None


def _claim_id(query: InferentialQuery, claim_type: ClaimType, theory: DerivationTheory) -> str:
    """ID deterministico e content-addressed del claim (NFR-02)."""
    return stable_id("CLAIM", query.id, claim_type.value, theory.metadata.version)


def _build_claim(
    *,
    claim_type: ClaimType,
    query: InferentialQuery,
    value: KnowledgeValue[Any],
    state: Determinability,
    assessment: UnitAssessment,
    theory: DerivationTheory,
    ruleset: Ruleset,
    evaluations: Sequence[RuleEvaluation],
    evidence_by_id: Mapping[str, EvidenceSpan],
) -> DerivedClaim:
    families = _CLAIM_TYPE_FAMILIES[claim_type]
    theory_clauses = _clause_ids(theory, families)
    return DerivedClaim(
        claim_id=_claim_id(query, claim_type, theory),
        claim_type=claim_type,
        query_id=query.id,
        value=value,
        determinability_state=state,
        support_grade=_support_grade(assessment, evidence_by_id),
        required_predicates=_required_predicates(theory, families),
        irrelevant_predicates=_irrelevant_predicates(theory, families),
        theory_version=theory.metadata.version,
        theory_clauses=theory_clauses,
        ruleset_version=ruleset.version,
        rule_trace=_rule_trace(theory_clauses, ruleset, evaluations),
        assumptions=("record_completeness", "predicate_sufficiency"),
    )


# ---------------------------------------------------------------------------
# Claim tipizzati
# ---------------------------------------------------------------------------


def _experimental_unit_claim(
    block: ExperimentBlock,
    assessment: UnitAssessment,
    query: InferentialQuery,
    theory: DerivationTheory,
    ruleset: Ruleset,
    context: RuleContext,
    memo: PredicateMemo,
    evaluations: Sequence[RuleEvaluation],
    evidence_by_id: Mapping[str, EvidenceSpan],
) -> DerivedClaim | None:
    floor = _floor_state(block)
    unit = assessment.experimental_unit
    if unit is not None:
        value: KnowledgeValue[Any] = KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT, value={"unit_type": str(unit)}
        )
        state = floor or _value_state(assessment, has_value=True)
    else:
        value = KnowledgeValue(
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=(
                "experimental unit non identificabile: assignment/separability "
                "non confermati (§7.15 A/B)"
            ),
        )
        state = floor or _value_state(assessment, has_value=False)
    # M.1: un claim DETERMINATE non puo avere valore UNKNOWN.
    if state is Determinability.DETERMINATE and unit is None:
        state = Determinability.INSUFFICIENT_INFORMATION
    return _build_claim(
        claim_type=ClaimType.EXPERIMENTAL_UNIT,
        query=query,
        value=value,
        state=state,
        assessment=assessment,
        theory=theory,
        ruleset=ruleset,
        evaluations=evaluations,
        evidence_by_id=evidence_by_id,
    )


def _eu_count_claim(
    block: ExperimentBlock,
    assessment: UnitAssessment,
    query: InferentialQuery,
    theory: DerivationTheory,
    ruleset: Ruleset,
    context: RuleContext,
    memo: PredicateMemo,
    evaluations: Sequence[RuleEvaluation],
    evidence_by_id: Mapping[str, EvidenceSpan],
) -> DerivedClaim | None:
    floor = _floor_state(block)
    n = assessment.n_independent
    if n is not None:
        value: KnowledgeValue[Any] = KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value={"experimental_unit_count": n, "group": assessment.scope.group},
        )
        state = floor or _value_state(assessment, has_value=True)
    elif assessment.conditional_scenarios:
        value = KnowledgeValue(
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="EU count condizionale: rami enumerati nello scenario",
        )
        state = floor or Determinability.CONDITIONALLY_DETERMINATE
    else:
        value = KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_REPORTED,
            rationale="EU count non riportato nello scope del contrasto (§7.15 C)",
        )
        state = floor or Determinability.INSUFFICIENT_INFORMATION
    if state is Determinability.DETERMINATE and n is None:
        state = Determinability.INSUFFICIENT_INFORMATION
    return _build_claim(
        claim_type=ClaimType.EXPERIMENTAL_UNIT_COUNT,
        query=query,
        value=value,
        state=state,
        assessment=assessment,
        theory=theory,
        ruleset=ruleset,
        evaluations=evaluations,
        evidence_by_id=evidence_by_id,
    )


def _source_count_claim(
    block: ExperimentBlock,
    assessment: UnitAssessment,
    query: InferentialQuery,
    theory: DerivationTheory,
    ruleset: Ruleset,
    context: RuleContext,
    memo: PredicateMemo,
    evaluations: Sequence[RuleEvaluation],
    evidence_by_id: Mapping[str, EvidenceSpan],
) -> DerivedClaim | None:
    floor = _floor_state(block)
    count = assessment.biological_source_count
    if count is not None:
        value: KnowledgeValue[Any] = KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT, value={"biological_source_count": count}
        )
        state = floor or Determinability.DETERMINATE
    elif assessment.biological_unit is None:
        # Nessuna provenienza biologica nello scope: dimensione non applicabile
        # al claim di source count, mai un silenzio implicito (Appendice AC).
        value = KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale=(
                "nessuna unita biologica nello scope: il source count non e' "
                "applicabile a questo claim (§7.15 D)"
            ),
        )
        state = floor or Determinability.DETERMINATE
    else:
        value = KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_REPORTED,
            rationale="provenienza confermata assente: source count non riportato (§7.15 D)",
        )
        state = floor or Determinability.INSUFFICIENT_INFORMATION
    return _build_claim(
        claim_type=ClaimType.BIOLOGICAL_SOURCE_COUNT,
        query=query,
        value=value,
        state=state,
        assessment=assessment,
        theory=theory,
        ruleset=ruleset,
        evaluations=evaluations,
        evidence_by_id=evidence_by_id,
    )


def _value_state(assessment: UnitAssessment, *, has_value: bool) -> Determinability:
    """Stato claim-specific dal nucleo di derivazione (non un giudizio di qualita')."""
    if assessment.conditional_scenarios:
        return Determinability.CONDITIONALLY_DETERMINATE
    if not has_value:
        return Determinability.INSUFFICIENT_INFORMATION
    if assessment.inferability is Inferability.INFERABLE:
        return Determinability.DETERMINATE
    return Determinability.INSUFFICIENT_INFORMATION


# ---------------------------------------------------------------------------
# Design adequacy findings, scenario e profile coverage
# ---------------------------------------------------------------------------

#: Mappatura di migrazione AlertClass -> asse di adeguatezza. L'adeguatezza non
#: deriva mai dalla determinabilita' (§7.18): i finding sono emessi solo in
#: presenza di alert con evidenza propria, con il valore piu' conservativo.
_ALERT_CLASS_FINDING: dict[AlertClass, str] = {
    AlertClass.DESIGN_REPLICATION: "DESIGN_REPLICATION_UNKNOWN",
    AlertClass.ANALYTICAL_DEPENDENCE: "ANALYTICAL_DEPENDENCE_UNKNOWN",
    AlertClass.INFERENCE_SCOPE: "SOURCE_SCOPE_UNKNOWN",
}


def _design_adequacy_findings(
    block: ExperimentBlock,
    claim_sets: Sequence[DerivedClaimSet],
    evidence_by_id: Mapping[str, EvidenceSpan],
) -> list[DesignAdequacyFinding]:
    findings: list[DesignAdequacyFinding] = []
    claim_ids = tuple(claim.claim_id for cs in claim_sets for claim in cs.claims)
    seen: set[str] = set()
    for alert in block.alerts:
        finding_value = _ALERT_CLASS_FINDING.get(alert.alert_class)
        if finding_value is None:
            continue
        evidence_ids = tuple(
            evidence_id for evidence_id in alert.evidence_ids if evidence_id in evidence_by_id
        )
        if not evidence_ids:
            # Fail-closed: un finding di adeguatezza senza evidenza propria non
            # e' emesso (§10.5); la lacuna resta nell'alert, non diventa finding.
            continue
        key = f"{finding_value}:{alert.id}"
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            DesignAdequacyFinding(
                finding=finding_value,
                query_id=None,
                claim_ids=claim_ids,
                evidence_ids=evidence_ids,
                rationale=(
                    f"migrazione AlertClass.{alert.alert_class.value} -> finding "
                    f"conservativo (regola {alert.rule_id}); l'adeguatezza non e' "
                    "derivata dalla determinabilita' (§7.18)"
                ),
            )
        )
    return findings


def _scenario_coverages(
    theory: DerivationTheory,
    claim_sets: Sequence[DerivedClaimSet],
    queries: Sequence[InferentialQuery] | None,
) -> list[ScenarioCoverage]:
    if not claim_sets:
        return []
    emitting = tuple(
        clause_id for cs in claim_sets for claim in cs.claims for clause_id in claim.theory_clauses
    )
    emitting = tuple(dict.fromkeys(emitting))
    profile_id = queries[0].profile_id if queries and queries[0].profile_id else "core"
    # Fail-closed: senza revisione scientifica la copertura non e' dichiarata
    # esaustiva (Scenario Coverage Protocol, §0.5).
    return [
        ScenarioCoverage(
            status=ScenarioCoverageStatus.NON_EXHAUSTIVE,
            profile_id=profile_id,
            theory_version=theory.metadata.version,
            emitting_clauses=emitting,
        )
    ]


def _profile_coverage(
    theory: DerivationTheory, claim_sets: Sequence[DerivedClaimSet]
) -> ProfileCoverageStatement | None:
    if not claim_sets:
        return None
    covered = tuple(claim.claim_id for cs in claim_sets for claim in cs.claims)
    known_gaps = tuple(sorted(theory.known_gap_predicates()))
    decisive = tuple(
        dict.fromkeys(
            predicate
            for cs in claim_sets
            for claim in cs.claims
            for predicate in claim.required_predicates
        )
    )
    return ProfileCoverageStatement(
        status=ProfileCoverageStatus.COVERED_WITH_KNOWN_GAPS,
        known_gaps=known_gaps,
        covered_claims=covered,
        decisive_predicate_set=decisive,
        reviewer=_reviewer(theory),
        version=theory.metadata.version,
        predicate_sufficiency_statement=(
            "predicate set sufficiente entro il profilo dichiarato; known gaps "
            f"registrati: {', '.join(known_gaps) if known_gaps else 'nessuno'} (§7.17)"
        ),
    )
