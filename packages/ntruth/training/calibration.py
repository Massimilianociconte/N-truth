"""Calibrazione locale delle confidence del parser AI.

La calibrazione usa soltanto il validation split congelato. Il test non entra mai
nella stima della temperatura o della soglia di astensione.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfidenceObservation:
    """Una confidence del modello e il suo esito rispetto al gold."""

    confidence: float
    correct: bool

    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence deve essere finita e compresa in [0, 1]")


def _clamp_probability(value: float, epsilon: float = 1e-6) -> float:
    return min(1.0 - epsilon, max(epsilon, value))


def probability_to_logit(probability: float) -> float:
    """Converte una probabilita in logit evitando gli infiniti ai bordi."""

    probability = _clamp_probability(probability)
    return math.log(probability / (1.0 - probability))


def calibrate_probability(probability: float, temperature: float) -> float:
    """Applica temperature scaling a una singola confidence."""

    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature deve essere positiva e finita")
    scaled = probability_to_logit(probability) / temperature
    if scaled >= 0:
        return 1.0 / (1.0 + math.exp(-scaled))
    exp_scaled = math.exp(scaled)
    return exp_scaled / (1.0 + exp_scaled)


def negative_log_likelihood(
    observations: tuple[ConfidenceObservation, ...], temperature: float
) -> float:
    if not observations:
        raise ValueError("servono osservazioni per calcolare la NLL")
    total = 0.0
    for observation in observations:
        probability = _clamp_probability(calibrate_probability(observation.confidence, temperature))
        total -= math.log(probability if observation.correct else 1.0 - probability)
    return total / len(observations)


def fit_temperature(
    observations: tuple[ConfidenceObservation, ...],
    *,
    lower: float = 0.05,
    upper: float = 20.0,
    iterations: int = 96,
) -> float:
    """Stima deterministicamente la temperatura sul validation split.

    La ricerca aurea opera nello spazio logaritmico. Sono richiesti entrambi gli
    esiti per evitare una calibrazione degenere su un validation set monoclasse.
    """

    if len(observations) < 2:
        raise ValueError("servono almeno due osservazioni di validazione")
    if len({observation.correct for observation in observations}) < 2:
        raise ValueError("la calibrazione richiede esempi corretti e incorretti")
    if lower <= 0 or upper <= lower or iterations < 1:
        raise ValueError("intervallo o numero di iterazioni non valido")

    left = math.log(lower)
    right = math.log(upper)
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    first = right - ratio * (right - left)
    second = left + ratio * (right - left)
    first_loss = negative_log_likelihood(observations, math.exp(first))
    second_loss = negative_log_likelihood(observations, math.exp(second))

    for _ in range(iterations):
        if first_loss <= second_loss:
            right = second
            second = first
            second_loss = first_loss
            first = right - ratio * (right - left)
            first_loss = negative_log_likelihood(observations, math.exp(first))
        else:
            left = first
            first = second
            first_loss = second_loss
            second = left + ratio * (right - left)
            second_loss = negative_log_likelihood(observations, math.exp(second))
    return math.exp((left + right) / 2.0)


def brier_score(observations: tuple[ConfidenceObservation, ...]) -> float:
    if not observations:
        raise ValueError("servono osservazioni per calcolare il Brier score")
    return sum(
        (observation.confidence - float(observation.correct)) ** 2 for observation in observations
    ) / len(observations)


def expected_calibration_error(
    observations: tuple[ConfidenceObservation, ...], *, bins: int = 10
) -> float:
    """ECE a bin equispaziati, con l'estremo 1 incluso nell'ultimo bin."""

    if not observations:
        raise ValueError("servono osservazioni per calcolare ECE")
    if bins < 2:
        raise ValueError("bins deve essere almeno 2")
    grouped: list[list[ConfidenceObservation]] = [[] for _ in range(bins)]
    for observation in observations:
        index = min(bins - 1, int(observation.confidence * bins))
        grouped[index].append(observation)
    total = len(observations)
    error = 0.0
    for group in grouped:
        if not group:
            continue
        mean_confidence = sum(item.confidence for item in group) / len(group)
        accuracy = sum(item.correct for item in group) / len(group)
        error += len(group) / total * abs(mean_confidence - accuracy)
    return error


def calibrated_observations(
    observations: tuple[ConfidenceObservation, ...], temperature: float
) -> tuple[ConfidenceObservation, ...]:
    return tuple(
        ConfidenceObservation(
            confidence=calibrate_probability(observation.confidence, temperature),
            correct=observation.correct,
        )
        for observation in observations
    )


def select_abstention_threshold(
    observations: tuple[ConfidenceObservation, ...],
    *,
    maximum_risk: float = 0.10,
    minimum_coverage_count: int = 10,
) -> dict[str, float | int | None]:
    """Sceglie sul validation set la copertura massima entro il rischio richiesto."""

    if not 0.0 <= maximum_risk < 1.0:
        raise ValueError("maximum_risk deve essere in [0, 1)")
    if minimum_coverage_count < 1:
        raise ValueError("minimum_coverage_count deve essere positivo")
    ordered = sorted(observations, key=lambda item: item.confidence, reverse=True)
    best: dict[str, float | int | None] = {
        "threshold": None,
        "covered": 0,
        "coverage": 0.0,
        "empirical_risk": None,
    }
    errors = 0
    for index, observation in enumerate(ordered, start=1):
        errors += int(not observation.correct)
        risk = errors / index
        if index >= minimum_coverage_count and risk <= maximum_risk:
            best = {
                "threshold": observation.confidence,
                "covered": index,
                "coverage": index / len(ordered),
                "empirical_risk": risk,
            }
    return best


def calibration_report(
    validation: tuple[ConfidenceObservation, ...],
    *,
    bins: int = 10,
    maximum_risk: float = 0.10,
    minimum_coverage_count: int = 10,
) -> dict[str, Any]:
    """Produce un artefatto JSON-serializzabile per model/system card."""

    temperature = fit_temperature(validation)
    calibrated = calibrated_observations(validation, temperature)
    return {
        "method": "temperature_scaling",
        "fit_split": "validation",
        "count": len(validation),
        "temperature": temperature,
        "before": {
            "negative_log_likelihood": negative_log_likelihood(validation, 1.0),
            "brier": brier_score(validation),
            "ece": expected_calibration_error(validation, bins=bins),
        },
        "after": {
            "negative_log_likelihood": negative_log_likelihood(validation, temperature),
            "brier": brier_score(calibrated),
            "ece": expected_calibration_error(calibrated, bins=bins),
        },
        "abstention": select_abstention_threshold(
            calibrated,
            maximum_risk=maximum_risk,
            minimum_coverage_count=minimum_coverage_count,
        ),
        "test_used_for_fit": False,
    }
