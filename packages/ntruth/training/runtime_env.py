"""Fingerprint dell'ambiente runtime per il resource manager (adapter training).

I valori devono riflettere la macchina reale: nessun etichetta M5/M-series viene
inventata se non rilevata dal sistema.
"""

from __future__ import annotations

import os
import platform
import subprocess

from ntruth.runtime_resources.schema import RuntimeEnvironment


class RuntimeEnvironmentProbeError(RuntimeError):
    """Ambiente non misurabile in modo fail-closed."""


def _sysctl_n(key: str) -> str | None:
    try:
        completed = subprocess.run(
            ["sysctl", "-n", key],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def detect_machine_model() -> str:
    """Modello macchina (es. ``Mac17,9`` su macOS); fallback a hostname/arch."""

    if platform.system() == "Darwin":
        model = _sysctl_n("hw.model")
        if model is not None:
            return model
    node = platform.node().strip()
    if node:
        return node
    machine = platform.machine().strip()
    if machine:
        return machine
    raise RuntimeEnvironmentProbeError("impossibile determinare machine_model")


def detect_unified_memory_bytes() -> int:
    """Memoria unificata/fisica in byte; non inventa valori predefiniti."""

    if platform.system() == "Darwin":
        raw = _sysctl_n("hw.memsize")
        if raw is not None:
            try:
                value = int(raw)
            except ValueError as exc:
                raise RuntimeEnvironmentProbeError(
                    f"hw.memsize non intero: {raw!r}"
                ) from exc
            if value > 0:
                return value
            raise RuntimeEnvironmentProbeError("hw.memsize non positivo")
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        value = int(pages) * int(page_size)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise RuntimeEnvironmentProbeError(
            "memoria unificata/fisica non misurabile su questo host"
        ) from exc
    if value <= 0:
        raise RuntimeEnvironmentProbeError("memoria fisica rilevata non positiva")
    return value


def detect_operating_system() -> str:
    """Stringa OS stabile e leggibile, senza claim di silicon marketing."""

    system = platform.system()
    if system == "Darwin":
        version = platform.mac_ver()[0] or platform.release()
        return f"macOS {version}".strip()
    release = platform.release()
    if release:
        return f"{system} {release}".strip()
    return system or platform.platform()


def probe_runtime_environment(
    runtime_name: str,
    runtime_version: str,
) -> RuntimeEnvironment:
    """Costruisce il fingerprint corrente per confrontarlo con il budget misurato."""

    name = runtime_name.strip()
    version = runtime_version.strip()
    if not name:
        raise RuntimeEnvironmentProbeError("runtime_name obbligatorio")
    if not version:
        raise RuntimeEnvironmentProbeError("runtime_version obbligatorio")
    return RuntimeEnvironment(
        machine_model=detect_machine_model(),
        unified_memory_bytes=detect_unified_memory_bytes(),
        operating_system=detect_operating_system(),
        runtime_name=name,
        runtime_version=version,
    )
