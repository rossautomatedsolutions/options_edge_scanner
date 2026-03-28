"""Expected value calculations for option spread opportunities.

This module uses a breakeven-aligned binary EV approximation for vertical spreads:

    EV_gross = P(win) * avg_profit + P(loss) * avg_loss

with a simple maximum-value-point assumption:
- avg_profit ~= max_profit
- avg_loss ~= -max_loss

Then transaction cost is applied consistently as:

    EV_net = EV_gross - TRANSACTION_COST
"""

from __future__ import annotations

from typing import Any, Mapping

TRANSACTION_COST = 0.05
_EPSILON = 1e-12

_SUPPORTED_SPREAD_TYPES = {
    "bull_call_debit",
    "bear_put_debit",
    "bull_put_credit",
    "bear_call_credit",
}


def _get_numeric_field(spread_row: Mapping[str, Any], *field_names: str) -> float:
    """Extract the first present numeric field from a spread row mapping."""
    for field_name in field_names:
        if field_name in spread_row and spread_row[field_name] is not None:
            return float(spread_row[field_name])

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
        "max_profit": float(max_profit),
        "max_loss": float(max_loss),
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

    Preferred mode for supported vertical spreads:
    - pass ``probability_weights`` containing win/loss probabilities.

    Fallback mode:
    - if ``probability_weights`` is omitted, use a generic binary approximation
      with ``probability``.
    """
    spread_type = str(spread_row.get("spread_type", "")).strip().lower()
    if spread_type in _SUPPORTED_SPREAD_TYPES:
        if probability_weights is not None:
            probs = _normalize_win_loss_probabilities(probability_weights)
        elif probability is not None:
            p = float(probability)
            if p < -_EPSILON or p > 1.0 + _EPSILON:
                raise ValueError("probability must be in [0, 1]")
            p = min(max(p, 0.0), 1.0)
            probs = {"win": p, "loss": 1.0 - p}
        else:
            raise ValueError(
                "probability or probability_weights is required for supported spread types"
            )

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
