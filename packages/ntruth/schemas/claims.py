"""Contratti dei claim derivati del PRD v8.0 (§10.2-§10.6, Appendici AF/M).

Ogni output scientifico e' un ``DerivedClaim`` keyed a una
``InferentialQuery``: nessun claim esiste fuori da una query. Il report
aggrega i claim con ``ReportResolutionState`` senza mai cancellare gli stati
dei singoli claim, e l'adeguatezza del disegno vive in
``DesignAdequacyFinding`` separati dalla determinabilita' (§7.18, §10.5).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import AliasChoices, Field, model_validator

from ntruth.schemas.core import Determinability, FrozenModel, stable_id
from ntruth.schemas.kernel import (
    ConflictRecord,
    KnowledgeState,
    KnowledgeValue,
    ProfileCoverageStatement,
    ProfileCoverageStatus,
    ScenarioCoverage,
    ScenarioCoverageStatus,
    SensitivityRecord,
    SupportGrade,
)


class ClaimType(StrEnum):
    """Tipo di claim derivato (token verbatim degli esempi §10.2/A/AF)."""

    EXPERIMENTAL_UNIT = "EXPERIMENTAL_UNIT"
    EXPERIMENTAL_UNIT_COUNT = "EXPERIMENTAL_UNIT_COUNT"
    BIOLOGICAL_SOURCE_COUNT = "BIOLOGICAL_SOURCE_COUNT"
    DESIGN_ADEQUACY_FINDING = "DESIGN_ADEQUACY_FINDING"


class IrrelevantPredicate(FrozenModel):
    """Predicato formalmente non richiesto dal claim, con rationale (§10.2)."""

    predicate_id: str = Field(validation_alias=AliasChoices("predicate_id", "id"))
    rationale: str

    model_config = FrozenModel.model_config | {"populate_by_name": True}

    @model_validator(mode="after")
    def _motivated(self) -> Self:
        if not self.rationale.strip():
            raise ValueError("predicato irrilevante senza rationale (§10.2)")
        return self


class ClaimAssumption(FrozenModel):
    """Assunzione strutturata di un claim (Appendice AF)."""

    predicate_id: str
    value: Any = None
    authority_event_id: str | None = None


class RuleTraceEntry(FrozenModel):
    """Voce di rule trace: rule id + valori delle premesse usate (§10.2)."""

    rule_id: str
    premise_values: dict[str, Any] = Field(default_factory=dict)


def _normalize_claim_value(raw: Any) -> Any:
    """Normalizza il valore del claim in un wrapper KnowledgeValue esplicito.

    Gli esempi normativi mostrano tre forme:
    - ``{unit_type: well}`` (§10.2): valore senza stato esplicito;
    - ``{knowledge_state: PRESENT, unit_type: well}`` (AF);
    - ``{knowledge_state: UNKNOWN}`` (Appendice A).
    Il silenzio non resta mai implicito: la forma senza stato viene marcata
    ``PRESENT`` con audit di migrazione.
    """
    if isinstance(raw, KnowledgeValue):
        return raw
    if isinstance(raw, dict):
        payload = dict(raw)
        if "knowledge_state" in payload:
            state = payload.pop("knowledge_state")
            wrapper_fields = {
                "value",
                "items",
                "source_scope",
                "rationale",
                "evidence_ids",
                "migration_note",
            }
            wrapped = {key: value for key, value in payload.items() if key in wrapper_fields}
            extras = {key: value for key, value in payload.items() if key not in wrapper_fields}
            if wrapped.get("value") is None and extras:
                wrapped["value"] = extras
            wrapped["knowledge_state"] = state
            return KnowledgeValue[Any].model_validate(wrapped)
        if not payload:
            raise ValueError("claim value vuoto: richiede KnowledgeState esplicito (AC)")
        return KnowledgeValue[Any](
            knowledge_state=KnowledgeState.PRESENT,
            value=payload,
            migration_note=(
                "claim value §10.2 senza knowledge_state esplicito: "
                "normalizzato a PRESENT con audit"
            ),
        )
    raise ValueError("claim value non strutturato: richiesto mapping KnowledgeValue")


def _normalize_profile_coverage(raw: Any) -> Any:
    """§10.2 usa lo stato come stringa; AF usa l'oggetto completo."""
    if isinstance(raw, str):
        return ProfileCoverageStatement(status=ProfileCoverageStatus(raw))
    return raw


