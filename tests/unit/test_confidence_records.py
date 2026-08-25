"""Test P5: ConfidenceRecord, calibrazione e OOD (PRD v9 §9.7, §12.8, §12.9)."""

from __future__ import annotations

import dataclasses
import math

import pytest

from ntruth.confidence.records import (
    BinningStrategy,
    CalibrationMetrics,
    ConfidenceRecord,
    ConfidenceRecordError,
    OODState,
    OODTrigger,
    ScoreOrigin,
    ScoreSemantics,
    TriggerSignal,
    _draw_cluster_index,
    cluster_bootstrap_ci,
    compute_bin_edges,
    compute_brier,
    compute_calibration_metrics,
    compute_error_per_bin,
    compute_expected_calibration_error,
    compute_log_loss,
    compute_risk_coverage_curve,
    evaluate_ood,
    false_high_confidence_critical_error_rate,
    reliability_diagram,
    selective_risk_at_coverage,
)

CALIBRATED_KWARGS = {
    "target_type": "assignment_unit_candidate",
    "score": 0.82,
    "score_semantics": ScoreSemantics.CALIBRATED_PROBABILITY_OF_LABEL_CORRECTNESS,
    "score_origin": ScoreOrigin.CALIBRATED_MODEL_OUTPUT,
    "model_runtime_fingerprint": "MR-001",
    "calibration_set_id": "CAL-P0-2026-01",
    "task_profile": "P0_assignment_explicit",
}


def make_record(**overrides: object) -> ConfidenceRecord:
    return ConfidenceRecord(**{**CALIBRATED_KWARGS, **overrides})  # type: ignore[arg-type]


class TestConfidenceRecordValidator:
    def test_valid_calibrated_record_accepted(self) -> None:
        record = make_record()
        assert record.score_semantics is ScoreSemantics.CALIBRATED_PROBABILITY_OF_LABEL_CORRECTNESS
        assert record.model_runtime_fingerprint == "MR-001"

    def test_verbalized_score_shown_as_probability_rejected(self) -> None:
        with pytest.raises(ConfidenceRecordError, match="UNQUALIFIED_MODEL_SCORE"):
            make_record(
                score_origin=ScoreOrigin.VERBALIZED_SCORE,
                score_semantics=ScoreSemantics.CALIBRATED_PROBABILITY_OF_LABEL_CORRECTNESS,
            )

    def test_uncalibrated_logit_as_ranking_score_rejected(self) -> None:
        with pytest.raises(ConfidenceRecordError):
            make_record(
                score_origin=ScoreOrigin.RAW_LOGIT,
                score_semantics=ScoreSemantics.RANKING_SCORE,
            )

    def test_uncalibrated_origin_forces_unqualified_semantics(self) -> None:
        record = make_record(
            score=0.7,
            score_origin=ScoreOrigin.RAW_LOGIT,
            score_semantics=ScoreSemantics.UNQUALIFIED_MODEL_SCORE,
            calibration_set_id=None,
        )
        assert record.score_semantics is ScoreSemantics.UNQUALIFIED_MODEL_SCORE

    def test_record_without_fingerprint_is_invalid(self) -> None:
        for blank in ("", "   "):
            with pytest.raises(ConfidenceRecordError, match="fingerprint"):
                make_record(model_runtime_fingerprint=blank)

    def test_calibrated_semantics_requires_calibration_set_id(self) -> None:
        with pytest.raises(ConfidenceRecordError, match="calibration_set_id"):
            make_record(calibration_set_id=None)

    def test_score_must_be_finite_in_unit_interval(self) -> None:
        for bad in (-0.1, 1.01, math.inf, math.nan):
            with pytest.raises(ConfidenceRecordError):
                make_record(score=bad)

    def test_immutability(self) -> None:
        record = make_record()
        with pytest.raises(dataclasses.FrozenInstanceError):
            record.score = 0.1
        mutated = dataclasses.replace(record, score=0.5)
        assert record.score == 0.82
        assert mutated.score == 0.5


