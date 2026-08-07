"""Core Semantic Kernel del PRD v8.0 (Appendice X.1, §8.2A).

Semantica profilo-invariante: KnowledgeState/open-world, modello ortogonale di
authority/evidence/support (§0.3-§0.4), InferentialQuery (§7.8), record di
confirmation/conflict/sensitivity/rule-challenge (§8.6-§9.7), scenario e
profile coverage (§10.7, Appendice N.2), contamination attestation
(Appendice AG) e wire contract v8 dei count (Appendice A/P, §15.10).

Politica fail-closed (Appendice AC): bare null, stringhe vuote e liste vuote
non sono mai una risposta scientifica autonoma; ogni campo significativo usa
un wrapper ``KnowledgeValue`` con stato esplicito.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any, Self

from pydantic import AliasChoices, Field, ValidationInfo, field_serializer, model_validator

from ntruth.schemas.core import FrozenModel, stable_id
from ntruth.schemas.experiment import (
    COUNT_KIND_V8_WIRE,
    CountKind,
    CountQuantifier,
    InferenceTarget,
    NScope,
)

# ---------------------------------------------------------------------------
# KnowledgeState e open-world semantics (§9.5, Appendice AC)
# ---------------------------------------------------------------------------


class KnowledgeState(StrEnum):
    """Stato open-world normativo di ogni campo scientificamente significativo."""

    PRESENT = "PRESENT"
    ABSENT_EXPLICIT = "ABSENT_EXPLICIT"
    NOT_REPORTED = "NOT_REPORTED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTING = "CONFLICTING"


#: Regole field-specific di migrazione dei bare null v7 (Appendice AC):
#: la mappatura e' consentita soltanto via regole esplicite con audit.
#: - NOT_REPORTED: le fonti ispezionate tacciono (campi dichiarativi/count);
#: - UNKNOWN: non determinabile dalle fonti disponibili (campi meccanicistici).
LEGACY_NULL_RULES: dict[str, KnowledgeState] = {
    # Count scalari di UnitAssessment: silenzio documentale.
    "n_planned": KnowledgeState.NOT_REPORTED,
    "n_declared": KnowledgeState.NOT_REPORTED,
    "n_allocated": KnowledgeState.NOT_REPORTED,
    "n_treated": KnowledgeState.NOT_REPORTED,
    "n_observed": KnowledgeState.NOT_REPORTED,
    "n_excluded": KnowledgeState.NOT_REPORTED,
    "n_analysed": KnowledgeState.NOT_REPORTED,
    "n_observational": KnowledgeState.NOT_REPORTED,
    "n_analytical": KnowledgeState.NOT_REPORTED,
    "n_independent": KnowledgeState.NOT_REPORTED,
    "biological_source_count": KnowledgeState.NOT_REPORTED,
    "effective_n": KnowledgeState.NOT_REPORTED,
    # Factor: timing esecutivi (silenzio documentale).
    "allocation_timing": KnowledgeState.NOT_REPORTED,
    "application_timing": KnowledgeState.NOT_REPORTED,
    # Factor: provenienza biologica e meccanismi (non determinabili).
    "source_biological_preparation": KnowledgeState.UNKNOWN,
    "assignment_mechanism": KnowledgeState.UNKNOWN,
    "assignment_separability": KnowledgeState.UNKNOWN,
}


class KnowledgeValue[T](FrozenModel):
    """Wrapper open-world: il silenzio non diventa mai un valore (Appendice AC).

    Regole applicate (Appendice AC):
    - bare null vietato; empty string vietata; empty list richiede lo stato;
    - ``PRESENT``/``CONFLICTING`` richiedono valore o insieme di valori;
    - ``ABSENT_EXPLICIT`` richiede evidence;
    - ``NOT_APPLICABLE`` richiede rationale.
    """

    knowledge_state: KnowledgeState
    value: T | None = None
    items: tuple[T, ...] | None = None
    source_scope: tuple[str, ...] = ()
    rationale: str | None = None
    evidence_ids: tuple[str, ...] = ()
    migration_note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any, info: ValidationInfo) -> Any:
        """Migrazione v7: bare null ammessi solo via regola field-specific."""
        if data is not None:
            return data
        context = info.context if isinstance(info.context, dict) else {}
        legacy_field = context.get("legacy_field")
        if isinstance(legacy_field, str) and legacy_field in LEGACY_NULL_RULES:
            state = LEGACY_NULL_RULES[legacy_field]
            return {
                "knowledge_state": state,
                "migration_note": (
                    "v7 bare null migrato secondo Appendice AC: "
                    f"field '{legacy_field}' -> {state.value}"
                ),
            }
        raise ValueError(
            "bare null vietato come risposta scientifica (Appendice AC); "
            "usare KnowledgeValue.migrate_legacy con regola field-specific"
        )

    @model_validator(mode="after")
    def _open_world_invariants(self) -> Self:
        if isinstance(self.value, str) and not self.value.strip():
            raise ValueError("empty string vietata come valore scientifico (AC)")
        if (
            self.knowledge_state in {KnowledgeState.PRESENT, KnowledgeState.CONFLICTING}
            and self.value is None
            and not self.items
        ):
            raise ValueError(f"{self.knowledge_state.value} richiede value o items")
        if self.knowledge_state is KnowledgeState.ABSENT_EXPLICIT:
            if self.value is not None or self.items:
                raise ValueError("ABSENT_EXPLICIT non ammette value/items")
            if not self.evidence_ids:
                raise ValueError("ABSENT_EXPLICIT richiede evidence (AC)")
        if (
            self.knowledge_state is KnowledgeState.NOT_APPLICABLE
            and not (self.rationale or "").strip()
        ):
            raise ValueError("NOT_APPLICABLE richiede rationale (AC)")
        return self

    @classmethod
    def migrate_legacy(cls, raw: Any, *, legacy_field: str) -> KnowledgeValue[T]:
        """Costruttore di migrazione v7->v8 con audit esplicito (Appendice AC)."""
        if legacy_field not in LEGACY_NULL_RULES:
            raise ValueError(f"migrazione bare null senza regola field-specific: {legacy_field!r}")
        if raw is None:
            state = LEGACY_NULL_RULES[legacy_field]
            return cls(
                knowledge_state=state,
                migration_note=(
                    "v7 bare null migrato secondo Appendice AC: "
                    f"field '{legacy_field}' -> {state.value}"
                ),
            )
        if isinstance(raw, list | tuple):
            return cls(
                knowledge_state=KnowledgeState.PRESENT,
                items=tuple(raw),
                migration_note=f"v7 lista migrata esplicitamente: field '{legacy_field}'",
            )
        return cls(
            knowledge_state=KnowledgeState.PRESENT,
            value=raw,
            migration_note=f"v7 valore migrato esplicitamente: field '{legacy_field}'",
        )


# ---------------------------------------------------------------------------
# Modello ortogonale di authority/evidence/support (§0.3-§0.4, §9.6, R.1)
# ---------------------------------------------------------------------------


class SourceClass(StrEnum):
    """Classe della fonte (Appendice A/I/AG).

    Il PRD non pubblica un elenco unico: enum chiusa sui token verbatim
    presenti negli esempi normativi (SRR-0009).
    """

    PUBLISHED_METHODS = "PUBLISHED_METHODS"
    SAMPLE_METADATA_EXECUTED = "SAMPLE_METADATA_EXECUTED"
    PROSPECTIVE_PRIVATE = "PROSPECTIVE_PRIVATE"
    POST_CUTOFF_PUBLIC = "POST_CUTOFF_PUBLIC"
    LEGACY_PUBLIC = "LEGACY_PUBLIC"


class AuthorityType(StrEnum):
    """Chi ha prodotto o confermato l'elemento (§0.4, valori minimi)."""

    SYSTEM_INFERENCE = "SYSTEM_INFERENCE"
    USER_CONFIRMATION = "USER_CONFIRMATION"
    AUTHOR_CLARIFICATION = "AUTHOR_CLARIFICATION"
    ANNOTATOR_CONFIRMATION = "ANNOTATOR_CONFIRMATION"
    DOMAIN_EXPERT_REVIEW = "DOMAIN_EXPERT_REVIEW"
    EXPERT_ADJUDICATION = "EXPERT_ADJUDICATION"
    RULE_DERIVATION = "RULE_DERIVATION"


