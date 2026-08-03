"""Cross-domain role policy (PRD v7 §14, §18)."""

from ntruth.cross_domain.roles import (
    AnnotationAuthority,
    CrossDomainRoleDecision,
    DataRole,
    GoldEligibility,
    decide_cross_domain_role,
)

__all__ = [
    "AnnotationAuthority",
    "CrossDomainRoleDecision",
    "DataRole",
    "GoldEligibility",
    "decide_cross_domain_role",
]
