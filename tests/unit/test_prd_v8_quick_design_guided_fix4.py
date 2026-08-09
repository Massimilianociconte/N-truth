from __future__ import annotations

import ntruth.quick_design as quick_design
from ntruth.quick_design.guided import (
    GuidedQuickDesignReviewSnapshot as GuidedQuickDesignReviewSnapshotImplementation,
)


def test_guided_review_snapshot_is_importable_from_public_facade() -> None:
    """Catches the reviewed snapshot being reachable only from the implementation module."""

    from ntruth.quick_design import GuidedQuickDesignReviewSnapshot

    assert GuidedQuickDesignReviewSnapshot is GuidedQuickDesignReviewSnapshotImplementation


def test_guided_review_snapshot_is_declared_in_public_facade_all() -> None:
    """Catches wildcard and introspection consumers omitting the public snapshot contract."""

    assert "GuidedQuickDesignReviewSnapshot" in quick_design.__all__