class EvidenceBasis(StrEnum):
    """Base epistemica (§0.4 valori minimi + §9.6 evidence support levels)."""

    DIRECT_RECORD = "DIRECT_RECORD"
    STRUCTURED_DIRECT = "STRUCTURED_DIRECT"
    AUTHOR_ASSERTED = "AUTHOR_ASSERTED"
    SELF_REPORT = "SELF_REPORT"
    CORROBORATED_CONFIRMATION = "CORROBORATED_CONFIRMATION"
    INFERRED_CANDIDATE = "INFERRED_CANDIDATE"
    ADJUDICATED_REFERENCE = "ADJUDICATED_REFERENCE"
    # Livelli aggiuntivi §9.6.
    SELF_REPORTED_CONFIRMATION = "SELF_REPORTED_CONFIRMATION"
    CONFLICTING = "CONFLICTING"
    NOT_REPORTED = "NOT_REPORTED"
    UNKNOWN = "UNKNOWN"


class SupportGrade(StrEnum):
    """Qualifica non probabilistica della base evidenziale (SRR-0005).

    Unione verbatim dei tre elenchi PRD divergenti: §0.4 (8 valori),
    Appendice R.1 (8 valori) ed esempi normativi (Appendice A, §10.2).
    """

    # §0.4.
    ADJUDICATED = "ADJUDICATED"
    CORROBORATED_DIRECT = "CORROBORATED_DIRECT"
    DIRECT_SINGLE_SOURCE = "DIRECT_SINGLE_SOURCE"
    AUTHOR_CLARIFIED = "AUTHOR_CLARIFIED"
    SELF_REPORT_ONLY = "SELF_REPORT_ONLY"
    ASSERTION_ONLY = "ASSERTION_ONLY"
    MODEL_CANDIDATE = "MODEL_CANDIDATE"
    CONFLICTED = "CONFLICTED"
    # Appendice R.1.
    ADJUDICATED_REFERENCE = "ADJUDICATED_REFERENCE"
    CORROBORATED_EXECUTION_RECORD = "CORROBORATED_EXECUTION_RECORD"
    DOMAIN_EXPERT_INTERPRETATION = "DOMAIN_EXPERT_INTERPRETATION"
    DOCUMENT_ASSERTION_ONLY = "DOCUMENT_ASSERTION_ONLY"
    MODEL_CANDIDATE_ONLY = "MODEL_CANDIDATE_ONLY"
    MIXED_UNRESOLVED = "MIXED_UNRESOLVED"
    # Esempi normativi (Appendice A).
    NOT_SUPPORTED = "NOT_SUPPORTED"


