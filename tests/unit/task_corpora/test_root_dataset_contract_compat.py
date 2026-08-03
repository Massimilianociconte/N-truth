"""Root ↔ dataset contract compatibility (PRD v7; no FLASH128 rebuild)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from ntruth.cross_domain import DataRole, decide_cross_domain_role
from ntruth.cross_domain.roles import AnnotationAuthority, GoldEligibility
from ntruth.reality_gate import DataReadiness, ScientificValidation
from ntruth.reality_gate.predicates import GateValue
from ntruth.task_corpora.authority import AuthorityLevel, LicenseStatus
from ntruth.task_corpora.config import FORBIDDEN_GOLD_USES, ROOT_REALITY_GATE_REF
from ntruth.task_corpora.readiness import (
    CANONICAL_FORBIDDEN_GOLD_USES,
    assert_projection_cannot_claim_scientific_readiness,
    forbidden_gold_uses_are_canonical_superset,
    project_sourcedata_c0_c1,
    role_decision_pending_model_use_allowed,
)
from ntruth.task_corpora.schemas import (
    EntityRolesPayload,
    LicenseUseDecision,
    SourceIdentity,
    TaskRecord,
    TransformLineage,
)

REPO = Path(__file__).resolve().parents[3]
TASK_CORPORA = REPO / "packages" / "ntruth" / "task_corpora"


def _minimal_task_record(**overrides: object) -> TaskRecord:
    data: dict[str, object] = {
        "record_id": "r1",
        "task_type": "entity_roles",
        "source": SourceIdentity(
            dataset="SourceData",
            version="2.0.3",
            commit="deadbeef",
            document_id="",
            segment_id="seg-1",
            source_record_id="src-1",
        ),
        "split": "train",
        "split_authority": "UPSTREAM_SOURCEDATA",
        "leakage_group": "src-1",
        "supervision_source": "STRUCTURED_METADATA",
        "authority_level": AuthorityLevel.AUXILIARY,
        "allowed_uses": ["adapter_development"],
        "forbidden_uses": list(FORBIDDEN_GOLD_USES),
        "licence": LicenseUseDecision(
            license_status=LicenseStatus.RESTRICTED,
            training_allowed=False,
            redistribution_allowed=False,
            derived_labels_allowed=True,
            decision_basis="test",
            reviewed_at="2026-08-03",
            development_allowed=False,
            evaluation_allowed="unknown",
        ),
        "training_eligible": False,
        "evaluation_eligible": False,
        "requires_review": False,
        "transform_lineage": TransformLineage(
            adapter="sourcedata_entity_roles",
            transform_version="0.2.0",
            parent_path="x",
            parent_checksum="abc",
            mapping_version="0.1.0",
        ),
        "checksum": "c" * 64,
        "payload": EntityRolesPayload(
            tokens=["a", "b"],
            entity_labels=["O", "O"],
            role_labels=["O", "O"],
        ),
    }
    data.update(overrides)
    return TaskRecord.model_validate(data)


def test_projection_blocks_real_anchor_and_readiness() -> None:
    proj = project_sourcedata_c0_c1()
    assert proj.real_anchor_available is GateValue.FALSE
    assert proj.data_readiness is DataReadiness.BLOCKED
    assert proj.scientific_validation is ScientificValidation.NOT_STARTED
    assert proj.reality_gate_status == "BLOCKED"
    assert proj.substantive_training_allowed is False
    assert proj.ai_claims_allowed is False
    assert proj.reality_gate_satisfied_by_public_corpora is False
    assert proj.reality_gate_satisfied_by_silver_adapter is False
    assert_projection_cannot_claim_scientific_readiness(proj)


def test_engineering_status_cannot_set_data_ready() -> None:
    proj = project_sourcedata_c0_c1(engineering_component_status="VERIFIED_FOR_C0_C1")
    assert proj.engineering_component_status == "VERIFIED_FOR_C0_C1"
    assert proj.data_readiness is not DataReadiness.READY


def test_silver_cannot_set_scientific_validation_via_projection() -> None:
    proj = project_sourcedata_c0_c1()
    with pytest.raises(ValueError, match="scientific_validation"):
        bad = proj.model_copy(update={"scientific_validation": ScientificValidation.VALIDATED})
        assert_projection_cannot_claim_scientific_readiness(bad)


def test_role_decision_pending_not_model_use_eligible() -> None:
    assert role_decision_pending_model_use_allowed() is False


def test_cross_profile_gold_rejected_via_root_policy() -> None:
    decision = decide_cross_domain_role(
        source_domain="in_vivo",
        source_profile="animal",
        target_profile="simple_cell_culture",
        annotation_authority=AnnotationAuthority(
            role="domain_expert", protocol_id="p1", decisive_fields_second_review=True
        ),
        licence_use_decision="verified",
        preferred_role=DataRole.GOLD,
        gold_eligibility=GoldEligibility(
            complete_provenance=True,
            decisive_fields_second_review=True,
            expert_adjudication=True,
            approved_gold_protocol=True,
            split_leakage_clear=True,
        ),
    )
    assert DataRole.GOLD in decision.forbidden_roles
    assert decision.chosen_role is not DataRole.GOLD


def test_unknown_licence_blocks_training_eligible() -> None:
    with pytest.raises(ValidationError):
        _minimal_task_record(
            licence=LicenseUseDecision(
                license_status=LicenseStatus.UNKNOWN,
                training_allowed=True,
                redistribution_allowed=False,
                derived_labels_allowed=True,
                decision_basis="x",
                reviewed_at="2026-08-03",
                development_allowed=True,
                evaluation_allowed=True,
            ),
            training_eligible=True,
        )


def test_test_split_cannot_be_training_eligible() -> None:
    with pytest.raises(ValidationError):
        _minimal_task_record(split="test", training_eligible=True)


def test_sourcedata_forbidden_gold_superset_of_canonical() -> None:
    assert forbidden_gold_uses_are_canonical_superset(FORBIDDEN_GOLD_USES)
    assert set(CANONICAL_FORBIDDEN_GOLD_USES).issubset(set(FORBIDDEN_GOLD_USES))


def test_record_level_fallback_cannot_claim_paper_level() -> None:
    proj = project_sourcedata_c0_c1(leakage_group_granularity="RECORD_LEVEL_FALLBACK")
    assert proj.paper_level_leakage_claim_allowed is False
    assert "RECORD_LEVEL_FALLBACK" in " ".join(proj.blockers)


def test_missing_root_mapping_fails_closed_for_claims() -> None:
    proj = project_sourcedata_c0_c1()
    fields = proj.as_manifest_fields()
    assert fields["data_readiness"] == "BLOCKED"
    assert fields["scientific_validation"] == "NOT_STARTED"
    assert fields["reality_gate_status"] == "BLOCKED"


def test_task_corpora_ast_does_not_import_parser_ai_or_model_backends() -> None:
    forbidden = ("parser_ai", "model_backends", "mlx_runtime", "training.mlx")
    hits: list[str] = []
    for path in TASK_CORPORA.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(f in alias.name for f in forbidden):
                        hits.append(f"{path.name}:{alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and any(f in node.module for f in forbidden)
            ):
                hits.append(f"{path.name}:{node.module}")
    assert hits == []


def test_root_reality_gate_ref_points_at_merge() -> None:
    assert ROOT_REALITY_GATE_REF.startswith("reality_gate@main:f2faace")


def test_auxiliary_must_list_forbidden_gold_uses() -> None:
    with pytest.raises(ValidationError):
        _minimal_task_record(forbidden_uses=["encoder_pretraining"])  # missing gold bans
