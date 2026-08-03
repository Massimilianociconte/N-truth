"""Load machine-readable licence / training-use decisions."""

from __future__ import annotations

import json

from ntruth.task_corpora.config import package_dir
from ntruth.task_corpora.schemas import LicenseUseDecision


class LicenseDecisionError(RuntimeError):
    """Missing or invalid licence decision file."""


def load_license_decision(dataset_key: str) -> LicenseUseDecision:
    path = package_dir() / "license_decisions" / f"{dataset_key}.json"
    if not path.exists():
        raise LicenseDecisionError(f"missing licence decision: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    decision = LicenseUseDecision.model_validate(data)
    return decision


def training_permitted(decision: LicenseUseDecision) -> bool:
    if decision.license_status.value == "UNKNOWN":
        return False
    return bool(decision.training_allowed and decision.derived_labels_allowed)
