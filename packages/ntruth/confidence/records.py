"""ConfidenceRecord, metriche di calibrazione e stato OOD (PRD v9 §9.7, §12.8, §12.9).

La confidence riguarda output AI candidati, non verità del claim. Score
verbalizzati o logit non calibrati non possono essere mostrati come probabilità.
Tutte le funzioni sono pure e deterministiche; il bootstrap cluster-aware usa
draw derivati da SHA-256 (nessuna dipendenza da RNG globale).
"""

from __future__ import annotations

import hashlib
import math
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

EPSILON = 1e-15
DEFAULT_BIN_COUNT = 10
DEFAULT_HIGH_CONFIDENCE_THRESHOLD = 0.9
DEFAULT_TARGET_COVERAGE = 0.8
DEFAULT_BOOTSTRAP_ITERATIONS = 2000
DEFAULT_BOOTSTRAP_CONFIDENCE_LEVEL = 0.95
DEFAULT_BOOTSTRAP_SEED = "ntruth-confidence-bootstrap-v1"
CLUSTER_BOOTSTRAP_METHOD_ID = "cluster-bootstrap-sha256-v1"


class ConfidenceRecordError(ValueError):
    """Violazione fail-closed dei contratti di confidence e calibrazione."""


class ScoreSemantics(StrEnum):
    CALIBRATED_PROBABILITY_OF_LABEL_CORRECTNESS = "CALIBRATED_PROBABILITY_OF_LABEL_CORRECTNESS"
    RANKING_SCORE = "RANKING_SCORE"
    UNQUALIFIED_MODEL_SCORE = "UNQUALIFIED_MODEL_SCORE"


class ScoreOrigin(StrEnum):
    VERBALIZED_SCORE = "VERBALIZED_SCORE"
    RAW_LOGIT = "RAW_LOGIT"
    CALIBRATED_MODEL_OUTPUT = "CALIBRATED_MODEL_OUTPUT"


class BinningStrategy(StrEnum):
    UNIFORM = "UNIFORM"
    QUANTILE = "QUANTILE"


class OODState(StrEnum):
    IN_PROFILE = "IN_PROFILE"
    POSSIBLE_SHIFT = "POSSIBLE_SHIFT"
    OUT_OF_PROFILE_DISTRIBUTION = "OUT_OF_PROFILE_DISTRIBUTION"
    UNKNOWN = "UNKNOWN"


class TriggerSignal(StrEnum):
    NOT_OBSERVED = "NOT_OBSERVED"
    POSSIBLE_SHIFT_SIGNAL = "POSSIBLE_SHIFT_SIGNAL"
    OUT_OF_PROFILE_SIGNAL = "OUT_OF_PROFILE_SIGNAL"
    UNKNOWN_SIGNAL = "UNKNOWN_SIGNAL"


_UNCALIBRATED_ORIGINS = frozenset({ScoreOrigin.VERBALIZED_SCORE, ScoreOrigin.RAW_LOGIT})


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ConfidenceRecordError(f"{field_name} obbligatorio e non vuoto")


def _validate_unit_interval(value: float, field_name: str) -> float:
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ConfidenceRecordError(f"{field_name} deve essere finito in [0, 1]")
    return score


@dataclass(frozen=True, slots=True)
class ConfidenceRecord:
    """Record di confidence per un output AI candidato (PRD §9.7)."""

    target_type: str
    score: float
    score_semantics: ScoreSemantics
    score_origin: ScoreOrigin
    model_runtime_fingerprint: str
    calibration_set_id: str | None = None
    task_profile: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.target_type, "target_type")
        _validate_unit_interval(self.score, "score")
        _require_text(self.model_runtime_fingerprint, "model_runtime_fingerprint")
        if self.calibration_set_id is not None:
            _require_text(self.calibration_set_id, "calibration_set_id")
        if self.task_profile is not None:
            _require_text(self.task_profile, "task_profile")
        if self.score_origin in _UNCALIBRATED_ORIGINS and (
            self.score_semantics is not ScoreSemantics.UNQUALIFIED_MODEL_SCORE
        ):
            raise ConfidenceRecordError(
                "score verbalizzato o logit non calibrato richiede "
                "score_semantics=UNQUALIFIED_MODEL_SCORE: non possono essere "
                "mostrati come probabilità calibrate"
            )
        if self.score_semantics is ScoreSemantics.CALIBRATED_PROBABILITY_OF_LABEL_CORRECTNESS:
            if self.score_origin is not ScoreOrigin.CALIBRATED_MODEL_OUTPUT:
                raise ConfidenceRecordError(
                    "CALIBRATED_PROBABILITY_OF_LABEL_CORRECTNESS richiede "
                    "score_origin=CALIBRATED_MODEL_OUTPUT"
                )
            if self.calibration_set_id is None:
                raise ConfidenceRecordError(
                    "CALIBRATED_PROBABILITY_OF_LABEL_CORRECTNESS richiede calibration_set_id"
                )


