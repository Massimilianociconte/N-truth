"""Cross-domain role policy (PRD v7 §14, §18).

A high-quality in vivo dataset may be gold for an Animal Profile, auxiliary for
in vitro, held-out challenge, schema alignment or stress test - never automatic
validation of an in vitro release.
"""

from ntruth.cross_domain.roles import (
    CrossDomainRoleDecision,
    DataRole,
    decide_cross_domain_role,
)

__all__ = [
    "CrossDomainRoleDecision",
    "DataRole",
    "decide_cross_domain_role",
]