class TestCalibrationMetrics:
    def test_brier_known_values(self) -> None:
        assert compute_brier([1.0, 0.0], [1, 0]) == pytest.approx(0.0)
        assert compute_brier([0.5, 0.5], [1, 0]) == pytest.approx(0.25)
        assert compute_brier([0.8], [0]) == pytest.approx(0.64)

    def test_log_loss_known_values(self) -> None:
        assert compute_log_loss([0.5, 0.5], [1, 0]) == pytest.approx(math.log(2))
        perfect = compute_log_loss([1.0 - 1e-9, 1e-9], [1, 0])
        assert perfect < 1e-6
        worst = compute_log_loss([1e-9, 1.0 - 1e-9], [1, 0])
        assert worst > 20.0

    def test_ece_known_case(self) -> None:
        scores = [1.0, 1.0, 0.0, 0.0]
        labels = [1, 0, 1, 0]
        assert compute_expected_calibration_error(scores, labels, bin_count=2) == (
            pytest.approx(0.5)
        )

    def test_ece_zero_for_perfectly_calibrated(self) -> None:
        scores = [0.75, 0.75, 0.75, 0.75]
        labels = [1, 1, 1, 0]
        assert compute_expected_calibration_error(scores, labels, bin_count=4) == (
            pytest.approx(0.0)
        )

    def test_error_per_bin_matches_diagram_bins(self) -> None:
        scores = [0.9, 0.85, 0.2, 0.1]
        labels = [1, 0, 0, 0]
        diagram = reliability_diagram(scores, labels, bin_count=10)
        errors = compute_error_per_bin(scores, labels, bin_count=10)
        assert errors == tuple(bin.absolute_error for bin in diagram.bins)

    def test_uniform_and_quantile_binning_edges(self) -> None:
        uniform = compute_bin_edges([0.1, 0.4, 0.9], bin_count=2)
        assert uniform == (0.0, 0.5, 1.0)
        quantile = compute_bin_edges(
            [0.1, 0.2, 0.3, 0.4], bin_count=2, binning=BinningStrategy.QUANTILE
        )
        assert quantile[0] == 0.0 and quantile[-1] == 1.0
        assert quantile == tuple(sorted(set(quantile)))

    def test_risk_coverage_curve_monotone_coverage(self) -> None:
        scores = [0.95, 0.9, 0.6, 0.3]
        labels = [1, 1, 0, 1]
        curve = compute_risk_coverage_curve(scores, labels)
        coverages = [point.coverage for point in curve]
        assert coverages == sorted(coverages)
        assert len(set(coverages)) == len(coverages)
        assert [point.selected_count for point in curve] == [1, 2, 3, 4]
        assert curve[-1].cumulative_risk == pytest.approx(0.25)

    def test_selective_risk_at_full_coverage_equals_error_rate(self) -> None:
        scores = [0.9, 0.8, 0.7, 0.6]
        labels = [1, 0, 1, 0]
        error_rate = sum(1 for label in labels if label == 0) / len(labels)
        assert selective_risk_at_coverage(scores, labels, 1.0) == pytest.approx(error_rate)

    def test_selective_risk_prefix_of_perfect_head(self) -> None:
        scores = [0.99, 0.98, 0.1, 0.05]
        labels = [1, 1, 0, 0]
        assert selective_risk_at_coverage(scores, labels, 0.5) == pytest.approx(0.0)

    def test_false_high_confidence_critical_error_rate_known_values(self) -> None:
        scores = [0.95, 0.92, 0.5, 0.93]
        labels = [1, 0, 1, 0]
        flags = [True, True, True, True]
        rate = false_high_confidence_critical_error_rate(scores, labels, flags)
        assert rate == pytest.approx(1 / 4)
        only_one_high = false_high_confidence_critical_error_rate(
            scores, labels, [False, False, False, True]
        )
        assert only_one_high == 0.0
        no_critical = false_high_confidence_critical_error_rate(
            scores, labels, [False, False, False, False]
        )
        assert no_critical == 0.0

    def test_compute_calibration_metrics_aggregates(self) -> None:
        metrics = compute_calibration_metrics(
            [0.9, 0.8, 0.2],
            [1, 0, 0],
            critical_flags=[True, False, False],
            target_coverage=1.0,
        )
        assert isinstance(metrics, CalibrationMetrics)
        assert metrics.brier == pytest.approx((0.01 + 0.64 + 0.04) / 3)
        assert metrics.selective_risk_at_target_coverage == pytest.approx(2 / 3)
        assert metrics.false_high_confidence_critical_error_rate == pytest.approx(1.0)

    def test_empty_or_mismatched_inputs_rejected(self) -> None:
        with pytest.raises(ConfidenceRecordError):
            compute_brier([], [])
        with pytest.raises(ConfidenceRecordError):
            compute_brier([0.5], [1, 0])
        with pytest.raises(ConfidenceRecordError):
            compute_brier([0.5], [2])


