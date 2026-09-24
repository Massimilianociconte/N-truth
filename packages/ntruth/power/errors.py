"""Errori fail-closed del power planner, modulo dedicato anti-ciclo."""

from __future__ import annotations


class PowerBlockedError(ValueError):
    """Piano non emesso: gate negato o input insufficiente (fail-closed)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


__all__ = ["PowerBlockedError"]
