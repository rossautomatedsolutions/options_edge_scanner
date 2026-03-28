"""Expected value calculations for option spread opportunities.

For vertical spreads we model expiration PnL across three regions:
1) below lower strike
2) between strikes
3) above upper strike

If region probabilities are provided, EV is computed as:
    EV = sum_i p_i * pnl_i - transaction_cost
where the between-strikes PnL uses a midpoint approximation.
"""

from __future__ import annotations

from typing import Any, Mapping

TRANSACTION_COST = 0.05
_EPSILON = 1e-12


def _get_numeric_field(spread_row: Mapping[str, Any], *field_names: str) -> float:
    """Extract the first present numeric field from a spread row mapping."""
    for field_name in field_names:
        if field_name in spread_row and spread_row[field_name] is not None:
            return float(spread_row[field_name])

    expected = ", ".join(field_names)
    raise KeyError(f"Missing required field. Expected one of: {expected}")


def _normalize_probability_weights(probability_weights: Mapping[str, Any]) -> dict[str, float]:
    """Normalize a 3-region probability map to sum to one.

    Accepted keys:
    - below / below_lower
    - between / between_strikes / middle
    - above / above_upper
    """
    below = float(
        probability_weights.get("below", probability_weights.get("below_lower", 0.0))
    )
    between = float(
        probability_weights.get(
            "between", probability_weights.get("between_strikes", probability_weights.get("middle", 0.0))
        )
    )
    above = float(probability_weights.get("above", probability_weights.get("above_upper", 0.0)))

    if min(below, between, above) < -_EPSILON:
        raise ValueError("Probability weights must be non-negative")

    total = below + between + above
    if total <= _EPSILON:
        raise ValueError("Probability weights must sum to a positive value")

    return {
        "below": max(0.0, below) / total,
        "between": max(0.0, between) / total,
        "above": max(0.0, above) / total,
    }


def _is_vertical_spread(spread_row: Mapping[str, Any]) -> bool:
    spread_type = str(spread_row.get("spread_type", "")).strip().lower()
    return spread_type in {
        "call_vertical",
        "put_vertical",
        "call_credit",
        "put_credit",
    }


def _extract_vertical_payoff_profile(spread_row: Mapping[str, Any]) -> dict[str, float | str]:
    """Resolve canonical payoff profile for vertical spreads."""
    spread_type = str(spread_row.get("spread_type", "")).strip().lower()
    lower = _get_numeric_field(spread_row, "strike_lower", "lower_strike", "long_strike", "short_put_strike")
    upper = _get_numeric_field(spread_row, "strike_upper", "upper_strike", "short_strike", "short_call_strike")
    low, high = sorted((lower, upper))
    width = high - low
    if width <= 0:
        raise ValueError("Vertical spread width must be positive")

    if spread_type in {"call_vertical", "put_vertical"}:
        max_profit = _get_numeric_field(spread_row, "max_profit", "payoff")
        max_loss = _get_numeric_field(spread_row, "cost", "max_loss", "loss")
        if max_profit < -_EPSILON or max_loss < -_EPSILON:
            raise ValueError("max_profit and max_loss must be non-negative")

        # For verticals, endpoint PnL magnitudes must satisfy:
        #   max_profit + max_loss == width
        # We use a tolerance for floating-point quote arithmetic.
        if abs((max_profit + max_loss) - width) > 1e-6:
            raise ValueError(
                "Inconsistent spread economics: expected max_profit + max_loss to equal strike width"
            )

        if spread_type == "call_vertical":
            pnl_by_region = {
                "below": -max_loss,
                "above": max_profit,
            }
        else:
            pnl_by_region = {
                "below": max_profit,
                "above": -max_loss,
            }
    elif spread_type in {"call_credit", "put_credit"}:
        max_profit = _get_numeric_field(spread_row, "credit", "max_profit", "payoff")
        max_loss = _get_numeric_field(spread_row, "max_loss", "loss")
        if max_profit < -_EPSILON or max_loss < -_EPSILON:
            raise ValueError("max_profit and max_loss must be non-negative")

        if abs((max_profit + max_loss) - width) > 1e-6:
            raise ValueError(
                "Inconsistent spread economics: expected max_profit + max_loss to equal strike width"
            )

        if spread_type == "call_credit":
            pnl_by_region = {
                "below": max_profit,
                "above": -max_loss,
            }
        else:
            pnl_by_region = {
                "below": -max_loss,
                "above": max_profit,
            }
    else:
        raise ValueError(f"Unsupported spread_type '{spread_type}' for vertical EV")

    middle_pnl = 0.5 * (float(pnl_by_region["below"]) + float(pnl_by_region["above"]))

    return {
        "spread_type": spread_type,
        "max_profit": float(max_profit),
        "max_loss": float(max_loss),
        "pnl_below": float(pnl_by_region["below"]),
        "pnl_between": float(middle_pnl),
        "pnl_above": float(pnl_by_region["above"]),
    }


def _binary_expected_value(spread_row: Mapping[str, Any], probability: float) -> tuple[float, float]:
    """Backward-compatible 2-point EV approximation."""
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

    Preferred mode for vertical spreads:
    - pass ``probability_weights`` with probabilities for below/between/above strike regions.

    Fallback mode:
    - if ``probability_weights`` is omitted, use a binary approximation with ``probability``.

    Notes on approximation:
    - The between-strikes region is represented by the average of endpoint PnL values,
      which assumes approximately uniform terminal-price density inside that region.
    """
    if probability_weights is not None and _is_vertical_spread(spread_row):
        weights = _normalize_probability_weights(probability_weights)
        profile = _extract_vertical_payoff_profile(spread_row)

        expected_value = (
            weights["below"] * float(profile["pnl_below"])
            + weights["between"] * float(profile["pnl_between"])
            + weights["above"] * float(profile["pnl_above"])
            - TRANSACTION_COST
        )

        max_profit = float(profile["max_profit"])
        max_loss = float(profile["max_loss"])
        # EV must remain within support bounds of the PnL distribution.
        lower_bound = -max_loss - TRANSACTION_COST
        upper_bound = max_profit - TRANSACTION_COST
        if expected_value < lower_bound:
            expected_value = lower_bound
        elif expected_value > upper_bound:
            expected_value = upper_bound

        edge_pct = (expected_value / max_loss * 100.0) if max_loss > _EPSILON else 0.0
        return {
            "expected_value": float(expected_value),
            "edge_pct": float(edge_pct),
            "ev_method": "three_region_midpoint",
            "pnl_below": float(profile["pnl_below"]),
            "pnl_between": float(profile["pnl_between"]),
            "pnl_above": float(profile["pnl_above"]),
            "prob_below": float(weights["below"]),
            "prob_between": float(weights["between"]),
            "prob_above": float(weights["above"]),
        }

    if probability is None:
        raise ValueError("probability is required when probability_weights is not provided")

    expected_value, edge_pct = _binary_expected_value(spread_row, probability)
    return {
        "expected_value": float(expected_value),
        "edge_pct": float(edge_pct),
        "ev_method": "binary",
    }
