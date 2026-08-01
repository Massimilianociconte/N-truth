"""Adapter sostituibile del parser AI; nessun backend concreto e incluso."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ntruth.parser_ai.contract import ParserAIInput, ParserAIOutput, validate_contract_pair


@runtime_checkable
class ParserAIAdapter(Protocol):
    """Un backend riceve/rende soltanto i modelli del contratto versionato."""

    name: str
    version: str

    def parse(self, request: ParserAIInput) -> ParserAIOutput: ...


def run_parser_adapter(adapter: ParserAIAdapter, request: ParserAIInput) -> ParserAIOutput:
    """Convalida sempre l'output rispetto alla stessa richiesta sorgente."""

    response = adapter.parse(request)
    if not isinstance(response, ParserAIOutput):
        response = ParserAIOutput.model_validate(response)
    return validate_contract_pair(request, response)
