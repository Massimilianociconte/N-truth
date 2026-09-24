"""Gerarchia SESOI: dichiarata > prior > meta > pilot esterno/interno > Cohen.

Il manuale G*Power ricorda che, quando sono disponibili informazioni
specifiche sul problema, l'effect size va derivato da parametri pertinenti
anziche dalle convenzioni di Cohen. N-Truth applica questa precedenza in
modo fail-closed: senza SESOI utilizzabile il piano non viene emesso;
la convenzione di Cohen e sempre marcata come weak planning assumption.
"""

from __future__ import annotations

from ntruth.power.schema import PowerAssumption, SesoiRecord, SesoiSource

SESOI_PRECEDENCE: tuple[SesoiSource, ...] = (
    SesoiSource.DECLARED_SESOI,
    SesoiSource.BIOLOGICAL_PRIOR,
    SesoiSource.META_ANALYSIS,
    SesoiSource.EXTERNAL_PILOT,
    SesoiSource.INTERNAL_PILOT,
    SesoiSource.CONVENTIONAL_COHEN,
)


def sesoi_rank(source: SesoiSource) -> int:
    """Rango di precedenza (0 = piu forte); fail-closed su token ignoto."""

    try:
        return SESOI_PRECEDENCE.index(source)
    except ValueError as exc:
        raise ValueError(f"SesoiSource sconosciuta: {source!r}") from exc


def is_weak_sesoi(record: SesoiRecord) -> bool:
    """True solo per la convenzione di Cohen (livello piu debole)."""

    return record.source is SesoiSource.CONVENTIONAL_COHEN


def require_sesoi(record: SesoiRecord, effect_scale: str) -> SesoiRecord:
    """Fail-closed: la SESOI deve coprire la scala di effetto pianificata."""

    if record.effect_scale != effect_scale:
        raise ValueError(
            "SESOI su scala "
            f"{record.effect_scale!r} non copre la scala pianificata {effect_scale!r}: "
            "dichiarare una SESOI sulla scala corretta prima di pianificare."
        )
    if not record.rationale.strip():
        raise ValueError("SESOI senza rationale: dichiarare il fondamento prima di pianificare.")
    return record


def cohen_conventional_assumption(record: SesoiRecord) -> PowerAssumption:
    """Assunzione weak obbligatoria quando la SESOI e convenzionale."""

    return PowerAssumption(
        code="conventional_cohen_weak_assumption",
        message=(
            "Effect size da convenzione di Cohen "
            f"({record.effect_scale}={record.value:g}): weak planning assumption, "
            "non informazione sperimentale. Sostituire con SESOI dichiarata, "
            "prior biologico, meta-analisi o pilot esterno appena disponibile. "
            f"Fondamento dichiarato: {record.rationale}"
        ),
        blocking=False,
    )


__all__ = [
    "SESOI_PRECEDENCE",
    "cohen_conventional_assumption",
    "is_weak_sesoi",
    "require_sesoi",
    "sesoi_rank",
]