def _normalize_rule_trace_entry(raw: Any) -> Any:
    if isinstance(raw, str):
        return RuleTraceEntry(rule_id=raw)
    return raw


class DerivedClaim(FrozenModel):
    """Singolo claim versionato per una InferentialQuery (§10.2, AF).

    Accetta entrambe le denominazioni normative dei campi (§10.2 usa
    ``inferential_query_id``/``determinability``; Appendice A/AF usano
    ``query_id``/``determinability_state``) e serializza in forma canonica
    v8 (SRR-0010).
    """

    claim_id: str
    claim_type: ClaimType
    query_id: str = Field(validation_alias=AliasChoices("query_id", "inferential_query_id"))
    value: KnowledgeValue[Any]
    determinability_state: Determinability = Field(
        validation_alias=AliasChoices("determinability_state", "determinability")
    )
    support_grade: SupportGrade
    required_predicates: tuple[str, ...] = ()
    irrelevant_predicates: tuple[IrrelevantPredicate, ...] = ()
    assumptions: tuple[str | ClaimAssumption, ...] = ()
    sensitivity_records: tuple[str, ...] = ()
    theory_version: str | None = None
    theory_clauses: tuple[str, ...] = ()
    ruleset_version: str | None = None
    rule_trace: tuple[str | RuleTraceEntry, ...] = ()
    profile_coverage: ProfileCoverageStatement | None = None

    model_config = FrozenModel.model_config | {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _normalize_representations(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if payload.get("claim_id") is None or not str(payload["claim_id"]).strip():
            payload["claim_id"] = stable_id(
                "CLAIM",
                payload.get("query_id", payload.get("inferential_query_id")),
                payload.get("claim_type"),
                payload.get("theory_version"),
            )
        if "value" in payload:
            payload["value"] = _normalize_claim_value(payload["value"])
        if "profile_coverage" in payload and payload["profile_coverage"] is not None:
            payload["profile_coverage"] = _normalize_profile_coverage(payload["profile_coverage"])
        if "rule_trace" in payload:
            payload["rule_trace"] = [
                _normalize_rule_trace_entry(entry) for entry in payload["rule_trace"]
            ]
        return payload

    @model_validator(mode="after")
    def _claim_science(self) -> Self:
        if not self.query_id.strip():
            raise ValueError("claim senza query: nessun claim esiste fuori da una query")
        if (
            self.determinability_state is Determinability.DETERMINATE
            and self.value.knowledge_state is KnowledgeState.UNKNOWN
        ):
            raise ValueError("claim DETERMINATE non puo' avere valore UNKNOWN")
        if (
            self.determinability_state is Determinability.CONDITIONALLY_DETERMINATE
            and not self.required_predicates
        ):
            raise ValueError("claim condizionale richiede i predicati decisivi mancanti dichiarati")
        return self


class DerivedClaimSet(FrozenModel):
    """Collezione di claim sempre keyed alla propria query (§10.2)."""

    query_id: str
    claims: tuple[DerivedClaim, ...]

    @model_validator(mode="after")
    def _claims_keyed_to_query(self) -> Self:
        if not self.claims:
            raise ValueError("DerivedClaimSet vuoto: nessun claim prodotto")
        foreign = [claim.claim_id for claim in self.claims if claim.query_id != self.query_id]
        if foreign:
            raise ValueError(f"claim fuori dalla query del set: {foreign}")
        ids = [claim.claim_id for claim in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim_id duplicati nel set")
        return self


class ReportResolutionState(StrEnum):
    """Stato aggregato del report (§10.4): mai un sostituto dei claim state."""

    COMPLETE_FOR_REQUESTED_CLAIMS = "COMPLETE_FOR_REQUESTED_CLAIMS"
    PARTIAL_WITH_ACTIONABLE_GAPS = "PARTIAL_WITH_ACTIONABLE_GAPS"
    MULTI_SCENARIO = "MULTI_SCENARIO"
    CONFLICTED = "CONFLICTED"
    INVALID = "INVALID"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


def aggregate_report_resolution(
    claim_states: tuple[Determinability, ...],
) -> ReportResolutionState:
    """Aggregazione pura degli stati claim -> stato report (SRR-0011).

    Il summary non cancella mai gli stati dei singoli claim; la precedenza e'
    fail-closed: invalidita' > conflitto > gap azionabili > multi-scenario >
    out-of-scope > completezza.
    """
    if not claim_states:
        raise ValueError("nessun claim da aggregare: stato report non derivabile")
    if any(state is Determinability.INVALID_GRAPH for state in claim_states):
        return ReportResolutionState.INVALID
    if any(state is Determinability.CONFLICTING_INFORMATION for state in claim_states):
        return ReportResolutionState.CONFLICTED
    if any(state is Determinability.INSUFFICIENT_INFORMATION for state in claim_states):
        return ReportResolutionState.PARTIAL_WITH_ACTIONABLE_GAPS
    if all(state is Determinability.OUT_OF_SCOPE for state in claim_states):
        return ReportResolutionState.OUT_OF_SCOPE
    if any(state is Determinability.OUT_OF_SCOPE for state in claim_states):
        return ReportResolutionState.PARTIAL_WITH_ACTIONABLE_GAPS
    if any(
        state
        in {
            Determinability.MULTIPLE_PLAUSIBLE_GRAPHS,
            Determinability.CONDITIONALLY_DETERMINATE,
        }
        for state in claim_states
    ):
        return ReportResolutionState.MULTI_SCENARIO
    return ReportResolutionState.COMPLETE_FOR_REQUESTED_CLAIMS


class ConditionalBranch(FrozenModel):
    """Ramo di output condizionale leggibile da un biologo (§10.6)."""

    condition: str
    output: dict[str, Any]

    @model_validator(mode="after")
    def _readable(self) -> Self:
        if not self.condition.strip():
            raise ValueError("ramo condizionale senza condizione leggibile (§10.6)")
        if not self.output:
            raise ValueError("ramo condizionale senza output")
        return self


class ConditionalClaimOutput(FrozenModel):
    """Output condizionale completo di domanda primaria e clausola (§10.6)."""

    claim_type: ClaimType
    determinability_state: Determinability
    scenario_coverage: ScenarioCoverageStatus
    branches: tuple[ConditionalBranch, ...]
    primary_question: str
    theory_clause: str | None = None

    @model_validator(mode="after")
    def _conditional_contract(self) -> Self:
        if self.determinability_state is not Determinability.CONDITIONALLY_DETERMINATE:
            raise ValueError("output condizionale richiede CONDITIONALLY_DETERMINATE")
        if len(self.branches) < 2:
            raise ValueError("output condizionale richiede almeno due rami")
        if not self.primary_question.strip():
            raise ValueError("output condizionale senza domanda primaria")
        return self


class AdequacyAxis(StrEnum):
    """I sei assi tipizzati dei finding di adeguatezza (§10.5, §7.18)."""

    DESIGN_REPLICATION = "DESIGN_REPLICATION"
    HARD_CONFOUNDING = "HARD_CONFOUNDING"
    INTERFERENCE = "INTERFERENCE"
    SOURCE_SCOPE = "SOURCE_SCOPE"
    ANALYTICAL_DEPENDENCE = "ANALYTICAL_DEPENDENCE"
    REPORTING = "REPORTING"


_ADEQUACY_VALUES: dict[str, AdequacyAxis] = {
    "DESIGN_REPLICATION_SUPPORTED": AdequacyAxis.DESIGN_REPLICATION,
    "DESIGN_REPLICATION_LIMITED": AdequacyAxis.DESIGN_REPLICATION,
    "DESIGN_REPLICATION_ABSENT": AdequacyAxis.DESIGN_REPLICATION,
    "DESIGN_REPLICATION_UNKNOWN": AdequacyAxis.DESIGN_REPLICATION,
    "HARD_CONFOUNDING_DOCUMENTED": AdequacyAxis.HARD_CONFOUNDING,
    "HARD_CONFOUNDING_POSSIBLE": AdequacyAxis.HARD_CONFOUNDING,
    "HARD_CONFOUNDING_NOT_IDENTIFIED": AdequacyAxis.HARD_CONFOUNDING,
    "HARD_CONFOUNDING_UNKNOWN": AdequacyAxis.HARD_CONFOUNDING,
    "INTERFERENCE_DOCUMENTED": AdequacyAxis.INTERFERENCE,
    "INTERFERENCE_POSSIBLE": AdequacyAxis.INTERFERENCE,
    "INTERFERENCE_NO_KNOWN_PATH": AdequacyAxis.INTERFERENCE,
    "INTERFERENCE_UNKNOWN": AdequacyAxis.INTERFERENCE,
    "SOURCE_SCOPE_SINGLE": AdequacyAxis.SOURCE_SCOPE,
    "SOURCE_SCOPE_MULTIPLE": AdequacyAxis.SOURCE_SCOPE,
    "SOURCE_SCOPE_UNKNOWN": AdequacyAxis.SOURCE_SCOPE,
    "ANALYTICAL_DEPENDENCE_CLUSTERED": AdequacyAxis.ANALYTICAL_DEPENDENCE,
    "ANALYTICAL_DEPENDENCE_REPEATED": AdequacyAxis.ANALYTICAL_DEPENDENCE,
    "ANALYTICAL_DEPENDENCE_SIMPLE": AdequacyAxis.ANALYTICAL_DEPENDENCE,
    "ANALYTICAL_DEPENDENCE_UNKNOWN": AdequacyAxis.ANALYTICAL_DEPENDENCE,
    "REPORTING_COMPLETE_FOR_CLAIM": AdequacyAxis.REPORTING,
    "REPORTING_INCOMPLETE": AdequacyAxis.REPORTING,
    "REPORTING_CONFLICTING": AdequacyAxis.REPORTING,
}

#: Esiti che un report non deve mai codificare come "verde": una conclusione
#: positiva di adeguatezza non puo' essere giustificata da DETERMINATE (§10.5).
_POSITIVE_ADEQUACY_VALUES = frozenset(
    {
        "DESIGN_REPLICATION_SUPPORTED",
        "HARD_CONFOUNDING_NOT_IDENTIFIED",
        "INTERFERENCE_NO_KNOWN_PATH",
        "ANALYTICAL_DEPENDENCE_SIMPLE",
        "REPORTING_COMPLETE_FOR_CLAIM",
    }
)


class DesignAdequacyFinding(FrozenModel):
    """Finding tipizzato di adeguatezza del disegno (§10.5, §7.18).

    Invarianti:
    - l'adeguatezza non e' mai derivabile dalla determinabilita';
    - ``DETERMINATE`` non mappa mai a un esito adequate/green;
    - ogni finding porta evidence refs e un asse distinto dalla determinabilita'.
    """

    finding: str
    axis: AdequacyAxis | None = None
    query_id: str | None = None
    claim_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...]
    rationale: str = ""
    source_determinability_state: Determinability | None = None

    @model_validator(mode="before")
    @classmethod
    def _infer_axis(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("axis") is None:
            finding = data.get("finding")
            if isinstance(finding, str) and finding in _ADEQUACY_VALUES:
                payload = dict(data)
                payload["axis"] = _ADEQUACY_VALUES[finding]
                return payload
        return data

    @model_validator(mode="after")
    def _separate_axis(self) -> Self:
        if self.finding not in _ADEQUACY_VALUES:
            raise ValueError(f"finding di adeguatezza non tipizzato: {self.finding!r}")
        if self.axis is not _ADEQUACY_VALUES[self.finding]:
            raise ValueError("asse dichiarato incoerente con il finding")
        if not self.evidence_ids:
            raise ValueError(
                "design adequacy finding senza evidence refs: l'adeguatezza non e' "
                "derivabile dalla sola determinabilita' (§10.5)"
            )
        if (
            self.source_determinability_state is Determinability.DETERMINATE
            and self.finding in _POSITIVE_ADEQUACY_VALUES
        ):
            raise ValueError(
                "DETERMINATE non e' una classe di adeguatezza e non puo' mai "
                "giustificare un esito adequate/green (§10.5)"
            )
        return self

    @staticmethod
    def finding_values() -> frozenset[str]:
        """Insieme normativo dei 22 esiti tipizzati (§10.5)."""
        return frozenset(_ADEQUACY_VALUES)

    @classmethod
    def from_determinability(cls, state: Determinability) -> DesignAdequacyFinding:
        """Vietato: l'adeguatezza non si deriva dalla determinabilita' (§7.18)."""
        raise ValueError(
            "DesignAdequacyFinding non e' derivabile da DeterminabilityState "
            f"({state.value}): servono finding tipizzati con evidence proprie"
        )


# ---------------------------------------------------------------------------
# ReportBundle, ReportContract e Reality Gate v8 (Appendice AF, NFR-28)
# ---------------------------------------------------------------------------


class ReportGateStatus(StrEnum):
    """Stato del Reality Gate sul bundle (NFR-28: fail-closed)."""

    PASSED = "PASSED"
    BLOCKED = "BLOCKED"


class RealityGate(FrozenModel):
    """Reality Gate v8 (§0.7, NFR-28): il default e' ``BLOCKED``.

    Il passaggio richiede attestazione esplicita (evidence + rationale):
    il silenzio o l'assenza di revisione non aprono mai il gate.
    """

    status: ReportGateStatus = ReportGateStatus.BLOCKED
    blockers: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    rationale: str = ""

    @model_validator(mode="after")
    def _passed_is_attested(self) -> Self:
        if self.status is ReportGateStatus.PASSED and (
            not self.evidence_ids or not self.rationale.strip()
        ):
            raise ValueError("Reality Gate PASSED richiede evidence e rationale esplicite (NFR-28)")
        return self


class ReportContract(FrozenModel):
    """Contratto di contenuto normativo del report (§10.4, Appendice AF).

    Dichiara cosa il bundle contiene (claim ids, risoluzione, versioni):
    la coerenza con il contenuto e' verificata dal ``ReportBundle``.
    """

    report_resolution_state: ReportResolutionState
    claim_ids: tuple[str, ...]
    theory_version: str | None = None
    ruleset_version: str | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        if not self.claim_ids:
            raise ValueError("contract senza claim: nessun report scientifico esiste")
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("claim_ids duplicati nel contract")
        return self


class ReportBundle(FrozenModel):
    """Bundle v8 finale (Appendice AF): claim + risoluzione + adeguatezza.

    Aggrega senza perdere granularita' (§10.4): il summary non sostituisce
    mai gli stati dei singoli claim. Il Reality Gate e' fail-closed: nessun
    bundle e' ``PASSED`` senza attestazione esplicita.
    """

    claims: tuple[DerivedClaim, ...]
    report_resolution_state: ReportResolutionState
    design_adequacy_findings: tuple[DesignAdequacyFinding, ...] = ()
    scenario_coverages: tuple[ScenarioCoverage, ...] = ()
    profile_coverage: ProfileCoverageStatement | None = None
    sensitivity_records: tuple[SensitivityRecord, ...] = ()
    conflicts: tuple[ConflictRecord, ...] = ()
    contract: ReportContract
    reality_gate: RealityGate = Field(default_factory=RealityGate)

    @model_validator(mode="after")
    def _contract_coherent(self) -> Self:
        if not self.claims:
            raise ValueError("ReportBundle senza claim")
        if self.contract.report_resolution_state is not self.report_resolution_state:
            raise ValueError("contract e bundle dichiarano risoluzioni diverse")
        bundle_ids = tuple(claim.claim_id for claim in self.claims)
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("claim_id duplicati nel bundle")
        if set(self.contract.claim_ids) != set(bundle_ids):
            raise ValueError("contract.claim_ids incoerente con i claim del bundle")
        record_ids = {record.id for record in self.sensitivity_records}
        referenced = {reference for claim in self.claims for reference in claim.sensitivity_records}
        dangling = referenced - record_ids
        if dangling:
            raise ValueError(f"sensitivity dichiarate dai claim assenti dal bundle: {dangling}")
        return self
