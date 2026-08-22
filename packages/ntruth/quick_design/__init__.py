"""Quick Design Session: artefatti deterministici (PRD v7 §1.1, §6.1).

Su questo branch (snapshot pre-migrazione v8) è disponibile solo il modulo
``templates``: la sessione interattiva (``session``) e l'export per il
biostatistico (``export``) appartengono alla linea PRD v7 su ``main`` e
dipendono da ``bootstrap_core``/``causal_context``/``determinability_v7``,
che qui non esistono. I target <10 minuti e <=3 domande restano ipotesi di
prodotto PROVISIONAL, non validatori scientifici.
"""

from ntruth.quick_design.templates import (
    SAMPLE_SHEET_COLUMNS,
    build_id_convention,
    build_methods_draft,
    build_sample_sheet,
)

__all__ = [
    "SAMPLE_SHEET_COLUMNS",
    "build_id_convention",
    "build_methods_draft",
    "build_sample_sheet",
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
