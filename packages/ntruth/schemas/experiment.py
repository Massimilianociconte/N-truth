"""ExperimentBlock e contratti dati (PRD 12).

L'unita primaria di annotazione e l'ExperimentBlock: un insieme coerente di
Methods, legend, statistica e metadata che descrive un esperimento o contrasto.
Un articolo contiene piu blocchi, spesso con gerarchie e n diversi; il paper
intero non riceve mai una singola label (PRD 12.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import (
    AlertClass,
    Confidence,
    Determinability,
    EvidenceSpan,
    NTruthModel,
    Provenance,
    ProvenanceKind,
    Severity,
    stable_id,
)
from ntruth.schemas.coreference import CoreferenceLink, Mention
from ntruth.schemas.graph import (
    ALLOCATABLE_NODE_TYPES,
    GraphNode,
    GraphRelation,
    NodeType,
    RelationType,
    rank_of,
)


class NKind(StrEnum):
    """Tipo di n (PRD 7 e 15.4 layer H)."""

    DECLARED = "declared"
    OBSERVATIONAL = "observational"
    INDEPENDENT = "independent"
    ALLOCATED = "allocated"
    ANALYZED = "analyzed"


class Inferability(StrEnum):
    """Quanto l'n indipendente e derivabile dal materiale disponibile."""

    INFERABLE = "inferable"
    CONDITIONAL = "conditional"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    NOT_INFERABLE = "not_inferable"


class RiskLabel(StrEnum):
    """Etichetta di rischio (PRD 15.4 layer I)."""

    NO_ISSUE = "no_issue"
    POTENTIAL = "potential_pseudoreplication"
    LIKELY = "likely_pseudoreplication"
    CRITICAL = "critical_pseudoreplication"
    INSUFFICIENT = "insufficient_information"


class InferenceTargetStatus(StrEnum):
    """Stato del target inferenziale, distinto dalla sua completezza.

    ``extracted`` e un candidate fact ancorato alla fonte; ``user_confirmed``
    registra una conferma esplicita; ``missing`` e ``conflicted`` impongono
    elicitazione o astensione. Nessuno stato certifica la validita scientifica
    del disegno.
    """

    EXTRACTED = "extracted"
    USER_CONFIRMED = "user_confirmed"
    MISSING = "missing"
    CONFLICTED = "conflicted"


class ConditionalScenario(NTruthModel):
    """Due esiti espliciti per un fatto decisivo ancora da confermare.

    Il motore conserva entrambe le alternative e la domanda che le risolve:
    non trasforma quindi l'incertezza in un singolo ``n`` apparentemente
    preciso (PRD v3, sezione 10.2).
    """

    conditional_on: str
    if_confirmed: dict[str, int]
    if_rejected: dict[str, int]
    question: str
    rule_id: str
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _complete_and_non_negative(self) -> Self:
        if not self.conditional_on.strip():
            raise ValueError("scenario condizionale senza condizione")
        if not self.question.strip():
            raise ValueError("scenario condizionale senza domanda")
        if not self.rule_id.strip():
            raise ValueError("scenario condizionale senza rule_id")
        if not self.if_confirmed or not self.if_rejected:
            raise ValueError("scenario condizionale senza entrambi gli esiti")
        if any(value < 0 for value in (*self.if_confirmed.values(), *self.if_rejected.values())):
            raise ValueError("scenario condizionale con n negativo")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("scenario condizionale con evidence_ids duplicati")
        return self


