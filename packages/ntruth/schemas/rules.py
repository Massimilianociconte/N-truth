"""Regole versionate (PRD 8.1).

Una regola e una risorsa con ID stabile, dominio, precondizioni grafiche,
evidenze necessarie, inferenza, severita, eccezioni, condizioni di astensione,
messaggio, domande, riferimenti e fixture. Le regole non vivono dentro un prompt
e non richiedono retraining per essere modificate (PRD FR-018).
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field, model_validator

from ntruth.schemas.core import AlertClass, NTruthModel, Severity, content_checksum

#: Zucchero sintattico delle precondizioni in stile triple, come nel PRD 8.1:
#: "Cell nested_in Field" -> nested(Cell, Field)
_TRIPLE_RE = re.compile(
    r"^(?P<subject>[A-Za-z_]+)\s+(?P<pred>[a-z_]+)\s+(?P<object>[A-Za-z_]+)"
    r"(?P<modifier>\s+or\s+(higher|lower))?$"
)

_TRIPLE_PREDICATES = {
    "nested_in": "nested",
    "derived_from": "derived",
    "measured_on": "measured_on",
    "analyzed_as": "analyzed_as",
    "assigned_at": "assigned_at",
    "pooled_into": "pooled",
    "member_of_pool": "pooled",
}


class RuleOutcome(StrEnum):
    """Esito della valutazione di una regola su uno scope."""

    FIRED = "fired"
    ABSTAINED = "abstained"
    EXCEPTED = "excepted"
    NOT_APPLICABLE = "not_applicable"
    UNEVALUABLE = "unevaluable"  # predicato sconosciuto: mai silenzioso


class RuleFixtureKind(StrEnum):
    """Quattro classi obbligatorie di fixture previste da NFR-12."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    AMBIGUOUS = "ambiguous"
    EXCEPTION = "exception"


class TheoryLinkageStatus(StrEnum):
    """Stato del collegamento regola<->clausola di teoria (PRD v8 §10.11, §13.6).

    Una regola senza clausola difendibile non viene inventata ne eliminata:
    resta nel ruleset, disabilitata e marcata, in attesa di revisione
    scientifica registrata (registro SRR).
    """

    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"


class RuleFixture(NTruthModel):
    """Fixture dichiarata e collegata a uno scenario riproducibile.

    Le fixture di contratto verificano il motore e i predicati; non sono casi gold e non
    sostituiscono la revisione scientifica delle regole.
    """

    id: str
    kind: RuleFixtureKind
    description: str = ""
    path: str
    scenario: str
    expected_outcome: RuleOutcome


class Rule(NTruthModel):
    """Regola deterministica applicata al grafo validato."""

    rule_id: str
    version: str
    domain: str
    title: str = ""
    preconditions: tuple[str, ...] = ()
    requires_evidence: bool = True
    required_evidence: tuple[str, ...] = ()
    inference: str
    message_it: str = ""
    message_en: str = ""
    severity: Severity
    alert_class: AlertClass = AlertClass.DESIGN_REPLICATION
    exceptions: tuple[str, ...] = ()
    abstain_if: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    fixtures: tuple[RuleFixture, ...] = ()
    requires_human_confirmation: bool = False
    scope_dimension: str = "contrast"  # contrast | endpoint | block
    enabled: bool = True
    #: Collegamento theory v8 (PRD §7.14: ogni regola eseguibile riferisce una
    #: clausola). None e' lecito solo nei ruleset legacy (senza theory_version)
    #: oppure nella forma fail-closed esplicita: regola disabilitata con
    #: ``theory_status=SCIENTIFIC_REVIEW_REQUIRED``.
    theory_clause: str | None = None
    theory_status: TheoryLinkageStatus | None = None

    @model_validator(mode="after")
    def _has_message(self) -> Rule:
        if not (self.message_it or self.message_en or self.inference):
            raise ValueError(f"regola {self.rule_id} senza messaggio ne inferenza")
        return self

    def message(self, lang: str = "it") -> str:
        """Il layer linguistico e separato da quello scientifico (PRD NFR-15)."""
        if lang == "it":
            return self.message_it or self.message_en or self.inference
        return self.message_en or self.inference

    def normalized_preconditions(self) -> tuple[str, ...]:
        return tuple(normalize_predicate(p) for p in self.preconditions)

    def normalized_exceptions(self) -> tuple[str, ...]:
        return tuple(normalize_predicate(p) for p in self.exceptions)

    def normalized_abstentions(self) -> tuple[str, ...]:
        return tuple(normalize_predicate(p) for p in self.abstain_if)


