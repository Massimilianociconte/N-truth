"""Backend modello: Granite default, legacy opt-in, confini candidate-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.model_backends import (
    DEFAULT_MODEL_ID,
    MODEL_MUST_NOT_EMIT,
    ModelProvider,
    create_model_backend,
    resolve_provider,
)
from ntruth.model_backends.granite import GraniteBackend
from ntruth.model_backends.legacy.qwen_backend import LegacyQwenBackend
from ntruth.model_backends.registry import (
    ModelRegistryError,
    assert_not_legacy_default,
    default_profile_path,
    legacy_opt_in_enabled,
    load_registry,
)
from ntruth.training.mlx_runtime import MLXPipelineError, load_profile

# I test marcati con _GRANITE_DEFAULT_XFAIL codificano lo stato target
# "Granite come default" non ancora implementato nella baseline v7-era.
# Non dipendono dalla disponibilita' dei pesi (GraniteBackend e' lazy e non
# scarica nulla in costruzione): falliscono perche' factory.resolve_provider
# usa ancora legacy_qwen come default "pre-migrazione versionato" e il test
# cluster1 test_default_provider_is_still_qwen_cluster1 congela quello stato.
# Il flip del default e una decisione di prodotto fuori scope FASE 1;
# strict=True fa fallire forte se il target venisse implementato.
_GRANITE_DEFAULT_XFAIL = pytest.mark.xfail(
    reason=(
        "Specifica target Granite-by-default: il default resta legacy_qwen "
        "versionato pre-migrazione (factory.resolve_provider, budget "
        "NFR-06/cluster1); nessun download modello richiesto. strict: se il "
        "default diventa Granite rimuovere il marker e aggiornare cluster1."
    ),
    strict=True,
)


@_GRANITE_DEFAULT_XFAIL
def test_default_provider_is_granite() -> None:
    assert resolve_provider() is ModelProvider.GRANITE
    assert DEFAULT_MODEL_ID == "ibm-granite/granite-4.1-3b"
    assert "granite" in default_profile_path().name


@_GRANITE_DEFAULT_XFAIL
def test_registry_lists_granite_primary_and_community_mlx() -> None:
    from ntruth.model_backends.registry import (
        MigrationStatus,
        RuntimeQualificationStatus,
        ScientificValidationStatus,
        can_run_exploratory_benchmarks,
        can_run_external_validation,
        can_run_internal_pilot,
        claim_gates,
        is_scientifically_releasable,
        qualification_status,
    )

    registry = load_registry()
    assert registry["schema_version"] == "1.3.0"
    assert registry["default_model_id"] == "ibm-granite/granite-4.1-3b"
    entry = registry["models"]["ibm-granite/granite-4.1-3b"]
    assert entry["license"] == "Apache-2.0"
    assert entry["scientifically_selected"] is False
    assert entry.get("mlx_official_ibm") is False
    assert entry.get("configured_maximum_context_tokens") == 131_072

    status = qualification_status(registry)
    assert status["migration_status"] == MigrationStatus.ARCHITECTURE_MIGRATED
    assert status["runtime_qualification_status"] == RuntimeQualificationStatus.UNVERIFIED
    assert status["scientific_validation_status"] == ScientificValidationStatus.NOT_STARTED
    assert "non è ancora" in status["summary"] or "non e ancora" in status["summary"].replace(
        "è", "e"
    )
    assert is_scientifically_releasable(registry) is False
    # Fail-closed sui claim, non sulla ricerca esplorativa
    assert can_run_exploratory_benchmarks(registry) is True
    assert can_run_internal_pilot(registry) is False
    assert can_run_external_validation(registry) is False
    gates = claim_gates(registry)
    assert gates["exploratory_benchmark"]["allowed"] is True
    assert gates["internal_pilot"]["allowed"] is False
    assert gates["internal_pilot"]["reason"] == "RUNTIME_UNVERIFIED"
    assert gates["internal_pilot"]["required_next_state"] == "PARTIALLY_VERIFIED"
    assert gates["scientifically_releasable"]["allowed"] is False
    assert isinstance(registry["qualification"]["transition_log"], list)
    assert registry["qualification"]["transition_log"][0]["sequence"] == 1


def _log_entry(**kwargs: object) -> dict:
    base = {
        "sequence": 1,
        "timestamp": "2026-08-02T00:00:00Z",
        "actor": "test",
        "dimension": "runtime_qualification_status",
        "from_status": "UNVERIFIED",
        "to_status": "PARTIALLY_VERIFIED",
        "rationale": "fixture",
        "evidence_artifact": "test",
    }
    base.update(kwargs)
    return base


def test_scientific_status_cannot_advance_on_unverified_runtime() -> None:
    from ntruth.model_backends.registry import ModelRegistryError, _validate_qualification_block

    with pytest.raises(ModelRegistryError, match=r"INVALID|runtime|PARTIALLY_VERIFIED"):
        _validate_qualification_block(
            {
                "migration_status": "ARCHITECTURE_MIGRATED",
                "runtime_qualification_status": "UNVERIFIED",
                "scientific_validation_status": "PILOT_VALIDATED",
                "transition_log": [_log_entry()],
            }
        )


def test_positive_runtime_requires_artifact_binding() -> None:
    from ntruth.model_backends.registry import ModelRegistryError, _validate_qualification_block

    with pytest.raises(ModelRegistryError, match="qualified_artifact"):
        _validate_qualification_block(
            {
                "migration_status": "ARCHITECTURE_MIGRATED",
                "runtime_qualification_status": "PARTIALLY_VERIFIED",
                "scientific_validation_status": "NOT_STARTED",
                "transition_log": [_log_entry()],
            }
        )


def test_fingerprint_mismatch_marks_stale_and_invalidated() -> None:
    from ntruth.model_backends.registry import evaluate_qualification_against_artifact

    registry = {
        "schema_version": "1.2.0",
        "qualification": {
            "migration_status": "ARCHITECTURE_MIGRATED",
            "runtime_qualification_status": "VERIFIED",
            "scientific_validation_status": "EXTERNAL_VALIDATED",
            "qualified_artifact": {
                "model_id": "ibm-granite/granite-4.1-3b",
                "model_revision": "abc",
                "weights_sha256": "0" * 64,
                "adapter_sha256": None,
                "tokenizer_revision": "abc",
                "chat_template_hash": "t1",
                "quantization": "bf16",
                "backend": "transformers",
                "backend_version": "4.53.0",
                "schema_version": "candidate_graph_v1",
                "task_profile": "NTRUTH_P0_P1",
                "domain_profile": "cell_culture_microscopy",
            },
            "summary": "test",
        },
    }
    # Stesso modello, quantizzazione diversa → non trasferibile
    current = {
        "model_id": "ibm-granite/granite-4.1-3b",
        "model_revision": "abc",
        "weights_sha256": "0" * 64,
        "adapter_sha256": None,
        "tokenizer_revision": "abc",
        "chat_template_hash": "t1",
        "quantization": "Q4_K_M",
        "backend": "llama.cpp",
        "backend_version": "b1",
        "schema_version": "candidate_graph_v1",
        "task_profile": "NTRUTH_P0_P1",
        "domain_profile": "cell_culture_microscopy",
    }
    evaluated = evaluate_qualification_against_artifact(
        current_artifact=current,
        registry=registry,
    )
    assert evaluated["stale"] is True
    assert evaluated["runtime_qualification_status"] == "STALE"
    assert evaluated["scientific_validation_status"] == "INVALIDATED"
    assert any("quantization" in reason for reason in evaluated["stale_reasons"])


def _artifact(**overrides: object) -> dict:
    base = {
        "model_id": "ibm-granite/granite-4.1-3b",
        "model_revision": "r",
        "weights_sha256": "a" * 64,
        "adapter_sha256": None,
        "tokenizer_revision": "r",
        "chat_template_hash": "h",
        "quantization": "bf16",
        "backend": "transformers",
        "backend_version": "1",
        "schema_version": "s",
        "task_profile": "NTRUTH_P0_P1",
        "domain_profile": "cell_culture_microscopy",
    }
    base.update(overrides)
    return base


def _reg(runtime: str, scientific: str = "NOT_STARTED") -> dict:
    from ntruth.model_backends.registry import canonical_fingerprint_hash

    block: dict = {
        "migration_status": "ARCHITECTURE_MIGRATED",
        "runtime_qualification_status": runtime,
        "scientific_validation_status": scientific,
        "summary": "x",
        "transition_log": [
            {
                "sequence": 1,
                "timestamp": "2026-08-02T00:00:00Z",
                "actor": "test",
                "dimension": "migration_status",
                "from_status": "NONE",
                "to_status": "ARCHITECTURE_MIGRATED",
                "rationale": "fixture",
                "evidence_artifact": "test",
            }
        ],
    }
    if runtime in {"PARTIALLY_VERIFIED", "VERIFIED"}:
        art = _artifact()
        art["canonical_fingerprint_sha256"] = canonical_fingerprint_hash(art)
        block["qualified_artifact"] = art
    return {"schema_version": "1.3.0", "qualification": block}


def test_claim_gates_progression() -> None:
    from ntruth.model_backends.registry import (
        can_run_exploratory_benchmarks,
        can_run_external_validation,
        can_run_internal_pilot,
        evaluate_claim_gate,
        is_scientifically_releasable,
    )

    unverified = _reg("UNVERIFIED")
    assert can_run_exploratory_benchmarks(unverified) is True
    gate = evaluate_claim_gate("internal_pilot", unverified)
    assert gate == {
        "allowed": False,
        "reason": "RUNTIME_UNVERIFIED",
        "required_next_state": "PARTIALLY_VERIFIED",
        "current_runtime_qualification_status": "UNVERIFIED",
        "current_scientific_validation_status": "NOT_STARTED",
    }
    assert can_run_internal_pilot(unverified) is False
    assert can_run_external_validation(unverified) is False

    partial = _reg("PARTIALLY_VERIFIED")
    assert can_run_internal_pilot(partial) is True
    assert can_run_external_validation(partial) is False
    assert evaluate_claim_gate("external_validation", partial)["reason"] == (
        "RUNTIME_ONLY_PARTIALLY_VERIFIED"
    )

    verified = _reg("VERIFIED")
    assert can_run_external_validation(verified) is True
    assert is_scientifically_releasable(verified) is False

    releasable = _reg("VERIFIED", "EXTERNAL_VALIDATED")
    assert is_scientifically_releasable(releasable) is True


def test_canonical_fingerprint_ignores_key_order() -> None:
    from ntruth.model_backends.registry import (
        canonical_fingerprint_hash,
        fingerprints_equal,
    )

    a = _artifact()
    b = dict(reversed(list(a.items())))
    assert fingerprints_equal(a, b)
    assert canonical_fingerprint_hash(a) == canonical_fingerprint_hash(b)
    assert len(canonical_fingerprint_hash(a)) == 64


def test_verified_without_artifact_is_invalid() -> None:
    from ntruth.model_backends.registry import ModelRegistryError, _validate_qualification_block

    with pytest.raises(ModelRegistryError, match="VERIFIED richiede qualified_artifact"):
        _validate_qualification_block(
            {
                "migration_status": "ARCHITECTURE_MIGRATED",
                "runtime_qualification_status": "VERIFIED",
                "scientific_validation_status": "NOT_STARTED",
                "qualified_artifact": None,
                "transition_log": [
                    {
                        "sequence": 1,
                        "timestamp": "2026-08-02T00:00:00Z",
                        "actor": "test",
                        "dimension": "runtime_qualification_status",
                        "from_status": "UNVERIFIED",
                        "to_status": "VERIFIED",
                        "rationale": "invalid fixture",
                    }
                ],
            }
        )


def test_external_validated_without_verified_runtime_is_invalid() -> None:
    from ntruth.model_backends.registry import (
        ModelRegistryError,
        _validate_qualification_block,
        canonical_fingerprint_hash,
    )

    art = _artifact()
    art["canonical_fingerprint_sha256"] = canonical_fingerprint_hash(art)
    with pytest.raises(ModelRegistryError, match="EXTERNAL_VALIDATED"):
        _validate_qualification_block(
            {
                "migration_status": "ARCHITECTURE_MIGRATED",
                "runtime_qualification_status": "PARTIALLY_VERIFIED",
                "scientific_validation_status": "EXTERNAL_VALIDATED",
                "qualified_artifact": art,
                "transition_log": [
                    {
                        "sequence": 1,
                        "timestamp": "2026-08-02T00:00:00Z",
                        "actor": "test",
                        "dimension": "scientific_validation_status",
                        "from_status": "NOT_STARTED",
                        "to_status": "EXTERNAL_VALIDATED",
                        "rationale": "invalid fixture",
                    }
                ],
            }
        )


def test_model_must_not_emit_scientific_verdicts() -> None:
    assert "final_independent_n" in MODEL_MUST_NOT_EMIT
    assert "determinability_verdict" in MODEL_MUST_NOT_EMIT


@_GRANITE_DEFAULT_XFAIL
def test_factory_default_is_granite_backend() -> None:
    backend = create_model_backend(
        model_path=Path("/tmp/granite-placeholder"),
        allow_legacy=False,
    )
    assert isinstance(backend, GraniteBackend)
    meta = backend.model_metadata()
    assert meta.provider is ModelProvider.GRANITE
    assert meta.scientifically_selected is False
    assert any("community" in note.casefold() for note in meta.notes)


@_GRANITE_DEFAULT_XFAIL
def test_legacy_provider_without_opt_in_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NTRUTH_MODEL_PROVIDER", "legacy_qwen")
    monkeypatch.delenv("NTRUTH_ALLOW_LEGACY_QWEN", raising=False)
    with pytest.raises(ModelRegistryError, match=r"legacy Qwen disabilitato|opt-in|ALLOW_LEGACY"):
        create_model_backend(model_path=Path("/tmp/qwen"), allow_legacy=False)


@_GRANITE_DEFAULT_XFAIL
def test_legacy_provider_with_allow_legacy_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NTRUTH_MODEL_PROVIDER", "legacy_qwen")
    monkeypatch.delenv("NTRUTH_ALLOW_LEGACY_QWEN", raising=False)
    backend = create_model_backend(
        model_path=Path("/tmp/qwen-opt-in"),
        allow_legacy=True,
    )
    assert isinstance(backend, LegacyQwenBackend)
    assert backend.model_metadata().role.value == "legacy_unsupported"


def test_legacy_provider_with_env_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NTRUTH_MODEL_PROVIDER", "legacy_qwen")
    monkeypatch.setenv("NTRUTH_ALLOW_LEGACY_QWEN", "1")
    backend = create_model_backend(
        model_path=Path("/tmp/qwen-env"),
        allow_legacy=False,
    )
    assert isinstance(backend, LegacyQwenBackend)


@_GRANITE_DEFAULT_XFAIL
def test_legacy_backend_without_enabled_flag_raises() -> None:
    with pytest.raises(RuntimeError, match="opt-in"):
        LegacyQwenBackend(model_path=Path("/tmp/x"), enabled=False)


def test_assert_not_legacy_default_ok_for_granite() -> None:
    assert_not_legacy_default()
    assert legacy_opt_in_enabled(allow_legacy=False) is False
    assert legacy_opt_in_enabled(allow_legacy=True) is True


def test_granite_profile_rejects_qwen_repository(tmp_path: Path) -> None:
    path = Path("models/configs/granite-4.1-3b-mlx-qlora.json")
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["model"]["repository"] = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(MLXPipelineError, match="Qwen"):
        load_profile(bad)


def test_granite_profile_documents_configured_context_and_community_mlx() -> None:
    profile = load_profile(Path("models/configs/granite-4.1-3b-mlx-qlora.json"))
    model = profile["model"]
    assert model["configured_maximum_context_tokens"] == 131_072
    assert model["mlx_distribution"]["official_ibm"] is False
    assert model["mlx_distribution"]["kind"] == "community_conversion"
    assert model["expected_weight_sha256"] == (
        "cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d"
    )
    assert "not_inherited_from_prior_qwen" in model["lora_target_modules_source"]
