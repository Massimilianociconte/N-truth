"""Checksum-verifying loaders for isolated PRD v8 theory/conformance assets."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ntruth.derivation_theory.contracts import (
    ConformanceBundle,
    ConformanceFixtureSet,
    DerivationTheory,
    ProfilePredicateClosureAsset,
    ReferenceRoleRegistry,
    ReviewedEvaluatorRegistry,
    V8Rulebook,
)

THEORY_FILENAME = "ntruth-derivation-theory-0.1.0.json"
PROFILE_CLOSURE_FILENAME = "simple-cell-culture-profile-closure-0.1.0.json"
RULEBOOK_FILENAME = "ntruth-v8-core-0.1.0.json"
REFERENCE_REGISTRY_FILENAME = "reference-role-registry-0.1.0.json"
FIXTURE_SET_FILENAME = "implementation-conformance-fixtures-simple-cell-culture-0.1.0.json"
EVALUATOR_REGISTRY_FILENAME = "reviewed-evaluator-registry-0.1.1.json"


class AssetChecksumError(ValueError):
    """The semantic JSON payload does not match its declared immutable pin."""


def canonical_checksum(payload: Any, *, exclude_declared_checksum: bool = False) -> str:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    if exclude_declared_checksum and isinstance(payload, dict):
        payload = {key: value for key, value in payload.items() if key != "declared_checksum"}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_verified[T: BaseModel](resource: Path | Traversable, model: type[T]) -> T:
    payload = json.loads(resource.read_text(encoding="utf-8"))
    declared = payload.get("declared_checksum")
    actual = canonical_checksum(payload, exclude_declared_checksum=True)
    if declared != actual:
        raise AssetChecksumError(
            f"checksum mismatch for {resource}: declared={declared} actual={actual}"
        )
    return model.model_validate(payload)


def load_derivation_theory_file(resource: Path | Traversable) -> DerivationTheory:
    return _load_verified(resource, DerivationTheory)


def load_v8_rulebook_file(resource: Path | Traversable) -> V8Rulebook:
    return _load_verified(resource, V8Rulebook)


def load_reference_registry_file(resource: Path | Traversable) -> ReferenceRoleRegistry:
    return _load_verified(resource, ReferenceRoleRegistry)


def load_profile_closure_file(resource: Path | Traversable) -> ProfilePredicateClosureAsset:
    return _load_verified(resource, ProfilePredicateClosureAsset)


def load_conformance_fixture_set_file(resource: Path | Traversable) -> ConformanceFixtureSet:
    return _load_verified(resource, ConformanceFixtureSet)


def load_evaluator_registry_file(resource: Path | Traversable) -> ReviewedEvaluatorRegistry:
    return _load_verified(resource, ReviewedEvaluatorRegistry)


def _load_bundle(
    *,
    theory_resource: Path | Traversable,
    profile_resource: Path | Traversable,
    rulebook_resource: Path | Traversable,
    registry_resource: Path | Traversable,
    fixture_set_resource: Path | Traversable,
    evaluator_registry_resource: Path | Traversable,
) -> ConformanceBundle:
    return ConformanceBundle(
        theory=load_derivation_theory_file(theory_resource),
        profile_closure=load_profile_closure_file(profile_resource),
        rulebook=load_v8_rulebook_file(rulebook_resource),
        reference_registry=load_reference_registry_file(registry_resource),
        fixture_set=load_conformance_fixture_set_file(fixture_set_resource),
        evaluator_registry=load_evaluator_registry_file(evaluator_registry_resource),
    )


def load_canonical_bundle(repository_root: Path) -> ConformanceBundle:
    """Load the checked-out canonical asset set without installed-resource fallback."""

    conformance_assets = repository_root / "packages" / "ntruth" / "conformance" / "assets"
    return _load_bundle(
        theory_resource=repository_root / "theories" / THEORY_FILENAME,
        profile_resource=repository_root / "theories" / PROFILE_CLOSURE_FILENAME,
        rulebook_resource=repository_root / "rulesets" / RULEBOOK_FILENAME,
        registry_resource=conformance_assets / REFERENCE_REGISTRY_FILENAME,
        fixture_set_resource=conformance_assets / FIXTURE_SET_FILENAME,
        evaluator_registry_resource=(repository_root / "theories" / EVALUATOR_REGISTRY_FILENAME),
    )


def load_installed_bundle() -> ConformanceBundle:
    """Load only wheel/sdist package resources and fail closed if any pin is absent."""

    package_root = files("ntruth")
    conformance_assets = files("ntruth.conformance").joinpath("assets")
    return _load_bundle(
        theory_resource=package_root.joinpath("_bundled", "theories", THEORY_FILENAME),
        profile_resource=package_root.joinpath("_bundled", "theories", PROFILE_CLOSURE_FILENAME),
        rulebook_resource=package_root.joinpath("_bundled", "rulesets", RULEBOOK_FILENAME),
        registry_resource=conformance_assets.joinpath(REFERENCE_REGISTRY_FILENAME),
        fixture_set_resource=conformance_assets.joinpath(FIXTURE_SET_FILENAME),
        evaluator_registry_resource=package_root.joinpath(
            "_bundled", "theories", EVALUATOR_REGISTRY_FILENAME
        ),
    )


__all__ = [
    "AssetChecksumError",
    "canonical_checksum",
    "load_canonical_bundle",
    "load_conformance_fixture_set_file",
    "load_derivation_theory_file",
    "load_evaluator_registry_file",
    "load_installed_bundle",
    "load_profile_closure_file",
    "load_reference_registry_file",
    "load_v8_rulebook_file",
]
