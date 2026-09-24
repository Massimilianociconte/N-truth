"""Read-only audit counterexamples; run from repository root with PYTHONPATH=packages."""

from ntruth.confidence.records import compute_calibration_metrics
from ntruth.parsers.base import RawDocument
from ntruth.parsers.pdf import _grid_to_table
from ntruth.parsers.tabular import _build_table
from ntruth.training.calibration import ConfidenceObservation, select_abstention_threshold

for label in (0, 1):
    result = compute_calibration_metrics([0.99], [label], critical_flags=[True])
    print("critical confidence", label, result)
observations = tuple(ConfidenceObservation(0.9, i < 10) for i in range(20))
result = select_abstention_threshold(observations)
print("threshold report", result)
selected = [o for o in observations if o.confidence >= result["threshold"]]
print(
    "actual selected",
    len(selected),
    "actual risk",
    sum(not o.correct for o in selected) / len(selected),
)
doc = RawDocument(parser="csv")
table = _build_table("sample", iter([["animal", "animal", "animal_1"], ["A", "B", "C"]]), doc)
print("tabular collision", table, doc.status, doc.warnings)
table = _grid_to_table([["id", "n"]] + [[str(i), "1"] for i in range(2002)], "t")
print("pdf table truncation", len(table.rows), table.warnings)
