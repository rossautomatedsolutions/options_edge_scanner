import pytest

from options_edge_scanner.models.probability_estimator import estimate_probability_of_profit


def _base_row(**overrides):
    row = {
        "underlying_price": 100.0,
        "lower_strike": 95.0,
        "upper_strike": 105.0,
        "implied_volatility": 0.25,
        "time_to_expiration": 0.5,
    }
    row.update(overrides)
    return row


def test_monotonicity_for_above_tail_probability_decreases_with_higher_breakeven() -> None:
    # bull_call_debit => PoP = P(S_T > lower_strike + debit)
    low_be = estimate_probability_of_profit(
        _base_row(spread_type="bull_call_debit", lower_strike=90.0, debit=4.0)
    )
    mid_be = estimate_probability_of_profit(
        _base_row(spread_type="bull_call_debit", lower_strike=90.0, debit=10.0)
    )
    high_be = estimate_probability_of_profit(
        _base_row(spread_type="bull_call_debit", lower_strike=90.0, debit=16.0)
    )

    assert low_be > mid_be > high_be


def test_monotonicity_for_below_tail_probability_increases_with_higher_breakeven() -> None:
    # bear_call_credit => PoP = P(S_T < lower_strike + credit)
    low_be = estimate_probability_of_profit(
        _base_row(spread_type="bear_call_credit", lower_strike=90.0, credit=1.0)
    )
    mid_be = estimate_probability_of_profit(
        _base_row(spread_type="bear_call_credit", lower_strike=90.0, credit=8.0)
    )
    high_be = estimate_probability_of_profit(
        _base_row(spread_type="bear_call_credit", lower_strike=90.0, credit=15.0)
    )

    assert low_be < mid_be < high_be


@pytest.mark.parametrize(
    "spread_row",
    [
        _base_row(spread_type="bull_call_debit", lower_strike=92.0, debit=5.0),
        _base_row(spread_type="bear_put_debit", upper_strike=108.0, debit=6.0),
        _base_row(spread_type="bull_put_credit", upper_strike=110.0, credit=4.0),
        _base_row(spread_type="bear_call_credit", lower_strike=90.0, credit=6.0),
    ],
)
def test_probability_is_always_bounded_between_zero_and_one(spread_row: dict) -> None:
    probability = estimate_probability_of_profit(spread_row)
    assert 0.0 <= probability <= 1.0


def test_edge_cases_deep_itm_and_deep_otm_for_above_tail() -> None:
    # bull_call_debit => PoP = P(S_T > BE)
    # Deep ITM: breakeven far below spot -> near 1.
    deep_itm = estimate_probability_of_profit(
        _base_row(
            spread_type="bull_call_debit",
            lower_strike=20.0,
            debit=1.0,
            implied_volatility=0.15,
            time_to_expiration=0.5,
        )
    )
    # Deep OTM: breakeven far above spot -> near 0.
    deep_otm = estimate_probability_of_profit(
        _base_row(
            spread_type="bull_call_debit",
            lower_strike=995.0,
            upper_strike=1200.0,
            debit=5.0,
            implied_volatility=0.15,
            time_to_expiration=0.5,
        )
    )

    assert deep_itm > 0.999
    assert deep_otm < 0.001


def test_edge_cases_deep_itm_and_deep_otm_for_below_tail() -> None:
    # bear_put_debit => PoP = P(S_T < BE)
    # Deep ITM: breakeven far above spot -> near 1.
    deep_itm = estimate_probability_of_profit(
        _base_row(
            spread_type="bear_put_debit",
            upper_strike=200.0,
            debit=1.0,
            implied_volatility=0.15,
            time_to_expiration=0.5,
        )
    )
    # Deep OTM: breakeven far below spot -> near 0.
    deep_otm = estimate_probability_of_profit(
        _base_row(
            spread_type="bear_put_debit",
            lower_strike=1.0,
            upper_strike=25.0,
            debit=24.5,
            implied_volatility=0.15,
            time_to_expiration=0.5,
        )
    )

    assert deep_itm > 0.999
    assert deep_otm < 0.001


def test_near_expiration_approaches_step_function_behavior() -> None:
    tiny_t = 1e-8

    above_when_be_below_spot = estimate_probability_of_profit(
        _base_row(
            spread_type="bull_call_debit",
            lower_strike=90.0,
            debit=9.0,  # BE=99 < spot
            implied_volatility=0.2,
            time_to_expiration=tiny_t,
        )
    )
    above_when_be_above_spot = estimate_probability_of_profit(
        _base_row(
            spread_type="bull_call_debit",
            lower_strike=90.0,
            debit=11.0,  # BE=101 > spot
            implied_volatility=0.2,
            time_to_expiration=tiny_t,
        )
    )

    below_when_be_above_spot = estimate_probability_of_profit(
        _base_row(
            spread_type="bear_call_credit",
            lower_strike=100.0,
            credit=1.0,  # BE=101 > spot
            implied_volatility=0.2,
            time_to_expiration=tiny_t,
        )
    )
    below_when_be_below_spot = estimate_probability_of_profit(
        _base_row(
            spread_type="bear_call_credit",
            lower_strike=98.0,
            credit=1.0,  # BE=99 < spot
            implied_volatility=0.2,
            time_to_expiration=tiny_t,
        )
    )

    assert above_when_be_below_spot > 0.99
    assert above_when_be_above_spot < 0.01
    assert below_when_be_above_spot > 0.99
    assert below_when_be_below_spot < 0.01
