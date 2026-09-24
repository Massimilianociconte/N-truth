"""Cluster 1: MiniCPM backend disponibile, default, no registry/constrained."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ntruth.model_backends import (
    MINICPM_CANONICAL_MODEL_ID,
    MODEL_MUST_NOT_EMIT,
    ComponentLoadError,
    ConstrainedDecodingUnavailable,
    GenerationRequest,
    MiniCPMBackend,
    MiniCPMBackendError,
    ModelProvider,
    create_model_backend,
    resolve_provider,
)


def test_default_provider_is_minicpm() -> None:
    assert resolve_provider() is ModelProvider.MINICPM
    assert MINICPM_CANONICAL_MODEL_ID == "openbmb/MiniCPM5-2B"


def test_minicpm_metadata_is_provisional_primary() -> None:
    backend = MiniCPMBackend(model_path=Path("/tmp/minicpm-placeholder"))
    meta = backend.model_metadata()
    assert meta.provider is ModelProvider.MINICPM
    assert meta.model_id == "openbmb/MiniCPM5-2B"
    assert meta.license == "Apache-2.0"
    assert meta.scientifically_selected is False
    assert meta.parameter_count == 2_516_756_480
    assert meta.context_window_tokens == 131_072
    assert any("Official vendor MLX" in note for note in meta.notes)
    assert any("enable_thinking=false" in note for note in meta.notes)


def test_minicpm_missing_weights_explicit_error(tmp_path: Path) -> None:
    backend = MiniCPMBackend(model_path=tmp_path / "no-such-model")
    with pytest.raises(ComponentLoadError, match=r"assenti|missing|pesi|acquire_minicpm"):
        backend.load()


def test_minicpm_constrained_request_fails_closed() -> None:
    backend = MiniCPMBackend(model_path=Path("/tmp/unused-minicpm-path"))
    req = GenerationRequest(
        messages=[{"role": "user", "content": "hi"}],
        constrained=True,
        output_schema="evidence_extraction",
    )
    with pytest.raises(ConstrainedDecodingUnavailable):
        backend.generate_structured(req)
    assert backend.supports_constrained_decoding() is False


def test_minicpm_template_disables_thinking(tmp_path: Path) -> None:
    model_dir = tmp_path / "fake-weights"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    fake_model = object()
    fake_tok = MagicMock()
    fake_tok.encode = lambda text, add_special_tokens=False: [1, 2, 3]
    fake_tok.apply_chat_template = MagicMock(return_value="<|im_start|>user")
    fake_tok.eos_token = "</s>"

    backend = MiniCPMBackend(model_path=model_dir, revision="test-rev")
    with (
        patch.dict("sys.modules", {"mlx_lm": MagicMock()}),
        patch("mlx_lm.load", return_value=(fake_model, fake_tok)),
        patch("mlx_lm.sample_utils.make_sampler", return_value=object()),
    ):
        import mlx_lm

        mlx_lm.load = MagicMock(return_value=(fake_model, fake_tok))
        with patch.dict(
            "sys.modules",
            {
                "mlx_lm": mlx_lm,
                "mlx_lm.sample_utils": MagicMock(make_sampler=MagicMock(return_value=object())),
            },
        ):
            rendered = backend.apply_chat_template(
                [{"role": "user", "content": "hi"}], add_generation_prompt=True
            )
            assert rendered == "<|im_start|>user"
            _, kwargs = fake_tok.apply_chat_template.call_args
            assert kwargs.get("enable_thinking") is False


def test_minicpm_template_flag_rejection_fails_closed(tmp_path: Path) -> None:
    model_dir = tmp_path / "fake-weights-think"
    model_dir.mkdir()

    fake_tok = MagicMock()
    fake_tok.encode = lambda text, add_special_tokens=False: [1, 2, 3]

    def _reject_template(*_a: Any, **_k: Any) -> str:
        raise TypeError("apply_chat_template() got an unexpected keyword 'enable_thinking'")

    fake_tok.apply_chat_template = _reject_template

    backend = MiniCPMBackend(model_path=model_dir, revision="test-rev")
    with (
        patch.dict("sys.modules", {"mlx_lm": MagicMock()}),
        patch("mlx_lm.load", return_value=(object(), fake_tok)),
        patch("mlx_lm.sample_utils.make_sampler", return_value=object()),
    ):
        import mlx_lm

        mlx_lm.load = MagicMock(return_value=(object(), fake_tok))
        with (
            patch.dict(
                "sys.modules",
                {
                    "mlx_lm": mlx_lm,
                    "mlx_lm.sample_utils": MagicMock(make_sampler=MagicMock(return_value=object())),
                },
            ),
            pytest.raises(MiniCPMBackendError, match="enable_thinking"),
        ):
            backend.apply_chat_template([{"role": "user", "content": "hi"}])


def test_minicpm_load_unload_reload_with_mock(tmp_path: Path) -> None:
    model_dir = tmp_path / "fake-weights"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    fake_model = object()
    fake_tok = MagicMock()
    fake_tok.encode = lambda text, add_special_tokens=False: [1, 2, 3]
    fake_tok.apply_chat_template = MagicMock(return_value="<|im_start|>userhi")
    fake_tok.eos_token = "</s>"

    def fake_generate(*_a: Any, **_k: Any) -> str:
        return '{"candidates":[]}'

    backend = MiniCPMBackend(model_path=model_dir, revision="test-rev")

    with (
        patch.dict("sys.modules", {"mlx_lm": MagicMock()}),
        patch("mlx_lm.load", return_value=(fake_model, fake_tok)),
        patch("mlx_lm.generate", fake_generate),
        patch("mlx_lm.sample_utils.make_sampler", return_value=object()),
    ):
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
            assert result.raw["backend"] == "minicpm-mlx"
            backend.unload()
            assert backend.get_resource_metrics().unloaded is True
            backend.reload()
            assert backend.get_resource_metrics().unloaded is False
            backend.unload()


def test_factory_default_is_minicpm_backend(tmp_path: Path) -> None:
    backend = create_model_backend(model_path=tmp_path / "minicpm")
    assert isinstance(backend, MiniCPMBackend)
    assert "final_independent_n" in MODEL_MUST_NOT_EMIT


def test_minicpm_module_import_graph_is_cluster1_closed() -> None:
    import ntruth.model_backends.minicpm as minicpm_mod

    source = Path(minicpm_mod.__file__).read_text(encoding="utf-8")
    assert "model_backends.registry" not in source
    assert "model_backends.constrained" not in source
    assert "stage_schemas" not in source
    assert "qualification_ledger" not in source
    assert "training" not in source