class NScope(NTruthModel):
    """n e per gruppo, contrasto ed endpoint (PRD GEN-006).

    Uno scope globale e ammesso solo se dichiarato esplicitamente (PRD 12.4).
    """

    factor_id: str | None = None
    contrast_id: str | None = None
    endpoint_id: str | None = None
    group: str | None = None
    timepoint: str | None = None
    inference_target_id: str | None = None
    is_global: bool = False

    @model_validator(mode="after")
    def _scope_is_explicit(self) -> Self:
        specified = any(
            (
                self.factor_id,
                self.contrast_id,
                self.endpoint_id,
                self.group,
                self.timepoint,
                self.inference_target_id,
            )
        )
        if not specified and not self.is_global:
            raise ValueError(
                "NScope vuoto: indicare factor/contrast/endpoint/group/target oppure is_global=True"
            )
        return self

    def key(self) -> tuple[str | None, ...]:
        legacy_key = (
            self.factor_id,
            self.contrast_id,
            self.endpoint_id,
            self.group,
            self.timepoint,
        )
        if self.inference_target_id is None:
            # Preserva gli ID content-addressed prodotti dalle versioni precedenti.
            return legacy_key
        return (*legacy_key, self.inference_target_id)

    def describe(self) -> str:
        if self.is_global and not any(self.key()):
            return "scope globale dichiarato"
        parts = [
            f"fattore={self.factor_id}" if self.factor_id else None,
            f"contrasto={self.contrast_id}" if self.contrast_id else None,
            f"endpoint={self.endpoint_id}" if self.endpoint_id else None,
            f"gruppo={self.group}" if self.group else None,
            f"tempo={self.timepoint}" if self.timepoint else None,
            f"target={self.inference_target_id}" if self.inference_target_id else None,
        ]
        return ", ".join(p for p in parts if p)


class NStatement(NTruthModel):
    """Una menzione di n nel materiale, con entita, scope ed evidenza (PRD 12.3)."""

    id: str
    value: int | None = Field(default=None, ge=0)
    entity_type: str
    node_type: NodeType | None = None
    scope: NScope
    kind: NKind
    qualifiers: tuple[str, ...] = ()
    raw_text: str = ""
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DataSufficiency(NTruthModel):
    """Completezza informativa per dimensione (PRD 12.3).

    Distinta dalla confidence estrattiva: un testo puo dichiarare "120 cells"
    con grande chiarezza e non dire se le colture sono indipendenti (PRD 13.5).
    """

    intervention_level: Confidence = Confidence.UNKNOWN
    source_independence: Confidence = Confidence.UNKNOWN
    exclusions: Confidence = Confidence.UNKNOWN
    aggregation: Confidence = Confidence.UNKNOWN
    statistical_model: Confidence = Confidence.UNKNOWN

    @property
    def overall(self) -> Confidence:
        order = [Confidence.UNKNOWN, Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH]
        values = [
            self.intervention_level,
            self.source_independence,
            self.exclusions,
            self.aggregation,
            self.statistical_model,
        ]
        return min(values, key=order.index)


