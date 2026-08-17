"""Versioned probability-model interfaces for scanner and calibration workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from options_edge_scanner.models.probability_estimator import (
    LOGNORMAL_BREAKEVEN_MODEL_NAME,
    LOGNORMAL_BREAKEVEN_MODEL_VERSION,
    estimate_probability_of_profit,
    resolve_probability_of_profit_event,
)


@dataclass(frozen=True)
class ProbabilityModelPrediction:
    """One fully described probability prediction."""

    probability: float
    probability_model_name: str
    probability_model_version: str
    predicted_event_name: str
    predicted_event_direction: str
    predicted_event_operator: str
    predicted_event_threshold: float
    predicted_event_horizon: str


class SpreadProbabilityModel(Protocol):
    """Minimal interface for versioned spread probability models."""

    @property
    def probability_model_name(self) -> str: ...

    @property
    def probability_model_version(self) -> str: ...

    def predict(self, spread_row: Mapping[str, Any]) -> ProbabilityModelPrediction: ...


@dataclass(frozen=True)
class LognormalBreakevenProbabilityModel:
    """Current baseline lognormal breakeven-tail probability model."""

    probability_model_name: str = LOGNORMAL_BREAKEVEN_MODEL_NAME
    probability_model_version: str = LOGNORMAL_BREAKEVEN_MODEL_VERSION

    def predict(self, spread_row: Mapping[str, Any]) -> ProbabilityModelPrediction:
        """Return one versioned probability prediction for a spread row."""
        probability_event = resolve_probability_of_profit_event(spread_row)
        probability = estimate_probability_of_profit(spread_row)
        return ProbabilityModelPrediction(
            probability=float(probability),
            probability_model_name=self.probability_model_name,
            probability_model_version=self.probability_model_version,
            predicted_event_name=probability_event.predicted_event_name,
            predicted_event_direction=probability_event.predicted_event_direction,
            predicted_event_operator=probability_event.predicted_event_operator,
            predicted_event_threshold=float(probability_event.predicted_event_threshold),
            predicted_event_horizon=probability_event.predicted_event_horizon,
        )


DEFAULT_SPREAD_PROBABILITY_MODEL = LognormalBreakevenProbabilityModel()


def predict_spread_probability(
    spread_row: Mapping[str, Any],
    *,
    model: SpreadProbabilityModel | None = None,
) -> ProbabilityModelPrediction:
    """Return one versioned spread probability prediction."""
    active_model = model or DEFAULT_SPREAD_PROBABILITY_MODEL
    return active_model.predict(spread_row)
