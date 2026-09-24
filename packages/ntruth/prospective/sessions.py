"""Sessioni effimere e memory-bounded per gli artefatti prospettici D0."""

from __future__ import annotations

import secrets
from _thread import RLock
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

from ntruth.prospective.schema import ProspectiveCompileAuditEvent, ProspectiveD0Compilation
from ntruth.schemas.core import content_checksum, stable_id


class ProspectiveSessionNotFound(KeyError):
    """La sessione non esiste più o appartiene a un altro processo locale."""


@dataclass(frozen=True, slots=True)
class ProspectiveSession:
    id: str
    compilation: ProspectiveD0Compilation
    audit_trail: tuple[ProspectiveCompileAuditEvent, ...]


class ProspectiveSessionRegistry:
    """Registro locale bounded; nessun upload e nessuna persistenza implicita."""

    def __init__(self, *, max_sessions: int = 16) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions deve essere positivo")
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, ProspectiveSession] = OrderedDict()
        self._lock = RLock()

    def create(
        self,
        compilation: ProspectiveD0Compilation,
        *,
        actor_role: str,
        input_checksum: str,
    ) -> ProspectiveSession:
        with self._lock:
            recorded_at = datetime.now(UTC)
            output_checksum = content_checksum(compilation.model_dump(mode="json"))
            event = ProspectiveCompileAuditEvent(
                id=stable_id(
                    "aud",
                    "prospective-d0-compile",
                    actor_role,
                    recorded_at.isoformat(),
                    input_checksum,
                    output_checksum,
                ),
                actor_role=actor_role,
                recorded_at=recorded_at,
                input_checksum=input_checksum,
                output_checksum=output_checksum,
            )
            session = ProspectiveSession(
                id=secrets.token_urlsafe(18),
                compilation=compilation,
                audit_trail=(event,),
            )
            self._sessions[session.id] = session
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
            return session

    def get(self, session_id: str) -> ProspectiveSession:
        with self._lock:
            try:
                session = self._sessions[session_id]
            except KeyError as exc:
                raise ProspectiveSessionNotFound(session_id) from exc
            self._sessions.move_to_end(session_id)
            return session
