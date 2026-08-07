"""ExperimentBlock e contratti dati (PRD 12).

L'unita primaria di annotazione e l'ExperimentBlock: un insieme coerente di
Methods, legend, statistica e metadata che descrive un esperimento o contrasto.
Un articolo contiene piu blocchi, spesso con gerarchie e n diversi; il paper
intero non riceve mai una singola label (PRD 12.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import (
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
    model_serializer,
    model_validator,
)

from ntruth.schemas.core import (
    AlertClass,
    Confidence,
    Determinability,
    EvidenceSpan,
    NTruthModel,
    Provenance,
    ProvenanceKind,
    Severity,
    content_checksum,
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
    """Tipo semantico/lifecycle di count previsto dal PRD v6."""

    PLANNED = "planned"
    DECLARED = "declared"
    OBSERVATIONAL = "observational"
    ANALYTICAL = "analytical"
    INDEPENDENT = "independent"
    BIOLOGICAL_SOURCE = "biological_source"
    EFFECTIVE = "effective"
    ALLOCATED = "allocated"
    TREATED = "treated"
    OBSERVED = "observed"
    EXCLUDED = "excluded"
    ANALYSED = "analysed"

    # Alias sorgente v3; il valore serializzato e il British English normativo.
    ANALYZED = "analysed"

    @classmethod
    def _missing_(cls, value: object) -> NKind | None:
        if value == "analyzed":
            return cls.ANALYSED
        return None


class TriState(StrEnum):
    """Valore esplicito: l'assenza di evidenza non diventa ``False``."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class LifecycleStatus(StrEnum):
    """Fase fisica/analitica a cui un count o un campione si riferisce."""

    PLANNED = "planned"
    ALLOCATED = "allocated"
    TREATED = "treated"
    OBSERVED = "observed"
    EXCLUDED = "excluded"
    ANALYSED = "analysed"

    @classmethod
    def _missing_(cls, value: object) -> LifecycleStatus | None:
        if value == "analyzed":
            return cls.ANALYSED
        return None


class CountQuantifier(StrEnum):
    """Semantica della quantita; silenzio e zero non sono intercambiabili."""

    EXACT = "EXACT"
    LOWER_BOUND = "LOWER_BOUND"
    UPPER_BOUND = "UPPER_BOUND"
    APPROXIMATE = "APPROXIMATE"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"
    NOT_REPORTED = "NOT_REPORTED"


class CountKind(StrEnum):
    """Registro canonico dei count: valori v6 congelati + vocabolario v8 (§7.9).

    I **valori** serializzati restano quelli v6 (PRD Appendice AE.1: gli output
    storici sono immutabili e gli stable_id v7-era non devono cambiare): il
    valore canonico di ogni membro e' la stringa legacy. I nomi §7.9
    (``*_unit_count``, SRR-0006) sono alias sullo stesso membro: il carico
    accetta entrambi i vocabolari, la serializzazione legacy non cambia.
    Il naming canonico v8 e' esposto solo via ``COUNT_KIND_V8_WIRE`` e il
    wire contract ``V8CountRecord`` (pattern ``INDETERMINATE``).
    """

    PLANNED_N = "planned_n"
    ALLOCATED_N = "allocated_n"
    TREATED_N = "treated_n"
    OBSERVED_N = "observed_n"
    EXCLUDED_N = "excluded_n"
    ANALYSED_N = "analysed_n"
    # Ortografia §7.9/P.1: stesso membro, valore serializzato congelato.
    ANALYZED_N = "analysed_n"
    DECLARED_N = "declared_n"
    OBSERVATIONAL_N = "observational_n"
    ANALYTICAL_N = "analytical_n"
    # ``independent_n`` e' alias di report deprecato (§7.9, P.1) ma resta il
    # valore congelato del count dell'unita sperimentale.
    INDEPENDENT_N = "independent_n"
    BIOLOGICAL_SOURCE_COUNT = "biological_source_count"
    EFFECTIVE_N = "effective_n"
    EFFECTIVE_N_DIAGNOSTIC = "effective_n"

    # Alias deprecati con denominazione §7.9: solo compatibilita di lettura;
    # la serializzazione canonica resta il valore v6 congelato (AE.1).
    PLANNED_UNIT_COUNT = "planned_n"
    ALLOCATED_UNIT_COUNT = "allocated_n"
    TREATED_UNIT_COUNT = "treated_n"
    OBSERVED_UNIT_COUNT = "observed_n"
    EXCLUDED_UNIT_COUNT = "excluded_n"
    ANALYZED_UNIT_COUNT = "analysed_n"
    OBSERVATIONAL_MEASUREMENT_COUNT = "observational_n"
    ANALYTICAL_ROW_COUNT = "analytical_n"
    EXPERIMENTAL_UNIT_COUNT = "independent_n"
    DIAGNOSTIC_EFFECTIVE_N = "effective_n"

    @classmethod
    def _missing_(cls, value: object) -> CountKind | None:
        """Accetta il vocabolario §7.9 senza cambiare il valore serializzato."""

        aliases = {
            "analyzed_n": cls.ANALYSED_N,
            "planned_unit_count": cls.PLANNED_N,
            "allocated_unit_count": cls.ALLOCATED_N,
            "treated_unit_count": cls.TREATED_N,
            "observed_unit_count": cls.OBSERVED_N,
            "excluded_unit_count": cls.EXCLUDED_N,
            "analyzed_unit_count": cls.ANALYSED_N,
            "observational_measurement_count": cls.OBSERVATIONAL_N,
            "analytical_row_count": cls.ANALYTICAL_N,
            "experimental_unit_count": cls.INDEPENDENT_N,
            "diagnostic_effective_n": cls.EFFECTIVE_N,
            "effective_n_diagnostic": cls.EFFECTIVE_N,
        }
        return aliases.get(value) if isinstance(value, str) else None


