"""Adapter sostituibile del parser AI; nessun backend concreto e incluso."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ntruth.parser_ai.contract import (
    ParserAIInput,
    ParserAIOutputV3,
    ParserCandidateOutput,
    validate_candidate_contract_pair,
    validate_contract_pair_v3,
)


@runtime_checkable
class ParserAIAdapter(Protocol):
    """Active v8 backend: candidate-only response."""

    name: str
    version: str

    def parse(self, request: ParserAIInput) -> ParserCandidateOutput: ...


def run_parser_adapter(adapter: ParserAIAdapter, request: ParserAIInput) -> ParserCandidateOutput:
    """Convalida sempre l'output rispetto alla stessa richiesta sorgente."""

    response = adapter.parse(request)
    if not isinstance(response, ParserCandidateOutput):
        response = ParserCandidateOutput.model_validate(response)
    return validate_candidate_contract_pair(request, response)


@runtime_checkable
class ParserAIAdapterV3(Protocol):
    """Deprecated, explicitly named PRD-v3 adapter boundary."""

    name: str
    version: str

    def parse(self, request: ParserAIInput) -> ParserAIOutputV3: ...


def run_parser_adapter_v3(adapter: ParserAIAdapterV3, request: ParserAIInput) -> ParserAIOutputV3:
    response = adapter.parse(request)
    if not isinstance(response, ParserAIOutputV3):
        response = ParserAIOutputV3.model_validate(response)
    return validate_contract_pair_v3(request, response)