class TheoryCoverageGap(NTruthModel):
    """Clausola theory dichiarata non coperta dal ruleset, con rationale (NFR-33)."""

    clause_id: str
    rationale: str = Field(min_length=1)


class Ruleset(NTruthModel):
    """Insieme versionato di regole, con checksum per il report."""

    ruleset_id: str
    version: str
    description: str = ""
    rules: tuple[Rule, ...] = ()
    source_path: str | None = None
    #: Riferimento theory ``<theory_id>-<version>`` (PRD §20.3, NFR-33).
    #: None = ruleset legacy pre-v8 senza collegamento theory.
    theory_version: str | None = None
    theory_coverage_gaps: tuple[TheoryCoverageGap, ...] = ()

    @property
    def is_legacy(self) -> bool:
        """Ruleset precedente al contratto theory v8 (nessun collegamento)."""
        return self.theory_version is None

    @model_validator(mode="after")
    def _unique_ids(self) -> Ruleset:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.rule_id in seen:
                raise ValueError(f"rule_id duplicato nel ruleset: {rule.rule_id}")
            seen.add(rule.rule_id)
        return self

    def checksum(self) -> str:
        #: ``exclude_none``: i campi theory assenti (ruleset legacy) non
        #: alterano il checksum storico dei ruleset pre-v8; i valori di
        #: collegamento presenti nei ruleset v8 restano invece nel checksum.
        return content_checksum(
            [r.model_dump(mode="json", exclude={"fixtures"}, exclude_none=True) for r in self.rules]
        )

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.rule_id == rule_id), None)

    def by_domain(self, *domains: str) -> list[Rule]:
        wanted = set(domains)
        return [r for r in self.rules if r.enabled and (not wanted or r.domain in wanted)]


class PremiseTrace(NTruthModel):
    """Legame machine-readable tra una premessa, i fatti e le evidenze usate."""

    expression: str
    result: bool | None
    fact_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    provenance_origins: tuple[str, ...] = ()


class RuleEvaluation(NTruthModel):
    """Traccia della valutazione, anche quando la regola non scatta (auditabilita)."""

    rule_id: str
    rule_version: str = ""
    ruleset_id: str = ""
    ruleset_version: str = ""
    ruleset_checksum: str = ""
    outcome: RuleOutcome
    matched: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    triggered_exception: str | None = None
    triggered_abstention: str | None = None
    unknown_predicates: tuple[str, ...] = Field(default=())
    scope_label: str = ""
    premise_trace: tuple[PremiseTrace, ...] = ()
    evidence_gap: tuple[str, ...] = ()
    output_ids: tuple[str, ...] = ()


def normalize_predicate(expr: str) -> str:
    """Converte la forma triple del PRD nella forma funzionale valutabile."""
    expr = expr.strip().rstrip(".")
    if "(" in expr:
        return expr
    match = _TRIPLE_RE.match(expr)
    if not match:
        return expr
    pred = match.group("pred")
    fn = _TRIPLE_PREDICATES.get(pred)
    if fn is None:
        return expr
    subject = match.group("subject")
    obj = match.group("object")
    modifier = (match.group("modifier") or "").strip()
    if fn == "assigned_at" and modifier.endswith("higher"):
        return f"assigned_at_or_above({obj})"
    if fn == "assigned_at" and modifier.endswith("lower"):
        return f"assigned_at_or_below({obj})"
    if fn in {"measured_on", "analyzed_as"}:
        return f"{fn}({obj})"
    return f"{fn}({subject}, {obj})"
