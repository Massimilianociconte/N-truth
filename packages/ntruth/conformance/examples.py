"""Checksum-verified PRD v8 source-example conformance registry.

Published examples are preserved verbatim. Internal PRD contradictions are
expected-negative fixtures tied to the scientific-review register; they are
never silently rewritten into a passing example.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ntruth.schemas.coverage import ScenarioCoverage

PRD_V8_EXAMPLE_REGISTRY_FILENAME = "prd-v8-example-conformance-registry-8.0.0.json"

# These reviewed digests bind the installed registry to the exact PRD excerpts and
# engineering-canonical payloads accepted by this code version.  The registry's own
# content address detects accidental drift; these independent pins prevent a modified
# source/payload from becoming "verbatim" merely by recalculating that address.
_REVIEWED_EXAMPLE_DIGESTS: dict[str, tuple[str, str]] = {
    "PRD-V8-APPENDIX-A-VERBATIM": (
        "1be8b411f19385375c472c96718bd4e6a42c9c0c1db252993dec2e7604b37f5a",
        "6be9659d394a56684305e2bb699545cec5801d380bfe7fbfb6f39f09737aa81d",
    ),
    "PRD-V8-APPENDIX-AF-VERBATIM": (
        "5b1380fd9d35cf7a0436048b558fd2502fdad1eff6d13958ffb18b48c32f8a1b",
        "a991c2415877cdc577a27e729d4aee1d73b851b795f4d5b8fdf67ebbccc4a0b1",
    ),
    "PRD-V8-APPENDIX-AG-VERBATIM": (
        "d8e80112f90724394e1038946a15b73bd4d23729368d63bb1c21ecafbf3bd1d5",
        "ad451d569bbf9e59f76c36fa2cbcdc8908215da32b1877ef76aef7d0e4d43fc2",
    ),
    "PRD-V8-CANONICAL-SCENARIO-COVERAGE": (
        "7c85d547de195d9202aad876b35dfbc34da2f3fd0f4eb38b7463e02fc0653d3f",
        "9a07895617a4a6e2ed0d830e0da7fe0c190136931c17c9648ebfb45b02277e1d",
    ),
}


def _checksum(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _text_checksum(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ExampleExpectation(StrEnum):
    POSITIVE = "POSITIVE"
    EXPECTED_NEGATIVE = "EXPECTED_NEGATIVE"


class PrdV8Example(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    example_id: str = Field(min_length=1)
    prd_location: str = Field(min_length=1)
    source_kind: Literal["VERBATIM_PRD", "ENGINEERING_CANONICAL_BLOCKED"]
    expectation: ExampleExpectation
    validation_contract: Literal[
        "APPENDIX_A_BUNDLE",
        "DERIVED_CLAIM",
        "CONTAMINATION_ATTESTATION",
        "SCENARIO_COVERAGE",
    ]
    verbatim_source: str = Field(min_length=1)
    payload: dict[str, Any]
    expected_diagnostic_ids: tuple[str, ...]
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _expectation_closed(self) -> Self:
        if self.expectation is ExampleExpectation.POSITIVE and self.expected_diagnostic_ids:
            raise ValueError("positive PRD example cannot declare expected diagnostics")
        if (
            self.expectation is ExampleExpectation.EXPECTED_NEGATIVE
            and not self.expected_diagnostic_ids
        ):
            raise ValueError("expected-negative PRD example requires diagnostic IDs")
        if len(set(self.expected_diagnostic_ids)) != len(self.expected_diagnostic_ids):
            raise ValueError("PRD example diagnostic IDs must be unique")
        if any(not item.startswith("SRR-V8-") for item in self.expected_diagnostic_ids):
            raise ValueError("PRD example diagnostics must reference the SRR register")
        return self


class PrdV8ExampleRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    schema_version: Literal["8.0.0"] = "8.0.0"
    registry_id: str
    source_document: Literal["N-Truth_PRD_scientifico_completo_v8.0.pdf"]
    examples: tuple[PrdV8Example, ...] = Field(min_length=1)
    declared_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _addressed_and_unique(self) -> Self:
        ids = tuple(example.example_id for example in self.examples)
        if len(set(ids)) != len(ids):
            raise ValueError("PRD example IDs must be unique")
        payload = self.model_dump(mode="json", exclude={"registry_id", "declared_checksum"})
        checksum = _checksum(payload)
        if self.declared_checksum != checksum:
            raise ValueError("PRD example registry checksum mismatch")
        if self.registry_id != f"PRD-V8-EXAMPLES-{checksum[:20]}":
            raise ValueError("PRD example registry ID mismatch")
        if set(ids) != set(_REVIEWED_EXAMPLE_DIGESTS):
            raise ValueError("PRD example registry differs from the reviewed example set")
        for example in self.examples:
            expected_source, expected_payload = _REVIEWED_EXAMPLE_DIGESTS[example.example_id]
            if _text_checksum(example.verbatim_source) != expected_source:
                raise ValueError(
                    f"{example.example_id} verbatim source differs from the reviewed excerpt"
                )
            if _checksum(example.payload) != expected_payload:
                raise ValueError(
                    f"{example.example_id} payload differs from the reviewed source projection"
                )
        return self


class PrdV8ExampleConformanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    failures: tuple[str, ...]
    observed_diagnostics: dict[str, tuple[str, ...]]


def _appendix_a_diagnostics(verbatim_source: str) -> set[str]:
    diagnostics: set[str] = set()
    if "\n    query_id:" in verbatim_source:
        diagnostics.add("SRR-V8-002")
    if (
        "required_predicates:" not in verbatim_source
        or "irrelevant_predicates:" not in verbatim_source
    ):
        diagnostics.add("SRR-V8-003")
    if "\n    determinability:" in verbatim_source:
        diagnostics.add("SRR-V8-004")
    if "report_resolution_state: MULTIPLE_PLAUSIBLE_GRAPHS" in verbatim_source:
        diagnostics.add("SRR-V8-005")
    if "claim_type: DESIGN_ADEQUACY_FINDING" in verbatim_source:
        diagnostics.add("SRR-V8-006")
    if "scenario_set:" in verbatim_source and "\n  exhaustive:" in verbatim_source:
        diagnostics.add("SRR-V8-007")
    if "\n    profile_coverage:" in verbatim_source:
        diagnostics.add("SRR-V8-008")
    if "\n    support_grade:" in verbatim_source:
        diagnostics.add("SRR-V8-001")
    if "source_class: PUBLISHED_METHODS" in verbatim_source or (
        "source_class: SAMPLE_METADATA_EXECUTED" in verbatim_source
    ):
        diagnostics.add("SRR-V8-015")
    return diagnostics


def _derived_claim_diagnostics(verbatim_source: str) -> set[str]:
    diagnostics: set[str] = set()
    if "\n  query_id:" in verbatim_source:
        diagnostics.add("SRR-V8-002")
    if (
        "required_predicates:" not in verbatim_source
        or "irrelevant_predicates:" not in verbatim_source
    ):
        diagnostics.add("SRR-V8-003")
    if "\n  support_grade:" in verbatim_source:
        diagnostics.add("SRR-V8-001")
    if (
        "profile_coverage:" in verbatim_source
        and "predicate_closure_argument_id:" not in verbatim_source
    ):
        diagnostics.add("SRR-V8-008")
    return diagnostics


def _contamination_diagnostics(verbatim_source: str) -> set[str]:
    diagnostics: set[str] = set()
    if "source_class: PROSPECTIVE_PRIVATE|POST_CUTOFF_PUBLIC|LEGACY_PUBLIC" in verbatim_source:
        diagnostics.add("SRR-V8-015")
    if "release_date: 2026-XX-XX" in verbatim_source or "probes_run: []" in verbatim_source:
        diagnostics.add("SRR-V8-018")
    return diagnostics


def _observed_diagnostics(example: PrdV8Example) -> set[str]:
    if example.validation_contract == "APPENDIX_A_BUNDLE":
        return _appendix_a_diagnostics(example.verbatim_source)
    if example.validation_contract == "DERIVED_CLAIM":
        return _derived_claim_diagnostics(example.verbatim_source)
    if example.validation_contract == "CONTAMINATION_ATTESTATION":
        return _contamination_diagnostics(example.verbatim_source)
    ScenarioCoverage.model_validate(example.payload)
    return set()


def evaluate_prd_v8_examples(
    registry: PrdV8ExampleRegistry,
) -> PrdV8ExampleConformanceReport:
    failures: list[str] = []
    observed: dict[str, tuple[str, ...]] = {}
    for example in registry.examples:
        try:
            diagnostics = _observed_diagnostics(example)
        except ValueError as exc:
            diagnostics = set()
            failures.append(f"{example.example_id}: positive validation failed: {exc}")
        observed[example.example_id] = tuple(sorted(diagnostics))
        expected = set(example.expected_diagnostic_ids)
        if diagnostics != expected:
            failures.append(
                f"{example.example_id}: expected {sorted(expected)}, observed {sorted(diagnostics)}"
            )
        if example.expectation is ExampleExpectation.POSITIVE and diagnostics:
            failures.append(f"{example.example_id}: positive example emitted diagnostics")
        if example.expectation is ExampleExpectation.EXPECTED_NEGATIVE and not diagnostics:
            failures.append(f"{example.example_id}: expected-negative example unexpectedly passed")
    return PrdV8ExampleConformanceReport(
        passed=not failures,
        failures=tuple(failures),
        observed_diagnostics=observed,
    )


def load_prd_v8_example_registry_file(path: Path) -> PrdV8ExampleRegistry:
    return PrdV8ExampleRegistry.model_validate_json(path.read_text(encoding="utf-8"))


def load_installed_prd_v8_example_registry() -> PrdV8ExampleRegistry:
    resource = files("ntruth.conformance").joinpath("assets", PRD_V8_EXAMPLE_REGISTRY_FILENAME)
    return PrdV8ExampleRegistry.model_validate_json(resource.read_text(encoding="utf-8"))


__all__ = [
    "PRD_V8_EXAMPLE_REGISTRY_FILENAME",
    "ExampleExpectation",
    "PrdV8Example",
    "PrdV8ExampleConformanceReport",
    "PrdV8ExampleRegistry",
    "evaluate_prd_v8_examples",
    "load_installed_prd_v8_example_registry",
    "load_prd_v8_example_registry_file",
]
