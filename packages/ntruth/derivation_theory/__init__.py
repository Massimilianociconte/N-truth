"""Derivation Theory v8: clausole minime di derivazione (PRD §7.13-§7.15)."""

from ntruth.derivation_theory.loader import (
    DEFAULT_THEORY_ID,
    DEFAULT_THEORY_VERSION,
    TheoryNotFound,
    available_theories,
    load_theory,
    load_theory_file,
    load_theory_ref,
    parse_theory_ref,
    theory_directories,
)
from ntruth.derivation_theory.models import (
    ClauseFamily,
    ClauseIdBasis,
    DerivationTheory,
    IrrelevantPredicateRef,
    PredicateAvailability,
    TheoryClause,
    TheoryMetadata,
    TheoryPredicateRef,
    TheoryStatus,
)

__all__ = [
    "DEFAULT_THEORY_ID",
    "DEFAULT_THEORY_VERSION",
    "ClauseFamily",
    "ClauseIdBasis",
    "DerivationTheory",
    "IrrelevantPredicateRef",
    "PredicateAvailability",
    "TheoryClause",
    "TheoryMetadata",
    "TheoryNotFound",
    "TheoryPredicateRef",
    "TheoryStatus",
    "available_theories",
    "load_theory",
    "load_theory_file",
    "load_theory_ref",
    "parse_theory_ref",
    "theory_directories",
]
