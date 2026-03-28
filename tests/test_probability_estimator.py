"""Unit tests for options_edge_scanner.models.probability_estimator."""

import pytest

from options_edge_scanner.models.probability_estimator import estimate_probability_of_profit


SPOT_PRICE = 100.0
IV_20_PERCENT = 0.20
ONE_MONTH = 30.0 / 252.0


def _base_row(**overrides):
    """Create synthetic spread input with fixed spot and reasonable volatility."""
    row = {
        "underlying_price": SPOT_PRICE,
        "lower_strike": 95.0,
        "upper_strike": 105.0,
        "implied_volatility": IV_20_PERCENT,
        "time_to_expiration": ONE_MONTH,
    }
    row.update(overrides)
    return row


def test_monotonicity_above_tail_decreases_as_breakeven_increases() -> None:
    """As BE rises, P(S_T > BE) must decrease."""
    # bull_call_debit => PoP = P(S_T > (lower_strike + debit))
    low_be = estimate_probability_of_profit(
        _base_row(spread_type="bull_call_debit", lower_strike=90.0, debit=6.0)  # BE=96
    )
    mid_be = estimate_probability_of_profit(
        _base_row(spread_type="bull_call_debit", lower_strike=90.0, debit=10.0)  # BE=100
    )
    high_be = estimate_probability_of_profit(
        _base_row(spread_type="bull_call_debit", lower_strike=90.0, debit=14.0)  # BE=104
    )

    assert low_be > mid_be > high_be


def test_monotonicity_below_tail_increases_as_breakeven_increases() -> None:
    """As BE rises, P(S_T < BE) must increase."""
    # bear_call_credit => PoP = P(S_T < (lower_strike + credit))
    low_be = estimate_probability_of_profit(
        _base_row(spread_type="bear_call_credit", lower_strike=92.0, credit=4.0)  # BE=96
    )
    mid_be = estimate_probability_of_profit(
        _base_row(spread_type="bear_call_credit", lower_strike=92.0, credit=8.0)  # BE=100
    )
    high_be = estimate_probability_of_profit(
        _base_row(spread_type="bear_call_credit", lower_strike=92.0, credit=12.0)  # BE=104
    )

    assert low_be < mid_be < high_be


@pytest.mark.parametrize(
    "spread_row",
    [
        _base_row(spread_type="bull_call_debit", lower_strike=94.0, debit=5.0),
        _base_row(spread_type="bear_put_debit", upper_strike=106.0, debit=6.0),
        _base_row(spread_type="bull_put_credit", upper_strike=106.0, credit=5.0),
        _base_row(spread_type="bear_call_credit", lower_strike=94.0, credit=5.0),
    ],
)
def test_probability_bounds_between_zero_and_one(spread_row: dict) -> None:
    """All returned probabilities must be valid probabilities."""
    probability = estimate_probability_of_profit(spread_row)
    assert 0.0 <= probability <= 1.0


def test_deep_itm_vs_deep_otm_for_above_tail() -> None:
    """Above-tail spreads should approach 1 when deep ITM and 0 when deep OTM."""
    # bull_call_debit => P(S_T > BE)
    deep_itm = estimate_probability_of_profit(
        _base_row(spread_type="bull_call_debit", lower_strike=50.0, upper_strike=70.0, debit=2.0, time_to_expiration=0.5)
    )
    deep_otm = estimate_probability_of_profit(
        _base_row(spread_type="bull_call_debit", lower_strike=180.0, upper_strike=200.0, debit=10.0, time_to_expiration=0.5)
    )

    assert deep_itm > 0.99
    assert deep_otm < 0.01


def test_deep_itm_vs_deep_otm_for_below_tail() -> None:
    """Below-tail spreads should approach 1 when deep ITM and 0 when deep OTM."""
    # bear_put_debit => P(S_T < BE), with BE = upper_strike - debit
    deep_itm = estimate_probability_of_profit(
        _base_row(spread_type="bear_put_debit", lower_strike=170.0, upper_strike=180.0, debit=2.0, time_to_expiration=0.5)
    )
    deep_otm = estimate_probability_of_profit(
        _base_row(spread_type="bear_put_debit", lower_strike=20.0, upper_strike=30.0, debit=25.0, time_to_expiration=0.5)
    )

    assert deep_itm > 0.99
    assert deep_otm < 0.01


def test_near_expiration_behaves_like_step_function() -> None:
    """As T -> 0, probabilities should become almost binary around spot vs BE."""
    tiny_t = 1e-8

    above_tail_when_be_below_spot = estimate_probability_of_profit(
        _base_row(
            spread_type="bull_call_debit",
            lower_strike=90.0,
            debit=8.0,  # BE=98 < spot
            implied_volatility=IV_20_PERCENT,
            time_to_expiration=tiny_t,
        )
    )
    above_tail_when_be_above_spot = estimate_probability_of_profit(
        _base_row(
            spread_type="bull_call_debit",
            lower_strike=90.0,
            debit=12.0,  # BE=102 > spot
            implied_volatility=IV_20_PERCENT,
            time_to_expiration=tiny_t,
        )
    )

    below_tail_when_be_above_spot = estimate_probability_of_profit(
        _base_row(
            spread_type="bear_call_credit",
            lower_strike=101.0,
            credit=1.0,  # BE=102 > spot
            implied_volatility=IV_20_PERCENT,
            time_to_expiration=tiny_t,
        )
    )
    below_tail_when_be_below_spot = estimate_probability_of_profit(
        _base_row(
            spread_type="bear_call_credit",
            lower_strike=97.0,
            credit=1.0,  # BE=98 < spot
            implied_volatility=IV_20_PERCENT,
            time_to_expiration=tiny_t,
        )
    )

    assert above_tail_when_be_below_spot > 0.99
    assert above_tail_when_be_above_spot < 0.01
    assert below_tail_when_be_above_spot > 0.99
    assert below_tail_when_be_below_spot < 0.01


@pytest.mark.parametrize(
    ("spread_type", "short_strike", "long_strike", "credit", "expected_range"),
    [
        ("put_credit", 105.0, 95.0, 5.0, (0.4, 0.6)),
        ("call_credit", 95.0, 105.0, 5.0, (0.4, 0.6)),
    ],
)
def test_credit_spread_aliases_accept_scanner_strike_keys(
    spread_type: str,
    short_strike: float,
    long_strike: float,
    credit: float,
    expected_range: tuple[float, float],
) -> None:
    """Scanner-style rows with short/long strikes should be supported."""
    probability = estimate_probability_of_profit(
        {
            "underlying_price": SPOT_PRICE,
            "short_strike": short_strike,
            "long_strike": long_strike,
            "implied_volatility": IV_20_PERCENT,
            "time_to_expiration": ONE_MONTH,
            "spread_type": spread_type,
            "credit": credit,
        }
    )
    low, high = expected_range
    assert low <= probability <= high