#: Naming canonico v8 (§7.9) per ogni membro, esposto soltanto dai contratti
#: v8 (``V8CountRecord``): la serializzazione v6/v7 non lo usa mai (AE.1).
COUNT_KIND_V8_WIRE: dict[CountKind, str] = {
    CountKind.PLANNED_N: "planned_unit_count",
    CountKind.ALLOCATED_N: "allocated_unit_count",
    CountKind.TREATED_N: "treated_unit_count",
    CountKind.OBSERVED_N: "observed_unit_count",
    CountKind.EXCLUDED_N: "excluded_unit_count",
    CountKind.ANALYSED_N: "analyzed_unit_count",
    CountKind.DECLARED_N: "declared_n",
    CountKind.OBSERVATIONAL_N: "observational_measurement_count",
    CountKind.ANALYTICAL_N: "analytical_row_count",
    CountKind.INDEPENDENT_N: "experimental_unit_count",
    CountKind.BIOLOGICAL_SOURCE_COUNT: "biological_source_count",
    CountKind.EFFECTIVE_N: "diagnostic_effective_n",
}


class ExclusionPhase(StrEnum):
    """Quando e avvenuta un'esclusione rispetto a trattamento e outcome."""

    PRE_ALLOCATION = "pre_allocation"
    POST_ALLOCATION = "post_allocation"
    POST_TREATMENT = "post_treatment"
    POST_MEASUREMENT = "post_measurement"
    POST_OUTCOME = "post_outcome"
    UNKNOWN = "unknown"


class GraphStatus(StrEnum):
    """Autorita del grafo su cui opera il compilatore deterministico."""

    CANDIDATE = "candidate"
    HUMAN_CONFIRMED = "human_confirmed"
    CONDITIONAL = "conditional"
    INVALID = "invalid"


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
    if_confirmed: dict[str, int | None]
    if_rejected: dict[str, int | None]
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
        if any(
            value < 0
            for value in (*self.if_confirmed.values(), *self.if_rejected.values())
            if value is not None
        ):
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
    unit_type: NodeType | None = None
    lifecycle: LifecycleStatus | None = None
    population: str | None = None
    condition: str | None = None
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
                self.unit_type,
                self.lifecycle,
                self.population,
                self.condition,
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
        extension_key = (
            str(self.unit_type) if self.unit_type is not None else None,
            str(self.lifecycle) if self.lifecycle is not None else None,
            self.population,
            self.condition,
        )
        if self.inference_target_id is None and not any(extension_key):
            # Preserva gli ID content-addressed prodotti dalle versioni precedenti.
            return legacy_key
        if not any(extension_key):
            # Anche l'estensione v3 con il solo inference target conserva la
            # propria chiave a sei elementi. I campi lifecycle v6 vengono
            # aggiunti soltanto quando sono realmente valorizzati.
            return (*legacy_key, self.inference_target_id)
        return (*legacy_key, self.inference_target_id, *extension_key)

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
            f"unita={self.unit_type}" if self.unit_type else None,
            f"lifecycle={self.lifecycle}" if self.lifecycle else None,
            f"popolazione={self.population}" if self.population else None,
            f"condizione={self.condition}" if self.condition else None,
        ]
        return ", ".join(p for p in parts if p)