# ---------------------------------------------------------------------------
# Event timing referenziato (§7.7, Appendice P.4)
# ---------------------------------------------------------------------------


class TimingRelation(StrEnum):
    """Relazione temporale fra eventi; ``timing_relative_to_split`` e' deprecato."""

    BEFORE = "BEFORE"
    AFTER = "AFTER"
    SAME_EVENT = "SAME_EVENT"
    OVERLAPS = "OVERLAPS"
    UNKNOWN = "UNKNOWN"


class EventTiming(FrozenModel):
    """Relazione temporale ancorata a event IDs (§7.7, Appendice P.4)."""

    subject_event_id: str | None = None
    reference_event_id: str
    relation: TimingRelation
    evidence_refs: tuple[str, ...] = ()
    knowledge_state: KnowledgeState | None = None

    @model_validator(mode="after")
    def _anchored(self) -> Self:
        if not self.reference_event_id.strip():
            raise ValueError("timing senza reference_event_id")
        return self


# ---------------------------------------------------------------------------
# InferentialQuery (§7.8, Appendice A)
# ---------------------------------------------------------------------------


class InferentialQuery(FrozenModel):
    """Oggetto versionato a cui ogni conclusione e' associata (§7.8).

    Superset dei contratti v6 ``InferenceTarget``/``NScope``: i campi
    scientificamente significativi accettano sia la forma stringa §7.8
    (``valore|unknown``) sia il wrapper ``KnowledgeValue`` dell'Appendice A.
    """

    id: str = Field(validation_alias=AliasChoices("id", "query_id"))
    profile_id: str | None = None
    factor_id: str | None = None
    contrast_id: str | None = None
    compared_levels: tuple[str, ...] = ()
    endpoint_id: str | None = None
    timepoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("timepoint", "timepoint_id", "condition_or_timepoint"),
    )
    estimand: str | KnowledgeValue[Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("estimand", "effect_measure_or_estimand"),
    )
    population: str | KnowledgeValue[Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("population", "inference_population"),
    )
    analysis_level: str | KnowledgeValue[Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("analysis_level", "inference_level"),
    )

    model_config = FrozenModel.model_config | {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _deterministic_id(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        raw_id = payload.get("id", payload.get("query_id"))
        if raw_id is None or not str(raw_id).strip():
            payload["id"] = stable_id(
                "IQ",
                payload.get("factor_id"),
                payload.get("contrast_id"),
                payload.get("endpoint_id"),
                payload.get("timepoint_id", payload.get("condition_or_timepoint")),
            )
        return payload

    @model_validator(mode="after")
    def _scoped(self) -> Self:
        if not any((self.factor_id, self.contrast_id, self.endpoint_id, self.compared_levels)):
            raise ValueError("InferentialQuery senza factor/contrast/endpoint/levels")
        return self

    @classmethod
    def from_inference_target(cls, target: InferenceTarget) -> InferentialQuery:
        """Conversione deterministica del contratto v6 ``InferenceTarget``."""
        return cls(
            id=target.id,
            factor_id=target.factor_ids[0] if target.factor_ids else None,
            contrast_id=target.contrast_ids[0] if target.contrast_ids else None,
            endpoint_id=target.endpoint_ids[0] if target.endpoint_ids else None,
            population=target.population_of_inference or None,
            analysis_level=(
                str(target.target_biological_unit.value)
                if target.target_biological_unit is not None
                else None
            ),
        )

    @classmethod
    def from_nscope(cls, scope: NScope, query_id: str | None = None) -> InferentialQuery:
        """Conversione deterministica del contratto v6 ``NScope``."""
        payload: dict[str, Any] = {
            "factor_id": scope.factor_id,
            "contrast_id": scope.contrast_id,
            "endpoint_id": scope.endpoint_id,
            "timepoint": scope.timepoint,
            "population": scope.population,
            "analysis_level": (str(scope.unit_type.value) if scope.unit_type is not None else None),
        }
        if query_id:
            payload["id"] = query_id
        if scope.group:
            payload["compared_levels"] = (scope.group,)
        if scope.is_global and not any(payload.values()):
            raise ValueError("NScope globale senza contenuto non e' una query v8")
        return cls(**payload)


# ---------------------------------------------------------------------------
# Confirmation, conflict, sensitivity, rule challenge (§8.7, §9.7)
# ---------------------------------------------------------------------------


class ConfirmationEvent(FrozenModel):
    """Evento di autorita' umana con qualificazione ortogonale (§0.3-§0.4)."""

    id: str
    authority_type: AuthorityType
    evidence_basis: EvidenceBasis
    support_grade: SupportGrade
    actor_id: str
    scope: str
    statement: str
    source_ref: str | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        if not self.statement.strip():
            raise ValueError("confirmation event senza statement")
        if not self.actor_id.strip():
            raise ValueError("confirmation event senza actor_id")
        return self


class ConflictStatus(StrEnum):
    """Stato di un conflitto fra fonti (§8.7)."""

    UNRESOLVED = "unresolved"
    RESOLVED_WITH_RATIONALE = "resolved_with_rationale"


class ConflictRecord(FrozenModel):
    """Fonti incompatibili: il conflitto resta tracciato, mai cancellato (§8.7)."""

    id: str
    field: str
    sources: tuple[str, ...]
    status: ConflictStatus
    resolution_event: KnowledgeValue[Any] | None = None

    @model_validator(mode="after")
    def _resolution_documented(self) -> Self:
        if len(self.sources) < 2:
            raise ValueError("conflict record richiede almeno due fonti")
        if self.status is ConflictStatus.RESOLVED_WITH_RATIONALE and (
            self.resolution_event is None or not (self.resolution_event.rationale or "").strip()
        ):
            raise ValueError("conflitto risolto richiede resolution_event con rationale")
        return self


class SensitivityRecord(FrozenModel):
    """Impatto controfattuale di una conferma fallibile (§9.7).

    Nessuna probabilita' soggettiva: solo trasparenza sull'impatto.
    """

    id: str
    derived_claim_id: str
    decisive_predicate_id: str
    current_support_grade: SupportGrade
    current_value: Any = None
    counterfactual_value: Any = None
    current_output: dict[str, Any] = Field(default_factory=dict)
    counterfactual_output: dict[str, Any] = Field(default_factory=dict)
    interpretation: str = ""

    @model_validator(mode="after")
    def _counterfactual_defined(self) -> Self:
        if not self.decisive_predicate_id.strip():
            raise ValueError("sensitivity senza predicato decisivo")
        if not self.current_output or not self.counterfactual_output:
            raise ValueError("sensitivity richiede entrambi gli output controfattuali")
        return self


class RuleChallengeStatus(StrEnum):
    """Stato di una contestazione di regola (§8.7)."""

    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class RuleChallenge(FrozenModel):
    """Un esperto contesta una derivazione senza patchare il claim (§8.7)."""

    id: str
    derived_claim_id: str
    challenged_clause: str
    challenger_role: AuthorityType
    rationale: str
    status: RuleChallengeStatus

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        if not self.rationale.strip():
            raise ValueError("rule challenge senza rationale")
        if not self.challenged_clause.strip():
            raise ValueError("rule challenge senza clausola contestata")
        return self


# ---------------------------------------------------------------------------
# Scenario e profile coverage (§10.7, Appendice N.2, §7.17)
# ---------------------------------------------------------------------------


class ScenarioCoverageStatus(StrEnum):
    """Attestazione di esaustivita' di un insieme di scenari (§10.7)."""

    EXHAUSTIVE_WITHIN_PROFILE = "EXHAUSTIVE_WITHIN_PROFILE"
    NON_EXHAUSTIVE = "NON_EXHAUSTIVE"
    UNKNOWN = "UNKNOWN"


class ScenarioCoverage(FrozenModel):
    """Ogni scenario set registra copertura, clausole emittenti e omissioni."""

    status: ScenarioCoverageStatus
    profile_id: str
    theory_version: str
    emitting_clauses: tuple[str, ...] = ()
    omitted_dimensions: KnowledgeValue[Any] | None = None
    caveat: KnowledgeValue[Any] | None = None

    @model_validator(mode="after")
    def _non_exhaustive_never_complete(self) -> Self:
        if not self.emitting_clauses:
            raise ValueError("scenario coverage senza clausole emittenti")
        return self


class ProfileCoverageStatus(StrEnum):
    """Stato di copertura del profilo (Appendice A, AF)."""

    COVERED_WITH_KNOWN_GAPS = "COVERED_WITH_KNOWN_GAPS"
    PARTIAL_PROFILE_COVERAGE = "PARTIAL_PROFILE_COVERAGE"


class ProfileCoverageStatement(FrozenModel):
    """Copertura del profilo + predicate sufficiency statement (Appendice N.2)."""

    status: ProfileCoverageStatus
    known_gaps: tuple[str, ...] = ()
    covered_claims: tuple[str, ...] = ()
    decisive_predicate_set: tuple[str, ...] = ()
    counterexamples_considered: tuple[str, ...] = ()
    reviewer: str | None = None
    version: str | None = None
    predicate_sufficiency_statement: str = ""


# ---------------------------------------------------------------------------
# Experiment Block boundary (§8.6)
# ---------------------------------------------------------------------------


class BlockBoundaryStatus(StrEnum):
    """Autorita' del boundary: proposto, confermato o in conflitto (§8.6)."""

    CONFIRMED = "CONFIRMED"
    CANDIDATE = "CANDIDATE"
    CONFLICTING = "CONFLICTING"


class BlockBoundaryRecord(FrozenModel):
    """Un block split/merge deve essere tracciato (§8.6)."""

    block_id: str
    boundary_basis: tuple[str, ...]
    source_refs: tuple[str, ...] = ()
    status: BlockBoundaryStatus
    rationale: str

    @model_validator(mode="after")
    def _grounded(self) -> Self:
        if not self.boundary_basis:
            raise ValueError("block boundary senza basis")
        if not self.rationale.strip():
            raise ValueError("block boundary senza rationale")
        return self


# ---------------------------------------------------------------------------
# Contamination attestation (Appendice AG)
# ---------------------------------------------------------------------------


class ChallengeSourceClass(StrEnum):
    """Classe della fonte di un external challenge item (Appendice AG)."""

    PROSPECTIVE_PRIVATE = "PROSPECTIVE_PRIVATE"
    POST_CUTOFF_PUBLIC = "POST_CUTOFF_PUBLIC"
    LEGACY_PUBLIC = "LEGACY_PUBLIC"


class TextExposureRisk(StrEnum):
    """Rischio di esposizione testuale del backbone (Appendice AG)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


def _first_alternative(value: Any, enum_type: type[StrEnum], field: str) -> Any:
    """Forma template ``A|B|C`` del PRD: ogni token deve essere un membro."""
    if isinstance(value, str) and "|" in value:
        tokens = value.split("|")
        for token in tokens:
            try:
                enum_type(token)
            except ValueError as exc:
                raise ValueError(f"{field}: token non normativo {token!r}") from exc
        return tokens[0]
    return value


class BackboneRecord(FrozenModel):
    """Backbone del modello sotto attestation (Appendice AG)."""

    model_id: str
    release_date: str | dt.date
    documented_training_cutoff: KnowledgeValue[Any]

    @model_validator(mode="after")
    def _model_named(self) -> Self:
        if not self.model_id.strip():
            raise ValueError("backbone senza model_id")
        return self


class ContaminationExposureAssessment(FrozenModel):
    """Valutazione dell'esposizione con evidenza e rischio residuo (AG)."""

    evidence: tuple[str, ...] = ()
    probes_run: tuple[str, ...] = ()
    residual_risk: TextExposureRisk


class ContaminationAttestation(FrozenModel):
    """External Challenge Contamination Attestation (Appendice AG).

    Un item HIGH/UNKNOWN puo' restare diagnostic ma non puo' essere l'unica
    base di un claim di generalizzazione.
    """

    challenge_item_id: str
    source_class: ChallengeSourceClass
    publication_or_creation_date: str | dt.date
    study_family_id: str
    training_eligible: bool
    model_selection_eligible: bool
    backbone: BackboneRecord
    text_exposure_risk: TextExposureRisk
    exposure_assessment: ContaminationExposureAssessment
    permitted_claim: tuple[str, ...] = ()
    forbidden_claim: tuple[str, ...] = ()
    custodian: str
    attested_by: str

    @model_validator(mode="before")
    @classmethod
    def _resolve_template_alternatives(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if "source_class" in payload:
            payload["source_class"] = _first_alternative(
                payload["source_class"], ChallengeSourceClass, "source_class"
            )
        if "text_exposure_risk" in payload:
            payload["text_exposure_risk"] = _first_alternative(
                payload["text_exposure_risk"], TextExposureRisk, "text_exposure_risk"
            )
        return payload

    @model_validator(mode="after")
    def _high_risk_never_sole_basis(self) -> Self:
        if (self.training_eligible or self.model_selection_eligible) and (
            self.source_class is not ChallengeSourceClass.PROSPECTIVE_PRIVATE
        ):
            raise ValueError(
                "item non prospective_private non e' eleggibile per training/selection"
            )
        return self


# ---------------------------------------------------------------------------
# ConditionRecord e domanda primaria (§10.12)
# ---------------------------------------------------------------------------


class ConditionRecord(FrozenModel):
    """Ogni output condizionale contiene condizione leggibile e domanda primaria."""

    id: str
    predicate: str
    claim_ids: tuple[str, ...] = ()
    human_readable: dict[str, str] = Field(default_factory=dict)
    evidence_required: tuple[str, ...] = ()
    if_true_effect: str
    if_false_effect: str
    scenario_coverage: ScenarioCoverageStatus | ScenarioCoverage
    primary_question_id: str

    @model_validator(mode="after")
    def _primary_question_mandatory(self) -> Self:
        if not self.primary_question_id.strip():
            raise ValueError("condition record senza domanda primaria (§10.12)")
        if not self.predicate.strip():
            raise ValueError("condition record senza predicate")
        if not self.if_true_effect.strip() or not self.if_false_effect.strip():
            raise ValueError("condition record senza entrambi gli effetti")
        return self


# ---------------------------------------------------------------------------
# Count wire contract v8 (Appendice A/P, §15.10)
# ---------------------------------------------------------------------------


class CountScopeStatus(StrEnum):
    """Stato dello scope di un count dichiarato (Appendice A, P.3)."""

    AMBIGUOUS = "AMBIGUOUS"


class V8CountRecord(FrozenModel):
    """Wire contract v8 di un count canonico, keyed a query/coorte.

    Estende il registro v6 (``CountRecord``) con KnowledgeState, query_id,
    group_id e cohort_id come mostrato negli esempi normativi; la logica di
    risoluzione resta quella v6 fino alla FASE 3. La serializzazione espone
    il naming canonico §7.9 (``COUNT_KIND_V8_WIRE``) mentre il registro v6
    conserva i valori legacy congelati (Appendice AE.1).
    """

    count_id: str
    kind: CountKind
    knowledge_state: KnowledgeState | None = None
    value: float | None = Field(default=None, ge=0)
    quantifier: CountQuantifier | None = None
    unit_type: str | KnowledgeValue[Any] | None = None
    query_id: str | None = None
    group_id: str | None = None
    cohort_id: str | None = None
    factor_id: str | None = None
    contrast_id: str | None = None
    endpoint_id: str | None = None
    timepoint: str | None = Field(
        default=None, validation_alias=AliasChoices("timepoint", "timepoint_id")
    )
    population_scope: str | None = None
    condition: str | None = None
    scope_status: CountScopeStatus | None = None
    source_evidence: tuple[str, ...] = ()
    rule_trace: tuple[str, ...] = ()
    diagnostic_only: bool = False

    model_config = FrozenModel.model_config | {"populate_by_name": True}

    @field_serializer("kind")
    def _serialize_kind_v8_wire(self, value: CountKind) -> str:
        """Il wire v8 espone la denominazione §7.9, non il valore v6 (AE.1)."""
        return COUNT_KIND_V8_WIRE[value]

    @model_validator(mode="before")
    @classmethod
    def _default_state_and_quantifier(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        has_value = payload.get("value") is not None
        if payload.get("knowledge_state") is None:
            if has_value:
                # §15.10: count con valore ma senza stato esplicito: il valore
                # e' presente, la normalizzazione lo marca PRESENT con audit.
                payload["knowledge_state"] = KnowledgeState.PRESENT
            else:
                raise ValueError("count v8 senza valore richiede knowledge_state esplicito (AC)")
        if payload.get("quantifier") is None:
            payload["quantifier"] = (
                CountQuantifier.EXACT if has_value else CountQuantifier.NOT_REPORTED
            )
        if payload.get("kind") is not None:
            try:
                resolved_kind = CountKind(payload["kind"])
            except ValueError as exc:
                raise ValueError(f"count v8 con kind non normativo: {payload['kind']!r}") from exc
            if resolved_kind is CountKind.DIAGNOSTIC_EFFECTIVE_N:
                # Il registro canonico mantiene la regola v6: l'effective n
                # resta un diagnostico separato, mai promosso a count.
                payload["diagnostic_only"] = True
        return payload

    @model_validator(mode="after")
    def _state_value_coherent(self) -> Self:
        assert self.knowledge_state is not None  # garantito dal before-validator
        if self.knowledge_state is KnowledgeState.PRESENT and self.value is None:
            raise ValueError("count PRESENT richiede value")
        if (
            self.knowledge_state
            in {
                KnowledgeState.NOT_REPORTED,
                KnowledgeState.UNKNOWN,
                KnowledgeState.NOT_APPLICABLE,
            }
            and self.value is not None
        ):
            raise ValueError(f"count {self.knowledge_state.value} non ammette value")
        return self

    def scope_key(self) -> tuple[str | None, ...]:
        """Chiave canonica dello scope v8 (Appendice P.1)."""
        return (
            str(self.unit_type) if self.unit_type is not None else None,
            self.factor_id,
            self.contrast_id,
            self.group_id,
            self.endpoint_id,
            self.timepoint,
            self.cohort_id,
            self.quantifier.value if self.quantifier is not None else None,
        )
