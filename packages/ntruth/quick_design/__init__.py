"""Quick Design Session: valore prospettico immediato (PRD v7 §1.1, §6.1).

Fetta verticale minima per ``simple_cell_culture``: dominio + CLI + export,
senza UI. I target <10 minuti e <=3 domande sono ipotesi di prodotto
PROVISIONAL, non validatori scientifici.
"""

from ntruth.quick_design.export import export_for_biostatistician, freeze_plan
from ntruth.quick_design.session import (
    QuickDesignAnswers,
    QuickDesignResult,
    run_quick_design_session,
)
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