class TestClusterBootstrapCI:
    def test_deterministic_and_contains_point_estimate(self) -> None:
        scores = [0.9, 0.8, 0.3, 0.2, 0.7]
        labels = [1, 1, 0, 0, 0]
        clusters = ["doc-a", "doc-a", "doc-b", "doc-b", "doc-c"]
        first = cluster_bootstrap_ci(compute_brier, scores, labels, clusters, iterations=200)
        second = cluster_bootstrap_ci(compute_brier, scores, labels, clusters, iterations=200)
        assert first == second
        assert first.lower <= first.point_estimate <= first.upper
        assert first.method_id == "cluster-bootstrap-sha256-v1"
        assert first.cluster_count == 3
        assert first.point_estimate == pytest.approx(compute_brier(scores, labels))

    def test_seed_determines_the_resampling_sequence(self) -> None:
        cluster_count = 7
        left = [
            _draw_cluster_index(seed="seed-left", iteration=i, draw=0, cluster_count=cluster_count)
            for i in range(8)
        ]
        right = [
            _draw_cluster_index(seed="seed-right", iteration=i, draw=0, cluster_count=cluster_count)
            for i in range(8)
        ]
        assert left != right
        assert left == [
            _draw_cluster_index(seed="seed-left", iteration=i, draw=0, cluster_count=cluster_count)
            for i in range(8)
        ]


class TestOODFailClosed:
    def test_all_clear_is_in_profile(self) -> None:
        assert evaluate_ood(OODTrigger()) is OODState.IN_PROFILE

    def test_any_out_signal_dominates(self) -> None:
        trigger = OODTrigger(
            topology_not_covered=TriggerSignal.OUT_OF_PROFILE_SIGNAL,
            verifier_disagreement=TriggerSignal.UNKNOWN_SIGNAL,
        )
        assert evaluate_ood(trigger) is OODState.OUT_OF_PROFILE_DISTRIBUTION

    def test_unknown_is_contagious(self) -> None:
        trigger = OODTrigger(unusual_lineage=TriggerSignal.UNKNOWN_SIGNAL)
        assert evaluate_ood(trigger) is OODState.UNKNOWN
        shift_with_unknown = OODTrigger(
            new_vocabulary_or_artifacts=TriggerSignal.POSSIBLE_SHIFT_SIGNAL,
            unusual_lineage=TriggerSignal.UNKNOWN_SIGNAL,
        )
        assert evaluate_ood(shift_with_unknown) is OODState.UNKNOWN

    def test_shift_signal_yields_possible_shift(self) -> None:
        trigger = OODTrigger(verifier_disagreement=TriggerSignal.POSSIBLE_SHIFT_SIGNAL)
        assert evaluate_ood(trigger) is OODState.POSSIBLE_SHIFT

    def test_trigger_record_is_frozen(self) -> None:
        trigger = OODTrigger()
        with pytest.raises(dataclasses.FrozenInstanceError):
            trigger.verifier_disagreement = TriggerSignal.OUT_OF_PROFILE_SIGNAL