class InferenceTarget(NTruthModel):
    """Domanda e popolazione a cui uno scope inferenziale deve rispondere.

    Questo e intenzionalmente un contratto minimale per disegni preclinici, non
    l'adozione implicita dell'estimand ICH E9(R1). Testo e popolazione non
    vengono completati dal motore: se mancano, il compiler genera domande.
    """

    id: str
    question_text: str = ""
    claim_text: str = ""
    population_of_inference: str = ""
    factor_ids: tuple[str, ...] = ()
    contrast_ids: tuple[str, ...] = ()
    endpoint_ids: tuple[str, ...] = ()
    target_biological_unit: NodeType | None = None
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance
    status: InferenceTargetStatus = InferenceTargetStatus.MISSING

    @model_validator(mode="after")
    def _evidence_grounded(self) -> Self:
        if self.status is not InferenceTargetStatus.MISSING and not (
            self.question_text.strip() or self.claim_text.strip()
        ):
            raise ValueError("inference target non-missing senza domanda o claim")

        if (
            self.status
            in {
                InferenceTargetStatus.EXTRACTED,
                InferenceTargetStatus.CONFLICTED,
            }
            and not self.evidence_ids
        ):
            raise ValueError(f"inference target {self.status} senza evidence_ids")

        if (
            self.status is InferenceTargetStatus.USER_CONFIRMED
            and not self.evidence_ids
            and self.provenance.origin not in {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION}
        ):
            raise ValueError(
                "inference target confermato senza evidenza o provenance utente/adjudication"
            )

        if not set(self.evidence_ids).issubset(self.provenance.evidence_ids):
            raise ValueError("evidence_ids del target assenti dalla provenance")

        for field_name, values in (
            ("factor_ids", self.factor_ids),
            ("contrast_ids", self.contrast_ids),
            ("endpoint_ids", self.endpoint_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contiene riferimenti duplicati")
        return self


class UnitAssessment(NTruthModel):
    """Unita e n per uno scope specifico (PRD 12.2)."""

    id: str
    scope: NScope
    biological_unit: NodeType | None = None
    experimental_unit: NodeType | None = None
    observational_unit: NodeType | None = None
    analytical_unit: NodeType | None = None
    n_declared: int | None = None
    n_allocated: int | None = Field(default=None, ge=0)
    n_analyzed: int | None = Field(default=None, ge=0)
    n_observational: int | None = None
    n_independent: int | None = None
    independent_entity_type: str | None = None
    cluster_types: tuple[NodeType, ...] = ()
    inferability: Inferability = Inferability.NOT_INFERABLE
    conditional_scenarios: tuple[ConditionalScenario, ...] = ()
    risk: RiskLabel = RiskLabel.INSUFFICIENT
    data_sufficiency: DataSufficiency = Field(default_factory=DataSufficiency)
    rationale: str = ""
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance

    @model_validator(mode="before")
    @classmethod
    def _conditional_inferability(cls, data: object) -> object:
        if isinstance(data, Mapping):
            payload = dict(data)
            if payload.get("conditional_scenarios") and "inferability" not in payload:
                payload["inferability"] = Inferability.CONDITIONAL
            return payload
        return data

    @model_validator(mode="after")
    def _no_silent_substitution(self) -> Self:
        """Uno scenario numerico non puo convivere con un n scalare autorevole."""
        if self.inferability is Inferability.NOT_INFERABLE and self.n_independent is not None:
            raise ValueError("n_independent valorizzato ma inferability=not_inferable")
        if self.conditional_scenarios and self.inferability is not Inferability.CONDITIONAL:
            raise ValueError("scenari condizionali richiedono inferability=conditional")
        if self.conditional_scenarios and self.n_independent is not None:
            raise ValueError("scenari condizionali richiedono n_independent=null")
        conditions = [scenario.conditional_on for scenario in self.conditional_scenarios]
        if len(conditions) != len(set(conditions)):
            raise ValueError("conditional_scenarios contiene condizioni duplicate")
        return self


class Question(NTruthModel):
    """Domanda mirata su informazione mancante (PRD FR-021)."""

    id: str
    text: str
    reason: str
    missing_field: str | None = None
    scope: NScope | None = None
    priority: int = Field(default=0, ge=0, le=100)
    decisive: bool = False
    impact: str = ""


class Contradiction(NTruthModel):
    """Fonti contraddittorie: restano alternative finche un umano non risolve (GEN-007)."""

    id: str
    description: str
    statement_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    status: Literal["unresolved", "resolved_by_user", "resolved_by_adjudication"] = "unresolved"


class Alert(NTruthModel):
    """Esito di una regola. Mai un verdetto sul paper (PRD FR-023)."""

    id: str
    rule_id: str
    ruleset_version: str
    alert_class: AlertClass = AlertClass.DESIGN_REPLICATION
    severity: Severity
    message: str
    scope: NScope | None = None
    evidence_ids: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    question_ids: tuple[str, ...] = ()
    premise_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # Deprecated compatibility alias. It describes confidence in the premises,
    # never a probability attached to the deterministic rule consequence.
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_human_confirmation: bool = False
    provenance: Provenance

    @model_validator(mode="before")
    @classmethod
    def _cohere_legacy_confidence(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        has_legacy = "confidence" in payload
        has_canonical = "premise_confidence" in payload
        if has_canonical:
            payload["confidence"] = payload["premise_confidence"]
        elif has_legacy:
            payload["premise_confidence"] = payload["confidence"]
        return payload

    @model_validator(mode="after")
    def _traceable(self) -> Self:
        """NFR-03: 100% alert con rule ID ed evidence o missing-info."""
        if not (self.evidence_ids or self.missing_information or self.conflict_ids):
            raise ValueError(
                f"alert {self.rule_id} senza evidence, missing_information o conflict_ids"
            )
        if self.confidence != self.premise_confidence:
            raise ValueError("confidence legacy incoerente con premise_confidence")
        return self


class CorrectionReason(StrEnum):
    """Motivo obbligatorio di una correzione (PRD 20.3)."""

    PARSER_ERROR = "parser_error"
    MODEL_ERROR = "model_error"
    SOURCE_MISSING = "source_missing"
    DOMAIN_JUDGEMENT = "domain_judgement"
    TYPO = "typo"
    OTHER = "other"


class Correction(NTruthModel):
    """Patch append-only. Non cancella mai l'estrazione originale (PRD 7.4)."""

    id: str
    sequence: int = Field(ge=0)
    reason: CorrectionReason
    rationale: str = ""
    patch: tuple[dict[str, object], ...] = ()  # JSON Patch (RFC 6902)
    evidence_ids: tuple[str, ...] = ()
    reviewer_role: str | None = None
    verified: bool = False  # correzioni non verificate non entrano nel training pool


class Factor(NTruthModel):
    """Fattore con allocazione e applicazione mantenute separate.

    ``assignment_*`` resta un alias serializzato per i consumer v0.1 e viene
    sincronizzato con ``allocation_*``. Non viene mai sincronizzato con
    ``application_*``, che puo legittimamente descrivere un livello diverso.
    """

    id: str
    name: str
    levels: tuple[str, ...] = ()
    kind: Literal["treatment", "genotype", "dose", "time", "diet", "other"] = "other"
    allocation_level: NodeType | None = None
    application_level: NodeType | None = None
    allocation_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    application_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    allocation_evidence_ids: tuple[str, ...] = ()
    application_evidence_ids: tuple[str, ...] = ()
    randomized: bool | None = None
    # UK spelling retained for the PRD example and serialized compatibility.
    randomised: bool | None = None
    # Deprecated compatibility aliases for the original v0.1 contract.
    assignment_level: NodeType | None = None
    assignment_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance

    @model_validator(mode="before")
    @classmethod
    def _cohere_legacy_assignment(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        legacy_level = payload.get("assignment_level")
        canonical_level = payload.get("allocation_level")
        if "allocation_level" in payload:
            payload["assignment_level"] = canonical_level
        elif "assignment_level" in payload:
            payload["allocation_level"] = legacy_level

        if "allocation_confidence" in payload:
            payload["assignment_confidence"] = payload["allocation_confidence"]
        elif "assignment_confidence" in payload:
            payload["allocation_confidence"] = payload["assignment_confidence"]

        if "allocation_evidence_ids" not in payload and payload.get("evidence_ids"):
            payload["allocation_evidence_ids"] = payload["evidence_ids"]
        if "randomized" in payload:
            payload["randomised"] = payload["randomized"]
        elif "randomised" in payload:
            payload["randomized"] = payload["randomised"]
        return payload

    @model_validator(mode="after")
    def _allocation_alias_is_coherent(self) -> Self:
        if self.assignment_level is not self.allocation_level:
            raise ValueError("assignment_level legacy incoerente con allocation_level")
        if self.assignment_confidence != self.allocation_confidence:
            raise ValueError("assignment_confidence legacy incoerente con allocation_confidence")
        if self.randomized != self.randomised:
            raise ValueError("randomized incoerente con alias randomised")
        for field_name, level in (
            ("allocation_level", self.allocation_level),
            ("application_level", self.application_level),
        ):
            if level is not None and level not in ALLOCATABLE_NODE_TYPES:
                raise ValueError(f"{field_name} non e un NodeType allocabile: {level}")
        for field_name, values in (
            ("levels", self.levels),
            ("evidence_ids", self.evidence_ids),
            ("allocation_evidence_ids", self.allocation_evidence_ids),
            ("application_evidence_ids", self.application_evidence_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contiene riferimenti duplicati")
        return self


class Contrast(NTruthModel):
    """Confronto specifico tra livelli di uno o piu fattori (PRD 7)."""

    id: str
    label: str
    factor_ids: tuple[str, ...] = ()
    # Deprecated compatibility alias: per contrasti multifattoriali indica il
    # primo fattore in ordine dichiarato, senza eliminare gli altri.
    factor_id: str = ""
    compared_levels: tuple[str, ...] = ()
    group_a: str | None = None
    group_b: str | None = None
    endpoint_id: str | None = None
    endpoint_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance

    @model_validator(mode="before")
    @classmethod
    def _cohere_factor_alias(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        factor_id = payload.get("factor_id")
        factor_ids = tuple(payload.get("factor_ids") or ())
        if factor_ids:
            payload["factor_id"] = factor_ids[0]
        elif factor_id is not None:
            payload["factor_ids"] = (factor_id,)

        compared_levels = tuple(payload.get("compared_levels") or ())
        legacy_levels = tuple(
            level for level in (payload.get("group_a"), payload.get("group_b")) if level is not None
        )
        if legacy_levels and not compared_levels:
            payload["compared_levels"] = legacy_levels
        elif compared_levels:
            payload["group_a"] = compared_levels[0]
            payload["group_b"] = compared_levels[1] if len(compared_levels) > 1 else None

        endpoint_id = payload.get("endpoint_id")
        endpoint_ids = tuple(payload.get("endpoint_ids") or ())
        if endpoint_ids:
            payload["endpoint_id"] = endpoint_ids[0]
        elif endpoint_id is not None:
            payload["endpoint_ids"] = (endpoint_id,)
        return payload

    @model_validator(mode="after")
    def _factor_refs_are_coherent(self) -> Self:
        if not self.factor_ids or not self.factor_id:
            raise ValueError("contrasto senza factor_ids")
        if self.factor_id not in self.factor_ids:
            raise ValueError("factor_id legacy assente da factor_ids")
        if len(self.factor_ids) != len(set(self.factor_ids)):
            raise ValueError("factor_ids contiene riferimenti duplicati")
        legacy_levels = tuple(level for level in (self.group_a, self.group_b) if level is not None)
        if legacy_levels and any(level not in self.compared_levels for level in legacy_levels):
            raise ValueError("group_a/group_b legacy incoerenti con compared_levels")
        if len(self.compared_levels) != len(set(self.compared_levels)):
            raise ValueError("compared_levels contiene valori duplicati")
        if self.endpoint_id is not None and self.endpoint_id not in self.endpoint_ids:
            raise ValueError("endpoint_id legacy assente da endpoint_ids")
        if len(self.endpoint_ids) != len(set(self.endpoint_ids)):
            raise ValueError("endpoint_ids contiene riferimenti duplicati")
        return self


class Estimand(NTruthModel):
    """Oggetto inferenziale minimo richiesto dal PRD v3, sezione 7.8."""

    id: str
    endpoint_id: str
    effect_measure: str
    target_population_or_unit: str
    generalization_level: str
    factor_ids: tuple[str, ...]
    timepoint: str | None = None
    condition: str | None = None
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def _minimum_is_explicit(self) -> Self:
        for field_name, value in (
            ("endpoint_id", self.endpoint_id),
            ("effect_measure", self.effect_measure),
            ("target_population_or_unit", self.target_population_or_unit),
            ("generalization_level", self.generalization_level),
        ):
            if not value.strip():
                raise ValueError(f"estimand senza {field_name}")
        if not self.factor_ids:
            raise ValueError("estimand senza factor_ids")
        if len(self.factor_ids) != len(set(self.factor_ids)):
            raise ValueError("estimand factor_ids duplicati")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("estimand evidence_ids duplicati")
        if self.provenance is not None and not set(self.evidence_ids).issubset(
            self.provenance.evidence_ids
        ):
            raise ValueError("evidence_ids dell'estimand assenti dalla provenance")
        return self


class Endpoint(NTruthModel):
    """Variabile di risultato e livello su cui e misurata (PRD 7)."""

    id: str
    name: str
    measured_on: NodeType | None = None
    timepoints: tuple[str, ...] = ()
    aggregation: str | None = None
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance


class StatisticalModelFact(NTruthModel):
    """Modello statistico dichiarato, versionato insieme all'ExperimentBlock.

    Questo e il fatto scientifico materializzato e correggibile. Le omonime
    dataclass del layer ``extract`` restano candidate fact transitorie e non
    entrano direttamente nel report o nel correction ledger.
    """

    id: str
    kind: str
    accounts_for: tuple[NodeType, ...] = ()
    declared_clustering: tuple[NodeType, ...] = ()
    raw_text: str = ""
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance

    @model_validator(mode="before")
    @classmethod
    def _cohere_declared_clustering(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        if "declared_clustering" in payload:
            payload["accounts_for"] = payload["declared_clustering"]
        elif "accounts_for" in payload:
            payload["declared_clustering"] = payload["accounts_for"]
        return payload

    @model_validator(mode="after")
    def _traceable(self) -> Self:
        if self.accounts_for != self.declared_clustering:
            raise ValueError("accounts_for legacy incoerente con declared_clustering")
        if len(self.declared_clustering) != len(set(self.declared_clustering)):
            raise ValueError("declared_clustering contiene livelli duplicati")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("statistical model evidence_ids duplicati")
        if not set(self.evidence_ids).issubset(self.provenance.evidence_ids):
            raise ValueError("evidence_ids del modello assenti dalla provenance")
        return self


class ProcessFact(NTruthModel):
    """Fatto di processo materializzato: pooling, esclusione, batch, ecc."""

    id: str
    kind: str
    detail: str = ""
    node_type: NodeType | None = None
    value: int | None = Field(default=None, ge=0)
    endpoint_hint: str | None = None
    group_hint: str | None = None
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance

    @model_validator(mode="after")
    def _traceable(self) -> Self:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("process evidence_ids duplicati")
        if not set(self.evidence_ids).issubset(self.provenance.evidence_ids):
            raise ValueError("evidence_ids del processo assenti dalla provenance")
        return self


def inference_target_scope_mismatches(
    scope: NScope,
    target: InferenceTarget,
    *,
    factors: Mapping[str, Factor],
    contrasts: Mapping[str, Contrast],
    endpoints: Mapping[str, Endpoint],
) -> tuple[str, ...]:
    """Dimensioni esplicite dello scope incompatibili con un target.

    Le dimensioni non dichiarate dal target non vengono inventate: in quel caso
    la completezza resta responsabilita dell'elicitation/compiler. Gruppo e
    timepoint sono verificati solo quando livelli o tempi ammissibili sono
    effettivamente dichiarati nel design.
    """

    mismatches: list[str] = []
    if (
        scope.factor_id is not None
        and target.factor_ids
        and scope.factor_id not in target.factor_ids
    ):
        mismatches.append("factor")
    if (
        scope.contrast_id is not None
        and target.contrast_ids
        and scope.contrast_id not in target.contrast_ids
    ):
        mismatches.append("contrast")
    if (
        scope.endpoint_id is not None
        and target.endpoint_ids
        and scope.endpoint_id not in target.endpoint_ids
    ):
        mismatches.append("endpoint")
    selected_contrast = contrasts.get(scope.contrast_id) if scope.contrast_id is not None else None
    if (
        selected_contrast is not None
        and scope.endpoint_id is not None
        and selected_contrast.endpoint_ids
        and scope.endpoint_id not in selected_contrast.endpoint_ids
        and "endpoint" not in mismatches
    ):
        mismatches.append("endpoint")

    group = _normalized_scope_value(scope.group)
    if group and group != "per_group":
        allowed_groups: set[str] = set()
        candidate_contrasts: list[Contrast] = []
        if scope.contrast_id is not None and scope.contrast_id in contrasts:
            candidate_contrasts.append(contrasts[scope.contrast_id])
        else:
            candidate_contrasts.extend(
                contrasts[contrast_id]
                for contrast_id in target.contrast_ids
                if contrast_id in contrasts
            )
        if scope.factor_id is not None:
            candidate_contrasts = [
                contrast
                for contrast in candidate_contrasts
                if scope.factor_id in contrast.factor_ids
            ]
        for contrast in candidate_contrasts:
            allowed_groups.update(
                normalized
                for value in (contrast.group_a, contrast.group_b)
                if (normalized := _normalized_scope_value(value))
            )

        if not allowed_groups:
            candidate_factor_ids = (
                (scope.factor_id,) if scope.factor_id is not None else target.factor_ids
            )
            for factor_id in candidate_factor_ids:
                factor = factors.get(factor_id)
                if factor is not None:
                    allowed_groups.update(
                        normalized
                        for value in factor.levels
                        if (normalized := _normalized_scope_value(value))
                    )
        groups_are_declared = bool(candidate_contrasts) and all(
            contrast.group_a is not None or contrast.group_b is not None
            for contrast in candidate_contrasts
        )
        if not candidate_contrasts:
            candidate_factor_ids = (
                (scope.factor_id,) if scope.factor_id is not None else target.factor_ids
            )
            candidate_factors = [
                factors[factor_id] for factor_id in candidate_factor_ids if factor_id in factors
            ]
            groups_are_declared = bool(candidate_factors) and all(
                factor.levels for factor in candidate_factors
            )
        if groups_are_declared and allowed_groups and group not in allowed_groups:
            mismatches.append("group")

    timepoint = _normalized_scope_value(scope.timepoint)
    if timepoint:
        candidate_endpoints: list[Endpoint] = []
        if scope.endpoint_id is not None and scope.endpoint_id in endpoints:
            candidate_endpoints.append(endpoints[scope.endpoint_id])
        else:
            candidate_endpoints.extend(
                endpoints[endpoint_id]
                for endpoint_id in target.endpoint_ids
                if endpoint_id in endpoints
            )
        allowed_timepoints = {
            normalized
            for endpoint in candidate_endpoints
            for value in endpoint.timepoints
            if (normalized := _normalized_scope_value(value))
        }
        timepoints_are_declared = bool(candidate_endpoints) and all(
            endpoint.timepoints for endpoint in candidate_endpoints
        )
        if timepoints_are_declared and allowed_timepoints and timepoint not in allowed_timepoints:
            mismatches.append("timepoint")

    return tuple(mismatches)


def _normalized_scope_value(value: str | None) -> str:
    return " ".join(value.casefold().split()) if value is not None else ""


class Hierarchy(NTruthModel):
    """Slice del grafo che descrive il blocco."""

    nodes: tuple[GraphNode, ...] = ()
    relations: tuple[GraphRelation, ...] = ()

    def node(self, node_id: str) -> GraphNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def levels(self) -> list[NodeType]:
        """Tipi presenti che sono livelli gerarchici, dal piu alto al piu basso."""
        seen = {n.type for n in self.nodes if rank_of(n.type) is not None}
        return sorted(seen, key=lambda t: rank_of(t) or 0)

    def nodes_of(self, node_type: NodeType) -> list[GraphNode]:
        return [n for n in self.nodes if n.type is node_type]

    def relations_of(self, rel_type: RelationType) -> list[GraphRelation]:
        return [r for r in self.relations if r.type is rel_type]


class Versions(NTruthModel):
    """Versioni riportate in ogni report (PRD FR-034)."""

    schema_version: str
    parser_version: str
    graph_version: str
    ruleset_id: str
    ruleset_version: str
    ontology_version: str | None = None
    model_version: str | None = None


class ExperimentBlock(NTruthModel):
    """Campi minimi del blocco (PRD 12.2)."""

    id: str
    title: str = ""
    document_id: str
    source_file_ids: tuple[str, ...] = ()
    inference_targets: tuple[InferenceTarget, ...] = ()
    factors: tuple[Factor, ...] = ()
    contrasts: tuple[Contrast, ...] = ()
    endpoints: tuple[Endpoint, ...] = ()
    estimands: tuple[Estimand, ...] = ()
    models: tuple[StatisticalModelFact, ...] = ()
    processes: tuple[ProcessFact, ...] = ()
    hierarchy: Hierarchy = Field(default_factory=Hierarchy)
    n_statements: tuple[NStatement, ...] = ()
    unit_assessments: tuple[UnitAssessment, ...] = ()
    alerts: tuple[Alert, ...] = ()
    questions: tuple[Question, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    data_sufficiency: DataSufficiency = Field(default_factory=DataSufficiency)
    evidence: tuple[EvidenceSpan, ...] = ()
    mentions: tuple[Mention, ...] = ()
    coreference_links: tuple[CoreferenceLink, ...] = ()
    determinability: Determinability = Determinability.INDETERMINATE
    versions: Versions
    corrections: tuple[Correction, ...] = ()

    @model_validator(mode="after")
    def _validate_local_references(self) -> Self:
        """Rifiuta riferimenti locali impossibili senza penalizzare report legacy."""

        target_ids = {target.id for target in self.inference_targets}
        if len(target_ids) != len(self.inference_targets):
            raise ValueError("inference_targets contiene ID duplicati")

        factor_ids = {factor.id for factor in self.factors}
        contrast_ids = {contrast.id for contrast in self.contrasts}
        endpoint_ids = {endpoint.id for endpoint in self.endpoints}
        estimand_ids = {estimand.id for estimand in self.estimands}
        evidence_ids = {evidence.id for evidence in self.evidence}

        if len(estimand_ids) != len(self.estimands):
            raise ValueError("estimands contiene ID duplicati")
        for estimand in self.estimands:
            unknown_factors = set(estimand.factor_ids) - factor_ids
            unknown_evidence = set(estimand.evidence_ids) - evidence_ids
            if estimand.endpoint_id not in endpoint_ids:
                raise ValueError(
                    f"estimand {estimand.id}: endpoint ref sconosciuto {estimand.endpoint_id}"
                )
            if unknown_factors:
                raise ValueError(
                    f"estimand {estimand.id}: factor refs sconosciuti {unknown_factors}"
                )
            if unknown_evidence:
                raise ValueError(
                    f"estimand {estimand.id}: evidence refs sconosciuti {unknown_evidence}"
                )

        for label, facts in (("models", self.models), ("processes", self.processes)):
            fact_ids = {fact.id for fact in facts}
            if len(fact_ids) != len(facts):
                raise ValueError(f"{label} contiene ID duplicati")
            for fact in facts:
                unknown_evidence = set(fact.evidence_ids) - evidence_ids
                if unknown_evidence:
                    raise ValueError(
                        f"{label} {fact.id}: evidence refs sconosciuti {unknown_evidence}"
                    )

        for target in self.inference_targets:
            unknown_factors = set(target.factor_ids) - factor_ids
            unknown_contrasts = set(target.contrast_ids) - contrast_ids
            unknown_endpoints = set(target.endpoint_ids) - endpoint_ids
            unknown_evidence = set(target.evidence_ids) - evidence_ids
            if unknown_factors:
                raise ValueError(f"target {target.id}: factor refs sconosciuti {unknown_factors}")
            if unknown_contrasts:
                raise ValueError(
                    f"target {target.id}: contrast refs sconosciuti {unknown_contrasts}"
                )
            if unknown_endpoints:
                raise ValueError(
                    f"target {target.id}: endpoint refs sconosciuti {unknown_endpoints}"
                )
            if unknown_evidence:
                raise ValueError(
                    f"target {target.id}: evidence refs sconosciuti {unknown_evidence}"
                )

            target_factor_ids = {
                factor_id
                for contrast in self.contrasts
                if contrast.id in target.contrast_ids
                for factor_id in contrast.factor_ids
            }
            if target.factor_ids and not target_factor_ids.issubset(target.factor_ids):
                raise ValueError(
                    f"target {target.id}: contrasto collegato a fattore non incluso nel target"
                )
            linked_endpoint_ids = {
                endpoint_id
                for contrast in self.contrasts
                if contrast.id in target.contrast_ids
                for endpoint_id in contrast.endpoint_ids
            }
            if linked_endpoint_ids and not set(target.endpoint_ids).issubset(linked_endpoint_ids):
                raise ValueError(
                    f"target {target.id}: endpoint non incluso nei contrasti collegati"
                )

        scoped_references = [
            *((item.id, item.scope) for item in self.n_statements),
            *((item.id, item.scope) for item in self.unit_assessments),
            *((item.id, item.scope) for item in self.alerts),
            *((item.id, item.scope) for item in self.questions),
        ]
        for item_id, scope in scoped_references:
            scoped_target_id = scope.inference_target_id if scope is not None else None
            if scoped_target_id is not None and scoped_target_id not in target_ids:
                raise ValueError(
                    f"scope di {item_id} riferisce inference target sconosciuto {scoped_target_id}"
                )
        return self

    def evidence_by_id(self, evidence_id: str) -> EvidenceSpan | None:
        return next((e for e in self.evidence if e.id == evidence_id), None)

    def factor(self, factor_id: str) -> Factor | None:
        return next((f for f in self.factors if f.id == factor_id), None)

    def endpoint(self, endpoint_id: str) -> Endpoint | None:
        return next((e for e in self.endpoints if e.id == endpoint_id), None)

    def max_severity(self) -> Severity | None:
        order = [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.INSUFFICIENT,
            Severity.INFO,
        ]
        present = [a.severity for a in self.alerts]
        for sev in order:
            if sev in present:
                return sev
        return None


def make_block_id(document_id: str, index: int, title: str) -> str:
    return stable_id("blk", document_id, index, title.strip().lower())
