"""Contratto OCR: registro vuoto di default e provenance obbligatoria."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.ocr import (
    OcrPageResult,
    OcrProvenance,
    OcrUnavailable,
    get_adapter,
    register_adapter,
    registered_engines,
    unregister_all,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    unregister_all()
    yield
    unregister_all()


def test_default_registry_is_empty_and_fail_closed() -> None:
    assert registered_engines() == ()
    with pytest.raises(OcrUnavailable):
        get_adapter("any-engine")


def test_explicit_registration_roundtrip() -> None:
    class FakeEngine:
        engine_id = "fake-ocr"
        engine_version = "0.0.1"

        def supports(self, path: str) -> bool:
            return path.endswith(".pdf")

        def run(self, path: str) -> list[OcrPageResult]:
            return [
                OcrPageResult(
                    page=1,
                    text="scanned",
                    provenance=OcrProvenance(
                        engine_id="fake-ocr",
                        engine_version="0.0.1",
                        page=1,
                        declared_confidence=0.7,
                    ),
                )
            ]

    register_adapter(FakeEngine())
    assert registered_engines() == ("fake-ocr",)
    adapter = get_adapter("fake-ocr")
    pages = adapter.run("doc.pdf")
    assert pages[0].provenance.engine_id == "fake-ocr"


def test_provenance_rejects_bad_page_or_confidence() -> None:
    with pytest.raises(ValidationError):
        OcrProvenance(engine_id="e", engine_version="1", page=0)
    with pytest.raises(ValidationError):
        OcrProvenance(
            engine_id="e",
            engine_version="1",
            page=1,
            declared_confidence=1.5,
        )
