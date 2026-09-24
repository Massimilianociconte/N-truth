"""Regressioni per i confini di import dei package pubblici."""

from __future__ import annotations

import subprocess
import sys


def test_reporting_imports_in_a_clean_python_process() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import ntruth.reporting; "
                "from ntruth.schemas import Report; "
                "assert Report.__name__ == 'Report'"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_graph_and_rules_do_not_import_the_ai_parser_runtime() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import ntruth.graph, ntruth.rules; "
                "loaded = sorted(name for name in sys.modules "
                "if name == 'ntruth.parser_ai' or name.startswith('ntruth.parser_ai.')); "
                "assert not loaded, loaded"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr


def test_runtime_resources_do_not_import_training() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import ntruth.runtime_resources; "
                "import ntruth.runtime_resources.budget_io; "
                "import ntruth.runtime_resources.manager; "
                "import ntruth.runtime_resources.schema; "
                "loaded = sorted(name for name in sys.modules "
                "if name == 'ntruth.training' or name.startswith('ntruth.training.')); "
                "assert not loaded, loaded"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr


def test_parser_ai_does_not_import_rules_engine() -> None:
    """Candidate generation must not pull deterministic scientific consequences."""

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import ntruth.parser_ai; "
                "import ntruth.parser_ai.stages; "
                "import ntruth.parser_ai.contract; "
                "loaded = sorted(name for name in sys.modules "
                "if name == 'ntruth.rules' or name.startswith('ntruth.rules.')); "
                "assert not loaded, loaded"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr


def test_candidate_graph_set_has_no_final_n_or_verdict_fields() -> None:
    from ntruth.parser_ai.stages import CandidateGraphSet

    fields = set(CandidateGraphSet.model_fields)
    forbidden = {
        "n_independent",
        "independent_n",
        "determinability",
        "verdict",
        "statistical_test",
        "paper_score",
        "pseudoreplication",
    }
    assert fields.isdisjoint(forbidden), fields & forbidden
