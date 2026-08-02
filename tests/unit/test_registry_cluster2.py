"""Cluster 2: registry, fingerprints, public chain, claim gates."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ntruth.model_backends.base import ModelProvider
from ntruth.model_backends.factory import create_model_backend, resolve_provider
from ntruth.model_backends.granite import GraniteBackend
from ntruth.model_backends.legacy.qwen_backend import LegacyQwenBackend
from ntruth.model_backends.registry import (
    ARTIFACT_FINGERPRINT_KEYS,
    RuntimeQualificationStatus,
    ScientificValidationStatus,
    artifact_fingerprint,
    canonical_fingerprint_hash,
    claim_gates,
    compute_transition_hash,
    evaluate_qualification_against_artifact,
    fingerprints_equal,
    is_scientifically_releasable,
    load_registry,
    qualification_status,
    verify_public_chain,
)


def test_cluster1_still_defaults_to_qwen() -> None:
    assert resolve_provider() is ModelProvider.LEGACY_QWEN
    backend = create_model_backend(model_path=Path("/tmp/x"))
    assert isinstance(backend, LegacyQwenBackend)
    g = create_model_backend(model_path=Path("/tmp/g"), provider="granite")
    assert isinstance(g, GraniteBackend)


def test_registry_schema_and_statuses() -> None:
    reg = load_registry()
    assert reg["schema_version"] == "1.3.0"
    assert reg["factory_default_provider"] == "legacy_qwen"
    q = reg["qualification"]
    assert q["migration_status"] == "ARCHITECTURE_MIGRATED"
    assert q["runtime_qualification_status"] == "PARTIALLY_VERIFIED"
    assert q["scientific_validation_status"] == "NOT_STARTED"
    status = qualification_status(reg)
    assert status["factory_default_provider"] == "legacy_qwen"


def test_public_chain_verifies() -> None:
    report = verify_public_chain(verify_evidence=True)
    assert report["ok"] is True
    assert report["event_count"] == 4
    assert report["tip_transition_hash"]


def test_fingerprint_stable_and_order_independent() -> None:
    a = {
        "model_id": "ibm-granite/granite-4.1-3b",
        "model_revision": "revA",
        "weights_sha256": "abc",
        "adapter_sha256": None,
        "tokenizer_revision": "revA",
        "chat_template_hash": "t1",
        "quantization": "4bit_mlx_community",
        "backend": "mlx-lm",
        "backend_version": "0.31.3",
        "schema_version": "candidate_graph_set_1.0.0",
        "task_profile": "parser_candidate_graph_v6",
        "domain_profile": "runtime_smoke_only",
    }
    b = {k: a[k] for k in reversed(list(a.keys()))}
    assert canonical_fingerprint_hash(a) == canonical_fingerprint_hash(b)
    assert fingerprints_equal(a, b)


def test_fingerprint_changes_on_revision_quant_or_template() -> None:
    base = {
        "model_id": "ibm-granite/granite-4.1-3b",
        "model_revision": "revA",
        "weights_sha256": "abc",
        "adapter_sha256": None,
        "tokenizer_revision": "revA",
        "chat_template_hash": "t1",
        "quantization": "4bit_mlx_community",
        "backend": "mlx-lm",
        "backend_version": "0.31.3",
        "schema_version": "candidate_graph_set_1.0.0",
        "task_profile": "parser_candidate_graph_v6",
        "domain_profile": "runtime_smoke_only",
    }
    h0 = canonical_fingerprint_hash(base)
    for key, value in (
        ("model_revision", "revB"),
        ("quantization", "gguf_q4_k_m"),
        ("chat_template_hash", "t2"),
        ("adapter_sha256", "deadbeef"),
        ("backend", "llama.cpp"),
    ):
        mutated = dict(base)
        mutated[key] = value
        assert canonical_fingerprint_hash(mutated) != h0


def test_no_inheritance_across_variants() -> None:
    reg = load_registry()
    binding = reg["qualification"]["qualified_artifact"]
    gguf = artifact_fingerprint(
        {
            **binding,
            "quantization": "gguf_q4_k_m",
            "backend": "llama.cpp",
            "model_revision": "gguf-rev",
        }
    )
    eval_out = evaluate_qualification_against_artifact(current_artifact=gguf, registry=reg)
    assert eval_out["match"] is False
    assert eval_out["evaluated_runtime_qualification_status"] == "STALE"


def test_claim_gates_fail_closed() -> None:
    reg = load_registry()
    gates = claim_gates(reg)
    assert gates["exploratory_benchmark"]["allowed"] is True
    assert gates["internal_pilot"]["allowed"] is True  # PARTIALLY_VERIFIED
    assert gates["external_validation"]["allowed"] is False
    assert gates["scientifically_releasable"]["allowed"] is False
    assert is_scientifically_releasable(reg) is False


def test_cannot_claim_science_on_runtime_only() -> None:
    reg = load_registry()
    bad = copy.deepcopy(reg)
    bad["qualification"]["scientific_validation_status"] = (
        ScientificValidationStatus.PILOT_VALIDATED.value
    )
    # PILOT with PARTIAL is allowed by schema for pilot, but EXTERNAL requires VERIFIED
    bad2 = copy.deepcopy(reg)
    bad2["qualification"]["scientific_validation_status"] = (
        ScientificValidationStatus.EXTERNAL_VALIDATED.value
    )
    from ntruth.model_backends.registry import ModelRegistryError, _validate_qualification_block

    with pytest.raises(ModelRegistryError, match="EXTERNAL_VALIDATED|VERIFIED"):
        _validate_qualification_block(bad2["qualification"])


def test_missing_evidence_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ntruth.model_backends import registry as regmod

    # Point public evidence to empty dir
    monkeypatch.setattr(regmod, "public_evidence_root", lambda repo_root=None: tmp_path / "empty")
    with pytest.raises(Exception, match="evidence|missing|mismatch"):
        verify_public_chain(repo_root=None, verify_evidence=True)


def test_transition_hash_deterministic() -> None:
    h1 = compute_transition_hash(
        sequence=1,
        registry_id="default",
        timestamp="2026-08-02T00:00:00Z",
        actor="test",
        dimension="migration_status",
        from_status="NONE",
        to_status="ARCHITECTURE_MIGRATED",
        rationale="r",
        evidence_sha256=None,
        previous_transition_hash=None,
        artifact_fingerprint_sha256=None,
    )
    h2 = compute_transition_hash(
        sequence=1,
        registry_id="default",
        timestamp="2026-08-02T00:00:00Z",
        actor="test",
        dimension="migration_status",
        from_status="NONE",
        to_status="ARCHITECTURE_MIGRATED",
        rationale="r",
        evidence_sha256=None,
        previous_transition_hash=None,
        artifact_fingerprint_sha256=None,
    )
    assert h1 == h2
    assert len(h1) == 64


def test_fingerprint_keys_cover_quant_backend_template() -> None:
    assert "quantization" in ARTIFACT_FINGERPRINT_KEYS
    assert "backend" in ARTIFACT_FINGERPRINT_KEYS
    assert "chat_template_hash" in ARTIFACT_FINGERPRINT_KEYS
    assert "adapter_sha256" in ARTIFACT_FINGERPRINT_KEYS
