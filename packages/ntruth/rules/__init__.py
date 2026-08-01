"""Rules engine deterministico e domande (PRD 11.1)."""

from ntruth.rules.engine import RuleRunResult, apply_rules
from ntruth.rules.loader import (
    DEFAULT_RULESET_ID,
    DEFAULT_RULESET_VERSION,
    RulesetNotFound,
    available_rulesets,
    load_ruleset,
    load_ruleset_file,
)
from ntruth.rules.predicates import REGISTRY, RuleContext, UnknownPredicate, resolve_type

__all__ = [
    "DEFAULT_RULESET_ID",
    "DEFAULT_RULESET_VERSION",
    "REGISTRY",
    "RuleContext",
    "RuleRunResult",
    "RulesetNotFound",
    "UnknownPredicate",
    "apply_rules",
    "available_rulesets",
    "load_ruleset",
    "load_ruleset_file",
    "resolve_type",
]
