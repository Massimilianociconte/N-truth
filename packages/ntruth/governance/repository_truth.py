"""Machine-readable current-to-target architecture truth for PRD v8.

The map is stored as JSON syntax in a ``.yaml`` file. JSON is a YAML 1.2 subset,
which keeps the clean-checkout gate dependency-free and deterministic.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

MAP_STATUSES = frozenset({"IMPLEMENTED", "PARTIAL", "MISSING", "INCOMPATIBLE", "LEGACY"})
ARCHITECTURE_MAP_ROOT_FIELDS: Final = frozenset(
    {
        "base_sha",
        "components",
        "map_id",
        "schema_version",
        "status_semantics",
        "target_contract",
    }
)
ARCHITECTURE_MAP_ROOT_LITERALS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "schema_version": "8.0.0",
        "map_id": "NTRUTH-PRD-V8-CURRENT-TARGET-20260809",
        "base_sha": "fe089eff42c16e3fa55606be340c85df57c5442b",
        "target_contract": "N-Truth PRD v8.0",
        "status_semantics": (
            "Engineering implementation status; scientific/data readiness is governed "
            "separately and remains HOLD where blocker_ids are present."
        ),
    }
)
COMPONENT_DESCRIPTOR_FIELDS: Final = (
    "component_id",
    "current_paths",
    "target",
    "status",
    "public_api",
    "owner",
    "adr_paths",
    "test_paths",
    "evidence_paths",
    "blocker_ids",
)
REQUIRED_COMPONENT_FIELDS = frozenset(COMPONENT_DESCRIPTOR_FIELDS)

# Reviewed literals are intentionally independent of the mutable architecture map.
CANONICAL_COMPONENT_DESCRIPTOR_SHA256: Final[Mapping[str, str]] = MappingProxyType(
    {
        "canonical-count-registry": (
            "0baf3bbcc78ec50b8839ba87e024afe461c41ff053ae1406f063522c8ccecb39"
        ),
        "core-semantic-kernel": (
            "41494d17c09cd8302a70c25a57dac3d4ea429aefbee1ed5f03167abbae04d778"
        ),
        "corrections-rederivation": (
            "f25b0e4ad2c6d3b64543ad3e052a55305c3a4197602544a20c1c18ce19f4e4f2"
        ),
        "coverage-contracts": ("133c890750748aef4e20d42570f3f0b8be8fe60724b2affb70b3f538211741dd"),
        "derivation-theory": ("13d79bc1a79bb34c8e4118f95e564c6c36d04fef0fddd1b960c31dcad529ab00"),
        "desktop-v8": "8867f0d41d52c84e31d3c8ba36a3345baf61e0ca9142b18da6f199a8692397c3",
        "evaluation-residual-cluster": (
            "e5351f65ba891afc06a9840aa9f6c26a983fea37fdd94b796fb17d9d174fee4f"
        ),
        "event-causal-context": (
            "9993f46f3a45a695a30f06dde869e02e7e0c0f6595f9f199e697cfb8e1ec1708"
        ),
        "experiment-block-boundary": (
            "ae4369f5ae26629c2f77a8b11279e38228bd3f95cfd010aae7c509eab634d1db"
        ),
        "external-challenge-custody": (
            "eada5789b47cf853f5bb5822843a58b3568889edce994014211253d520401607"
        ),
        "graph-equality": ("e3d2b3ed8d132a638958d161b51e44d0ee0740d1c90b96580da392535951305b"),
        "guided-quick-design-v8": (
            "ff8e92ba6741890afee60f38f3da939dc65ebe2c8b56525d7b3436ef6af058be"
        ),
        "ingest-safety": ("175de797d40dc207c5722148fddbfefefb4080095405cc0c6f5848e95983fd6b"),
        "orthogonal-evidence-support": (
            "2520862ae50d8e15b77db9385693c8294bcfc50f14eae1770a9ab38bb357d0cf"
        ),
        "parser-candidate-boundary": (
            "d6a8f7bf9a5a30caa22400ec0f5931de098f0bc6847df3170981f00fb7522b9c"
        ),
        "planned-executed-reporting": (
            "ffb70f0cedc2e3f7a7d9596e3c709da75253c14c289b714fb30fd65d0a8e06f1"
        ),
        "prd-examples-and-schema": (
            "da9baa6009596ef26fa779100d6661600e208c8e2df1efc57f5e42ee52470c98"
        ),
        "protected-training-boundary": (
            "0ba78b9f8e2f76c797525f55b57162b13ee81c3e8c3c21cc977811a765b15b8e"
        ),
        "query-scoped-claims": ("4eefaa665f75d01c87b343d5c3021886d019d687a8efecaeec68ba855fe2c2ef"),
        "reality-gate-v8": ("926c091b52f3372baa05f7107ea4031ea7c9b7d15ab1f046d7a7c53cc9433553"),
        "repository-contract-truth": (
            "e51279ea806af239d70d8d883b1d6ee479e5f660fda9363a4558d0f54fc5db14"
        ),
        "rulebook-conformance": (
            "0e3b9390eff43926dea22ee852dc36a15a4947d195164a3fe6c5f76e86deec7c"
        ),
        "statistical-handoff": ("cd05e8bbf4642a587971caa6838067c0b6de523a7b4ead4de59f1d8c24edea3e"),
        "v7-compatibility": ("069bf653a8b5e9267b59a58ffc5d78e429deb0a2a5cf812e77f8c87e162e7d64"),
        "v7-to-v8-migrations": ("2619879b9042c05c930dd5be08b77d324cfe4ab4dd2ed47805aae9386c316ec5"),
    }
)
CANONICAL_COMPONENT_IDS = frozenset(CANONICAL_COMPONENT_DESCRIPTOR_SHA256)
PATH_FIELDS = ("current_paths", "adr_paths", "test_paths", "evidence_paths")
BLOCKER_RE = re.compile(r"^SRR-V8-[0-9]{3}$")
REGISTER_ROW_RE = re.compile(r"^\| (SRR-V8-[0-9]{3}) \|", re.MULTILINE)
HTTP_METHODS = frozenset({"DELETE", "GET", "PATCH", "POST", "PUT"})
PATH_ROLE_PATTERNS = {
    "current_paths": (
        re.compile(r"^packages/ntruth/(?:[^/]+/)*[^/]+\.py$"),
        re.compile(r"^apps/desktop/src/(?:[^/]+/)*[^/]+\.tsx?$"),
        re.compile(r"^scripts/[^/]+\.py$"),
        re.compile(r"^\.github/workflows/[^/]+\.ya?ml$"),
        re.compile(r"^(?:rulesets|theories)/[^/]+\.json$"),
    ),
    "adr_paths": (re.compile(r"^docs/adr/[0-9]{4}-[^/]+\.md$"),),
    "test_paths": (
        re.compile(r"^tests/(?:integration|security|unit)/(?:[^/]+/)*test_[^/]+\.py$"),
        re.compile(r"^apps/desktop/src/(?:[^/]+/)*[^/]+\.test\.tsx?$"),
    ),
    "evidence_paths": (
        re.compile(r"^docs/audits/prd-v8-full-migration/[^/]+\.md$"),
        re.compile(r"^docs/training/DECISION-[^/]+\.md$"),
        re.compile(r"^docs/architecture/prd-v7-migration-map\.md$"),
        re.compile(r"^theories/[^/]+\.json$"),
        re.compile(r"^packages/ntruth/conformance/assets/[^/]+\.json$"),
        re.compile(r"^apps/desktop/src/test-fixtures/[^/]+\.json$"),
    ),
}


@dataclass(frozen=True)
class CurrentTargetMapValidation:
    valid: bool
    diagnostics: tuple[str, ...]
    base_sha: str
    target_contract: str
    component_ids: tuple[str, ...]


class _DuplicateObjectKeyError(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise _DuplicateObjectKeyError(key)
        decoded[key] = value
    return decoded


def _string_list(value: Any, *, field: str, component_id: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{component_id}.{field} must be a non-empty string list")
    if len(set(value)) != len(value):
        raise ValueError(f"{component_id}.{field} must contain unique strings")
    return tuple(value)


def _path_role_diagnostic(relative: str, *, field: str, component_id: str) -> str | None:
    if field == "current_paths" and ("/test-fixtures/" in relative or ".test." in relative):
        return f"{component_id}.{field} has non-implementation path: {relative}"
    if any(pattern.fullmatch(relative) for pattern in PATH_ROLE_PATTERNS[field]):
        return None
    return f"{component_id}.{field} has non-{field.removesuffix('_paths')} path: {relative}"


def _component_descriptor_sha256(component: dict[str, Any]) -> str:
    descriptor = {field: component.get(field) for field in COMPONENT_DESCRIPTOR_FIELDS}
    blob = json.dumps(
        descriptor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _public_api_diagnostic(reference: str, *, component_id: str) -> str | None:
    if reference.startswith("python:"):
        parts = reference.split(":", maxsplit=2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            return f"{component_id}.public_api has malformed Python reference: {reference}"
        module_name, qualified_name = parts[1:]
        try:
            value: object = importlib.import_module(module_name)
            for attribute in qualified_name.split("."):
                if not attribute or not hasattr(value, attribute):
                    return f"{component_id}.public_api does not resolve: {reference}"
                value = getattr(value, attribute)
        except (ImportError, RuntimeError, ValueError) as exc:
            return f"{component_id}.public_api cannot import {reference}: {exc}"
        return None
    if reference.startswith("http:"):
        parts = reference.split(":", maxsplit=2)
        if len(parts) != 3 or parts[1] not in HTTP_METHODS or not parts[2].startswith("/"):
            return f"{component_id}.public_api has malformed HTTP reference: {reference}"
        try:
            from ntruth.api.app import create_app

            routes = {
                (method, route.path)
                for route in create_app().routes
                for method in (getattr(route, "methods", None) or ())
            }
        except Exception as exc:
            return f"{component_id}.public_api cannot inspect HTTP routes: {exc}"
        if (parts[1], parts[2]) not in routes:
            return f"{component_id}.public_api route does not exist: {reference}"
        return None
    return (
        f"{component_id}.public_api must use python:<module>:<qualname> or "
        f"http:<METHOD>:</path>: {reference}"
    )


def validate_current_target_map(path: Path, *, repository_root: Path) -> CurrentTargetMapValidation:
    diagnostics: list[str] = []
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
        )
    except _DuplicateObjectKeyError as exc:
        return CurrentTargetMapValidation(
            valid=False,
            diagnostics=(f"architecture map contains duplicate object key: {exc.key}",),
            base_sha="",
            target_contract="",
            component_ids=(),
        )
    except (OSError, json.JSONDecodeError) as exc:
        return CurrentTargetMapValidation(
            valid=False,
            diagnostics=(f"architecture map is not readable JSON/YAML: {exc}",),
            base_sha="",
            target_contract="",
            component_ids=(),
        )
    if not isinstance(payload, dict):
        return CurrentTargetMapValidation(
            False, ("architecture map root must be an object",), "", "", ()
        )

    root_fields = set(payload)
    if missing_root_fields := sorted(ARCHITECTURE_MAP_ROOT_FIELDS - root_fields):
        diagnostics.append(
            "architecture map missing root fields: " + ", ".join(missing_root_fields)
        )
    if unexpected_root_fields := sorted(root_fields - ARCHITECTURE_MAP_ROOT_FIELDS):
        diagnostics.append(
            "architecture map has unexpected root fields: " + ", ".join(unexpected_root_fields)
        )
    for field, expected in ARCHITECTURE_MAP_ROOT_LITERALS.items():
        if field in payload and payload[field] != expected:
            diagnostics.append(f"architecture map {field} does not match its reviewed literal")

    base_sha_value = payload.get("base_sha", "")
    base_sha = base_sha_value if isinstance(base_sha_value, str) else ""
    target_contract_value = payload.get("target_contract", "")
    target_contract = target_contract_value if isinstance(target_contract_value, str) else ""

    register_path = (
        repository_root
        / "docs"
        / "audits"
        / "prd-v8-full-migration"
        / "SCIENTIFIC_REVIEW_REGISTER.md"
    )
    try:
        registered_blockers = frozenset(
            REGISTER_ROW_RE.findall(register_path.read_text(encoding="utf-8"))
        )
    except OSError as exc:
        diagnostics.append(f"scientific review register is not readable: {exc}")
        registered_blockers = frozenset()

    # Component rows are a keyed semantic set; their array order is intentionally non-semantic.
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        diagnostics.append("architecture map components must be a non-empty list")
        components = []
    component_ids: list[str] = []
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            diagnostics.append(f"component[{index}] must be an object")
            continue
        missing = REQUIRED_COMPONENT_FIELDS - set(component)
        unexpected = set(component) - REQUIRED_COMPONENT_FIELDS
        component_id = component.get("component_id", f"component[{index}]")
        if not isinstance(component_id, str) or not component_id.strip():
            diagnostics.append(f"component[{index}].component_id must be non-blank")
            continue
        component_ids.append(component_id)
        if missing:
            diagnostics.append(f"{component_id} missing fields: {sorted(missing)}")
        if unexpected:
            diagnostics.append(f"{component_id} has unexpected fields: {sorted(unexpected)}")
        expected_descriptor_sha256 = CANONICAL_COMPONENT_DESCRIPTOR_SHA256.get(component_id)
        if expected_descriptor_sha256 is not None and (
            _component_descriptor_sha256(component) != expected_descriptor_sha256
        ):
            diagnostics.append(
                f"{component_id} descriptor does not match its reviewed content anchor"
            )
        if component.get("status") not in MAP_STATUSES:
            diagnostics.append(f"{component_id}.status is not a PRD migration status")
        for scalar in ("target", "owner"):
            if not isinstance(component.get(scalar), str) or not component[scalar].strip():
                diagnostics.append(f"{component_id}.{scalar} must be non-blank")
        try:
            public_api = _string_list(
                component.get("public_api"), field="public_api", component_id=component_id
            )
            diagnostics.extend(
                diagnostic
                for reference in public_api
                if (diagnostic := _public_api_diagnostic(reference, component_id=component_id))
                is not None
            )
            blockers = component.get("blocker_ids")
            if not isinstance(blockers, list) or any(
                not isinstance(item, str) or BLOCKER_RE.fullmatch(item) is None for item in blockers
            ):
                diagnostics.append(f"{component_id}.blocker_ids contains a non-canonical ID")
            elif unknown_blockers := sorted(set(blockers) - registered_blockers):
                diagnostics.append(
                    f"{component_id}.blocker_ids contains unregistered IDs: "
                    + ", ".join(unknown_blockers)
                )
            for field in PATH_FIELDS:
                for relative in _string_list(
                    component.get(field), field=field, component_id=component_id
                ):
                    if diagnostic := _path_role_diagnostic(
                        relative, field=field, component_id=component_id
                    ):
                        diagnostics.append(diagnostic)
                    candidate = (repository_root / relative).resolve()
                    try:
                        candidate.relative_to(repository_root.resolve())
                    except ValueError:
                        diagnostics.append(f"{component_id}.{field} escapes repository: {relative}")
                        continue
                    if not candidate.is_file():
                        diagnostics.append(f"{component_id}.{field} missing path: {relative}")
        except ValueError as exc:
            diagnostics.append(str(exc))
    if len(set(component_ids)) != len(component_ids):
        diagnostics.append("architecture map component_id values must be unique")
    component_id_set = set(component_ids)
    if missing_components := sorted(CANONICAL_COMPONENT_IDS - component_id_set):
        diagnostics.append(
            "architecture map missing canonical components: " + ", ".join(missing_components)
        )
    if unexpected_components := sorted(component_id_set - CANONICAL_COMPONENT_IDS):
        diagnostics.append(
            "architecture map has unexpected components: " + ", ".join(unexpected_components)
        )

    return CurrentTargetMapValidation(
        valid=not diagnostics,
        diagnostics=tuple(diagnostics),
        base_sha=base_sha,
        target_contract=target_contract,
        component_ids=tuple(component_ids),
    )


__all__ = [
    "CANONICAL_COMPONENT_DESCRIPTOR_SHA256",
    "CANONICAL_COMPONENT_IDS",
    "MAP_STATUSES",
    "CurrentTargetMapValidation",
    "validate_current_target_map",
]
