"""Migrazione KnowledgeState dei campi scientifici v7 (Appendice AC/AE).

I campi bare-nullable restano invariati nei payload legacy (storage e golden
non si rompono); la semantica open-world v8 vive nelle proiezioni di confine
``knowledge_values()`` dove ogni bare null diventa uno stato esplicito con
audit, secondo regole field-specific.
"""

from __future__ import annotations

from ntruth.schemas.core import Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    _FACTOR_V8_FIELDS,
    _UNIT_ASSESSMENT_V8_FIELDS,
    Factor,
    NScope,
    UnitAssessment,
)
from ntruth.schemas.kernel import KnowledgeState


def _provenance() -> Provenance:
    return Provenance(origin=ProvenanceKind.EXPLICIT)


def _assessment(**overrides: object) -> UnitAssessment:
    payload: dict[str, object] = {
        "id": "UA-01",
        "scope": NScope(is_global=True),
        "provenance": _provenance(),
    }
    payload.update(overrides)
    return UnitAssessment.model_validate(payload)


def _factor(**overrides: object) -> Factor:
    payload: dict[str, object] = {
        "id": "F-01",
        "name": "treatment",
        "provenance": _provenance(),
    }
    payload.update(overrides)
    return Factor.model_validate(payload)


def test_unit_assessment_bare_nulls_become_explicit_states() -> None:
    projection = _assessment().knowledge_values()
    assert set(projection) == set(_UNIT_ASSESSMENT_V8_FIELDS)
    for field_name, wrapped in projection.items():
        assert wrapped.knowledge_state is KnowledgeState.NOT_REPORTED, field_name
        assert wrapped.value is None
        assert wrapped.migration_note and field_name in wrapped.migration_note


def test_unit_assessment_set_values_stay_present() -> None:
    assessment = _assessment(n_planned=6, effective_n=2.5, biological_source_count=1)
    projection = assessment.knowledge_values()
    assert projection["n_planned"].knowledge_state is KnowledgeState.PRESENT
    assert projection["n_planned"].value == 6
    assert projection["effective_n"].value == 2.5
    assert projection["biological_source_count"].value == 1
    assert projection["n_declared"].knowledge_state is KnowledgeState.NOT_REPORTED


def test_unit_assessment_serialization_unchanged_by_migration() -> None:
    payload = {
        "id": "UA-02",
        "scope": {"is_global": True},
        "n_planned": 4,
        "n_analysed": 3,
        "provenance": {"origin": "explicit"},
    }
    loaded = UnitAssessment.model_validate(payload)
    dumped = loaded.model_dump()
    # Nessun campo v8 nuovo entra nella serializzazione legacy.
    assert "knowledge_values" not in dumped
    assert "knowledge_state" not in dumped
    assert dumped["n_planned"] == 4
    assert dumped["n_analysed"] == 3
    # Round-trip identico sul payload legacy.
    assert UnitAssessment.model_validate(dumped).model_dump() == dumped


def test_factor_timing_and_source_open_world_projection() -> None:
    projection = _factor().knowledge_values()
    assert set(projection) == set(_FACTOR_V8_FIELDS)
    timing = projection["allocation_timing"]
    source = projection["source_biological_preparation"]
    assert timing.knowledge_state is KnowledgeState.NOT_REPORTED
    assert timing.migration_note and "allocation_timing" in timing.migration_note
    assert source.knowledge_state is KnowledgeState.UNKNOWN
    assert source.migration_note and "source_biological_preparation" in source.migration_note


def test_factor_set_fields_stay_present_and_serialization_unchanged() -> None:
    payload = {
        "id": "F-02",
        "name": "treatment",
        "allocation_timing": "after_splitting",
        "source_biological_preparation": "culture_batch_01",
        "provenance": {"origin": "explicit"},
    }
    factor = Factor.model_validate(payload)
    projection = factor.knowledge_values()
    assert projection["allocation_timing"].value == "after_splitting"
    assert projection["source_biological_preparation"].value == "culture_batch_01"
    dumped = factor.model_dump()
    assert "knowledge_values" not in dumped
    assert dumped["allocation_timing"] == "after_splitting"
    assert Factor.model_validate(dumped).model_dump() == dumped
