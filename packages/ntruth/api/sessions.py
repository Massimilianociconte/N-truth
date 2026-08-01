"""Sessioni locali per correzione, ricalcolo e download controllato."""

from __future__ import annotations

import secrets
from _thread import RLock
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ntruth.application import AnalysisExecution
from ntruth.artifacts import remap_artifact_paths, staged_directory
from ntruth.corrections import (
    CorrectionLedger,
    candidate_annotations_payload,
    recalculate_corrected_block,
    write_candidate_annotations,
)
from ntruth.pipeline import BlockAnalysis, replace_block_analysis
from ntruth.reporting import write_all
from ntruth.reporting.privacy import build_privacy_audit, build_share_readiness
from ntruth.rules.loader import load_ruleset
from ntruth.schemas.experiment import Correction


class SessionNotFound(KeyError):
    """La sessione API non esiste più o appartiene a un altro processo."""


class SessionBlockNotFound(KeyError):
    """Il blocco richiesto non fa parte della sessione."""


class SessionArtifactNotFound(KeyError):
    """Nome artefatto non registrato nella sessione."""


CorrectionFactory = Callable[[CorrectionLedger], Correction]


@dataclass(frozen=True, slots=True)
class SessionUpdate:
    """Risultato di una navigazione del ledger con ricalcolo completo."""

    execution: AnalysisExecution
    ledger: CorrectionLedger
    elapsed_ms: float
    candidate_payload: dict[str, object]
    candidate_artifact_name: str


@dataclass(slots=True)
class AnalysisSession:
    """Stato effimero del processo; gli audit vengono anche persistiti su file."""

    id: str
    execution: AnalysisExecution
    ledgers: dict[str, CorrectionLedger] = field(default_factory=dict)
    candidate_artifacts: dict[str, Path] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def block_analysis(self, block_id: str) -> BlockAnalysis:
        with self._lock:
            return self._block_analysis(block_id)

    def _block_analysis(self, block_id: str) -> BlockAnalysis:
        analysis = next(
            (item for item in self.execution.result.block_analyses if item.block.id == block_id),
            None,
        )
        if analysis is None:
            raise SessionBlockNotFound(block_id)
        return analysis

    def ledger(self, block_id: str) -> CorrectionLedger:
        with self._lock:
            return self._ledger(block_id)

    def _ledger(self, block_id: str) -> CorrectionLedger:
        existing = self.ledgers.get(block_id)
        if existing is not None:
            return existing
        ledger = CorrectionLedger.start(self._block_analysis(block_id).block)
        self.ledgers[block_id] = ledger
        return ledger

    def apply(self, block_id: str, correction: Correction) -> SessionUpdate:
        """Applica una correzione gia costruita, rifiutandone una sequenza stale."""

        with self._lock:
            return self._commit(block_id, self._ledger(block_id).apply(correction))

    def apply_generated(self, block_id: str, factory: CorrectionFactory) -> SessionUpdate:
        """Costruisce ID/sequence sullo stato corrente e commette sotto lo stesso lock."""

        with self._lock:
            ledger = self._ledger(block_id)
            return self._commit(block_id, ledger.apply(factory(ledger)))

    def undo(self, block_id: str) -> SessionUpdate:
        with self._lock:
            return self._commit(block_id, self._ledger(block_id).undo())

    def redo(self, block_id: str) -> SessionUpdate:
        with self._lock:
            return self._commit(block_id, self._ledger(block_id).redo())

    def artifact(self, name: str) -> Path:
        with self._lock:
            paths = {**self.execution.written, **self.candidate_artifacts}
            path = paths.get(name)
            if path is None or not path.is_file():
                raise SessionArtifactNotFound(name)
            return path

    def _commit(self, block_id: str, ledger: CorrectionLedger) -> SessionUpdate:
        """Pubblica una revisione completa prima di rendere visibile il nuovo head."""

        original = self._block_analysis(block_id)
        ruleset = load_ruleset(
            self.execution.result.report.versions.ruleset_id,
            self.execution.result.report.versions.ruleset_version,
        )
        recalculation = recalculate_corrected_block(
            original,
            ledger,
            ruleset,
            lang=self.execution.result.report.language,
        )
        result = replace_block_analysis(
            self.execution.result,
            recalculation.analysis,
        )
        prospective_ledgers = {**self.ledgers, block_id: ledger}
        privacy_audit = build_privacy_audit(result.document, result.report)
        share_readiness = build_share_readiness(
            privacy_audit,
            assets=self.execution.share_readiness.assets,
        )
        next_revision = self.execution.revision + 1
        revision_dir = self.execution.run_dir / "revisions" / f"{next_revision:04d}"
        candidate_name = f"candidate_{block_id}"
        with staged_directory(revision_dir) as staging:
            staged_candidates: dict[str, Path] = {}
            for candidate_block_id, candidate_ledger in sorted(prospective_ledgers.items()):
                name = f"candidate_{candidate_block_id}"
                path = staging / f"candidate-annotations-{candidate_block_id}.json"
                staged_candidates[name] = write_candidate_annotations(candidate_ledger, path)
            staged_written = write_all(
                result.report,
                staging,
                additional_artifacts=staged_candidates,
                privacy_audit=privacy_audit,
                share_readiness=share_readiness,
            )

        written = remap_artifact_paths(
            staged_written,
            source_root=staging,
            destination_root=revision_dir,
        )
        candidate_artifacts = {
            name: path for name, path in written.items() if name.startswith("candidate_")
        }
        # Stato in memoria aggiornato soltanto dopo la pubblicazione atomica.
        self.candidate_artifacts = candidate_artifacts
        self.ledgers[block_id] = ledger
        self.execution = AnalysisExecution(
            result=result,
            ingest=self.execution.ingest,
            written=written,
            transparency=self.execution.transparency,
            run_id=self.execution.run_id,
            run_dir=self.execution.run_dir,
            privacy_audit=privacy_audit,
            share_readiness=share_readiness,
            revision=next_revision,
        )
        payload = candidate_annotations_payload(ledger)
        return SessionUpdate(
            execution=self.execution,
            ledger=ledger,
            elapsed_ms=recalculation.elapsed_ms,
            candidate_payload=payload,
            candidate_artifact_name=candidate_name,
        )


class SessionRegistry:
    """Registro memory-bounded; nessun dato viene inviato fuori dal processo."""

    def __init__(self, *, max_sessions: int = 16) -> None:
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, AnalysisSession] = OrderedDict()
        self._lock = RLock()

    def create(self, execution: AnalysisExecution) -> AnalysisSession:
        with self._lock:
            session_id = secrets.token_urlsafe(18)
            session = AnalysisSession(id=session_id, execution=execution)
            self._sessions[session_id] = session
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
            return session

    def get(self, session_id: str) -> AnalysisSession:
        with self._lock:
            try:
                session = self._sessions[session_id]
            except KeyError as exc:
                raise SessionNotFound(session_id) from exc
            self._sessions.move_to_end(session_id)
            return session
