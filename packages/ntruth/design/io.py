"""Import/export deterministico del DesignSpecification e del JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ntruth.design.schema import DesignCompilation, DesignSpecification


def _dumps_model(model: DesignSpecification | DesignCompilation) -> str:
    payload = model.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def dumps_design_specification(specification: DesignSpecification) -> str:
    """Serializza in JSON stabile e leggibile, con newline finale."""

    return _dumps_model(specification)


def dumps_design_compilation(compilation: DesignCompilation) -> str:
    """Serializza l'esito del compiler senza aggiungere interpretazioni."""

    return _dumps_model(compilation)


def loads_design_specification(payload: str | bytes) -> DesignSpecification:
    """Valida un payload JSON senza effettuare accessi di rete."""

    return DesignSpecification.model_validate_json(payload)


def write_design_specification(specification: DesignSpecification, path: str | Path) -> Path:
    """Scrive una specifica validata; la directory deve gia esistere."""

    destination = Path(path)
    destination.write_text(dumps_design_specification(specification), encoding="utf-8")
    return destination


def write_design_compilation(compilation: DesignCompilation, path: str | Path) -> Path:
    """Scrive l'handoff strutturale e le assunzioni irrisolte."""

    destination = Path(path)
    destination.write_text(dumps_design_compilation(compilation), encoding="utf-8")
    return destination


def load_design_specification(path: str | Path) -> DesignSpecification:
    """Carica e valida una specifica JSON locale."""

    return loads_design_specification(Path(path).read_bytes())


def design_specification_json_schema() -> dict[str, Any]:
    """Restituisce il JSON Schema ufficiale generato dal contratto Pydantic."""

    return DesignSpecification.model_json_schema(mode="validation")


def write_design_json_schema(path: str | Path) -> Path:
    """Esporta il JSON Schema in forma deterministica."""

    destination = Path(path)
    payload = json.dumps(
        design_specification_json_schema(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    destination.write_text(payload + "\n", encoding="utf-8")
    return destination
