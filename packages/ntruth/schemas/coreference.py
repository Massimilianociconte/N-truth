"""Explicit mention and intra-document coreference contracts (PRD FR-011).

Coreference is represented between textual mentions, not inferred between the
aggregate biological/technical node types used by the experiment graph.  This
keeps the evidence auditable and prevents a surface-form heuristic from
silently merging scientific entities.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ntruth.schemas.core import NTruthModel
from ntruth.schemas.graph import NodeType, RelationType


class Mention(NTruthModel):
    """A localized entity mention participating in a possible coreference chain."""

    id: str
    text: str
    normalized: str
    node_type: NodeType
    evidence_id: str
    is_anaphor: bool = False


class CoreferenceLink(NTruthModel):
    """Directed link from an anaphoric mention to its explicit antecedent."""

    id: str
    anaphor_mention_id: str
    antecedent_mention_id: str
    relation_type: Literal[RelationType.COREFERS_WITH] = RelationType.COREFERS_WITH
    evidence_ids: tuple[str, ...] = ()
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    method: str = "deterministic_anaphoric_head_match"
