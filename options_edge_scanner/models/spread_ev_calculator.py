"""Expected value calculations for option spread opportunities."""

from typing import Mapping, Any

TRANSACTION_COST = 0.05


def _get_numeric_field(spread_row: Mapping[str, Any], field_name: str) -> float:
    """Extract a numeric field from a spread row mapping."""
    if field_name not in spread_row:
        raise KeyError(f"Missing required field '{field_name}' in spread_row")
    return float(spread_row[field_name])


def calculate_expected_value(spread_row: Mapping[str, Any], probability: float) -> dict:
    """Calculate expected value and edge percentage for a spread.

    Formula used:
        EV = p * payoff - (1 - p) * loss - transaction_cost
    """
    p = float(probability)
    payoff = _get_numeric_field(spread_row, "payoff")
    loss = _get_numeric_field(spread_row, "loss")

    expected_value = (p * payoff) - ((1.0 - p) * loss) - TRANSACTION_COST
    edge_pct = (expected_value / loss * 100.0) if loss else 0.0

    return {
        "expected_value": float(expected_value),
        "edge_pct": float(edge_pct),
    }
