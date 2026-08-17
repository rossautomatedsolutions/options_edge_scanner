"""Probability estimator utilities for spread outcomes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


_EPSILON = 1e-9
_TRADING_DAYS_PER_YEAR = 252.0
LOGNORMAL_BREAKEVEN_MODEL_NAME = "lognormal_breakeven"
LOGNORMAL_BREAKEVEN_MODEL_VERSION = "1"
TERMINAL_BREAKEVEN_EVENT_NAME = "terminal_underlying_crosses_spread_breakeven"
TERMINAL_BREAKEVEN_EVENT_HORIZON = "expiration"


@dataclass(frozen=True)
class SpreadProbabilityEvent:
    """Canonical event definition for one spread probability prediction."""

    spread_type: str
    predicted_event_name: str
    predicted_event_direction: str
    predicted_event_operator: str
    predicted_event_threshold: float
    predicted_event_horizon: str


def _normal_cdf(value: float) -> float:
    """Compute the standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _read_float(spread_row: Mapping[str, Any], *candidate_keys: str) -> float:
    """Read the first available numeric value from candidate keys."""
    for key in candidate_keys:
        if key in spread_row and spread_row[key] is not None:
            return float(spread_row[key])

    joined_keys = ", ".join(candidate_keys)
    raise KeyError(f"Missing required key; expected one of: {joined_keys}")


def _resolve_time_to_expiration(spread_row: Mapping[str, Any]) -> float:
    """Resolve year-fraction time to expiration from row data."""
    if "time_to_expiration" in spread_row and spread_row["time_to_expiration"] is not None:
        return max(float(spread_row["time_to_expiration"]), _EPSILON)

    days = _read_float(spread_row, "days_to_expiration", "dte")
    return max(days / _TRADING_DAYS_PER_YEAR, _EPSILON)


def resolve_probability_of_profit_event(spread_row: Mapping[str, Any]) -> SpreadProbabilityEvent:
    """Resolve the exact terminal event represented by the current PoP model."""
    lower_strike = _read_float(
        spread_row,
        "lower_strike",
        "short_put_strike",
        "put_strike",
        "short_strike",
        "long_strike",
    )
    upper_strike = _read_float(
        spread_row,
        "upper_strike",
        "short_call_strike",
        "call_strike",
        "long_strike",
        "short_strike",
    )
    low, high = sorted((lower_strike, upper_strike))
    spread_type = str(spread_row.get("spread_type", "")).strip().lower()

    if spread_type == "bull_call_debit":
        debit = _read_float(spread_row, "debit", "cost", "max_loss", "loss")
        threshold = low + debit
        direction = "above"
        operator = ">"
    elif spread_type == "bear_put_debit":
        debit = _read_float(spread_row, "debit", "cost", "max_loss", "loss")
        threshold = high - debit
        direction = "below"
        operator = "<"
    elif spread_type in {"bull_put_credit", "put_credit"}:
        credit = _read_float(spread_row, "credit", "max_profit", "payoff")
        threshold = high - credit
        direction = "above"
        operator = ">"
    elif spread_type in {"bear_call_credit", "call_credit"}:
        credit = _read_float(spread_row, "credit", "max_profit", "payoff")
        threshold = low + credit
        direction = "below"
        operator = "<"
    else:
        raise ValueError(
            "Unsupported spread_type for probability_of_profit; "
            "expected one of: bull_put_credit, put_credit, "
            "bear_call_credit, call_credit, bull_call_debit, bear_put_debit"
        )

    if threshold <= 0:
        raise ValueError("breakeven must be positive")

    return SpreadProbabilityEvent(
        spread_type=spread_type,
        predicted_event_name=TERMINAL_BREAKEVEN_EVENT_NAME,
        predicted_event_direction=direction,
        predicted_event_operator=operator,
        predicted_event_threshold=float(threshold),
        predicted_event_horizon=TERMINAL_BREAKEVEN_EVENT_HORIZON,
    )


def estimate_probability_of_profit(spread_row: Mapping[str, Any]) -> float:
    """Estimate probability of profit for a vertical spread at expiration.

    Assumptions:
    - Underlying follows a lognormal distribution under a zero-drift model.
    - Implied volatility is annualized and held constant to expiration.
    - Profit probability is computed from spread breakeven as a one-sided tail event.
    """
    spot = _read_float(spread_row, "underlying_price", "spot_price", "spot", "stock_price")
    lower_strike = _read_float(
        spread_row,
        "lower_strike",
        "short_put_strike",
        "put_strike",
        "short_strike",
        "long_strike",
    )
    upper_strike = _read_float(
        spread_row,
        "upper_strike",
        "short_call_strike",
        "call_strike",
        "long_strike",
        "short_strike",
    )
    implied_vol = _read_float(spread_row, "implied_volatility", "iv")
    time_to_expiration = _resolve_time_to_expiration(spread_row)
    spread_type = str(spread_row.get("spread_type", "")).strip().lower()

    if spot <= 0:
        raise ValueError("underlying_price must be positive")
    if lower_strike <= 0 or upper_strike <= 0:
        raise ValueError("strike values must be positive")
    if implied_vol <= 0:
        raise ValueError("implied_volatility must be positive")

    sigma_t = implied_vol * math.sqrt(time_to_expiration)
    sigma_t = max(sigma_t, _EPSILON)
    probability_event = resolve_probability_of_profit_event(spread_row)
    breakeven = probability_event.predicted_event_threshold

    # Lognormal terminal distribution at expiration:
    # ln(ST / S0) ~ N(-0.5 * sigma^2 * T, sigma^2 * T)
    # Transform breakeven into this log-space, then evaluate the standard
    # normal CDF to recover P(ST <= BE) and convert to the required tail.
    drift = -0.5 * (implied_vol ** 2) * time_to_expiration
    z_be = (math.log(breakeven / spot) - drift) / sigma_t
    cdf_at_be = _normal_cdf(z_be)

    if probability_event.predicted_event_direction == "above":
        probability_raw = 1.0 - cdf_at_be
    else:
        probability_raw = cdf_at_be

    if not math.isfinite(probability_raw):
        raise ValueError("Estimated probability must be finite")
    if probability_raw < -1e-12 or probability_raw > 1.0 + 1e-12:
        raise ValueError("Estimated probability must be within [0, 1]")

    # Numerical safety for tiny floating-point overshoots.
    probability = max(0.0, min(1.0, probability_raw))
    return probability
