"""Expected value calculations for option spread opportunities.

For scanner-supported debit verticals with spot/IV/time inputs available, this
module computes the exact expected terminal payoff under the repo's current
lognormal terminal-price assumption. When those distribution inputs are not
available, it falls back to the older binary approximation.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

TRANSACTION_COST = 0.05
_EPSILON = 1e-12
_TRADING_DAYS_PER_YEAR = 252.0

_SUPPORTED_SPREAD_TYPES = {
    "bull_call_debit",
    "bear_put_debit",
    "bull_put_credit",
    "bear_call_credit",
}
_EXACT_DISTRIBUTIONAL_SPREAD_TYPES = {
    "bull_call_debit",
    "bear_put_debit",
}


def _get_numeric_field(spread_row: Mapping[str, Any], *field_names: str) -> float:
    """Extract the first present numeric field from a spread row mapping."""
    for field_name in field_names:
        if field_name in spread_row and spread_row[field_name] is not None:
            try:
                value = float(spread_row[field_name])
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                return value

    expected = ", ".join(field_names)
    raise KeyError(f"Missing required field. Expected one of: {expected}")


def _normalize_win_loss_probabilities(probability_weights: Mapping[str, Any]) -> dict[str, float]:
    """Validate and normalize a win/loss probability map.

    Accepted keys:
    - win / probability_of_profit / p_win
    - loss / probability_of_loss / p_loss
    """
    win = float(
        probability_weights.get(
            "win",
            probability_weights.get("probability_of_profit", probability_weights.get("p_win", 0.0)),
        )
    )
    loss = float(
        probability_weights.get(
            "loss",
            probability_weights.get("probability_of_loss", probability_weights.get("p_loss", 0.0)),
        )
    )

    if win < -_EPSILON or win > 1.0 + _EPSILON:
        raise ValueError("win probability must be in [0, 1]")
    if loss < -_EPSILON or loss > 1.0 + _EPSILON:
        raise ValueError("loss probability must be in [0, 1]")

    total = win + loss
    if abs(total - 1.0) > 1e-8:
        raise ValueError("win and loss probabilities must sum to 1")

    return {
        "win": min(max(win, 0.0), 1.0),
        "loss": min(max(loss, 0.0), 1.0),
    }


def _normal_cdf(value: float) -> float:
    """Compute the standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _resolve_time_to_expiration(spread_row: Mapping[str, Any]) -> float:
    """Resolve year-fraction time to expiration from row data."""
    if "time_to_expiration" in spread_row and spread_row["time_to_expiration"] is not None:
        return max(float(spread_row["time_to_expiration"]), _EPSILON)

    if "days_to_expiration" in spread_row and spread_row["days_to_expiration"] is not None:
        return max(float(spread_row["days_to_expiration"]) / _TRADING_DAYS_PER_YEAR, _EPSILON)

    if "dte" in spread_row and spread_row["dte"] is not None:
        return max(float(spread_row["dte"]) / _TRADING_DAYS_PER_YEAR, _EPSILON)

    raise KeyError("Missing required field. Expected one of: time_to_expiration, days_to_expiration, dte")


def _resolve_distribution_inputs(spread_row: Mapping[str, Any]) -> dict[str, float] | None:
    """Return spot/IV/time inputs for exact vertical EV when available."""
    try:
        spot = _get_numeric_field(spread_row, "underlying_price", "spot_price", "spot", "stock_price")
        implied_vol = _get_numeric_field(spread_row, "implied_volatility", "iv")
        time_to_expiration = _resolve_time_to_expiration(spread_row)
    except (KeyError, ValueError):
        return None

    if (
        not math.isfinite(spot)
        or not math.isfinite(implied_vol)
        or not math.isfinite(time_to_expiration)
        or spot <= 0
        or implied_vol <= 0
        or time_to_expiration <= 0
    ):
        return None

    return {
        "spot": float(spot),
        "implied_volatility": float(implied_vol),
        "time_to_expiration": float(time_to_expiration),
    }