def _validated_pairs(scores: Sequence[float], labels: Sequence[int]) -> list[tuple[float, int]]:
    if len(scores) != len(labels):
        raise ConfidenceRecordError("scores e labels devono avere la stessa lunghezza")
    if not scores:
        raise ConfidenceRecordError("serve almeno un paio (score, label)")
    pairs: list[tuple[float, int]] = []
    for score, label in zip(scores, labels, strict=True):
        if label not in (0, 1):
            raise ConfidenceRecordError("label deve essere 0 o 1")
        pairs.append((_validate_unit_interval(score, "score"), int(label)))
    return pairs


def _interpolated_quantile(values: list[float], probability: float) -> float:
    if not 0.0 <= probability <= 1.0:
        raise ConfidenceRecordError("quantile fuori range")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower_index = math.floor(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * weight


def compute_bin_edges(
    scores: Sequence[float],
    *,
    bin_count: int = DEFAULT_BIN_COUNT,
    binning: BinningStrategy = BinningStrategy.UNIFORM,
) -> tuple[float, ...]:
    if bin_count < 1:
        raise ConfidenceRecordError("bin_count deve essere >= 1")
    if binning is BinningStrategy.UNIFORM:
        return tuple(index / bin_count for index in range(bin_count + 1))
    ordered = sorted(_validate_unit_interval(score, "score") for score in scores)
    if not ordered:
        raise ConfidenceRecordError("serve almeno uno score per il binning quantile")
    interior = tuple(
        _interpolated_quantile(ordered, index / bin_count) for index in range(1, bin_count)
    )
    return (0.0, *interior, 1.0)


def _bin_index(edges: tuple[float, ...], score: float) -> int:
    return min(max(bisect_right(edges, score) - 1, 0), len(edges) - 2)


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    bin_index: int
    lower: float
    upper: float
    sample_count: int
    mean_predicted: float
    empirical_accuracy: float
    absolute_error: float


@dataclass(frozen=True, slots=True)
class ReliabilityDiagramData:
    bin_count: int
    binning: BinningStrategy
    bin_edges: tuple[float, ...]
    bins: tuple[CalibrationBin, ...]
    sample_count: int


def reliability_diagram(
    scores: Sequence[float],
    labels: Sequence[int],
    *,
    bin_count: int = DEFAULT_BIN_COUNT,
    binning: BinningStrategy = BinningStrategy.UNIFORM,
) -> ReliabilityDiagramData:
    pairs = _validated_pairs(scores, labels)
    edges = compute_bin_edges(scores, bin_count=bin_count, binning=binning)
    grouped: dict[int, list[tuple[float, int]]] = {}
    for pair in pairs:
        grouped.setdefault(_bin_index(edges, pair[0]), []).append(pair)
    bins: list[CalibrationBin] = []
    for index in range(len(edges) - 1):
        members = grouped.get(index, [])
        if not members:
            continue
        mean_predicted = sum(score for score, _ in members) / len(members)
        accuracy = sum(label for _, label in members) / len(members)
        bins.append(
            CalibrationBin(
                bin_index=index,
                lower=edges[index],
                upper=edges[index + 1],
                sample_count=len(members),
                mean_predicted=mean_predicted,
                empirical_accuracy=accuracy,
                absolute_error=abs(accuracy - mean_predicted),
            )
        )
    return ReliabilityDiagramData(
        bin_count=bin_count,
        binning=binning,
        bin_edges=edges,
        bins=tuple(bins),
        sample_count=len(pairs),
    )


def compute_brier(scores: Sequence[float], labels: Sequence[int]) -> float:
    pairs = _validated_pairs(scores, labels)
    return sum((score - label) ** 2 for score, label in pairs) / len(pairs)


def compute_log_loss(scores: Sequence[float], labels: Sequence[int]) -> float:
    pairs = _validated_pairs(scores, labels)
    total = 0.0
    for score, label in pairs:
        clipped = min(max(score, EPSILON), 1.0 - EPSILON)
        total -= label * math.log(clipped) + (1 - label) * math.log(1.0 - clipped)
    return total / len(pairs)


def compute_expected_calibration_error(
    scores: Sequence[float],
    labels: Sequence[int],
    *,
    bin_count: int = DEFAULT_BIN_COUNT,
    binning: BinningStrategy = BinningStrategy.UNIFORM,
) -> float:
    diagram = reliability_diagram(scores, labels, bin_count=bin_count, binning=binning)
    return sum(
        bin_data.absolute_error * bin_data.sample_count / diagram.sample_count
        for bin_data in diagram.bins
    )


def compute_error_per_bin(
    scores: Sequence[float],
    labels: Sequence[int],
    *,
    bin_count: int = DEFAULT_BIN_COUNT,
    binning: BinningStrategy = BinningStrategy.UNIFORM,
) -> tuple[float, ...]:
    diagram = reliability_diagram(scores, labels, bin_count=bin_count, binning=binning)
    return tuple(bin_data.absolute_error for bin_data in diagram.bins)


@dataclass(frozen=True, slots=True)
class RiskCoveragePoint:
    selected_count: int
    coverage: float
    cumulative_risk: float


def compute_risk_coverage_curve(
    scores: Sequence[float], labels: Sequence[int]
) -> tuple[RiskCoveragePoint, ...]:
    pairs = _validated_pairs(scores, labels)
    total = len(pairs)
    order = sorted(range(total), key=lambda index: (-pairs[index][0], index))
    points: list[RiskCoveragePoint] = []
    errors = 0
    for selected, index in enumerate(order, start=1):
        errors += 1 - pairs[index][1]
        points.append(
            RiskCoveragePoint(
                selected_count=selected,
                coverage=selected / total,
                cumulative_risk=errors / selected,
            )
        )
    return tuple(points)


def selective_risk_at_coverage(
    scores: Sequence[float],
    labels: Sequence[int],
    coverage: float,
) -> float:
    _validated_pairs(scores, labels)
    _validate_unit_interval(coverage, "coverage")
    if coverage == 0.0:
        raise ConfidenceRecordError("coverage deve essere > 0")
    curve = compute_risk_coverage_curve(scores, labels)
    total = len(curve)
    selected = min(total, max(1, math.ceil(coverage * total)))
    return curve[selected - 1].cumulative_risk


def false_high_confidence_critical_error_rate(
    scores: Sequence[float],
    labels: Sequence[int],
    critical_flags: Sequence[bool],
    *,
    threshold: float = DEFAULT_HIGH_CONFIDENCE_THRESHOLD,
) -> float:
    pairs = _validated_pairs(scores, labels)
    if len(critical_flags) != len(pairs):
        raise ConfidenceRecordError("critical_flags deve avere la stessa lunghezza di scores")
    _validate_unit_interval(threshold, "threshold")
    critical_total = 0
    false_high_confidence = 0
    for (score, label), critical in zip(pairs, critical_flags, strict=True):
        if not critical:
            continue
        critical_total += 1
        if label == 1 and score >= threshold:
            false_high_confidence += 1
    if critical_total == 0:
        return 0.0
    return false_high_confidence / critical_total


@dataclass(frozen=True, slots=True)
class CalibrationMetrics:
    brier: float
    log_loss: float
    expected_calibration_error: float
    error_per_bin: tuple[float, ...]
    risk_coverage_curve: tuple[RiskCoveragePoint, ...]
    selective_risk_at_target_coverage: float
    false_high_confidence_critical_error_rate: float


def compute_calibration_metrics(
    scores: Sequence[float],
    labels: Sequence[int],
    *,
    critical_flags: Sequence[bool] | None = None,
    target_coverage: float = DEFAULT_TARGET_COVERAGE,
    high_confidence_threshold: float = DEFAULT_HIGH_CONFIDENCE_THRESHOLD,
    bin_count: int = DEFAULT_BIN_COUNT,
    binning: BinningStrategy = BinningStrategy.UNIFORM,
) -> CalibrationMetrics:
    pairs = _validated_pairs(scores, labels)
    if critical_flags is not None and len(critical_flags) != len(pairs):
        raise ConfidenceRecordError("critical_flags deve avere la stessa lunghezza di scores")
    flags: Sequence[bool] = critical_flags if critical_flags is not None else [False] * len(pairs)
    return CalibrationMetrics(
        brier=compute_brier(scores, labels),
        log_loss=compute_log_loss(scores, labels),
        expected_calibration_error=compute_expected_calibration_error(
            scores, labels, bin_count=bin_count, binning=binning
        ),
        error_per_bin=compute_error_per_bin(scores, labels, bin_count=bin_count, binning=binning),
        risk_coverage_curve=compute_risk_coverage_curve(scores, labels),
        selective_risk_at_target_coverage=selective_risk_at_coverage(
            scores, labels, target_coverage
        ),
        false_high_confidence_critical_error_rate=(
            false_high_confidence_critical_error_rate(
                scores, labels, list(flags), threshold=high_confidence_threshold
            )
        ),
    )


@dataclass(frozen=True, slots=True)
class BootstrapEstimate:
    method_id: str
    seed: str
    iterations: int
    confidence_level: float
    point_estimate: float
    lower: float
    upper: float
    cluster_count: int


def _draw_cluster_index(*, seed: str, iteration: int, draw: int, cluster_count: int) -> int:
    payload = f"{seed}\0{iteration}\0{draw}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % cluster_count


def cluster_bootstrap_ci(
    metric_fn: Callable[[Sequence[float], Sequence[int]], float],
    scores: Sequence[float],
    labels: Sequence[int],
    cluster_ids: Sequence[str],
    *,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    confidence_level: float = DEFAULT_BOOTSTRAP_CONFIDENCE_LEVEL,
    seed: str = DEFAULT_BOOTSTRAP_SEED,
) -> BootstrapEstimate:
    """Intervallo percentile cluster-aware: i cluster sono ricampionati interi."""
    pairs = _validated_pairs(scores, labels)
    if len(cluster_ids) != len(pairs):
        raise ConfidenceRecordError("cluster_ids deve avere la stessa lunghezza di scores")
    if iterations < 2:
        raise ConfidenceRecordError("iterations deve essere >= 2")
    _validate_unit_interval(confidence_level, "confidence_level")
    if confidence_level in (0.0, 1.0):
        raise ConfidenceRecordError("confidence_level deve essere in aperto (0, 1)")
    _require_text(seed, "seed")
    cleaned_clusters = [cluster.strip() for cluster in cluster_ids]
    if any(not cluster for cluster in cleaned_clusters):
        raise ConfidenceRecordError("cluster id obbligatori e non vuoti")
    unique_ids: list[str] = []
    seen: set[str] = set()
    for cluster in cleaned_clusters:
        if cluster not in seen:
            seen.add(cluster)
            unique_ids.append(cluster)
    points_by_cluster: dict[str, list[tuple[float, int]]] = {}
    for pair, cluster in zip(pairs, cleaned_clusters, strict=True):
        points_by_cluster.setdefault(cluster, []).append(pair)
    point_estimate = metric_fn(scores, labels)
    if not math.isfinite(point_estimate):
        raise ConfidenceRecordError("metrica puntuale non finita")
    bootstrap_values: list[float] = []
    cluster_count = len(unique_ids)
    for iteration in range(iterations):
        resampled_scores: list[float] = []
        resampled_labels: list[int] = []
        for draw in range(cluster_count):
            chosen = unique_ids[
                _draw_cluster_index(
                    seed=seed,
                    iteration=iteration,
                    draw=draw,
                    cluster_count=cluster_count,
                )
            ]
            for score, label in points_by_cluster[chosen]:
                resampled_scores.append(score)
                resampled_labels.append(label)
        value = metric_fn(resampled_scores, resampled_labels)
        if not math.isfinite(value):
            raise ConfidenceRecordError("metrica bootstrap non finita")
        bootstrap_values.append(value)
    alpha = (1.0 - confidence_level) / 2.0
    lower = _interpolated_quantile(bootstrap_values, alpha)
    upper = _interpolated_quantile(bootstrap_values, 1.0 - alpha)
    return BootstrapEstimate(
        method_id=CLUSTER_BOOTSTRAP_METHOD_ID,
        seed=seed,
        iterations=iterations,
        confidence_level=confidence_level,
        point_estimate=point_estimate,
        lower=min(lower, point_estimate),
        upper=max(upper, point_estimate),
        cluster_count=cluster_count,
    )


@dataclass(frozen=True, slots=True)
class OODTrigger:
    """Trigger OOD del §12.9; ogni segnale è tri-stato (fail-closed)."""

    topology_not_covered: TriggerSignal = TriggerSignal.NOT_OBSERVED
    new_vocabulary_or_artifacts: TriggerSignal = TriggerSignal.NOT_OBSERVED
    incompatible_role_type: TriggerSignal = TriggerSignal.NOT_OBSERVED
    verifier_disagreement: TriggerSignal = TriggerSignal.NOT_OBSERVED
    unusual_lineage: TriggerSignal = TriggerSignal.NOT_OBSERVED

    def signals(self) -> tuple[TriggerSignal, ...]:
        return (
            self.topology_not_covered,
            self.new_vocabulary_or_artifacts,
            self.incompatible_role_type,
            self.verifier_disagreement,
            self.unusual_lineage,
        )


def evaluate_ood(trigger: OODTrigger) -> OODState:
    """Fail-closed: qualsiasi OUT domina; UNKNOWN è contagioso; OOD non viene forzato."""
    signals = trigger.signals()
    if any(signal is TriggerSignal.OUT_OF_PROFILE_SIGNAL for signal in signals):
        return OODState.OUT_OF_PROFILE_DISTRIBUTION
    if any(signal is TriggerSignal.UNKNOWN_SIGNAL for signal in signals):
        return OODState.UNKNOWN
    if any(signal is TriggerSignal.POSSIBLE_SHIFT_SIGNAL for signal in signals):
        return OODState.POSSIBLE_SHIFT
    return OODState.IN_PROFILE
