"""Per-asset rights, DUA, redistribution and training/evaluation use.

Incomplete licence, DUA, redistribution, use grant, or paper/experiment/family
identity keeps a record non-eligible. ``unknown`` fails closed for that use.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import model_validator

from ntruth.schemas.core import FrozenModel

RIGHTS_SCHEMA_VERSION = "1.0.0"
CANONICAL_SOURCES: tuple[str, ...] = ("SourceData", "PreClinIE", "MeasEval", "CRAFT")
REQUIRED_IDENTITY_FIELDS: tuple[str, ...] = (
    "paper_id",
    "experiment_id",
    "family_id",
)

PermissionTriState = bool | Literal["unknown"]


class RightsReviewStatus(StrEnum):
    LICENSE_REVIEW_REQUIRED = "LICENSE_REVIEW_REQUIRED"
    LICENSE_SCOPE_VERIFIED = "LICENSE_SCOPE_VERIFIED"
    DUA_REQUIRED = "DUA_REQUIRED"
    INCOMPLETE = "INCOMPLETE"


class UseGrant(FrozenModel):
    training: PermissionTriState = "unknown"
    evaluation: PermissionTriState = "unknown"
    development: PermissionTriState = "unknown"
    redistribution: PermissionTriState = "unknown"
    dua_required: bool = True
    dua_on_file: bool = False


class StableIdentity(FrozenModel):
    paper_id: str | None = None
    experiment_id: str | None = None
    family_id: str | None = None
    source_asset_id: str
    source_ref: str

    def complete(self) -> bool:
        return all(
            isinstance(getattr(self, name), str) and str(getattr(self, name)).strip()
            for name in REQUIRED_IDENTITY_FIELDS
        )


class AssetRightsRecord(FrozenModel):
    schema_version: Literal["1.0.0"] = RIGHTS_SCHEMA_VERSION
    source: str
    asset_id: str
    license_spdx: str | None = None
    license_status: str
    license_note: str
    dua: UseGrant
    identity: StableIdentity
    review_status: RightsReviewStatus
    steward_authorization: Literal[None] = None
    training_eligible: bool = False
    evaluation_eligible: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _fail_closed(self) -> AssetRightsRecord:
        blockers = compute_rights_blockers(self)
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "training_eligible", False)
        object.__setattr__(self, "evaluation_eligible", False)
        if self.steward_authorization is not None:
            raise ValueError("rights records cannot self-authorize")
        return self


def _grant_blocks(name: str, value: PermissionTriState) -> str | None:
    if value is True:
        return None
    if value == "unknown":
        return f"{name}_unknown"
    return f"{name}_forbidden"


def compute_rights_blockers(record: AssetRightsRecord) -> tuple[str, ...]:
    blockers: list[str] = []
    if not record.license_spdx or record.license_status in {
        "UNKNOWN",
        "LICENSE_REVIEW_REQUIRED",
        "INCOMPLETE",
    }:
        blockers.append("license_incomplete")
    if record.dua.dua_required and not record.dua.dua_on_file:
        blockers.append("dua_missing")
    for use in ("training", "evaluation", "development", "redistribution"):
        blocked = _grant_blocks(use, getattr(record.dua, use))
        if blocked:
            blockers.append(blocked)
    if not record.identity.complete():
        blockers.append("identity_incomplete")
    if record.review_status is not RightsReviewStatus.LICENSE_SCOPE_VERIFIED:
        blockers.append("review_not_closed")
    if record.steward_authorization is None:
        blockers.append("steward_authorization_absent")
    return tuple(dict.fromkeys(blockers))


def record_is_eligible(record: AssetRightsRecord, *, use: Literal["training", "evaluation"]) -> bool:
    if record.blockers:
        return False
    grant = record.dua.training if use == "training" else record.dua.evaluation
    return grant is True


def rights_catalog_dir() -> Path:
    return Path(__file__).resolve().parent / "source_rights"


@lru_cache(maxsize=1)
def load_source_rights() -> dict[str, AssetRightsRecord]:
    catalog: dict[str, AssetRightsRecord] = {}
    for path in sorted(rights_catalog_dir().glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = AssetRightsRecord.model_validate(payload)
        catalog[record.source] = record
    missing = [name for name in CANONICAL_SOURCES if name not in catalog]
    if missing:
        raise ValueError(f"missing per-source rights records: {missing}")
    return catalog


def rights_for_source(source: str) -> AssetRightsRecord:
    return load_source_rights()[source]


def evaluate_record_eligibility(
    source: str,
    *,
    identity: Mapping[str, Any] | None = None,
) -> tuple[bool, tuple[str, ...]]:
    base = rights_for_source(source)
    if identity is None:
        return False, base.blockers
    merged = base.model_copy(
        update={
            "identity": StableIdentity(
                paper_id=identity.get("paper_id"),
                experiment_id=identity.get("experiment_id"),
                family_id=identity.get("family_id"),
                source_asset_id=str(identity.get("source_asset_id") or base.identity.source_asset_id),
                source_ref=str(identity.get("source_ref") or base.identity.source_ref),
            )
        }
    )
    blockers = compute_rights_blockers(merged)
    return (not blockers), blockers
