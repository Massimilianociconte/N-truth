"""Per-operation memo for deterministic re-verification of content-addressed records.

The kernel re-validates nested records on every parent validation
(``revalidate_instances="always"``) and several validators re-execute
deterministic checks, up to the whole v8 pipeline. Inside one top-level
operation (a guided confirmation, one Quick Design run) the same byte-identical
content is therefore re-verified many times.

Inside :func:`verification_scope`, a validator that has *recomputed and matched*
the content checksum of its record may skip the remaining deterministic checks
when that exact content was already fully verified in the same scope. Outside a
scope every helper returns ``None`` and behaviour is unchanged: each validation
re-verifies from scratch. Keys are always recomputed content checksums, never
object identity or a claimed checksum; failures are never recorded; the memo
dies with the scope and nested scopes share the outermost one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any

_VERIFIED_CONTENT: ContextVar[dict[str, set[str]] | None] = ContextVar(
    "ntruth_verified_content", default=None
)
_MEMOIZED_RESULTS: ContextVar[dict[tuple[str, ...], Any] | None] = ContextVar(
    "ntruth_memoized_results", default=None
)


@contextmanager
def verification_scope() -> Iterator[None]:
    """Open (or join) the per-operation verification memo."""

    if _VERIFIED_CONTENT.get() is not None:
        yield
        return
    content_token = _VERIFIED_CONTENT.set({})
    results_token = _MEMOIZED_RESULTS.set({})
    try:
        yield
    finally:
        _MEMOIZED_RESULTS.reset(results_token)
        _VERIFIED_CONTENT.reset(content_token)


def within_verification_scope[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Run ``function`` inside :func:`verification_scope`."""

    @wraps(function)
    def scoped(*args: P.args, **kwargs: P.kwargs) -> R:
        with verification_scope():
            return function(*args, **kwargs)

    return scoped


def already_verified(namespace: str, checksum: str) -> bool:
    """True only inside a scope, for content fully verified earlier in it."""

    verified = _VERIFIED_CONTENT.get()
    return verified is not None and checksum in verified.get(namespace, ())


def record_verified(namespace: str, checksum: str) -> None:
    """Record fully verified content; a no-op outside a scope."""

    verified = _VERIFIED_CONTENT.get()
    if verified is not None:
        verified.setdefault(namespace, set()).add(checksum)


def memoized_results() -> dict[tuple[str, ...], Any] | None:
    """Scope-local memo of deterministic results; ``None`` outside a scope."""

    return _MEMOIZED_RESULTS.get()


__all__ = [
    "already_verified",
    "memoized_results",
    "record_verified",
    "verification_scope",
    "within_verification_scope",
]
