"""Checksum-verifying loaders for isolated PRD v8 theory/conformance assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ntruth.derivation_theory.contracts import (
    ConformanceBundle,
    DerivationTheory,
    ReferenceRoleRegistry,
    V8Rulebook,
)


class AssetChecksumError(ValueError):
    """The semantic JSON payload does not match its declared immutable pin."""


def canonical_checksum(payload: Any, *, exclude_declared_checksum: bool = False) -> str:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    if exclude_declared_checksum and isinstance(payload, dict):
        payload = {key: value for key, value in payload.items() if key != "declared_checksum"}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_verified[T: BaseModel](path: Path, model: type[T]) -> T:
    payload = json.loads(path.read_text(encoding="utf-8"))
    declared = payload.get("declared_checksum")
    actual = canonical_checksum(payload, exclude_declared_checksum=True)
    if declared != actual:
        raise AssetChecksumError(
            f"checksum mismatch for {path}: declared={declared} actual={actual}"
        )
    return model.model_validate(payload)


def load_derivation_theory_file(path: Path) -> DerivationTheory:
    return _load_verified(path, DerivationTheory)


def load_v8_rulebook_file(path: Path) -> V8Rulebook:
    return _load_verified(path, V8Rulebook)


def load_reference_registry_file(path: Path) -> ReferenceRoleRegistry:
    return _load_verified(path, ReferenceRoleRegistry)


def load_canonical_bundle(repository_root: Path) -> ConformanceBundle:
    theory = load_derivation_theory_file(
        repository_root / "theories" / "ntruth-derivation-theory-0.1.0.json"
    )
    rulebook = load_v8_rulebook_file(repository_root / "rulesets" / "ntruth-v8-core-0.1.0.json")
    registry = load_reference_registry_file(
        repository_root
        / "packages"
        / "ntruth"
        / "conformance"
        / "assets"
        / "reference-role-registry-0.1.0.json"
    )
    return ConformanceBundle(theory=theory, rulebook=rulebook, reference_registry=registry)


__all__ = [
    "AssetChecksumError",
    "canonical_checksum",
    "load_canonical_bundle",
    "load_derivation_theory_file",
    "load_reference_registry_file",
    "load_v8_rulebook_file",
]
