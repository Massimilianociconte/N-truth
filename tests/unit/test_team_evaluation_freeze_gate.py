"""Fail-closed regressions for the TEAM-EVAL-V0.1 mechanical freeze-kit."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ntruth.team_evaluation import (
    CaseGroupingLevel,
    CaseGroupingSpec,
    ClaimKind,
    ClaimPolicyRule,
    ClusterAwarenessDimension,
    ClusteredAnalysisPlan,
    ComplementarityBasis,
    DecisionRegion,
    DecisionRegionKind,
    ExperimentalDesign,
    ExperimentCondition,
    InitialJudgementCaptureSubset,
    LoggingContract,
    MissingDataRule,
    PreregistrationStatus,
    PrimaryOutcomeMetric,
    RandomizationSeedCommitment,
    ReferencePolicy,
    SecondaryOutcomeMetric,
    StoppingRule,
    StratificationFactor,
    StratificationSpec,
    TeamCondition,
    TeamEvaluationProtocolRecord,
    TeamMetricPreregistration,
    WashoutTrainingPeriod,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "team_evaluation_freeze_gate.py"
PROTOCOL_PATH = REPOSITORY_ROOT / "docs" / "team-evaluation-protocol-v0.1.md"

_SPEC = importlib.util.spec_from_file_location("team_evaluation_freeze_gate", SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
gate = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("team_evaluation_freeze_gate", gate)
_SPEC.loader.exec_module(gate)

ALL_ROLES: tuple[str, ...] = (
    "biostatistician-methodologist",
    "wet-lab-lead",
    "annotation-lead",
    "evaluation-custodian",
)
ROLE_INITIALS: dict[str, str] = {
    "biostatistician-methodologist": "BS",
    "wet-lab-lead": "WL",
    "annotation-lead": "AL",
    "evaluation-custodian": "EC",
}
SIGNED_DATE = "2026-09-01"


def _protocol_sha256(path: Path = PROTOCOL_PATH) -> str:
    return gate.sha256_of_bytes(path.read_bytes())


def _entry(role_token: str, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "role_token": role_token,
        "signed_name_initials": ROLE_INITIALS[role_token],
        "attested_at": SIGNED_DATE,
        "statement_ref": f"{role_token}: header freeze-commitment sentences",
    }
    entry.update(overrides)
    return entry


def _complete_entries() -> list[dict[str, Any]]:
    return [_entry(role) for role in ALL_ROLES]


def _bundle(
    attestations: list[dict[str, Any]],
    *,
    protocol_sha256: str | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bundle": "team-eval-freeze-attestations",
        "schema_version": "9.0.0",
        "protocol_id": "TEAM-EVAL-V0.1",
        "protocol_sha256": protocol_sha256 if protocol_sha256 else _protocol_sha256(),
        "status": "PREREGISTRATION_DRAFT",
        "attestations": attestations,
    }
    payload.update(extra_fields)
    return payload


def _verify_payload(bundle: dict[str, Any]) -> gate.VerifiedBundle:
    return gate.verify_attestation_payload(
        bundle,
        expected_protocol_sha256=_protocol_sha256(),
        origin="test-bundle.json",
    )


def test_missing_bundle_file_blocks_freeze_naming_all_four_roles() -> None:
    absent = Path(REPOSITORY_ROOT / "tmp" / "does-not-exist-attestations.json")
    with pytest.raises(gate.FreezeGateError) as excinfo:
        gate.verify_attestation_file(absent, protocol_path=PROTOCOL_PATH)
    message = str(excinfo.value)
    assert "freeze blocked: no attestations provided" in message
    for role in ALL_ROLES:
        assert role in message


def test_partial_coverage_names_the_missing_human_role() -> None:
    partial = [
        entry for entry in _complete_entries() if entry["role_token"] != "evaluation-custodian"
    ]
    with pytest.raises(gate.FreezeGateError) as excinfo:
        _verify_payload(_bundle(partial))
    message = str(excinfo.value)
    assert "no valid attestation coverage for 1 human role attestation" in message
    assert "evaluation-custodian" in message


def test_duplicate_role_and_duplicate_signer_are_rejected() -> None:
    duplicated_role = [
        _entry("biostatistician-methodologist"),
        _entry("biostatistician-methodologist"),
        _entry("wet-lab-lead"),
        _entry("annotation-lead"),
    ]
    with pytest.raises(gate.FreezeGateError) as excinfo:
        _verify_payload(_bundle(duplicated_role))
    assert "attests twice" in str(excinfo.value)

    duplicated_signer = [
        _entry(role) for role in ("biostatistician-methodologist", "wet-lab-lead")
    ] + [
        _entry("annotation-lead", signed_name_initials="BS"),
        _entry("evaluation-custodian"),
    ]
    with pytest.raises(gate.FreezeGateError) as excinfo:
        _verify_payload(_bundle(duplicated_signer))
    message = str(excinfo.value)
    assert "signs two roles" in message
    assert "four signers must be distinct" in message


@pytest.mark.parametrize(
    ("initials", "offence"),
    [
        ("mc", "lowercase"),
        ("M", "too short"),
        ("MARCCO", "longer than the initials pattern allows"),
        ("Marco Rossi", "personal-looking name"),
        ("marco@rossi.example", "email-like field"),
    ],
)
def test_malformed_or_personal_initials_fields_are_rejected(initials: str, offence: str) -> None:
    del offence  # only the enforced rejection matters; labels document intent
    tampered = [_entry(role) for role in ("biostatistician-methodologist", "wet-lab-lead")] + [
        _entry("annotation-lead", signed_name_initials=initials),
        _entry("evaluation-custodian"),
    ]
    with pytest.raises(gate.FreezeGateError) as excinfo:
        _verify_payload(_bundle(tampered))
    message = str(excinfo.value)
    assert "^[A-Z]{2,4}$" in message
    assert "OFF-repo" in message


def test_stale_protocol_hash_is_fail_closed() -> None:
    stale_sha256 = "a" * 64
    assert stale_sha256 != _protocol_sha256()
    with pytest.raises(gate.FreezeGateError) as excinfo:
        _verify_payload(_bundle(_complete_entries(), protocol_sha256=stale_sha256))
    message = str(excinfo.value)
    assert "stale or deviated bundle" in message
    assert "Re-run prepare-record" in message


@pytest.mark.parametrize("bad_date", ["2026-08-24", "not-a-date"])
def test_unacceptable_attestation_dates_are_rejected(bad_date: str) -> None:
    tampered = [_entry(role) for role in ("biostatistician-methodologist", "wet-lab-lead")] + [
        _entry("annotation-lead", attested_at=bad_date),
        _entry("evaluation-custodian"),
    ]
    with pytest.raises(gate.FreezeGateError) as excinfo:
        _verify_payload(_bundle(tampered))
    message = str(excinfo.value)
    if bad_date.startswith("2026-08-24"):
        assert "predates the protocol draft date" in message
    else:
        assert "YYYY-MM-DD" in message


def test_prepare_record_pins_live_protocol_hash_deterministically() -> None:
    scaffold = gate.prepare_scaffold(PROTOCOL_PATH)
    again = gate.prepare_scaffold(PROTOCOL_PATH)
    assert scaffold == again
    canonical = json.dumps(scaffold, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert canonical == gate.canonical_json_blob(scaffold)
    assert scaffold["protocol_id"] == "TEAM-EVAL-V0.1"
    assert scaffold["status"] == "PREREGISTRATION_DRAFT"
    assert scaffold["protocol_sha256"] == _protocol_sha256()
    assert [item["role_token"] for item in scaffold["attestations"]] == list(ALL_ROLES)
    with pytest.raises(gate.FreezeGateError) as excinfo:
        _verify_payload(scaffold)
    message = str(excinfo.value)
    assert "freeze blocked" in message
    assert "evaluation-custodian" in message


# ---------------------------------------------------------------------------
# Draft-record fixture factory mirrored from tests/unit/test_team_evaluation_protocol.py.


PREREGISTERED_AT = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
SEED_COMMITTED_AT = datetime(2026, 7, 15, 9, 0, 0, tzinfo=UTC)


def _conditions() -> tuple[ExperimentCondition, ...]:
    return (
        ExperimentCondition(
            condition=TeamCondition.H,
            label="Human-only",
            workflow_spec="Reviewer completes the report without AI candidate output.",
        ),
        ExperimentCondition(
            condition=TeamCondition.A,
            label="AI-only diagnostic",
            workflow_spec="Candidate pipeline output, never presented as intended use.",
            diagnostic_only=True,
            ai_candidate_ref="candidate-pipeline-v0",
        ),
        ExperimentCondition(
            condition=TeamCondition.H_PLUS_A,
            label="Full human+AI workflow",
            workflow_spec="Reviewer works with candidate output, explanations and UI support.",
            ai_candidate_ref="candidate-pipeline-v0",
        ),
    )


def _metric_preregistrations() -> TeamMetricPreregistration:
    regions = (
        DecisionRegion(
            metric=PrimaryOutcomeMetric.DECISIVE_CLAIM_CORRECTNESS,
            kind=DecisionRegionKind.SUPERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
        ),
        DecisionRegion(
            metric=PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE,
            kind=DecisionRegionKind.NON_INFERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
            margin=Decimal("0.02"),
        ),
        DecisionRegion(
            metric=PrimaryOutcomeMetric.ACTIVE_REVIEW_TIME,
            kind=DecisionRegionKind.NON_INFERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
            margin=Decimal("300"),
        ),
        DecisionRegion(
            metric=PrimaryOutcomeMetric.UNRESOLVED_MATERIAL_GAP_DETECTION,
            kind=DecisionRegionKind.SUPERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
        ),
    )
    claim_policy = (
        ClaimPolicyRule(
            claim_kind=ClaimKind.TIME_SAVING,
            criterion_metric=PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE,
        ),
        ClaimPolicyRule(
            claim_kind=ClaimKind.SAFETY_ACCURACY_IMPROVEMENT,
            criterion_metric=PrimaryOutcomeMetric.DECISIVE_CLAIM_CORRECTNESS,
            comparator_condition=TeamCondition.H,
        ),
        ClaimPolicyRule(
            claim_kind=ClaimKind.COMPLEMENTARITY,
            complementarity_basis=ComplementarityBasis.EXCEEDS_BOTH_ON_PREREGISTERED_CRITERION,
            criterion_metric=PrimaryOutcomeMetric.UNRESOLVED_MATERIAL_GAP_DETECTION,
        ),
    )
    analysis_plan = ClusteredAnalysisPlan(
        clustered_by=(
            ClusterAwarenessDimension.PARTICIPANT,
            ClusterAwarenessDimension.CASE_FAMILY,
        ),
        estimation_description="Mixed-effects estimates per preregistered decision region.",
        uncertainty_description="Cluster-robust confidence intervals.",
    )
    return TeamMetricPreregistration(
        primary_outcomes=tuple(PrimaryOutcomeMetric),
        secondary_outcomes=tuple(SecondaryOutcomeMetric),
        decision_regions=regions,
        analysis_plan=analysis_plan,
        claim_policy=claim_policy,
    )


def _draft_record_json() -> str:
    protocol = TeamEvaluationProtocolRecord.model_validate(
        {
            "protocol_id": "TEAM-EVAL-V0.1",
            "status": PreregistrationStatus.PREREGISTRATION_DRAFT,
            "data_collection_started": False,
            "preregistered_at": PREREGISTERED_AT,
            "design": ExperimentalDesign.CROSSOVER_COUNTERBALANCED,
            "conditions": _conditions(),
            "stratification": StratificationSpec(
                factors=(StratificationFactor.ROLE, StratificationFactor.EXPERIENCE),
                stratum_labels=("staff-senior", "phd-junior"),
            ),
            "case_grouping": CaseGroupingSpec(
                levels=(CaseGroupingLevel.STUDY_FAMILY, CaseGroupingLevel.LAB_CLUSTER),
                isolation_between_conditions=True,
            ),
            "washout_training": WashoutTrainingPeriod(
                washout_days=14,
                training_description="Training cases with the UI before the first arm.",
                learning_carryover_assessment_planned=True,
            ),
            "randomization_seed_commitment": RandomizationSeedCommitment(
                sealed_seed_fingerprint=gate.sha256_of_bytes(b"deterministic-test-seed"),
                generator="hashlib-based Fisher-Yates over frozen case bundle",
                committed_before_enrollment_at=SEED_COMMITTED_AT,
                covers_arm_allocation=True,
                covers_case_order=True,
            ),
            "reference_policy": ReferencePolicy.INDEPENDENT_BLIND,
            "uniform_source_access": True,
            "time_budget_declared_uniform": True,
            "initial_judgement_capture": InitialJudgementCaptureSubset(
                captured_before_ai_display=True,
                subset_fraction=Decimal("0.25"),
                blinding_enforced_until_capture=True,
                rationale="Estimate anchoring on a blinded case subset.",
            ),
            "logging_contract": LoggingContract(
                log_accept_reject_override=True,
                log_evidence_inspection=True,
                log_active_review_time=True,
            ),
            "missing_data_rules": (
                MissingDataRule(
                    metric_scope="ACTIVE_REVIEW_TIME",
                    policy="MULTIPLE_IMPUTATION_WITH_SENSITIVITY",
                    rationale="Session crashes must not silently drop arm time.",
                ),
            ),
            "stopping_rule": StoppingRule(
                max_participants=24,
                max_cases=120,
                early_stop_criteria=("critical false-certainty above preregistered bound",),
                stop_on_unacceptable_critical_error_rate=True,
            ),
            "metric_preregistrations": _metric_preregistrations(),
        }
    )
    encoded = protocol.model_dump(mode="json")
    assert encoded["status"] == "PREREGISTRATION_DRAFT"
    assert encoded["data_collection_started"] is False
    return json.dumps(encoded, ensure_ascii=False, sort_keys=True)


def _write_bundle_file(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _run_emit(tmp_path: Path, *, out: Path | None, force: bool = False) -> dict[str, Any]:
    bundle_path = _write_bundle_file(tmp_path / "attestations.json", _bundle(_complete_entries()))
    draft_path = tmp_path / "draft-record.json"
    draft_path.write_text(_draft_record_json(), encoding="utf-8")
    return gate.emit_frozen_record(
        bundle_path=bundle_path,
        draft_record_path=draft_path,
        protocol_path=PROTOCOL_PATH,
        out_path=out,
        force=force,
    )


def test_happy_path_end_to_end_yields_package_accepted_frozen_record(tmp_path: Path) -> None:
    out_path = tmp_path / "frozen-record.json"
    result = _run_emit(tmp_path, out=out_path)
    assert result["record_status"] == "FROZEN_PREREGISTRATION"

    envelope = json.loads(out_path.read_text(encoding="utf-8"))
    assert envelope["bundle_kind"] == "team-eval-freeze-record"
    assert envelope["source_protocol_sha256"] == _protocol_sha256()
    assert envelope["attestations_digest"] == gate.attestations_digest(
        sorted(envelope["attestations"], key=lambda item: item["role_token"])
    )
    assert [item["role_token"] for item in envelope["attestations"]] == sorted(ALL_ROLES)

    frozen = TeamEvaluationProtocolRecord.model_validate(envelope["record"])
    assert frozen.status is PreregistrationStatus.FROZEN_PREREGISTRATION
    assert frozen.data_collection_started is False
    assert frozen.protocol_id == "TEAM-EVAL-V0.1"
    restored_status = json.loads(frozen.model_dump_json())["status"]
    assert restored_status == "FROZEN_PREREGISTRATION"


def test_emit_refuses_when_working_tree_protocol_deviates_from_attested_hash(
    tmp_path: Path,
) -> None:
    variant = tmp_path / "protocol-variant.md"
    variant.write_bytes(PROTOCOL_PATH.read_bytes() + b"\n<!-- post-verify drift -->\n")

    bundle_path = _write_bundle_file(
        tmp_path / "attestations.json",
        _bundle(_complete_entries(), protocol_sha256=_protocol_sha256(variant)),
    )
    verified = gate.verify_attestation_file(bundle_path, protocol_path=variant)
    assert verified.attestations_digest

    draft_path = tmp_path / "draft-record.json"
    draft_path.write_text(_draft_record_json(), encoding="utf-8")
    with pytest.raises(gate.FreezeGateError) as excinfo:
        gate.emit_frozen_record(
            verified=verified,
            draft_record_path=draft_path,
            protocol_path=PROTOCOL_PATH,
            out_path=None,
            force=False,
        )
    message = str(excinfo.value)
    assert "working-tree protocol bytes deviate from the attested bundle" in message
    assert "preregistered deviation" in message


def test_emit_refuses_overwrite_without_force_and_warns_when_forced(tmp_path: Path) -> None:
    out_path = tmp_path / "frozen-record.json"
    _run_emit(tmp_path, out=out_path)

    with pytest.raises(gate.FreezeGateError) as excinfo:
        _run_emit(tmp_path, out=out_path)
    assert "refusing to overwrite existing" in str(excinfo.value)
    assert "--force" in str(excinfo.value)

    forced = _run_emit(tmp_path, out=out_path, force=True)
    assert forced["warning"] is not None
    assert "[WARN] overwriting existing frozen record file" in forced["warning"]
