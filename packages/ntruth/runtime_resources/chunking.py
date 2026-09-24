"""Chunking gerarchico section-first con coordinate riproducibili."""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel, stable_id

_TOKEN_RE = re.compile(r"\S+")


class RuntimeSection(FrozenModel):
    section_id: str = Field(min_length=1)
    text: str
    document_id: str = Field(min_length=1)
    start_offset: int = Field(default=0, ge=0)
    parent_section_id: str | None = None
    level: int = Field(default=1, ge=1)


class RuntimeChunk(FrozenModel):
    chunk_id: str
    document_id: str
    section_id: str
    parent_section_id: str | None = None
    section_level: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    token_count: int = Field(gt=0)

    @model_validator(mode="after")
    def _coordinates_match_text(self) -> RuntimeChunk:
        if self.end <= self.start:
            raise ValueError("end deve essere maggiore di start")
        return self


class HierarchicalChunker:
    """Preserva prima la gerarchia di sezione, poi crea finestre sovrapposte.

    Il tokenizzatore predefinito usa token whitespace e serve per routing e test.
    Un adapter modello deve sostituire ``token_spans`` con gli offset del tokenizer
    effettivo prima di usare queste misure per un benchmark di release.
    """

    def __init__(self, *, chunk_tokens: int, overlap_tokens: int) -> None:
        if chunk_tokens < 1:
            raise ValueError("chunk_tokens deve essere positivo")
        if overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
            raise ValueError("overlap_tokens deve essere tra 0 e chunk_tokens - 1")
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = overlap_tokens

    def chunk_sections(self, sections: Iterable[RuntimeSection]) -> tuple[RuntimeChunk, ...]:
        chunks: list[RuntimeChunk] = []
        for section in sections:
            spans = self.token_spans(section.text)
            if not spans:
                continue
            step = self.chunk_tokens - self.overlap_tokens
            for index, first_token in enumerate(range(0, len(spans), step)):
                selected = spans[first_token : first_token + self.chunk_tokens]
                if not selected:
                    break
                relative_start = selected[0][0]
                relative_end = selected[-1][1]
                text = section.text[relative_start:relative_end]
                start = section.start_offset + relative_start
                end = section.start_offset + relative_end
                chunks.append(
                    RuntimeChunk(
                        chunk_id=stable_id(
                            "chunk",
                            section.document_id,
                            section.section_id,
                            index,
                            start,
                            end,
                            text,
                        ),
                        document_id=section.document_id,
                        section_id=section.section_id,
                        parent_section_id=section.parent_section_id,
                        section_level=section.level,
                        chunk_index=index,
                        start=start,
                        end=end,
                        text=text,
                        token_count=len(selected),
                    )
                )
                if first_token + self.chunk_tokens >= len(spans):
                    break
        return tuple(chunks)

    @staticmethod
    def token_spans(text: str) -> tuple[tuple[int, int], ...]:
        return tuple((match.start(), match.end()) for match in _TOKEN_RE.finditer(text))
