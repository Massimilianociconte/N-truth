"""Machine-readable current-to-target architecture truth for PRD v8.

The map is stored as JSON syntax in a ``.yaml`` file. JSON is a YAML 1.2 subset,
which keeps the clean-checkout gate dependency-free and deterministic.
"""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAP_STATUSES = frozenset({"IMPLEMENTED", "PARTIAL", "MISSING", "INCOMPATIBLE", "LEGACY"})
CANONICAL_COMPONENT_IDS = frozenset(
    {
        "canonical-count-registry",
        "core-semantic-kernel",
        "corrections-rederivation",
        "coverage-contracts",
        "derivation-theory",
        "desktop-v8",
        "evaluation-residual-cluster",
        "event-causal-context",
        "experiment-block-boundary",
        "external-challenge-custody",
        "graph-equality",
        "guided-quick-design-v8",
        "ingest-safety",
        "orthogonal-evidence-support",
        "parser-candidate-boundary",
        "planned-executed-reporting",
        "prd-examples-and-schema",
        "protected-training-boundary",
        "query-scoped-claims",
        "reality-gate-v8",
        "repository-contract-truth",
        "rulebook-conformance",
        "statistical-handoff",
        "v7-compatibility",
        "v7-to-v8-migrations",
    }
)
REQUIRED_COMPONENT_FIELDS = frozenset(
    {
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
    }
)
PATH_FIELDS = ("current_paths", "adr_paths", "test_paths", "evidence_paths")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
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
        payload = json.loads(path.read_text(encoding="utf-8"))
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

    base_sha = payload.get("base_sha", "")
    target_contract = payload.get("target_contract", "")
    if payload.get("schema_version") != "8.0.0":
        diagnostics.append("architecture map schema_version must be 8.0.0")
    if not isinstance(base_sha, str) or SHA_RE.fullmatch(base_sha) is None:
        diagnostics.append("architecture map base_sha must be a 40-character lowercase SHA")
        base_sha = ""
    if target_contract != "N-Truth PRD v8.0":
        diagnostics.append("architecture map target_contract must be N-Truth PRD v8.0")
        target_contract = str(target_contract)

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
        component_id = component.get("component_id", f"component[{index}]")
        if not isinstance(component_id, str) or not component_id.strip():
            diagnostics.append(f"component[{index}].component_id must be non-blank")
            continue
        component_ids.append(component_id)
        if missing:
            diagnostics.append(f"{component_id} missing fields: {sorted(missing)}")
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
    "CANONICAL_COMPONENT_IDS",
    "MAP_STATUSES",
    "CurrentTargetMapValidation",
    "validate_current_target_map",
]