def _d1_d2(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> tuple[float, float]:
    """Return the Black-Scholes-style d1/d2 pair under zero carry."""
    sigma_t = implied_vol * math.sqrt(time_to_expiration)
    if sigma_t <= _EPSILON:
        sigma_t = _EPSILON
    d1 = (
        math.log(spot / strike) + (0.5 * implied_vol * implied_vol * time_to_expiration)
    ) / sigma_t
    d2 = d1 - sigma_t
    return d1, d2


def _call_expectation(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> float:
    """Return E[(S_T - K)+] under the current lognormal scanner assumption."""
    if time_to_expiration <= _EPSILON or implied_vol <= _EPSILON:
        return max(spot - strike, 0.0)
    d1, d2 = _d1_d2(spot, strike, implied_vol, time_to_expiration)
    return float((spot * _normal_cdf(d1)) - (strike * _normal_cdf(d2)))


def _put_expectation(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> float:
    """Return E[(K - S_T)+] under the current lognormal scanner assumption."""
    if time_to_expiration <= _EPSILON or implied_vol <= _EPSILON:
        return max(strike - spot, 0.0)
    d1, d2 = _d1_d2(spot, strike, implied_vol, time_to_expiration)
    return float((strike * _normal_cdf(-d2)) - (spot * _normal_cdf(-d1)))


def _probability_above(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> float:
    """Return P(S_T > K) under the current lognormal scanner assumption."""
    if time_to_expiration <= _EPSILON or implied_vol <= _EPSILON:
        if spot > strike:
            return 1.0
        if spot < strike:
            return 0.0
        return 0.5
    _d1, d2 = _d1_d2(spot, strike, implied_vol, time_to_expiration)
    return float(_normal_cdf(d2))


def _probability_below(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> float:
    """Return P(S_T < K) under the current lognormal scanner assumption."""
    return float(1.0 - _probability_above(spot, strike, implied_vol, time_to_expiration))


def _expected_spot_above(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> float:
    """Return E[S_T * 1{S_T > K}] under the current lognormal scanner assumption."""
    if time_to_expiration <= _EPSILON or implied_vol <= _EPSILON:
        if spot > strike:
            return float(spot)
        if spot < strike:
            return 0.0
        return float(spot * 0.5)
    d1, _d2 = _d1_d2(spot, strike, implied_vol, time_to_expiration)
    return float(spot * _normal_cdf(d1))


def _expected_spot_below(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> float:
    """Return E[S_T * 1{S_T < K}] under the current lognormal scanner assumption."""
    return float(spot - _expected_spot_above(spot, strike, implied_vol, time_to_expiration))


def _extract_spread_payoff_profile(spread_row: Mapping[str, Any]) -> dict[str, float | str]:
    """Resolve canonical payoff profile for supported vertical spreads."""
    spread_type = str(spread_row.get("spread_type", "")).strip().lower()
    if spread_type not in _SUPPORTED_SPREAD_TYPES:
        raise ValueError(
            "Unsupported spread_type for EV; expected one of: "
            "bull_call_debit, bear_put_debit, bull_put_credit, bear_call_credit"
        )

    lower = _get_numeric_field(
        spread_row,
        "strike_lower",
        "lower_strike",
        "long_strike",
        "short_put_strike",
    )
    upper = _get_numeric_field(
        spread_row,
        "strike_upper",
        "upper_strike",
        "short_strike",
        "short_call_strike",
    )
    low, high = sorted((lower, upper))
    width = high - low
    if width <= 0:
        raise ValueError("Vertical spread width must be positive")

    if spread_type in {"bull_call_debit", "bear_put_debit"}:
        max_profit = _get_numeric_field(spread_row, "max_profit", "payoff")
        max_loss = _get_numeric_field(spread_row, "debit", "cost", "max_loss", "loss")
    else:
        max_profit = _get_numeric_field(spread_row, "credit", "max_profit", "payoff")
        max_loss = _get_numeric_field(spread_row, "max_loss", "loss")

    if max_profit < -_EPSILON or max_loss < -_EPSILON:
        raise ValueError("max_profit and max_loss must be non-negative")

    if abs((max_profit + max_loss) - width) > 1e-6:
        raise ValueError(
            "Inconsistent spread economics: expected max_profit + max_loss to equal strike width"
        )

    return {
        "spread_type": spread_type,
        "lower_strike": float(low),
        "upper_strike": float(high),
        "max_profit": float(max_profit),
        "max_loss": float(max_loss),
    }


def _build_exact_vertical_ev(spread_row: Mapping[str, Any]) -> dict[str, float | str] | None:
    """Return exact EV for scanner-supported debit verticals when inputs allow it."""
    spread_type = str(spread_row.get("spread_type", "")).strip().lower()
    if spread_type not in _EXACT_DISTRIBUTIONAL_SPREAD_TYPES:
        return None

    distribution_inputs = _resolve_distribution_inputs(spread_row)
    if distribution_inputs is None:
        return None

    profile = _extract_spread_payoff_profile(spread_row)
    spot = distribution_inputs["spot"]
    implied_vol = distribution_inputs["implied_volatility"]
    time_to_expiration = distribution_inputs["time_to_expiration"]
    low = float(profile["lower_strike"])
    high = float(profile["upper_strike"])
    max_profit = float(profile["max_profit"])
    max_loss = float(profile["max_loss"])

    if spread_type == "bull_call_debit":
        expected_payoff = _call_expectation(spot, low, implied_vol, time_to_expiration) - _call_expectation(
            spot,
            high,
            implied_vol,
            time_to_expiration,
        )
        breakeven = low + max_loss
        prob_win = _probability_above(spot, breakeven, implied_vol, time_to_expiration)
        prob_high = _probability_above(spot, high, implied_vol, time_to_expiration)
        prob_between = max(prob_win - prob_high, 0.0)
        expected_spot_between = max(
            _expected_spot_above(spot, breakeven, implied_vol, time_to_expiration)
            - _expected_spot_above(spot, high, implied_vol, time_to_expiration),
            0.0,
        )
        profit_contrib = (
            expected_spot_between
            - (breakeven * prob_between)
            + (max_profit * prob_high)
        )
    else:
        expected_payoff = _put_expectation(spot, high, implied_vol, time_to_expiration) - _put_expectation(
            spot,
            low,
            implied_vol,
            time_to_expiration,
        )
        breakeven = high - max_loss
        prob_below_low = _probability_below(spot, low, implied_vol, time_to_expiration)
        prob_win = _probability_below(spot, breakeven, implied_vol, time_to_expiration)
        prob_between = max(prob_win - prob_below_low, 0.0)
        expected_spot_between = max(
            _expected_spot_below(spot, breakeven, implied_vol, time_to_expiration)
            - _expected_spot_below(spot, low, implied_vol, time_to_expiration),
            0.0,
        )
        profit_contrib = (
            (max_profit * prob_below_low)
            + (breakeven * prob_between)
            - expected_spot_between
        )

    expected_value_gross = float(expected_payoff - max_loss)
    prob_win = min(max(float(prob_win), 0.0), 1.0)
    prob_loss = 1.0 - prob_win
    profit_contrib = max(float(profit_contrib), 0.0)
    loss_contrib = float(expected_value_gross - profit_contrib)

    if prob_win > _EPSILON:
        avg_profit = min(max(profit_contrib / prob_win, 0.0), max_profit)
    else:
        avg_profit = 0.0

    if prob_loss > _EPSILON:
        avg_loss = min(max(loss_contrib / prob_loss, -max_loss), 0.0)
    else:
        avg_loss = 0.0

    expected_value = float(expected_value_gross - TRANSACTION_COST)
    edge_pct = (expected_value / max_loss * 100.0) if max_loss > _EPSILON else 0.0
    return {
        "expected_value": expected_value,
        "edge_pct": float(edge_pct),
        "ev_method": "lognormal_vertical_exact",
        "avg_profit": float(avg_profit),
        "avg_loss": float(avg_loss),
        "prob_win": float(prob_win),
        "prob_loss": float(prob_loss),
    }


def _binary_expected_value(spread_row: Mapping[str, Any], probability: float) -> tuple[float, float]:
    """Backward-compatible binary EV approximation for generic opportunities."""
    p = float(probability)
    if p < -_EPSILON or p > 1.0 + _EPSILON:
        raise ValueError("probability must be in [0, 1]")
    p = min(max(p, 0.0), 1.0)

    payoff = _get_numeric_field(spread_row, "payoff", "max_profit", "credit")
    loss = _get_numeric_field(spread_row, "loss", "max_loss", "cost")

    expected_value = (p * payoff) - ((1.0 - p) * loss) - TRANSACTION_COST
    edge_pct = (expected_value / loss * 100.0) if abs(loss) > _EPSILON else 0.0
    return float(expected_value), float(edge_pct)


def calculate_expected_value(
    spread_row: Mapping[str, Any],
    probability: float | None = None,
    probability_weights: Mapping[str, Any] | None = None,
) -> dict[str, float | str]:
    """Calculate expected value and edge percentage.

    Preferred mode for scanner-supported debit verticals:
    - use exact lognormal payoff expectation when spot/IV/time are available.

    Secondary mode for supported vertical spreads:
    - pass ``probability_weights`` containing win/loss probabilities.

    Fallback mode:
    - if ``probability_weights`` is omitted, use a generic binary approximation
      with ``probability``.
    """
    exact_result = _build_exact_vertical_ev(spread_row)
    if exact_result is not None:
        return exact_result

    spread_type = str(spread_row.get("spread_type", "")).strip().lower()
    if spread_type in _SUPPORTED_SPREAD_TYPES:
        if probability_weights is None:
            raise ValueError(
                "probability_weights is required for supported spread types; "
                "expected win/loss probabilities"
            )

        probs = _normalize_win_loss_probabilities(probability_weights)
        profile = _extract_spread_payoff_profile(spread_row)

        max_profit = float(profile["max_profit"])
        max_loss = float(profile["max_loss"])

        avg_profit = max_profit
        avg_loss = -max_loss

        expected_value_gross = (probs["win"] * avg_profit) + (probs["loss"] * avg_loss)

        # EV support bounds before transaction cost.
        expected_value_gross = min(max(expected_value_gross, -max_loss), max_profit)

        expected_value = expected_value_gross - TRANSACTION_COST
        edge_pct = (expected_value / max_loss * 100.0) if max_loss > _EPSILON else 0.0
        return {
            "expected_value": float(expected_value),
            "edge_pct": float(edge_pct),
            "ev_method": "breakeven_binary_mvp",
            "avg_profit": float(avg_profit),
            "avg_loss": float(avg_loss),
            "prob_win": float(probs["win"]),
            "prob_loss": float(probs["loss"]),
        }

    if probability_weights is not None:
        raise ValueError(
            "Unsupported spread_type for probability_weights mode; "
            "expected one of: bull_call_debit, bear_put_debit, bull_put_credit, bear_call_credit"
        )

    if probability is None:
        raise ValueError("probability is required when probability_weights is not provided")

    expected_value, edge_pct = _binary_expected_value(spread_row, probability)
    return {
        "expected_value": float(expected_value),
        "edge_pct": float(edge_pct),
        "ev_method": "binary",
    }
