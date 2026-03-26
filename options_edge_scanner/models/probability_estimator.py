"""Probability estimator utilities for spread outcomes."""

from __future__ import annotations

import math
from typing import Any, Mapping


_EPSILON = 1e-9
_TRADING_DAYS_PER_YEAR = 252.0


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


def estimate_probability_of_profit(spread_row: Mapping[str, Any]) -> float:
    """Estimate probability underlying price settles between strikes at expiration.

    Assumptions:
    - Underlying follows a lognormal distribution under a zero-drift model.
    - Implied volatility is annualized and held constant to expiration.
    - Profit is approximated as finishing between lower and upper strike.
    """
    spot = _read_float(spread_row, "underlying_price", "spot_price", "spot", "stock_price")
    lower_strike = _read_float(spread_row, "lower_strike", "short_put_strike", "put_strike")
    upper_strike = _read_float(spread_row, "upper_strike", "short_call_strike", "call_strike")
    implied_vol = _read_float(spread_row, "implied_volatility", "iv")
    time_to_expiration = _resolve_time_to_expiration(spread_row)

    if spot <= 0:
        raise ValueError("underlying_price must be positive")
    if lower_strike <= 0 or upper_strike <= 0:
        raise ValueError("strike values must be positive")
    if implied_vol <= 0:
        raise ValueError("implied_volatility must be positive")

    low, high = sorted((lower_strike, upper_strike))
    sigma_t = implied_vol * math.sqrt(time_to_expiration)
    sigma_t = max(sigma_t, _EPSILON)

    # Lognormal terminal distribution with E[log(ST/S0)] = -0.5 * sigma^2 * T.
    drift = -0.5 * (implied_vol ** 2) * time_to_expiration
    z_low = (math.log(low / spot) - drift) / sigma_t
    z_high = (math.log(high / spot) - drift) / sigma_t

    probability = _normal_cdf(z_high) - _normal_cdf(z_low)
    return max(0.0, min(1.0, probability))
