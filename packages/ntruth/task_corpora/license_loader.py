"""Load machine-readable licence / training-use decisions."""

from __future__ import annotations

import json

from ntruth.task_corpora.config import package_dir
from ntruth.task_corpora.schemas import LicenseUseDecision, PermissionFlag


class LicenseDecisionError(RuntimeError):
    """Missing or invalid licence decision file."""


def load_license_decision(dataset_key: str) -> LicenseUseDecision:
    path = package_dir() / "license_decisions" / f"{dataset_key}.json"
    if not path.exists():
        raise LicenseDecisionError(f"missing licence decision: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    decision = LicenseUseDecision.model_validate(data)
    return decision


def permission_granted(flag: PermissionFlag) -> bool:
    """True only for explicit True; False and \"unknown\" fail closed."""
    return flag is True


def training_permitted(decision: LicenseUseDecision) -> bool:
    if decision.license_status.value == "UNKNOWN":
        return False
    return bool(
        decision.training_allowed
        and decision.derived_labels_allowed
        and permission_granted(decision.development_allowed)
    )


def evaluation_permitted(decision: LicenseUseDecision) -> bool:
    """Metrics / held-out scoring require explicit evaluation_allowed=true."""
    if decision.license_status.value == "UNKNOWN":
        return False
    return permission_granted(decision.evaluation_allowed)


def development_permitted(decision: LicenseUseDecision) -> bool:
    """Rule tuning / B0 iteration / non-weight development on the corpus."""
    if decision.license_status.value == "UNKNOWN":
        return False
    return permission_granted(decision.development_allowed)


def adapter_build_permitted(decision: LicenseUseDecision) -> bool:
    return bool(decision.adapter_build_allowed and decision.derived_labels_allowed)


def format_validation_permitted(decision: LicenseUseDecision) -> bool:
    return bool(decision.local_format_validation_allowed)
