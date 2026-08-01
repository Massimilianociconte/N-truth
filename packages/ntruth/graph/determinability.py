"""Derivazione deterministica dello stato di determinabilita del disegno."""

from __future__ import annotations

from ntruth.design.schema import DesignCompilation
from ntruth.schemas.core import Determinability
from ntruth.schemas.experiment import ExperimentBlock, Inferability


def derive_determinability(
    block: ExperimentBlock,
    compilation: DesignCompilation,
) -> Determinability:
    """Classifica lo stato senza usare confidence come sostituto dei fatti.

    I conflitti espliciti hanno precedenza. Scenari condizionali rappresentano
    grafi alternativi, mentre un contratto incompleto o una qualunque unita non
    inferibile impongono astensione. ``DETERMINATE`` significa soltanto che il
    grafo corrente e lo scope richiesto sono completi, non che il disegno sia
    scientificamente valido.
    """

    if any(item.status == "unresolved" for item in block.contradictions):
        return Determinability.CONFLICTING_INFORMATION

    if any(
        assessment.conditional_scenarios
        or assessment.inferability in {Inferability.CONDITIONAL, Inferability.REQUIRES_CONFIRMATION}
        for assessment in block.unit_assessments
    ):
        return Determinability.MULTIPLE_PLAUSIBLE_GRAPHS

    if (
        not block.unit_assessments
        or compilation.abstained
        or any(
            assessment.inferability is not Inferability.INFERABLE
            for assessment in block.unit_assessments
        )
    ):
        return Determinability.INDETERMINATE

    return Determinability.DETERMINATE
