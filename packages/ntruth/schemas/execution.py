"""Content-addressed execution pins for the deterministic PRD v8 lane."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ntruth.schemas.claims import IrrelevantPredicate
from ntruth.schemas.kernel import KernelModel, NonBlankStr

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ImplementationRulePin(KernelModel):
    theory_id: NonBlankStr
    theory_version: NonBlankStr
    theory_checksum: Sha256
    rule_id: NonBlankStr
    rule_version: NonBlankStr
    rule_checksum: Sha256
    theory_clause_id: NonBlankStr
    theory_clause_version: NonBlankStr
    implementation_artifact_id: NonBlankStr
    implementation_artifact_version: NonBlankStr
    implementation_artifact_checksum: Sha256
    required_predicate_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    irrelevant_predicates: tuple[IrrelevantPredicate, ...] = Field(min_length=1)


class AdequacyEvaluatorPin(KernelModel):
    theory_id: NonBlankStr
    theory_version: NonBlankStr
    theory_checksum: Sha256
    theory_clause_id: NonBlankStr
    theory_clause_version: NonBlankStr
    rule_id: NonBlankStr
    rule_version: NonBlankStr
    rule_checksum: Sha256
    implementation_artifact_id: NonBlankStr
    implementation_artifact_version: NonBlankStr
    implementation_artifact_checksum: Sha256


class V8ExecutionManifest(KernelModel):
    manifest_id: NonBlankStr
    theory_id: NonBlankStr
    theory_version: NonBlankStr
    theory_checksum: Sha256
    rulebook_id: NonBlankStr
    rulebook_version: NonBlankStr
    rulebook_checksum: Sha256
    profile_closure_asset_id: NonBlankStr
    profile_closure_asset_version: NonBlankStr
    profile_closure_checksum: Sha256
    reference_registry_id: NonBlankStr
    reference_registry_version: NonBlankStr
    reference_registry_checksum: Sha256
    fixture_set_id: NonBlankStr
    fixture_set_version: NonBlankStr
    fixture_set_checksum: Sha256
    implementation_rules: tuple[ImplementationRulePin, ...] = Field(min_length=7)
    adequacy_evaluator: AdequacyEvaluatorPin
    release_blocker_issue_ids: tuple[NonBlankStr, ...]


__all__ = ["AdequacyEvaluatorPin", "ImplementationRulePin", "V8ExecutionManifest"]
