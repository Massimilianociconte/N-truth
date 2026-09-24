"""Profili runtime modificabili; nessuno incorpora un claim di memoria."""

from __future__ import annotations

from ntruth.runtime_resources.schema import (
    RuntimeDevice,
    RuntimeProfile,
    RuntimeProfileName,
)

_PROFILES: dict[RuntimeProfileName, RuntimeProfile] = {
    RuntimeProfileName.LOW_MEMORY: RuntimeProfile(
        name=RuntimeProfileName.LOW_MEMORY,
        context_window_tokens=4_096,
        reserved_output_tokens=1_024,
        chunk_tokens=3_072,
        chunk_overlap_tokens=256,
        max_cached_components=0,
        preferred_device=RuntimeDevice.METAL,
        allow_cpu_fallback=True,
    ),
    RuntimeProfileName.BALANCED: RuntimeProfile(
        name=RuntimeProfileName.BALANCED,
        context_window_tokens=8_192,
        reserved_output_tokens=2_048,
        chunk_tokens=6_144,
        chunk_overlap_tokens=512,
        max_cached_components=1,
        preferred_device=RuntimeDevice.METAL,
        allow_cpu_fallback=True,
    ),
    RuntimeProfileName.QUALITY: RuntimeProfile(
        name=RuntimeProfileName.QUALITY,
        context_window_tokens=16_384,
        reserved_output_tokens=4_096,
        chunk_tokens=12_288,
        chunk_overlap_tokens=1_024,
        max_cached_components=1,
        preferred_device=RuntimeDevice.METAL,
        allow_cpu_fallback=True,
    ),
}


def runtime_profile(
    name: RuntimeProfileName | str,
    *,
    context_window_tokens: int | None = None,
    reserved_output_tokens: int | None = None,
    chunk_tokens: int | None = None,
    chunk_overlap_tokens: int | None = None,
    max_cached_components: int | None = None,
) -> RuntimeProfile:
    """Restituisce una copia del profilo con override espliciti e validati."""

    selected = _PROFILES[RuntimeProfileName(name)]
    updates = {
        key: value
        for key, value in {
            "context_window_tokens": context_window_tokens,
            "reserved_output_tokens": reserved_output_tokens,
            "chunk_tokens": chunk_tokens,
            "chunk_overlap_tokens": chunk_overlap_tokens,
            "max_cached_components": max_cached_components,
        }.items()
        if value is not None
    }
    return RuntimeProfile.model_validate({**selected.model_dump(), **updates})
