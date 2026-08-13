"""GOLD-pilot contracts. No record is declared NTRUTH_GOLD here.

Quantity is not invented. Promotion requires human-closure inputs that this
module never synthesizes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.task_corpora.authority import AuthorityLevel

REQUIRED_SPLIT_KEYS: tuple[str, ...] = (
    "experiment_bundle_id",
    "paper_id",
    "version",
    "laboratory",
    "semantic_family",
)

DECISIVE_REVIEW_FIELDS: tuple[str, ...] = (
    "FactorRole",
    "ContrastType",
    "ContrastSupportClaim",
    "ObservedEvidenceScope",
    "ExperimentalUnitClaim",
)


class GoldPilotStatus(StrEnum):
    OPEN = "OPEN"
    DUAL_ANNOTATION_IN_PROGRESS = "DUAL_ANNOTATION_IN_PROGRESS"
    AGREEMENT_MEASURED = "AGREEMENT_MEASURED"
    ADJUDICATION_PENDING = "ADJUDICATION_PENDING"
    ADJUDICATION_RECORDED = "ADJUDICATION_RECORDED"
    DECISIVE_REVIEW_PENDING = "DECISIVE_REVIEW_PENDING"
    PILOT_COMPLETE_NOT_GOLD = "PILOT_COMPLETE_NOT_GOLD"


class AmbiguousAnswer(StrEnum):
    INSUFFICIENT = "insufficiente"
    INDETERMINATE = "indeterminata"
    VALUE = "value"


class IndependentAnnotation(FrozenModel):
    annotator_role: str
    annotation_id: str
    payload: dict[str, Any]
    ambiguous: AmbiguousAnswer
    created_at: str

    @model_validator(mode="after")
    def _identity(self) -> IndependentAnnotation:
        if not self.annotator_role.strip() or not self.annotation_id.strip():
            raise ValueError("independent annotation requires role and id")
        return self


class AgreementReport(FrozenModel):
    measured_before_adjudication: Literal[True] = True
    pair: tuple[str, str]
    observed_agreement: float = Field(ge=0.0, le=1.0)
    decisive_field_disagreements: tuple[str, ...] = ()
    measured_at: str


class AdjudicationRecord(FrozenModel):
    adjudication_id: str
    adjudicator_role: str
    rationale: str
    resolution: dict[str, Any]
    recorded_at: str

    @model_validator(mode="after")
    def _traced(self) -> AdjudicationRecord:
        if not self.rationale.strip():
            raise ValueError("adjudication must be traced with rationale")
        if not self.adjudication_id.strip():
            raise ValueError("adjudication_id required")
        return self


class DecisiveFieldReview(FrozenModel):
    fields_reviewed: tuple[str, ...]
    reviewer_role: str
    complete: bool
    reviewed_at: str

    @model_validator(mode="after")
    def _mandatory(self) -> DecisiveFieldReview:
        missing = [name for name in DECISIVE_REVIEW_FIELDS if name not in self.fields_reviewed]
        if missing and self.complete:
            raise ValueError(f"decisive review incomplete: {missing}")
        return self


class SplitKeys(FrozenModel):
    experiment_bundle_id: str
    paper_id: str
    version: str
    laboratory: str
    semantic_family: str

    @model_validator(mode="after")
    def _all_present(self) -> SplitKeys:
        for name in REQUIRED_SPLIT_KEYS:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"split key missing: {name}")
        return self


class ProvenanceBundle(FrozenModel):
    source_id: str
    source_asset_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license_or_authorization_id: str
    guideline_version: str


class HumanClosureInputs(FrozenModel):
    steward_signed_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    steward_role: str
    closed_at: str


class GoldPilotRecord(FrozenModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_type: Literal["ntruth-gold-pilot-record"] = "ntruth-gold-pilot-record"
    record_id: str
    status: GoldPilotStatus
    authority_level: AuthorityLevel = AuthorityLevel.CANDIDATE
    annotations: tuple[IndependentAnnotation, ...]
    agreement: AgreementReport | None = None
    adjudication: AdjudicationRecord | None = None
    decisive_review: DecisiveFieldReview | None = None
    provenance: ProvenanceBundle
    split_keys: SplitKeys
    rights_eligible: bool = False
    gold_quantity_declared: Literal[None] = None

    @model_validator(mode="after")
    def _never_gold(self) -> GoldPilotRecord:
        if self.authority_level is AuthorityLevel.NTRUTH_GOLD:
            raise ValueError("GOLD-pilot machinery cannot set AuthorityLevel.NTRUTH_GOLD")
        if self.gold_quantity_declared is not None:
            raise ValueError("GOLD quantity must not be invented")
        if self.status is GoldPilotStatus.AGREEMENT_MEASURED and self.agreement is None:
            raise ValueError("agreement must be measured before adjudication")
        if self.adjudication is not None and self.agreement is None:
            raise ValueError("adjudication requires pre-adjudication agreement")
        if (
            self.agreement is not None
            and not self.agreement.measured_before_adjudication
        ):
            raise ValueError("agreement must be measured before adjudication")
        if len({item.annotator_role for item in self.annotations}) < 2 and self.status not in {
            GoldPilotStatus.OPEN,
            GoldPilotStatus.DUAL_ANNOTATION_IN_PROGRESS,
        }:
            raise ValueError("dual independent annotation required")
        if (
            len(self.annotations) >= 2
            and {item.annotator_role for item in self.annotations.__iter__()}
            and len({item.annotation_id for item in self.annotations}) < 2
        ):
            raise ValueError("independent annotations must not share annotation_id")
        return self


def measure_agreement(
    first: IndependentAnnotation,
    second: IndependentAnnotation,
    *,
    measured_at: str,
) -> AgreementReport:
    if first.annotator_role == second.annotator_role:
        raise ValueError("agreement requires independent annotators")
    if first.annotation_id == second.annotation_id:
        raise ValueError("agreement requires distinct annotation records")
    disagreements = tuple(
        sorted(
            key
            for key in DECISIVE_REVIEW_FIELDS
            if first.payload.get(key) != second.payload.get(key)
        )
    )
    compared = len(DECISIVE_REVIEW_FIELDS)
    observed = (compared - len(disagreements)) / compared
    return AgreementReport(
        pair=(first.annotation_id, second.annotation_id),
        observed_agreement=observed,
        decisive_field_disagreements=disagreements,
        measured_at=measured_at,
    )


def evaluate_gold_promotion(
    record: GoldPilotRecord,
    human_closure: HumanClosureInputs | None = None,
) -> dict[str, Any]:
    """Never writes NTRUTH_GOLD without human-closure inputs.

    Even with a well-formed closure object, this tranche does not auto-promote:
    a human steward must write GOLD outside any automatic path.
    """

    if human_closure is None:
        return {
            "promoted": False,
            "authority_level": record.authority_level.value,
            "reason": "missing_human_closure",
        }
    if not human_closure.steward_role.strip() or not human_closure.closed_at.strip():
        return {
            "promoted": False,
            "authority_level": record.authority_level.value,
            "reason": "incomplete_human_closure",
        }
    return {
        "promoted": False,
        "authority_level": record.authority_level.value,
        "reason": "human_steward_must_write_gold_outside_auto_path",
        "closure_checksum": content_checksum(human_closure.model_dump(mode="json")),
    }


def split_key_payload(keys: SplitKeys) -> dict[str, str]:
    return {name: getattr(keys, name) for name in REQUIRED_SPLIT_KEYS}
