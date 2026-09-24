"""SESOI hierarchy: precedenza e marcatura debole di Cohen."""

from __future__ import annotations

import pytest

from ntruth.power.schema import SesoiRecord, SesoiSource
from ntruth.power.sesoi import (
    SESOI_PRECEDENCE,
    cohen_conventional_assumption,
    is_weak_sesoi,
    require_sesoi,
    sesoi_rank,
)


def _record(source: SesoiSource) -> SesoiRecord:
    return SesoiRecord(
        source=source,
        value=0.5,
        effect_scale="d",
        endpoint_id="viability",
        contrast_id="control_vs_treated",
        rationale="Fondamento documentato dal team.",
    )


def test_precedence_order_is_declared_first_cohen_last() -> None:
    assert SESOI_PRECEDENCE[0] is SesoiSource.DECLARED_SESOI
    assert SESOI_PRECEDENCE[-1] is SesoiSource.CONVENTIONAL_COHEN
    assert sesoi_rank(SesoiSource.DECLARED_SESOI) < sesoi_rank(SesoiSource.CONVENTIONAL_COHEN)


def test_only_cohen_is_weak() -> None:
    for source in SESOI_PRECEDENCE:
        assert is_weak_sesoi(_record(source)) is (source is SesoiSource.CONVENTIONAL_COHEN)


def test_require_sesoi_enforces_scale() -> None:
    require_sesoi(_record(SesoiSource.DECLARED_SESOI), "d")
    with pytest.raises(ValueError, match="non copre la scala"):
        require_sesoi(_record(SesoiSource.DECLARED_SESOI), "f")


def test_cohen_assumption_is_non_blocking_but_explicit() -> None:
    assumption = cohen_conventional_assumption(_record(SesoiSource.CONVENTIONAL_COHEN))
    assert assumption.code == "conventional_cohen_weak_assumption"
    assert assumption.blocking is False
    assert "weak planning assumption" in assumption.message
