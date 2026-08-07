"""Modelli frozen della Derivation Theory (PRD v8.0 §7.13-§7.15, §20.3, §26.3).

La teoria e' indipendente dal Rulebook (PRD §7.14): definisce, per un grafo
validato ``G``, un profilo ``P`` e una query ``Q``, il contratto
``D_T(G, P, Q) -> DerivedClaimSet``. Ogni clausola minima di derivazione
(§7.15, famiglie A-G) dichiara enunciato normativo, predicati richiesti e
irrilevanti, minimal counterfactual e known gaps (NFR-33, §26.3).

Politica fail-closed: l'artefatto 0.1.0 non e' revisionato
(``SCIENTIFIC_REVIEW_REQUIRED``, registro SRR-0003); nessun enunciato oltre il
testo PRD v8.0 viene introdotto senza revisione scientifica registrata.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel, content_checksum


class TheoryStatus(StrEnum):
    """Stato di revisione scientifica dell'artefatto theory (registro SRR)."""

    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"
    APPROVED = "APPROVED"


class ClauseFamily(StrEnum):
    """Famiglie di clausole minime di derivazione (PRD v8.0 §7.15 A-G)."""

    ASSIGNMENT_UNIT = "A"
    EXPERIMENTAL_UNIT = "B"
    EXPERIMENTAL_UNIT_COUNT = "C"
    BIOLOGICAL_SOURCE_COUNT = "D"
    INTERFERENCE_ESTIMAND_SUPPORT = "E"
    ANALYTICAL_DEPENDENCE = "F"
    INFERENCE_SCOPE = "G"


class PredicateAvailability(StrEnum):
    """Disponibilita' del predicato nel registro del rules engine."""

    IMPLEMENTED = "implemented"
    KNOWN_GAP = "known_gap"


class ClauseIdBasis(StrEnum):
    """Origine del clause ID: verbatim negli esempi PRD oppure convenzione."""

    PRD_EXAMPLE_VERBATIM = "prd_example_verbatim"
    MIGRATION_DERIVED = "migration_derived"


class TheoryPredicateRef(FrozenModel):
    """Predicato richiesto da una clausola, con stato di implementazione."""

    predicate: str = Field(min_length=1)
    status: PredicateAvailability


class IrrelevantPredicateRef(FrozenModel):
    """Predicato irrilevante per la clausola, con rationale obbligatoria.

    La rilevanza e' claim-specifica e versionata con la teoria (PRD §7.13,
    §10.2 e Appendice M.2): una dimensione irrilevante non puo' essere omessa.
    """

    predicate: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class TheoryClause(FrozenModel):
    """Clausola minima di derivazione (PRD v8.0 §7.15, §26.3)."""

    clause_id: str = Field(pattern=r"^DT-[A-Z0-9-]+$")
    family: ClauseFamily
    id_basis: ClauseIdBasis
    id_provenance: tuple[str, ...] = ()
    normative_statement: str = Field(min_length=1)
    normative_source: str = Field(min_length=1)
    required_predicates: tuple[TheoryPredicateRef, ...] = ()
    irrelevant_predicates: tuple[IrrelevantPredicateRef, ...] = ()
    minimal_counterfactual: str = ""
    known_gaps: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _gap_documentation(self) -> TheoryClause:
        #: ogni predicato segnato known_gap deve essere motivato nei known_gaps.
        gaps = {p.predicate for p in self.required_predicates if p.status is PredicateAvailability.KNOWN_GAP}
        if gaps and not self.known_gaps:
            raise ValueError(f"clausola {self.clause_id}: known_gap senza known_gaps documentati")
        return self


class TheoryMetadata(FrozenModel):
    """Identita' e stato di revisione della teoria (PRD §20.3, NFR-33)."""

    theory_id: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: TheoryStatus
    derivation_contract: str = "D_T(G, P, Q) -> DerivedClaimSet"
    prd_document: str = ""
    prd_sections: tuple[str, ...] = ()
    reviewer: str = ""
    review_date: str = ""
    srr_entry: str = ""
    notes: str = ""

    @property
    def theory_ref(self) -> str:
        """Riferimento completo ``<theory_id>-<version>`` usato dai ruleset v8."""
        return f"{self.theory_id}-{self.version}"


class DerivationTheory(FrozenModel):
    """Artefatto theory versionato: metadati + clausole A-G."""

    metadata: TheoryMetadata
    clauses: tuple[TheoryClause, ...]

    @model_validator(mode="after")
    def _unique_clauses(self) -> DerivationTheory:
        seen: set[str] = set()
        for clause in self.clauses:
            if clause.clause_id in seen:
                raise ValueError(f"clause_id duplicato nella teoria: {clause.clause_id}")
            seen.add(clause.clause_id)
        if not self.clauses:
            raise ValueError("teoria senza clausole")
        return self

    @property
    def theory_ref(self) -> str:
        return self.metadata.theory_ref

    def clause_ids(self) -> tuple[str, ...]:
        return tuple(c.clause_id for c in self.clauses)

    def clause(self, clause_id: str) -> TheoryClause | None:
        return next((c for c in self.clauses if c.clause_id == clause_id), None)

    def clauses_by_family(self, family: ClauseFamily) -> tuple[TheoryClause, ...]:
        return tuple(c for c in self.clauses if c.family is family)

    def known_gap_predicates(self) -> frozenset[str]:
        gaps: set[str] = set()
        for clause in self.clauses:
            gaps.update(
                p.predicate
                for p in clause.required_predicates
                if p.status is PredicateAvailability.KNOWN_GAP
            )
        return frozenset(gaps)

    def checksum(self) -> str:
        return content_checksum([c.model_dump(mode="json") for c in self.clauses])
