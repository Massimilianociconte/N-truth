"""Cluster 1: Granite backend available, not default, no registry/constrained."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ntruth.model_backends import (
    GRANITE_CANONICAL_MODEL_ID,
    MODEL_MUST_NOT_EMIT,
    ComponentLoadError,
    ConstrainedDecodingUnavailable,
    GenerationRequest,
    GraniteBackend,
    ModelProvider,
    create_model_backend,
    resolve_provider,
)
from ntruth.model_backends.profile import (
    ProfileValidationError,
    default_granite_profile_path,
    load_backend_profile,
    validate_backend_profile,
)


def test_default_provider_is_still_qwen_cluster1() -> None:
    assert resolve_provider() is ModelProvider.LEGACY_QWEN


def test_granite_provider_explicit_only() -> None:
    assert resolve_provider(provider="granite") is ModelProvider.GRANITE


def test_import_model_backend_and_granite() -> None:
    from ntruth.model_backends.base import ModelBackend
    from ntruth.model_backends.granite import GraniteBackend as GB

    assert issubclass(GB, ModelBackend)


def test_forbidden_outputs_policy() -> None:
    assert "final_independent_n" in MODEL_MUST_NOT_EMIT
    assert "determinability_verdict" in MODEL_MUST_NOT_EMIT


def test_technical_profile_validates_and_forbids_operational_status() -> None:
    path = default_granite_profile_path()
    assert path.is_file(), f"missing technical profile {path}"
    data = load_backend_profile(path)
    assert data["model"]["canonical_repository"] == GRANITE_CANONICAL_MODEL_ID
    bad = json.loads(path.read_text(encoding="utf-8"))
    bad["model"]["runtime_qualification_status"] = "UNVERIFIED"
    with pytest.raises(ProfileValidationError, match="operational status"):
        validate_backend_profile(bad)


def test_granite_missing_weights_explicit_error(tmp_path: Path) -> None:
    backend = GraniteBackend(model_path=tmp_path / "no-such-model")
    with pytest.raises(ComponentLoadError, match="assenti|missing|pesi"):
        backend.load()


def test_granite_constrained_request_fails_closed() -> None:
    backend = GraniteBackend(model_path=Path("/tmp/unused-granite-path"))
    req = GenerationRequest(
        messages=[{"role": "user", "content": "hi"}],
        constrained=True,
        output_schema="evidence_extraction",
    )
    with pytest.raises(ConstrainedDecodingUnavailable):
        backend.generate_structured(req)
    assert backend.supports_constrained_decoding() is False


def test_factory_default_is_qwen_backend(tmp_path: Path) -> None:
    backend = create_model_backend(model_path=tmp_path / "qwen")
    from ntruth.model_backends.legacy.qwen_backend import LegacyQwenBackend

    assert isinstance(backend, LegacyQwenBackend)


def test_factory_granite_explicit(tmp_path: Path) -> None:
    backend = create_model_backend(
        model_path=tmp_path / "granite",
        provider="granite",
    )
    assert isinstance(backend, GraniteBackend)
    meta = backend.model_metadata()
    assert meta.scientifically_selected is False
    assert meta.provider is ModelProvider.GRANITE


def test_granite_load_unload_reload_with_mock(tmp_path: Path) -> None:
    model_dir = tmp_path / "fake-weights"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    fake_model = object()
    fake_tok = MagicMock()
    fake_tok.encode = lambda text, add_special_tokens=False: [1, 2, 3]
    fake_tok.apply_chat_template = MagicMock(
        return_value="<|start_of_role|>user<|end_of_role|>hi"
    )
    fake_tok.eos_token = "</s>"

    def fake_generate(*_a: Any, **_k: Any) -> str:
        return '{"candidates":[]}'

    backend = GraniteBackend(model_path=model_dir, revision="test-rev")

    with (
        patch.dict("sys.modules", {"mlx_lm": MagicMock()}),
        patch("mlx_lm.load", return_value=(fake_model, fake_tok)),
        patch("mlx_lm.generate", fake_generate),
        patch("mlx_lm.sample_utils.make_sampler", return_value=object()),
    ):
        # Import path used inside load():
        import mlx_lm

        mlx_lm.load = MagicMock(return_value=(fake_model, fake_tok))
        mlx_lm.generate = fake_generate
        with patch.dict(
            "sys.modules",
            {
                "mlx_lm": mlx_lm,
                "mlx_lm.sample_utils": MagicMock(make_sampler=MagicMock(return_value=object())),
                "mlx_lm.generate": MagicMock(
                    stream_generate=MagicMock(side_effect=Exception("no stream"))
                ),
            },
        ):
            backend.load()
            assert backend.get_resource_metrics().unloaded is False
            result = backend.generate_structured(
                GenerationRequest(
                    messages=[{"role": "user", "content": "extract candidates"}],
                    max_tokens=32,
                    task_tag="TASK_EVIDENCE",
                )
            )
            assert "candidates" in result.text or result.text is not None
            assert result.constrained_status == "FREE_DECODE"
            backend.unload()
            assert backend.get_resource_metrics().unloaded is True
            backend.reload()
            assert backend.get_resource_metrics().unloaded is False
            backend.unload()


def test_package_init_does_not_export_registry_or_constrained() -> None:
    import ntruth.model_backends as mb

    assert not hasattr(mb, "load_registry")
    assert not hasattr(mb, "QualificationLedger")
    assert not hasattr(mb, "probe_outlines_mlx")
    assert not hasattr(mb, "STAGE_SCHEMA_REGISTRY")


def test_granite_module_import_graph_is_cluster1_closed() -> None:
    import ntruth.model_backends.granite as granite_mod

    source = Path(granite_mod.__file__).read_text(encoding="utf-8")
    assert "model_backends.registry" not in source
    assert "model_backends.constrained" not in source
    assert "stage_schemas" not in source
    assert "qualification_ledger" not in source
    assert "training" not in source
