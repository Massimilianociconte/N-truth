"""Budget prestazioni della baseline deterministica (PRD NFR-06/NFR-07).

La fixture e sintetica: il test impedisce regressioni macroscopiche ma non chiude DOD-12, che
richiede corpus MVP rappresentativo e prova sul Mac M5 Pro di riferimento.
"""

from __future__ import annotations

import platform
import resource
import time
from pathlib import Path

import pytest
from conftest import analyze_directory

pytestmark = pytest.mark.performance


def test_typical_rules_only_block_stays_within_prd_budget(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "scientific_fixtures" / "uc02_preparations"
    started = time.perf_counter()
    result = analyze_directory(source, tmp_path / "benchmark-project")
    elapsed = time.perf_counter() - started

    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = raw_rss if platform.system() == "Darwin" else raw_rss * 1024

    assert result.report.blocks
    assert elapsed < 60 * len(result.report.blocks), (
        f"{elapsed:.3f}s per {len(result.report.blocks)} blocchi, target <60s/blocco"
    )
    assert rss_bytes < 20 * 1024**3, f"peak RSS {rss_bytes / 1024**3:.2f} GiB, target <20 GiB"
