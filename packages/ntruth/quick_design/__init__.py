"""Quick Design Session: valore prospettico immediato (PRD v7 §1.1, §6.1).

Fetta verticale minima per ``simple_cell_culture``: dominio + CLI + export,
senza UI. I target <10 minuti e <=3 domande sono ipotesi di prodotto
PROVISIONAL, non validatori scientifici.
"""

from ntruth.quick_design.export import (
    export_for_biostatistician as export_v7_for_biostatistician,
)
from ntruth.quick_design.export import freeze_plan as freeze_v7_plan
from ntruth.quick_design.session import (
    QuickDesignAnswers as QuickDesignV7Answers,
)
from ntruth.quick_design.session import (
    QuickDesignResult as QuickDesignV7Result,
)
from ntruth.quick_design.session import (
    run_quick_design_session as run_quick_design_v7_session,
)
from ntruth.quick_design.templates import (
    build_id_convention as build_v7_id_convention,
)
from ntruth.quick_design.templates import (
    build_methods_draft as build_v7_methods_draft,
)
from ntruth.quick_design.templates import (
    build_sample_sheet as build_v7_sample_sheet,
)
from ntruth.quick_design.v8 import (
    QuickDesignScientificReviewRequired,
    QuickDesignV8Result,
    QuickDesignV8Submission,
    run_quick_design_v8,
)

__all__ = [
    "QuickDesignScientificReviewRequired",
    "QuickDesignV7Answers",
    "QuickDesignV7Result",
    "QuickDesignV8Result",
    "QuickDesignV8Submission",
    "build_v7_id_convention",
    "build_v7_methods_draft",
    "build_v7_sample_sheet",
    "export_v7_for_biostatistician",
    "freeze_v7_plan",
    "run_quick_design_v7_session",
    "run_quick_design_v8",
]
