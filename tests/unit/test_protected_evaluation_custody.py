"""Protected evaluation custody: physical split, one-shot permit, ledger, attestation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput, ParserAIOutput
from ntruth.training import (
    AnnotationStatus,
    SupervisedRecord,
    SupervisionProvenance,
    prepare_dataset,
)
from ntruth.training.blind_evaluation import freeze_training_view, validate_training_view
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.protected_evaluation import (
    ProtectedEvaluationError,
    append_ledger,
    consume_permit,
    issue_permit,
    mark_development_opened,
    reject_open_development_as_protected,
    seal_protected_splits,
    verify_attestation,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _target() -> dict[str, object]:
    return ParserAIOutput.model_validate(
        {
            "contract_version": "2.0.0",
            "experiment_blocks": [],
            "evidence_spans": [],
            "candidate_nodes": [],
            "candidate_edges": [],
            "factors": [],
            "endpoints": [],
            "contrasts": [],
            "candidate_estimands": [],
            "determinability": {
                "status": "INDETERMINATE",
                "rationale": "No decisive evidence.",
                "confidence": 0.5,
                "evidence_ids": [],
            },
            "alternatives": [],
            "clarification_questions": [],
            "model_metadata": {
                "adapter_name": "eval-custody-test",
                "model_name": "annotation",
                "model_version": "1",
                "model_checksum": None,
                "prompt_template_version": "eval-custody-test",
                "contract_version": "2.0.0",
                "local_execution": True,
            },
        }
    ).model_dump(mode="json")


def _record(record_id: str, split: CorpusSplit) -> SupervisedRecord:
    parser_input = ParserAIInput(
        metadata={"record": record_id},
        domain_hint="eval_custody_test",
        language="en",
    )
    return SupervisedRecord(
        record_id=record_id,
        task="parser_ai_v2",
        language="en",
        domain="eval_custody_test",
        input_text=parser_input.model_dump_json(),
        target=_target(),
        provenance=SupervisionProvenance(
            source_id=f"source-{record_id}",
            source_asset_id=f"asset-{record_id}",
            source_sha256=_sha(f"source:{record_id}"),
            governance_hash=_sha(f"governance:{record_id}"),
            license_or_authorization_id=f"license-{record_id}",
            guideline_version="eval-custody-test",
            reviewer_count=2,
            reviewer_roles=("wet-lab", "biostatistician"),
        ),
        annotation_status=AnnotationStatus.DOUBLE_REVIEWED,
        training_eligible=True,
        requested_split=split,
    )


def _custody(path: Path) -> Path:
    dataset = prepare_dataset(
        (
            _record("train-a", CorpusSplit.TRAIN),
            _record("valid-a", CorpusSplit.VALIDATION),
            _record("test-secret", CorpusSplit.TEST),
            _record("external-secret", CorpusSplit.EXTERNAL),
        )
    )
    export_mlx_dataset(dataset, path)
    return path


def test_training_view_cannot_enumerate_protected_payloads(tmp_path: Path) -> None:
    custody = _custody(tmp_path / "custody")
    view = tmp_path / "training-view"
    freeze_training_view(custody, view)
    validated = validate_training_view(view)

    names = {path.name for path in view.iterdir()}
    assert "test.jsonl" not in names
    assert "external.jsonl" not in names
    assert "train.jsonl" in names
    assert "valid.jsonl" in names
    assert "test" not in validated["counts"]
    assert "external" not in validated["counts"]
    view_text = " ".join(path.read_text(encoding="utf-8") for path in view.glob("*.jsonl"))
    assert "test-secret" not in view_text
    assert "external-secret" not in view_text


def test_permit_is_single_use_and_attestation_verifies_ledger(tmp_path: Path) -> None:
    custody = _custody(tmp_path / "custody")
    vault = tmp_path / "vault"
    seal_protected_splits(custody, vault, commitments={})
    permit = issue_permit(
        scope="test",
        vault_dir=vault,
        ttl=timedelta(minutes=5),
        issuer_role="evaluation-custodian",
    )
    assert permit["scope"] == "test"
    assert permit["nonce"]
    assert permit["expires_at"]
    ledger = tmp_path / "ledger.json"
    attestation = consume_permit(permit, vault_dir=vault, ledger_path=ledger)
    assert attestation["attestation_sha256"]
    from ntruth.training.protected_evaluation import load_ledger

    verify_attestation(attestation, load_ledger(ledger))
    with pytest.raises(ProtectedEvaluationError, match="gia consumato"):
        consume_permit(permit, vault_dir=vault, ledger_path=ledger)


def test_expired_permit_and_incomplete_permit_fail(tmp_path: Path) -> None:
    custody = _custody(tmp_path / "custody")
    vault = tmp_path / "vault"
    seal_protected_splits(custody, vault, commitments={})
    permit = issue_permit(
        scope="external",
        vault_dir=vault,
        ttl=timedelta(seconds=1),
        issuer_role="evaluation-custodian",
        now=datetime(2020, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ProtectedEvaluationError, match="scaduto"):
        consume_permit(
            permit,
            vault_dir=vault,
            ledger_path=tmp_path / "ledger.json",
            now=datetime(2020, 1, 2, tzinfo=UTC),
        )
    with pytest.raises(ProtectedEvaluationError, match="incompleto"):
        consume_permit(
            {"schema_version": "1.0.0", "scope": "test"},
            vault_dir=vault,
            ledger_path=tmp_path / "ledger.json",
        )


def test_open_development_test_is_rejected_as_protected(tmp_path: Path) -> None:
    custody = _custody(tmp_path / "custody")
    vault = tmp_path / "vault"
    seal_protected_splits(custody, vault, commitments={})
    mark_development_opened(vault, reason="opened during prompt debugging")
    permit = issue_permit(
        scope="test",
        vault_dir=vault,
        ttl=timedelta(minutes=5),
        issuer_role="evaluation-custodian",
    )
    with pytest.raises(ProtectedEvaluationError, match="development"):
        consume_permit(permit, vault_dir=vault, ledger_path=tmp_path / "ledger.json")
    with pytest.raises(ProtectedEvaluationError, match="development"):
        consume_permit(
            permit,
            vault_dir=vault,
            ledger_path=tmp_path / "ledger.json",
            development_test=True,
        )
    with pytest.raises(ProtectedEvaluationError, match="development"):
        reject_open_development_as_protected(custody / "test.jsonl")


def test_ledger_is_append_only(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    append_ledger(
        ledger,
        {
            "permit_id": "p1",
            "nonce": "n1",
            "scope": "test",
            "payload_sha256": "a" * 64,
        },
    )
    append_ledger(
        ledger,
        {
            "permit_id": "p2",
            "nonce": "n2",
            "scope": "external",
            "payload_sha256": "b" * 64,
        },
    )
    with pytest.raises(ProtectedEvaluationError, match="gia consumato"):
        append_ledger(
            ledger,
            {
                "permit_id": "p1",
                "nonce": "n3",
                "scope": "test",
                "payload_sha256": "a" * 64,
            },
        )
    from ntruth.training.protected_evaluation import load_ledger

    loaded = load_ledger(ledger)
    assert [entry["permit_id"] for entry in loaded["entries"]] == ["p1", "p2"]


def test_freeze_contracts_exist_and_do_not_claim_authorized() -> None:
    root = Path(__file__).resolve().parents[2]
    snapshot = (
        root / "docs" / "training" / "contracts" / "snapshot-freeze-v1.json"
    )
    baseline = (
        root / "docs" / "training" / "contracts" / "baseline-protocol-freeze-v1.json"
    )
    import json

    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    proto = json.loads(baseline.read_text(encoding="utf-8"))
    assert snap["authorized"] is False
    assert proto["executed"] is False
    assert "test" in snap["physical_partitions"]
    assert proto["fine_tuning_justification_requires"]["normative_registry_v9_frozen"] is True
