from __future__ import annotations

import importlib
from typing import Any, Literal

import pytest

from ntruth.mvt_a.verifier import hard_verify_candidates
from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.schemas import block_boundary as boundary

fix1 = importlib.import_module("test_prd_v8_experiment_block_boundary_fix1")


def _forged_extra_model(
    model: Any,
    *,
    field: str,
    value: object,
    construction: Literal["model_copy", "model_construct"],
) -> Any:
    if construction == "model_copy":
        return model.model_copy(update={field: value})
    forged = type(model).model_construct(**model.__dict__)
    forged.__dict__[field] = value
    return forged


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("determinability", "DETERMINATE"),
        ("design_adequacy", "ADEQUATE"),
        ("n", 12),
        ("experimental_unit", "CAGE"),
        ("rule_result", {"verdict": "PASS"}),
    ),
)
@pytest.mark.parametrize("location", ("root", "nested"))
@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
def test_hard_verifier_rejects_pickle_visible_raw_final_fields(
    field: str,
    value: object,
    location: Literal["root", "nested"],
    construction: Literal["model_copy", "model_construct"],
) -> None:
    """Catches model dumping away a forbidden final field before verification."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    if location == "root":
        forged = _forged_extra_model(
            valid,
            field=field,
            value=value,
            construction=construction,
        )
    else:
        forged_boundary = _forged_extra_model(
            valid.block_boundaries[0],
            field=field,
            value=value,
            construction=construction,
        )
        forged = valid.model_copy(update={"block_boundaries": (forged_boundary,)})

    restored = fix1._unsafe_candidate_pickle_roundtrip(forged)
    restored_target = restored if location == "root" else restored.block_boundaries[0]
    assert dict(restored_target)[field] == value

    result = hard_verify_candidates(restored)
    assert result.passed is False
    assert any(field in error.detail for error in result.errors)
    with pytest.raises(ValueError, match=field):
        boundary.verify_candidate_experiment_block_boundaries(restored)


def test_hard_verifier_checks_pydantic_extra_storage_before_dumping() -> None:
    """Catches a forbidden final field hidden in Pydantic's separate extra store."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    forged = valid.model_copy()
    object.__setattr__(forged, "__pydantic_extra__", {"determinability": "DETERMINATE"})
    restored = fix1._unsafe_candidate_pickle_roundtrip(forged)

    result = hard_verify_candidates(restored)
    assert result.passed is False
    assert any("determinability" in error.detail for error in result.errors)


def test_hard_verifier_rejects_undeclared_private_cache_attributes() -> None:
    """Catches an underscored cache laundering undeclared parser state."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    cached = valid.model_copy()
    cached.__dict__["_private_cache"] = {"determinability": "DETERMINATE"}

    result = hard_verify_candidates(cached)

    assert result.passed is False
    assert "undeclared" in result.errors[0].detail
    with pytest.raises(ValueError, match="undeclared"):
        boundary.verify_candidate_experiment_block_boundaries(cached)


def test_change_ledger_rejects_consuming_one_split_with_two_merges() -> None:
    """Catches two incompatible merged successors resolving the same prior split."""

    split = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.SPLIT,
        prior_block_ids=("EB-OLD",),
        resulting_block_ids=("EB-01", "EB-02"),
        boundary_basis=(fix1._predicate(),),
        source_refs=("EV-1",),
        rationale="One confirmed split created the two blocks.",
        confirmation_event_ids=("CONF-SPLIT",),
    )
    merge_one = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.MERGE,
        prior_block_ids=("EB-01", "EB-02"),
        resulting_block_ids=("EB-MERGED-ONE",),
        boundary_basis=(
            fix1._predicate(representability=boundary.InternalQueryRepresentability.REPRESENTABLE),
        ),
        source_refs=("EV-1",),
        rationale="The first merged successor resolves the split.",
        confirmation_event_ids=("CONF-MERGE-ONE",),
        previous=split,
    )
    merge_two = boundary.build_experiment_block_boundary_change(
        change_kind=boundary.BlockBoundaryChangeKind.MERGE,
        prior_block_ids=("EB-01", "EB-02"),
        resulting_block_ids=("EB-MERGED-TWO",),
        boundary_basis=(
            fix1._predicate(representability=boundary.InternalQueryRepresentability.REPRESENTABLE),
        ),
        source_refs=("EV-1",),
        rationale="A contradictory second successor has no revision contract.",
        confirmation_event_ids=("CONF-MERGE-TWO",),
        previous=merge_one,
    )
    changes = (split, merge_one, merge_two)
    change_ledger = boundary.build_experiment_block_boundary_change_ledger(changes=changes)

    with pytest.raises(ValueError, match=r"MERGE|consum|resolved|successor"):
        boundary.verify_experiment_block_boundary_change_ledger(
            change_ledger,
            ledger=fix1._epistemic_change_ledger(*changes),
        )
