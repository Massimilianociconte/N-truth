"""Quick Design Session: valore prospettico immediato (PRD v7 §1.1, §6.1).

Fetta verticale minima per ``simple_cell_culture``: dominio + CLI + export,
senza UI. I target <10 minuti e <=3 domande sono ipotesi di prodotto
PROVISIONAL, non validatori scientifici.
"""

from ntruth.quick_design.templates import (
    build_id_convention,
    build_methods_draft,
    build_sample_sheet,
)

__all__ = [
    "QuickDesignAnswers",
    "QuickDesignResult",
    "build_id_convention",
    "build_methods_draft",
    "build_sample_sheet",
    "export_for_biostatistician",
    "freeze_plan",
    "run_quick_design_session",
]

# I moduli ``export`` e ``session`` non sono presenti in questo albero
# (snapshot v7-era): l'accesso resta fail-closed con errore esplicito.
_MISSING_MODULE_BY_NAME: dict[str, str] = {
    "export_for_biostatistician": "ntruth.quick_design.export",
    "freeze_plan": "ntruth.quick_design.export",
    "QuickDesignAnswers": "ntruth.quick_design.session",
    "QuickDesignResult": "ntruth.quick_design.session",
    "run_quick_design_session": "ntruth.quick_design.session",
}


def __getattr__(name: str) -> object:
    module = _MISSING_MODULE_BY_NAME.get(name)
    if module is not None:
        raise ImportError(f"{name!r} richiede il modulo {module}, assente in questo albero")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
