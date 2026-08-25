"""PRD v8 Quick Design service plus explicitly qualified v7 compatibility adapters.

The canonical service emits only verified deterministic v8 results and neutral
HANDOFF_ONLY reports.  Historical v7 helpers remain available only under names
that carry the ``v7`` qualifier.
"""

from ntruth.quick_design.export import (
    export_for_biostatistician as export_v7_for_biostatistician,
)
from ntruth.quick_design.export import freeze_plan as freeze_v7_plan
from ntruth.quick_design.guided import (
    GUIDED_QUESTION_PRIORITY_REVIEW_ISSUE_ID,
    GUIDED_SAMPLE_SHEET_MAX_ROWS,
    GuidedAnswerStatus,
    GuidedBuildAction,
    GuidedBuildState,
    GuidedIdSetAnswer,
    GuidedInterferenceAnswer,
    GuidedInterferenceStatus,
    GuidedPlannedGroup,
    GuidedQuestionPriorityState,
    GuidedQuickDesignBuildRequest,
    GuidedQuickDesignBuildResponse,
    GuidedQuickDesignConfirmation,
    GuidedQuickDesignDraft,
    GuidedQuickDesignReviewSnapshot,
    GuidedQuickDesignSummary,
    GuidedTextAnswer,
    GuidedTheoryQuestion,
    GuidedTimingAnswer,
    build_guided_quick_design,
    run_confirmed_guided_quick_design,
)
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
    validate_raw_wizard_submission,
)

from ntruth.quick_design.templates import (  # noqa: E402
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
    "GUIDED_QUESTION_PRIORITY_REVIEW_ISSUE_ID",
    "GUIDED_SAMPLE_SHEET_MAX_ROWS",
    "GuidedAnswerStatus",
    "GuidedBuildAction",
    "GuidedBuildState",
    "GuidedIdSetAnswer",
    "GuidedInterferenceAnswer",
    "GuidedInterferenceStatus",
    "GuidedPlannedGroup",
    "GuidedQuestionPriorityState",
    "GuidedQuickDesignBuildRequest",
    "GuidedQuickDesignBuildResponse",
    "GuidedQuickDesignConfirmation",
    "GuidedQuickDesignDraft",
    "GuidedQuickDesignReviewSnapshot",
    "GuidedQuickDesignSummary",
    "GuidedTextAnswer",
    "GuidedTheoryQuestion",
    "GuidedTimingAnswer",
    "QuickDesignScientificReviewRequired",
    "QuickDesignV7Answers",
    "QuickDesignV7Result",
    "QuickDesignV8Result",
    "QuickDesignV8Submission",
    "build_guided_quick_design",
    "build_v7_id_convention",
    "build_v7_methods_draft",
    "build_v7_sample_sheet",
    "export_v7_for_biostatistician",
    "freeze_v7_plan",
    "run_confirmed_guided_quick_design",
    "run_quick_design_v7_session",
    "run_quick_design_v8",
    "validate_raw_wizard_submission",
]
