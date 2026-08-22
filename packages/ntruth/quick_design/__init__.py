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