class NStatement(NTruthModel):
    """``CountRecord`` scope-aware, con alias storico ``NStatement``.

    ``effective`` e un diagnostico separato: non puo essere promosso a count
    indipendente dal rules engine. I bounds non vengono trasformati in valori
    esatti e ``NOT_REPORTED`` resta distinto da zero.
    """

    id: str
    value: StrictInt | None = Field(default=None, ge=0)
    entity_type: str
    node_type: NodeType | None = None
    scope: NScope
    kind: NKind
    quantifier: CountQuantifier = CountQuantifier.EXACT
    lower_bound: StrictInt | None = Field(default=None, ge=0)
    upper_bound: StrictInt | None = Field(default=None, ge=0)
    qualifiers: tuple[str, ...] = ()
    raw_text: str = ""
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rule_trace_ids: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _infer_legacy_quantifier(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        if "quantifier" not in payload:
            payload["quantifier"] = (
                CountQuantifier.EXACT
                if payload.get("value") is not None
                else CountQuantifier.UNKNOWN
            )
        return payload

    @model_validator(mode="after")
    def _quantifier_is_coherent(self) -> Self:
        if self.quantifier in {CountQuantifier.EXACT, CountQuantifier.APPROXIMATE}:
            if self.value is None:
                raise ValueError(f"{self.quantifier} richiede value")
            if self.lower_bound is not None or self.upper_bound is not None:
                raise ValueError(f"{self.quantifier} non ammette bounds")
        elif self.quantifier in {CountQuantifier.LOWER_BOUND, CountQuantifier.UPPER_BOUND}:
            if self.value is None:
                raise ValueError(f"{self.quantifier} richiede il limite in value")
        elif self.quantifier is CountQuantifier.RANGE:
            if self.value is not None:
                raise ValueError("RANGE non ammette un singolo value")
            if self.lower_bound is None or self.upper_bound is None:
                raise ValueError("RANGE richiede lower_bound e upper_bound")
            if self.upper_bound < self.lower_bound:
                raise ValueError("RANGE con upper_bound < lower_bound")
        elif self.value is not None or self.lower_bound is not None or self.upper_bound is not None:
            raise ValueError(f"{self.quantifier} non ammette valori numerici")
        if len(self.rule_trace_ids) != len(set(self.rule_trace_ids)):
            raise ValueError("rule_trace_ids duplicati")
        return self


class CountScope(NTruthModel):
    """Scope esplicito del count; i ``null`` hanno sempre un reason code.

    La v8 aggiunge ``query_id`` e ``cohort_id`` (Appendice A/P.1): sono
    opzionali per compatibilita con i payload v6 e non rientrano nell'audit
    dei null dello scope fisico. Finche' restano null la serializzazione non
    li emette (Appendice AE.1: il wire v7-era e gli stable_id sono congelati).
    """

    unit_type: NodeType | None
    factor_id: str | None
    contrast_id: str | None
    group_or_level: str | None
    endpoint_id: str | None
    timepoint: str | None
    lifecycle: LifecycleStatus | None
    population: str | None
    condition: str | None
    query_id: str | None = None
    cohort_id: str | None = None
    unknown_reasons: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _nulls_are_explained(self) -> Self:
        decisive = {
            "unit_type": self.unit_type,
            "factor_id": self.factor_id,
            "contrast_id": self.contrast_id,
            "group_or_level": self.group_or_level,
            "endpoint_id": self.endpoint_id,
            "timepoint": self.timepoint,
            "lifecycle": self.lifecycle,
        }
        unexplained = [
            field_name
            for field_name, value in decisive.items()
            if value is None and not self.unknown_reasons.get(field_name, "").strip()
        ]
        if unexplained:
            raise ValueError(f"count scope null senza reason code: {sorted(unexplained)}")
        unknown_fields = set(self.unknown_reasons) - decisive.keys()
        if unknown_fields:
            raise ValueError(
                f"unknown_reasons contiene campi non ammessi: {sorted(unknown_fields)}"
            )
        return self

    @model_serializer(mode="wrap")
    def _freeze_v7_wire(self, handler: Any) -> Any:
        """AE.1: i campi v8 non impostati non entrano nella serializzazione."""
        data = handler(self)
        if isinstance(data, dict):
            if self.query_id is None:
                data.pop("query_id", None)
            if self.cohort_id is None:
                data.pop("cohort_id", None)
        return data

    @classmethod
    def from_legacy(cls, statement: NStatement) -> CountScope:
        lifecycle_by_kind = {
            NKind.PLANNED: LifecycleStatus.PLANNED,
            NKind.ALLOCATED: LifecycleStatus.ALLOCATED,
            NKind.TREATED: LifecycleStatus.TREATED,
            NKind.OBSERVED: LifecycleStatus.OBSERVED,
            NKind.EXCLUDED: LifecycleStatus.EXCLUDED,
            NKind.ANALYSED: LifecycleStatus.ANALYSED,
        }
        lifecycle = statement.scope.lifecycle or lifecycle_by_kind.get(statement.kind)
        values = {
            "unit_type": statement.scope.unit_type or statement.node_type,
            "factor_id": statement.scope.factor_id,
            "contrast_id": statement.scope.contrast_id,
            "group_or_level": statement.scope.group,
            "endpoint_id": statement.scope.endpoint_id,
            "timepoint": statement.scope.timepoint,
            "lifecycle": lifecycle,
        }
        reasons = {
            field_name: "not reported in legacy source"
            for field_name, value in values.items()
            if value is None
        }
        return cls(
            unit_type=statement.scope.unit_type or statement.node_type,
            factor_id=statement.scope.factor_id,
            contrast_id=statement.scope.contrast_id,
            group_or_level=statement.scope.group,
            endpoint_id=statement.scope.endpoint_id,
            timepoint=statement.scope.timepoint,
            lifecycle=lifecycle,
            population=statement.scope.population,
            condition=statement.scope.condition,
            unknown_reasons=reasons,
        )


class CountRecord(NTruthModel):
    """Wire contract canonico per ogni significato di ``n`` (PRD v6 e v8).

    La v8 lega ogni count a ``query_id``/``cohort_id`` (Appendice A/P.1); i
    campi restano opzionali per non alterare i payload v6 e la risoluzione
    esistente (la proiezione derivazionale arriva in FASE 3). Finche' restano
    null la serializzazione non li emette (Appendice AE.1).
    """

    count_id: str
    kind: CountKind
    value: StrictInt | StrictFloat | None = Field(default=None, ge=0)
    quantifier: CountQuantifier
    lower_bound: StrictInt | StrictFloat | None = Field(default=None, ge=0)
    upper_bound: StrictInt | StrictFloat | None = Field(default=None, ge=0)
    scope: CountScope
    query_id: str | None = None
    cohort_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    rule_trace_ids: tuple[str, ...] = ()
    diagnostic_only: bool = False
    provenance: Provenance

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.quantifier in {CountQuantifier.EXACT, CountQuantifier.APPROXIMATE}:
            if self.value is None or self.lower_bound is not None or self.upper_bound is not None:
                raise ValueError(f"{self.quantifier} richiede solo value")
        elif self.quantifier in {CountQuantifier.LOWER_BOUND, CountQuantifier.UPPER_BOUND}:
            if self.value is None or self.lower_bound is not None or self.upper_bound is not None:
                raise ValueError(f"{self.quantifier} usa soltanto value come limite")
        elif self.quantifier is CountQuantifier.RANGE:
            if self.value is not None or self.lower_bound is None or self.upper_bound is None:
                raise ValueError("RANGE richiede soltanto lower_bound e upper_bound")
            if self.upper_bound < self.lower_bound:
                raise ValueError("RANGE con upper_bound < lower_bound")
        elif self.value is not None or self.lower_bound is not None or self.upper_bound is not None:
            raise ValueError(f"{self.quantifier} non ammette valori numerici")
        if self.kind is CountKind.EFFECTIVE_N and not self.diagnostic_only:
            raise ValueError("effective_n deve essere diagnostic_only=true")
        if self.kind is not CountKind.EFFECTIVE_N and self.diagnostic_only:
            raise ValueError("diagnostic_only e riservato a effective_n")
        numeric_values = tuple(
            value for value in (self.value, self.lower_bound, self.upper_bound) if value is not None
        )
        if self.kind is not CountKind.EFFECTIVE_N and any(
            isinstance(value, bool) or not float(value).is_integer() for value in numeric_values
        ):
            raise ValueError("i count fisici non possono contenere valori frazionari")
        for field_name, values in (
            ("evidence_ids", self.evidence_ids),
            ("rule_trace_ids", self.rule_trace_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} duplicati")
        if self.provenance.origin not in {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION}:
            if not (
                self.evidence_ids
                or self.rule_trace_ids
                or (self.provenance.derivation and self.provenance.derivation.strip())
            ):
                raise ValueError("count estratto/derivato senza evidence_ids o rule_trace_ids")
            if not set(self.evidence_ids).issubset(self.provenance.evidence_ids):
                raise ValueError("count evidence_ids assenti dalla provenance")
        return self

    @model_serializer(mode="wrap")
    def _freeze_v7_wire(self, handler: Any) -> Any:
        """AE.1: i campi v8 non impostati non entrano nella serializzazione."""
        data = handler(self)
        if isinstance(data, dict):
            if self.query_id is None:
                data.pop("query_id", None)
            if self.cohort_id is None:
                data.pop("cohort_id", None)
        return data

    def scope_key(self) -> tuple[object | None, ...]:
        """Chiave canonica dello scope v8 (Appendice P.1, §7.9).

        unit type, factor, contrast, group, endpoint, timepoint,
        lifecycle cohort e quantifier identificano un count senza ambiguita'.
        """

        return (
            self.scope.unit_type,
            self.scope.factor_id,
            self.scope.contrast_id,
            self.scope.group_or_level,
            self.scope.endpoint_id,
            self.scope.timepoint,
            self.scope.cohort_id or self.cohort_id,
            self.quantifier,
        )

    @classmethod
    def from_legacy(cls, statement: NStatement) -> CountRecord:
        kind_map = {
            NKind.PLANNED: CountKind.PLANNED_N,
            NKind.ALLOCATED: CountKind.ALLOCATED_N,
            NKind.TREATED: CountKind.TREATED_N,
            NKind.OBSERVED: CountKind.OBSERVED_N,
            NKind.EXCLUDED: CountKind.EXCLUDED_N,
            NKind.ANALYSED: CountKind.ANALYSED_N,
            NKind.DECLARED: CountKind.DECLARED_N,
            NKind.OBSERVATIONAL: CountKind.OBSERVATIONAL_N,
            NKind.ANALYTICAL: CountKind.ANALYTICAL_N,
            NKind.INDEPENDENT: CountKind.INDEPENDENT_N,
            NKind.BIOLOGICAL_SOURCE: CountKind.BIOLOGICAL_SOURCE_COUNT,
            NKind.EFFECTIVE: CountKind.EFFECTIVE_N,
        }
        return cls(
            count_id=statement.id,
            kind=kind_map[statement.kind],
            value=statement.value,
            quantifier=statement.quantifier,
            lower_bound=statement.lower_bound,
            upper_bound=statement.upper_bound,
            scope=CountScope.from_legacy(statement),
            evidence_ids=statement.evidence_ids,
            rule_trace_ids=statement.rule_trace_ids,
            diagnostic_only=statement.kind is NKind.EFFECTIVE,
            provenance=statement.provenance,
        )

    def to_legacy(self) -> NStatement | None:
        """Proietta un count fisico v6 sul resolver legacy, senza effective_n.

        ``CountRecord`` resta il contratto autorevole. L'adapter esiste soltanto
        finche il resolver deterministico legge ``NStatement``; il diagnostico
        effective_n non vi entra, cosi non puo influenzare regole o derivazione
        dell'unita sperimentale.
        """

        if self.kind is CountKind.EFFECTIVE_N:
            return None
        kind_map = {
            CountKind.PLANNED_N: NKind.PLANNED,
            CountKind.ALLOCATED_N: NKind.ALLOCATED,
            CountKind.TREATED_N: NKind.TREATED,
            CountKind.OBSERVED_N: NKind.OBSERVED,
            CountKind.EXCLUDED_N: NKind.EXCLUDED,
            CountKind.ANALYSED_N: NKind.ANALYSED,
            CountKind.DECLARED_N: NKind.DECLARED,
            CountKind.OBSERVATIONAL_N: NKind.OBSERVATIONAL,
            CountKind.ANALYTICAL_N: NKind.ANALYTICAL,
            CountKind.INDEPENDENT_N: NKind.INDEPENDENT,
            CountKind.BIOLOGICAL_SOURCE_COUNT: NKind.BIOLOGICAL_SOURCE,
        }

        def physical_int(value: int | float | None) -> int | None:
            if value is None:
                return None
            return int(value)

        legacy_scope_values = (
            self.scope.factor_id,
            self.scope.contrast_id,
            self.scope.endpoint_id,
            self.scope.group_or_level,
            self.scope.timepoint,
            self.scope.unit_type,
            self.scope.lifecycle,
            self.scope.population,
            self.scope.condition,
        )
        if not any(value is not None for value in legacy_scope_values):
            # CountScope sa rappresentare un'origine ignota con reason code;
            # NScope legacy no. Non trasformiamo l'assenza in scope globale.
            return None

        return NStatement(
            id=self.count_id,
            value=physical_int(self.value),
            entity_type=(
                self.scope.unit_type.value
                if self.scope.unit_type is not None
                else "unspecified_count_unit"
            ),
            node_type=self.scope.unit_type,
            scope=NScope(
                factor_id=self.scope.factor_id,
                contrast_id=self.scope.contrast_id,
                endpoint_id=self.scope.endpoint_id,
                group=self.scope.group_or_level,
                timepoint=self.scope.timepoint,
                unit_type=self.scope.unit_type,
                lifecycle=self.scope.lifecycle,
                population=self.scope.population,
                condition=self.scope.condition,
            ),
            kind=kind_map[self.kind],
            quantifier=self.quantifier,
            lower_bound=physical_int(self.lower_bound),
            upper_bound=physical_int(self.upper_bound),
            evidence_ids=self.evidence_ids,
            provenance=self.provenance,
            rule_trace_ids=self.rule_trace_ids,
        )


class ExclusionRecord(NTruthModel):
    """Attrition endpoint-specific e auditabile lungo il lifecycle."""

    id: str
    unit_id: str | None = None
    unit_type: NodeType
    phase: ExclusionPhase = ExclusionPhase.UNKNOWN
    prespecified: TriState = TriState.UNKNOWN
    endpoint_id: str | None = None
    factor_id: str | None = None
    contrast_id: str | None = None
    group: str | None = None
    author_role: str | None = None
    reason: str | None = None
    evidence_ids: tuple[str, ...] = ()
    impact: str | None = None
    unknown_reasons: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def _traceable_and_unique(self) -> Self:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("exclusion evidence_ids duplicati")
        if self.provenance.origin not in {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION}:
            if not self.evidence_ids:
                raise ValueError("exclusion estratta/derivata senza evidence_ids")
            if not set(self.evidence_ids).issubset(self.provenance.evidence_ids):
                raise ValueError("exclusion evidence_ids assenti dalla provenance")
        auditable_fields: dict[str, object | None] = {
            "phase": None if self.phase is ExclusionPhase.UNKNOWN else self.phase,
            "prespecified": None if self.prespecified is TriState.UNKNOWN else self.prespecified,
            "endpoint_id": self.endpoint_id,
            "group": self.group,
            "author_role": self.author_role,
            "reason": self.reason,
            "evidence_ids": self.evidence_ids or None,
            "impact": self.impact,
        }
        missing = [
            field_name
            for field_name, value in auditable_fields.items()
            if (value is None or (isinstance(value, str) and not value.strip()))
            and not self.unknown_reasons.get(field_name, "").strip()
        ]
        if missing:
            raise ValueError(f"exclusion fields mancanti senza reason code: {sorted(missing)}")
        unknown_fields = set(self.unknown_reasons) - auditable_fields.keys()
        if unknown_fields:
            raise ValueError(
                f"exclusion unknown_reasons contiene campi non ammessi: {sorted(unknown_fields)}"
            )
        return self


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


#: Campi count v6 proiettati nella semantica open-world v8 (Appendice AC).
#: Costante di modulo: un attributo underscore nel corpo del modello pydantic
#: diventerebbe un ModelPrivateAttr e non sarebbe piu' ispezionabile dai test.
_UNIT_ASSESSMENT_V8_FIELDS = (
    "n_planned",
    "n_declared",
    "n_allocated",
    "n_treated",
    "n_observed",
    "n_excluded",
    "n_analysed",
    "n_observational",
    "n_analytical",
    "n_independent",
    "biological_source_count",
    "effective_n",
)


class UnitAssessment(NTruthModel):
    """Unita e n per uno scope specifico (PRD 12.2)."""

    id: str
    scope: NScope
    biological_unit: NodeType | None = None
    allocation_unit_candidate: NodeType | None = None
    experimental_unit: NodeType | None = None
    observational_unit: NodeType | None = None
    analytical_unit: NodeType | None = None
    n_planned: int | None = Field(default=None, ge=0)
    n_declared: int | None = Field(default=None, ge=0)
    n_allocated: int | None = Field(default=None, ge=0)
    n_treated: int | None = Field(default=None, ge=0)
    n_observed: int | None = Field(default=None, ge=0)
    n_excluded: int | None = Field(default=None, ge=0)
    n_analysed: int | None = Field(default=None, ge=0)
    # Alias di migrazione v3; nuovi consumer devono leggere ``n_analysed``.
    n_analyzed: int | None = Field(default=None, ge=0)
    n_observational: int | None = Field(default=None, ge=0)
    n_analytical: int | None = Field(default=None, ge=0)
    n_independent: int | None = Field(default=None, ge=0)
    biological_source_count: int | None = Field(default=None, ge=0)
    effective_n: float | None = Field(default=None, ge=0.0)
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
            if "n_analysed" in payload:
                payload["n_analyzed"] = payload["n_analysed"]
            elif "n_analyzed" in payload:
                payload["n_analysed"] = payload["n_analyzed"]
            return payload
        return data

    @model_validator(mode="after")
    def _no_silent_substitution(self) -> Self:
        """Uno scenario numerico non puo convivere con un n scalare autorevole."""
        if self.n_analysed != self.n_analyzed:
            raise ValueError("n_analyzed legacy incoerente con n_analysed")
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

    def knowledge_values(self) -> dict[str, Any]:
        """Proiezione v8 dei count scalari in wrapper ``KnowledgeValue``.

        Scelta di migrazione (Appendice AC/AE): i campi legacy restano
        invariati per non rompere storage e payload golden; la semantica
        open-world vive in questa proiezione di confine, dove ogni bare null
        diventa uno stato esplicito con audit (regole field-specific in
        ``ntruth.schemas.kernel.LEGACY_NULL_RULES``). ``n_analyzed`` non e'
        proiettato: e' l'alias serializzato di ``n_analysed``.
        """

        from ntruth.schemas.kernel import KnowledgeValue  # lazy: evita il ciclo

        return {
            field_name: KnowledgeValue.migrate_legacy(
                getattr(self, field_name), legacy_field=field_name
            )
            for field_name in _UNIT_ASSESSMENT_V8_FIELDS
        }


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
    retained_interpretations: tuple[str, ...] = ()
    provenance: Provenance | None = None
    status: Literal["unresolved", "resolved_by_user", "resolved_by_adjudication"] = "unresolved"

    @model_validator(mode="after")
    def _unresolved_conflict_is_traceable(self) -> Self:
        if self.status != "unresolved":
            return self
        interpretations = tuple(
            dict.fromkeys(item.strip() for item in self.retained_interpretations if item.strip())
        )
        if len(interpretations) < 2:
            raise ValueError("contraddizione irrisolta senza almeno due interpretazioni trattenute")
        if interpretations != self.retained_interpretations:
            raise ValueError("retained_interpretations vuote o duplicate")
        human_record = self.provenance is not None and self.provenance.origin in {
            ProvenanceKind.USER,
            ProvenanceKind.ADJUDICATION,
        }
        if not (self.statement_ids or self.evidence_ids or human_record):
            raise ValueError("contraddizione irrisolta senza statement/evidence o provenance umana")
        return self


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
    # Per privacy si conserva il ruolo operativo, non l'identita personale.
    reviewer_role: str = Field(default="reviewer", min_length=2, max_length=64)
    # Il ledger assegna l'istante server-side se il client non lo fornisce.
    recorded_at: datetime | None = None
    verified: bool = False  # correzioni non verificate non entrano nel training pool

    @field_validator("reviewer_role")
    @classmethod
    def _reviewer_role_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("reviewer_role deve identificare un ruolo non vuoto")
        return normalized

    @field_validator("recorded_at")
    @classmethod
    def _recorded_at_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("recorded_at deve includere il fuso orario")
        return value


#: Campi timing/source del Factor proiettati nella semantica open-world v8 (AC).
_FACTOR_V8_FIELDS = (
    "allocation_timing",
    "source_biological_preparation",
)


class Factor(NTruthModel):
    """Fattore con allocazione e applicazione mantenute separate.

    ``assignment_*`` resta un alias serializzato per i consumer v0.1 e viene
    sincronizzato con ``allocation_*``. Non viene mai sincronizzato con
    ``application_*``, che puo legittimamente descrivere un livello diverso.
    """

    id: str
    name: str
    levels: tuple[str, ...] = ()
    kind: Literal["treatment", "genotype", "dose", "time", "diet", "other", "unknown"] = "other"
    allocation_level: NodeType | None = None
    application_level: NodeType | None = None
    allocation_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    application_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    allocation_evidence_ids: tuple[str, ...] = ()
    application_evidence_ids: tuple[str, ...] = ()
    independence_evidence_ids: tuple[str, ...] = ()
    independently_assigned: TriState = TriState.UNKNOWN
    randomization_unit: NodeType | None = None
    independence_mechanism: str | None = None
    shared_environment: tuple[str, ...] = ()
    confounded_with: tuple[str, ...] = ()
    source_biological_preparation: str | None = None
    allocation_event_id: str | None = None
    allocation_timing: str | None = None
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
            ("randomization_unit", self.randomization_unit),
        ):
            if level is not None and level not in ALLOCATABLE_NODE_TYPES:
                raise ValueError(f"{field_name} non e un NodeType allocabile: {level}")
        for field_name, values in (
            ("levels", self.levels),
            ("evidence_ids", self.evidence_ids),
            ("allocation_evidence_ids", self.allocation_evidence_ids),
            ("application_evidence_ids", self.application_evidence_ids),
            ("independence_evidence_ids", self.independence_evidence_ids),
            ("shared_environment", self.shared_environment),
            ("confounded_with", self.confounded_with),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contiene riferimenti duplicati")
        if self.independently_assigned is TriState.TRUE and not (
            self.independence_mechanism and self.independence_mechanism.strip()
        ):
            raise ValueError(
                "independently_assigned=TRUE richiede independence_mechanism esplicito"
            )
        for field_name, value in (
            ("independence_mechanism", self.independence_mechanism),
            ("source_biological_preparation", self.source_biological_preparation),
            ("allocation_event_id", self.allocation_event_id),
            ("allocation_timing", self.allocation_timing),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{field_name} non puo essere vuoto")
        return self

    def knowledge_values(self) -> dict[str, Any]:
        """Proiezione v8 dei campi timing/source in ``KnowledgeValue``.

        Scelta di migrazione (Appendice AC/AE): i campi legacy restano
        invariati per non rompere storage e payload golden; il silenzio
        diventa stato esplicito solo nella proiezione di confine, con regole
        field-specific e audit (``ntruth.schemas.kernel.LEGACY_NULL_RULES``):
        timing esecutivo -> NOT_REPORTED, provenienza biologica -> UNKNOWN.
        """

        from ntruth.schemas.kernel import KnowledgeValue  # lazy: evita il ciclo

        return {
            field_name: KnowledgeValue.migrate_legacy(
                getattr(self, field_name), legacy_field=field_name
            )
            for field_name in _FACTOR_V8_FIELDS
        }


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


class GraphAlternativeConsequence(NTruthModel):
    """Conseguenza scope-aware di un singolo grafo plausibile.

    Il testo esplicita l'effetto scientifico dell'alternativa; i campi
    strutturati rendono pubblicabili EU e ``n`` soltanto *dentro* quel ramo,
    mai come risposta unica del blocco.
    """

    id: str
    scope: NScope
    description: str
    experimental_unit: NodeType | None = None
    n_independent: StrictInt | None = Field(default=None, ge=0)
    n_independent_by_group: dict[str, StrictInt] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _is_materialized_and_traceable(self) -> Self:
        if not self.id.strip():
            raise ValueError("conseguenza di grafo alternativo senza id")
        if not self.description.strip():
            raise ValueError("conseguenza di grafo alternativo senza descrizione")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("conseguenza di grafo alternativo con evidence_ids duplicati")
        if not set(self.evidence_ids).issubset(self.provenance.evidence_ids):
            raise ValueError("evidence_ids della conseguenza assenti dalla provenance")
        if self.provenance.origin is ProvenanceKind.MODEL:
            raise ValueError("una conseguenza core non puo avere autorita model")
        if any(not group.strip() for group in self.n_independent_by_group):
            raise ValueError("n_independent_by_group contiene un gruppo vuoto")
        if any(value < 0 for value in self.n_independent_by_group.values()):
            raise ValueError("n_independent_by_group contiene un valore negativo")
        if (
            self.n_independent is not None or self.n_independent_by_group
        ) and self.experimental_unit is None:
            raise ValueError("un n alternativo richiede experimental_unit nel medesimo ramo")
        return self

    def scientific_signature(self) -> str:
        """Firma strutturata, priva di ID, narrativa e lineage non scientifica."""

        return content_checksum(
            {
                "scope": self.scope.model_dump(mode="json"),
                "experimental_unit": (
                    self.experimental_unit.value if self.experimental_unit is not None else None
                ),
                "n_independent": self.n_independent,
                "n_independent_by_group": self.n_independent_by_group,
            }
        )


class PlausibleGraphAlternative(NTruthModel):
    """Un grafo completo mantenuto come alternativa, senza ranking o scelta."""

    id: str
    label: str
    hierarchy: Hierarchy
    consequences: tuple[GraphAlternativeConsequence, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _is_distinct_and_traceable(self) -> Self:
        if not self.id.strip():
            raise ValueError("grafo alternativo senza id")
        if not self.label.strip():
            raise ValueError("grafo alternativo senza label")
        if not self.hierarchy.nodes:
            raise ValueError("grafo alternativo senza nodi")
        consequence_ids = [item.id for item in self.consequences]
        if len(consequence_ids) != len(set(consequence_ids)):
            raise ValueError("grafo alternativo con consequence id duplicati")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("grafo alternativo con evidence_ids duplicati")
        if not set(self.evidence_ids).issubset(self.provenance.evidence_ids):
            raise ValueError("evidence_ids del grafo alternativo assenti dalla provenance")
        if self.provenance.origin is ProvenanceKind.MODEL:
            raise ValueError("un grafo alternativo core non puo avere autorita model")
        return self

    def scientific_signature(self) -> str:
        """Firma topologica e delle conseguenze, esclusi ID, confidence e lineage."""

        node_payload_by_id = {
            node.id: {
                "type": node.type.value,
                "label": " ".join(node.label.casefold().split()),
                "count": node.count,
                "attributes": node.attributes,
            }
            for node in self.hierarchy.nodes
        }
        node_signatures = {
            node_id: content_checksum(payload) for node_id, payload in node_payload_by_id.items()
        }
        relation_payloads = [
            {
                "type": relation.type.value,
                "source": node_signatures.get(relation.source, f"missing:{relation.source}"),
                "target": node_signatures.get(relation.target, f"missing:{relation.target}"),
                "attributes": relation.attributes,
            }
            for relation in self.hierarchy.relations
        ]
        return content_checksum(
            {
                "nodes": sorted(
                    node_payload_by_id.values(),
                    key=content_checksum,
                ),
                "relations": sorted(relation_payloads, key=content_checksum),
                "consequences": sorted(item.scientific_signature() for item in self.consequences),
            }
        )


class PlausibleGraphSet(NTruthModel):
    """Almeno due grafi scientificamente distinti compatibili con l'evidenza.

    La domanda e un riferimento a ``ExperimentBlock.questions``: in questo modo
    resta un solo oggetto correggibile e auditabile, marcato ``decisive``.
    """

    id: str
    alternatives: tuple[PlausibleGraphAlternative, ...] = Field(min_length=2)
    discriminating_question_id: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _contains_real_alternatives(self) -> Self:
        if not self.id.strip():
            raise ValueError("plausible graph set senza id")
        if not self.discriminating_question_id.strip():
            raise ValueError("plausible graph set senza domanda discriminante")
        alternative_ids = [item.id for item in self.alternatives]
        if len(alternative_ids) != len(set(alternative_ids)):
            raise ValueError("plausible graph set con alternative id duplicate")
        signatures = [item.scientific_signature() for item in self.alternatives]
        if len(signatures) != len(set(signatures)):
            raise ValueError("plausible graph set con alternative scientificamente duplicate")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("plausible graph set con evidence_ids duplicati")
        if not set(self.evidence_ids).issubset(self.provenance.evidence_ids):
            raise ValueError("evidence_ids del plausible graph set assenti dalla provenance")
        if self.provenance.origin is ProvenanceKind.MODEL:
            raise ValueError("un plausible graph set core non puo avere autorita model")
        return self


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
    graph_status: GraphStatus = GraphStatus.CANDIDATE
    hierarchy: Hierarchy = Field(default_factory=Hierarchy)
    plausible_graph_set: PlausibleGraphSet | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    n_statements: tuple[NStatement, ...] = ()
    count_records: tuple[CountRecord, ...] = ()
    exclusion_records: tuple[ExclusionRecord, ...] = ()
    unit_assessments: tuple[UnitAssessment, ...] = ()
    alerts: tuple[Alert, ...] = ()
    questions: tuple[Question, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    data_sufficiency: DataSufficiency = Field(default_factory=DataSufficiency)
    evidence: tuple[EvidenceSpan, ...] = ()
    mentions: tuple[Mention, ...] = ()
    coreference_links: tuple[CoreferenceLink, ...] = ()
    determinability: Determinability = Determinability.INSUFFICIENT_INFORMATION
    versions: Versions
    corrections: tuple[Correction, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_counts(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        # Un payload realmente legacy non contiene il campo canonico. Quando
        # entrambi sono espliciti, CountRecord e autorevole: puo essere corretto
        # e il ricalcolo rigenera l'adapter NStatement senza sovrascriverlo nel
        # model validator.
        if payload.get("n_statements") and "count_records" not in payload:
            legacy = tuple(
                item if isinstance(item, NStatement) else NStatement.model_validate(item)
                for item in payload["n_statements"]
            )
            payload["count_records"] = tuple(CountRecord.from_legacy(item) for item in legacy)
        return payload

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
        question_ids = {question.id for question in self.questions}

        if self.plausible_graph_set is not None:
            graph_set = self.plausible_graph_set
            if self.graph_status is not GraphStatus.CONDITIONAL:
                raise ValueError("plausible_graph_set richiede graph_status=conditional")
            if graph_set.discriminating_question_id not in question_ids:
                raise ValueError(
                    "plausible_graph_set riferisce una domanda discriminante sconosciuta"
                )
            discriminating_question = next(
                question
                for question in self.questions
                if question.id == graph_set.discriminating_question_id
            )
            if not discriminating_question.decisive:
                raise ValueError("la domanda discriminante deve avere decisive=true")

            traceable_objects = [
                ("plausible graph set", graph_set.id, graph_set.evidence_ids, graph_set.provenance),
                *(
                    (
                        "grafo alternativo",
                        alternative.id,
                        alternative.evidence_ids,
                        alternative.provenance,
                    )
                    for alternative in graph_set.alternatives
                ),
                *(
                    (
                        "conseguenza di grafo alternativo",
                        consequence.id,
                        consequence.evidence_ids,
                        consequence.provenance,
                    )
                    for alternative in graph_set.alternatives
                    for consequence in alternative.consequences
                ),
                *(
                    ("nodo di grafo alternativo", node.id, node.evidence_ids, node.provenance)
                    for alternative in graph_set.alternatives
                    for node in alternative.hierarchy.nodes
                ),
                *(
                    (
                        "relazione di grafo alternativo",
                        relation.id,
                        relation.evidence_ids,
                        relation.provenance,
                    )
                    for alternative in graph_set.alternatives
                    for relation in alternative.hierarchy.relations
                ),
            ]
            for kind, owner_id, direct_evidence, provenance in traceable_objects:
                unknown_evidence = (
                    set(direct_evidence) | set(provenance.evidence_ids)
                ) - evidence_ids
                if unknown_evidence:
                    raise ValueError(
                        f"{kind} {owner_id}: evidence refs sconosciuti {unknown_evidence}"
                    )

        count_ids = {record.count_id for record in self.count_records}
        if len(count_ids) != len(self.count_records):
            raise ValueError("count_records contiene count_id duplicati")
        for count in self.count_records:
            unknown_evidence = set(count.evidence_ids) - evidence_ids
            if unknown_evidence:
                raise ValueError(
                    f"count {count.count_id}: evidence refs sconosciuti {unknown_evidence}"
                )
            if count.scope.factor_id is not None and count.scope.factor_id not in factor_ids:
                raise ValueError(
                    f"count {count.count_id}: factor ref sconosciuto {count.scope.factor_id}"
                )
            if count.scope.contrast_id is not None and count.scope.contrast_id not in contrast_ids:
                raise ValueError(
                    f"count {count.count_id}: contrast ref sconosciuto {count.scope.contrast_id}"
                )
            if count.scope.endpoint_id is not None and count.scope.endpoint_id not in endpoint_ids:
                raise ValueError(
                    f"count {count.count_id}: endpoint ref sconosciuto {count.scope.endpoint_id}"
                )

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

        exclusion_ids = {record.id for record in self.exclusion_records}
        if len(exclusion_ids) != len(self.exclusion_records):
            raise ValueError("exclusion_records contiene ID duplicati")
        for exclusion in self.exclusion_records:
            unknown_evidence = set(exclusion.evidence_ids) - evidence_ids
            if unknown_evidence:
                raise ValueError(
                    f"exclusion {exclusion.id}: evidence refs sconosciuti {unknown_evidence}"
                )
            if exclusion.factor_id is not None and exclusion.factor_id not in factor_ids:
                raise ValueError(
                    f"exclusion {exclusion.id}: factor ref sconosciuto {exclusion.factor_id}"
                )
            if exclusion.contrast_id is not None and exclusion.contrast_id not in contrast_ids:
                raise ValueError(
                    f"exclusion {exclusion.id}: contrast ref sconosciuto {exclusion.contrast_id}"
                )
            if exclusion.endpoint_id is not None and exclusion.endpoint_id not in endpoint_ids:
                raise ValueError(
                    f"exclusion {exclusion.id}: endpoint ref sconosciuto {exclusion.endpoint_id}"
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
            *(
                (item.id, item.scope)
                for alternative in (
                    self.plausible_graph_set.alternatives
                    if self.plausible_graph_set is not None
                    else ()
                )
                for item in alternative.consequences
            ),
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
