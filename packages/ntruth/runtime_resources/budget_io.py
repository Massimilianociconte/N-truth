"""Serializzazione fail-closed del budget runtime misurato.

I budget non contengono stime teoriche: solo envelope derivati da osservazioni.
Nessun valore di RAM predefinito viene inventato in lettura o scrittura.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ntruth.runtime_resources.schema import RuntimeResourceBudget


class RuntimeBudgetIOError(ValueError):
    """Budget assente, illeggibile o non conforme allo schema."""


def load_runtime_resource_budget(path: Path) -> RuntimeResourceBudget:
    """Carica un ``RuntimeResourceBudget`` da JSON; fallisce a schema invalido."""

    path = Path(path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeBudgetIOError(f"budget non leggibile: {path}: {exc}") from exc
    try:
        payload: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeBudgetIOError(f"budget JSON non valido: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeBudgetIOError(
            f"budget deve essere un oggetto JSON: {path} ({type(payload).__name__})"
        )
    try:
        return RuntimeResourceBudget.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeBudgetIOError(f"schema budget non valido: {path}: {exc}") from exc


def save_runtime_resource_budget(budget: RuntimeResourceBudget, path: Path) -> None:
    """Scrive il budget in forma canonica; non completa campi mancanti."""

    path = Path(path)
    if not isinstance(budget, RuntimeResourceBudget):
        raise RuntimeBudgetIOError(
            f"atteso RuntimeResourceBudget, ricevuto {type(budget).__name__}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = budget.model_dump(mode="json")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
