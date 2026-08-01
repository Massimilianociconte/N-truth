"""Conservative deterministic intra-document coreference baseline (FR-011).

Only explicit demonstrative/identity cues (for example ``these cultures`` or
``le stesse colture``) are linked to the nearest preceding mention with the
same already-defined node type.  Bare pronouns and cross-file links are left
unresolved: guessing them would invent scientific identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ntruth.extract.facts import make_evidence
from ntruth.extract.lexicon import ENTITY_PATTERN, lookup_entity, normalize_term
from ntruth.schemas.core import EvidenceSpan, stable_id
from ntruth.schemas.coreference import CoreferenceLink, Mention
from ntruth.schemas.document import DocumentIR
from ntruth.schemas.graph import NodeType

_ANAPHOR_CUE = re.compile(
    r"(?P<cue>these|those|such|this|the\s+same|"
    r"queste|questi|quei|quelle|tali|la\s+stessa|le\s+stesse|"
    r"lo\s+stesso|gli\s+stessi)\s+$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class CoreferenceResult:
    mentions: list[Mention] = field(default_factory=list)
    links: list[CoreferenceLink] = field(default_factory=list)
    evidence: list[EvidenceSpan] = field(default_factory=list)


def resolve_coreferences(ir: DocumentIR) -> CoreferenceResult:
    """Resolve only evidence-grounded anaphoric noun phrases inside each file."""
    result = CoreferenceResult()
    last_by_file_and_type: dict[tuple[str, NodeType], Mention] = {}

    for paragraph in ir.paragraphs:
        section = ir.section(paragraph.section_id)
        for match in ENTITY_PATTERN.finditer(paragraph.text):
            surface = match.group(0)
            node_type = lookup_entity(surface)
            if node_type is None:
                continue

            cue_start = _cue_start(paragraph.text, match.start())
            is_anaphor = cue_start is not None
            local_start = cue_start if cue_start is not None else match.start()
            local_end = match.end()
            mention_text = paragraph.text[local_start:local_end]
            evidence = make_evidence(
                file_id=paragraph.file_id,
                section_id=paragraph.section_id,
                section_title=section.title if section else None,
                start=paragraph.start + local_start,
                end=paragraph.start + local_end,
                text=mention_text,
                parser_version=ir.parser_version,
            )
            result.evidence.append(evidence)
            mention = Mention(
                id=stable_id("men", evidence.id, str(node_type), normalize_term(surface)),
                text=mention_text,
                normalized=normalize_term(surface),
                node_type=node_type,
                evidence_id=evidence.id,
                is_anaphor=is_anaphor,
            )
            result.mentions.append(mention)

            key = (paragraph.file_id, node_type)
            antecedent = last_by_file_and_type.get(key)
            if is_anaphor and antecedent is not None:
                result.links.append(
                    CoreferenceLink(
                        id=stable_id("crf", mention.id, antecedent.id),
                        anaphor_mention_id=mention.id,
                        antecedent_mention_id=antecedent.id,
                        evidence_ids=(antecedent.evidence_id, mention.evidence_id),
                        confidence=0.99,
                    )
                )
            last_by_file_and_type[key] = mention

    result.evidence = list({e.id: e for e in result.evidence}.values())
    return result


def _cue_start(text: str, entity_start: int) -> int | None:
    prefix_start = max(0, entity_start - 24)
    prefix = text[prefix_start:entity_start]
    match = _ANAPHOR_CUE.search(prefix)
    return prefix_start + match.start("cue") if match else None
