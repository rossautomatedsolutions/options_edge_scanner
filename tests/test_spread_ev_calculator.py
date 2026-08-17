import math

import pytest

from options_edge_scanner.models.spread_ev_calculator import TRANSACTION_COST, calculate_expected_value


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _call_expectation(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> float:
    sigma_t = implied_vol * math.sqrt(time_to_expiration)
    d1 = (
        math.log(spot / strike) + (0.5 * implied_vol * implied_vol * time_to_expiration)
    ) / sigma_t
    d2 = d1 - sigma_t
    return (spot * _normal_cdf(d1)) - (strike * _normal_cdf(d2))


def _put_expectation(spot: float, strike: float, implied_vol: float, time_to_expiration: float) -> float:
    sigma_t = implied_vol * math.sqrt(time_to_expiration)
    d1 = (
        math.log(spot / strike) + (0.5 * implied_vol * implied_vol * time_to_expiration)
    ) / sigma_t
    d2 = d1 - sigma_t
    return (strike * _normal_cdf(-d2)) - (spot * _normal_cdf(-d1))


@pytest.mark.parametrize(
    ("spread", "max_profit", "max_loss"),
    [
        (
            {
                "spread_type": "bull_call_debit",
                "strike_lower": 100,
                "strike_upper": 110,
                "cost": 3,
                "max_profit": 7,
            },
            7,
            3,
        ),
        (
            {
                "spread_type": "bear_put_debit",
                "strike_lower": 100,
                "strike_upper": 110,
                "cost": 4,
                "max_profit": 6,
            },
            6,
            4,
        ),
        (
            {
                "spread_type": "bull_put_credit",
                "short_strike": 110,
                "long_strike": 100,
                "credit": 2,
                "max_loss": 8,
            },
            2,
            8,
        ),
        (
            {
                "spread_type": "bear_call_credit",
                "short_strike": 110,
                "long_strike": 100,
                "credit": 3,
                "max_loss": 7,
            },
            3,
            7,
        ),
    ],
)
def test_ev_bounds_before_transaction_cost(spread, max_profit, max_loss) -> None:
    probabilities = {"win": 0.63, "loss": 0.37}

    result = calculate_expected_value(spread, probability_weights=probabilities)
    ev_gross = result["expected_value"] + TRANSACTION_COST

    assert ev_gross <= max_profit + 1e-12
    assert ev_gross >= -max_loss - 1e-12


@pytest.mark.parametrize(
    "spread",
    [
        {
            "spread_type": "bull_call_debit",
            "strike_lower": 100,
            "strike_upper": 110,
            "cost": 3,
            "max_profit": 7,
        },
        {
            "spread_type": "bear_put_debit",
            "strike_lower": 100,
            "strike_upper": 110,
            "cost": 4,
            "max_profit": 6,
        },
        {
            "spread_type": "bull_put_credit",
            "short_strike": 110,
            "long_strike": 100,
            "credit": 2,
            "max_loss": 8,
        },
        {
            "spread_type": "bear_call_credit",
            "short_strike": 110,
            "long_strike": 100,
            "credit": 3,
            "max_loss": 7,
        },
    ],
)
def test_higher_win_probability_increases_ev(spread) -> None:
    low_win = calculate_expected_value(spread, probability_weights={"win": 0.35, "loss": 0.65})
    high_win = calculate_expected_value(spread, probability_weights={"win": 0.75, "loss": 0.25})

    assert high_win["expected_value"] > low_win["expected_value"]


@pytest.mark.parametrize(
    ("better_ratio_spread", "worse_ratio_spread"),
    [
        (
            {
                "spread_type": "bull_call_debit",
                "strike_lower": 100,
                "strike_upper": 110,
                "cost": 3,
                "max_profit": 7,
            },
            {
                "spread_type": "bull_call_debit",
                "strike_lower": 100,
                "strike_upper": 110,
                "cost": 6,
                "max_profit": 4,
            },
        ),
        (
            {
                "spread_type": "bear_put_debit",
                "strike_lower": 100,
                "strike_upper": 110,
                "cost": 4,
                "max_profit": 6,
            },
            {
                "spread_type": "bear_put_debit",
                "strike_lower": 100,
                "strike_upper": 110,
                "cost": 7,
                "max_profit": 3,
            },
        ),
        (
            {
                "spread_type": "bull_put_credit",
                "short_strike": 110,
                "long_strike": 100,
                "credit": 4,
                "max_loss": 6,
            },
            {
                "spread_type": "bull_put_credit",
                "short_strike": 110,
                "long_strike": 100,
                "credit": 2,
                "max_loss": 8,
            },
        ),
        (
            {
                "spread_type": "bear_call_credit",
                "short_strike": 110,
                "long_strike": 100,
                "credit": 5,
                "max_loss": 5,
            },
            {
                "spread_type": "bear_call_credit",
                "short_strike": 110,
                "long_strike": 100,
                "credit": 2,
                "max_loss": 8,
            },
        ),
    ],
)
def test_worse_payoff_ratio_reduces_ev(better_ratio_spread, worse_ratio_spread) -> None:
    probability_weights = {"win": 0.55, "loss": 0.45}

    better = calculate_expected_value(better_ratio_spread, probability_weights=probability_weights)
    worse = calculate_expected_value(worse_ratio_spread, probability_weights=probability_weights)

    assert better["expected_value"] > worse["expected_value"]


@pytest.mark.parametrize(
    ("spread", "max_profit", "max_loss"),
    [
        (
            {
                "spread_type": "bull_call_debit",
                "strike_lower": 100,
                "strike_upper": 110,
                "cost": 3,
                "max_profit": 7,
            },
            7,
            3,
        ),
        (
            {
                "spread_type": "bear_put_debit",
                "strike_lower": 100,
                "strike_upper": 110,
                "cost": 4,
                "max_profit": 6,
            },
            6,
            4,
        ),
        (
            {
                "spread_type": "bull_put_credit",
                "short_strike": 110,
                "long_strike": 100,
                "credit": 2,
                "max_loss": 8,
            },
            2,
            8,
        ),
        (
            {
                "spread_type": "bear_call_credit",
                "short_strike": 110,
                "long_strike": 100,
                "credit": 3,
                "max_loss": 7,
            },
            3,
            7,
        ),
    ],
)
def test_edge_probabilities_match_extreme_payoffs(spread, max_profit, max_loss) -> None:
    all_win = calculate_expected_value(spread, probability_weights={"win": 1.0, "loss": 0.0})
    all_loss = calculate_expected_value(spread, probability_weights={"win": 0.0, "loss": 1.0})

    assert math.isclose(all_win["expected_value"], max_profit - TRANSACTION_COST, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(all_loss["expected_value"], -max_loss - TRANSACTION_COST, rel_tol=0, abs_tol=1e-12)


@pytest.mark.parametrize(
    "aliases",
    [
        {"win": 0.7, "loss": 0.3},
        {"probability_of_profit": 0.7, "probability_of_loss": 0.3},
        {"p_win": 0.7, "p_loss": 0.3},
    ],
)
def test_probability_weight_aliases_work_for_supported_spreads(aliases) -> None:
    spread = {
        "spread_type": "bear_call_credit",
        "short_strike": 110,
        "long_strike": 100,
        "credit": 3,
        "max_loss": 7,
    }

    result = calculate_expected_value(spread, probability_weights=aliases)
    expected = (0.7 * 3) + (0.3 * -7) - TRANSACTION_COST

    assert math.isclose(result["expected_value"], expected, rel_tol=0, abs_tol=1e-12)


@pytest.mark.parametrize(
    "probability_weights",
    [
        {"win": 0.8, "loss": 0.3},
        {"win": -0.1, "loss": 1.1},
        {"win": 1.2, "loss": -0.2},
    ],
)
def test_invalid_probability_weights_raise(probability_weights) -> None:
    spread = {
        "spread_type": "bear_put_debit",
        "strike_lower": 100,
        "strike_upper": 110,
        "cost": 3,
        "max_profit": 7,
    }

    with pytest.raises(ValueError):
        calculate_expected_value(spread, probability_weights=probability_weights)


def test_binary_fallback_compatibility() -> None:
    spread = {"payoff": 1.5, "loss": 3.0}

    result = calculate_expected_value(spread, probability=0.4)
    expected = (0.4 * 1.5) - (0.6 * 3.0) - TRANSACTION_COST

    assert math.isclose(result["expected_value"], expected)
    assert result["ev_method"] == "binary"


def test_exact_lognormal_ev_matches_call_spread_expectation() -> None:
    spread = {
        "spread_type": "bull_call_debit",
        "lower_strike": 100.0,
        "upper_strike": 110.0,
        "debit": 3.0,
        "max_profit": 7.0,
        "underlying_price": 100.0,
        "implied_volatility": 0.20,
        "days_to_expiration": 30.0,
    }

    result = calculate_expected_value(spread)
    expected_payoff = _call_expectation(100.0, 100.0, 0.20, 30.0 / 252.0) - _call_expectation(
        100.0,
        110.0,
        0.20,
        30.0 / 252.0,
    )
    expected_value = expected_payoff - 3.0 - TRANSACTION_COST

    assert result["ev_method"] == "lognormal_vertical_exact"
    assert math.isclose(result["expected_value"], expected_value, rel_tol=0, abs_tol=1e-12)
    assert result["avg_profit"] > 0.0
    assert result["avg_loss"] < 0.0


def test_exact_lognormal_ev_matches_put_spread_expectation() -> None:
    spread = {
        "spread_type": "bear_put_debit",
        "lower_strike": 100.0,
        "upper_strike": 110.0,
        "debit": 2.0,
        "max_profit": 8.0,
        "underlying_price": 100.0,
        "implied_volatility": 0.25,
        "days_to_expiration": 45.0,
    }

    result = calculate_expected_value(spread)
    expected_payoff = _put_expectation(100.0, 110.0, 0.25, 45.0 / 252.0) - _put_expectation(
        100.0,
        100.0,
        0.25,
        45.0 / 252.0,
    )
    expected_value = expected_payoff - 2.0 - TRANSACTION_COST

    assert result["ev_method"] == "lognormal_vertical_exact"
    assert math.isclose(result["expected_value"], expected_value, rel_tol=0, abs_tol=1e-12)
