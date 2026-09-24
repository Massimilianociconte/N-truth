"""PRD v8 Task 9 regressions for transitive evaluator implementation pins."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from ntruth.schemas.claims import DerivedClaim


def _runtime() -> Any:
    return import_module("ntruth.derivation_theory.runtime")


def _bundle() -> Any:
    loader = import_module("ntruth.derivation_theory.loader")
    return loader.load_canonical_bundle(Path(__file__).parents[2])


def _replacement_stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-unreviewed-identity-drift-{len(parts)}"


class _DriftedDerivedClaim(DerivedClaim):
    unreviewed_output_contract_field: str = "unreviewed"


def test_derivation_digest_covers_live_stable_id_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    clause_id = "DT-A-ASSIGNMENT-UNIT"
    reviewed = runtime._derivation_code_checksum(clause_id)

    monkeypatch.setattr(runtime, "stable_id", _replacement_stable_id)

    assert runtime._derivation_code_checksum(clause_id) != reviewed


def test_derivation_digest_covers_live_output_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    clause_id = "DT-A-ASSIGNMENT-UNIT"
    reviewed = runtime._derivation_code_checksum(clause_id)

    monkeypatch.setattr(runtime, "DerivedClaim", _DriftedDerivedClaim)

    assert runtime._derivation_code_checksum(clause_id) != reviewed


def test_reviewed_bundle_fails_closed_after_transitive_dependency_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    bundle = _bundle()
    clause = bundle.theory.clauses[0]
    rule = next(item for item in bundle.rulebook.rules if item.theory_clause_id == clause.clause_id)

    monkeypatch.setattr(runtime, "stable_id", _replacement_stable_id)

    with pytest.raises(runtime.V8EvaluatorReviewRequired):
        runtime._reviewed_derivation_artifact(bundle, clause, rule)
