from __future__ import annotations

import importlib

import pytest
from pydantic import PydanticDeprecatedSince20, ValidationError

fix6 = importlib.import_module("test_prd_v8_task7_evaluation_fix6")


def test_result_deprecated_copy_cannot_skip_cluster_authority_validation() -> None:
    """Catches deprecated copy creating a serializable scientific result bypass."""

    result, _conformance = fix6._cluster_outputs()

    with (
        pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"),
        pytest.raises(ValidationError),
    ):
        forged = result.copy(
            update={
                "scientific_use_permitted": True,
                "blockers": (),
            }
        )
        forged.model_dump_json()


def test_conformance_deprecated_copy_cannot_skip_non_authority_validation() -> None:
    """Catches deprecated copy creating a serializable conformance authority bypass."""

    _result, conformance = fix6._cluster_outputs()

    with (
        pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"),
        pytest.raises(ValidationError),
    ):
        forged = conformance.copy(
            update={
                "scientific_use_permitted": True,
                "blockers": (),
            }
        )
        forged.model_dump_json()


def test_cluster_output_deprecated_copy_without_update_remains_supported() -> None:
    """Catches closing the bypass by removing ordinary deprecated-copy compatibility."""

    for output in fix6._cluster_outputs():
        with pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"):
            copied = output.copy()

        assert copied == output
        assert copied is not output
        assert type(output).model_validate(copied.model_dump(mode="python")) == output


def test_cluster_output_deprecated_copy_rejects_partial_models() -> None:
    """Catches include/exclude producing a serializable but invalid governed output."""

    result, _conformance = fix6._cluster_outputs()

    with (
        pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"),
        pytest.raises(TypeError, match="partial cluster output copies are forbidden"),
    ):
        result.copy(exclude={"blockers"})
