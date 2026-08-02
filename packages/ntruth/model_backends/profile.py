"""Caricamento e validazione della config tecnica Granite (senza stato operativo)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ntruth.model_backends.constants import GRANITE_MLX_PROFILE_FILENAME

# Fields that must not appear (qualification belongs to registry).
_FORBIDDEN_OPERATIONAL_KEYS = frozenset(
    {
        "runtime_qualification_status",
        "scientific_validation_status",
        "migration_status",
        "qualified_artifact",
        "verification_status",
    }
)


class ProfileValidationError(ValueError):
    pass


def default_granite_profile_path(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[3]
    return root / "models" / "configs" / GRANITE_MLX_PROFILE_FILENAME


def load_backend_profile(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProfileValidationError("profile root must be a JSON object")
    validate_backend_profile(data)
    return data


def validate_backend_profile(data: dict[str, Any]) -> None:
    """Reject operational qualification fields; require load-relevant model keys."""

    model = data.get("model")
    if not isinstance(model, dict):
        raise ProfileValidationError("profile.model object required")

    for key in _FORBIDDEN_OPERATIONAL_KEYS:
        if key in data or key in model:
            raise ProfileValidationError(
                f"operational status field {key!r} not allowed in backend profile; "
                "use models/registry (cluster 2) for qualification"
            )

    required = ("canonical_repository", "repository", "local_path")
    missing = [k for k in required if not model.get(k)]
    if missing:
        raise ProfileValidationError(f"profile.model missing: {missing}")


__all__ = [
    "ProfileValidationError",
    "default_granite_profile_path",
    "load_backend_profile",
    "validate_backend_profile",
]
